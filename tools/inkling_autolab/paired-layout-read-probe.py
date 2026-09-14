"""Compare original expert allocation with temporary sequential byte-identical copies."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import statistics
import tempfile
from threading import Barrier
import time


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


base = module('read_probe', 'uncached-read-probe.py')
layout = module('extent_metadata', 'file-extent-metadata.py')
RAW_BYTES = 31850496


def run(args):
    native = base.NativeIO()
    extents = layout.ExtentQuery(native)
    trace = json.loads((args.root / '074-cache-confirmation-routes.json').read_text())
    assert trace['correctness_verified'] and trace['output_hash'] == 'ce0fbb9a116d3d09'
    excluded = {(layer['layer'], e) for sample in trace['samples'] for layer in sample['layers']
                for row in layer['routed_experts_per_position'] for e in row}
    previous = set()
    for name, key in (('069-async-read-probe.json', 'samples'), ('073-async-read-paired.json', 'pairs'), ('084-compressed-read-probe.json', 'pairs')):
        for sample in json.loads((args.root / name).read_text())[key]:
            previous.update(str(Path(a['path'])) for a in sample['artifacts'])
    paths = [args.root / f'model/experts/layer_{layer:02}/expert_{expert:03}.bin'
             for layer in range(2, 66) for expert in range(256)
             if (layer, expert) not in excluded
             and str(Path(f'model/experts/layer_{layer:02}/expert_{expert:03}.bin')) not in previous]
    random.Random(920914).shuffle(paths)
    assert len(paths) >= 120
    samples = []
    with tempfile.TemporaryDirectory(prefix='092-layout-fixtures-', dir=args.root) as directory:
        fixtures = []
        for index, path in enumerate(paths[:120]):
            assert not base.active_full(args.root)
            raw = path.read_bytes()
            assert len(raw) == RAW_BYTES
            copy = Path(directory) / f'{index:03}.bin'
            with copy.open('xb', buffering=0) as output:
                assert output.write(raw) == len(raw)
                os.fsync(output.fileno())
            fixtures.append(dict(original=path, copy=copy, sha256=hashlib.sha256(raw).hexdigest(),
                                 original_layout=extents.query(path), copy_layout=extents.query(copy)))
        with ExitStack() as stack:
            outputs = [stack.enter_context(native.buffer(RAW_BYTES)) for _ in range(6)]
            with ThreadPoolExecutor(max_workers=6) as pool:
                ready = Barrier(6)
                warmup = [pool.submit(ready.wait, 10) for _ in range(6)]
                for future in warmup:
                    future.result()
                position = 0
                for block in range(10):
                    for files in (2, 4, 6):
                        assert not base.active_full(args.root)
                        cohort = fixtures[position:position + files]
                        position += files
                        order = ['original', 'copy'] if block % 2 == 0 else ['copy', 'original']
                        elapsed = {}
                        for mode in order:
                            futures = []
                            start = time.perf_counter()
                            try:
                                for index, fixture in enumerate(cohort):
                                    futures.append(pool.submit(native.read, fixture[mode], outputs[index], True))
                                for future in futures:
                                    future.result()
                            finally:
                                wait(futures)  # Keep all native buffers alive on every failure path.
                            elapsed[mode] = time.perf_counter() - start
                            assert [hashlib.sha256(b).hexdigest() for b in outputs[:files]] == [f['sha256'] for f in cohort]
                        sample = dict(block=block, files=files, order=order, seconds=elapsed,
                                      original_over_copy_ratio=elapsed['original'] / elapsed['copy'],
                                      sha256_verified=True,
                                      artifacts=[dict(path=str(f['original'].relative_to(args.root)), sha256=f['sha256'],
                                                      original_layout=f['original_layout'], copy_layout=f['copy_layout']) for f in cohort])
                        samples.append(sample)
                        print(json.dumps(sample), flush=True)
    summaries = []
    for files in (2, 4, 6):
        group = [s for s in samples if s['files'] == files]
        summaries.append(dict(files=files, pairs=len(group), copy_wins=sum(s['original_over_copy_ratio'] > 1 for s in group),
                              median_pair_speedup=statistics.median(s['original_over_copy_ratio'] for s in group),
                              median_seconds={mode: statistics.median(s['seconds'][mode] for s in group) for mode in ('original', 'copy')},
                              median_pair_speedup_by_first_mode={mode: statistics.median(s['original_over_copy_ratio'] for s in group if s['order'][0] == mode) for mode in ('original', 'copy')}))
    artifacts = [a for s in samples for a in s['artifacts']]
    report = dict(scope='paired_uncached_original_vs_sequential_copy_component', full_model_speedup_measured=False,
                  temporary_fixtures_removed=True, cluster_bytes=extents.cluster_bytes,
                  median_physical_runs={mode: statistics.median(a[mode + '_layout']['physical_runs'] for a in artifacts) for mode in ('original', 'copy')},
                  pairs=samples, summaries=summaries,
                  caveats=['Copies differ in disk location and allocation layout; hardware caches remain uncontrolled.',
                           'Balanced AB/BA pairs share file contents, native read APIs, and destination buffers.',
                           'All copy creation, extent queries and SHA checks are outside timing.',
                           'No original model file was replaced or modified. Component gains need full-model validation.'])
    with args.out.open('x') as f:
        json.dump(report, f, indent=2)
    return summaries


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('C:/Users/devcloud/inkling-autolab'))
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error('refusing to overwrite report')
    import msvcrt

    def state(status, **fields):
        path = a.root / 'layout-read-probe-state.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(status=status, pid=os.getpid(), unix=time.time(), **fields), indent=2))
        temporary.replace(path)

    with (a.root / 'layout-read-probe.lock').open('a+b') as owner:
        owner.seek(0)
        msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            state('waiting_for_affinity_sweep')
            deadline = time.monotonic() + 7200
            reports = [a.root / f'{n:03}-affinity-{mask}-{threads}.json' for n, mask, threads in ((89, 65535, 16), (90, 4095, 12), (91, 4095, 16))]
            while base.active_full(a.root) or not all(p.exists() for p in reports):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Affinity trials did not complete')
                time.sleep(15)
            for report in reports:
                data = json.loads(report.read_text())
                assert data['scope'] == 'full_large_model_decode' and len(data['samples']) == 3
                assert data['correctness_verified'] and data['output_hash'] == 'ce0fbb9a116d3d09'
            with (a.root / 'baseline-queue.lock').open('a+b') as slot:
                slot.seek(0)
                msvcrt.locking(slot.fileno(), msvcrt.LK_NBLCK, 1)
                assert not base.active_full(a.root)
                state('probing')
                summaries = run(a)
            state('complete', summaries=summaries, full_model_speedup_measured=False)
        except BaseException as error:
            state('failed', error=str(error))
            raise


if __name__ == '__main__':
    main()
