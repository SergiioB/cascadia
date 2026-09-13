"""Independent CUDA processes with disjoint layer outputs and one final publisher.

Requires a complete local source checkpoint on Linux. Sources are retained. GPU
workers write only expert/dense bins; the parent publishes shells, sidecars and
the manifest after every worker succeeds. Existing atomic parts/finals resume.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import signal
import time


def _worker(model, out, manifest, layers, gpu, cpus, workers, chunk, verify, parent):
    # Terminate our own workers if the controller dies, including SIGKILL.
    import ctypes
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_SET_PDEATHSIG failed")
    if os.getppid() != parent:
        raise SystemExit("export parent exited")
    os.sched_setaffinity(0, cpus)
    import export_inkling as ex
    ex._set_threads(workers)
    source = ex.ShardSource(Path(model))
    try:
        converter = ex.Exporter(source, manifest, Path(out), workers=workers,
                                packer=ex.make_packer(f"cuda:{gpu}", chunk, verify))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for layer in layers:
                units = [u for u in converter.per_layer[layer] if u.kind != "shell"]
                started = time.monotonic()
                counts = converter.process(units, pool)
                if counts["pending"] or not all(ex.unit_output_done(u) for u in units):
                    raise RuntimeError(f"GPU {gpu}: incomplete expert layer {layer}")
                ex.log(f"[parallel GPU {gpu}] layer {layer}: {counts}; "
                       f"{time.monotonic() - started:.3f}s")
    finally:
        source.close_handles()


def export_parallel(model, out, *, processes, workers=1, cuda_chunk_mib=64,
                    verify_cuda=False, strict=False):
    import sys
    if sys.platform != "linux":
        raise ValueError("parallel CUDA export requires Linux CPU affinity and output locking")
    import fcntl
    import torch
    import export_inkling as ex

    if processes < 2 or workers < 1 or not 1 <= cuda_chunk_mib <= 256:
        raise ValueError("parallel export requires processes >= 2, workers >= 1 and chunk MiB 1..256")
    if not torch.cuda.is_available() or torch.cuda.device_count() < processes:
        raise ValueError(f"parallel export requires {processes} accessible NVIDIA GPUs")
    model, out = Path(model).resolve(), Path(out).resolve()
    if model == out or model in out.parents or out in model.parents:
        raise ValueError("source and output directories must be separate, without nesting")
    manifest = ex.load_and_validate_config(model / "config.json", strict=strict)
    source_config = json.loads((model / "config.json").read_text())
    if out.exists() and any(out.iterdir()):
        config = out / "source_config.json"
        if not config.is_file() or json.loads(config.read_text()) != source_config:
            raise ValueError("refusing nonempty output without matching source_config.json")
    # Validate all required tensors before any output is created or GPU work begins.
    source = ex.ShardSource(model)
    try:
        units, per_layer, by_tensor = ex.build_plan(manifest, out)
        missing = [name for name in by_tensor if not source.available(name)]
        if missing:
            raise ValueError(f"parallel export requires a complete source; missing {missing[:8]}")
    finally:
        source.close_handles()
    cpus = sorted(os.sched_getaffinity(0))
    count = min(processes, manifest["num_layers"], len(cpus))
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".parallel-export.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = out / "source_config.json"
        if not config.exists():
            ex.atomic_write_bytes(config, [(model / "config.json").read_bytes()])
        # Audit markers so a missing/truncated bin is repaired on a resumed run.
        for layer, layer_units in per_layer.items():
            marker = ex.layer_marker(out, layer)
            if marker.exists() and not all(ex.unit_output_done(u) for u in layer_units):
                marker.unlink()
        converter = ex.Exporter(ex.ShardSource(model), manifest, out)
        try:
            ex.check_space(out, converter.pass_bytes(units), ex.estimate_export_bytes(manifest), True)
        finally:
            converter.src.close_handles()
        children = []
        started = time.monotonic()
        context = multiprocessing.get_context("spawn")
        previous_handler = signal.getsignal(signal.SIGTERM)

        def stop(signum, frame):
            raise SystemExit(128 + signum)

        signal.signal(signal.SIGTERM, stop)
        try:
            for rank in range(count):
                child = context.Process(target=_worker, args=(
                    str(model), str(out), manifest,
                    list(range(rank, manifest["num_layers"], count)), rank,
                    cpus[len(cpus) * rank // count:len(cpus) * (rank + 1) // count],
                    workers, cuda_chunk_mib, verify_cuda, os.getpid()))
                child.start()
                children.append(child)
            while any(child.is_alive() for child in children):
                if any(child.exitcode not in (None, 0) for child in children):
                    raise RuntimeError("parallel converter failed; manifest was not published")
                time.sleep(.1)
            if any(child.exitcode != 0 for child in children):
                raise RuntimeError("parallel converter failed; manifest was not published")
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
            for child in children:
                child.join(timeout=10)
                if child.is_alive():
                    child.kill()
                    child.join()
            signal.signal(signal.SIGTERM, previous_handler)
        bins = [u for u in units if u.kind not in ("shell", "embed", "head")]
        if not all(ex.unit_output_done(u) for u in bins):
            raise RuntimeError("parallel output audit failed; manifest was not published")
        # All int4 work is finished. This CPU pass writes only the BF16/F32 shell
        # and edge tables, then verifies completeness and publishes the manifest.
        summary = ex.export_real(model, out, workers=min(4, len(cpus)), strict=strict)
        if not summary["complete"]:
            raise RuntimeError("parallel export finalization is incomplete")
        summary["parallel"] = {"processes": count, "workers_per_process": workers,
                               "seconds": time.monotonic() - started}
        ex.log("INKLING_PARALLEL " + json.dumps(summary["parallel"]))
        return summary
