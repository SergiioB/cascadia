# Full Inkling expert-parallel validation

2026-09-15 measurements, implementation on `feat/inkling-expert-routing`.
See [expert routing](INKLING_EXPERT_ROUTING.md) for architecture and deployment.

## Results and scope

| Comparison | Generated choices | Captured tensors | Result |
|---|---:|---:|---|
| Three-NUC CPU EP vs original single-machine CPU reference | 48 | 3,216 | Bit exact |
| Three iGPU workers vs twelve workers on the same three NUCs | 24 | 1,608 | Bit exact: 51,028,848 float values |

The GPU comparison has zero different float bits, zero relative RMS, and
matching whole-payload SHA256 for every prompt. All 64 MoE layers use fused GPU
experts, with zero CPU expert calls or fused errors. Attention, the two dense
layers, embedding and output head remain on CPU. All experts are available from
the complete export; each token uses its normal sparse selection.

The model has 66 layers, hidden size 6,144, intermediate size 3,072, 256 routed
and two shared experts per MoE layer, and six selected routed experts per token.
The complete export contains 16,588 unique files and 548,985,140,942 bytes.
All 200,058 exported head logits are captured, as are all layer residuals and
prefill rows. The manifest's vocabulary capacity is 201,024.

The GPU baseline is `full-gpu-ordered3-v13`; the twelve-worker candidates are
`full-gpu-ordered12-v14-{water_cycle,binary_search,short_story}`. Each candidate
uses an exact slice of the free-running baseline and independently chooses the
same eight greedy tokens. Both complete corpora execute 58,368 selected expert
rows. The candidate's 10,972 lossless replies carry 1,168,207,872 tensor bytes
versus 2,336,415,744 FP32-equivalent bytes, plus one scale byte per reply. No
FP32 reply fallback occurred. These counters include prefill and wire padding.

There are important limits:

- These are twelve **logical workers on three physical NUCs**, not twelve tested
  physical hosts. Additional processes share each machine's memory bandwidth.
- The GPU baseline matches 24/24 choices from an independent FP16 CPU reference
  and 22/24 from the original BF16 CPU reference. The two differences are in
  the water-cycle continuation. Full CPU/GPU numerical parity is unresolved;
  topology equality does not make that separate contract pass.
- The short deterministic corpus does not certify broad model quality,
  long-context behavior, concurrency or fault tolerance.
- These are instrumented, resource-limited SSD-streaming runs, not throughput
  records or evidence of reaching 25 tok/s. Candidate elapsed times are
  741.311, 755.997 and 750.737 seconds. The CPU comparison measured 0.1101 tok/s
  with tracing and restricted resources, separate from the original single-box
  [1.1161344306 tok/s CPU record](https://github.com/labscommunity/cascadia/blob/fdcc043370ebc0dc56da414e94edf5b037f8b778/tools/inkling_autolab/INKLING_129_REPRODUCTION.md).

## Evidence archive and independent recheck

Generated logs, placements, native source ZIPs, captured regression inputs,
failed/interrupted runs and full report bundles are preserved on
[`archive/inkling-ep-validation-20260915`](https://github.com/labscommunity/cascadia/tree/archive/inkling-ep-validation-20260915/docs/perf),
pinned at `9c59e4498d2a65048bbb4289c43df100960e490d`. They are excluded from the
implementation PR. Normal unit tests generate their own inputs and require
neither this archive nor access to the NUCs.

Key evidence under the archive's `docs/perf/inkling-ep-full/`:

- [GPU topology result](https://github.com/labscommunity/cascadia/blob/9c59e4498d2a65048bbb4289c43df100960e490d/docs/perf/inkling-ep-full/gpu-topology-v14-summary.json),
  `gpu-baseline-v13-summary.json`, and `cpu-v7-summary.json`.
- `full-gpu-ordered3-v13.json.gz`, the three v14 candidate bundles, and
  `full-cpu-v7.json.gz`: native reports, exact JSON bytes, trace metadata,
  payload hashes, backend profiles, guarded-job results and provenance.
- `final-audit.json` and `tate-v14-final-audit.json`: unchanged protected service
  identities, healthy live/ready endpoints and no remaining task processes,
  listeners or firewall rule.
- `run-builds.json` and `build-v13/v14-provenance.json`: executable/source hashes.
  The v13 source snapshot applies atop `4d3dc7ce`; v14 applies atop `43e16f84`.
- `manifest.json`, `placement.json`, `workers.json`, `full-cases.json` and all
  source/reference SHA256 manifests needed to reproduce the deployment.

Extract just the evidence into a temporary directory and audit it with the
current tools; this starts no model jobs and contacts no NUC:

```sh
git fetch origin archive/inkling-ep-validation-20260915
INKLING_REVIEW=$(mktemp -d)
git archive 9c59e4498d2a65048bbb4289c43df100960e490d \
  docs/perf/inkling-ep-full | tar -x -C "$INKLING_REVIEW"
INKLING_EVIDENCE="$INKLING_REVIEW/docs/perf/inkling-ep-full"
python3 tools/inkling_ep_topology_report.py \
  --artifacts "$INKLING_EVIDENCE" --baseline full-gpu-ordered3-v13 \
  --candidate full-gpu-ordered12-v14-water_cycle \
    full-gpu-ordered12-v14-binary_search full-gpu-ordered12-v14-short_story \
  --out "$INKLING_REVIEW/topology-result.json"
```

The auditor checks all tensor identities, numerical metrics, greedy IDs,
payload SHA256 equality, slice provenance, build identity, expert-row counts,
GPU coverage and service/resource evidence. Large `tensors.f32` files remain
in the isolated remote trace directories under their archived hashes. The
separate `inkling_ep_full_report.py` checks CPU/GPU equivalence to the original
CPU reference and deliberately fails on the retained GPU failures.

## Reproduce inference

The native `inkling_ep_validate` accepts any worker count, rejects reduced
architectures unless `--allow-fixture` is explicit, resets state per prompt,
and records every residual and full logits vector in `tensors.f32` plus trace
metadata, progress and a report. With a reference it follows that trajectory
and requires matching independently selected greedy IDs. Tolerance zero means
bit equality; a free-running reference recording has
`correctness_verified=false` because there is no comparison input. Generation
uses a fixed token count, not EOS termination.

```sh
# All endpoints must be in placement order; select CPU or GPU workers first.
inkling_ep_validate --export /models/inkling-driver --cases cases.json \
  --ep-workers "$EP_ENDPOINTS" --ep-placement placement.json \
  --reference /references/gpu-baseline --tokens 8 --max-relative-rms 0 \
  --out /results/gpu-candidate-NEW

# Recompare existing captures without model execution.
inkling_ep_validate --candidate /results/gpu-candidate-NEW \
  --candidate-trajectory /references/gpu-baseline \
  --reference /references/gpu-baseline --max-relative-rms 0 \
  --out /results/comparison-NEW.json
```

For a new free-running reference omit `--reference`. A saved teacher-forced
candidate requires its original `--candidate-trajectory` so that divergent
states cannot masquerade as free generation. Corrupt payloads, nonfinite values,
wrong tensor shapes/order/counts and differing greedy choices fail the checks.

`inkling_ep_trace_slice.py --source BASE --hashes BASE-sha256.json --case NAME
--out NEW_REFERENCE` copies exact single-prompt tensor byte ranges and binds
them to the source SHA256; it never recomputes values. Run it where the original
payload lives. This allows bounded per-prompt jobs without weakening the corpus
requirement. Use fresh labels and output paths to preserve previous evidence.

## Three-NUC operator and twelve-host deployment

The current `inkling_ep_full_run.py` launcher targets alpha, beta and charlie,
under `C:/Users/tatef/inkling-ep-lan-20260915`. It is specific to that inventory;
do not use it unchanged on other hosts. The saved uneven placement assigns
43.456, 217.312 and 236.622 GiB of packed experts to these machines, with shared
replicas and all driver files on charlie. Their aggregate RAM cannot hold the
model; derived GPU blobs require additional disk space.

With that deployment already staged, the archived placement can be reused:

```sh
python3 tools/inkling_ep_full_run.py --label gpu-base-NEW \
  --mode fused-stream --record --reference full-reference16-v4 --tokens 8 \
  --placement "$INKLING_EVIDENCE/placement.json" --cache-mb-per-host 2400 \
  --out /tmp/gpu-base-NEW
python3 tools/inkling_ep_full_run.py --label gpu-12-NEW \
  --mode fused-stream --workers-per-host 4 --lossless-wire \
  --reference gpu-base-NEW --tokens 8 --max-relative-rms 0 \
  --placement "$INKLING_EVIDENCE/placement.json" --cache-mb-per-host 2400 \
  --seconds 3400 --out /tmp/gpu-12-NEW
```

The completed campaign used one-prompt reference slices and matching `--cases`
files, each with its own 3,400-second lease. Reference/case names resolve under
the isolated root on charlie. `inkling_ep_full_collect.py` archives a completed
run; `inkling_ep_full_audit.py` checks final service/resource state.

Preflight verifies completed staging, source-file identities, manifest/placement
agreement, executable/runtime hashes, fused ownership metadata and reference
checksums. The launcher uses below-normal priority, limited CPU affinity, a
12 GiB available-memory reserve, 3 GiB worker RSS caps and an 80 GiB free-disk
floor. Service activity pauses only task processes; CI activity or a memory
limit stops them. Private ports 29475–29478 admit only charlie and the task
executable. Cleanup verifies process identities and removes only task rules.
The final GPU candidates kept driver RSS below 3.676 GiB and available memory
above 16.98 GiB; all protected services remained unchanged.

`inkling_ep_topology.py` divides each of the three physical shards into four
read-only worker views, hardlinking weights and preserving parent IR indices.
It tests twelve sockets and ownership sets without creating extra weight copies.
For twelve physical hosts, create a new capacity-checked placement, stage and
checksum every assigned expert, build version-2 scaled GPU shards, and deploy
matching binaries/runtime. Extend the launcher's and auditor's inventories and
service guards. Then compare CPU EP against the original CPU reference and GPU
EP against the saved GPU reference, both at zero tolerance, retaining full
layer/logit evidence and zero GPU fallback. Add representative longer prompts
and serving tests before accepting production traffic.
