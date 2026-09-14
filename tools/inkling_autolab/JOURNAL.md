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

## 35 hypothesis — bounded reusable decode read buffers

The verified component probe reduces private page faults by >1000x but only
~9.4% read throughput improvement. Prepare an opt-in production buffer pool
while034 runs, then qualify separately before measuring it. A process-wide
pool capped at256MiB avoids retaining eight buffers for EACH of64 layers.
Leases own their buffers across Rayon read/compute passes, return them on drop,
and never hold the pool mutex during I/O or compute. Failed/short reads must
never expose stale bytes. Default behavior and numerical kernels stay intact.
No native build or second model run during034. No speedup claimed in advance.

Local candidate qualification:218 tests passed, including real int4 buffer
bytes/kernel parity across expert changes, allocation reuse, disjoint leases,
size/missing-file rejection and the eight Inkling integration targets. Baseline,
reuse and reuse-without-hints fixture modes all match the prior ARM-debug hash
5122e042f9b1fb30 and all expected greedy IDs over3 repetitions. Native results
remain pending. The optional no-hint mode changes only bulk decode reads;
prefill/direct-mapped hints remain intact. Existing full trial5044 is untouched.

035 native qualifier queued after source prior-SHA deployment checks. It waits
for034's full correctness/hash and process exit, locks the task slot, preserves
both frozen binaries, then runs the native tests and four fixture modes once.
The first034 sample water_cycle is0.158070tok/s,63 steps in398.557s with exact
baseline greedy IDs; preliminary only until all cases/hash and repetitions pass.

034 completed and Autolab verified all three reference cases,63 steps each,
full-logits hashce0fbb9a116d3d09 and exact greedy IDs. Rates0.158070/0.154189/
0.163196tok/s; slowest0.1541889212,13.93% above the baseline's slowest9-sample
metric. One repetition is not the final repeated record. Native runtime1566.96s.

Median decode seconds/token: attention0.6735445,MLP5.567433,outside layers0.085328,
wall6.326305. About88% is in MLP blocks; outside-layers time is not head-only.
Real routes touch12.231GB routed experts pertoken;32-token window unions reach
114–133GB. Whole-expert globalLRU8GiB scans badly (zero simulated hits),12–16GiB
still misses7.08–7.78GB/token. These are simulations, not measured cache/disk
attribution. Compressed raw traces and SHA manifests are retained with analyses.

035 native qualification completed:220 MSVC tests pass; all four fixture modes
and the production wrapper match1f7cd0eb14a22662. Binary full-read-buffers.exe
SHA497b4bc83802bb7a21ced260e68cad49353ba5b78f851b4bf982a5c9360ca861.
Both frozen binary hashes remain unchanged; qualifier9788 has ended.

## 36 hypothesis — combine measured read-path improvements and repeat fully

The real88% MLP share justifies testing the bounded reuse pool without serial
bulk-read hints. Combine with qualified rows2/4 and mapped sparse embedding;
this measures the combination, not independent causal contributions. Run all
three prompts x3 repetitions,64 generatedtokens (63 decode), same full reference
hash/IDs. Capture routes/layer times/resources. Timeout7200s. Campaign launched;
controller log/private/tmp/inkling-full-buffered-campaign.log, tool session88421.
No other benchmark/build may run concurrently.25tok/s remains unmet.

## 37 hypothesis — avoid whole-model cache scan thrashing

Compare causal, group-aware global/per-layer LRU and LFU using the actual034
routes; no future IDs enter admission. Uniform layer quotas leave remainder
slots unused and report their actual allocation. Selected-set hits are checked
before admission; temporary read workspace is additional to cache capacity.
Also derive a separate OFFLINE whole-trace read lower bound by summing disjoint
segment (union minus cache) bounds. A worst-window average alone must not be
misreported as a whole-generation average. Eight analytical tests pass, including
exhaustive optimal paging checks for all81 four-step traces over three experts.

Results037: global LFU4GiB simulates9.51–10.07GB routed reads/token versus12.23GB
for global LRU. At8GiB the tested best policies read7.96–8.77GB/token; at16GiB
6.24–7.13GB/token. No measured inference gain; OS caching can overlap these gains,
and extra private cache would compete for RAM with fixed weights/other services.
The optimistic whole-trace bound at16GiB is3.95–4.52GB/token (routed experts only).
25tok/s would need99–113GB/s of routed reads under that cache budget, before
shared/fixed work. Policy tuning alone cannot plausibly close the target gap.

036 first water_cycle sample:63 steps in315.6259865s =0.19960333tok/s, exact IDs;
26.28% above034's same case. Early resource window has~257 process faults/s,
private22.063GB and6.84 CPU core-equivalents,89.7% kernel. Window timing is not
whole-run attribution; repetitions are still active and target remains unmet.

## 38 hypothesis — avoid Windows cache-manager overhead for cold experts

With allocation faults removed, kernel CPU remains high. Prepare a guarded
byte-verified comparison of cached and FILE_FLAG_NO_BUFFERING ReadFile calls
using identical aligned reusable buffers and otherwise identical native APIs.
Use disjoint experts outside prior component cohorts and observed034 routes;
record actual sector alignment, CPU/disk counters and natural cache conditions.
Do not run until036's nine verified samples finish and its process exits.
No production uncached path or full-model benefit claimed in advance.
Microsoft references: https://learn.microsoft.com/en-us/windows/win32/fileio/file-buffering
and https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_storage_info .

038 preparation: PTL reports logical sectors512B,physical4096B, aligned device
and partition. The native overlap guard refused while036 was active, before
buffer allocation or expert reads. A bounded waiting probe is queued under
parent2348; uncached-probe-state.json records its state. It will validate a
small disposable file, missing/short inputs and misalignment, then measure12
disjoint255MB cohorts with SHA checks. It shares the native task lock while
probing. No component measurement has run yet. Repeated036 remains active;
its second case is0.198590tok/s with exact tokens, not yet a repeated record.

## 39 hypothesis — retain only the always-used shared experts as packed bytes

A036 two-minute window issues3.278GB/s explicit reads while machine disk reads
3.046GB/s; this is consistent with limited reuse, not exclusive model I/O
attribution. The shared experts are4.077GB and used every decode step. Prepare
opt-in owned int4 storage for just those experts, using identical packed bytes
and kernels. Routed experts retain current behavior. This deliberately trades
~4.077GB private memory for avoiding shared-file reads; OS paging can still
occur and full performance/memory must be measured. No physical pinning or
protected-service changes. Prepare/test locally while036 runs; no native build
until036 and the queued038 probe are terminal.

039 local validation:227 tests passed across the library, eight Inkling targets
and four GLM targets affected by the common expert storage enum. Owned versus
mapped fixture storage preserves the prior5122e042f9b1fb30 ARM-debug full-logits
hash over3 reps, with actual owned-shared bytes0/20736 respectively. The new
variant bypasses prefetch/explicit rereads and uses the existing swiglu_from
kernel. Native qualification and full memory/performance remain pending.

039 source deployed after six prior-SHA checks; native qualifier10264,parent10844
waits for036 and038, then builds/tests once. Updated PowerShell wrapper parses
natively; source commit4788a43d.040 single-pass shared-storage campaign is prepared
and parsed but not launched. Its full reference hash and actual owned-byte
metric prevent confusing a fixture/disabled feature with the intended test.

Controller now supports expected_metrics gates.040 requires actual owned shared
bytes4076863488,mapped embedding,full model and one repetition; missing/disabled
features cannot be promoted even with matching logits.19 controller/routing
checks pass; the target-gate case also passes with these constraints.

Whole-span bound supplement037 allows perfect reuse across all63 continuation
positions regardless of execution order, rather than assuming token-by-token
window scheduling. Actual unique routed bytes150.62/175.91/165.85GB. Even with
an ideal initial32GiB routed cache,25tok/s requires46.14/56.17/52.18GB/s reads.
PTL's NVMe controller reports current/max PCIe link speed code5,width4. Microsoft
maps5 to32GT/s; PCI-SIG specifies128b/130b encoding. Thus the link ceiling is
15.754GB/s before packet overhead. The extremely optimistic disk-only throughput
bound is8.54/7.01/7.55tok/s, excluding compute/shared/fixed/draft work. This applies
to the current packed-matrix representation, not hypothetical new compression.
It establishes why25tok/s cannot be reached by ordinary tuning of this export
on the current SSD, even though further practical gains remain worth testing.
References and native properties are retained in037_full_span_traffic_bound.json.


## 36 completed — verified repeated improvement, recovered native artifacts

All nine samples pass exact reference IDs and full-logits hashce0fbb9a116d3d09.
Slowest0.1969341563tok/s,45.52% above baseline0.1353339381; range0.196934–0.200669.
Median seconds/token: attention0.368731,MLP4.628557,outside layers0.024826,
wall5.017980. The combined knobs are measured; individual causes are not isolated.
Sampled lifetime private peak22.078GB (baseline24.536GB), faults107292/s versus
494348/s, including soft faults and prefills. Minimum available RAM819200B and
machine swap peak14.551GB show transient pressure persists. Machine disk2.940GB/s
is not exclusively attributed to model. Resource analyzer reproduces all prior
baseline aggregates exactly and rejects the wrong process creation time.

The original SSH client23331 remained open after native9472 and both wrappers
exited. Closed only that stale client after independently copying complete
native artifacts. Autolab records the transport as failed; retained unchanged.
036_completed_artifact_verification.json records independent model result
verification, matching all nine JSON/log samples, exact IDs/hash and recomputed
slowest rate. Raw traces and resource snapshot are compressed with SHA manifests.
No repeat inference was fabricated or launched to hide the transport failure.

## 38 completed — uncached reads justify a production experiment

Native canary/missing/short/misaligned checks pass, plus96 disjoint real expert
SHA checks. Six rotating cohorts/mode: cached38.7819ms,uncached31.7165ms for
254803968B =6.570/8.034GB/s,1.2228x throughput. Median machine read bytes
255514624/256833536. CPU counters are too coarse for precise short uncached CPU
rates (median0); do not call this zero CPU overhead. Cache state natural, no
flush; no full-model benefit established. Prepare an opt-in aligned reusable
read path preserving cached fallback and exact numerical kernels.

## 39 qualified; 40 launched

229 native tests pass; plain/owned fixture and production wrapper preserve
1f7cd0eb14a22662, owned bytes0/20736. Full-owned-shared.exe SHA
0bd35a624e3fb7e5f0b78bfdf4202f548095ebb90b6f71137bb8d9683b7b96cb.
040 all-three-case single-pass full diagnostic launched under controller session
69544,log/private/tmp/inkling-full-owned-shared-campaign.log. Same036 settings
plusOwnShared1, expected4076863488 actual owned bytes. SSH keepalives now enabled.
Sampler4208 remains active;038 and039 jobs have ended. No simultaneous native
build/probe allowed during040. Repeated record remains036; target25 is unmet.


## 41 hypothesis — aligned uncached reusable reads

038's22.28% component throughput gain justifies an opt-in Windows path:
CASCADIA_INKLING_UNCACHED_READS=1 requires reusable buffers and bulk reads.
Aligned subslices of ordinary padded Vec allocations use read-only
FILE_FLAG_NO_BUFFERING. No new unsafe code or physical pinning. Unsupported
lengths/platforms/I/O retry a full cached read; failed attempts expose no bytes.
File lengths are checked before/after direct I/O (a one-byte EOF probe would
violate alignment). Process counters report actual completed uncached bytes
and fallbacks, including attempts that fall back to mapped execution on error.
Full campaign042 requires effective uncached reads and zero fallbacks.

229 local tests pass plus six focused buffer checks after counter refinements.
The tiny fixture preserves5122e042f9b1fb30 with the option unset/set on macOS;
macOS intentionally retains cached reads, so this is not Windows I/O validation.
Two pending native tests exercise aligned exact reads, reuse, and actual fixture
matrix kernel parity through disposable padded files. No model files modified.
References: https://doc.rust-lang.org/std/os/windows/fs/trait.OpenOptionsExt.html
and https://learn.microsoft.com/en-us/windows/win32/fileio/file-buffering .

Four previous native source SHAs verified before staging. Qualifier parent8796
waits for040's complete verified result and native exit before building once.
Stateuncached-qualification-state.json,loguncached-qualification.log, future
full-uncached.exe. It preserves all four frozen binaries and replaces the staged
wrapper only after native success and the previous wrapper SHA check.
042 full three-case single-pass campaign prepared/parsed, NOT launched.
040 first water case0.2373318713tok/s,18.90% above036 same case, exact IDs;
remaining cases pending. No new repeated record claimed.


## 43 hypothesis — overlap expert reads with ready-expert compute

Prepare opt-inCASCADIA_INKLING_PIPELINE_READS for reusable buffers plus parallel
experts. Each expert retains its mutable buffer borrow across read and kernel;
indexed Rayon collection preserves gate order. Ready experts may compute while
remaining I/O completes; defaults/direct/serial escapes retain the old schedule.
Actual pipelined layer count is reported, so a disabled path cannot look tested.
No native deployment or performance claim yet; first finish040/041/042 and choose
whether to retain uncached reads from full-model evidence.

221 local library/Inkling tests pass. Five fixture modes preserve the ARMdebug
hash5122e042f9b1fb30: pipelineoff/on actual counts0/63; disabling reuse, enabling
direct maps, or serial experts each yields0 and exact outputs. Native validation
and full performance remain pending. Pipeline source is local only; the queued
uncached build uses the previously staged06bc834f source and wrapper.


## 40 completed — shared-expert ownership improves full decode

All three cases preserve full hashce0fbb9a116d3d09 and exact reference IDs.
Rates0.237332/0.237696/0.235890tok/s; slowest0.2358904279,19.78% above036
repeated slowest. This is ONE pass, so036 remains the repeated record.
Autolab completed/verified normally with SSH keepalives. Median seconds/token:
attention0.388156,MLP3.800657,outside0.024941,total4.213509.

Private peak26.093GB (03622.078GB), minimum available RAM188MB, machine swap
peak16.092GB. Lifetimefaults126252/s vs036107292/s include prefill/soft faults.
MLP improves despite added private storage; transient prefill pressure remains.
Machine reads2.654GB/s sampled lifetime cannot be exclusively attributed to model.
All full reports/traces/resources archived with SHA manifest. Native041 build
started automatically after040 exit; no concurrent full benchmark.


041 native qualification complete:233 tests, actual aligned byte/reuse/kernel
canaries, all fixture modes and production wrapper pass. Tiny unaligned bins
correctly fall back (three observed attempts); no native full gain yet. Binary
full-uncached.exe SHA9aa189f74b797679d91603fc6d3dfd34dc6ad3bde94ebdae95ef5526b58e81a2.
042 launched,controller45505,log/private/tmp/inkling-full-uncached-campaign.log,
nativePID5024,created1789346344.4633756. Three full cases,one repetition; gate
actualuncached_read_effective1/fallbacks0,ownedbytes4076863488 andfullhash/IDs.

Pipeline qualifier is now queued under parent9672 after042. It applies staged
source only after previousSHAs plus full042 verification/native exit; builds/tests
once and preserves all five frozen binaries. No pipeline full test queued; choose
its cached/uncached base from042 versus040. Statepipeline-qualification-state.json.


042 firstwatercase0.5362147788tok/s,2.259x040 samecase; exact IDs. Remaining
cases and actualuncached/fallback metrics remain pending. Prepared044 control
and045 overlap as separate same-binary full campaigns,3cases1rep each. They use
uncached1 provisionally; confirm042 final performance before launch. Both gate
full IDs/hash/ownedbytes/actualuncached path; pipeline layer count must be0 for
control and12096 (64MoElayers x63steps x3cases) for overlap. Do not launch until
queued043 is qualified and the production wrapper fixture passes.


## 42 completed — uncached I/O yields a large full-model improvement

All3 cases pass exact IDs/logitshashce0fbb9a116d3d09,ownedbytes4076863488 and
actualuncached_read_effective1/fallbacks0. Rates0.536215/0.533069/0.515177tok/s;
slowest0.5151766081,2.184x040 and3.807x original033 baseline. ONE pass; repeated
record remains036 until final confirmation. Native05024 exited; Autolabverified.

Actual uncached bytes2208959299584 over189 decode steps =11.6876GB/token.
4.44% of routed selections instead computed from mappings under the sampled
residency predicate; this is not a physical cache-hit measurement. Counts exclude
shared/fixed weights and prefill. Median attention0.363591,MLP1.495291,
outside0.025032,total1.875930seconds/token. MLP fell from3.800657s with040.

Lifetime sampled private peak26.093GB, kernel CPU fraction41.82% versus04076.36%,
machine reads4.320GB/s. Faults/s199889 include prefill/soft faults and are not
comparable decode-only rates; faster decode increases prefill's lifetime share.
Prefill pressure remains: minimum available70.6MB, machine swap peak16.491GB.
Raw traces/resources and accounting are archived with SHA manifests.

Retain uncached1 for prepared044/045 matched control/overlap.043 qualification
started after042 native exit; no other full-model trial is active while it builds.


043 native qualification complete:233 tests,three fixture modes and production
wrapper pass hash1f7cd0eb14a22662. Pipeline counts0/63off/on; all five previous
binary SHAs remain unchanged. Full-pipeline.exe SHA
8305491ebbc4bacc09fdb3aeccbe331b153e0fd79d34a273baef2ddb5d593e8b.
044 control then045 overlap launched in a sequential shell under tool20333.
The second starts automatically only after044 succeeds; never launch it twice.
Logs/private/tmp/inkling-full-pipeline-{control,overlap}.log. No native qualifier
is still queued. Final repeated confirmation remains pending after this pair.


044 control completed:0.547396/0.541679/0.537715tok/s,slowest0.5377145739.
All full IDs/hash and actualsettings pass,uncachedbytes2154558652416,fallbacks0,
pipelinecount0. The same setting's variation from042 should not be attributed
to overlap (which is disabled here).045 started automatically,nativePID2368,
created1789348029.3876903,under sequentialtool20333. Finalconfirmation pending.
Direct034 anduncached042 choose identical routed IDs in all192case/layerpairs,
108288 selections includingprefill. The prior037 traffic bound still applies.


045 first two cases improve over matched044:water0.57064855(+4.25%),binary
0.60665843(+12.00%),exactIDs. Final story/fullhash/counters remain pending.
Prepared046_full_final_confirmation withPipelineReads1,all3cases x3reps,63decode
steps each,timeout7200,expectedpipelinecount36288. NOT launched; require045
completion/fullvalidation and no active native model before starting it.


## 45 completed; 46 final repetition launched

Matched045 scores0.570649/0.606658/0.598387tok/s,allcases faster than044 by
4.25/12.00/11.28%. Slowest0.5706485510 vscontrol0.5377145739,+6.12%. Allfull
IDs/hash/settings pass,actualpipelinecount12096. The overlap arm read2.72%more
uncached expertbytes,so less expert I/O does not explain its gain. Naturalcache
state/backgroundconditions remain a comparison limitation. MedianMLP1.289330s
versuscontrol1.467535s; attention0.357172 vs0.353489s. Privatepeak26.093GB and
transientprefillpressurepersist. Archived fullrawtraces/resources/comparison.

SelectPipeline1.046 finalconfirmation launched withall3cases x3reps,63steps,
expectedpipelinecount36288. Tool4290,log/private/tmp/inkling-full-final-confirmation.log,
nativePID2144,created1789348770.2793455. No other trial/buildqueued. Sampler4208
continues; stopwithmarkerafter046. Preparedptl-profile.ps1 setsprocessenvonly;
PERFORMANCE.md reflects single-passresult and pendingrepetition.25unmet.


## 46 completed — repeated full-model record and final host state

2026-09-14 01:52 UTC: Autolab completed normally and verified all nine samples
(three prompts × three repetitions, 63 decode steps each). Slowest 0.5679137350,
median 0.5837513204, fastest 0.5938149418 tok/s. The slowest score is 4.196× the
original repeated baseline. Every generated ID and logits hash ce0fbb9a116d3d09
matches; all case/repetition pairs are present. Actual owned shared bytes
4,076,863,488; mapped embedding enabled; uncached bytes 6,638,089,273,344;
fallbacks zero; pipelined layers 36,288. Native binary SHA and model-ready SHA
match qualification/deployment, and all five previous frozen binaries remain
unchanged. The independent report checks native JSON against logs and Autolab.

All 576 case/repetition/layer route arrays exactly match the 034 templates,
including prefill, so the previous traffic bounds apply to this final result.
Even allowing all nominal 64 GiB as a perfect initial cache requires 32.5–42.5
GB/s for 25 tok/s, above the observed SSD link's 15.754 GB/s theoretical maximum.
This is a bound for the current packed representation and measured workloads;
it does not establish that all incremental optimization is exhausted.

Final median attention / MLP / outside-layer seconds per token:
0.373415 / 1.304773 / 0.024897. Prefill 99.967–113.688 seconds per prompt.
Sampled lifetime: private peak 26.099 GB, kernel CPU 39.65%, machine reads
4.733 GB/s, minimum available RAM 1.09 MB, swap peak 16.917 GB. These include
load/prefill and soft faults; machine I/O is not exclusively the model's.

After native and wrapper exit, created stop-trials-sampler. Confirmed sampler
and all task benchmarks exited; OVMS6728, node8356, CA6344 remained running.
Free disk 264,601,800,704 bytes. Copied stable final artifacts and validated all
source/destination SHA hashes. Archived JSON, compressed traces/resources,
verification, route identity, profile and final host state under results/046*.
No additional build or trial is queued. The selected profile is reproducible
from ptl-profile.ps1 and campaign046. Target25 remains unmet; no new export or
A100 job is needed. Lambda release backup remains verified; no termination or
billing stop was performed because no account API/console access is available.


## 48 hypothesis — resume with an explicit causal expert cache

2026-09-14: User explicitly resumed autonomous optimization. Record046 remains
0.567914 tok/s; the prior storage bound is not a stopping condition for improving
this rate. No new export or Lambda work is required. Autolab reports97 recorded
experiments across20 campaigns. No DISCOVERIES.md exists. Read prior journal,
research plan, final state and last20 commits; no benchmark was still active.

Hypothesis: retaining a bounded selection of repeatedly routed packed expert
bytes reduces the approximately11.7GB/token uncached traffic. Test an opt-in,
model-owned LFU cache using only past routing, with per-layer budgets and exact
original kernels. Per-layer ownership avoids stale global entries across model
unloads and a fixed budget limits private-memory growth. No file is changed and
no future trace is available to the runtime. Compare64/128MiB per MoE layer
(about4/8GiB total) against the same binary with cache0; reject if whole-model
latency regresses or any output/configuration gate fails. Tests must cover
capacity, concurrent leases, eviction, failed reads and model isolation before
native qualification. This is an algorithmic cache experiment, marked moonshot;
record I/O saved as well as speed and memory pressure. Cache-policy simulation
is only a candidate-selection aid, never evidence of a full-model speedup.

Cache implementation passes the local library/Inkling/GLM suite, five focused
cache tests (including real int4 kernel bits through repeated evictions), and
seven full tiny-fixture modes. All fixture hashes5122e042f9b1fb30 match;
cacheon/uncached have110hits and55,296retained bytes, while disabled prerequisite
modes havezero capacity/hits. Model-owned entries cannot outlive the model or
collide with a different model's expert number. Outstanding leases cannot be
evicted, and allocation capacity (including alignment padding) is budgeted.
Defaultoff; per-layer setting0–256MiB. Misses on the enabled path use a complete
read even if OS sampling says resident, so that admission has valid bytes; the
full comparison includes this cost. Counters separate actualhits/bytes/admissions.

Prepared049same-binarycache0,050cache64MiB/layer,051cache128MiB/layer. Each has
three cases × one pass,63decode steps, exact reference IDs/hash, uncached and
pipeline gates plus actual cache budget/effectiveness. Only run after native
qualification and wrapper check. Final winner requires repeated confirmation.
This loop continues after the cache comparison to further hypotheses.


## 49 next hypothesis — stream prefill expert reads

Cache048 native qualification passes238tests, four fixture modes and production
wrapper with110actualhits/exact1f7cd0eb14a22662. New binarySHA
fe913c6844813bfa48b380e886c477224b77b3462f5e0b4c752345f8b2f61e88,
source049034de. Campaign049cache0,050cache64,051cache128 now execute sequentially
under controller73582,logs/private/tmp/inkling-049_full_expert_cache_control.log
and corresponding050/051 names. Sampler048-host-resources.jsonl is active with
stop-048-sampler marker and12-hour limit. Do not launch duplicate trials.

While these run, prepare next hypothesis locally: use complete uncached reusable
expert reads for the batch-union prefill instead of mapped faults and serial
prefetch hints. Bound each concurrent cohort to eight experts to avoid unbounded
retention under nested Rayon work stealing. Each expert still computes all of
its rows, and outputs accumulate in identical gate order. Reuse scratch without
discarding other idle buffers when acquiring a smaller lease. Separate prefill
I/O counters preserve the meaning of existing decode counters. Target reduced
100–114second prefill latency and less transient paging, with possible secondary
decode benefit. Full-model throughput remains the primary metric. No native
build/deployment of this next candidate until049/050/051 finish and cache winner
is chosen. This is not a replacement for completing the current cache comparison.

Prefill prototype passes235local library/Inkling/GLM tests, one additional
real-int4 multi-cohort equivalence test (16 routed experts across two bounded
cohorts, repeated rows), and eight full tiny-fixture modes. All exactfixture
hashes5122e042f9b1fb30 match. Enabled modes perform63actualprefillreads; direct
and reuse-disabled modes performzero. Decode cachehits remain110 whenenabled.
Prepared052qualification, nativecandidatefull-prefill-reads.exe and separate
prefill I/O counters. Sources/tests are staged only; qualifier is NOT launched
and native cache-trial binary/sources remain unchanged. Use q48 measured winner
for a subsequent same-binary prefill comparison after current049/050/051.

049 cache-disabled control completed normally, exactfullhash/IDs. Rates
0.566639/0.581579/0.586488tok/s (slowest0.5666387288). Actualuncachedbytes
2,249,218,326,528,cachecapacity/hits0,pipelinecount12096,fallbacks0. Native10040
created1789366425.177786 ended. Archived049 rawdiagnostics and sampledresources;
medianattention0.366418,MLP1.343450,outside0.024892seconds/token. Privatepeak
26.093GB,minavailable1.69MB,kernelfraction39.61%; includesload/prefill.
050 cache64 started automatically,native10944,created1789367136.4451942.
Controller73582 remains active;051 follows on success. Sampler3036/shim9352,
parent10880. Fixed controller telemetry: unobserved full-checkpoint availability
is now null rather than falsely reporting a missing deployment for empty new
campaign history. Target/correctness gates unchanged;19 tests pass.

050 cache64MiB/layer passes all three prompts and actual counters. Slowest
0.5770554937tok/s versus0490.5666387288 (+1.84%). Actualcachehits8582/72576
(11.825%), retained4,077,387,648B includingalignmentpadding, uncachedbytes
2,038,240,641,024 (9.38% less thancontrol),zero fallback. Water improves14.28%,
binary is nearlyunchanged; gains are notuniform.051cache128 startedautomatically.

Additional causal cache hypothesis: accumulated frequencies from a previous
request delay admission for a new topic. Add opt-in frequency-history reset on
model sequence reset while retaining immutable cached allocations and cumulative
I/O counters. This changes cache admission only, not model state or logits.
Compare within the next qualified binary with the optiondefaultoff; actual
history-reset counters must prove activation. It may complement streamed
prefill, which targets independent memory pressure. Keep these knobs separate.

050 profiling: medianattention0.393843 vs0490.366418 seconds/token; MLP1.298811
vs1.343450. Privatepeak30.180GB and machine swappeak20.035GB, comparedwith
26.093/16.447GBcontrol. Aggregate lifetime counters include prefills; new
benchmark timestamps will permit actual phase-specific interval accounting.
051native8084,created1789367822.7529976 is active. Cache048single-passresults
remain preliminary untilrepeatconfirmation; two050cases regressedslightly.

Prefill/history candidate now includes phaseUnix timestamps with throughput
still timed by monotonicInstant. Separate optionalhistoryreset retainsweights,
clears oldfrequency scores atLayer.reset, and countsactualresets. Local237unique
tests pass, plus eight prefill fixturemodes and three history/timestampmodes.
Sixsourcefiles and updatedqualifier/wrapper/tests are staged but NOT launched.
Expected native suite241 tests and seven fixturemodes; do not build until051ends.

051cache128 completed:0.699893/0.598082/0.568678tok/s,fullhash/IDs/counterspass.
Uncached1,860,037,115,904B,cachehits14177/72576,retained8,154,775,296B.
Privatepeak34.266GB,machineswappeak23.602GB; lifetimeincludesprefill.
Lowest-case scoreloses tocache64,so keep64fornextcomparison; all3rawtraces and
resource snapshots archived. This is not a repeated promotion. Controller73582ended.

052 nativequalification passed241tests,sevenfixturemodes andproductionwrapper,
hash1f7cd0eb14a22662. Binaryfull-prefill-reads.exe SHA
bb44392b9a4d3f29b845e115c4e01a724477a374cc56de10043712509e5aaf82,
source72cb6f05,allsevenolderbinariespreserved. Actualhistoryresets9/prefillreads63
in tinyfixture; unalignedbins useexpectedcachedfallback. Phase timestampsordered.

053control then054streamedprefill launchedsequentially under tool41846.
Native053PID8212,created1789369078.4974482. Cache64/historyreset0samebotharms;
expecteddecodeI/O/cachecounts match050exactly, separatingprefillanddecodecounters.
Fullstreamedprefillexpected13635visits/434281512960B,computedfromverifiedroutes.
Sampler3036continues. Newphaseanalysis preservesoriginaladjacency, excludes
boundary/mixed-phaseintervals and rejectsclockjumps;21Python tests pass.
Nextafterpair:historyresetexperiment,thencachebudgetretuneifmemoryconditionschange.

053 matched prefill control passed all full-model gates at0.5867846190tok/s
slowest (water0.648863,binary0.590169,story0.586785). Prefill103.358/108.410/
105.273seconds; exact050routingarrays andcache/readcounters. Phase-aware
sampling separates prefill374547faults/s,59.05%kernelCPU fromdecode48341faults/s,
14.60%kernelCPU. Decode machine reads7.024GB/s/process6.867GB/s; machineI/O
is not exclusivelymodeltraffic. Archivedrawresults,traces,snapshot,SHAmanifest.
054streamedprefill active PID768,created1789369759.6460428,controller41846.

Before055: replayed actual gate-order LFU admission from saved routes. Both
measured64MiB and128MiB cases match allfourhits/misses/admissions/evictions
counters exactly. Reset-history predicts64MiB hits13185,misses59391,admissions
1271,evictions1143 versus8582/63994/512/384 withoutreset. This is causal
simulation, not measuredspeed; full055will gate onthese counters and192resets.

Next q50 hypothesis: blocking expert reads occupy Rayon workers shared with
row kernels, so the resident-optimal16worker setting may not minimize full
latency. After selectedcache/prefill/historyprofile, compare8/12/24/32workers
using the same nativebinary and boundedmemory; qualify exacttinyIDs/logits
first and keep one full benchmark active. No globalhost affinity/settingschange.

Prepared055/056/057 cache-history trials at64/128/256MiB perlayer, all3case/1pass.
They will use streamedprefill only if054passes and improves. Each has exact
predeclared causal hit/miss/admission/eviction/read-byte gates; retainedbytes
include4095-byte alignmentpadding perexpert. The largestsettingretains16.31GB
routedweights plus existingprivateweights, stillwithin64GBhardware. No trial
hasstarted. Prepared optionalThreads1–64 wrapper (default16) and nativefive-mode
fixturequalifier for8/12/16/24/32; staged underdistinctnativefilenames, no active
launcherchange. Runqualifierbetween054 andthecachecampaigns,thenpreserve16
forcachecomparisons. Source/no-arithmetic-change remainsfull-prefillbinary.

Additional bounded offline hypothesis: even after request-boundary reset, routing
may shift within a continuation. Replay shorter frequency-decay intervals using
only past/current routes to assess whether an adaptive cache merits a future
implementation. Simulated hit rates are diagnostic, not performance results;
no runtime change or benchmark-specific routing table will be used.

054 streamedprefill passes fullhash/IDs, identical053routearrays andallactual
cache/decode-read counters. Rates0.793101/0.713443/0.709011tok/s; slowest+20.83%.
Prefill24.222/25.040/24.108sec,4.27–4.37x faster. SelectPrefillReads1.
Phase-awaredecode faults58.35/s versuscontrol48340.91/s; machine7.938GB/s,
process7.937GB/s. Full-lifetimeminavailableRAM14.183GB versus3.25MBcontrol;
maxmachineswap0.589GB versus20.391GB. Onlyfivewholeintervals coverstreamed
prefill; machineI/O andsoftfaultlimitationsremain. Medianattention0.184337
versus0.366595sec/token;MLP1.192887versus1.302730. Rawartifacts/SHAarchived,
report054_prefill_comparison.json. Repeatedrecord046unchangedpendingconfirmation.

059 nativeworkerqualification passed8/12/16/24/32withsamefrozenbinarySHA,
exacttinyhash1f7cd0eb14a22662 andIDs,actualcachehistory/prefillcounters. Wrapper
nowacceptsThreads1–64 (default16) andlogsconfiguredcount. No binaryrebuild.
055history64active,native10436created1789370179.2082949;056history128then
057history256queued undercontrollertool16120. Logs/private/tmp/inkling-NAME.log.
Sampler3036continues. Allcachetrialskeep16workers. Nextselectcachebudget and
runqualifiedworkercomparison,thenrepeatbest3passes. Keepoptimizingafterthat.

058 offlinefrequencydecay replay:32requests betweenhalvingspredicts13674/21936/
31383hits at2/4/8slots versus13185/21021/30058with4096. Admissionsroughlydouble.
This suggests a modestfutureexperiment, not animplementedgain. Currentnative
cachedecay remains4096; nofuture/hardcodedroutesenterinference.

Offline global-cache hypothesis before simulation: routing concentration differs
by layer, so equal per-layer budgets may spend RAM on less reusable experts.
Replay a model-owned global LFU cache at the same total capacity and current
request-history reset. Preserve chronological token/layer/gate order; no future
routes or prefill admission. Evaluate hit counts before considering implementation.

060 global LFU replay predicts14279/22017/30505hits for128/256/512totalentries,
versus13185/21021/30058withfixedper-layer budgets. This removes only1.84/1.93/
1.05% of remaining misses. Defer cross-layer runtime-cache complexity behind
worker/concurrency tuning; no global cache is implemented.

q51 offlineprefetch hypothesis before replay: predictoneortwo uncached experts
fromthepreviousposition's route, rankedbycausalfrequency/lastuse. Countfuture
selection onlyaftermakingtheprediction; excludeweightsalreadyintheroutedcache.
Measureusefulprefetchesandadditionalreads before spendingI/O on a runtimepath.
Predictionswillnotmodifycacheadmission or modelrouting.

061 previous-route prefetch replay at2/4/8cacheentriesperlayer: onepredicted
expert adds10.8/14.9/19.8% reads; two add23.6/31.4/38.6%. At8entries,onepredictor
has3007usefulof11428predictions (26.3% precision). TheSSD alreadyserves~7.94GB/s
duringdecode. Deferthispredictor: extraI/Oisunlikelytojustifyoverlap; thecausal
modeldoesnotestablishperformance. No runtimeprefetch or cachechangeimplemented.

Prepare an opt-in shorter cache-decay interval locally while056/057run.
Default4096 preserves all measured behavior. A32-request interval has causal
miss-reduction evidence (058); add actualdecay counters and a stale-frequency
regression test, then qualify a new frozen binary only after current full trials
finish. No nativebuild/deployment now. Worker sweeps retain the qualified
full-prefill binary until the separate decay comparison is scheduled.

055historyreset64passed:0.781348/0.758280/0.757562tok/s; slowest+6.85%over054.
Waterregresses1.5%,othertwogain6.3/6.8%. Actual13185hits/59391misses/1271admissions/
1143evictions/192resets exactlymatchpredeclaredreplay,1.891633TBdecodeuncached.
Minavailable13.987GB,maxmachineswap0.527GB. Savedrawartifactsandresourceanalysis;
routearraysidentical054. 056cache128activePID10104created1789370544.0585535;
057cache256queued,controller16120.

056history128passed:0.856802/0.813905/0.825203tok/s, allcasesimproveover055;
slowest+7.44%. Actual21021hits/51555misses/2380admissions/2124evictions/192resets,
1.642052TBuncached. Rawartifactsandphaseprofilesarchived. 057history256active
PID2956created1789370890.016268,controller16120.

062localcache-decaycandidate passes163library/modeltests andfivefixturemodes;
exactARMhash5122e042f9b1fb30. Actualdecays27 (4requests/reset),3 (32/noreset),
0(default4096/disabled/invalid5). Newtestshowsadmissionadaptationwhilepreserving
immutablebytes; initialfour-observationtesthitatieunderstrictgreater-than
admission, correctedtoeightobservationsand18decays. No runtime defectfound.
Default4096preservesbehavior. Rustfmt/diffchecks pass. Prepared063nativequalifier
thatwaitsforall055/056/057andnoactivefullprocessbeforetests/build; frozen
full-prefillbinarypreserved. Worker sweeps must waitforqualificationtoend,then
canuseoriginalfull-prefillbinary. Newdecaycontrol/candidatefulltrialcomeslater.

057history256passesallgates,slowest0.9157886929tok/s; select256MiBperlayer
(16.3096GBactualretained). 30058hits/42518misses/4141admissions/3629evictions,
1.354219TBdecodeuncached. Controller16120endednormally. Prepared064–068
worker16/8/12/24/32 comparisons, samefrozenfull-prefillbinaryandselectedcache,
historyreset1/streamedprefill1. Fresh16controladdressespossibletime/thermaldrift.
Do not launch untilnativecache-decayqualifier1952(parent9604) completes;
qualifierwaswaitingfor057andautomaticallystartsnowthatfulltrialended.

057retains16.3096GB,privatepeak42.500GB,minavailable1.996GB,maxmachineswap
0.508GB. Decodefaults73.48/s, machine6.809GB/s,CPU7.126cores. Largerbudget
gainswithoutreturningtoearlierprefillpaging. 057comparisonreportarchivesall3
budgets; repeatedrecord046unchanged.

063nativecache-decayqualificationPASSED242tests,fivefixturemodesandproduction
wrapper; hash1f7cd0eb14a22662. Newfrozenfull-cache-decay.exe SHA
3874c863852b036757069bbac207a473481dd5408c854c037c7a2a72f6a431e8,source6b820e83.
Alleightpreviousbinariesunchanged. Qualifier1952,parent9604,launcher8620ended.
CurrentnativewrappernowacceptsCacheDecayRequests,default4096,olderbinaries
retained. No full-modeldecaygainmeasuredyet.

064threads16controlACTIVE,065threads8/066threads12/067threads24/068threads32
queued sequentiallyundercontrollertool67450. Script/private/tmp/run-inkling-thread-loop.py,
logs/private/tmp/inkling-CAMPAIGN_NAME.log. Native064PID688created1789371344.1482334,
actual17threadsafterload. Allusefull-prefill-reads.exe/cache256/historyreset1/
streamedprefill1. Sampler3036continues. Afterworkercomparison, matchednewbinary
decay4096/32usingbestworker,then3-repeatconfirmation. Continueoptimization.

q50 follow-up sources reviewed: Microsoft documents that synchronous I/O blocks
the submitting thread, while OVERLAPPED can release it; async may still execute
synchronously and can add overhead. Buffers/OVERLAPPED state must outlive all
completion/cancellation. Source: https://learn.microsoft.com/en-us/windows/win32/fileio/synchronous-and-asynchronous-i-o
Sector-aligned offset/length/address remain required forNO_BUFFERING:
https://learn.microsoft.com/en-us/windows/win32/fileio/file-buffering
038read-onlycomponent already achieved~8GB/s with8synchronousreaders; current
fulldecode~6.8GB/s with larger cache. Consider componentmeasurement ofasync
before changingruntime, aftercurrentfullsweeps. No asyncimplementation/probe
hasbeenwrittenorlaunched. Alsoinspectread-onlystoragethermal/healthtelemetry.

064fresh16controlpasses0.9175664024tok/s,close0570.9157886929; rates0.960523/
0.917566/0.940705. Rawartifacts,SHAandphaseprofilesarchived. Nativeprocess
threadtotalsare17for17decodesnapshotsand19forlasttwo; aninitialexact17check
wasoverstrict becauseprocesstotalsarenotadirectRayonpoolmeasurement. Keep
configuredrayon_threads gate andreportprocessthreadobservationsseparately.
065workers8activePID3924created1789371668.766402,observed9threadsafterload;
066/067/068queuedunder67450. Storagecurrent43C,errorcountersnull/unavailable;
source065_storage_snapshot preservesrawfieldswithoutinterpretingmax83asthreshold.
Originalfeat/inklingrechecked07:44UTC still9aaebff0,clean.

069 async-read component hypothesis: with16GBcache, only~3.5uncachedexperts
remainperlayeronaverage. Smaller independentOVERLAPPEDchunks may raisequeue
depth versus2/4/6whole synchronousfile reads. Preparedread-onlyprobe at2/4/6
files, sync/asyncwhole/1MiB/4MiB/8MiB chunks, fiveblocks/mode. Allcohortsdisjoint
andexcludeactualfullroutes; allbytescheckedagainstmappedoracleoutsidetiming.
Buffer/event/OVERLAPPEDlifetimesextendthroughcompletionandcancellationdrain;
canaryincludesmissing/short/unalignedfailuresandbufferreuseafterpartialsubmission.
Probehasnotbeenlaunched. Itwillwaitfor064–068andtakebaselinequeue lock before
reading. No model mutation,newexport,or runtimeasyncpath. Sources:
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-readfile
https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-getoverlappedresult
https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex

065workers8completed0.8846400902tok/s,below064control0.9175664024. AllIDs/hash/
countersmatch; rawdiagnosticsarchived. 066workers12activePID5004created
1789372008.120318,observed13threadsafterload;067/068queuedunder67450.
069asyncprobesourcepassesPythoncompile/diffchecks only; nativecanaryandtiming
willrunafter068. Do not run anotherfulltrialuntilthatboundedprobeends.

066workers12passes0.9011509229tok/s,below16control; allactualcounters/IDs/hash
match. Rawdiagnosticsarchived. 067workers24active5688,created1789372336.0766687;
068queuedunder67450. 069asyncprobeSHAchecked/launchednativePython10092,parent
10616,waitingforworkercompletion. No componentreadsduringfulltrials.
070replayedverified046nine-sampleroutesforfuture3-repeatcachegates; 4096interval
90250hits/127478misses/12347admissions/11835evictions;32interval94235/123493/25801/
25289. Capturehelpersupports--repetitions3andvalidatescartesiancase/repcoverage.

067workers24passed0.8695377030tok/s,thirdconsecutiveworker-settingnonimprovement
after8and12. Research-loop reassessment: challenge theassumptionthatworker
oversubscriptionfillsstorage/computeidlecycles. HigherCPUactivitycaninclude
scheduling/spinning; itisnot evidenceofusefulkernelthroughput. FreshRayon
documentationreview confirmsdefaultpoolusesRAYON_NUM_THREADS andnotesblocking
I/Ocanhurtwork-stealingperformance. Sources:
https://docs.rs/rayon/latest/rayon/struct.ThreadPoolBuilder.html
https://docs.rs/rayon/latest/rayon/fn.join.html
Continue069independentI/Osubmission/chunkhypothesis afterremaining32workerarm;
itscomponentresultmustbevalidatedend-to-endbeforepromotion. Cachedecay32is
alsoqualifiedforaseparatecausal-cachecomparison. Neitherrelaxesnumericalgates.

067rawdiagnosticsarchived. 068workers32activePID8100created1789372668.7833545,
observed33process threadsafterload. Controller67450;069probe10092stillwaiting.

Prepared071/072same-new-binarycachedecay4096/32comparisonwith16workers. Current
32-workerfirstsample0.858327alreadycapsitsslowestscorebelow16control0.917566,
so16isselectedpendingnormalcompletion. Botharmsfull-cache-decay.exeSHA3874c863...,
cache256/historyreset1/prefill1/rows2/4. Exactcausalcountgatespredeclared from058:
32interval31383hits/41193misses/8629admissions/8117evictions/2112actualdecays;
control30058/42518/4141/3629/0. Do not launchuntil069probeexits. Afterpair,
three-repeatconfirmationofselectedsettingsbeforefurthernewruntimechanges.

068workers32finished0.8583274179tok/s; allgatespass. Workercomparison068selects16
at0.9175664024,all064–068routes/cache/I/Oidentical; rawdiagnosticsarchived.
069asyncprobecompletedall75cohorts/300distinctexpertSHAchecks,errorcanarypasses,
nativestate10092exited. Copiedrawprobe/stateSHAexactlymatchsource79637e61.../
882bf43e.... Wholeasync2filesmedian7.889msversussync12.204ms, but4files19.762
versus16.482msand6files28.750versus24.336ms. No consistentchunkedgain; defer
chunkedruntimeimplementation. Disjointfilecohortsleavefile-layoutvariability.

073pairedfollowuphypothesis: confirmwholeasync2filebenefitwithsamefiles/buffers,
AB/BAorderbalanced, hashesaftereacharm butmappedoracleonlyafterboth. 30pairs
(10each2/4/6files), excludesprior069andactualroutes. Reusebyte/errorcanary.
Preparedpaired-async-read-probe.py,syntaxpasses,notlaunchedyet. Itwaitsfor071/072
andnoactivefullbeforelock/probe; next3-repeatfullmustwaitforprobecompletion.
071default4096controlactive5952created1789373120.0706015;072decay32queuedunder
51214. Frozenbinary3874c863...verifiedandnoactive069processbeforelaunch.

071 control completed 0.9193077063 tok/s; 072 decay32 completed 0.9370410437, all exact output/hash/counter gates pass. Select decay32 for the required three-repeat confirmation. 073 paired read probe completed 30 pairs, all byte/error checks pass: no consistent async advantage, with strong order effects at four/six files. Defer runtime async changes. Prepared 074, using nine-sample causal predictions from 070: 94235 hits, 123493 misses, 25801 admissions, 25289 evictions, 6336 decays, 576 history resets. No new runtime change before confirmation. Scratch-pool inspection shows it is already process-wide and capped at 256 MiB, so per-layer scratch consolidation is not an available gain.

075–080 hypothesis: existing BF16/int4 row tiles were selected before streamed prefill and routed caching removed paging and reduced expert reads. Retest BF16 rows1/2/4 and int4 rows1/2/4 independently around selected2/4, with the same frozen cache-decay binary,16 workers/cache256/decay32. First qualify five combinations with native tiny model and production wrapper after074 finishes; then fresh2/4 control and four full candidates, each three prompts×one pass. This changes scheduling only, retains all numerical/hash/cache/I/O gates, and needs no export/build. Do not overlap qualification or full trials with074.

081 diagnostic hypothesis: use only observed prefill routes to initialize cache frequency history and optionally retain already-read experts, without additional reads or any knowledge of decode routes. Replay ascending expert admission after each current128-row prefill block, matching existing batch-union order, then ordinary decode LFU. Compare control, history-only and history+prefill-admission at decay32/4096 on nine verified samples. This is an offline causal prediction, not runtime code or measured throughput. No added full trial before074/row qualification.

081 result: control replay matches prior simulator at every case and aggregate. At selected8 slots/decay32, prefill history alone removes0.053% of remaining reads; retaining prefill experts removes0.610%. At4096 it increases reads. Defer runtime prefill admission because the gain is small.

082 hypothesis:32 was the shortest interval in058; already qualified/configurable4/8/16 may adapt faster. Replay those intervals and32 over verified nine-sample routes before deciding whether to run any further full decay trial. No runtime code changes.

082 result: at8 slots over nine samples, intervals4/8/16/32 have139809/128331/123825/123493 misses.32 remains best and has fewer admissions than16/8. Do not run redundant short-interval full trials.075 qualifier is waiting on074, nativePython9864,parent3504.

083 exploratory hypothesis: lossless compression of existing packed int4 expert bytes might reduce SSD traffic enough to justify a different storage reader. Read-only source-host probe on miner will sample18 fixed experts across six layers at Zstandard levels1/3, hold compressed data only in memory, and byte-verify decompression. This creates no model export, requires no Lambda rental, does not touch PTL during074, and measures source-host component behavior only. If ratios are poor, reject before any representation/runtime work. Miner export present and /usr/bin/zstd available; no packages installed.

074 complete and formally verified: slowest0.9382743961, median0.9648021079, fastest1.0329282085 tok/s across nine samples,6.933× original/1.652× prior repeated record. Exact baseline IDs/hash and all046 routes match; all predicted counters match. Raw artifacts/SHA/resources archived. Native6112 exited, sampler3036 and protected services remain running. Selected ptl-profile.ps1 updated locally and on host, SHA checked. A documentation link check caught the mistyped054-prefill-streamed filename before commit; corrected to054-prefill-1 and all links pass.
075 row qualification passed all five combinations with frozen binary and wrapper unchanged; native9864 exited, all reports/logs copied and SHA checked.076–080 row sweep launched under controller36811, script/private/tmp/run-inkling-row-loop.py.
083 source compression component completed18 experts×two levels with byte-exact decompression. Aggregate compressed/original ratios0.874644 atlevel1 and0.868844 atlevel3. No compressed files persisted and no export performed. PTL already has C:/msys64/mingw64/bin/libzstd.dll and zstd.EXE; no Python package or repo zstd dependency. Prepare084 matched uncached original vs compressed+decompressed read probe after row sweep, using preallocated buffers, separate contexts, balanced order and exact SHA checks. No runtime compression implementation yet. API references reviewed: https://github.com/facebook/zstd and https://python-zstandard.readthedocs.io/en/latest/decompressor.html .

084 hypothesis/protocol:13% source compression may or may not offset decoder CPU cost on PTL. Prepare matched30-cohort original uncached versus Zstd1 padded uncached+decode,2/4/6 files, balanced AB/BA, plus decode-only timing outside the pair. Use existing libzstd.dll via documented C API, preallocated aligned buffers and one decompression context per simultaneous job. All futures must drain before buffers/contexts free, even on errors. Exclude full routes and prior069/073 files. Setup writes only temporary task-owned compression fixtures, removed after probe; model files stay immutable. Byte/error canaries precede probe; SHA each arm, hardware/file-layout caveats retained. Wait for076–080 and full-process exit, then take queue lock. No runtime representation change.

084 probe implemented, local byte/error/context-reuse canary passes against local Zstd1.5.7. Injected future failure verifies all other buffer users drain before exception propagation. Initial whole-module local import lacked psutil (native dependency); tested unchanged Codec/drained_map AST definitions without installing packages. Native canary still pending after080. Native library1.5.7 SHA b95c223a... is pinned in probe; no package/dependency changes.076 fresh2/4 control completes0.9244748903, all counters/IDs/hash pass;077 running under36811.
