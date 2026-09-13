"""Compare Windows prefetch scheduling on disjoint existing Inkling expert sets.

Does not flush caches or modify weights. Cache state is natural/mixed. The timed
touch copies all mapped bytes into preallocated buffers using parallel native
memcpy calls. This isolates page-in plus copy cost, not GEMV/model throughput.
Machine disk counters can include unrelated I/O. Refuses overlap with deployment
ready/full baseline unless --after-baseline explicitly checks for its completion.
The optional reused buffer pool is allocated once outside steady-state timing.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
import hashlib
import json
import mmap
from pathlib import Path
import random
import statistics
import time

import psutil


class Range(ctypes.Structure):
    _fields_ = [("address", ctypes.c_void_p), ("size", ctypes.c_size_t)]


def read_exact_into(file, destination):
    """Fill existing storage, including short-read handling; no full-size copy."""
    with memoryview(destination).cast('B') as view:
        position = 0
        while position < len(view):
            count = file.readinto(view[position:])
            if not count:
                raise EOFError('expert ended before the destination was filled')
            position += count
        if file.read(1):
            raise ValueError('expert has trailing bytes beyond the expected size')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("C:/Users/devcloud/inkling-autolab"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--buffered", action="store_true",
                        help="compare buffered reads with/without hints against serial-hint mapped copy")
    parser.add_argument("--reuse-buffered", action="store_true",
                        help="add steady-state readinto comparisons using eight reused buffers")
    parser.add_argument("--after-baseline", action="store_true",
                        help="require completed baseline and native qualification, with no full process")
    parser.add_argument("--exclude-report", type=Path, action='append', default=[],
                        help="exclude every expert already touched by a preceding report")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("refusing to overwrite report")
    if args.reuse_buffered and not args.buffered:
        parser.error('--reuse-buffered requires --buffered')

    def check_idle():
        if args.after_baseline:
            for name, expected in [('baseline-queue-state.json', 'baseline_recorded_needs_review'),
                                   ('mmap-qualification-state.json', 'qualified_needs_full_trial')]:
                if json.loads((args.root / name).read_text()).get('status') != expected:
                    raise RuntimeError('baseline/native qualification must complete first')
            for candidate in psutil.process_iter(['exe']):
                exe = candidate.info['exe'] or ''
                if exe.lower().startswith(str(args.root / 'bin').lower() + '\\') and Path(exe).name.lower().startswith('full-'):
                    raise RuntimeError(f'full benchmark active: {candidate.pid}')
        elif (args.root / "model-ready.json").exists():
            raise RuntimeError("full baseline may start; component probe stopped")

    check_idle()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    prefetch = kernel.PrefetchVirtualMemory
    prefetch.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(Range), ctypes.c_ulong]
    prefetch.restype = ctypes.c_int
    memcpy = ctypes.CDLL("msvcrt").memcpy
    memcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    memcpy.restype = ctypes.c_void_p
    process = kernel.GetCurrentProcess()
    paths = []
    for layer in range(2, 22):
        paths += sorted((args.root / f"model/experts/layer_{layer:02}").glob("expert_[0-9][0-9][0-9].bin"))
    paths = [path for path in paths if path.stat().st_size == 31850496]
    for report in args.exclude_report:
        previous = json.loads(report.read_text())
        used = {file["path"] for sample in previous["samples"] for file in sample["files"]}
        paths = [path for path in paths if str(path.relative_to(args.root)) not in used]
    random.Random(22191).shuffle(paths)
    modes = ["read", "serial_read", "serial"] if args.buffered else ["none", "serial", "parallel", "batch"]
    if args.reuse_buffered:
        modes += ['reuse_read', 'serial_reuse_read']
    if len(paths) < 6 * len(modes) * 8:
        parser.error("not enough untouched complete production-sized expert bins")
    samples = []
    setup_start = time.perf_counter()
    reused = [ctypes.create_string_buffer(31850496) for _ in range(8)] if args.reuse_buffered else []
    buffer_setup_seconds = time.perf_counter() - setup_start
    this_process = psutil.Process()
    for block in range(6):
        for offset in range(len(modes)):
            check_idle()
            mode = modes[(offset + block) % len(modes)]
            cohort = paths[len(samples) * 8:(len(samples) + 1) * 8]
            files, maps, destinations = [], [], []
            try:
                for path in cohort:
                    file = path.open("rb")
                    files.append(file)
                    # ACCESS_COPY permits obtaining an address; no mapped bytes
                    # are written, and writes could never change the source file.
                    maps.append(mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_COPY))
                    if "read" not in mode:
                        destinations.append(ctypes.create_string_buffer(path.stat().st_size))
                if 'reuse' in mode:
                    destinations = reused
                ranges = (Range * len(maps))(*[
                    Range(ctypes.addressof(ctypes.c_char.from_buffer(mapping)), len(mapping))
                    for mapping in maps])

                def one_prefetch(index):
                    entry = ranges[index]
                    ok = prefetch(process, 1, ctypes.byref(entry), 0)
                    if not ok:
                        raise ctypes.WinError(ctypes.get_last_error())

                def touch(index):
                    memcpy(destinations[index], ranges[index].address, ranges[index].size)

                def read_reused(index):
                    # Include open/close inside timing, as path.read_bytes()
                    # does for the allocating control. Only storage is reused.
                    with cohort[index].open('rb', buffering=0) as source:
                        read_exact_into(source, destinations[index])

                with ThreadPoolExecutor(max_workers=8) as pool:
                    disk_before = psutil.disk_io_counters()
                    faults_before = this_process.memory_info().num_page_faults
                    start = time.perf_counter()
                    if mode in ("serial", "serial_read", "serial_reuse_read"):
                        for i in range(8):
                            one_prefetch(i)
                    elif mode == "parallel":
                        list(pool.map(one_prefetch, range(8)))
                    elif mode == "batch":
                        if not prefetch(process, 8, ranges, 0):
                            raise ctypes.WinError(ctypes.get_last_error())
                    prefetched = time.perf_counter()
                    if 'reuse' in mode:
                        list(pool.map(read_reused, range(8)))
                    elif "read" in mode:
                        destinations = list(pool.map(lambda path: path.read_bytes(), cohort))
                    else:
                        list(pool.map(touch, range(8)))
                    end = time.perf_counter()
                    disk_after = psutil.disk_io_counters()
                    faults_after = this_process.memory_info().num_page_faults
                hashes = []
                for path, mapping, destination in zip(cohort, maps, destinations):
                    assert len(destination) == len(mapping)
                    copied = hashlib.sha256(destination).hexdigest()
                    assert copied == hashlib.sha256(mapping).hexdigest(), "native copy differs from mapping"
                    hashes.append({"path": str(path.relative_to(args.root)), "sha256": copied})
                sample = {"mode": mode, "block": block, "bytes": sum(len(m) for m in maps),
                          "prefetch_seconds": prefetched - start, "touch_seconds": end - prefetched,
                          "total_seconds": end - start, "sha256_verified": True, "files": hashes,
                          "machine_disk_read_bytes": disk_after.read_bytes - disk_before.read_bytes,
                          "machine_disk_read_count": disk_after.read_count - disk_before.read_count}
                sample['process_page_faults_includes_soft_faults'] = faults_after - faults_before
                samples.append(sample)
                print(json.dumps({k: v for k, v in sample.items() if k != "files"}), flush=True)
            finally:
                for mapping in maps:
                    mapping.close()
                for file in files:
                    file.close()
    medians = {mode: statistics.median(s["total_seconds"] for s in samples if s["mode"] == mode)
               for mode in modes}
    report = {"scope": "real_expert_pagein_copy_component", "cache_state": "natural_mixed_no_flush",
              "modes": modes, "excluded_reports": [str(p) for p in args.exclude_report],
              "concurrent_checkpoint_transfer": not args.after_baseline, "full_model_measured": False,
              "reused_buffer_bytes": sum(len(b) for b in reused), "buffer_setup_seconds": buffer_setup_seconds,
              "allocation_and_touch_of_reused_buffers_excluded_from_steady_state": args.reuse_buffered,
              "bytes_verified": True, "samples": samples, "median_seconds": medians}
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print("median_seconds=" + json.dumps(medians), flush=True)


if __name__ == "__main__":
    main()
