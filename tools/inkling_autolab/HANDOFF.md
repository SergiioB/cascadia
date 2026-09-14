# Inkling / Panther Lake Autolab restart handoff

Updated 2026-09-14 10:01 UTC. Work is ACTIVE. User requested autonomous optimization toward
25 tok/s. Do not stop after a finite campaign. The target remains unmet.

## Current record

Confirmed074: **0.9382743961 tok/s**, slowest of nine samples; median0.9648021079,
fastest1.0329282085. This is6.933× the original. All tokens/logits/routes/counters
match. Selected profile remains16workers, all16CPUs, BF16rows2/int4rows4,
cache256MiB perMoElayer, historyreset1, decay32, streamedprefill and all prior
I/O flags. Full CPU backend. No full Arc backend. No Lambda or export needed.

094/095 repeated row comparison finished:2/4control0.9354823511 versus2/2candidate
0.9355367858, a0.00582% difference. Retain2/4. Both raw artifacts, all route arrays,
cache counters and nine output samples are verified.095_repeated_row_comparison.json.
Native094 PID5132(created1789378071.276495),095 PID7928(created1789378926.7827115),
and localcontroller95987 exited. Their outputs094-rows-repeated-control.* and
095-rows-repeated-candidate.* are archived. No new record was promoted.

## Active full cache-recency comparison

**100_full_cache_recency_control RUNNING**, native **PID9956**, created
**1789379922.80522**. Outputs100-cache-recency-control.json/.log/-routes.json/-layers.json.
Localcontroller **70713**, script **/private/tmp/run-inkling-cache-recency-loop.py**.
It runs100 then101_full_cache_recency_recent sequentially, with logs
/private/tmp/inkling-CAMPAIGN_NAME.log.101 outputs101-cache-recency-recent.*.
Both3prompts×1rep,64generated/63decode, rows2/4/all16CPUs/16workers/cache256/decay32.
100CacheRecentTies0;101CacheRecentTies1. Actual counters/hash/IDs are gated.

Qualified frozen **full-cache-recency.exe**, source **849a08bd**,
SHA **a23289477c2d5ade1e838ccf92d27ec8b5d31b1cebc4d79bc7d74ec85d1daa40**.
098 native245 tests andfive tiny wrapper modes passed. Python3144,parent10896,
cmd2616 exited. All raw098 artifacts andSHA copied;098_artifact_verification.json.
Native productionrun-full.ps1 promoted after tests and matches local file,
SHA2217f5076314e4462bc95dbe2e5d6a643981e65d11a2444bd412813d59ed1f97.
All9 older frozen binaries remain unchanged, including recordfull-cache-decay.exe
SHA3874c863852b036757069bbac207a473481dd5408c854c037c7a2a72f6a431e8/source6b820e83.

Recent-tie admission is opt-in CASCADIA_INKLING_CACHE_RECENT_TIES=1. It admits a
newer expert on equal frequency, while preserving later current-cohort hits and
outstanding leases. No arithmetic/weight changes. Actualrecent_tie_admissions
is cumulative.096 causal replay predicts4.549% fewer reads; no full speedup yet.
Counter predictions097_cache_recency_counter_predictions.json:
1rep recent33257hits/39319misses/26816admit/26304evict/20015ties;
uncached1252329652224, hitbytes1059251945472.
3rep99853/117875/80366/79854/60045ties; uncached3754377216000,hitbytes3180367577088.
All other profile/counters unchanged. Control1rep31383hits/41193misses/8629admit/
8117evict/0ties; uncached1312017481728,hitbytes999564115968.

**102_full_cache_recency_confirmation PREPARED, NOT LAUNCHED.**
After100/101 finish and are compared, run102 only if recent wins.102uses3reps/
nine samples and exact predicted counters. Controller70713 does not launch102.
Capture completed runs with the helper below, preserve failures, confirm before
promoting profile/record, then continue optimization.

## Future103 prediction diagnostic and104 qualification

Source **67973647** is committed/pushed, but not deployed natively. It adds a
separate decode-only pre-attention observer using current residual input plus
the existing MLP norm/router. Actual routes/cache history/state are unchanged;
no speculative reads occur. Benchmark--prediction-trace requires--route-trace.
analyze-route-prediction.py scores1–6uncached predictions against causal cache
state.243localtests pass, includingtwo observer/causality tests.3repeatARMfixture
hash5122e042f9b1fb30, actualroute arrays andcachecountersexact. Invaliddiagnostics
rejected. Artifacts103*. **Do not confuse this later code with098 binary849a08bd.**
104 qualification scripts are PREPARED locally:qualify-route-prediction.py,
test-route-prediction.bat,run-full-prediction.ps1. Package/stage their source
manifest/tar and launch;104 waits100/101 then builds/tests247native tests and
four tiny modes. It preserves all10older binaries. Currentproductionwrapper
remains2217f507; candidatewrapper is a separate file, promoted only aftertests.
**102must wait104qualified/exited if104is staged.** Then102 may confirmthe
frozenrecencybinary;105fullpredictiondiagnostic can follow. No105campaign yet.
Published other-model accuracy is not Inkling evidence. Sources inJOURNAL.md.

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
