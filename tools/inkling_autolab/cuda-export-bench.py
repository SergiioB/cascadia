"""Compare CPU/CUDA conversion of production-sized experts, including copies and fsync.

This is a warm-source subset benchmark, not a timed export of the 975B checkpoint.
Every output bin must match CPU bytes. Scratch files live in one temporary directory.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import torch
from safetensors.torch import save_file
import export_inkling as exporter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--experts', type=int, default=8)
    parser.add_argument('--samples', type=int, default=3)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--cuda-workers', type=int, help='CUDA I/O workers; defaults to --workers')
    parser.add_argument('--device', default='cuda', help='cuda, cuda:N or cuda:all')
    parser.add_argument('--chunk-mib', type=int, default=64)
    args = parser.parse_args()
    if min(args.experts, args.samples, args.workers) < 1:
        parser.error('experts, samples and workers must be positive')
    if args.cuda_workers is not None and args.cuda_workers < 1:
        parser.error('cuda-workers must be positive')
    if args.out.exists():
        parser.error('refusing to overwrite an existing report')
    man = exporter.load_and_validate_config(args.config)
    man['num_experts'] = args.experts
    hidden, inter = man['hidden_size'], man['moe_intermediate']
    exporter._set_threads(args.workers)
    cuda = exporter.make_packer(args.device, args.chunk_mib)
    device_indices = ([p.device.index for p in cuda.packers] if args.device == 'cuda:all'
                      else [cuda.device.index])
    args.work_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    expected = None
    with tempfile.TemporaryDirectory(prefix='cuda-export-bench-', dir=args.work_dir) as temporary:
        root = Path(temporary)
        source = root / 'source'
        source.mkdir()
        generator = torch.Generator().manual_seed(8327)
        tensors = {
            'model.llm.layers.2.mlp.experts.w13_weight':
                torch.randn(args.experts, 2 * inter, hidden, generator=generator, dtype=torch.bfloat16) * .05,
            'model.llm.layers.2.mlp.experts.w2_weight':
                torch.randn(args.experts, hidden, inter, generator=generator, dtype=torch.bfloat16) * .05,
        }
        source_bytes = sum(w.numel() * w.element_size() for w in tensors.values())
        save_file(tensors, str(source / 'model.safetensors'))
        del tensors
        inputs = exporter.ShardSource(source)
        try:
            # Alternate order after the first reference. Timings include source slice reads,
            # H2D, quantization, D2H, byte serialization and the exporter's atomic fsynced writes.
            for repetition in range(args.samples):
                order = ['cpu', 'cuda'] if repetition % 2 == 0 else ['cuda', 'cpu']
                for device in order:
                    workers = args.workers if device == 'cpu' else (args.cuda_workers or args.workers)
                    exporter._set_threads(workers)
                    destination = root / f'{device}-{repetition}'
                    packer = exporter.pack_int4 if device == 'cpu' else cuda
                    run = exporter.Exporter(inputs, man, destination, workers=workers, packer=packer)
                    selected = [u for u in run.per_layer[2] if u.kind == 'expert'][:args.experts]
                    assert len(selected) == args.experts
                    run.stats = defaultdict(float)
                    for index in device_indices:
                        torch.cuda.synchronize(index)
                        torch.cuda.reset_peak_memory_stats(index)
                    started = time.perf_counter()
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        counts = run.process(selected, pool)
                    elapsed = time.perf_counter() - started
                    assert counts['direct'] == args.experts and counts['pending'] == 0
                    hashes = {u.output.name: hashlib.sha256(u.output.read_bytes()).hexdigest() for u in selected}
                    if expected is None:
                        expected = hashes
                    assert hashes == expected, f'{device} output differs from CPU reference'
                    sample = {'device': device, 'repetition': repetition, 'seconds': elapsed,
                              'workers': workers, 'torch_threads_per_worker': torch.get_num_threads(),
                              'experts_per_second': args.experts / elapsed,
                              'source_bytes': source_bytes,
                              'output_bytes': sum(u.output.stat().st_size for u in selected),
                              'cuda_peak_allocated_bytes': sum(torch.cuda.max_memory_allocated(i) for i in device_indices),
                              'worker_times_sum': dict(run.stats), 'sha256_verified': True}
                    samples.append(sample)
                    print('sample_json=' + json.dumps(sample), flush=True)
                    # The comparison hashes persist; each completed attempt's files are disposable.
                    import shutil
                    shutil.rmtree(destination)
        finally:
            inputs.close_handles()
    medians = {d: statistics.median(s['seconds'] for s in samples if s['device'] == d) for d in ['cpu', 'cuda']}
    report = {'scope': 'warm_source_expert_subset_conversion_with_fsync', 'full_model_export': False,
              'torch': torch.__version__, 'cuda_runtime': torch.version.cuda,
              'gpu': torch.cuda.get_device_name(0), 'cpu_threads': os.cpu_count(),
              'cpu_workers': args.workers, 'cuda_workers': args.cuda_workers or args.workers,
              'cuda_chunk_mib': args.chunk_mib, 'hidden': hidden, 'intermediate': inter,
              'cuda_device': args.device, 'cuda_device_indices': device_indices,
              'experts': args.experts, 'samples': samples, 'median_seconds': medians,
              'speedup': medians['cpu'] / medians['cuda'], 'output_sha256': expected}
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'median_seconds': medians, 'speedup': report['speedup']}), flush=True)
    print(f"export_experts_per_s={args.experts / medians['cuda']:.9f}")
    print('output_hash=' + hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest())
    print('bytes_verified=1')


if __name__ == '__main__':
    main()
