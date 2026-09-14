# Inkling / Panther Lake Autolab restart handoff

Updated 2026-09-14 09:26 UTC. Work is ACTIVE. User requested autonomous
optimization toward25tok/s. Do not stop after a finite campaign. Target unmet.

## Current record and active trials

Confirmed campaign074: **0.9382743961tok/s** slowest of nine samples,
median0.9648021079, fastest1.0329282085.6.933×original and1.652×prior046record.
All tokens/logits/routes/actual counters match. PERFORMANCE.md and native/local
ptl-profile.ps1 were promoted. Full CPU backend; no full Arc backend.

**089–091 affinity sweep COMPLETE; keep all16CPUs/16workers.**
Scores:089mask65535/thread16=.9268264569;090mask4095/thread12=.8891493949;
091mask4095/thread16=.8906346900. All numerical/configuration gates and raw
artifact SHA checks passed. Controller43106 and all native full processes exited.
089 optional phase resource attribution rejected a1.544745s wall-clock shift;
089_resources.json is lifetime-only with monotonic elapsed, and089_clock_anomaly
records the limitation. RustInstant benchmark rates remain valid.

**092 layout probe COMPLETE AND EXITED**, Python6392,parent10052.
All30pairs/120files passed SHA; temporary copies removed,260.59GB free afterward.
Median original/copy physical runs5/1. Copies win4/10,7/10,10/10 for2/4/6files;
paired median speedups.831/1.058/1.052.2files has large order effects. Modest,
mixed component result; no original model file relocated. Raw artifacts/state
and hashes saved in092_artifact_verification.json.

**093 qualifier COMPLETE/EXITED;094 repeated control RUNNING.**
Controller95987: /private/tmp/run-inkling-repeated-rows.py.
Native094 PID5132, created1789378071.276495. Outputs094-rows-repeated-control.*.
095candidate queued automatically; logs /private/tmp/inkling-CAMPAIGN_NAME.log.
093Python8176,parent9488 exited; both modes passed, all raw files SHA copied.
Read native row-affinity-qualification-state.json for status/PID.
Sourcequalify-row-affinity.py tests rows2/4 and2/2 with mask65535/thread16,
cache1MiB tiny oracle, decay32/current wrapper; no wrapper mutation.
It waits for092 complete/exited and no temp files/full process, then queue lock.
After093 passes, run094_full_rows_repeated_control then095_full_rows_repeated_candidate.
Each3prompts×3reps,64generated/63decode, exact full hash/IDs/cache/I/O counters.
094rows2/4,095rows2/2; both all16CPUs/16workers/cache256perlayer/historyreset1/decay32.
Frozen full-cache-decay.exe SHA3874c863852b036757069bbac207a473481dd5408c854c037c7a2a72f6a431e8,
source6b820e83 unchanged. Do not promote2/2 before repeated comparison.
Continue optimization afterward; finite campaign completion is not task completion.

## Pending cache recency implementation (097/098)

096 causal replay: recent-use admission on frequency ties predicts4.549% fewer
reads at32/ceil/8slots; every sample4.34–4.85% reduction. Default strict policy
unchanged. Implemented opt-in CASCADIA_INKLING_CACHE_RECENT_TIES and actual
recent_tie_admissions statistic, three buffer/ordering/real-byte tests.
Local241 tests pass, including all10 cache tests. No native build yet.
Localrun-full.ps1 candidate supportsCacheRecentTies andfull-cache-recency.exe;
**native run-full.ps1 still old/current and used by094/095**. Never replace it
mid-sweep. Newqualify-cache-recency.py/test-cache-recency.bat will wait both
repeated trials finish, then verify previous source/frozen binaries, build/test,
runfive tiny wrapper modes, and promote wrapper only after qualification.
Source849a08bd committed/pushed; manifest cache-recency-source.json and tar
/private/tmp/cache-recency-source.tar built from SHA-verified native baseline.
All candidate files staged and SHA verified, PowerShell parser passed.
098 qualifier ACTIVE/WAITING, Python3144,parent10896, state
cache-recency-qualification-state.json. It waits094/095.
No full recency trial prepared yet. Counter predictions097_cache_recency_counter_predictions.json:
1rep recent33257hits39319misses26816admit26304evict20015ties,
uncached1252329652224/hitbytes1059251945472.3rep99853/117875/80366/79854/60045ties,
uncached3754377216000/hitbytes3180367577088. Other counters/profile unchanged.
Rowchoice for futurefullrecency campaigns depends on094/095 repeated outcome.

## Completed evidence

076–080 row sweep complete:2/4=.924475,1/4=.927358,4/4=.931144,
2/1=.929776,2/2=.935296. Last improves everyprompt0.75–1.17% vsfreshcontrol,
but needs repeatedconfirmation.080_row_comparison.json. Confirmed profile
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
Originalfeat/inkling rechecked09:12UTC unchanged clean9aaebff0.
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
