# Inkling / Panther Lake Autolab restart handoff

Updated 2026-09-14 08:19 UTC. User resumed autonomous optimization.
Work is ACTIVE. Do not stop after a finite campaign. Target 25 tok/s is unmet.

## Active work

**074_full_cache_confirmation RUNNING**, local tool session **54245**.
Native **full-cache-decay.exe PID 6112**, created **1789373844.4969847**.
Controller log `/private/tmp/inkling-074_full_cache_confirmation.log`.
Native outputs `074-cache-confirmation.json/.log/-routes.json/-layers.json`.
Three prompts × three repetitions; 64 generated / 63 decode tokens each.
Settings: 16 workers, BF16 rows2, int4 rows4, Reads0, Reuse1, SkipBulk1,
OwnShared1, MmapEmbed1, Uncached1, Pipeline1, cache256 MiB PER MoE layer,
PrefillReads1, CacheResetHistory1, CacheDecayRequests32, High priority,
affinity65535. Binary SHA3874c863852b036757069bbac207a473481dd5408c854c037c7a2a72f6a431e8,
source6b820e83. No new runtime changes before confirmation.

Expected actual nine-sample counters are in campaign074, predicted causally
from verified046 routes in070: hits94235/misses123493, admissions25801,
evictions25289, frequency decays6336, history resets576, pipeline36288,
prefill expert visits40905, prefill uncached1302844538880B, retained16309550592B,
capacity17179869184B, owned shared4076863488B, zero uncached fallbacks.
Require full hashce0fbb9a116d3d09 and exact saved baseline IDs in all nine samples.

Capture after native process exits:
`python3 /private/tmp/capture-inkling-trial.py 074 074-cache-confirmation 6112 1789373844.4969847 --repetitions 3`
It checks PID AND creation lifetime, Cartesian case/repetition coverage, IDs,
full dimensions/hash, and SHA-checks copied logs/traces/resource snapshot.
Then write formal verification, update PERFORMANCE.md and ptl-profile.ps1.
Continue with further optimization; prepared next hypothesis is to retest
existing BF16/int4 row tiling under the new cache/prefill profile. Qualify the
frozen binary on native tiny fixtures before full trials, after074 exits.

## Latest completed evidence

071 default decay4096: **0.9193077063** tok/s slowest, rates0.960814/0.919308/0.943939.
072 decay32: **0.9370410437** tok/s slowest, rates0.975015/0.937041/0.963865.
Each one pass. Same outputs/hash/routes; all actual counters pass. Decay32 reads
3.116% fewer routed bytes and improves every prompt1.48–2.11%. Selected for074.
All raw artifacts, SHA manifests, layer and resource profiles archived.
`072_cache_decay_comparison.json` records the matched comparison.
Bestsingle-pass0.937041; formal repeated record remains0460.5679137350 until074.

064–068 worker sweep complete:16=.917566,8=.884640,12=.901151,24=.869538,
32=.858327. Select16. Same cache/read/route counters; all artifacts archived.
069 async component75 cohorts/300 files passed bytes and error canary.
073 matched follow-up30 pairs (10 each2/4/6 files), balanced AB/BA, passed all
SHA checks; actualPython2520 and parent2460 exited. Async wins5/10 eachsize,
median paired speedups1.001/1.108/.875 with strong order effects at4/6 files.
No consistent benefit: defer runtime async/chunked reads. Reports073-* and
073_artifact_verification.json; copied bytes match native SHA exactly.
Controller51214 for071/072 exited normally; push11420395 completed.

Sampler **3036** remains ACTIVE (shim9352,parent10880), follows trial PIDs,
`048-host-resources.jsonl`, stopmarker`stop-048-sampler`, expires~18:13UTC.
Do not stop it while the loop continues. Capturehelper accepts --repetitions3.
Layer diagnostics use actual phase timestamps; resource analyzer ignores
intervals crossing phase boundaries. Process thread totals include non-Rayon
threads; do not assert total=Rayon+1. Configured thread count remains gated.

Current scratch pool is already process-wide and capped at256MiB; per-layer
scratch consolidation offers no gain. Current cache, reset, prefill, decay
features are opt-in and native qualified.242 native tests and five tiny modes
plus production-wrapper oracle passed for frozen cache-decay binary.

No new export or Lambda rental is needed. Preserve protected services and
other agents' worktrees. Commit AND push as Tate Berenbaum
<t8@users.noreply.github.com>, no coauthor trailers. Current branch
perf/inkling-panther-autolab in /private/tmp/tahoma-inkling-panther-autolab.
Canonical history and earlier details follow; the active state above takes precedence.

## Verified outcome

Final campaign046: **0.5679137350 decode tok/s**, slowest of nine samples;
median0.5837513204, fastest0.5938149418. This is **4.196×** the original repeated
baseline0.1353339381. Three prompts × three repetitions, 64 generated tokens
with63 decode steps each. All saved greedy IDs and full-logits hash
**ce0fbb9a116d3d09** match. Autolab returned normally and passed all gates.
Full CPU backend, all66 layers; this is not an Arc B390 or component rate.

See **PERFORMANCE.md**, results/046_final_verification.json,
046_full_final_confirmation.json, 046_final_layer_profile.json,
046_final_resources.json and 046_final_host_state.json. Raw traces/resources
are compressed with source/compressed SHA manifests. Stable originals:
`/private/tmp/inkling-full-final-artifacts` and native task root046-final*.
The ignored tools/inkling_autolab/.autolab/state.json reports verified/full
checkpoint available/targetfalse. Local results.db contains campaign history.

All576 final case/repetition/layer route arrays match034, including prefill.
The current packed export requires32.5–42.5GB/s at25tok/s even with an ideal
initial cache using ALL nominal64GiB RAM and ignoring other memory/compute.
The observed PCIe5x4 SSD link ceiling is15.754GB/s before protocol overhead.
See037_full_span_traffic_bound.json,047_all_RAM_traffic_bound.json and
046_route_identity.json. This rules out ordinary tuning to25 for this export,
SSD and workload. It does NOT prove mathematical optimality of0.568tok/s or
rule out gains from a different representation/backend/hardware. No new compression or full GPU backend has been implemented; an optional
routed cache is now under evaluation in the resumed loop.

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
