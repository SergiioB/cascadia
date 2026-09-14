# Inkling / Panther Lake Autolab restart handoff

Updated 2026-09-14: USER RESUMED AUTONOMOUS OPTIMIZATION. Work is active again;
the prior final campaign below is the completed reference, not a stopping point.

## Resumed iteration048 — expert cache

Cache048 QUALIFIED:238native tests, four fixture modes and productionwrapper
pass hash1f7cd0eb14a22662,110cachehits. Binaryfull-expert-cache.exe SHA
fe913c6844813bfa48b380e886c477224b77b3462f5e0b4c752345f8b2f61e88,
source049034de. Qualifier10336/test8168/parent1452 ended. All six older binaries
preserved. Evidence048_expert_cache_windows_validation.json.

**049cache0 -> 050cache64MiB/layer -> 051cache128MiB/layer RUNNING sequentially**
under local tool73582. Logs/private/tmp/inkling-049_full_expert_cache_control.log,
/private/tmp/inkling-050_full_expert_cache_64mib.log,
/private/tmp/inkling-051_full_expert_cache_128mib.log. Do not launch duplicates.
Native outputs049-cache-0.*,050-cache-64.*,051-cache-128.*. Sampler
048-host-resources.jsonl,stopmarkerstop-048-sampler,12-hour limit from~06:14UTC.

Continue analyzing and optimizing after this comparison; 25tok/s bandwidth
constraint does not mean0.568tok/s is maximized. No Lambda/newexport work needed.
Questionq49 prefill streaming is being prepared LOCALLY while cache trials run;
do not deploy/build it onPTL until the current three trials finish. Questions
q48–q51 track cache, prefill, read concurrency and causal next-layer prefetch.
User expects continued work; no stopping after a single completed campaign.

Prefill prototype now passes236distinct local tests plus eight fixture modes.
Native source archiveprefill-read-source.tar/json andqualify-prefill-reads.py,
test-prefill-reads.bat,run-full-prefill-reads.ps1 are STAGED ONLY. QualifierNOT
launched. It guards completed049/050/051, all seven frozen binaries and previous
source/wrapperSHAs. Newcandidatefull-prefill-reads.exe does not yet exist.
Do not overlap its build with current full trials; choose cache setting first.

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
rule out gains from a different representation/backend/hardware. No explicit
routed cache, new compression or full GPU backend has been implemented.

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
