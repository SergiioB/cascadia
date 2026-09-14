# Inkling / Panther Lake Autolab restart handoff

Updated 2026-09-14 09:15 UTC. Work is ACTIVE. User requested autonomous
optimization toward25tok/s. Do not stop after a finite campaign. Target unmet.

## Current record and active trials

Confirmed campaign074: **0.9382743961tok/s** slowest of nine samples,
median0.9648021079, fastest1.0329282085.6.933×original and1.652×prior046record.
All tokens/logits/routes/actual counters match. PERFORMANCE.md and native/local
ptl-profile.ps1 were promoted. Full CPU backend; no full Arc backend.

**090_full_affinity_4095_12 RUNNING;091_full_affinity_4095_16 QUEUED.**
Controller **43106**, script`/private/tmp/run-inkling-affinity-loop.py`.
Logs`/private/tmp/inkling-CAMPAIGN_NAME.log`.
Native090 **PID4780**, created**1789377059.9814112**.
Outputs090-affinity-4095-12.json/.log/-routes.json/-layers.json;
next091-affinity-4095-16.*.089 all16CPU/16worker control completed0.9268264569.
089 PID8156 created1789376738.9105453 exited; raw artifacts/SHA/layer profile
verified. Its optional phase resource analysis rejected a1.544745s wall-clock
shift in short_story decode. **089_resources.json is explicitly lifetime-only**
with monotonic sampler elapsed;089_clock_anomaly.json records the limitation.
Benchmark rates use RustInstant and remain valid. Do not relax phase checks.

Both candidates restrict process affinity to4095(CPUs0–11), with12/16workers.
They retain BF16rows2/int4rows4, cache256MiBperlayer, PrefillReads1, historyreset1,
decay32, all selected flags. Actual child affinity is read back and gated.
Native production run-full.ps1 was promoted by088 after all3tiny modes passed;
it matches the local file. Sourcewrapper0840a7f1; affinity-source.json has exact
old/newSHA. **Frozen engine unchanged**: full-cache-decay.exe SHA
3874c863852b036757069bbac207a473481dd5408c854c037c7a2a72f6a431e8, source6b820e83.
Each full trial3prompts×1rep,64generated/63decode; exact hashce0fbb9a116d3d09,
IDs and cache/I/O counters. Native08810528,parent3964 exited; all artifacts saved.

After affinity sweep, **092 matched layout-read probe PREPARED, NOT STAGED OR
LAUNCHED** at this checkpoint. Sourcepaired-layout-read-probe.py and helper
file-extent-metadata.py. Stage both, SHA check them plus unchanged
uncached-read-probe.py, then launch detached with
--out C:/Users/devcloud/inkling-autolab/092-layout-read-probe.json.
It waits for089–091 reports and no full process, then takes queue lock.
30matched cohorts,2/4/6 files, balancedAB/BA; writes only temporary sequential
byte-identical copies, queries original/copy extents, hashes both timed arms.
Original model files remain untouched; temp files are removed afterward.
Local extent-parser tests and syntax checks passed (092_probe_local_validation).
**Do not start another full trial until092 completes/exits.** Then confirm the
best row/affinity combination across3reps (nine samples) before promoting it.
Row2/2 is the current unconfirmed candidate; keep an exact native tiny oracle
for the combined settings. Continue optimization afterward.

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
