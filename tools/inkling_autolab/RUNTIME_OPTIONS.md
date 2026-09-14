# Inkling runtime experiments on tate-07

The complete large model currently reaches **0.915789 decode tokens/s over one
pass** across the three reference prompts. This is an exploratory result;
[PERFORMANCE.md](PERFORMANCE.md) retains the separately confirmed three-repeat
record. The 25 tokens/s target is unmet. The active loop is in [HANDOFF.md](HANDOFF.md).

All options below preserve packed weights and numerical kernels. They affect
I/O, memory retention, or scheduling. Set environment variables before loading
a new model, or pass the corresponding argument to `run-full.ps1`.

| Environment variable | Wrapper argument | Default | Purpose |
| --- | --- | ---: | --- |
| `RAYON_NUM_THREADS` | `Threads` | Wrapper:16 | Workers shared by expert reads and row kernels. |
| `CASCADIA_INKLING_REUSE_READ_BUFFERS` | `ReuseBuffers` | 0 | Reuse scratch allocations, with a 256MiB process-wide idle limit. |
| `CASCADIA_INKLING_UNCACHED_READS` | `UncachedReads` | 0 | Aligned Windows reads, with complete cached retry on failure. |
| `CASCADIA_INKLING_PIPELINE_READS` | `PipelineReads` | 0 | Compute an expert as its read completes, preserving accumulation order. |
| `CASCADIA_INKLING_EXPERT_CACHE_MIB` | `ExpertCacheMiB` | 0 | Retained packed routed weights per MoE layer; maximum256MiB. |
| `CASCADIA_INKLING_PREFILL_READS` | `PrefillReads` | 0 | Read prefill experts through bounded reusable buffers. |
| `CASCADIA_INKLING_CACHE_RESET_HISTORY` | `CacheResetHistory` | 0 | Forget prior-request admission scores while retaining valid cached weights. |
| `CASCADIA_INKLING_CACHE_DECAY_REQUESTS` | `CacheDecayRequests` | 4096 | Halve frequency scores after this many routed requests per layer. |

The selected cache experiment uses256MiB per layer. Across64 MoE layers, the
actual retained allocations total16,309,550,592 bytes, including alignment
padding. Allocations grow from successful decode reads. Prefill does not admit
weights. Entries with outstanding read leases cannot be evicted. Model instances
own separate caches, so equal expert indices cannot mix weights across models.

Cached/pipelined reads require `Reads0`, parallel experts, and `ReuseBuffers1`.
Prefill reads require `Reads0` and `ReuseBuffers1`. The wrapper validates these
dependencies. Uncached mode is Windows-specific; unsupported sizes retry a full
cached read. Tiny fixture files exercise that retry, while full-model tests
verify zero fallback on aligned expert bins.

Cache-decay intervals accept powers of two from4 through65536. Invalid engine
values use4096; the wrapper rejects invalid arguments. The new `full-cache-decay.exe`
is natively qualified, including actual decay counters, but has no full-model
performance result yet. Other active experiments use the frozen
`full-prefill-reads.exe`; its interval remains4096. The worker sweep changes only
worker count, retaining the selected cache, streamed prefill and request reset.

Keep prefill and decode timing distinct. The native benchmark counts63 decode
steps after the first generated token, which belongs to prefill. Its score is
the slowest case/repetition and includes logits hashing. Exact baseline IDs,
full-logits hash and actual I/O/cache counters gate every full-model result.

## Benchmark process affinity

`run-full.ps1 -AffinityMask MASK` sets affinity only on the benchmark child and
reads the actual mask back before timing proceeds. Default65535 retains all16
logical processors. Mask4095 selectsCPUs0–11, which Windows reports as sharing
one last-level cache;CPUs12–15 report a separate cache. Native qualification088
passed65535/16workers,4095/12workers and4095/16workers with exact fixture outputs.
Full comparison089–091 found both restricted-affinity configurations slower;
the selected profile uses all16 CPUs. This option does not change machine power or service settings.

`CASCADIA_INKLING_CACHE_RECENT_TIES=1` allows a more recently observed expert
to replace an older cached expert when their decayed frequencies are equal.
Default0 retains the strict-frequency admission rule. It changes storage only;
all selected experts and arithmetic remain unchanged. Recent use is compared
after observing the complete current cohort, so an earlier missing expert
cannot replace a later hit on an equal-frequency tie. Outstanding buffer
leases still exclude eviction. The new cumulative `recent_tie_admissions`
statistic counts actual replacements by this rule. Native qualification098
passed245 tests and five tiny modes. Campaign102 confirmed0.965412 tok/s over
three prompts × three repetitions, with exact outputs and4.55% fewer reads.
This option is enabled in the selected PTL profile; the library default stays0.

`CASCADIA_INKLING_PREDICT_READS=1` is an experimental decode-only option requiring
the pipelined local expert cache. It predicts the first uncached expert before
attention and reads its complete bytes on one bounded background worker. Actual
routing alone determines whether those bytes are used. Unused reads drain before
the layer returns; failures retain the ordinary complete-read fallback. It does
not change cache history, expert selection, weights, or arithmetic. Default is
off. Local248 tests and four tiny modes pass. Native109 qualification passed252
tests and four tiny modes with exact outputs/routes/cache counters and13
scheduled/11useful/2unused predicted reads. Full speed measurements are pending. Do not enable it in the selected profile yet.
