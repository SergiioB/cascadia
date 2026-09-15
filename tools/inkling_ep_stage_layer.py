#!/usr/bin/env python3
"""Download an explicit expert list at a bounded rate, verifying source SHA256.

Downloads into the isolated job root only; stops for active CI or low free disk.
Existing complete files resume, unrelated data is never removed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request

from inkling_ep_guard import ci_active


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--files", type=Path, required=True)
    p.add_argument("--mib-per-second", type=float, default=48)
    a = p.parse_args()
    if not 0 < a.mib_per_second <= 100:
        p.error("rate must be positive and <=100 MiB/s")
    files = json.loads(a.files.read_text())
    if any(not isinstance(x, str) or Path(x).name != x or not x.endswith(".bin") for x in files):
        raise ValueError("file list must contain simple .bin names")
    with urllib.request.urlopen(a.source + "/index.json", timeout=30) as r:
        index = json.load(r)
    target = a.root / "layer/experts/layer_02"
    target.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    transferred = 0
    for name in files:
        if ci_active():
            raise RuntimeError("CI job started; transfer paused before next expert")
        meta = index[name]
        dest = target / name
        if dest.exists():
            with dest.open("rb") as f:
                if hashlib.file_digest(f, "sha256").hexdigest() == meta["sha256"]:
                    continue
            raise RuntimeError("existing expert differs from source: " + name)
        if shutil.disk_usage(target).free - meta["bytes"] < 80 * 2**30:
            raise RuntimeError("preserving at least 80 GiB free disk")
        h = hashlib.sha256()
        count = 0
        part = dest.with_suffix(".bin.part")
        with urllib.request.urlopen(a.source + "/" + name, timeout=60) as r, part.open("wb") as f:
            while chunk := r.read(2**20):
                f.write(chunk)
                h.update(chunk)
                count += len(chunk)
                transferred += len(chunk)
                delay = transferred / (a.mib_per_second * 2**20) - (time.monotonic() - started)
                if delay > 0:
                    time.sleep(min(delay, 0.1))
        if count != meta["bytes"] or h.hexdigest() != meta["sha256"]:
            raise RuntimeError("expert checksum failed: " + name)
        part.replace(dest)
    report = dict(files=len(files), transferred_bytes=transferred, elapsed_seconds=time.monotonic()-started,
                  source=a.source, source_index=index, scope="one MoE layer of real 975B weights")
    (a.root / "layer-transfer.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k != "source_index"}))


if __name__ == "__main__":
    main()
