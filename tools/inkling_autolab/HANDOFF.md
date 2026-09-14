# Inkling / Panther Lake Autolab restart handoff

Updated 2026-09-14 07:38UTC. USER RESUMED AUTONOMOUS OPTIMIZATION. Work is ACTIVE;
do not stop after a completed campaign. The25tok/s target is unmet.

## Live update08:01UTC —068running

067workers24completed0.8695377030tok/s; allartifactsarchived,exactgatespass.
**068_full_threads_32 RUNNING**,native**8100**,created**1789372668.7833545**,
observed33threadsafterload;controller**67450**. Nootherfulltrialqueued.
069asyncprobe**10092**/parent10616iswaitingfor068completion; sampler3036active.
Do not startanynewfulltrialuntilprobeiscompleteorfailedanditsprocesshasexited.
Thenchooseworkers(overallbestcurrently16at0.9175664024),runqualifieddecay
control4096/candidate32,then3-repeatconfirmation. Keepoptimizingafterthat.

## Latest checkpoint —067running,069probe waiting

064controlcomplete0.9175664024;065workers8complete0.8846400902;
066workers12complete0.9011509229. Allrawdiagnosticsarchivedandverified.
**067_full_threads_24 ACTIVE**,native**5688**,created**1789372336.0766687**,
observed25threadsafterload. **068threads32queued**,controller**67450**.
Sampler3036continues. Current067partialresultmustnotbecommittedascomplete.

**069async-read-probe LAUNCHEDANDWAITING**,Python**10092**,parentcmd**10616**,
stateasync-read-probe-state.json,logasync-read-probe.log,output069-async-read-probe.json.
Itwaitsfor064–068/noactivefull,thenholdsbaselinequeue lockandrunstheread-only
component. Sourcecommit**ae35cd71**,probe/basefilesSHAcheckedbeforelaunch.
Do not duplicate it orstartthenextfulltrialuntilprobefinishes. Nativecanaryand
75cohortreadcomparisonarestillpending; nospeedgainclaimed. Filesoutsideactual
fullroutes; sync/asyncwhole/1MiB/4MiB/8MiB at2/4/6files,5blocks,allbytesSHAchecked.
Allbuffers/events/OVERLAPPEDstatespersistthroughcompletion/canceldrain.
Afterprobe: matchedqualifiedfull-cache-decay.exe4096/32usingbestworker,then
3-repeatconfirmation. Continuedruntimeworkifproberesultswarrantit.

Capturehelper nowaccepts**--repetitions 3** andvalidatesallcase/repetitionpairs;
default1preservescurrentcaptures. 070_repeated_cache_predictions.json uses
verified046nine-sampleroutes: cache256/historyreset1 has4096intervalhits90250,
misses127478,admissions12347,evictions11835;32intervalhits94235,misses123493,
admissions25801,evictions25289. For3reps:historyresets576,decays6336for32/0for4096,
prefillvisits40905,uncachedprefillB1302844538880,pipeline36288;
readbytes=misses*31850496,retained16309550592. Thesearegatepredictions,notspeed.

## Current live work — worker sweep064–068

064control COMPLETE0.9175664024; rawartifacts/SHA/profileverified.
**065_full_threads_8 RUNNING;066_full_threads_12,
067_full_threads_24,068_full_threads_32 QUEUED sequentially.**
Controller tool**67450**,script/private/tmp/run-inkling-thread-loop.py.
Logs/private/tmp/inkling-CAMPAIGN_NAME.log. Native065PID**3924**,
created**1789371668.766402**,observed9threadsafterload. Allusefrozen
full-prefill-reads.exe. Nativeoutputs064-threads-16.*,065-threads-8.*,
066-threads-12.*,067-threads-24.*,068-threads-32.*. Do not launchduplicates.

Selectedsettings: cache256MiBperlayer (16.3096GBactual),PrefillReads1,
CacheResetHistory1,Reads0,Reuse1,OwnShared1,Uncached1,Pipeline1,SkipBulk1,
MmapEmbed1,BF16Rows2,Int4Rows4,Highpriority,affinity65535. Onlyworkercountvaries;
fresh16controladdressesdrift. Eachtrial3prompts×1pass,64generated/63decode.
Allrequirefullhashce0fbb9a116d3d09,exactbaselineIDs,cachehits30058/misses42518,
admissions4141/evictions3629/historyresets192/retained16309550592,decodeuncachedB
1354219388928,pipeline12096,prefillvisits13635/uncached434281512960B,zero fallback.
Wrapperconfiguredrayon_threads isgated. Sampledprocess totals include extra
runtimethreads:064decodeobserved17and19, so doNOTgateexactlythreads+1.

**Best single-pass result064:0.9175664024tok/s**; previous0570.9157886929 (water0.931246,binary0.915789,
story0.941372). Repeatedrecord046remains0.5679137350 untilnew3-repeatverification.
053control0.586785→054streamedprefill0.709011 (+20.83%). Prefill103–108sec→24–25sec.
055historyreset64cache0.757562;056historyreset128cache0.813905;057history2560.915789.
AllIDs/logits/routesandactualcountersmatch. 057privatepeak42.500GB,minavailable
1.996GB,maxmachineswap0.508GB;decodefaults73/s. See054/055/057comparisonreports.
All053–057rawresults/traces/resource snapshotsarchivedandSHAverified.

**063nativecache-decayQUALIFIED**,242tests,fivefixturemodes+productionwrapper.
Newfrozenfull-cache-decay.exeSHA
3874c863852b036757069bbac207a473481dd5408c854c037c7a2a72f6a431e8,
source6b820e83. Alleightolderbinariespreserved. Qualifier1952,parent9604,
launcher8620ended. Report063_cache_decay_windows_validation.jsonandcompressedtestlog.
EnvCASCADIA_INKLING_CACHE_DECAY_REQUESTS takespowersoftwo4..65536,default4096;
invalidenginevaluesdefault4096,wrapperrejectsinvalid. Actualfrequency_decays
counterseparatefromhistoryresets. Nativewrapperwaspromotedafterqualification;
latestrepo run-full.ps1matchesit. 062local163tests+fivefixtures also pass.
Full-modeldecaygainNOTmeasured. ActiveworkersweepusesOLDfull-prefillbinary,
whoseintervalremains4096. Do not rerunnativequalification orrebuildfrozenbinaries.
Sourcearchive/private/tmp/inkling-cache-decay-source.tar/json2SHAguardedRustfiles;
nativebase72cb6f05,candidate6b820e83. Stagednativefilescache-decay-source.tar/json,
run-full-cache-decay.ps1,qualify-cache-decay.py/test-cache-decay.bat preserved.

Nextafterworkercomparison: choosebestworker;matchedfull-cache-decaybinary
control4096versus32,keepingcache256/historyreset1/prefill1. Prediction058at8slots:
4096hits30058,misses42518,admissions4141,evictions3629;32hits31383,misses41193,
admissions8629,evictions8117. Decay32shouldperform2112actualhalvings across3cases;
control4096zero. Readbytes=misses*31850496. Then3-repeatbest-profileconfirmation.
Continuewithfurthermeaningfuloptimization;do not stopjustbecausethequeuefinished.
060globalcachepredictionremovesonly1–2%misses/deferred.061naiveprefetchadds11–39%
reads/deferred. Thesearecausalreplays,notimplemented/measuredspeedgains.

Sampler3036/shim9352,parent10880 ACTIVE,048-host-resources.jsonl,
stopmarkerstop-048-sampler.12-hourlimitfrom06:13UTC (~18:13UTCexpiry).
Do not stopwhileloopcontinues. Capturehelper
/private/tmp/capture-inkling-trial.py NUMBER STEM PID CREATED
refusesactivePID+creation, snapshotswholelines, copies/SHAchecks nativefiles,
checksIDs/hash,archivesgzipandrunscorrectlayer+phaseanalysis. It currentlyexpects
3case/1pass;extendforfuture3-repeatverification. Native samplestimestampsseparate
prefill/decode, ratesusemonotonicInstant. analyze-host-resources.py --benchmark
usesonlycompleteadjacentintervalsinsidephases;21Python tests pass.
Completedartifacts/private/tmp/inkling-NNN-STEM-artifacts;last057is
/private/tmp/inkling-057-history-256-artifacts. 064alsoarchived/private/tmp/inkling-064-threads-16-artifacts. Active065notcapturedyet.

full-prefill-reads.exeSHA
bb44392b9a4d3f29b845e115c4e01a724477a374cc56de10043712509e5aaf82,
source72cb6f05. Native052241tests/sevenfixturemodes;059workerqualification
8/12/16/24/32 passed. full-expert-cache.exeSHA
fe913c6844813bfa48b380e886c477224b77b3462f5e0b4c752345f8b2f61e88,source049034de.
No Lambda/newexportrequired. Preserveprotectedservices/otherworktrees.
Originalfeat/inklinglastchecked06:32UTC unchanged9aaebff0.

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
