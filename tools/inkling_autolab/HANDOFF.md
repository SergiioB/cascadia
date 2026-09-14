# Inkling / Panther Lake Autolab restart handoff

Updated2026-09-14 12:20UTC. Work is ACTIVE. User requested autonomous optimization
toward25tok/s. The target is unmet; do not stop after a finite campaign.

## Completed113/114 longer-prompt comparison (11:55UTC)

113 COMPLETE/SHA captured, score0.9165585148, all gates pass; native8876 exited.
114 COMPLETE/SHA captured; native2540 exited. Controller73146 exited normally.
114score1.0570071611, allthreeheldoutprompts+15.02/16.15/15.32%. Every128ID,
fullhash e396cc533e658e44, actualroutes/cache/readcounts exact.24124successful,
22873useful/1251unused, zero failures; minavailableRAM1.69GB. NoMLPevents>.5s
in eitherarm.114_heldout_prefetch_comparison.json, notcanonicalrecord. Controller was
/private/tmp/run-inkling-heldout-prefetch-loop.py. It verifies each campaign,
records native identity, SHA captures with scoped helper
/private/tmp/capture-inkling-heldout-prefetch.py, then compares all outputs,
routes/cache/read counts. It runs113control then114prefetch on the same frozen
full-predicted-read.exe. Both128generated/127decode, one repetition, frozen
heldout cases. No prediction trace, only PredictReads differs. Separate from
canonical record. Native113-heldout-prefetch-control.*,114-heldout-prefetch-prefetch.*.
Local logs/private/tmp/inkling-113_heldout_prefetch_control.log and corresponding114.

## Current confirmed record112

**1.0904267748tok/s**, slowest of nine; median1.1492074013,max1.2299078616.
Allnine faster than102; conservative+12.9494%,8.0573× original.
Fullhash ce0fbb9a116d3d09, every ID/route/cache/predicted-read counter exact.
35,718 scheduled/successful,34,014 useful,1,704 unused,0failures. Actualreads
3,808,650,461,184 bytes,1.4456% extra vs102. Firstwater second-token MLP layer48
stall2.6689s remainsincluded; no samples removed. MinavailableRAM1.85GB,
peakprivate42.52GB. Native8584/controller84880 and verifier83854 exited.
112_final_verification.json,112_repeated_prefetch_comparison.json and
112_profile_promotion.json preserve proof. Selected profile nowPredictReads1,
local/nativeptl-profile.ps1 SHA ff9572f5c3889b9678cecf230948efde635aceeefcce2195e222df92e4b2d08d.
Frozenbinary7b20ee35/source dc4badd3, native/localwrapper3eac49ad unchanged.
25targetunmet. No export/Lambda work needed.

## Current121/122 runtime comparison (12:20UTC)

121current-prefetch control RUNNING native9348, creation1789388242.4688969,
full-early-prefetch.exe381c116608c3c9d6cec94861d0f09f66073c79989b750c4aead019d82d4942c6.
Controller4645 script/private/tmp/run-inkling-early-prefetch-loop.py archives
all exact outputs/routes/cache/readcounts and runs122early candidate next.
Bothoriginal3prompts×1rep,64generated/63decode, PredictReads1. Only
EarlyPredictReads0/1 differs. It saves122_early_prefetch_comparison.json and
ends for root review before conditional123nine-sample confirmation. Continue
autonomously after finite campaigns; target25 remains unmet.
Native121-current-prefetch-control.* and122-early-prefetch-candidate.*.
Local logs/private/tmp/inkling-121_full_current_prefetch_control.log and122equivalent.
123_full_early_prefetch_confirmation prepared, notlaunched. Repeatedforecast
35844scheduled/31168useful/4676unused from fullnine route/cache replay. Do not
blindly multiply117singlepasscounts. Firstsamples/stalls must stay included.

120 COMPLETE/SHA archived:255 native tests/13suites, fourtiny modes, invalid
EarlyPredictReads1/PredictReads0 dependency rejected. All13olderbinaries preserved.
Sourceb53a984b410b84a19cc03f8b66ef1db6610d282d,3Rustsourcefiles in
 early-prefetch-source.json; archiveSHA69eaf25c674f9be92af4bef35edfbb4376b64008c9ca44035fc8a6ac5bd163bd.
Native6672(created1789388126.538558)/parent6324 exited. Native/localwrappernow
ca787020488b22653939aaf27fe1413600e81e8b347e527a50397fe6003c0106.
Controller uses dedicatedControlMaster/ControlPersist60; all120 transfers succeeded.
SelectedprofileexplicitEarly0 guard synced native/localSHA
5f7a0440f22312a9586d5b64fdc268f5b8c2cce058abb9f283228bd96633fbf1;
120_profile_default_guard.json. Record112/PredictReads1/current-layer remains.

119 IMPLEMENTED and locally251tests/fivetiny modes pass. Envflag
CASCADIA_INKLING_EARLY_PREDICT_READS=1 requires existingpredictedreads+localcache.
Model schedules nextlayer frompredecessorinput, carriesPendingRead intoLayer,
skips duplicatecurrentpredictions evenwhen earlylookupfoundnone. Layer0retains
current behavior. Atmostcurrent+next pending permodel; unused/error/unwinddrain
andactualgate/cacheadmissionunchanged. Requestchannelnow2, oneworker,response1;
blockedworker testproves queued submissionprogress andownership. Layer-only/staged
execution retains currentlayerbehavior (earlypath is wholeModel). Benchmark
actualearly_prediction_reads_effectivegates runtime mode. Tinycurrent13/11/2,
early16/10/6 scheduled/useful/unused; exact priorpredictiontraces andoutputs.

## Completed117/118 evidence

117 one-layer-early diagnostic: all original3×1rep/64IDs/hash/actual routes/cache
and zeroactualprefetch counters exact. Rates.9772436894/.9468468067/.9711400874,
diagnostic-only. Firstuncached forecast11948predicted/10390useful/1558extra,
precision86.9602%, coverage26.4249%, extra3.9625%. More thanone prediction has
largeamplification; focusone. Source23412241/full-early-prediction.exe853c4cbe.
117_early_prediction_accuracy.json and allraw/SHA/resources are archived.
Native10960(created1789387032.1257544)/controller18569 exited.

118 exclusivefilehandle read-onlyprobe:30balancedpairs/120full-sizedexpertfiles,
botharmsSHAchecked vs mmap, canaryvalid and removed, handles/buffersreleased.
Median ratios2/4/6files .99942/1.00785/1.01242; sensitive tofirstmode. Reject
runtimehandlecache;118_decision.json. Source68f515fc, capture17451 complete.
Probe73373 ended and nativeidentity is in118_artifact_verification.json.

116 qualified254native tests/fourtiny modes; all12older binaries preserved.
Native/localrun-full.ps1 both6db0fff9febcde166227c4909eab4376454623e1c5b74cd21564202dc1f59c04.
Current nativeRust source234122415f292d51519b9f40684b60c30bfc71df, frozen
full-early-prediction.exe853c4cbe2ecfb5e35f0f948cfff3196686e779d66c4c62fd152fc00b6cbd9d9d.
Record remains112/frozenfull-predicted-read.exe7b20ee35, selectedprofileff9572f5.
Preserve all13frozenbinaries in nextqualifier. Qualified115 diagnostic source,
250localtests/fourmodes. Native116rawproof in116_artifact_verification.json.

SSH transport:116 initialcontroller11957 failed copying only finaltinyfile;
all prior copiesSHA valid. Resume18569 reusedvalidcopies, enabled dedicated
ControlMaster socket/private/tmp/inkling-early-ctl-%C,ControlPersist60, and
completedtransfer+117. Connection reuse reduces bursts of handshakes; exact
jump-host reset cause not established. No gates bypassed or tests repeated.

## Historical110/111 launch state (both now complete)

**111_full_predicted_read_prefetch RUNNING**, native **PID3408**, created
**1789384539.2968717**, frozenfull-predicted-read.exe. Localcontroller **92370**,
script **/private/tmp/run-inkling-predicted-read-loop.py**.110 control completed
0.9679409165tok/s, all outputs/counters/SHA archives verified. Native1107308
(created1789384238.1766171) exited; capture7662 completed. Controller92370 now
runs111 and stops for review before conditional112. Logs
/private/tmp/inkling-110_full_predicted_read_control.log and
/private/tmp/inkling-111_full_predicted_read_prefetch.log.
Native outputs110-predicted-read-control.* and111-predicted-read-prefetch.*.
Both canonicalthree prompts × onerep,64generated/63decode, selectedrecentcache.
110PredictReads0;111PredictReads1. Full exact output and actual-counter gates.

109 COMPLETE:252 native tests/13suites and four tiny read/recency modes pass.
All outputs/routes/cache counters match. Tiny13scheduled/11useful/2unused with
0failures, matching independent native104 causal replay. All11 older frozen
binaries unchanged. Python8624 and launcher9300 exited (parent3856).
New full-predicted-read.exe SHA
7b20ee3592cb09267787792f2994a7cb54555f1dc0f1a74bf2d3517b0ead6f7a,
source **dc4badd3d21e5be1be7bfd542019cb9c3527b09a**.109_artifact_verification.json.
Native/local production run-full.ps1 now both match candidatewrapper SHA
3eac49ad3042d50a4425f372e24fed12ff9b8b5b983974dfe0d3ee4d3262a7a7.
Earlier controller58085 failed only while copying the last109 artifact after
qualification.92370 resumed SHA-verified files, copied the missing final file,
archived109, synced localwrapper, then started110. No experiment was bypassed.

Expected111: prediction_read_scheduled11906,successful11906,useful11338,
unused568. Use the campaign YAML as the exact byte-counter source;
uncached_read_bytes1270420733952. Failures0, allcache counters same101.
110prediction counters0 anduncached1252329652224. All future campaigns use
**runner.connect_timeout:30**, not a duplicate ssh_options setting.

**112_full_predicted_read_confirmation PREPARED, not launched.** Conditional on
verified111 gain; three repetitions, scheduled35718/useful34014/unused1704,
uncached3808650461184, allcache counters same102. Forecast repeats observed105
predictions for identical reset inputs; actual counters must verify determinism.
No promotion until complete repeated score and exact artifacts are checked.

Capture110/111 with /private/tmp/capture-inkling-trial.py NUMBER STEM PID CREATED.
It supports the original63decode/ce0fbb9a116d3d09 grid. 111 nativeidentity3408/1789384539.2968717 is confirmed. Use--repetitions3 for112.
Snapshot, SHA copies, exact grid/IDs/full shape, layer/resource analysis included.
No broad process kills; preserve OVMS6728/node8356/CA6344 and sampler3036.

## Prefetch implementation and completed diagnostic evidence

108 code committeddb496530, included in native dc4badd3.248 local tests/13suites
and four complete tiny modes passed. Newpredicted_read.rs uses one bounded
background reader independent of Rayon and one predicted uncached expert per
layer. Layer launches before attention; actual MoE selection alone consumes
complete bytes via normal scratch slots. Unused reads drain before return;
failures keep ordinary full-read fallback. Cache membership query is read-only;
math/routes/cache admission order unchanged. Defaultoff, flag
CASCADIA_INKLING_PREDICT_READS=1. Explicit counters distinguish scheduled,
successful/useful/unused bytes, read/worker/dispatch failures. No speed claim yet.

105 diagnostic (no reads) verified first-uncached prediction precision95.229%,
28.836% miss coverage,1.4446% extra reads;11338useful/568unused. Canonicalthree
prompts ×1rep; alloutputs/routes/cache counters exact. Diagnostic score.947160.
105_pre_attention_prediction.json, raw/SHA archives. Source32e2de69, frozen
full-route-prediction.exe SHA89c0f361ac53bbae6af52979d889216138800296c99699976dbeb1732da93984.

106/107 unseen-prompt validation COMPLETE. Three frozen new128generated/
127decode-token prefixes (algebra,JSON inventory,dialogue), hash
**e396cc533e658e44**. Alloutputs/routes exact; text reviewed coherent truncated
prefixes (JSON is not a completed JSON document). Initial106 correctness flag
remainsfalse/reference-only;107 verifies its IDs/hash. No canonicalrecord claim.
106strict cache87070misses;107recentcache82859, down4.836%.107prediction precision
94.814%,27.605% miss coverage,1.510% extra reads(24124/22873/1251).

107diagnostic ratesalgebra.90215vs106.94204,JSON.90125vs.94585,dialogue.885139vs
.885341. It includes prediction overhead absent106, so not a purecacheA/B.
NoMLPevent>.5s in either run. Matched14242 identical actual read-set visits show
medianMLP ratio1.0188 andattention1.0555; cause ofremaining variation unestablished.
No samples excluded.107_heldout_comparison.json/107_identical_read_set_timing.json.
Finisher63210 completed /private/tmp/finish-inkling-heldout.py; do not rerun its
exclusive-output writes. Scopedcapture/private/tmp/capture-inkling-heldout.py
is only for106/107, handles128tokens/newhash and reference-only labels.

107 initialSSHbanner failure beforelaunch is preserved. Identical107b retry
controller12159 succeeded, native4424(created1789383292.9362197) exited.
106native596(created1789382341.9607809)/Python3092 also exited. Autolab default
connect_timeout10 precedes ssh_options, so extraConnectTimeout30 had no effect;
localssh-G proved it. Futurecampaigns use dedicated connect_timeout30.

## Restart and source pointers

Our worktree/private/tmp/tahoma-inkling-panther-autolab, branch
perf/inkling-panther-autolab. Latest pushed checkpointa15e27e5;107/109 completion
checkpoint next. Run git log -1 for currentHEAD. Author AND committer
Tate Berenbaum<t8@users.noreply.github.com>, no coauthor. User authorizedpush.
Native source manifestpredicted-read-source.json; tar/private/tmp/predicted-read-source.tar,
SHA d2100c0cfecb8e4b6c4b3ec6951322240f78c4888a4d3aaba8c57462eb2ec14c.
Selected ptl-profile.ps1 recentties1 SHA
deaec33e4c80b1f167eb04fe25945980000cd58df8370cb5c9e1783fad1dd304 synced.
Sampler3036 remains active,048-host-resources.jsonl, expiry~18:13UTC.
Read-only memory ownership099 explains20.03GB sharedGPU use by existingOVMS;
do not stop it. No global power/affinity/service changes. Details/history follow.

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
