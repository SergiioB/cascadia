# Inkling large975B on Panther Lake

The confirmed three-repeat record is **0.567914 decode tokens/s** on tate-07,
**4.20× the original baseline**. All nine samples passed exact token and logits
checks; their rates range from 0.567914 to 0.593815, with median 0.583751.
**The 25 tokens/s target has not been reached.**

The resumed loop has reached **0.937041 tok/s over one pass** with streamed
prefill, a 16.31 GB routed cache, request-history reset and cache-frequency decay
at 32 routed requests. All three prompts improved against the matched default
decay control; [the comparison](results/072_cache_decay_comparison.json) records
exact output and route equality. Prefill takes 24–25 seconds. The worker sweep
selected 16 threads, and the paired storage probe found no consistent async gain.

Three-repeat confirmation campaign 074 is running. See [HANDOFF.md](HANDOFF.md)
for active jobs and [RUNTIME_OPTIONS.md](RUNTIME_OPTIONS.md) for opt-in settings.
The three-repeat record above remains the confirmed result until this finishes.

## What was measured

The complete 548,985,140,942-byte int4 export is on tate-07, with all 16,654 files
SHA-256 verified. The production Inkling loader and decoder run all 66 layers,
embeddings, attention, routed/shared experts, and output head. These results use
the CPU backend with 16 threads on a Core Ultra X7 358H and 64 GB of RAM.
The Arc B390 is not used by these full-model runs.

Each pass contains three prompts: a water-cycle explanation, binary search, and
a short story. Each case generates 64 tokens, of which 63 belong to decode; the
first token belongs to prefill. The score is the slowest case/repetition,
including the first decode run and output checking. Every candidate must match
the baseline's saved greedy IDs and full-logits hash `ce0fbb9a116d3d09`.
Separate tiny-model tests check the port against the Hugging Face fixture.

| Profile | Passes | Slowest decode tokens/s | Change from original |
| --- | ---: | ---: | ---: |
| [Original baseline](results/033_large-baseline.json) | 3 | 0.135334 | 1.00× |
| [Reusable buffers, row tiles, mapped embedding](results/036-buffered.json) | 3 | 0.196934 | 1.46× |
| [Also own the shared expert bytes](results/040-owned-shared.json) | 1 | 0.235890 | 1.74× |
| [Also use uncached expert reads](results/042-uncached.json) | 1 | 0.515177 | 3.81× |
| [Control for read/compute overlap](results/044-pipeline-control.json) | 1 | 0.537715 | 3.97× |
| [Overlap each expert's read and compute](results/045-pipeline-overlap.json) | 1 | 0.570649 | 4.22× |
| [Final repeated overlap profile](results/046-final.json) | 3 | **0.567914** | **4.20×** |

The 036 SSH connection did not return after native completion. Its transport
failure remains in Autolab history; its complete native results were separately
[verified against the saved artifacts](results/036_completed_artifact_verification.json).
The full campaigns 040, 042, 044, 045 and 046 completed through Autolab normally. The final
[verification report](results/046_final_verification.json) checks all nine
case/repetition pairs, native logs, reference IDs, logits hash, binary identity,
and actual configuration counters. Those046 jobs exited; the resumed loop has
new full-model trials and a resource sampler running.

## What improved

Reusing destination allocations avoids repeatedly faulting in newly allocated
read buffers. Mapping the sparsely accessed embedding table reduces private
memory, and the row tiles retain the same numerical accumulation. Owning the
always-used shared experts adds about 4.08 GB of private weights but avoids
repeated shared-file reads.

Uncached Windows reads bypass the file-cache path for nonresident routed
experts, using aligned reusable buffers and the same packed bytes and kernels.
The final repeated run recorded 6.638 TB of successful uncached reads with zero fallbacks.
Mapped execution still handles experts selected by the residency check. Failed
or unsupported uncached reads retry a complete cached read; partial buffers are
never consumed. These are ordinary private allocations, not physically pinned
pages. All options remain opt-in.

Median expert-block time fell from 3.801 seconds/token in 040 to 1.495 in 042;
attention was 0.364 and work outside the layers was 0.025 seconds/token in 042.
Prefill still takes roughly two minutes for these short prompts, with transient
memory pressure. Decode speed does not include that prefill latency.

The matched overlap comparison improved the slowest-case score by 6.1%, with
each case improving by 4.2–12.0%. The overlap arm completed 2.72% more uncached
expert bytes, so its gain did not come from reading fewer expert bytes.
The [comparison report](results/045_pipeline_comparison.json) retains both arms.
The final three-repeat run confirms the selected profile at 0.567914 tokens/s.
Median seconds per decode token are 0.373 for attention, 1.305 for the expert
block and 0.025 outside layers. Prefill takes 100–114 seconds per prompt.
The sampled lifetime still shows transient memory pressure (minimum available
RAM 1.09 MB); it includes loading and prefills, not just decode. Protected
OVMS and Cascadia services remained running throughout.

## Reproduce the selected profile

Dot-source [ptl-profile.ps1](ptl-profile.ps1) before launching a new Inkling engine
process on tate-07. It sets process environment variables only. The benchmark
also uses High process priority and all 16 logical processors; the production
launcher [run-full.ps1](run-full.ps1) applies those conditions to its own child.

The qualified `full-pipeline.exe` SHA-256 is
`8305491ebbc4bacc09fdb3aeccbe331b153e0fd79d34a273baef2ddb5d593e8b`.
Its source is commit `18f8becb`. The exact repeated benchmark command is saved in
[campaign 046](campaigns/046_full_final_confirmation.yaml). All 233 native
qualification tests passed before this binary was used for full-model trials.
The selected process profile is verified; it does not meet the 25 tokens/s target.

The [journal](JOURNAL.md) records hypotheses, tests, and rejected approaches.
Raw layer/routing traces and sampled host resources are archived under
`results/` with SHA manifests. Machine disk counters include other processes;
page-fault counters include soft faults.

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
