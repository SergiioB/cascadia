# Inkling / Panther Lake research journal

## 0 — orientation (2026-09-12)

User directive: autonomously maximize Inkling performance on the single authorized
Panther Lake host tate-07 (100.82.253.76), using ../autolab; commit as t8 without
coauthors. Work isolated on perf/inkling-panther-autolab from feat/inkling 9aaebff0.
The source worktree ../tahoma-inkling was clean. Latest progress: resident 975B
export runs at 1.5 model tokens/s on the Mac Pro, after concurrent experts,
residency-adaptive reads, pinning, and physical-core Rayon defaults.

Host inspection: Intel Core Ultra X7 358H, 16 cores/16 threads, Windows 11 Pro,
64 GB RAM (~40 GB available), C: only 4.07 GB free. No Inkling export found in the
model tree. The 512 GB export cannot be deployed with this storage capacity.
Full-model throughput remains unmeasured; synthetic production-size layer/kernel
rates are NOT model tokens/s and cannot establish a single-machine model record.
No existing model, cache, source, or service is removed by this research.

## 1 — hypothesis: thread/schedule tuning

Before measurement: on this 4P+8E+4LPE hybrid CPU, default 16-thread nested Rayon
execution may be slower than a smaller pool. Sweep threads, then expert schedule
and mmap read policy, against fixed synthetic full-size attention + eight selected
int4 experts. Preserve all output bits across scheduling changes. Use identical
inputs, warmup, repeated timing samples, and independent process runs. The bank
contains eight distinct full-size expert bins; 256 router rows select six fixed
routed experts plus two shared. This represents the resident active working set,
not the full expert population or paged-checkpoint behavior.

## Next hypotheses

- Process affinity can avoid scheduling work onto the low-power cores.
- Reusing each activation vector across several bf16 output rows may improve
  the attention GEMV while preserving each row's accumulation order.
- Independent attention projections may overlap through the same Rayon pool.

Stop a finite sweep after all configurations; confirm winners in paired repeated
runs and stop code exploration when tested alternatives no longer improve by 3%.
Do not describe a tested local optimum as a proven hardware maximum.

## 1 results — thread sweep

High priority removed the initial background scheduling variance (normal-priority
first scout: 47–64 ms; High priority at 16 threads: 45.97–46.51 ms). All seven
thread counts preserve output hash `4e89f0793afa1015`. Best 16 threads: median
46.358 ms/layer-token; 12: 47.679; 10: 48.407; 8: 50.047; 6: 56.187;
4: 62.134; 2: 90.707. The smaller-pool hypothesis is refuted at this schedule.

## 2 — expert schedule/read-policy hypothesis

Before measurement: Windows working-set residency may keep using whole-bin
copies despite a warm standby cache. Direct mmap reads should avoid copies in
this resident workload; concurrent versus serial experts may change contention.
Sweep both switches at 16 threads, requiring the reference hash.

## 2 results — direct mmap wins

16 threads, concurrent experts: default adaptive reads 46.602 ms, direct mmap
18.016 ms (2.59x). Serial experts: 49.108 ms adaptive, 20.082 ms direct.
All four runs preserve every output bit. The likely explanation is Windows
standby-cache versus process-working-set residency: explicit reads can leave
the mapping unvisited, so a working-set query keeps choosing a copy. This is
a hypothesis about the cause, not a traced conclusion. Keep the production
default for paged workloads until a real checkpoint can verify that regime.
For this resident configuration, set CASCADIA_INKLING_SEQ_READS=1.

## 3 — direct-read thread and affinity hypothesis

Before measurement: once copy traffic disappears the best thread count may
change. Repeat a smaller thread sweep, then compare explicit CPU bit masks.
Do not infer P/E/LPE identities solely from bit positions.

## Paused at user request — restart checkpoint

Stopped the controller with SIGINT during campaign 003, before the 8-thread
experiment could be recorded. Completed results: 16 threads 18.141694 ms;
12 threads 19.094159 ms, both hash `4e89f0793afa1015`. The raw partial export
is retained. Resume the same campaign/SQLite database; the first unrecorded
configuration is 8 threads, then 4, 6, 10. No kernel candidate was deployed.
The bf16 row-tiling candidate is local and untested: preserve as a patch and
do not promote it until x86 tests plus fixed-hash benchmarks pass.

## Resumed (2026-09-12)

The user resumed after restarting Codex. Worktree/SQLite database/candidate patch
intact; no benchmark/build processes on the host. Existing OVMS service retained.
Campaign 003 resumed from its first unrecorded configuration, 8 threads.

Before campaign 004: compare explicit affinity masks with a thread per allowed
CPU: 0xffff/16, 0x0fff/12, 0xfff0/12, 0x000f/4. These are bit masks, not asserted
P/E core identities. Same reference hash and five repeated timing samples.

## 5 — bf16 row reuse hypothesis (before measurement)

Candidate: share each activation load across two/four independent output rows
in the production bf16 GEMV, retaining each row's exact two FMA accumulators,
reduction and bf16 rounding. Default remains the reference one-row path during
experimentation. Require new x86 bit-exact tests, the Inkling fixture suite,
and the full synthetic-layer reference hash. Compare rows 1/2/4 in one binary
with direct mmap reads at 16 threads.

## Target clarified by user

The user is offline and explicitly requested continued autonomous work until
**25 tokens/s for the large Inkling model on this one PTL box**. That target is
full-model throughput, not the synthetic layer metric. Do not equate these.
The current export requires 512 GB storage and touches about 36.5 GB per decode
token; the resident batch-1 bandwidth arithmetic in INKLING_SCALING.md is far
below 25 tok/s. Investigate actual deployment capacity and throughput semantics
alongside engine optimizations; do not silently prune/change the model or claim
an estimated layer rate as attainment.

## 3–4 results

Direct reads remain fastest at 16 threads: 18.142 ms; 12: 19.094; 10: 20.143;
8: 21.485; 6: 23.710; 4: 27.427. Affinity campaign also favors all cores:
0xffff/16 18.658 ms; 0x0fff/12 19.045; 0xfff0/12 21.889; 0x000f/4 26.667.
All output hashes match. The affinity hypothesis is refuted for these masks.

## 6 — int4 row reuse hypothesis (before measurement)

The current AVX2 expert dot keeps one FMA dependency chain per row. A two/four
row tile can interleave independent chains and reuse activation loads, while
preserving the exact within-row sequence of four FMAs per quantization group.
Test separate bf16/int4 knobs and their composition. Exclude the AVX-512 dispatch
from this path because its reduction differs. Require bit-exact row tests over
all nibble values, varied scales, odd row counts and real input dimensions.

## 5 results — bf16 row reuse inconclusive

75 MSVC tests passed (new exact-row test + all 74 Inkling tests). Full-layer
reference hash remains exact at rows 1/2/4. Median ms: 17.953 / 17.823 /
18.083. The best change is <1%, below the 3% promotion threshold. Do not
change the default from this result. Retain the candidate as an experiment
while testing whether it composes with int4 row tiling.

## 7 — independent projection concurrency (before measurement)

Inkling's Q/K/V/relative-position projections all read the same hidden vector
and are independent. Run them concurrently through nested Rayon joins, preserving
the production GEMV and all output bits. Compare the new switch on/off after
selecting the int4 setting. Test fixtures with the switch enabled before timing.

## Deployment search result

Read-only inspection found one 1.024 TB physical SSD, no spare/unallocated disk,
no mapped network drives, and a 1 Gb/s physical Ethernet adapter. A bounded,
junction-safe scan of 20,095 non-system directories (including model and user
cache locations) found no Inkling manifest. The 100 Gb/s value reported for the
Tailscale tunnel is virtual-adapter metadata, not the physical link rate.
Result: there is still no full checkpoint to benchmark locally and no capacity
to copy the 512 GB export without reclaiming other projects' storage. The target
is not reached; all rates so far are synthetic resident-layer rates.

## 8 — iGPU backend hypothesis (before measurement)

Challenge the CPU-only implementation: use the existing exporter helpers to
build one 975B-sized expert as an OpenVINO graph on the bins' original u4/bf16
scale grid, preserving bf16 boundaries after each linear. Compare CPU and GPU
component latency and validate against independent f64 dots + bf16 rounding.
Numerical gate: RMS relative error <=0.5%, worst error <=3% of reference RMS;
this allows summation-order differences, not re-quantization. It is a component
probe, cannot establish model quality/throughput, and will not silently replace
the production backend. No recompilation/cache churn or full-population paging
is included in steady-state component timings.

## 6–7 results

All row combinations preserve the full output hash. Best combined bf16=2,
int4=4 is 17.114 ms versus 17.991 ms for 1/1 in campaign 006 (~5% speedup).
Campaign 007 independently repeats 17.116 ms for that combination. Concurrent
projections regress it to 17.518 ms; with int4=1 they regress 17.871 to 18.129.
Reject projection concurrency as production code; keep its patch/evidence.
Require interleaved independent process confirmation for the combined tiling
before promoting the optional optimized path.

## 9 — paired confirmation (before measurement)

Six independent process groups, each containing the original adaptive baseline,
original direct-read baseline, and bf16=2/int4=4 direct-read candidate. Rotate
order across groups so heat/cache/order does not always favor one arm. Seven
samples per process. Every run requires the same full-layer hash. Retain the
actual arm and binary SHA256 in the raw output, since the scheduled slot is
rotated by repetition number. This tests a local layer improvement only.

## 8 result and 10 hypothesis — GPU under the active working set

The single-expert OpenVINO probe passed its numerical oracle on both devices:
CPU 1.265 ms, GPU 0.483 ms. This compares two OpenVINO paths, not a Rust
whole-model run. Next test eight distinct experts (255 MB of original int4
weights) with fused, serial and asynchronous dispatch, on CPU and GPU. Validate
each expert independently at two inputs before timing; the same numerical
thresholds apply. Excludes dynamic routing, compilation churn, attention and
paging. This determines whether single-expert gains survive the active weight
set and dispatch overhead before considering a production GPU backend.

## 9 result — confirmed, optional profile accepted

Every one of 18 independent processes preserved the full output hash. Median
across six processes per arm: original adaptive 47.325608 ms; original direct
18.389891 ms; bf16=2/int4=4 direct 17.190217 ms. The combined improvement is
2.753x. Relative to direct reads alone the tiles give 1.070x, winning in all six
paired groups (1.062–1.075x), beyond the 3% promotion threshold. Keep the tiles
as opt-in shared kernels, with original defaults on untested platforms and
workloads. Reject and remove production projection concurrency; retain its patch.

## 11 hypothesis — Windows residency diagnosis

The adaptive path may repeatedly copy file-cache-hot weights because a buffered
read does not populate the mmap's process working set. Microsoft documents that
soft page faults can be satisfied from RAM outside the process working set:
https://learn.microsoft.com/en-us/windows/win32/memory/working-set
Probe QueryWorkingSetEx on a fresh mapping before/after three buffered reads,
prefetch, and a mapping page walk. Use only our synthetic bin; do not clear global
caches or change working-set limits. This diagnoses the resident-path gap; it
does not establish how an alternative policy performs with cold real weights.

## 10 result, validation, and 12 final confirmation hypothesis

Eight experts, CPU fused/serial/async: 10.052 / 12.332 / 9.541 ms.
GPU fused/serial/async: 3.777 / 4.239 / 3.268 ms. Every expert at both inputs
passed the independent numerical oracle. Production GPU integration and full
population/paging are unvalidated; retain this as a promising component result.

Final retained CPU source: 222 MSVC regression tests passed, including all
Inkling fixtures and shared DSV4/GLM math/expert tests. The new full-decode
harness reproduces all eight HF fixture greedy IDs across three repetitions,
with fixture-only metric, full_model=0 and hash 1f7cd0eb14a22662. Clippy completes
with existing library warnings and three benchmark iterator style suggestions.

Toolchain audit correction: an explicit query reports MSVC rustc 1.98.1,
LLVM 22.1.8. Earlier hand-entered 1.95 metadata did not establish the explicit
MSVC version and has been corrected, preserving a note. To remove ambiguity
from binary/compiler differences, campaign 012 repeats the rotating comparison
using the SAME final binary for all three settings (original algorithms at
rows 1/1, direct and adaptive, versus tiles 2/4). This is the final promotion
measurement; frozen earlier binaries/results remain intact.

## 11 result — diagnosis confirmed

All 64 sampled mmap pages remained invalid after each of three buffered reads
(8.79 / 8.18 / 8.04 ms for 31.85 MB) and a successful PrefetchVirtualMemory call.
A page walk of the mapping changed the same sample to 64/64 valid. This confirms
that the adaptive working-set gate can repeatedly take the bulk-copy path for
warm file-cache data on Windows. Corrected its source comment: it is a lower
bound on file-cache residency, not a true cache-miss count. Retained the explicit
direct-read resident profile. No automatic cold/paged policy change is justified
by this probe; it would need real-checkpoint paging measurements.

## 12 result — final profile and target status

All 18 runs completed, same final binary in every arm, all hashes exact. Median
across processes: adaptive 47.105705 ms, direct 18.229506 ms, tiled direct
17.455544 ms. Combined 2.699x; incremental tiles 1.044x. All six paired groups
favor tiles by 3.37–7.50%. Use these conservative final numbers as the retained
profile result; campaign 009's frozen-binary figures remain historical evidence.

The full-model launcher was exercised at the intended deployment path and
correctly failed because no checkpoint is present. 25 full-model tok/s is NOT
reached or measured. The complete-model benchmark is built and fixture-verified,
and the full campaign template plus target gate are ready for actual weights.
The resource blocker remains ~3.4 GB free disk versus a ~512 GB export. Do not
claim an ongoing background research agent after this session or burn repeated
component sweeps as a substitute for the missing full-model measurement.

The large resident-layer speedup is conditional: real-model prefill can touch the
mappings before decode and thereby avoid some repeated copies already. Full
checkpoint routing, prefill and paging must be measured before projecting this
factor onto user-visible generation. Likewise the GPU probe omits compilation
churn across the 16,512 MoE expert instances; it is not yet a deployment strategy.


## 13 — authorized disk cleanup and checkpoint deployment

The user explicitly authorized clearing unused disk artifacts on tate-07 and
asked for the record and hardware requirements. Inspected current processes,
services, scheduled tasks, source trees and recursive disk usage. Preserved the
running Qwen3.6-35B OVMS export, its active compilation cache, cascadia services,
source trees, experiment logs, installed toolchains and all current Inkling assets.
Archived small model metadata/config/recipes before deleting dormant model
exports, duplicate HF snapshots, inactive compilation caches, generated Cargo
targets and old installer archives. Both deletion reports have zero errors.

Actual filesystem space reclaimed: **821,909,577,728 bytes (822 GB)**. Free space
after cleanup: **825,192,165,376 bytes (825 GB / 768.5 GiB)**, before deployment.
The Qwen endpoint still returned HTTP 200 and the same model, with unchanged
OVMS/node/CA process IDs. Raw path/byte audits are in `results/013_disk_cleanup*`.
The archived small metadata is under the task's two `cleanup-20260913*` folders
on PTL; these are not backups of the removed weights.

Located the complete unchanged export on `miner:/mnt/external_ssd/inkling/out`:
548,985,140,942 bytes, 66 shells, 16,514 expert bins (including two dense layers),
plus embeddings, head and tokenizer/config. No new export is needed for the
retained CPU kernel changes. CPU execution of the full model on PTL remains
unmeasured; the best documented complete large-model rate is **1.5 tok/s on the
1.5 TB Mac Pro**, not the PTL component rate.

Deployment hypothesis: avoid the controller Mac relay to reduce transfer time.
The Mac-to-PTL Tailscale route used DERP with 737–875 ms latency and copied at
about 2.8 MiB/s. PTL-to-miner used DERP at 58–69 ms. A read-only export endpoint
bound only to miner's Tailscale IP, restricted to PTL's source IP and an ephemeral
Bearer token, verified a real 31,850,496-byte expert against its source SHA-256 in
11.843 s. This single-file check does not establish bulk throughput. Full copy
started with four independent streams, then resumed with eight streams and per-file source/destination SHA-256 checks.
Only verified complete files get final names; interrupted copies resume and a
permanent error cancels pending files. The server stops after successful transfer
or expires after 96 hours. No SSH private key or public Funnel was shared.

The disk prerequisite is resolved. Checkpoint transfer, full autoregressive
baseline, and correctness-checked optimization trials remain. The transfer and
finite benchmark jobs are distinct from the session's autonomous research loop.

## 14 hypothesis — first complete PTL baseline, queued behind verified transfer

Before promoting another kernel or paging policy, establish the actual complete
model behavior. A finite native PTL job will wait for the all-files SHA-256
marker, verify the frozen executable, reproduce the documented `Paris` answer,
and then record three long prompts at 64 tokens and three repetitions under
the original adaptive rows=1/1 settings. It will stop on transfer failure,
timeout, changed executable, incorrect smoke text, incomplete sample counts or
short completion. The initial baseline has no supplied expected IDs and is
explicitly not correctness-verified by the benchmark; review its generated text
and use its IDs/hash to configure the next Autolab comparison. This queued job
collects evidence only and cannot claim the 25 tok/s target or promote a change.


Deployment checks: localhost integration passed missing/wrong authorization,
path traversal rejection, changed-source rejection, exact Range suffix, resume,
repair of same-size corrupt destination, zero-byte file, full marker accounting,
and authenticated shutdown/token deletion. The source/destination 31.85 MB PTL
expert hash check also passed. `--prepare-only` passed on PTL with documented
25-token Paris framing and long prompt lengths 30/32/31; corrected Transformers
5.2's default BatchEncoding return by explicitly extracting input_ids. The
PowerShell launcher parses successfully. Native transfer and waiting baseline
were independently observed after their initiating SSH sessions exited. No
full-model benchmark result or promotion is implied by these deployment checks.

Bulk deployment result: bypassing the Mac did NOT improve sustained transfer.
Eight streams gained 128,974,848 logical destination bytes over 48.297 seconds,
**2,670,453 bytes/s (~2.7 MB/s)**. At that rate the remaining checkpoint needs
roughly 57 hours. Extended temporary server expiry and baseline transfer wait
to 96 hours; per-file integrity and baseline gates are unchanged. The immediate
deployment constraint is the network route, not export CPU time.

The native transfer recovered from the scoped server restart and SHA-256
verified a 270,929,340-byte full shell file. The finite baseline queue is waiting
as PID 3856 (parent cmd 7388); transfer PID 7060 (parent 7232); temporary source
server PID 199701. Removed eight unused rclone chunks, another 573,833,216 logical
bytes, with a separate audit; active native partials were retained.


## 15 hypothesis — optional CUDA acceleration for export quantization

The user requested CUDA export acceleration. Current export is 548,985,140,942
bytes (549 GB / 511.3 GiB). The CPU packer expands bf16 matrices to f32 and
materializes several quantization intermediates per expert; moving group-32
quantization and nibble packing to CUDA could reduce conversion time while
leaving source streaming, staging, atomic writes and the PTL layout unchanged.
Implement an explicit opt-in device and bounded GPU working set, retain CPU
defaults, and require byte-level parity on boundary inputs and complete tiny
exports before measuring speed, including transfers. An idle RTX 4060 Ti 8 GB
on miner is available for validation; no rental is needed for this phase.
Record component and conversion/write timings separately; do not extrapolate a
quantization speedup into a measured whole-975B export improvement.

CUDA parity diagnosis: the first eager implementation failed before writing
exports. PyTorch's CUDA division by a Python scalar uses reciprocal multiply,
whereas CPU f32 division uses true division. On bf16 random inputs this changed
13 quantized values in the startup probe. Replaced the divisor 7.0 with a scalar
tensor on the selected CUDA device to retain true division. Reference source:
https://github.com/pytorch/pytorch/blob/main/aten/src/ATen/native/cuda/BinaryDivTrueKernel.cu
All 42 CPU/CUDA exporter tests then passed, including float32/bf16/float64,
strided/chunked inputs, half-integer and scale rounding, concurrent workers,
complete tiny model/HF token parity and all streaming/deletion/resume paths.

Initial timed conversion: eight distinct synthetic production-sized experts
(6144 hidden, 3072 intermediate), source safetensors in the warm file cache,
three repetitions in alternating CPU/CUDA order, eight export workers. Includes
source slice reads, CPU/GPU copies, quantization, byte serialization and atomic
fsynced output writes. CPU median 1.584464 s, CUDA 0.738039 s: **2.147x**. Every
output SHA-256 matches CPU; peak CUDA allocation about 206 MB. This is a subset
conversion measurement, not a measured full-975B export or inference speedup.

Follow-up worker/chunk experiments retained 64 MiB chunks and four CUDA I/O
workers; 128 MiB regressed. Final comparison uses the faster tested CPU pool
(eight workers) against CUDA four workers, five repetitions with alternating
order: CPU median **1.483070 s**, CUDA **0.626925 s**, **2.366x**. All 80 output
files across ten attempts match their CPU SHA-256. Peak PyTorch allocation is
205,521,408 bytes; CUDA context and allocator reservations are additional.
Results include the initial, four-worker, rejected 128 MiB and selected trials.

Real-weight qualification fetched only layer 2 expert 0's original bf16 tensors
(113,246,208 bytes) using HTTP Range at the source revision
`828496eeae4c243ff1a22f7f28ff83694f2f7bc9`. Both CPU and CUDA reproduce the frozen
31,850,496-byte `expert_000.bin` exactly: SHA-256
`98792b4c2db0369cab8da5d8f12d8acf794e8b1b248b40c3dcb368b535bec8da`.
Five alternating repetitions, including transfers and byte serialization but
excluding file reads/writes: CPU median **0.270414 s**, CUDA **0.063884 s**,
**4.233x**. This is one real expert, not a whole export timing.

Final exporter validation: **43 passed in 17.43 s** on RTX 4060 Ti 8 GB,
PyTorch 2.14.0+cu130, Transformers 5.16.1. Added a failure-before-output test for
unavailable CUDA. The GPU returned to idle (32 MiB, 0% utilization). No rented
hardware was provisioned, no complete checkpoint was re-exported, and the
original CPU environment/export are unchanged. The new isolated miner venv
and real source sample remain available for subsequent exporter work.

PTL deployment remains independent: transfer PID 7060 has SHA-256 verified
19 files / 5,147,657,460 bytes with no errors; finite baseline PID 3856 is still
waiting. Existing OVMS/node/CA PIDs are unchanged. CUDA export acceleration
does not change the recorded full-model inference rate or establish 25 tok/s.

## 16 deployment — make the user's 8xA100 host the default exporter

The user designated `ubuntu@129.146.170.51` for all future exports. Existing
`~/.ssh/amx-bench_ed25519` authenticates; the default and cascadia identities do
not. Added controller SSH alias `inkling-export` with the working identity.
Read-only inventory confirmed eight idle A100-SXM4-40GB GPUs, driver 580.105.08,
about 1.7 TiB RAM, 124 visible CPUs and 5.7 TiB free root disk. Preserve the
host's existing Jupyter/container/monitoring services.

Prepare an isolated `/home/ubuntu/inkling-export` environment, deploy the
committed exporter, and qualify byte parity on A100 before future conversions.
Record the host in `export-host.json` and use `export-remote.py` by default.
The current packer uses one selected GPU; this setup does not imply eight-GPU
scaling. No new full export is necessary for the existing PTL kernel changes.

## 17 hypothesis — use the eight GPUs only if measured scaling justifies cost

The user requested export ETA/cost at about $15/hour and resumed the PTL loop.
Single-A100 qualification passed all 43 tests. Five alternating eight-expert
trials: CUDA median 0.478556 s, versus miner CUDA 0.626925 s (1.310x).
Scaling that warm-source expert stage to 16,514 bins is about 16.5 minutes
versus 21.6 minutes, excluding dense-size differences, shells, cold I/O and
downloads. It does not establish a full-export ETA. Test one process with an
available-device queue so independent matrices can use all eight GPUs while
the existing exporter remains the only owner of staging and output files.
Require multi-GPU byte parity and tiny HF parity before timing.

Deployment hypothesis: the user-supplied direct SSH jump route can shorten
PTL deployment. Existing cascadia key works for both guest@192.55.48.214 and
devcloud@192.168.22.2. A random 32 MiB scp took 4.618 s (7.265 MB/s including
SSH startup), with matching SHA-256. Check sustained traffic with the current
verified-copy machinery before replacing the working Tailscale transfer.

Campaign 017 completed eight configurations; all output hashes match the
miner reference. Best eight-expert result is cuda:all with four workers,
20.143 experts/s, about 1.58x miner CUDA. More workers did not help this short
batch. Test 64 experts next: a larger queue might sustain eight GPUs better
and will expose whether extrapolating eight experts understates I/O cost.

The direct-route native client copied and SHA-256 verified a real 31,850,496-byte
expert in 2.235 s. Replaced only transfer PID 7060 after this gate passed;
the new native transfer was launched by parent cmd PID 10884. Existing data and
partials resume, and the baseline queue remains unchanged. The source endpoint
is restricted to miner localhost and reached through two SSH loopback forwards
on the controller; no SSH private key leaves this device. Supervisor PID 85720
restarts those forwards and expires after 96 hours or verified deployment.

Direct-route sustained result: destination grew 2,410,908,384 bytes in
117.574 seconds, **20.51 MB/s**, about 7.7x the prior 2.67 MB/s bulk rate.
No transfer errors; baseline is still waiting. At that sample rate about
7.2 hours remain. Hypothesis: 32 independent HTTP/SSH channels can better fill
the path than eight. Raise only the transfer worker cap (bounded 1 MiB buffers),
resume existing partials and measure logical growth again. Preserve services
and revert the worker count if sustained throughput regresses.

Campaign 018 completed all four 64-expert configurations, with identical hashes
and per-file CPU parity. Best remains cuda:all/four workers, 22.656 experts/s
(2.824842 s for 64), versus 18.054 on one A100. More workers lost. The selected
remote launcher now uses cuda:all/four workers. About 12.1 minutes/$3.04 for
16,514 expert bins is only a scaled warm-source stage estimate.

The pinned raw checkpoint is 1,904,604,285,204 bytes. A four-worker 1 GiB guest
O_DIRECT probe measured 3.82 GB/s writes and 13.79 GB/s reads; the latter can
reflect lower-level cache and must not be assumed for the full source. Serial
256 MiB HTTP ranges measured median 39.3 MB/s, implying roughly 13.5 hours if
naively downloaded serially. Test parallel ranges before using that pessimistic
download/cost estimate; downloaded probe bytes are discarded, not full shards.

Parallel download probes: eight streams measured 196 and 323 MB/s (median
259.5 MB/s); sixteen streams varied widely and did not improve the median.
At eight-stream observed rates, 1.9 TB takes about 1.6–2.7 hours before export.
Planning estimate: 15–30 minutes/$4–8 with raw weights local; roughly 2–3 hours/
$30–45 for the first download plus export at the user-supplied $15/hour rate.
These are extrapolations, not a measured full-model export or sustained 1.9 TB
download. The current PTL loop needs no re-export and no A100 rental during copy.

32 transfer workers on one SSH jump transport regressed to 18.13 MB/s. Source
storage is an actual SanDisk Extreme Pro USB SSD and source CPU use is modest.
Hypothesis: the nested jump channel's flow-control window limits a single
transport; more HTTP workers cannot enlarge that outer channel. OpenSSH's
current default TCP channel window is 64 * 32 KiB:
https://github.com/openssh/openssh-portable/blob/master/channels.h
Test four independent SSH transports with 16 HTTP workers to the same loopback
source. Preserve per-file source/destination SHA checks and resume semantics.

Four independent transports confirmed the hypothesis: 8,727,035,904 logical
destination bytes added in 188.161 seconds, **46.38 MB/s**, versus 20.51 MB/s
with one transport/eight HTTP workers and 18.13 with one/32. Approximately
three hours remain at the observed four-transport rate. All per-file checks
continue and the full baseline remains queued. Test eight transports next to
approach PTL's 1 Gb/s link. This optimizes deployment, not model token throughput.

A100 work is complete and GPUs idle. The remote launcher selected cuda:all/four
workers, 45 GPU exporter tests passed, and nine controller/transfer tests passed.
The configurable transfer CLI test exercises denied auth/traversal, partial
resume, same-size corruption repair, repeated endpoints, zero-byte files,
the all-files marker and authenticated shutdown/token cleanup.

Eight jump transports confirmed further scaling: 20,670,971,904 logical bytes
added in 199.334 seconds, **103.70 MB/s**, near the 1 Gb/s Ethernet limit and
38.8x the original 2.67 MB/s DERP bulk transfer. Retain eight transports with
32 HTTP workers. Remaining copy estimate at that sample: 1.26 hours. New native
client PID 4740 (parent cmd 9040), baseline queue PID 3856 still waiting, no
transfer errors. Additional supervisor PID 89290 owns ports 18872–18875.
Full-model inference is still unmeasured; no 25 tok/s claim is implied.

## 20 hypothesis — measure routed-expert reuse before changing cache policy

The full 549 GB export exceeds PTL RAM, but each token selects only six routed
experts plus two shared per MoE layer. Actual reuse determines disk traffic.
Add an opt-in route observer and benchmark trace output, prove that tracing
preserves fixture logits/greedy IDs, and prepare a working-set analyzer. Keep
the frozen queued baseline executable unchanged. Once the real baseline is
available, use traces from correctness-checked runs to quantify routed working
sets over token windows and estimate cache misses. Do not infer full-model
residency or 25 tok/s feasibility from one layer or synthetic routes.

Diagnostic validation completed: **75 Inkling MSVC tests passed** across eight
test targets, including observer-on/off bitwise prefill/decode parity. New
`bin/full-routing.exe` with and without trace output and the frozen baseline
all reproduce the eight HF fixture IDs and logits hash `1f7cd0eb14a22662`.
The PowerShell launcher also passed its fixture trace invocation. Original
`full-decode.exe` SHA-256 remains unchanged; the queued baseline still uses it.
Compiler is rustc 1.98.1 / LLVM 22.1.8. The routing analyzer's three tests cover
window unions, layer identity, prefill warming, LRU eviction, repeated-route
validation and rejecting partial traces labeled as full models.

Current export metadata: 23,041,852,040 bytes of fixed shell/edge/dense files,
4,076,863,488 shared-expert bytes, and 16,384 routed bins of 31,850,496 bytes each.
These are file sizes, not a process working-set measurement. The analyzer keeps
routed cache budgets separate from fixed/shared weights and other memory use.
No real routing trace or full-model throughput result exists yet.

## 21 hypothesis — separate conversion processes may improve A100 utilization

The eight-GPU thread pool improved throughput only modestly. Python byte
serialization and host-side work still share one interpreter. While the PTL
copy proceeds independently, test one, four and eight converter processes with
disjoint expert outputs and CPU affinity. Compare the same 64 production-sized
synthetic experts against the saved CPU hashes, exclude startup from conversion
timing and include atomic fsynced output writes. This is a bounded cost-saving
experiment; no raw checkpoint download or full re-export is needed. Only build
a production multiprocess launcher if the measured gain justifies it.

Separate interpreters confirm the hypothesis: median 64-expert conversion times
are 3.620183 s (one process/four workers), 1.745651 s (four/one each), and
1.085111 s (eight/one each), with all CPU output hashes exact in all nine
samples. Eight processes yield 58.980 experts/s, 3.336x this one-GPU control
and 2.603x the previous best eight-GPU thread pool. At 16,514 bins this scales
to 4.67 minutes/$1.17 for the expert stage only. Per-expert rate relative to
miner is 4.62x CUDA / 10.93x CPU, but those comparisons use different batch
sizes (64 versus eight); do not present them as measured full-export speedups.

Added opt-in Linux --processes with disjoint per-process layer bins, CPU
affinity, output flock and parent-death cleanup. Complete source is required;
parallel source deletion and streaming are rejected. Source config is written
once; only the parent publishes shells/sidecars/manifest after all children
and final bins pass. Complete sharded tiny export, staged resume, truncated
output repair and child-failure behavior passed. All 48 CUDA/exporter tests
passed in 39.34 s. Remote profile selects eight processes/one worker; default
CPU behavior remains one process. All GPU jobs ended and eight GPUs were idle.
Keep the overall local-source export budget at 15–30 minutes until cold I/O
and a real full export are measured; download remains the expensive first use.

## 22 hypothesis — full-model paging may dominate the resident kernel gains

PTL has 64 GB RAM, while fixed export tables occupy about 23 GB and the existing
OVMS service has a 20 GB working set. The routed expert population is 522 GB.
Observe the queued full baseline from a separate low-frequency sampler to
measure available RAM, process CPU/working set/commit/page-fault counters and
physical-disk I/O. Scope process counters to binaries in this task's bin folder,
retain the protected service, and label machine-wide disk activity as such.
This diagnostic may distinguish CPU work from paging without changing model
math or restarting the frozen baseline queue. Wait for actual decode evidence
before selecting the next cache/I/O experiment.

## 23 hypothesis — one Windows prefetch call per selected expert set

Code review found that Inkling calls PrefetchVirtualMemory separately for every
selected expert, before the parallel buffered-read path. Microsoft documents
that the API accepts discontiguous ranges and can issue concurrent I/O across
them; it does not promise those pages join the process working set:
https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-prefetchvirtualmemory

Hypothesis: a single call with eight ranges reduces I/O latency relative to
eight serial calls. Compare no prefetch, serial, parallel calls and one range
batch on disjoint existing expert files, in rotating order. Measure call time,
subsequent page-touch time and machine disk-read deltas. Do not flush shared
caches, modify checkpoint bytes or label naturally mixed-cache samples as cold.
Stop this component probe if full-model deployment becomes ready, so it cannot
overlap the queued baseline. Only implement a production change if measured.

Hypothesis refuted on this device: median page-in plus native-copy time for
eight 31.85 MB experts was **65.021 ms no prefetch, 66.508 ms serial calls,
96.951 ms parallel calls, 86.745 ms one multi-range call** (six rotating
cohorts each). Every native copy SHA matches its mapping. Physical disk-read
counters show about 254 MB per 255 MB cohort, so the tests observed substantial
real I/O despite not flushing shared caches. Concurrent checkpoint transfer
continues and is a stated confounder. Serial prefetch is already effective;
parallel/batched variants lose, so make no production prefetch change. No
prefetch is only a 2.3% component difference and needs a full-model test before
promotion. Prefetch calls took nontrivial time, so existing comments should
not be read as a guarantee that a hint returns immediately.

Host sampler validation passed with installed psutil 7.2.2. Native sampler
PID 2208, parent cmd 8336, records host-resources.jsonl every 10 seconds under
a task lock. It exits when the baseline queue is terminal and no task full
binary remains, or after 96 hours. Initial available RAM was ~39.6 GB; no
full-model process yet. It records only task-owned full binaries' process
counters and labels disk counters as machine-wide.

Retired unused Tailscale source server PID 199701 after checking its exact
/proc command. The current jump-path source server/client/tunnels are unchanged.

## 24 hypothesis — buffered reads may not need an earlier prefetch pass

Experiment 023 measured ~38 ms inside the serial prefetch calls themselves.
The default nonresident path then performs parallel whole-file reads as well.
Hypothesis: omitting the earlier hints lets those bulk reads do the same I/O
with less overhead. Compare parallel buffered reads with/without serial hints
and retain the serial-hint+native-mapped-copy control. Exclude the 192 files
already used in 023, rotate profiles, retain SHA equality checks, and report
physical reads. No cache flush; stop before the queued baseline can start.

Buffered-read probe: hints + read 112.698 ms versus read alone 104.155 ms
(8.2% throughput difference); serial hints + mapped copy 63.475 ms. Physical
reads are again ~255 MB per cohort, all hashes pass. Allocation/copy behavior
differs between buffered reads and the preallocated-copy diagnostic, so this
only strengthens the case for testing the existing direct-map profile on the
real model. Do not add a second prefetch switch or promote a 2.7x resident
result to full-model throughput. Keep q15 pending the full baseline comparison.

## 25 hypothesis — attention and MoE timing will identify the next backend target

The external sampler separates paging from CPU use but cannot locate time
within the model. Add opt-in per-layer attention/MLP timing for decode and
prefill, default off and exact logits unchanged. Validate traced/untraced
fixture output against the frozen binary, preserve the queued executable, and
combine timings with routing traces in the next correctness-checked full run.
This avoids selecting a GPU or caching change from resident microbenchmarks
without knowing which component dominates the real workload.

Layer timing qualification passed: **76 Inkling MSVC tests**, including
observer-on/off bitwise prefill/decode parity and disabling callbacks. New
full-profile.exe, both unobserved and with simultaneous routing/timing capture,
reproduces all eight HF fixture IDs and hash 1f7cd0eb14a22662; the PowerShell
wrapper does too. Frozen full-decode.exe SHA is unchanged. The analyzer
accepts the measured fixture decomposition, rejects fixture-as-full, missing
layers and inconsistent duration sums. No real full-model timing exists yet.

Diagnostic binary SHA-256:
437c7134198fd99b167e45ab76e4cd1c963bc7af8d17e43215de985c13ea6386.
Use run-full.ps1 -Binary full-profile.exe -RouteTrace FILE -LayerProfile FILE
for the next correctness-checked full run; no change to the queued baseline.

## 26 deployment completed — first complete PTL model is running

All 16,654 files / 548,985,140,942 bytes passed SHA-256 verification, no transfer
errors. The final resumed copy took 4,851.64 s. Native source endpoint and
three controller tunnel supervisors exited automatically. The frozen model
loaded in **37.309 s**, full_model=1, and is running the queued smoke test.
Initial working set 25.7 GB/private commit 24.3 GB; available RAM ~15.7 GB.
Do not start a competing full run; the queue will run the longer baseline
if the Paris smoke passes. No full-model token-rate result exists yet.

The full-model smoke answered **Paris** exactly. Initial throughput is
**0.109008 tok/s over three decode steps** (27.521 s); prefill 81.483 s.
This is a short smoke, not a qualifying >=32-step/repeated throughput record.
The longer baseline started: launcher 10976, full-decode.exe PID 7340, same
queue 3856. Its load took 29.913 s. Sampler observed available RAM below 1 GB
during prefill and model working-set peaks above 43 GB. Preserve existing
services; collect longer decode samples before selecting changes.

## 27 rental release readiness

User identified Lambda.ai, with no attached persistent filesystem. All A100 jobs
ended, no GPU compute processes; raw checkpoint absent and exports empty.
Backed up deployed code, all task logs, config and package freeze to the
controller (345,278 bytes), source/destination SHA-256 identical. Committed
restoration recipe and exact requirements; existing-environment install dry run
checked 56 packages and would make no changes. No fresh environment rebuild
is claimed. PTL model and baseline are independent of the rental.

Lambda documents termination as the billing stop; guest shutdown still bills
and suspend is unsupported. No provider account access found and no termination
performed. User can release 129.146.170.51 through the Lambda console.

First long baseline sample arrived while preparing this handoff: water_cycle,
repetition 0, prefill 100.131945 s, decode 443.772822 s / 63 steps = 0.141965
tok/s. The other repetitions/cases remain active. No complete repeatability gate
or baseline hash yet; do not promote this partial observation as a final record.

## 28 hypothesis — map the sparse embedding table to reduce private memory

The full loader copies the entire roughly 2.47 GB embedding table into a
private bf16 vector even though inference reads only one 12 KiB row per token.
The PTL sampler already observed available memory below 1 GB and substantial
pagefile use with the existing services present. Hypothesis: opt-in read-only
mapping of the embedding table reduces private commit and paging without
changing any weight or arithmetic. Keep the output head resident since every
logit evaluation reads it. No checkpoint conversion or rental is needed.

Prepare locally while the frozen baseline runs; do not compile/benchmark on
PTL concurrently. Validate mapping bounds, dtype/shape/alignment, mapping
lifetime and exact fixture logits/greedy IDs before any full-model trial.
Measure actual private-memory savings and full throughput before promotion.

Local qualification: 217 tests passed across library, eight Inkling targets,
DSV4 model and GLM5 loaders. Both complete tiny model runs produce all eight
HF greedy IDs over three repetitions and the same full-logits hash
5122e042f9b1fb30 (ARM debug fixture, not the Windows hash). Mapped mode reports
embedding_mapped=true; the control reports false. Clippy completed with
existing warnings; the new alignment style suggestion was corrected. MSVC
qualification is prepared but waits for the active baseline to finish.

Partial baseline counters over 290.25 s: 5.29 core-equivalents, 84.7% of
process CPU in kernel, 2.108 GB/s machine-wide disk reads, 518k page faults/s
including soft faults. Minimum available RAM during this run was 7.58 MB.
These support a direct-read experiment but do not establish exclusive I/O
attribution, exact phase timing or a speedup for the new embedding option.

Native finite qualification is staged and waiting: Python PID 7892 / cmd 596.
It waits for successful baseline completion and the baseline task lock, then
builds/tests a separate full-mmap-embed.exe and verifies the MSVC fixture hash
1f7cd0eb14a22662 in mapped/unmapped modes. It refuses active full benchmarks
and existing candidate binaries, preserves the frozen hash, and never launches
a full-model trial or promotes a result. Waiting state was observed; source
parse and deployment/frozen-hash checks passed. Native results remain pending.

## 29 hypothesis — estimate n-gram speculation opportunity from observed text

At 36.5 GB/token in the current layout, 25 tok/s would require about 0.91 TB/s
of weight traffic unless multiple tokens reuse weights. The existing scaling
note already identifies this limit and expects limited routed-expert reuse.
Before implementing an n-gram verifier, use only each recorded prompt plus
already generated prefix as the drafter's input; compare proposed tokens to
the saved continuation only as an offline oracle. Report accepted drafts and
optimistic target-call reduction, not measured tokens/s or a target result.
Short first-repetition samples are indicative only. This needs no rental.

Observed all three first-pass cases (63 decode steps each): water_cycle
0.141965, binary_search 0.135469, short_story 0.138188 tok/s. Repeats remain
active; final full-model hash/slowest repeated metric are still pending.

Offline n-gram result: minimum suffix length 1 accepts one draft token in each
of the first two cases and none in the story. Optimistic call reduction is
only 1.016x / 1.016x / 1.000x, with 1.40–3.51x target-input rows depending on
budget/case. Minimum length >=2 accepts zero drafts. This rejects implementing
this n-gram path for these short prompts now; it does not rule out other
drafters or more repetitive/longer workloads. No inference speedup claimed.
No-repeat, periodic exact-match, prefix-continuation and zero-budget analytical
checks passed. The implementation recursively extends only the observed prefix
and its own proposals; saved future tokens are used only by the offline verifier.

## 30 hypothesis — reuse buffered-read storage to avoid fresh page faults

The baseline's ~518k process page faults/s is close to one new 4 KiB page
for its ~2.04 GB/s explicit read traffic. The default expert path allocates
and discards a ~31.85 MB vector for each nonresident expert. Hypothesis: a
small reusable pool of read buffers avoids this private-page allocation cost
while preserving bulk reads. This is distinct from mapped compute and needs
a component check before production changes.

Extend the existing disjoint-file probe with reusable readinto buffers and
per-process page-fault counts. Allocate/touch the fixed 255 MB pool once outside
the steady-state timer and report that setup separately. Compare allocating
reads, reusable reads, and prefetch+mapped-copy controls; preserve all SHA
checks. Do not run while the full baseline or native qualification is active.

Preparation checks passed: exact reusable bytes, short reads, premature EOF
and trailing bytes. The deployed Windows script rejected --after-baseline
while the full run was active, before allocating the pool or reading experts.
No component measurement or production pool implementation has run yet.

Prepared four explicit full-model profiles (baseline, direct, tiles, mapped)
instead of the old eight-way Cartesian template. All use the same qualified
full-mmap-embed.exe; only the intended read/row/embedding knobs vary. Template
parses as four experiments. The baseline hash remains an explicit placeholder,
so no full campaign is launched prematurely. The first actual campaign can
select only the candidates justified by the component/diagnostic measurements.

## 31 retired transfer credentials removed

All transfer endpoints/supervisors had ended and PTL's full copy was verified.
Removed four obsolete task tokens across controller, miner and PTL; the other
two token paths were already absent. Verified all six paths absent afterward.
No token contents were read into reports; model files and live baseline were
untouched. Result031 records only paths/removal status.

## 32 resource sampler must survive between campaign trials

The original sampler exits when the baseline queue is terminal and no full
process is currently alive. Reusing that behavior for a sequential campaign
would stop sampling in the gaps between candidate runs. Add explicit bounded
follow-trials mode with a task stop marker; retain the original default for
the already running baseline sampler. Validate terminal-baseline behavior
without running another inference workload. No speedup claim.

Native isolated canary passed: default mode stopped after one sample with a
terminal baseline/no model process; follow-trials remained active for two
idle samples and exited cleanly on its stop marker. No inference workload
was started. Existing baseline sampler2208 continues its original in-memory
code; use a new output/stop marker when starting the campaign sampler.

Buffer probe timing refinement before measurement: both fresh and reusable
read paths open/close the file inside the timer. Only destination storage is
reused; preopened mapping handles are not an extra advantage for the candidate.

## 33 full baseline complete and reviewed

All nine samples completed,63 decode steps each, three prompts x three repeats.
Slowest rate **0.1353339381 tok/s**, full-logits hash **ce0fbb9a116d3d09**.
Repeated logits and greedy IDs match. All three texts were reviewed and are
coherent; fixed64-token generation intentionally truncates these longer answers.
Initial baseline has no supplied greedy IDs and reports correctness_verified=false;
its saved reference cases/hash now gate subsequent changes.25tok/s remains unmet.

## 34 hypothesis — direct reads remove repeated buffer allocation during decode

First full candidate uses the qualified new binary, direct reads, rows1/1,
mapped embedding off. Keep all three reference cases and64 generated tokens,
with one repetition for initial diagnosis. Capture routing and layer timing;
require the exact full baseline hash and reference IDs. One repetition cannot
satisfy the25tok/s target gate. Promote only after full repeated validation.

Native qualification completed:216 tests passed, plain/mapped fixture hash
1f7cd0eb14a22662 and all expected IDs match. All four comparison-wrapper arms
also match; actual embedding_mapped agrees with the selected arm (result033).

Buffer probe030 completed30 samples, all SHA verified. Reused buffers reduce
median faults from62,390.5 to53 per255MB batch, while time improves36.872ms to
33.714ms (~9.4% throughput). Machine disk bytes remain253.755MB median. Setup
46.930ms excluded/reported. Prefetch hurts these buffered reads. This supports
allocation-churn reduction but no full-model speedup yet; earlier transfer-active
component timings are not a controlled cross-run comparison.
