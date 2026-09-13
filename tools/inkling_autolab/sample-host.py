"""Observe task-owned full decode processes without changing their execution.

Requires psutil (already in the PTL environment). Disk counters are machine-wide,
not attributed to the model; process page faults include soft faults. Sampling
overhead remains part of observed benchmark timing. No process is stopped.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import time

import psutil


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def snapshot(root):
    processes = []
    for process in psutil.process_iter(["pid", "name"]):
        if not (process.info["name"] or "").lower().startswith("full-"):
            continue
        try:
            executable = Path(process.exe()).resolve()
            if executable.parent != (root / "bin").resolve():
                continue
            with process.oneshot():
                processes.append({
                    "pid": process.pid, "created_unix": process.create_time(),
                    "executable": str(executable), "cpu_seconds": process.cpu_times()._asdict(),
                    "memory_info": process.memory_info()._asdict(),
                    "io_cumulative": process.io_counters()._asdict(),
                    "threads": process.num_threads(),
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    disk = psutil.disk_io_counters()
    return {
        "unix": time.time(), "monotonic": time.monotonic(), "hostname": socket.gethostname(),
        "sampler_pid": os.getpid(), "processes": processes,
        "cpu_percent_per_logical_processor": psutil.cpu_percent(percpu=True),
        "memory": psutil.virtual_memory()._asdict(),
        "swap": psutil.swap_memory()._asdict(),
        "machine_disk_io_cumulative": disk._asdict() if disk else None,
        "baseline_queue": read_json(root / "baseline-queue-state.json"),
        "transfer": read_json(root / "transfer-state.json"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("C:/Users/devcloud/inkling-autolab"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--hours", type=float, default=96)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--follow-trials", action="store_true",
                        help="continue across gaps between candidates after the baseline ends")
    parser.add_argument("--stop-file", type=Path,
                        help="stop when this new marker under the task root is created")
    args = parser.parse_args()
    if not args.root.is_dir() or args.interval < 5 or not 0 < args.hours <= 96:
        parser.error("existing root, interval >=5 seconds and 0<hours<=96 required")
    if args.once:
        print(json.dumps(snapshot(args.root)))
        return
    if not args.out:
        parser.error("--out is required; existing reports are never overwritten")
    if args.follow_trials and not args.stop_file:
        parser.error("--follow-trials requires --stop-file for explicit campaign cleanup")
    if args.stop_file and (args.stop_file.parent.resolve() != args.root.resolve()
                          or args.stop_file.exists() or args.stop_file.resolve() == args.out.resolve()):
        parser.error("--stop-file must be a new, distinct marker directly under --root")
    import msvcrt
    with (args.root / "host-sampler.lock").open("a+b") as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        with args.out.open("x", encoding="utf-8", buffering=1) as output:
            deadline = time.monotonic() + args.hours * 3600
            while time.monotonic() < deadline:
                if args.stop_file and args.stop_file.exists():
                    break
                sample = snapshot(args.root)
                sample["follow_trials"] = args.follow_trials
                output.write(json.dumps(sample) + "\n")
                queue = sample["baseline_queue"] or {}
                if not args.follow_trials and not sample["processes"] and queue.get("status") in (
                        "failed", "baseline_recorded_needs_review"):
                    break
                time.sleep(args.interval)


if __name__ == "__main__":
    main()
