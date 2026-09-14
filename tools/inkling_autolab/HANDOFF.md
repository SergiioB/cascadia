# Inkling / Panther Lake Autolab restart handoff

Updated2026-09-14 09:01UTC. User resumed autonomous optimization.
Work is ACTIVE; do not stop after a finite campaign. Target25tok/s is unmet.

## Current record and live work

**Confirmed074 record:0.9382743961tok/s**, slowest of nine samples,
median0.9648021079,fastest1.0329282085.6.933×original,1.652×prior046 record.
All baseline IDs/hash, all046 prefill+decode routes, all actual cache/I/O counters
match. Native6112 exited. Verification074_final_verification.json, raw artifacts
and SHA manifests committed with this handoff. PERFORMANCE.md and ptl-profile.ps1
promoted; native profile copy SHA verified. Sampler remains active.

**076 control COMPLETE0.9244748903**, **077 rows1/4 COMPLETE0.9273579552**;
**078 rows4/4 COMPLETE0.9311444128**, **079b rows2/1 COMPLETE0.9297757263**;
**080_full_rows_2_2 RUNNING**.
Controller **66059**, script`/private/tmp/run-inkling-row-loop-resume.py`.
Original36811 exited after079 SSH banner timeout; failed079 history is retained.
Host recheck proved no079 files/process before retry. Newcampaign079b_full_rows_2_1_retry
uses original079 native outputs,30sConnectTimeout;080 has same transport timeout.
Logs`/private/tmp/inkling-076_full_rows_2_4.log` and equivalent campaign names.
Native0786304 and0776752 exited; both artifacts/SHA/profiles are archived.
Native080 **PID5180**, created**1789376229.1035454**.079b3268 exited;
079 native artifacts and retry campaign report are archived, original failed079 retained.
Outputs076-rows-2-4.json/.log/-routes.json/-layers.json, then077-rows-1-4.*,
078-rows-4-4.*,079-rows-2-1.*,080-rows-2-2.*.
Frozenfull-cache-decay.exe SHA3874c863852b036757069bbac207a473481dd5408c854c037c7a2a72f6a431e8,
source6b820e83. All have16workers/cache256MiBperlayer/PrefillReads1/
CacheResetHistory1/CacheDecayRequests32, other selected flags unchanged.
Each3prompts×1rep,64generated/63decode; only row tile knobs vary.
Exact hashce0fbb9a116d3d09, IDs/counters/config gates remain enabled.

075native row qualification passed all five modes, tiny hash1f7cd0eb14a22662,
IDs[28,48,106,84,28,48,106,84]×3. Binary/wrapper unchanged. Native9864,parent3504
exited; all reports/logs copied and SHA verified. Sourcequalify-row-retune.py,
commite6881951 (pushed). Controller refuses to start without074 formal and075
qualification reports. Capture each full trial after its PID/lifetime exits:
`python3 /private/tmp/capture-inkling-trial.py 076 076-rows-2-4 2208 1789374854.695914`
Future3-repeat capture uses`--repetitions3`. Helper checks exact grid/IDs/full
shape/hash; copies and SHA checks reports, log, traces and whole-line sampler
snapshot; archives gzip plus layer/phase-resource analyses. Outputdir
/private/tmp/inkling-STEM-artifacts. Do not overwrite immutable snapshots.

After row sweep, select best candidate and continue. **084 compressed-read
component probe is STAGED AND WAITING.** NativePython**3204**,parent**10144**,
state`compressed-read-probe-state.json`, output084-compressed-read-probe.json/.log.
Source`compressed-read-probe.py`, commit1b3a0640(pushed);
local byte/error/context-reuse canary and failure-drain check pass; see084_probe_local_validation.json. PTL already has
C:/msys64/mingw64/bin/libzstd.dll and zstd.EXE, plus include/zstd.h; nativePython
3.11.9 has no zstandard package. Repo has no zstd dependency. Probe pins existingDLLSHA b95c223a9548a9ecf51377c962e0bc8f0c51eb0c6f67a296dbc885996f0dd40d,version1.5.7; usesctypes, separate decompression contexts/preallocated buffers, original
uncached read vs temporary padded compressed uncached read+decompression,
matched cohorts/balanced order/exact bytes. Wait until080/full processes exit;
never overlap component benchmark with full trial. No runtime compression code.

## Evidence and remaining experiments

071defaultdecay4096 onepass0.9193077063;072decay32 onepass0.9370410437.
Allthree prompts improved1.48–2.11%; reads3.116%lower. Report072comparison.
074 repeated score0.938274 is the selected profile; record details above.
064–068workers16/8/12/24/32 select16; scores.917566/.884640/.901151/.869538/.858327.
069async75cohorts and073matched30pairs passed all bytes/error canaries but show
no consistent gain. Defer async/chunked runtime. Both exited; artifacts verified.
081 causal prefill-cache seeding removes only0.610%remaining reads at8slots/32;
history-only0.053%. Defer runtime prefill admission. All simulator controls match.
082 shorterdecays4/8/16/32 have139809/128331/123825/123493 misses over9samples;
32 remains best, so no extra short-decay full tests needed.
083 source-host compressibility probe:18experts across6layers, Zstd1 ratio.874644,
Zstd3 .868844.36byte-exact decompressions. Compressed bytes stayed in memory;
no model export or files written. Report083_source_compressibility.json. Miner
onlyread existing /mnt/external_ssd/inkling/out; no Lambda used. Need084 PTL
read+decompression comparison before treating13%bytesaved as a speed gain.
Current scratch pool already global/capped256MiB; no per-layer consolidation.

Sampler3036(shim9352,parent10880) ACTIVE,048-host-resources.jsonl,
stopmarkerstop-048-sampler,12h expiry~18:13UTC. Do not stop while loopcontinues.
Resource analyzer uses only whole adjacent intervals within exact phasewindows.
Process thread totals include other runtime threads; do not assertRayon+1.
Selected flags:16workers,BF16rows2,int4rows4,Reads0,MmapEmbed1,Reuse1,SkipBulk1,
OwnShared1,Uncached1,Pipeline1,cache256perlayer,PrefillReads1,historyreset1,decay32,
Highpriority,affinity65535. Actual cache16.3096GB,ownedshared4.0769GB.
All runtime flags opt-in. Cache-decay native qualification242tests+five modes+
productionwrapper passed; preserve all frozen olderbinaries.

No new export or Lambda rental required. Preserve OVMS6728/node8356/CA6344 and
other agents' worktrees. Commit AND push as Tate Berenbaum
<t8@users.noreply.github.com>, no coauthor trailers. Branchperf/inkling-panther-autolab,
worktree/private/tmp/tahoma-inkling-panther-autolab. Historical details below.

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
