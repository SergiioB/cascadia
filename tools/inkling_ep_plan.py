#!/usr/bin/env python3
"""Build a capacity-checked EP placement and per-worker copy lists (no exports).

Worker JSON is an array of name, expert_capacity_bytes, read_us, compute_us,
dispatch_us. Budgets cover packed weights only; reserve runtime/KV/OS memory.
Costs should come from measurements on the intended interconnect and devices.
"""
import argparse
import json
import math
from pathlib import Path


def make_plan(manifest, workers, routed_replicas=1, shared_replicas=None):
    count = len(workers)
    if manifest["arch"] != "inkling" or count == 0:
        raise ValueError("an Inkling manifest and at least one worker are required")
    shared_replicas = count if shared_replicas is None else shared_replicas
    if not 1 <= routed_replicas <= count or not 1 <= shared_replicas <= count:
        raise ValueError("replica counts must be in 1..number of workers")
    required = {"name", "expert_capacity_bytes", "read_us", "compute_us", "dispatch_us"}
    names = set()
    for w in workers:
        if set(w) != required or not isinstance(w["name"], str) or not w["name"] or w["name"] in names:
            raise ValueError("workers need unique names and exactly these fields: " + ", ".join(sorted(required)))
        names.add(w["name"])
        if type(w["expert_capacity_bytes"]) is not int or w["expert_capacity_bytes"] < 0:
            raise ValueError("expert_capacity_bytes must be a nonnegative integer")
        if any(not math.isfinite(w[k]) or w[k] < 0 for k in ("read_us", "compute_us", "dispatch_us")) or w["read_us"] == 0:
            raise ValueError("costs must be finite, read_us > 0 and other costs >= 0")
    h, inter = manifest["hidden_size"], manifest["moe_intermediate"]
    if h <= 0 or inter <= 0 or h % 32 or inter % 32:
        raise ValueError("hidden and intermediate must be positive multiples of 32")
    # Three matrices: nibble weights plus one bf16 scale per group of 32.
    expert_bytes = 3 * h * inter * 9 // 16
    capacity = [w["expert_capacity_bytes"] // expert_bytes for w in workers]
    used = [0] * count
    nr, ns = manifest["num_experts"], manifest.get("n_shared_experts", 2)
    dense = set(manifest.get("dense_layers", []))
    layers = [[] if li in dense else [[] for _ in range(nr + ns)]
              for li in range(manifest["num_layers"])]
    # Place the highest replication degree first, avoiding fragmentation that
    # could leave too few distinct workers for a later shared expert.
    jobs = [(li, eid, routed_replicas if eid < nr else shared_replicas)
            for li, layer in enumerate(layers) for eid in range(len(layer))]
    jobs.sort(key=lambda job: (-job[2], job[0], job[1]))
    for li, eid, replicas in jobs:
        owners = layers[li][eid]
        for _ in range(replicas):
            eligible = [wi for wi in range(count) if wi not in owners and used[wi] < capacity[wi]]
            if not eligible:
                raise ValueError(f"insufficient expert memory for layer {li} expert {eid}; "
                                 "reduce replicas or add capacity (no paging plan was emitted)")
            # Spread storage in proportion to budget, with deterministic ties.
            wi = min(eligible, key=lambda i: ((used[i] + 1) / capacity[i], used[i], i))
            owners.append(wi)
            used[wi] += 1
        owners.sort()
    return dict(version=1, hidden_size=h, moe_intermediate=inter, num_experts=nr,
                n_shared_experts=ns, expert_bytes=expert_bytes, workers=workers, layers=layers)


def shard_files(plan, worker):
    files = ["manifest.json"]
    for li, layer in enumerate(plan["layers"]):
        for eid, owners in enumerate(layer):
            if worker in owners:
                name = (f"expert_{eid:03}.bin" if eid < plan["num_experts"] else
                        f"expert_shared{eid - plan['num_experts']}.bin")
                files.append(f"experts/layer_{li:02}/{name}")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--workers", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    parser.add_argument("--routed-replicas", type=int, default=1)
    parser.add_argument("--shared-replicas", type=int, help="default: all workers")
    args = parser.parse_args()
    try:
        plan = make_plan(json.loads(args.manifest.read_text()), json.loads(args.workers.read_text()),
                         args.routed_replicas, args.shared_replicas)
    except (ValueError, KeyError, TypeError) as e:
        parser.error(str(e))
    # A new directory protects an existing deployment's placement/copy lists.
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "placement.json").write_text(json.dumps(plan, indent=2) + "\n")
    summary = []
    for wi, w in enumerate(plan["workers"]):
        files = shard_files(plan, wi)
        (args.out / f"worker-{wi}.files").write_text("\n".join(files) + "\n")
        summary.append(dict(index=wi, name=w["name"], experts=len(files) - 1,
                            packed_bytes=(len(files) - 1) * plan["expert_bytes"],
                            budget_bytes=w["expert_capacity_bytes"]))
    report = dict(workers=summary, scope="packed expert storage; no measured throughput or guaranteed residency")
    (args.out / "storage.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
