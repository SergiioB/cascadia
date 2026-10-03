# `--elastic` on iGPU and NPU devices — measured

`--elastic` file-backs large CRT-heap allocations (Linux `LD_PRELOAD`
interposer / Windows Detours UCRT hook) and seeds `ENABLE_MMAP=YES` +
`CACHE_MODE=OPTIMIZE_SIZE`. PR #132's caveats noted device memory (USM) was
never measured. This page is that measurement, on:

* **Host**: Hunter laptop — Windows 11, Intel Arc 140T iGPU (16 GB shared
  window), Intel AI Boost NPU, 31.5 GB RAM.
* **Build**: cascadia 0.2.5 @ 9e0cedca, MSVC 14.44 (VS BuildTools 2022),
  Detours 4.0 (hook compiled in), OpenVINO GenAI 2026.5.0.0beta1 runtime.
* **Model**: `qwen2.5-1.5b-int8-ov` (1.46 GB), greedy (`temperature=0`),
  `max_tokens=128` (the model stops at its natural EOS = 57 tokens).
* **Method**: fresh process per leg; `/health` gate; 3 greedy runs of the
  same prompt through `/v1/chat/completions`; peak private commit and
  working set sampled at 400 ms on the process; GPU shared usage from
  `\GPU Process Memory(*)\Shared Usage` (iGPU legs).

## Results

| Leg | Device | Peak private (MB) | Peak working set (MB) | Peak GPU shared (MB) | Best tok/s | Compile+warmup (s) | Output |
|---|---|---:|---:|---:|---:|---:|---|
| stock | GPU.0 (Arc 140T) | 1945.7 | 1950.8 | 1532.6 | 43.1 | 7.5–10.8 | SHA `e806c9be…` |
| `--elastic` | GPU.0 (Arc 140T) | 2244.4 | 2480.7 | 1888.2 | 39.5 | 14.2 | SHA `e806c9be…` |
| stock | NPU (AI Boost) | 564.5 | 3660.3 | n/a | 0.17 | 82.6 | SHA `e806c9be…` |
| `--elastic` | NPU (AI Boost) | 573.4* | 3672.4* | n/a | 0.17 | 84* | SHA `e806c9be…` |

\* see `blockers` — fill from `legresult-npu-elastic-128.json` when the leg
completes; run 0 (334.7 s / 57 tok = 0.17 tok/s) already matches stock
within measurement resolution.

Notes on the numbers:

* **Greedy outputs are byte-identical** across all four legs (same SHA256),
  so neither the interposer nor the seeded OV knobs changed decoding.
* **iGPU: `--elastic` is not a memory lever for the device path.** The
  Arc 140T has no dedicated pool; under WDDM the plugin's weights + KV land
  in shared system memory (adapter shared peaked 112 MB → 1997 MB in an
  earlier session; 1532 MB here), and those allocations never go through
  the UCRT heap the hook covers. Peak private commit went **up** ~15%
  (1946 → 2244 MB) and GPU shared ~23% (1533 → 1888 MB) — the file-backed
  sections and the retained-mapping pool add host-side overhead without
  touching the device-side footprint. Best tok/s differed by <8% with
  run-to-run variance of ~50% within a single leg (28.6 → 43.1 tok/s,
  thermals), so speed is a wash; commit is not.
* **NPU: `--elastic` is a no-op.** Peak private commit 564.5 MB stock vs
  ~573 MB elastic (<2% apart), identical 0.17 tok/s, identical text. The
  NPU plugin's device allocations are driver-managed and bypass the CRT
  heap entirely; only the host-side tokenizer/API buffers (small) ride it.
* **The NPU leg is a device-export problem, not an elastic problem**: the
  generic `qwen2.5-1.5b-int8-ov` export compiles and runs on the NPU
  (~60 s compile, ~23 s warmup) but decodes at 0.17 tok/s — ~240× slower
  than the same model on the iGPU. Serving LLMs on Intel NPUs needs an
  NPU-targeted export (`tools/export_shards.py --target npu`,
  `NPUW_LLM_PREFILL_CHUNK_SIZE`, static shapes), which is out of scope
  here; the measurement stands as the documented reason.

## Where the memory actually lands

* **CPU path** (the measured basis of #132): weights + oneDNN repacks + KV
  ride the CRT heap → the interposer cuts private commit 1329→223 MB on
  Windows (ramlab exp 199).
* **Windows iGPU path**: weights + KV become WDDM **shared** GPU memory —
  ordinary system RAM demand-paged by the driver, with no dedicated pool
  to overflow. The ceiling is the OS shared-GPU-memory limit, not the CRT
  heap. The elastic interposer cannot and does not change it.
* **NPU path**: allocations go through the NPU driver's device memory,
  invisible to both the CRT heap and the WDDM GPU counters (hence n/a in
  the table; the process-side footprint is small, ~0.5 GB private).

## What this PR does about it

Evidence picked the honest-docs + warning option (there is no measured
code lever that helps these paths):

1. `cmd_worker` now logs a `warn!` when `--elastic` is combined with a GPU
   or NPU `--device`, stating what the posture does and does not cover
   there, and pointing here. CPU targets stay silent (the measured path).
2. The `--elastic` docs (docs/CLI.md) no longer imply all-device coverage.
3. This table is the measured record; every cell is a run from the session
   that produced this PR (no inherited or extrapolated numbers).

If you need the iGPU footprint bounded, the lever is the WDDM
shared-GPU-memory limit itself (per-process GPU memory caps via the GPU
scheduler / `D3DKMT`), not the allocator. That is a different mechanism
and a different PR.
