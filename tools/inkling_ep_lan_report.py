#!/usr/bin/env python3
"""Validate and summarize the saved three-NUC qualification (never emits tok/s)."""
import argparse
import json
import math
from pathlib import Path
import statistics


def require(condition, message):
    if not condition:
        raise ValueError(message)


def distribution(values):
    require(bool(values) and all(math.isfinite(x) and x > 0 for x in values),
            "timings must be positive and finite")
    values = sorted(values)
    return dict(count=len(values), mean=statistics.mean(values), median=statistics.median(values),
                p95=values[math.ceil(len(values)*0.95)-1],
                p99=values[math.ceil(len(values)*0.99)-1], maximum=max(values))


def summarize(root):
    def read(name):
        return json.loads((root/name).read_text())
    local, remote = (read("alpha/layer-"+mode+".json") for mode in ["local", "ep"])
    for result in [local, remote]:
        require(result["scope"] == "real_expert_phase_with_synthetic_inputs" and
                result["full_model_inference"] is False, "wrong benchmark scope")
        require(result["self_consistency_verified"], "output changed during timing")
        require(len(result["timings"]) == result["frames"]*result["samples"], "incomplete timings")
        observed = {(v["sample"], v["frame"]) for v in result["timings"]}
        require(observed == {(s, f) for s in range(result["samples"]) for f in range(result["frames"])},
                "duplicate or missing sample/frame")
    require(remote["reference_verified"] and local["workers"] == 0 and remote["workers"] == 3,
            "remote run must verify the local oracle")
    for field in ["hidden", "intermediate", "model_layers_in_export", "frames", "samples"]:
        require(local[field] == remote[field], "benchmark dimensions differ: "+field)
    fixture_a, fixture_b = read("alpha/fixture-local.json"), read("alpha/fixture-driver.json")
    require(fixture_a["correctness_verified"] and fixture_b["correctness_verified"], "fixture failed")
    require(fixture_a["output_hash"] == fixture_b["output_hash"], "fixture logits differ")
    require([x["generated_ids"] for x in fixture_a["samples"]] ==
            [x["generated_ids"] for x in fixture_b["samples"]], "fixture tokens differ")
    hosts = {}
    binaries = None
    for host in ["alpha", "beta", "charlie"]:
        audit = read(host+"/audit-after.json")
        require(audit["ovms_health"] == {"live": 200, "ready": 200}, host+" service health failed")
        require(not audit["own_processes"] and not audit["own_listening_ports"] and
                audit["task_firewall_rule_removed"], host+" cleanup incomplete")
        if binaries is None:
            binaries = audit["binaries"]
        require(audit["binaries"] == binaries, "workers used different binaries")
        statuses = [json.loads(p.read_text()) for p in sorted((root/host).glob("*.status.json"))]
        for status in statuses:
            require(status["state"] == "finished" and status["protected_processes_unchanged"],
                    host+" job incomplete or protected process changed")
            require(status["protected_after"] == audit["protected"], host+" protected identity changed")
            # The first local fixture intentionally failed its large-model-only
            # assertion; it never produced performance data. Preserve that attempt.
            if status["job"]["label"] != "fixture-local":
                require(status["returncode"] == 0 and status["stop_reason"] is None,
                        host+" benchmark failed or was preempted")
        hosts[host] = dict(free_memory_gib_after=audit["free_memory_gib"],
                           minimum_available_gib=min(s["minimum_available_gib"] for s in statuses),
                           free_disk_gib_after=audit["free_disk_gib"],
                           protected_processes_unchanged=True, ovms_health=audit["ovms_health"],
                           task_processes_and_firewall_removed=True)
    a = distribution([v["milliseconds"] for v in local["timings"]])
    b = distribution([v["milliseconds"] for v in remote["timings"]])
    return dict(scope="one_real_MoE_layer_with_synthetic_inputs", full_model_inference=False,
                timing_unit="milliseconds", local=a, expert_parallel=b,
                mean_phase_speedup=a["mean"]/b["mean"],
                median_phase_speedup=a["median"]/b["median"],
                wire_round_trip_microseconds=[dict(worker=p["worker"],
                    payload_bytes_each_way=p["payload_bytes_each_way"],
                    **distribution(p["round_trip_us"])) for p in remote["wire_probes"]],
                tiny_fixture_logits_hash=fixture_b["output_hash"],
                real_expert_outputs_bit_exact=True, hosts=hosts, binaries=binaries,
                limitation="No attention, token generation, disk misses, or full-model throughput. "
                           "Four compute CPUs per worker versus four on the local baseline. "
                           "Wire p99 is the maximum of only 32 retained observations.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifacts", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    result = summarize(a.artifacts)
    a.out.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
