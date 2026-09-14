# Inkling / Panther Lake Autolab restart handoff

Updated 2026-09-14 10:33 UTC. Work is ACTIVE. User requested autonomous optimization toward
25 tok/s. Do not stop after a finite campaign. The target remains unmet.

## Latest active state (2026-09-14 10:44 UTC)

105 completed and all raw artifacts/SHA/counters/routes verified. First uncached
prediction:95.229% precision,28.836% miss coverage,1.4446% extra reads
(11338 useful,568 unused,11906 scheduled).105_pre_attention_prediction.json.
No prefetch occurred; diagnostic score.947160 is not a promoted record.

106 held-out strict reference finished generation; capture4863 is RUNNING: native596 created1789382341.9607809,
Python3092, launcher5324, detached parent10768. Native state
heldout-reference-state.json preserves identities. Outputs106-heldout-control.*;
128generated tokens on three frozen unseen prompts. Wait for completion, review
106-heldout-reference.json text, build107 recent-policy prediction campaign
using reference IDs/hash and causal cache counters. Initial106 lacks an oracle
and is not record eligible. Do not use normal capture helper blindly: it assumes
original three case names,64tokens,ce0fbb9a116d3d09; prepare scoped106 capture.

108 prefetch implementation is LOCAL ONLY; native sources/binaries stay
unchanged while106/107 run. New predicted_read.rs: bounded channel, one background
reader, one predicted uncached expert per layer, actual-ID-only consumption,
normal fallback, unused reads drained, explicit counters. Cache query is read-only;
actual route/math/admission order unchanged. Layer starts I/O before attention;
MoE consumes in its parallel read/compute branch.All248 local tests/13suites and example build pass. Four tiny modes preserve
exact outputs/routes/cache counters; enabled mode13reads/11useful/2unused, all
failures0. Native104 replay predicts the same counts. Still needs native252
tests and wrapper qualification,
then full110/111 A/B and confirmation if it wins. Do not claim speedup from105.
One-prediction runtime choice frozen before observing held-out routes.

Commit/push105 artifacts and108 implementation checkpoint now; run git log -1
for latest source. Native sources remain32e2de69 until109 qualifies later.
Update this top section on progress; older active descriptions below are historical.

## Current record

Confirmed102: **0.9654120906 tok/s**, slowest of nine samples; median0.9916481036,
fastest1.0604665236. This is7.1336× original and2.8923% above074. All nine samples
improved and all output IDs/full-logits hashes/routes/counters match. See
102_final_verification.json and102_repeated_recency_comparison.json.

Selected profile:16workers, all16CPUs, BF16rows2/int4rows4, cache256MiB per MoE
layer, historyreset1, decay32, **recent ties1**, streamed prefill and prior I/O
flags. Full CPU backend; Arc unused. No new export or Lambda work needed.
Frozen full-cache-recency.exe source849a08bd, SHA
 a23289477c2d5ade1e838ccf92d27ec8b5d31b1cebc4d79bc7d74ec85d1daa40.
098 qualification passed245 native tests and five tiny modes.

102 native8204(created1789380877.6939435) and controller94756 exited normally.
Raw outputs102-cache-recency-confirmation.* are captured with SHA manifests.
Actual reads3.754TB (4.549% less), hits99853/misses117875/admit80366/evict79854/
recent_tie_admissions60045. MinavailableRAM1.70GB, peakprivate42.51GB.
Earlier101 first-water second-token stall remains included in101 score;
it did not recur in102. No token or sample was discarded. Target25 is unmet.

## Active105 full-model prediction diagnostic

**105_full_pre_attention_prediction_diagnostic RUNNING**, local controller34745.
Native **PID9432**, created**1789381862.621628**, full-route-prediction.exe.
Local log/private/tmp/inkling-105_full_pre_attention_prediction_diagnostic.log.
Native outputs105-route-prediction.json/.log/-routes.json/-layers.json plus
105-route-prediction-predicted.json. Three prompts × one repetition, same
selected recent-tie profile, full exact output and actual counter gates.
No expert prefetch or changed actual routing; explicit diagnostic_only and
promotion_allowed=false prevent it from claiming a performance record.

104 qualified247 native tests/13suites and four tiny modes. All actual routes,
cache counters and native fixture hash1f7cd0eb14a22662 matched. Python2468 exited;
all10 older frozen binaries unchanged.104_artifact_verification.json holds SHA
archive and source32e2de69. New prediction binary SHA
89c0f361ac53bbae6af52979d889216138800296c99699976dbeb1732da93984.
Native/local production wrapper SHA
b0af52ea911f1a46ffc14f2a0f3588689443987a17db8aa1d60a0cea84d0934c.

After105 exit, capture with helper using9432/1789381862.621628 and default1rep.
Separately SHA-copy105-route-prediction-predicted.json, then run
analyze-route-prediction.py --trace ACTUAL --predictions PREDICTED
--benchmark RAW --recent-ties1 --out FRESH_REPORT. Review precision and extra
reads before implementing prefetch. Full-model prediction accuracy is unknown.

## Prepared106/107 unseen-prompt validation

heldout-prompts.json freezes three new tasks and128 generated tokens before
viewing their routes: worked algebra, JSON inventory, engineering dialogue.
record-heldout-reference.py records a strict-cache reference using the qualified
frozen recency binary; it requires105 complete/no active full processes and
owns the native queue lock. **Staged, not launched.** See106_heldout_staging.json
for SHA state. Launch only after105 capture/review, detached Win32_Process.Create.
It uses transformer tokenizer already on PTL; no export or build.

Native stateheldout-reference-state.json captures launcher/native PID+creation.
Outputs106-heldout-control.* plus106-heldout-reference.json and
heldout-cases.json/heldout-cases.reference.json. Initial reference has no supplied
oracle and cannot establish a record. Review text and use its IDs/hash to prepare
107 recent-policy prediction campaign, with exact causal cache counter predictions.
No107 campaign yet. These new prompts stay separate from the established score.

## Completed evidence

076–080 row sweep complete:2/4=.924475,1/4=.927358,4/4=.931144,
2/1=.929776,2/2=.935296. Last improves everyprompt0.75–1.17% vsfreshcontrol,
but094/095 did not reproduce the gain.080_row_comparison.json. Confirmed profile
remains2/4/.938274. All raw artifacts/SHA/route/counter comparisons archived.
079 initial SSH banner failure happened before launch; original failed history
retained.079b retried after proving no files/process and supplied native079data.
Controllers36811(failedtransport) and66059(resumednormal) exited.

084 Zstd component rejected: all30matched pairs lost.2/4/6 original reads
11.310/19.371/25.215ms versuscompressed+decode40.443/47.113/48.949ms.
Decode-only26.5–26.9ms. All120expert SHA/error canaries pass, temporary3.8GBscale
fixtures removed. Native3204,parent10144 exited. No runtime compression code.
083 source18experts had compressed/original ratios.874644/.868844 atlevels1/3;
source timing was not PTL speed. No new export or rental performed.

086 metadata read-only:36originalfiles, physicalrun counts4for2files,5for32,
6for2; cluster4096B. Native3604,parent1164 exited. No filedata/allocationchange.
084/086/088 copied in SHA-verified native084-086-088-artifacts.zip;
local/private/tmp/inkling-084-086-088-artifacts.zip,088_bundle_verification.json.

087 topology: class1CPU0–3,class0CPU4–15. CPU0–11 shareLLCindex0;
CPU12–15 shareindex12. All16 materially active in saved074 decode. Utilization
is machine-wide; do not infer individual model usage or name core types solely
from EfficiencyClass.087_cpu_topology.json/087_decode_cpu_usage.json.
085 joined36288MoEvisits with validated causal misses; medianMLP0–6misses
3.795/5.373/8.540/11.572/14.578/17.582/20.617ms. Correlation only.
081prefillseeding removes0.610%remaining reads/deferred.082decays4/8/16lose
on miss counts to32/deferred.069/073 async probes show no consistentgain/deferred.

## Operations

Sampler3036(shim9352,parent10880) ACTIVE,048-host-resources.jsonl,
stopmarkerstop-048-sampler, expiry~18:13UTC. Keep it running.
Capture completed trial with exactPID+creation:
`python3 /private/tmp/capture-inkling-trial.py NUMBER STEM PID CREATED`
Use`--repetitions3` for confirmation. Helper checks IDs/grid/full shape/hash,
SHA-verifies copies and archives diagnostics. Output/private/tmp/inkling-STEM-artifacts.
Do not overwrite immutable snapshots; failed optional analysis needs explicit
scoped diagnostic treatment, as089 demonstrates. Process thread totals include
non-Rayon threads; do not gate total=Rayon+1.

Selected profile:16workers,rows2/4,Reads0,MmapEmbed1,Reuse1,SkipBulk1,OwnShared1,
Uncached1,Pipeline1,cache256perlayer,PrefillReads1,historyreset1,decay32,
Highpriority,all16CPUaffinity65535. Actual retained16.3096GB,ownedshared4.0769GB.
Runtime flags remain opt-in; native cache-decay242tests+five tiny modes passed.
Preserve all frozen binaries, protectedOVMS6728/node8356/CA6344, otherworktrees.
Originalfeat/inkling rechecked09:51UTC unchanged clean9aaebff0.
No new export/Lambda work needed. Commit AND push as Tate Berenbaum
<t8@users.noreply.github.com>; no coauthor trailers. Our branch/worktree:
perf/inkling-panther-autolab at/private/tmp/tahoma-inkling-panther-autolab.
Historical details below; active state above takes precedence.

## Ownership and repositories

- Our worktree: `/private/tmp/tahoma-inkling-panther-autolab`.
- Branch: `perf/inkling-panther-autolab`; run `git log -1` for latest commit.
- Origin: https://github.com/labscommunity/cascadia.git.
- Author AND committer: `Tate Berenbaum <t8@users.noreply.github.com>`.
  User authorized commit/push and expressly prohibited coauthor trailers.
- Original agent worktree: `/Users/tatef/Workspaces/tahoma-inkling`,
  feat/inkling,9aaebff0,PR154, last checked unchanged. Leave it alone.
- Main checkout: `/Users/tatef/Workspaces/tahoma`,perf/prefill-layer-streaming.
  Dirty glm5_run.rs and untracked ngram_sim.rs belong to other work. Untouched.
- Autolab: `/Users/tatef/Workspaces/autolab`,3993e2c4; pre-existing dirty
  src/autolab/runners/ssh.py untouched.
- Python: `/private/tmp/inkling-autolab-venv/bin/python` (editable Autolab,
  pytest,PyYAML). Main ignored pointer:tmp/INKLING_AUTOLAB_HANDOFF.md.
- Research-loop skill read/applied from sibling Autolab plugin; record
  hypotheses/results in JOURNAL.md. No separate Claude process required.
- No AGENTS.md found. rg shim hangs; use git grep/git ls-files/bounded Python.
  Unrestricted permissions, approvalnever, never pass sandbox_permissions.
  Latest developer disallows delegation absent explicit request; none spawned.

## Hosts and current process state

`inkling-ptl-direct`: devcloud@192.168.22.2 via guest@192.55.48.214, both using
`~/.ssh/cascadia_ed25519`. User authorized this route. Fallback alias
cascadia-tate-07-ts:devcloud@100.82.253.76,~/.ssh/id_ed25519.
Native hostpdx88-pa0794,Windows11Pro,CoreUltraX7 358H,16threads,64GBRAM,
ArcB390,LPDDR5X8533,SamsungMZVLC1T0HFLU-00BT7 SSD.

Task root **C:\Users\devcloud\inkling-autolab**; subdirsrepo,bin,target,model.
Final native2144 and controller4290 exited normally at01:52UTC. Resource sampler
4208/shim3376 exited after stop-trials-sampler marker. Final host check01:54UTC:
active taskjobs[], free disk264,601,800,704B; protected services **OVMS6728,
node8356,CA6344** still running. Never broad-kill Python/Cargo/full processes.
Old036 SSH transport failed after native completion; its native result was
independently verified and the failed Autolab history deliberately preserved.

Remote default shellPowerShell. Complex Python reliably runs via local
subprocess.run(['ssh','-o','BatchMode=yes','inkling-ptl-direct',
'C:/Users/devcloud/venvs/qwen38/Scripts/python.exe -'],input=script,text=True).
For complex PS use UTF16LEbase64 EncodedCommand with ProgressPreferenceSilentlyContinue.
SCP paths use inkling-ptl-direct:C:/Users/devcloud/.... Wait for transfers to
finish before dependent actions. Never print/copy private keys or tokens.

## Model and selected profile

Full export **548,985,140,942B /16,654files**, every source/destinationSHA verified.
Model-ready SHA9e7f11b6131131e8c3db879a814e121cd6a4fde9c6987fa6de7e86a80cb46a20.
Independent source **miner:/mnt/external_ssd/inkling/out**, miner SSH
tatef@192.168.0.235:1990,cascadia key. Priorcleanup reclaimed821,909,577,728B.
All model transfers/sourceHTTPservers/tunnels ended; retired tokens absent
from all six known paths(report031). Historical deployment is archived in
DEPLOYMENT_HISTORY.md. Do not restart it.

**ptl-profile.ps1** sets12 process environment values before NEW engine launch:
Rayon16,parallel experts,Reads0,Pin0,BF16Rows2,Int4Rows4,MmapEmbed1,
ReuseBuffers1,SkipBulkPrefetch1,OwnShared1,UncachedReads1,PipelineReads1.
The run-full.ps1 wrapper additionally sets its child High priority/all16CPUs.
It does not mutate global settings or restart services. Campaign046 contains
the exact command/reference cases and actual-setting gates, with SSH keepalives
15seconds/count3. Avoid concurrent full benchmarks/builds on this host.

Qualified binary **full-pipeline.exe**,source18f8becb,SHA
8305491ebbc4bacc09fdb3aeccbe331b153e0fd79d34a273baef2ddb5d593e8b.
All five earlier binaries preserved/unchanged; hashes in046_final_host_state.
All233 native qualification tests passed, fixture greedy IDs and hashmatch.
Tiny fixturehash1f7cd0eb14a22662 onMSVCrelease,5122e042f9b1fb30 onARMdebug;
never compare hashes across those architectures.

Opt-in implementations: sparse BF16 embeddingmapping, bounded256MiBidle
allocation pool, skipped redundant bulk-read hints,4.077GBowned shared packed
experts, aligned Windows FILE_FLAG_NO_BUFFERING reads with complete cached
fallback, and per-expert read/compute overlap preserving indexed gate order.
No arithmetic/weight changes. Tiny fixture bins are unaligned and correctly
fall back; native aligned canaries/full042/046 validate actualuncached path.
Final actual counters:owned4076863488,uncached6638089273344B,fallbacks0,
pipelinedlayers36288,mappedembedding1. Full hash/IDs preserved.

## Rental readiness and cost

User designated **ubuntu@129.146.170.51**,8×A100SXM4-40GB,~$15/hour,for all
future exports. Aliasinkling-export,key~/.ssh/amx-bench_ed25519. ProviderLambda,
user confirmed no attached persistent filesystem. Export jobs all ended;
no raw checkpoint or complete export on rental, only tiny config,code,logs,venv.
Current PTL experiments require no rental or new export.

Verified backup:
`/Users/tatef/Workspaces/inkling-export-backups/20260913/inkling-export-release-20260913.tar.gz`
345,278B,SHA743ebc8229913500e5eda01bea4994128503e7ea2eaf819cb633b913d7b2a5f2.
Includes deployed code, task logs,config,packagefreeze,hostmetadata; no keys.
Extracted snapshot adjacent. Rebuild guide **EXPORT_HOST.md** and package lock
are committed. Fresh restore time not measured; UV existing-envdryrun passed.

**No Lambda termination performed; billing has not been stopped by this agent.**
No accountAPI/console tools or configured APIaccess found. Lambda requires
termination to stop billing; guestshutdown still bills and suspension is not
supported. Termination erases local disk. User can terminate129.146.170.51 in
Lambda console after reviewing the backup; do not claim this already happened.
https://docs.lambda.ai/public-cloud/on-demand/creating-managing-instances/

CUDA exporter48tests passed. Defaultcuda:all,8processes×1worker,64MiBchunks,
host-localflock,complete source required for multiprocess mode; source retained.
Useprocesses1 for original streaming/partial mode. Measured58.98experts/s,
2.60×priorGPUthreadpool,all9CPUbyteoracles match. Expertstageextrap4.67min/$1.17.
Whole export estimate15–30min/$4–8 with source local; first1.905TBdownload+
exportroughly2–3hours/$30–45. These are estimates, not timed full exports.
Matched8-expert CUDA speedup1.58×minerCUDA/3.73×minerCPU; othercrossbatchnumbers
are not matched full-export speedups. Fresh549GBdelivery at103.7MB/s adds88min
(~$22 if rental serves it); rentalroute unmeasured. Current export already onPTL.

085 offline timing join validated all36288MoEvisits against actual074 counters.
MedianMLP time for0/1/2/3/4/5/6misses:3.795/5.373/8.540/11.572/14.578/17.582/20.617ms.
These are correlations, not isolated read timings. Report085_cache_miss_timing.json.

086 allocation metadata probe STAGED AND WAITING: nativePython3604,parent1164,
statefile-extents-probe-state.json, output086-file-extents.json/.log. Sourceprobe-file-extents.py
will wait for084 terminal state and exit, then take queue lock and query36 original
files withFSCTL_GET_RETRIEVAL_POINTERS. Native-only; localsyntax passes. No data
reads or file/volume mutation. Staged script and unchanged read helper SHA verified before launch.

087 topology: class1CPU0–3;class0CPU4–15. CPU0–11 LLCindex0;CPU12–15 LLCindex12.
All16 used during074 decode;087_decode_cpu_usage.json is machine-wide, not process-only.
088_affinity qualifier PREPARED, NOT STAGED/LAUNCHED as of this checkpoint.
Localrun-full.ps1 now adds optionalAffinityMask/readback, default65535 unchanged.
Native production wrapper still OLD; stage new asrun-full-affinity.ps1 with
affinity-source.json andqualify-affinity.py. Nativequalifier must wait084+086
terminal/exited, then tinytestmasks65535/16,4095/12,4095/16. It promotes wrapper
only afterallpassandprevious/candidate/binary SHA checks. After088 complete,
prepared089/090/091 full-affinity campaigns may run sequentially. No rebuild.
