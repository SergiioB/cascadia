# Inkling 1.116 tok/s reproduction record

This document describes campaign 129, the confirmed performance record used by
the Panther Lake autolab. It was a local full-model run on tate-07, not a
fixture, layer microbenchmark, or partial-model measurement.

## What ran

The benchmark ran on `tate-07` (Core Ultra X7 358H, 16 logical CPUs, 64 GB
RAM). The Arc B390 iGPU was not used. The executable was the qualified native
Windows binary `full-second-prefetch.exe`, SHA-256
`71f7e4ef0364ab7ed030ca12400479deeb4f8e44c9cbe9818875a3b199d66476`, built
from source commit `ede10f9896952ccad13426351e6523ee6e39c4fe` (the complete source commit is recorded
in the campaign artifacts).

The model directory was
`C:\Users\devcloud\inkling-autolab\model`. It contained the complete
548,985,140,942-byte export in 16,654 files. The loader reported
`full_model=1`, loaded all 66 layers, and exercised embeddings, attention,
routed experts, shared experts, and the output head. The model's output hash
was `ce0fbb9a116d3d09`.

## Runtime settings

The exact campaign used:

```
RAYON_NUM_THREADS=16
processor_affinity=65535
bf16_rows=2
int4_rows=4
CASCADIA_INKLING_MMAP_EMBED=1
CASCADIA_INKLING_REUSE_READ_BUFFERS=1
CASCADIA_INKLING_SKIP_BULK_PREFETCH=1
CASCADIA_INKLING_OWN_SHARED=1
CASCADIA_INKLING_UNCACHED_READS=1
CASCADIA_INKLING_PIPELINE_READS=1
CASCADIA_INKLING_EXPERT_CACHE_MIB=256
CASCADIA_INKLING_PREFILL_READS=1
CASCADIA_INKLING_CACHE_RESET_HISTORY=1
CASCADIA_INKLING_CACHE_DECAY_REQUESTS=32
CASCADIA_INKLING_CACHE_RECENT_TIES=1
CASCADIA_INKLING_PREDICT_READS=1
CASCADIA_INKLING_EARLY_PREDICT_READS=0
CASCADIA_INKLING_SECOND_PREDICT_READS=1
CASCADIA_INKLING_SECOND_PREDICT_RANK=2
CASCADIA_INKLING_THIRD_PREDICT_READS=0
```

The benchmark used three canonical prompts (`water_cycle`, `binary_search`,
and `short_story`) and three repetitions, with 64 generated tokens per sample.
Each sample therefore had 63 timed decode steps. Prefill and decode timing
included all observed work and stalls; no samples or outlier steps were
discarded.

## How 1.1161344306111156 was calculated

For each sample, the benchmark computed:

```
decode_tokens_per_s = decode_steps / decode_seconds
                     = 63 / measured_decode_seconds
```

The campaign's conservative score was the slowest of all nine samples. The
nine rates, in execution order, were:

```
1.1464094565911267  1.1171082030633117  1.1515257935188460
1.2297446393679272  1.1193573316840948  1.1519785729352340
1.2312886559775449  1.1161344306111156  1.1519316729424331
```

Thus the reported record is the minimum:

```
min(nine rates) = 1.1161344306111156 decode tokens/second
```

The median was `1.151525793518846` and the fastest sample was
`1.2312886559775449` tok/s. The campaign ran for three repetitions and passed
the full-model correctness gates before the profile was promoted.

## Verification artifacts

The authoritative files are:

- [`129_final_verification.json`](results/129_final_verification.json), which
  records `scope=completed_full_model_repeated_confirmation`,
  `full_model=1`, `correctness_verified=true`, nine samples, 63 minimum decode
  steps, the output hash, and the promoted score.
- [`129_full_second_prefetch_confirmation.json`](results/129_full_second_prefetch_confirmation.json),
  the raw Autolab campaign history containing each command's captured output
  and metrics.
- [`129_profile_promotion.json`](results/129_profile_promotion.json), which
  records the selected two-reader/rank-2 profile and the conservative record.
- [`PERFORMANCE.md`](PERFORMANCE.md), the maintained performance summary and
  limitations.

The result is therefore a whole-model, local CPU measurement of the exported
Inkling model. It is not an iGPU result, and it is not a measurement of only a
subset of layers.
