#!/usr/bin/env python3
"""Run one isolated Windows benchmark job, yielding to existing services/CI.

Uses only the Popen handle of its own child for termination. Never stops,
restarts or reconfigures a service. Job JSON has argv, env, cores, seconds,
min_available_gib, max_rss_gib and label; argv[0] must be inside --root.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

import psutil


def protected():
    names = {"ovms.exe", "cascadia-node.exe", "runnerservice.exe", "runner.listener.exe"}
    result = []
    for p in psutil.process_iter(["name", "create_time"]):
        if (p.info["name"] or "").lower() in names:
            result.append(dict(pid=p.pid, name=p.info["name"], create_time=p.info["create_time"]))
    return result


def ci_active():
    return any((p.info["name"] or "").lower() == "runner.worker.exe"
               for p in psutil.process_iter(["name"]))


def run(root, job):
    root = root.resolve()
    exe = Path(job["argv"][0]).resolve()
    if not exe.is_relative_to(root) or not exe.is_file():
        raise ValueError("benchmark executable must be inside the isolated root")
    label = job["label"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", label):
        raise ValueError("invalid job label")
    seconds = job.get("seconds", 180)
    if not 1 <= seconds <= 600:
        raise ValueError("job duration must be 1..600 seconds")
    cores = job.get("cores", [0, 1])
    if not cores or len(cores) > max(1, psutil.cpu_count() // 2):
        raise ValueError("benchmark may use at most half the logical CPUs")
    floor = job.get("min_available_gib", 12) * 2**30
    if ci_active() or psutil.virtual_memory().available < floor:
        raise RuntimeError("host is busy or below memory reserve; no process started")
    before = protected()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CASCADIA_INKLING_", "CASCADIA_GLM5_"))}
    env.update(job.get("env", {}))
    env["RAYON_NUM_THREADS"] = str(len(cores))
    started = time.monotonic()
    reason = None
    peak_rss = 0
    minimum_available = psutil.virtual_memory().available
    status_path = root / (label + ".status.json")
    if status_path.exists():
        raise FileExistsError(status_path)
    watched = {x["pid"]: psutil.Process(x["pid"]) for x in before
               if x["name"].lower() in {"ovms.exe", "cascadia-node.exe"}}
    for p in watched.values():
        p.cpu_percent()
    # Windows accounts CPU time in coarse ticks. A startup interval of a few
    # milliseconds can report a large percentage for one background tick;
    # retain the same threshold, but always measure a full 500 ms window.
    next_service_sample = time.monotonic() + 0.5

    def service_busy():
        nonlocal next_service_sample
        now = time.monotonic()
        if now < next_service_sample:
            return False
        next_service_sample = now + 0.5
        return any(p.cpu_percent() > 20 for p in watched.values() if p.is_running())

    with (root / (label + ".log")).open("x") as log:
        child = subprocess.Popen(job["argv"], cwd=root, env=env, stdout=log,
                                 stderr=subprocess.STDOUT, creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        proc = psutil.Process(child.pid)
        try:
            proc.cpu_affinity(cores)
            status_path.write_text(json.dumps(dict(state="running", pid=child.pid, exe=str(exe), job=job)))
            while child.poll() is None:
                available = psutil.virtual_memory().available
                minimum_available = min(minimum_available, available)
                try:
                    rss = proc.memory_info().rss
                except psutil.NoSuchProcess:
                    break
                peak_rss = max(peak_rss, rss)
                if time.monotonic() - started > seconds:
                    reason = "lease expired"
                elif ci_active():
                    reason = "CI job started"
                elif available < floor:
                    reason = "available memory below reserve"
                elif rss > job.get("max_rss_gib", 10) * 2**30:
                    reason = "benchmark RSS exceeded cap"
                elif service_busy():
                    reason = "existing inference service became busy"
                if reason:
                    break
                time.sleep(0.5)
        finally:
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    after = protected()
    result = dict(state="finished", returncode=child.returncode, stop_reason=reason,
                  elapsed_seconds=time.monotonic()-started, peak_rss_gib=peak_rss/2**30,
                  minimum_available_gib=minimum_available/2**30, protected_before=before,
                  protected_after=after, protected_processes_unchanged=before == after,
                  job=job)
    status_path.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result))
    if child.returncode or reason:
        raise SystemExit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--job", type=Path, required=True)
    a = p.parse_args()
    run(a.root, json.loads(a.job.read_text()))
