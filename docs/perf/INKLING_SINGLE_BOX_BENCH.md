# Inkling on one Panther Lake box: CPU vs iGPU vs OpenVINO-native

Three whole-model, single-stream decode measurements of Inkling (975B MoE,
66 layers, 549 GB int4 export) on **tate-07** (Core Ultra X7 358H, 16 CPUs,
64 GB, Arc B390 iGPU, one Samsung PM9C1 Gen4 NVMe, Windows 11, OpenVINO
2026.3.1), all with the **campaign-129 protocol** from
`tools/inkling_autolab/INKLING_129_REPRODUCTION.md`:

* `inkling_decode_bench --export <model> --cases large-cases.baseline-reference.json --tokens 64 --samples 3 --layer-profile …`
* three prompts (`water_cycle`, `binary_search`, `short_story`) × three
  repetitions, 64 generated tokens each, 63 timed decode steps per sample;
* process pinned: PriorityClass High, affinity 65535 (`tools/inkling_autolab`
  Windows E-core rule);
* env = the promoted PTL read profile (`ptl-profile.ps1` +
  `SECOND_PREDICT_RANK=2`); the expert cache is 256 MiB per MoE layer
  (16 GiB) unless stated;
* score = **min over the nine samples of `63 / decode_seconds`** (median and
  max shown too); greedy output must hash to `ce0fbb9a116d3d09`, the record's
  reference, or the run is not correct.

Runner: scratchpad `t07_bench129.ps1`; raw artifacts on tate-07 under
`C:\Users\devcloud\inkling-igpu\logs\b129_<tag>.{json,profile.json,log}`.

## Results

| configuration | what runs where | decode tok/s min / median / max | prefill (30–32 tok) | hash |
|---|---|---|---|---|
| **CPU control** (record binary `full-second-prefetch.exe`, campaign 129 as documented) | everything Rust on the CPU; experts streamed from NVMe through the tuned reader (uncached + pipelined + predicted reads, 16 GiB cache) | **1.098 / 1.127 / 1.200** | 24.6–26.1 s | ✓ `ce0fbb9a…` |
| **ours on iGPU** (`feat/inkling-igpu`) | attention projections (int8 IRs, all 66 layers) + unembed head (int8 IR) on the Arc B390 via OpenVINO; Rust bf16 attention copies released; MoE experts streamed by the same tuned reader | _pending_ | _pending_ | _pending_ |
| ours on iGPU, cache 384 MiB/layer | as above, the RAM freed by the released copies given to the expert cache (24 GiB) | _pending_ | | |
| **OpenVINO-native MoE** | as "ours on iGPU" plus OpenVINO's own fused MoE kernel (`moe_3gemm_fused_compressed`) **and** OpenVINO's on-disk expert offload (`OFFLOAD_RATIO=99`, `WEIGHTS_PATH`) serving layers 2–7; the remaining 58 MoE layers as in the control | _pending_ | | |
| OpenVINO fused MoE, experts resident | fused kernel with the experts resident on the device for layers 2–4 (the Windows iGPU budget: three 8.3 GB layers per 64 GB box) | _pending_ | | |

Per-layer decode medians from the layer profiles (ms per token):

| layer set | CPU control | ours on iGPU | OpenVINO offload (cold) | OpenVINO fused, resident |
|---|---|---|---|---|
| dense L0/L1 attention + MLP | 2.9 + 3.8 | _pending_ | — | — |
| MoE layers, attention | 3.0 / **3.4** / 3.5 (min/med/max) | _pending_ | | |
| MoE layers, MLP (experts) | 5.1 / **8.8** / 14.8 | _pending_ | _pending_ (L2–7) | _pending_ (L2–4) |
| sum over 66 layers | 0.22 attention + 0.61 MoE = 0.83 s | _pending_ | | |

## Reading the numbers

**The single box is disk-bound, and no device changes that.** In the
control the 16 GiB expert cache hits 46 % of routed-expert reads; the
misses (~6.6 GB per token) stream from the one NVMe at ~7 GB/s, which is the
0.61 s of MoE time per token. Compute is hidden under the reads. What the
iGPU can take off the token is the part that is *not* disk: the attention
projections (0.22 s on the CPU) and the head (2.46 GB of bf16 per token,
~31 ms), plus whatever RAM the released bf16 copies (17.4 GB) hand back to the
expert cache.

**Fused MoE layers must stay off a single 64 GB box.** Each fused layer holds
8.3 GB of expert weights in unified memory. Six of them (50 GB) next to the
38–41 GB benchmark process is what made an earlier `cascadia run` on this box
page at 55 s per token; one resident layer saves ~11 ms per token, the same
8 GB as expert cache saves an order of magnitude more.

**OpenVINO's expert offload is not a substitute for the tuned reader.** Its
`OffloadExpertWeightProvider` streams positional reads at ~1 GB/s per layer
call (225–257 ms for an 8-expert call on this box), with no cross-layer
prediction and no cache across tokens; the Rust reader sustains ~7 GB/s with
predicted reads and a cache. The per-layer column above is the direct
comparison inside one run.

**The fleet is different physics.** With a rank's layers resident (the
12-box installation: 5–6 layers per box), per-layer decode is 30 ms on the
CPU versus 5.1–5.5 ms with fused MoE + int8 attention on the iGPU (see
`docs/architectures/inkling.md`, "OpenVINO fused-MoE backend"), and the
single-stream time is the sum across ranks: ≈ 2.5–2.7 tok/s all-iGPU versus
≈ 0.5 tok/s all-CPU. On Windows the iGPU holds three fused layers per 64 GB
box (the driver caps shared memory at half of RAM); Linux ranks or 96–128 GB
boxes lift that.

## Serving-path note

`cascadia run` logs `tok_s` as generated tokens over the whole request, prefill
included, so a 16-token answer behind a 25 s Inkling prefill reads as
0.02 tok/s next to the 1.1 tok/s decode figure above. The single-stage task
log now also carries `prefill_s`, `decode_s`, `decode_steps` and
`decode_tok_s` (the benchmark's definition). The decode code path is the
same as the benchmark's (`StagedRunner::generate_reason` →
`Layer::forward_token` → the pipelined predicted reads); a serving check with
the same env profile and no fused MoE layers is reported below once measured.

| `cascadia run`, same profile, 16-token request | prefill | decode tok/s (from the task log) |
|---|---|---|
| CPU | _pending_ | _pending_ |
| ours on iGPU (attention + head) | _pending_ | _pending_ |
