"""Compare cached/uncached Win32 reads after the repeated full trial completes.

Read-only model probe: identical aligned buffers/APIs, disjoint cohorts, no
cache flush. Hardware caches remain uncontrolled. No inference speed claim.
Alignment contract: https://learn.microsoft.com/en-us/windows/win32/fileio/file-buffering
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
import ctypes as C
import hashlib
import json
import mmap
import os
from pathlib import Path
import random
import statistics
import tempfile
import time

import psutil


class StorageInfo(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in (
        'logical', 'physical_atomic', 'physical_performance', 'effective_physical',
        'flags', 'sector_offset', 'partition_offset')]


class NativeIO:
    def __init__(self):
        self.k = C.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateFileW': (C.c_void_p, [C.c_wchar_p, C.c_uint32, C.c_uint32, C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p]),
            'CloseHandle': (C.c_int, [C.c_void_p]),
            'GetFileSizeEx': (C.c_int, [C.c_void_p, C.POINTER(C.c_int64)]),
            'GetFileInformationByHandleEx': (C.c_int, [C.c_void_p, C.c_int, C.c_void_p, C.c_uint32]),
            'ReadFile': (C.c_int, [C.c_void_p, C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32), C.c_void_p]),
            'VirtualAlloc': (C.c_void_p, [C.c_void_p, C.c_size_t, C.c_uint32, C.c_uint32]),
            'VirtualFree': (C.c_int, [C.c_void_p, C.c_size_t, C.c_uint32]),
        }
        for name, (result, args) in signatures.items():
            function = getattr(self.k, name)
            function.restype, function.argtypes = result, args

    @contextmanager
    def handle(self, path, uncached=False):
        # Read access only; share existing immutable mappings. Only this flag
        # differs between the two measured modes. No OVERLAPPED/asynchronous I/O.
        handle = self.k.CreateFileW(str(path), 0x80000000, 7, None, 3,
                                    0x80 | (0x20000000 if uncached else 0), None)
        if handle == C.c_void_p(-1).value:
            raise C.WinError(C.get_last_error())
        try:
            yield handle
        finally:
            if not self.k.CloseHandle(handle):
                raise C.WinError(C.get_last_error())

    def storage(self, handle):
        info = StorageInfo()
        if not self.k.GetFileInformationByHandleEx(handle, 16, C.byref(info), C.sizeof(info)):
            raise C.WinError(C.get_last_error())
        return {name: getattr(info, name) for name, _ in info._fields_}

    @contextmanager
    def buffer(self, size):
        pointer = self.k.VirtualAlloc(None, size, 0x3000, 0x04)
        if not pointer:
            raise C.WinError(C.get_last_error())
        try:
            C.memset(pointer, 0, size)  # Touch private pages once, outside read timing.
            yield (C.c_ubyte * size).from_address(pointer)
        finally:
            if not self.k.VirtualFree(pointer, 0, 0x8000):
                raise C.WinError(C.get_last_error())

    def read(self, path, destination, uncached):
        with self.handle(path, uncached) as handle:
            size = C.c_int64()
            if not self.k.GetFileSizeEx(handle, C.byref(size)):
                raise C.WinError(C.get_last_error())
            if size.value != len(destination):
                raise ValueError('expert size differs from destination')
            info = self.storage(handle)
            alignment = max(info[name] for name in ('logical', 'physical_atomic', 'physical_performance', 'effective_physical'))
            pointer = C.addressof(destination)
            if (not info['logical'] or not alignment or alignment & (alignment - 1)
                    or pointer % alignment or len(destination) % alignment):
                raise ValueError(f'incompatible aligned destination: {info}')
            position = 0
            while position < len(destination):
                count = C.c_uint32()
                remaining = len(destination) - position
                if remaining > 0xffffffff or position % alignment:
                    raise ValueError('unaligned short read or oversized request')
                if not self.k.ReadFile(handle, pointer + position, remaining, C.byref(count), None):
                    raise C.WinError(C.get_last_error())
                if not 0 < count.value <= remaining:
                    raise EOFError('incomplete expert read')
                position += count.value


def active_full(root):
    prefix = str((root / 'bin').resolve()).lower() + '\\'
    return [p.pid for p in psutil.process_iter(['exe', 'name'])
            if (p.info['exe'] or '').lower().startswith(prefix)
            and (p.info['name'] or '').lower().startswith('full-')]


def run(args):
    native = NativeIO()
    # Functional check uses only a small task-owned file, after the full run.
    with tempfile.TemporaryDirectory(prefix='uncached-canary-', dir=args.root) as directory:
        path = Path(directory) / 'known.bin'
        expected = bytes(range(256)) * 256
        with path.open('wb') as output:
            output.write(expected)
            output.flush()
            os.fsync(output.fileno())
        with native.handle(path) as handle:
            storage = native.storage(handle)
        with native.buffer(len(expected)) as buffer:
            for uncached in (False, True):
                native.read(path, buffer, uncached)
                assert bytes(buffer) == expected
            try:
                native.read(path.with_name('missing.bin'), buffer, True)
            except OSError:
                pass
            else:
                raise AssertionError('missing file was accepted')
            short = path.with_name('short.bin')
            short.write_bytes(expected[:4096])
            try:
                native.read(short, buffer, True)
            except ValueError:
                pass
            else:
                raise AssertionError('short file was accepted')
        with native.buffer(len(expected) + 4096) as storage_buffer:
            misaligned = (C.c_ubyte * len(expected)).from_address(C.addressof(storage_buffer) + 1)
            try:
                native.read(path, misaligned, True)
            except ValueError:
                pass
            else:
                raise AssertionError('misaligned destination was accepted')
    paths = [p for layer in range(2, 22)
             for p in sorted((args.root / f'model/experts/layer_{layer:02}').glob('expert_[0-9][0-9][0-9].bin'))
             if p.stat().st_size == 31850496]
    excluded = set()
    for report in args.exclude_report:
        excluded.update(f['path'] for s in json.loads(report.read_text())['samples'] for f in s['files'])
    trace = json.loads(args.exclude_trace.read_text())
    assert trace['full_model'] and trace['correctness_verified'] and trace['output_hash'] == 'ce0fbb9a116d3d09'
    for sample in trace['samples']:
        for layer in sample['layers']:
            for expert in {e for row in layer['routed_experts_per_position'] for e in row}:
                excluded.add(str(Path(f"model/experts/layer_{layer['layer']:02}/expert_{expert:03}.bin")))
    paths = [p for p in paths if str(p.relative_to(args.root)) not in excluded]
    random.Random(380619).shuffle(paths)
    assert len(paths) >= 96, 'not enough unused expert bins'
    samples = []
    process = psutil.Process()
    setup = time.perf_counter()
    with ExitStack() as stack:
        buffers = [stack.enter_context(native.buffer(31850496)) for _ in range(8)]
        setup = time.perf_counter() - setup
        with ThreadPoolExecutor(max_workers=8) as pool:
            for block in range(6):
                for uncached in ((False, True) if block % 2 == 0 else (True, False)):
                    assert not active_full(args.root), 'full benchmark started during probe'
                    cohort = paths[len(samples) * 8:(len(samples) + 1) * 8]
                    before_disk, before_cpu = psutil.disk_io_counters(), process.cpu_times()
                    before_faults = process.memory_info().num_page_faults
                    start = time.perf_counter()
                    list(pool.map(lambda pair: native.read(pair[0], pair[1], uncached), zip(cohort, buffers)))
                    seconds = time.perf_counter() - start
                    after_disk, after_cpu = psutil.disk_io_counters(), process.cpu_times()
                    faults = process.memory_info().num_page_faults - before_faults
                    hashes = []
                    for path, buffer in zip(cohort, buffers):
                        copied = hashlib.sha256(buffer).hexdigest()
                        with path.open('rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as mapping:
                            assert copied == hashlib.sha256(mapping).hexdigest(), 'read bytes differ'
                        hashes.append({'path': str(path.relative_to(args.root)), 'sha256': copied})
                    sample = dict(mode='uncached' if uncached else 'cached', block=block, seconds=seconds,
                                  bytes=8 * 31850496, files=hashes, sha256_verified=True,
                                  process_faults_includes_soft=faults,
                                  user_cpu_seconds=after_cpu.user - before_cpu.user,
                                  kernel_cpu_seconds=after_cpu.system - before_cpu.system,
                                  machine_disk_read_bytes=after_disk.read_bytes - before_disk.read_bytes)
                    samples.append(sample)
                    print(json.dumps(sample), flush=True)
    result = dict(scope='windows_cached_vs_uncached_read_component', full_model_measured=False,
                  cache_state='natural_mixed_no_flush', excludes_observed_full_routes=True,
                  storage_info=storage, canary_bytes_verified=True, buffer_setup_seconds=setup,
                  reusable_buffer_bytes=8 * 31850496, samples=samples,
                  median_seconds={mode: statistics.median(s['seconds'] for s in samples if s['mode'] == mode)
                                  for mode in ('cached', 'uncached')})
    with args.out.open('x') as output:
        json.dump(result, output, indent=2)
    return result['median_seconds']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('C:/Users/devcloud/inkling-autolab'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--exclude-report', type=Path, action='append', default=[])
    parser.add_argument('--exclude-trace', type=Path, required=True)
    parser.add_argument('--wait', action='store_true', help='wait at most two hours for036')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('refusing to overwrite report')
    import msvcrt
    state_path = args.root / 'uncached-probe-state.json'
    def state(status, **fields):
        temporary = state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(status=status, pid=os.getpid(), unix=time.time(), **fields), indent=2))
        temporary.replace(state_path)
    with (args.root / 'uncached-probe.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            state('waiting_for_036')
            deadline = time.monotonic() + 7200
            report = args.root / '036-buffered.json'
            while active_full(args.root) or not report.exists():
                if not args.wait or time.monotonic() >= deadline:
                    raise RuntimeError('036 must finish and all full processes must exit before this probe')
                time.sleep(15)
            result = json.loads(report.read_text())
            assert result['scope'] == 'full_large_model_decode' and result['correctness_verified']
            assert result['output_hash'] == 'ce0fbb9a116d3d09' and len(result['samples']) == 9
            with (args.root / 'baseline-queue.lock').open('a+b') as slot:
                slot.seek(0)
                msvcrt.locking(slot.fileno(), msvcrt.LK_NBLCK, 1)
                assert not active_full(args.root), 'another full process started'
                state('probing')
                medians = run(args)
            state('complete', median_seconds=medians, full_model_speedup_measured=False)
        except BaseException as error:
            state('failed', error=str(error))
            raise


if __name__ == '__main__':
    main()
