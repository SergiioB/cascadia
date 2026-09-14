"""Matched PTL uncached reads versus temporary Zstd reads plus decompression.

This component experiment starts only after row trials076–080. It never changes
the model export. Temporary compressed fixtures are removed on completion.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import ExitStack, contextmanager
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import statistics
import tempfile
import time

spec = importlib.util.spec_from_file_location('read_probe', Path(__file__).with_name('uncached-read-probe.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
RAW_BYTES = 31850496
DLL = Path('C:/msys64/mingw64/bin/libzstd.dll')
DLL_SHA = 'b95c223a9548a9ecf51377c962e0bc8f0c51eb0c6f67a296dbc885996f0dd40d'


class Codec:
    def __init__(self):
        assert hashlib.sha256(DLL.read_bytes()).hexdigest() == DLL_SHA
        self.lib = C.CDLL(str(DLL))
        signatures = {
            'ZSTD_versionString': (C.c_char_p, []),
            'ZSTD_isError': (C.c_uint, [C.c_size_t]),
            'ZSTD_getErrorName': (C.c_char_p, [C.c_size_t]),
            'ZSTD_compressBound': (C.c_size_t, [C.c_size_t]),
            'ZSTD_compress': (C.c_size_t, [C.c_void_p, C.c_size_t, C.c_void_p, C.c_size_t, C.c_int]),
            'ZSTD_createDCtx': (C.c_void_p, []),
            'ZSTD_freeDCtx': (C.c_size_t, [C.c_void_p]),
            'ZSTD_decompressDCtx': (C.c_size_t, [C.c_void_p, C.c_void_p, C.c_size_t, C.c_void_p, C.c_size_t]),
        }
        for name, (result, args) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, args

    def checked(self, code):
        if self.lib.ZSTD_isError(code):
            raise ValueError(self.lib.ZSTD_getErrorName(code).decode())
        return code

    def compress(self, raw):
        source = C.create_string_buffer(raw)
        target = C.create_string_buffer(self.lib.ZSTD_compressBound(len(raw)))
        size = self.checked(self.lib.ZSTD_compress(target, len(target), source, len(raw), 1))
        return target.raw[:size]

    @contextmanager
    def context(self):
        context = self.lib.ZSTD_createDCtx()
        if not context:
            raise MemoryError('ZSTD_createDCtx')
        try:
            yield context
        finally:
            self.checked(self.lib.ZSTD_freeDCtx(context))

    def decode(self, context, source, size, destination):
        assert 0 <= size <= len(source)
        result = self.checked(self.lib.ZSTD_decompressDCtx(
            context, C.addressof(destination), len(destination), C.addressof(source), size))
        if result != len(destination):
            raise ValueError('decoded expert length differs from destination')

    def canary(self):
        expected = bytes(range(256)) * 256
        packed = self.compress(expected)
        source = C.create_string_buffer(packed)
        target = C.create_string_buffer(len(expected))
        with self.context() as context:
            self.decode(context, source, len(packed), target)
            assert target.raw == expected
            for src, size, dst in ((source, len(packed) - 1, target),
                                   (source, len(packed), C.create_string_buffer(4096)),
                                   (C.create_string_buffer(b'not a frame'), 11, target)):
                try:
                    self.decode(context, src, size, dst)
                except ValueError:
                    pass
                else:
                    raise AssertionError('invalid frame/output size was accepted')
            self.decode(context, source, len(packed), target)
            assert target.raw == expected
        return True


def drained_map(pool, function, items):
    # An exception in one task must not free another task's native buffers.
    futures = []
    try:
        for item in items:
            futures.append(pool.submit(function, item))
        return [future.result() for future in futures]
    finally:
        wait(futures)


def run(args):
    codec, native = Codec(), base.NativeIO()
    assert codec.canary()
    trace = json.loads((args.root / '074-cache-confirmation-routes.json').read_text())
    assert trace['correctness_verified'] and trace['output_hash'] == 'ce0fbb9a116d3d09'
    excluded = {(layer['layer'], e) for sample in trace['samples'] for layer in sample['layers']
                for row in layer['routed_experts_per_position'] for e in row}
    previous = set()
    for name, key in (('069-async-read-probe.json', 'samples'), ('073-async-read-paired.json', 'pairs')):
        for sample in json.loads((args.root / name).read_text())[key]:
            previous.update(str(Path(a['path'])) for a in sample['artifacts'])
    paths = [args.root / f'model/experts/layer_{layer:02}/expert_{expert:03}.bin'
             for layer in range(2, 66) for expert in range(256)
             if (layer, expert) not in excluded
             and str(Path(f'model/experts/layer_{layer:02}/expert_{expert:03}.bin')) not in previous]
    random.Random(840914).shuffle(paths)
    assert len(paths) >= 120
    samples = []
    with tempfile.TemporaryDirectory(prefix='084-codec-fixtures-', dir=args.root) as directory:
        fixtures = []
        for index, path in enumerate(paths[:120]):
            assert not base.active_full(args.root)
            raw = path.read_bytes()
            assert len(raw) == RAW_BYTES
            packed = codec.compress(raw)
            padding = (-len(packed)) % 4096
            destination = Path(directory) / f'{index:03}.zst-padded'
            with destination.open('xb') as output:
                output.write(packed)
                output.write(bytes(padding))
                output.flush()
                os.fsync(output.fileno())
            fixtures.append(dict(original=path, packed=destination, packed_bytes=len(packed),
                                 padded_bytes=len(packed) + padding, sha256=hashlib.sha256(raw).hexdigest()))
        with ExitStack() as stack:
            outputs = [stack.enter_context(native.buffer(RAW_BYTES)) for _ in range(6)]
            contexts = [stack.enter_context(codec.context()) for _ in range(6)]
            with ThreadPoolExecutor(max_workers=6) as pool:
                position = 0
                for block in range(10):
                    for files in (2, 4, 6):
                        assert not base.active_full(args.root)
                        cohort = fixtures[position:position + files]
                        position += files
                        order = ['original', 'compressed'] if block % 2 == 0 else ['compressed', 'original']
                        elapsed = {}
                        with ExitStack() as inputs_stack:
                            inputs = [inputs_stack.enter_context(native.buffer(f['padded_bytes'])) for f in cohort]

                            def execute(item):
                                index, fixture = item
                                if mode == 'original':
                                    native.read(fixture['original'], outputs[index], True)
                                else:
                                    if mode == 'compressed':
                                        native.read(fixture['packed'], inputs[index], True)
                                    codec.decode(contexts[index], inputs[index], fixture['packed_bytes'], outputs[index])

                            # Decode-only runs after both paired arms and uses
                            # already-loaded compressed bytes; no storage I/O.
                            for mode in order + ['decode_only']:
                                start = time.perf_counter()
                                drained_map(pool, execute, enumerate(cohort))
                                elapsed[mode] = time.perf_counter() - start
                                assert [hashlib.sha256(b).hexdigest() for b in outputs[:files]] == [f['sha256'] for f in cohort]
                        sample = dict(block=block, files=files, order=order, seconds=elapsed,
                                      original_over_compressed_ratio=elapsed['original'] / elapsed['compressed'],
                                      sha256_verified=True,
                                      artifacts=[dict(path=str(f['original'].relative_to(args.root)), sha256=f['sha256'],
                                                      packed_bytes=f['packed_bytes'], padded_bytes=f['padded_bytes']) for f in cohort])
                        samples.append(sample)
                        print(json.dumps(sample), flush=True)
    summaries = []
    for files in (2, 4, 6):
        group = [s for s in samples if s['files'] == files]
        summaries.append(dict(files=files, pairs=len(group),
                              compressed_wins=sum(s['original_over_compressed_ratio'] > 1 for s in group),
                              median_pair_speedup=statistics.median(s['original_over_compressed_ratio'] for s in group),
                              median_seconds={mode: statistics.median(s['seconds'][mode] for s in group)
                                              for mode in ('original', 'compressed', 'decode_only')},
                              median_pair_speedup_by_first_mode={mode: statistics.median(s['original_over_compressed_ratio'] for s in group if s['order'][0] == mode)
                                                                 for mode in ('original', 'compressed')}))
    assert hashlib.sha256(DLL.read_bytes()).hexdigest() == DLL_SHA
    result = dict(scope='paired_uncached_compressed_read_component', full_model_speedup_measured=False,
                  codec=codec.lib.ZSTD_versionString().decode(), codec_dll_sha256=hashlib.sha256(DLL.read_bytes()).hexdigest(),
                  codec_level=1, byte_error_canary_verified=True, temporary_fixtures_removed=True,
                  pairs=samples, summaries=summaries,
                  caveats=['Original and temporary compressed files have different disk locations; hardware caches are uncontrolled.',
                           'Every pair alternates arm order; input allocation and all SHA checks are outside timing.',
                           'This measures reads plus decoding, not GEMV overlap or full-model throughput.'])
    with args.out.open('x') as output:
        json.dump(result, output, indent=2)
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
        path = a.root / 'compressed-read-probe-state.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(status=status, pid=os.getpid(), unix=time.time(), **fields), indent=2))
        temporary.replace(path)

    with (a.root / 'compressed-read-probe.lock').open('a+b') as owner:
        owner.seek(0)
        msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            state('waiting_for_row_sweep')
            deadline = time.monotonic() + 7200
            reports = [a.root / f'{n:03}-rows-{b}-{i}.json' for n, b, i in ((76, 2, 4), (77, 1, 4), (78, 4, 4), (79, 2, 1), (80, 2, 2))]
            while base.active_full(a.root) or not all(p.exists() for p in reports):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Row trials did not complete')
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
