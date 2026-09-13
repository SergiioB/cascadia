"""Summarize opt-in Inkling layer timings alongside the matching decode report.

Branch times include their norms, residuals and short convolutions. Time outside
layers includes head, embeddings, argmax, validation and observer overhead; it
must not be described as head time alone. No component rate is a model rate.
"""
import argparse
import json
import math
from pathlib import Path
import statistics


def analyze(profile, benchmark, require_full=False):
    if profile.get("scope") != "layer_timing_diagnostics":
        raise ValueError("expected layer timing diagnostics")
    if (profile["generation_scope"] != benchmark["scope"]
            or profile["output_hash"] != benchmark["output_hash"]
            or profile["correctness_verified"] != benchmark["correctness_verified"]):
        raise ValueError("profile and benchmark identity/correctness differ")
    full = (profile["full_model"] and profile["layers"] == 66
            and benchmark["scope"] == "full_large_model_decode"
            and benchmark["manifest"] == {"layers": 66, "hidden": 6144, "experts": 256})
    if require_full and not (full and profile["correctness_verified"]):
        raise ValueError("a correctness-verified complete large model is required")
    reference = {(row["case"], row["repetition"]): row for row in benchmark["samples"]}
    samples, seen = [], set()
    for sample in profile["samples"]:
        key = sample["case"], sample["repetition"]
        if key in seen or key not in reference:
            raise ValueError("duplicate or unmatched profile sample")
        seen.add(key)
        result = reference[key]
        if sorted(layer["layer"] for layer in sample["layers"]) != list(range(profile["layers"])):
            raise ValueError("missing or repeated layer")
        sums = {phase: {"attention_seconds": 0., "mlp_seconds": 0., "total_seconds": 0.}
                for phase in ("prefill", "decode")}
        per_layer = []
        for layer in sample["layers"]:
            events = layer["events"]
            if (len(events) != 1 + result["decode_steps"] or not events[0]["prefill"]
                    or events[0]["rows"] < 1
                    or any(e["prefill"] or e["rows"] != 1 for e in events[1:])):
                raise ValueError("profile positions do not match the generation")
            local = {name: 0. for name in sums["decode"]}
            for event in events:
                if any(not math.isfinite(event[name]) or event[name] < 0 for name in local):
                    raise ValueError("invalid timing")
                if not math.isclose(event["attention_seconds"] + event["mlp_seconds"],
                                    event["total_seconds"], rel_tol=1e-8, abs_tol=1e-9):
                    raise ValueError("branch times do not add to layer time")
                phase = "prefill" if event["prefill"] else "decode"
                for name in local:
                    sums[phase][name] += event[name]
                    if phase == "decode":
                        local[name] += event[name]
            per_layer.append({"layer": layer["layer"], "decode_seconds_per_token":
                              {name: value / result["decode_steps"] for name, value in local.items()}})
        for phase in sums:
            wall = result[phase + "_seconds"]
            if sums[phase]["total_seconds"] > wall + 1e-6:
                raise ValueError("layer sum exceeds measured model time")
            sums[phase]["outside_layers_seconds"] = max(0, wall - sums[phase]["total_seconds"])
            sums[phase]["wall_seconds"] = wall
        samples.append({"case": key[0], "repetition": key[1], "decode_steps": result["decode_steps"],
                        "prefill": sums["prefill"], "decode": sums["decode"], "layers": per_layer})
    if seen != set(reference) or not samples:
        raise ValueError("incomplete profile sample set")
    medians = {name: statistics.median(s["decode"][name] / s["decode_steps"] for s in samples)
               for name in samples[0]["decode"]}
    return {"scope": "layer_timing_analysis", "full_model": full,
            "correctness_verified": profile["correctness_verified"], "output_hash": profile["output_hash"],
            "median_decode_seconds_per_token": medians, "samples": samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--require-full", action="store_true")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("refusing to overwrite analysis")
    result = analyze(json.loads(args.profile.read_text()), json.loads(args.benchmark.read_text()),
                     args.require_full)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "samples"}))


if __name__ == "__main__":
    main()
