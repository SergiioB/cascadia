# Fused Inkling expert sharding on three Panther Lake iGPUs

2026-09-15, `feat/inkling-expert-routing`.

Fused GPU expert sharding is implemented and physically tested on alpha,
beta, and charlie. For the resident layer-2 decode probe, two independent
process runs per configuration give **3.312 ms per layer with per-expert
routing versus 2.733 ms with compact fused routing: 1.212× throughput**
(17.5% less latency). This is **not a full-975B token-generation rate**.

## What changed

The existing driver still owns attention, routing, sequence state, and the
final MoE residual. It selects owners using the existing capacity-checked
placement and sends the original gate weights with the hidden rows and
global expert IDs. The new `FusedExpertDispatch` wire code is `0x534d4552`.
Workers return one weighted partial vector per original row through
`ExpertResult` with `k=1`. The driver sums partials in worker order. Weights
are never renormalized within a shard, and each shared expert contributes
exactly once through the existing replica assignment.

The normal per-expert protocol remains the default. Both the driver and
workers opt into the fused protocol with `CASCADIA_INKLING_EP_FUSED=1`.
Workers load shard metadata and reject mismatched dimensions, ownership,
missing IRs, oversized cache entries, malformed routing, and non-GPU devices.
An unsupported weighted request is fully consumed before rejection; the
connection remains aligned. Old builds reject the unknown frame code.

Each worker compiles an expert-major OpenVINO graph containing only its
owned experts. The runtime requires profiling evidence of `MOECompressed`
executing `ocl::moe::moe_3gemm_*` (or the older named compressed fused MoE
operation). A failed GPU call or failed fusion check fails the request;
there is no CPU or per-expert fallback. The actual measured kernel was
`ocl::moe::moe_3gemm_swiglu_opt___f16`.

The first implementation used a graph with eight routing slots and zero
weights for unassigned slots. It measured **3.544 ms**. The promoted compact
graph has `K=1`: the worker batches actual `(token, expert)` pairs as GPU
rows, executes their weighted expert functions in the fused graph, and
combines the results into one partial vector per original token. This
avoids computing unassigned expert slots. Zero-weight entries can be
omitted. Expanded rows are split into at most 32 rows per GPU call by default
(`CASCADIA_INKLING_EP_FUSED_ROWS`, configurable from 1 to 256). A large
request's last chunk is padded to that same shape with zero weights. The
existing two-row minimum and GPU GEMV workaround remain.

## Measurements and numerical scope

Same original int4 layer-2 expert weights, placement, and 36 route frames as
[the per-expert qualification](INKLING_IGPU_EXPERT_ROUTING.md): hidden 6,144,
intermediate 3,072, six routed plus two shared experts per row. Routes come
from campaign 129; hidden inputs are deterministic synthetic values and
decode weights are all 1/8. This probe does not execute attention, the head,
prefill of the full model, or token generation.

Every process uses two complete warm passes, then three timed passes. Each
row below contains **108 observations**, with no timed observations dropped.
Both modes use the same native build, the same four host CPU cores per
worker, and alpha's two separate driver cores. GPU computation runs on all
three NUCs; transport uses their direct LAN addresses and 2.5 GbE network.

| Three-NUC mode | Mean ms | Median ms | Maximum ms |
|---|---:|---:|---:|
| Eight-slot fused graph, initial version | 3.544 | 3.557 | 4.206 |
| Compact fused, run 1 | 2.749 | 2.702 | 3.349 |
| Per-expert, run 1 | 3.253 | 3.149 | 4.558 |
| Compact fused, run 2 | 2.716 | 2.664 | 3.688 |
| Per-expert, run 2 | 3.372 | 3.299 | 4.933 |
| **Compact fused, both runs (216 observations)** | **2.733** | **2.677** | **3.688** |
| **Per-expert, both runs (216 observations)** | **3.312** | **3.245** | **4.933** |

The final native build (`v7`, including the batch-size fix and malformed-frame
regression fix) was checked again with new processes: compact fused measured
**2.765 ms** versus **3.642 ms** for per-expert routing, **1.317×**, with 108
timings per mode. This confirms the improvement; the two-run 1.212× comparison
above is retained rather than selecting the largest observed ratio.

The earlier 3.595 ms per-expert record would imply a 1.316× improvement,
but **1.212× against these fresh controls is the appropriate comparison**.
The sample groups share routes; these are repeated phase measurements,
not independent full-model requests or a statistical confidence interval.

A local full-layer fused reference on **tate-07** measured 3.046 ms mean /
3.010 ms median for the same 36 frames. Its purpose is a numerical oracle;
tate-07 has 64 GB rather than the NUCs' 32 GB, and uses an eight-slot graph.
It is not a matched local-Nuc compact-graph performance control. The full
fused graph peaks near 17 GiB RSS, which would violate the NUC memory reserve.

Compact distributed outputs differ from that local fused reference by
**0.0004313 relative RMS (0.0431%)**, maximum absolute error 0.0146484.
The local fused reference differs from the CPU reference by 0.0027645
relative RMS (0.2764%). The preselected acceptance limit is 0.005 (0.5%).
Different FP16 rounding and reduction order mean CPU/GPU bit parity is not
promised. Each configuration's additional warm and timed outputs remain
bit-identical to its own first-pass outputs.

In each compact decode run, all three workers perform 180 successful fused
calls, for **540 fused calls total**. Their selected expert-row counts are
550, 450, and 440: **1,440**, exactly five passes × 36 frames × eight experts.
The matching per-expert run requires 1,440 separate expert calls. All runs
report zero CPU calls and zero fallbacks/errors.

Additional correctness probes use nonuniform routing weights, zero shared
weights, deliberately uneven ownership, and batches of 1, 2, 3, 8, 16, and
33 rows. They pass at 0.0003649 relative RMS against the full-layer fused
oracle. A 129-row probe also passes, including splitting expanded expert
rows across GPU calls. These probes establish batched routing correctness;
they are not full-model prefill speedup measurements or generation-quality
validation. The initial 257-row local probe was rejected by the worker's
256-row frame cap before inference; the 129-row probe exercises worker-side
splitting while respecting that cap.

The initial 129-row compact implementation used 256-row GPU chunks and
measured 549 ms mean, with substantial variation. Padding its last chunk
to 256 rows did not reliably fix that delay. Using 32-row chunks reduced
the same probe to 165 ms mean in the tuning run and **155 ms in the final
build**, retaining numerical correctness. This is a targeted improvement to the compact implementation;
it does not compare full-model prefill against the per-expert runtime.
The final build repeats decode, the small batch suite, and the 129-row case;
all results, including unsuccessful tuning choices, are retained.

## Export and enable

No checkpoint reconstruction, requantization, CUDA exporter, or Lambda
instance is needed. `inkling_ep_fused_export.py recipe` extracts the graph
and small constants from an existing same-dimension `u4zp` fused layer.
`build` streams the owned experts from their existing packed bins, preserving
nibbles and converting BF16 scales to FP16. It records source, XML, blob,
and placement hashes plus the exact global-to-local expert mapping.
The current recipe format targets the large model's group-32, K=8 graph.

```sh
python tools/inkling_ep_fused_export.py recipe \
  --ir-layer MODEL/moe_ov/layer_02 --out fused-recipe.json
python tools/inkling_ep_fused_export.py build \
  --recipe fused-recipe.json --export MODEL --placement placement.json \
  --index 0 --layer 2 --out fused-k8 --guarded
python tools/inkling_ep_fused_export.py compact \
  --src fused-k8/layer_02 --out fused-compact/layer_02
```

Repeat the build for each worker's index and each required layer. `compact`
changes the routing dimension to one and hard-links the immutable weight
blob; it does not duplicate or rewrite it. Source/destination must support
hard links on the same filesystem. The NUC exports took approximately
61 seconds each at the guarded 48 MiB/s rate, without OpenVINO or numpy
installed in their Python environments.

Build the examples with `tools/inkling_ep_build_gpu_windows.bat` or build
the serving executable with OpenVINO support. Workers use:

```text
CASCADIA_INKLING_EP_FUSED=1
CASCADIA_INKLING_EP_REQUIRE_GPU=1
CASCADIA_INKLING_EP_FUSED_DIR=C:/Users/tatef/inkling-ep-lan-20260915/fused-compact
CASCADIA_INKLING_EP_FUSED_CACHE_MB=3500
CASCADIA_INKLING_EP_FUSED_ROWS=32
CASCADIA_INKLING_OV_MOE_DEVICE=GPU
OV_GPU_MOE_BATCHED_GEMV_THRESHOLD=0
```

The driver needs `CASCADIA_INKLING_EP_FUSED=1` and the existing EP worker
endpoints/placement. Do not enable owned CPU weight copies in fused mode.
Without `EP_FUSED_DIR`, the worker looks in `MODEL/moe_ep/worker_NN`.
The fallback default IR cache budget is 4,096 MiB. Do not point the full
975B driver at these three-layer test manifests.

## Memory and coexistence

Alpha owns 88 experts; beta and charlie own 87 each, including replicated
shared experts. Their fused blobs are 2,860,941,516 / 2,828,796,108 /
2,828,796,108 bytes. The LRU bounds cached IR weight bytes and drops old
compiled runtimes before admitting another layer. **This does not bound
OpenVINO allocation overhead or compilation peaks.** Across the recorded
NUC experiments, worker peak RSS was about 6.06 GiB and available memory
stayed above 16.69 GiB, against the 12 GiB guard reserve.

All testing used isolated files and private runtime DLLs. The guard runs
below normal priority, checks CI and service activity, bounds RSS and job
lifetimes, and terminates only its own child. CPU service activity now uses
a full 500 ms sampling window, including startup; the 20% threshold is
unchanged. This fixes false triggers from a Windows accounting tick divided
by a very short startup interval. Aborted startup/export attempts are
retained separately and contributed no timed observations.

No existing OVMS, Cascadia, or runner process was restarted or reconfigured.
Final live/ready checks returned 200 on all NUCs, and protected PIDs/creation
times match. Benchmark workers and the temporary, source-restricted port
29474 firewall rules are removed after runs. The shard files and binaries
remain available under the isolated deployment root.

The three NUCs still have only about 95 GiB physical RAM versus the complete
export's roughly 549 GB. A fused shard retains every owned expert of a layer,
whereas the per-expert cache can retain just hot experts. Compiling/evicting
layer shards every token can erase the resident-phase gain. Full-model use
still needs adequate aggregate memory or a measured caching strategy, plus
end-to-end generation-quality and decode benchmarks. This change does not
establish 25 tok/s or a new full-model token/s record.

## Reproduction artifacts

[inkling-ep-fused](inkling-ep-fused/) contains every successful run's timings,
worker/driver logs and guarded jobs, the initial eight-slot result, export
provenance, CPU/fused oracle results, input frames, exact DLL/executable
hashes, final audits, and the native source snapshot atop commit `41853f8d`.
The hardware measurements identify their native build version explicitly.
Native snapshots for v4 and v7 allow exact reconstruction. The final v7 Rust
source hashes match the committed implementation; the older snapshot records
the earlier decode comparison.

```sh
python tools/inkling_ep_fused_report.py \
  --artifacts docs/perf/inkling-ep-fused \
  --out /tmp/inkling-fused-summary.json
```

The validator checks call counts, nonzero selected expert rows, numerical
limits, fused GPU evidence, service preservation, cleanup, artifact identity,
and computes the comparison using all 216 timings per final decode mode.
Local validation also includes 12 EP integration tests, fused request
validation tests, and an independent byte-level exporter test covering
nonconsecutive expert IDs, FP16 scales, source hashes, and compact IRs.
