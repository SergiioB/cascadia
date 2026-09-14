# Inkling large975B on Panther Lake

The confirmed record is **1.116134 decode tokens/s**, the slowest of nine samples,
**8.25× the original baseline**. The median is1.151526 and the fastest sample is
1.231289. Every saved token, full-logits hash and actual route matches.
**The 25 tokens/s target is unmet.**

[Campaign129 verification](results/129_final_verification.json) covers three
prompts × three repetitions, with64 generated tokens and63 decode steps each.
Prefill takes23.86–25.23 seconds. The conservative record is2.36% above112;
the [matched127/128 comparison](results/128_second_prefetch_comparison.json)
measured1.2–1.5% gains on the same binary. The historical nine-sample median gain
is only0.20%, and two samples are within0.02% below their112 counterparts.
The old112 first water sample included a2.67-second MLP stall; it remains in
that result. These limits are preserved in the
[repeated comparison](results/129_repeated_second_prefetch_comparison.json).
All first samples and stalls remain included; the entire historical record
change should not be attributed to the new setting.

The selected profile reads the first predicted uncached expert before attention
and a second only when its original predicted gate rank is within the top three.
Two bounded workers supply complete bytes only if actual routing selects those
experts; unused requests drain. Routing, cache admission and arithmetic remain
unchanged. Across129,53,152 predictions completed:50,539 useful and2,613 unused,
with zero read or worker failures. Of these, the second worker completed17,434
reads:16,525 useful and909 unused. Actual read bytes rise0.760% over first-only112.

The earlier first-only predictor also passed a separate
[113/114 comparison](results/114_heldout_prefetch_comparison.json) on three frozen
longer prompts and128-token continuations. Each gained15–16%, with exact
outputs/routes/cache counters and no read failures. Those runs do not measure
the second reader's speed. See [HANDOFF.md](HANDOFF.md) for active rank-selection
experiments; optimization continues without a new export or Lambda instance.

## What was measured

The complete 548,985,140,942-byte int4 export is on tate-07. All 16,654 files
were SHA-256 verified. The production loader and decoder execute all 66 layers,
embeddings, attention, routed/shared experts and output head. These are CPU
results on a Core Ultra X7 358H with 64 GB RAM and 16 worker threads. The
Arc B390 is not used by these full-model runs.

The three prompts cover the water cycle, binary search and a short story.
Every candidate must match baseline greedy IDs and full-logits hash
`ce0fbb9a116d3d09`. Separate tiny-model tests compare against the Hugging Face
fixture. Full outputs, actual configuration counters, binary identity, route
identity and the complete case/repetition grid are checked before promotion.

| Profile | Passes | Slowest decode tok/s |
| --- | ---: | ---: |
| [Original baseline](results/033_large-baseline.json) | 3 | 0.135334 |
| [Reusable buffers, row tiles, mapped embedding](results/036-buffered.json) | 3 | 0.196934 |
| [Owned shared expert bytes](results/040-owned-shared.json) | 1 | 0.235890 |
| [Uncached expert reads](results/042-uncached.json) | 1 | 0.515177 |
| [Repeated read/compute overlap](results/046-final.json) | 3 | 0.567914 |
| [Streamed prefill with 4 GB routed cache](results/054-prefill-1.json) | 1 | 0.709011 |
| [16 GB routed cache and request-history reset](results/057-history-256.json) | 1 | 0.915789 |
| [Shorter cache frequency history](results/072-decay-32.json) | 1 | 0.937041 |
| [Short-history profile, repeated confirmation](results/074-cache-confirmation.json) | 3 | 0.938274 |
| [Recent-use tie admission, repeated confirmation](results/102-cache-recency-confirmation.json) | 3 | 0.965412 |
| [One predicted expert read, repeated confirmation](results/112-predicted-read-confirmation.json) | 3 | 1.090427 |
| [Selective second read, repeated confirmation](results/129-second-prefetch-confirmation.json) | 3 | **1.116134** |

The 036 SSH connection failed to return after native completion. That transport
failure remains in Autolab history; its complete native artifacts were
[verified separately](results/036_completed_artifact_verification.json).
Campaigns074,102,112 and129 completed normally through Autolab. Each native benchmark process
exited; the resource sampler continues for subsequent trials. Protected OVMS
and Cascadia services remain running.

## What improved

Reusable aligned destination buffers avoid repeated allocation faults. Mapping
the embedding reduces private memory. Owning the always-used shared experts
retains about 4.08 GB of packed weights and avoids repeated shared-file reads.
Uncached Windows reads bypass the file-cache path for routed experts, and
pipelining overlaps each expert's read and compute. Invalid or failed direct
reads retry a complete cached read before any bytes reach a kernel.

Streamed prefill reads each unique current-block expert through a bounded pool
of reusable buffers. In the [matched comparison](results/054_prefill_comparison.json),
prefill fell from 103–108 seconds to 24–25 seconds and decode improved 20.8%.
This removed paging pressure and made a larger routed cache useful: increasing
its retained weights from 4 to 8 to 16 GB improved every measured prompt.

The routed cache uses observed routing frequency, resets its admission history
at each request and halves those counts every 32 routed requests. Weight bytes
remain unchanged. [Shorter history](results/072_cache_decay_comparison.json)
removed 3.12% of remaining decode reads and improved all three prompts against
the matched default-history control. A worker sweep selected 16 threads over
8, 12, 24 and 32. Matched asynchronous-read probes found no consistent benefit.

Campaign129 retained16.31 GB of routed weights, recorded99,853 cache hits and
117,875 misses, and completed3.838 TB of uncached decode reads with zero
fallbacks. Streamed prefill completed1.303 TB of reads with zero fallbacks.
Median time per decoded token is0.211 seconds in the attention span (including
prediction submission),0.633 in the expert blocks and0.024 outside the layers.
The sampled process peak was42.51 GB private memory; minimum available machine
RAM was1.84 GB. Decode used9.05 CPU core equivalents and read about7.83 GB/s
in the complete sampled decode intervals.
A separate Qwen OVMS service holds about 20.03 GB of shared GPU memory, as
confirmed by the [memory ownership snapshot](results/099_memory_ownership.json).
That service remains running and limits RAM available for a larger cache.
See the [layer profile](results/129_layer_profile.json) and
[resource report](results/129_resources.json). Machine disk counters include
other processes, and page-fault counters include soft faults.

## Reproduce the selected profile

Dot-source [ptl-profile.ps1](ptl-profile.ps1) before starting a new Inkling
process. It sets process environment variables only. Cache256 MiB is per MoE
layer, not a model-wide budget. The benchmark uses High process priority and
all 16 logical processors; [run-full.ps1](run-full.ps1) applies those settings
to its own child. See [runtime options](RUNTIME_OPTIONS.md) for dependencies.

The record's frozen `full-second-prefetch.exe` SHA-256 is
`71f7e4ef0364ab7ed030ca12400479deeb4f8e44c9cbe9818875a3b199d66476`,
built from source `ede10f98`. Qualification passed257 native tests, five tiny
fixture modes and three invalid-dependency guards before full trials. The exact
repeated command and expected counters are in
[campaign129](campaigns/129_full_second_prefetch_confirmation.yaml).

All raw traces and resource snapshots are archived with SHA manifests.
[The journal](JOURNAL.md) records hypotheses, measured results and rejected ideas.

## Why 25 tokens/s requires a different setup

The [whole-continuation traffic bound](results/037_full_span_traffic_bound.json)
allows perfect reuse across all 63 decode positions and an optimistic initial
32 GiB cache of routed experts. Even then, 25 tokens/s would require **46–56 GB/s**
of routed-weight reads for these cases. The observed PCIe 5.0 ×4 SSD link has a
theoretical maximum of **15.754 GB/s before protocol overhead**. The bound also
omits all computation and fixed/shared weights.

Even granting the entire nominal 64 GiB of RAM to this perfect initial cache,
ignoring every competing memory need, would still require **32.5–42.5 GB/s** at
25 tokens/s. This [more generous bound](results/047_all_RAM_traffic_bound.json)
shows that changing the chosen cache budget cannot remove the storage limit.

This rules out reaching 25 tokens/s by ordinary tuning of this packed export on
this SSD. It does not claim a limit for a different representation, model, or
hardware configuration. Current measured speed remains well below the ideal
disk-only bound; that bound is not a performance prediction.

## Export rental

These runtime experiments require no new export or A100 work. The Lambda host
at `129.146.170.51` is backed up and ready for release; no termination has been
performed. Lambda requires instance termination to stop billing, and termination
erases its local disk. See [Lambda's instance documentation](https://docs.lambda.ai/public-cloud/on-demand/creating-managing-instances/).

The [export-host guide](EXPORT_HOST.md) contains the verified backup and rebuild
recipe. With raw weights already local, a complete export is estimated at
15–30 minutes, about $4–8 at $15/hour. First download plus export is estimated at
2–3 hours, about $30–45. These are estimates from measured component/download
rates, not a timed full export. The current PTL export is already complete.
