#!/usr/bin/env python3
"""Qualify separate EP worker processes against a local tiny-model oracle.

Makes partial exports: the driver has no MoE bins, workers have only their
placement's bins and manifest. These fixture rates are not 975B measurements.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from inkling_ep_plan import make_plan, shard_files


def copy_files(source, dest, files):
    for name in files:
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new directory for logs/results")
    parser.add_argument("--workers", type=int, default=3, help="number of separate worker processes (1..64)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--owned-workers", action="store_true", help="copy each shard to owned packed bytes once")
    mode.add_argument("--stream-cpu-workers", action="store_true", help="use bounded packed expert reads")
    parser.add_argument("--export", type=Path, default=Path(__file__).resolve().parents[1] /
                        "crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export")
    args = parser.parse_args()
    if not 1 <= args.workers <= 64:
        parser.error("workers must be 1..64")
    args.bin_dir = args.bin_dir.resolve()
    args.out = args.out.resolve()
    manifest = json.loads((args.export / "manifest.json").read_text())
    if manifest["hidden_size"] > 128 or manifest["num_experts"] > 16:
        parser.error("smoke test only accepts a tiny fixture")
    reference = json.loads((args.export / "reference.json").read_text())
    plan = make_plan(manifest, [dict(name=f"worker-{i}", expert_capacity_bytes=1 << 30,
                                    read_us=10, compute_us=1, dispatch_us=2) for i in range(args.workers)])
    args.out.mkdir(parents=True, exist_ok=False)
    placement = args.out / "placement.json"
    placement.write_text(json.dumps(plan, indent=2) + "\n")
    cases = args.out / "cases.json"
    cases.write_text(json.dumps([dict(name="hf-fixture", prompt_ids=reference["prompt_ids"],
                                     greedy_ids=reference["greedy_ids"])]))
    source_files = [str(p.relative_to(args.export)).replace("\\", "/") for p in args.export.rglob("*") if p.is_file()]
    driver_files = [f for f in source_files if not f.startswith("experts/") or f.endswith("/dense.bin")]
    copy_files(args.export, args.out / "driver", driver_files)
    suffix = ".exe" if os.name == "nt" else ""
    bench = args.bin_dir / ("inkling_decode_bench" + suffix)
    worker = args.bin_dir / ("inkling_ep_worker" + suffix)
    # Isolate correctness from inherited Autolab/OpenVINO optimization knobs.
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CASCADIA_INKLING_", "CASCADIA_GLM5_"))}
    env["RAYON_NUM_THREADS"] = "2"
    worker_env = dict(env)
    if args.owned_workers:
        worker_env["CASCADIA_INKLING_EP_OWN_EXPERTS"] = "1"
    if args.stream_cpu_workers:
        worker_env["CASCADIA_INKLING_EP_STREAM_CPU"] = "1"
    base = [str(bench), "--cases", str(cases), "--tokens", str(len(reference["greedy_ids"])),
            "--samples", "2", "--allow-fixture"]
    def run_bench(tag, model, extra):
        with (args.out / f"{tag}.log").open("w") as log:
            subprocess.run(base + ["--export", str(model), "--out", str(args.out / f"{tag}.json")] + extra,
                           stdout=log, stderr=subprocess.STDOUT, env=env, check=True, timeout=90)
        return json.loads((args.out / f"{tag}.json").read_text())
    local = run_bench("local", args.export, [])
    # Reserve all ports together to avoid duplicate ephemeral-port choices.
    sockets = [socket.socket() for _ in range(args.workers)]
    for s in sockets:
        s.bind(("127.0.0.1", 0))
    ports = [s.getsockname()[1] for s in sockets]
    children, logs = [], []
    try:
        for wi, port in enumerate(ports):
            model = args.out / f"worker-{wi}"
            copy_files(args.export, model, shard_files(plan, wi))
            log = (args.out / f"worker-{wi}.log").open("w")
            logs.append(log)
            sockets[wi].close()
            children.append(subprocess.Popen([str(worker), "--export", str(model), "--index", str(wi),
                                               "--count", str(args.workers), "--listen", f"127.0.0.1:{port}",
                                               "--placement", str(placement)], stdout=log, stderr=subprocess.STDOUT, env=worker_env))
        deadline = time.monotonic() + 30
        while not all("listening=" in (args.out / f"worker-{i}.log").read_text() for i in range(args.workers)):
            if any(p.poll() is not None for p in children) or time.monotonic() > deadline:
                raise RuntimeError("worker startup failed; inspect worker logs")
            time.sleep(0.05)
        remote = run_bench("ep", args.out / "driver", ["--ep-workers", ",".join(f"127.0.0.1:{p}" for p in ports),
                                                         "--ep-placement", str(placement)])
        for p in children:
            if p.wait(timeout=10) != 0:
                raise RuntimeError("worker failed")
        assert local["correctness_verified"] and remote["correctness_verified"]
        assert local["output_hash"] == remote["output_hash"]
        assert [s["generated_ids"] for s in local["samples"]] == [s["generated_ids"] for s in remote["samples"]]
        report = dict(scope="tiny_fixture_process_expert_parallel_correctness", passed=True,
                      output_hash=remote["output_hash"], workers=args.workers, samples=2,
                      driver_has_moe_bins=False, workers_have_only_assigned_bins=True,
                      owned_packed_expert_workers=args.owned_workers,
                      streamed_cpu_expert_workers=args.stream_cpu_workers,
                      performance_claim="none; loopback processes share one machine's memory bandwidth")
        (args.out / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        for p in children:
            if p.poll() is None:
                p.terminate()
        for p in children:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for s in sockets:
            s.close()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
