# Inkling runtime experiments on tate-07

The complete large model's confirmed score is **1.090427 decode tokens/s**,
the slowest of nine samples. [PERFORMANCE.md](PERFORMANCE.md) retains the
verification, raw results and selected profile. The25 tokens/s target is unmet.
The active loop is in [HANDOFF.md](HANDOFF.md).

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
| `CASCADIA_INKLING_CACHE_RECENT_TIES` | `CacheRecentTies` | 0 | Prefer more recent experts on equal-frequency admission ties. |
| `CASCADIA_INKLING_PREDICT_READS` | `PredictReads` | 0 | Read one predicted uncached expert before attention on a bounded worker. |

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
values use4096; the wrapper rejects invalid arguments. The selected profile
uses32,16 workers, recent-tie admission and one predicted expert read. Use the
qualified `full-predicted-read.exe` identified in [PERFORMANCE.md](PERFORMANCE.md).

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
scheduled/11useful/2unused predicted reads. Campaign112 confirmed1.090427 tok/s over nine samples, up12.95% from102. All
35,718 reads completed,34,014 were useful and1,704 unused, with zero failures.
Extra1.45% readbytes and all stalls remain in the timings. This option is now
enabled in the selected PTL profile; the library default remains0.

The benchmark's `--prediction-trace` observes current-layer pre-attention routes.
The separate experimental `--prediction-lead-layers 1` observes the target
router before its predecessor executes, using that earlier residual input.
It is decode-only and performs no additional expert I/O. The trace explicitly
labels its prediction input and lead; layer0 has no predecessor and is omitted.
Observer time is included in the model benchmark, outside layer timing spans.
Local115 and native116 qualification pass (250 local/254 native tests and
four tiny modes). Full-model prediction accuracy is being measured. Its
`PredictionLeadLayers` wrapper argument requires the separate candidate binary.

`CASCADIA_INKLING_EARLY_PREDICT_READS=1` (`EarlyPredictReads1`) is a separate
experimental whole-Model decode path requiring `PredictReads1` and the
qualified `full-early-prefetch.exe`. It schedules one target expert before the
preceding layer executes, with at most current+next pending requests per model.
Actual selection/cache admission stays unchanged; unused requests drain and
failures use complete ordinary reads. Layer0 retains current-layer prefetch;
layer-only/staged execution does not use early scheduling. Local251 tests/five
fixture modes and native255 tests/four modes pass. The selected profile
explicitly keeps this flag0: full121/122 comparisons found every prompt slower
with earlier prefetch (conservative score-3.47%). The first-sample stall remains
in the result; the other two prompts also regressed. See122_decision.json.

`CASCADIA_INKLING_SECOND_PREDICT_READS=1` (`SecondPredictReads1`) requires
`PredictReads1` and qualified `full-second-prefetch.exe`. Keep the first uncached
prediction and add a second only if its original predicted gate rank is within
the top three. Two independent bounded workers overlap these reads with current
attention. Actual routing, full expert bytes and cache admission order remain
unchanged. Aggregate nine-field read counters include both workers; separate
`second_prediction_reads` and `prediction_read_workers` expose the additional
work. Early mode takes precedence in the library; the wrapper rejects combined
flags. Native126 qualification passes257 tests and five exact tiny modes.
Full127/128 gains1.2–1.5%, and129 verifies nine samples with minimum1.116134,
median1.151526 tok/s. The selected profile enablesSecond1 at rank ceiling2.
The historical median gain over112 is0.20%; two samples are essentially tied.
All costs and the prior112 stall remain included. See129_profile_promotion.json.

`CASCADIA_INKLING_SECOND_PREDICT_RANK` (`SecondPredictRank`) is an experimental
zero-based ceiling1..5, default2. It changes only second-read selection and
never increases the two-reader bound. Changing it requires a qualified
`full-second-rank.exe` and `SecondPredictReads1` in the wrapper. Local130 passes
255 tests and ten fixture modes; native131 passes259 tests, seven fixture modes
and four dependency guards.132–135 full performance comparisons are active.
The selected profile explicitly retains rank2.
