#!/usr/bin/env python3
"""Compare independent CUDA converter processes on the saved 64-expert byte oracle.

Only synthetic experts are generated. Startup/generation/hash checks are outside
the conversion timer; source reads, GPU copies, packing and fsynced writes are
inside it. Every worker owns disjoint expert files. CPU affinity bounds its pool.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time


def wait_paths(paths, children=(), parent=None):
    deadline = time.monotonic() + 180
    while not all(path.exists() for path in paths):
        if parent is not None and os.getppid() != parent:
            raise RuntimeError('Benchmark parent exited')
        if any(child.poll() is not None for child in children):
            raise RuntimeError('Converter exited before completing the barrier; inspect worker logs')
        if time.monotonic() > deadline:
            raise TimeoutError('Converter barrier timed out')
        time.sleep(.002)


def worker(path):
    config = json.loads(path.read_text())
    os.sched_setaffinity(0, config['cpus'])
    import torch
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import export_inkling as exporter
    torch.set_num_threads(max(1, len(config['cpus']) // config['workers']))
    packer = exporter.make_packer(f"cuda:{config['gpu']}", 64)
    root = Path(config['root'])
    source = exporter.ShardSource(Path(config['source']))
    try:
        for repetition in range(config['samples']):
            output = root / f'output-{repetition}'
            run = exporter.Exporter(source, config['manifest'], output, workers=config['workers'], packer=packer)
            units = [u for u in run.per_layer[2] if u.kind == 'expert'][config['lo']:config['hi']]
            assert len(units) == config['hi'] - config['lo']
            run.stats = defaultdict(float)
            torch.cuda.synchronize(config['gpu'])
            (root / f"ready-{repetition}-{config['rank']}").touch()
            wait_paths([root / f'start-{repetition}'], parent=config['parent'])
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=config['workers']) as pool:
                counts = run.process(units, pool)
            elapsed = time.perf_counter() - started
            assert counts['direct'] == len(units) and counts['pending'] == 0
            result = {'gpu': config['gpu'], 'rank': config['rank'], 'seconds': elapsed,
                      'experts': len(units), 'workers': config['workers'], 'cpus': config['cpus'],
                      'torch_threads': torch.get_num_threads()}
            done = root / f"done-{repetition}-{config['rank']}.json"
            temporary = done.with_suffix('.tmp')
            temporary.write_text(json.dumps(result))
            temporary.replace(done)
            wait_paths([root / f'ack-{repetition}'], parent=config['parent'])
    finally:
        source.close_handles()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker)
    if not all((args.config, args.reference, args.work_dir, args.out)):
        parser.error('config, reference, work-dir and out are required')
    if args.out.exists():
        parser.error('refusing to overwrite report')
    import torch
    from safetensors.torch import save_file
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import export_inkling as exporter
    if torch.cuda.device_count() < 8:
        parser.error('this bounded experiment requires eight visible NVIDIA GPUs')
    reference = json.loads(args.reference.read_text())
    assert reference['experts'] == 64
    expected = reference['output_sha256']
    assert len(expected) == 64
    manifest = exporter.load_and_validate_config(args.config)
    manifest['num_experts'] = 64
    hidden, intermediate = manifest['hidden_size'], manifest['moe_intermediate']
    assert (hidden, intermediate) == (reference['hidden'], reference['intermediate'])
    cpus = sorted(os.sched_getaffinity(0))
    torch.set_num_threads(max(1, len(cpus) // 8))
    args.work_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    with tempfile.TemporaryDirectory(prefix='export-process-bench-', dir=args.work_dir) as temp:
        root = Path(temp)
        source = root / 'source'
        source.mkdir()
        generator = torch.Generator().manual_seed(8327)
        tensors = {
            'model.llm.layers.2.mlp.experts.w13_weight':
                torch.randn(64, 2 * intermediate, hidden, generator=generator, dtype=torch.bfloat16) * .05,
            'model.llm.layers.2.mlp.experts.w2_weight':
                torch.randn(64, hidden, intermediate, generator=generator, dtype=torch.bfloat16) * .05,
        }
        save_file(tensors, str(source / 'model.safetensors'))
        del tensors
        for count in (1, 4, 8):
            profile = root / f'processes-{count}'
            profile.mkdir()
            children, logs = [], []
            try:
                for rank in range(count):
                    config = {'root': str(profile), 'source': str(source), 'manifest': manifest,
                              'samples': 3, 'rank': rank, 'parent': os.getpid(),
                              'gpu': rank * 8 // count, 'workers': 4 if count == 1 else 1,
                              'cpus': cpus[len(cpus) * rank // count:len(cpus) * (rank + 1) // count],
                              'lo': 64 * rank // count, 'hi': 64 * (rank + 1) // count}
                    path = profile / f'worker-{rank}.json'
                    path.write_text(json.dumps(config))
                    log = (profile / f'worker-{rank}.log').open('w')
                    logs.append(log)
                    children.append(subprocess.Popen([sys.executable, '-u', __file__, '--worker', str(path)],
                                                     stdin=subprocess.DEVNULL, stdout=log, stderr=log))
                for repetition in range(3):
                    wait_paths([profile / f'ready-{repetition}-{rank}' for rank in range(count)], children)
                    started = time.perf_counter()
                    (profile / f'start-{repetition}').touch()
                    paths = [profile / f'done-{repetition}-{rank}.json' for rank in range(count)]
                    wait_paths(paths, children)
                    elapsed = time.perf_counter() - started
                    output = profile / f'output-{repetition}'
                    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in (output / 'experts/layer_02').glob('*.bin')}
                    assert hashes == expected, 'Output differs from the saved CPU oracle'
                    sample = {'processes': count, 'repetition': repetition, 'seconds': elapsed,
                              'experts_per_second': 64 / elapsed, 'sha256_verified': True,
                              'workers': [json.loads(path.read_text()) for path in paths]}
                    samples.append(sample)
                    print(json.dumps(sample), flush=True)
                    shutil.rmtree(output)
                    (profile / f'ack-{repetition}').touch()
                for child in children:
                    assert child.wait(timeout=30) == 0
            finally:
                for child in children:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=10)
                for log in logs:
                    log.close()
    report = {'scope': 'multiprocess_warm_source_expert_subset_with_fsync', 'full_export_measured': False,
              'torch': torch.__version__, 'experts': 64, 'samples': samples,
              'reference_output_sha256': expected,
              'median_seconds': {str(n): statistics.median(s['seconds'] for s in samples if s['processes'] == n)
                                 for n in (1, 4, 8)}}
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'median_seconds': report['median_seconds']}), flush=True)


if __name__ == '__main__':
    main()
