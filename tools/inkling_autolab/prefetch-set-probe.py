"""Compare Windows prefetch scheduling on disjoint existing Inkling expert sets.

Does not flush caches or modify weights. Cache state is natural/mixed. The timed
touch copies all mapped bytes into preallocated buffers using parallel native
memcpy calls. This isolates page-in plus copy cost, not GEMV/model throughput.
Machine disk counters can include unrelated I/O. Refuses overlap with deployment
ready/full baseline. Own mappings and scratch buffers are released per cohort.
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("C:/Users/devcloud/inkling-autolab"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--buffered", action="store_true",
                        help="compare buffered reads with/without hints against serial-hint mapped copy")
    parser.add_argument("--exclude-report", type=Path,
                        help="exclude every expert already touched by a preceding report")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("refusing to overwrite report")
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
    if args.exclude_report:
        previous = json.loads(args.exclude_report.read_text())
        used = {file["path"] for sample in previous["samples"] for file in sample["files"]}
        paths = [path for path in paths if str(path.relative_to(args.root)) not in used]
    random.Random(22191).shuffle(paths)
    modes = ["read", "serial_read", "serial"] if args.buffered else ["none", "serial", "parallel", "batch"]
    if len(paths) < 6 * len(modes) * 8:
        parser.error("not enough untouched complete production-sized expert bins")
    samples = []
    for block in range(6):
        for offset in range(len(modes)):
            if (args.root / "model-ready.json").exists():
                raise RuntimeError("full baseline may start; component probe stopped")
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

                with ThreadPoolExecutor(max_workers=8) as pool:
                    disk_before = psutil.disk_io_counters()
                    start = time.perf_counter()
                    if mode in ("serial", "serial_read"):
                        for i in range(8):
                            one_prefetch(i)
                    elif mode == "parallel":
                        list(pool.map(one_prefetch, range(8)))
                    elif mode == "batch":
                        if not prefetch(process, 8, ranges, 0):
                            raise ctypes.WinError(ctypes.get_last_error())
                    prefetched = time.perf_counter()
                    if "read" in mode:
                        destinations = list(pool.map(lambda path: path.read_bytes(), cohort))
                    else:
                        list(pool.map(touch, range(8)))
                    end = time.perf_counter()
                    disk_after = psutil.disk_io_counters()
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
              "modes": modes, "excluded_report": str(args.exclude_report) if args.exclude_report else None,
              "concurrent_checkpoint_transfer": True, "full_model_measured": False,
              "bytes_verified": True, "samples": samples, "median_seconds": medians}
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print("median_seconds=" + json.dumps(medians), flush=True)


if __name__ == "__main__":
    main()
