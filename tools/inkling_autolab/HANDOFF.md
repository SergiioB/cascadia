# Inkling / Panther Lake Autolab restart handoff

Updated 2026-09-14 00:55 UTC. Target is **25 decode tok/s for large975B Inkling on ONE
PTL machine**, not a component rate, aggregate throughput or remote inference.
**Target has not been reached.** Continue in this session autonomously.

## Ownership and locations

- Our worktree: `/private/tmp/tahoma-inkling-panther-autolab`.
- Branch: `perf/inkling-panther-autolab`, pushed through `12c19a3e` before this
  handoff refresh; run `git log -1` for the current commit.
- Origin: https://github.com/labscommunity/cascadia.git.
- Author AND committer: `Tate Berenbaum <t8@users.noreply.github.com>`.
  User expressly requested commit/push and **no coauthor trailers**.
- Original agent's worktree: `/Users/tatef/Workspaces/tahoma-inkling`,
  `feat/inkling`, unchanged `9aaebff0`, PR154. Leave it alone.
- Main checkout: `/Users/tatef/Workspaces/tahoma`, `perf/prefill-layer-streaming`.
  Its dirty glm5_run.rs / untracked ngram_sim.rs belong to other work. Untouched.
- Autolab: `/Users/tatef/Workspaces/autolab`, 3993e2c4. Pre-existing dirty
  `src/autolab/runners/ssh.py` is unrelated and untouched.
- Controller Python: `/private/tmp/inkling-autolab-venv/bin/python` (editable
  Autolab + pytest). Main ignored pointer: `tmp/INKLING_AUTOLAB_HANDOFF.md`.
- Research-loop skill was read from sibling Autolab plugin and applied.
  Record hypotheses/results in JOURNAL.md; no separate Claude process required.
- No AGENTS.md found. rg shim hangs; use git grep/git ls-files/bounded Python.
  Permissions unrestricted, approval never; never pass sandbox_permissions.
  Latest developer disallows delegation unless explicitly requested. No agents spawned.

## SSH and host rules

`inkling-ptl-direct`: devcloud@192.168.22.2 via guest@192.55.48.214, cascadia key
`~/.ssh/cascadia_ed25519` for both hops. User authorized this direct route.
Fallback `cascadia-tate-07-ts`: devcloud@100.82.253.76, `~/.ssh/id_ed25519`.
Actual host: pdx88-pa0794, Windows 11 Pro, Core Ultra X7 358H, Arc B390,
16 cores/threads, 64 GB RAM. WMI reports LPDDR5X 8533. High performance power
scheme is already active. Disk: SAMSUNG MZVLC1T0HFLU-00BT7, ~1 TB.

PTL task root **C:\Users\devcloud\inkling-autolab**. Existing services are
protected: **OVMS6728, node8356, CA6344**. Do not stop them or broad-kill Python,
Cargo or inference processes. One full benchmark/native build at a time.

Remote default shell is PowerShell. Reliable complex Python: local
`subprocess.run(['ssh','-o','BatchMode=yes','inkling-ptl-direct',
'C:/Users/devcloud/venvs/qwen38/Scripts/python.exe -'], input=script, text=True)`.
For complex PS use UTF-16LE base64 `powershell -NoProfile -EncodedCommand`.
Set `$ProgressPreference='SilentlyContinue'` to avoid CLIXML noise. SCP paths
use `inkling-ptl-direct:C:/Users/devcloud/...`. Detached native jobs use
Win32_Process.Create with a task .cmd launcher, whose redirection saves logs.
Never print or copy private keys/tokens.

## Complete export and current live jobs

All **16,654 files / 548,985,140,942 B (549 GB /511.3 GiB)** are source/destination
SHA-256 verified on PTL, errors []. Model path: task root `model`.
`model-ready.json` SHA256:
`9e7f11b6131131e8c3db879a814e121cd6a4fde9c6987fa6de7e86a80cb46a20`.
Free disk after deployment: 276,129,026,048 B. Prior cleanup reclaimed ~822 GB.
Source remains independently at **miner:/mnt/external_ssd/inkling/out**.
Miner SSH: tatef@192.168.0.235:1990, cascadia key.

**All transfer clients, source servers and tunnel supervisors ended.** Do not
restart archived transfers. Four retired task tokens were removed; all six
controller/source/target token paths are absent (report031). Eight direct-jump
transports reached103.70 MB/s
versus2.67 MB/s old DERP. Historical details are in DEPLOYMENT_HISTORY.md and
JOURNAL.md; they are NOT current instructions.

Current live state (2026-09-14 00:55 UTC; refresh before any action):

- **044_full_pipeline_control RUNNING**, followed automatically by
  **045_full_pipeline_overlap** only if044 exits successfully. One shell tool
  session **20333** owns this sequential pair. Do NOT launch045 separately.
- Controller logs`/private/tmp/inkling-full-pipeline-control.log` and
  `/private/tmp/inkling-full-pipeline-overlap.log` (second created when it starts).
  Native044-pipeline-control* and045-pipeline-overlap* hold logs/JSON/traces.
- Both use **full-pipeline.exe**, SHA
  **8305491ebbc4bacc09fdb3aeccbe331b153e0fd79d34a273baef2ddb5d593e8b**,
  source18f8becb. Three cases x1rep,63 decode steps each. Samebinarycomparison.
- Both: Reads0,Rows2/4,Mmap1,Reuse1,SkipPrefetch1,OwnShared1,UncachedReads1.
  PipelineReads0control/1overlap. Gatesfullhashce0fbb9a116d3d09,owned4076863488,
  actualuncached_effective1/fallbacks0,actualpipeline layer count0/12096.
- **042 completed/Autolabverified:** slowest **0.5151766081427948tok/s** over
  3cases1rep; rates0.536215/0.533069/0.515177. Exact tokens/logits.2.184x040,
  3.807xoriginalbaseline. Actualuncached bytes2208959299584,fallbacks0.
  This is SINGLE-PASS; repeated record remains036 until final confirmation.
- **Repeated record036:0.1969341563127117tok/s**,9samples,45.52% overbaseline.
  Exact IDs/hash. Original SSH client stayed open after native/wrapper exit;
  closed exact local23331, kept Autolab transport failure. Complete native
  artifacts independently verified in036_completed_artifact_verification.json.
- **043 pipeline qualification COMPLETE:**233 native tests, three fixture modes
  and production wrapper preserve1f7cd0eb14a22662. Pipelinecounts0/63off/on.
  All five earlier frozen binaries unchanged. Qualifier5952,parent9672 ended.
- **041 uncached qualification COMPLETE:**233 native tests inclactualaligned
  byte/kernel canaries. Tiny fixture uses cached fallback for unaligned bins.
  full-uncached.exe SHA9aa189f74b797679d91603fc6d3dfd34dc6ad3bde94ebdae95ef5526b58e81a2.
- Sampler4208,parent1420 active;host-trials-resources.jsonl, six-hour limit from
  22:38UTC,stopmarkerstop-trials-sampler. Stop when campaign sequence ends.
- Target25 remains unmet; current export/workload/SSD bandwidth bound rules out
  ordinary tuning to25. Continue useful measured improvements without false wins.

## Baseline and qualified candidates

Full baseline: **0.13533393807754676 tok/s**, the slowest of nine samples,
three prompts x three repetitions,63 decode steps each. Hash
**ce0fbb9a116d3d09**; repeated logits and greedy IDs match. All three generated
texts reviewed and coherent; fixed64-token cap truncates longer responses.
Initial baseline has no supplied reference IDs, so correctness_verified=false;
subsequent candidates must match its saved IDs and full-logits hash.
Artifacts033 are copied locally; native reference:
`large-cases.baseline-reference.json`. Frozen full-decode.exe SHA:
`f0bf021af04edd76f6fec5b77d8571225ba38f8f2315cbaac2bed189c04fc77a`.
Baseline reads0, rows1/1, unmapped embedding, Rayon16, affinity65535, High.
Load29.913s. Smoke was only0.109008tok/s over3 steps, not the long record.

New **full-mmap-embed.exe** qualified with216 native tests and all8 HF greedy
IDs x3 repetitions; fixture hash1f7cd0eb14a22662 in all four wrapper arms.
SHA **95f664c6a4af52f5dcdaf5fe6d12886cb45c6bb70edecb79a65d8b52daf5ec6d**.
Mapped embedding is opt-in/defaultoff. It avoids the private ~2.47GB copy;
head remains resident. Full results are in036 for the combined settings.217 local tests
passed separately (ARM fixture hash5122e042f9b1fb30).

Resource baseline window(result028): ~5.29 CPU core-equivalents,84.7% kernel,
2.108GB/s machine disk reads,518k process faults/s including soft faults;
RAM available briefly7.58MB. Machine I/O is not exclusively attributed to model.
Do not stop protected services to free RAM.

Buffer probe030: fresh reads36.872ms versus reused33.714ms for255MB batches,
~9.4% throughput improvement; process faults62,390.5 versus53 median. Both
read~253.755MB from machine disk. Setup46.930ms separately; no full inference
speedup established. Fresh+prefetch48.550ms, reused+prefetch43.566ms,
prefetch+mapped-copy55.973ms. Conditions differ from transfer-active023/024.

## Full diagnostic findings and next decisions

034 passed all three cases with exact reference IDs and full logits hash.
Rates0.158070,0.154189,0.163196 tok/s; the slowest is13.93% above the repeated
baseline's slowest rate, but034 itself has only one repetition.
Median seconds/token: attention0.673545,MLP5.567433,outside layers0.085328,
wall6.326305. About88% in MLP; outside layers is not head-only.

Actual routed-expert working set12.231GB/token;32-token unions114–133GB.
Global whole-expert LRU8GiB simulates zero hits;12–16GiB misses7.08–7.78GB/token.
These are cache models, not measured physical I/O or inference speedups.
Raw traces are committed as034-direct-{routes,layers}.json.gz, with source and
compressed SHA hashes in034_trace_artifacts.json. Original JSON copies remain
under `/private/tmp/inkling-full-direct-artifacts` and on PTL. Layer/routing
analysis reports are committed. Run analyzers on decompressed JSON.

036 measures combined reusable reads, omitted bulk-read hints, row tiles and
mapped embedding over three repetitions. All220 Windows tests and all four
fixture modes plus the production wrapper passed beforehand. Candidate SHA:
**497b4bc83802bb7a21ced260e68cad49353ba5b78f851b4bf982a5c9360ca861**.
Source revisionffa23e6f; both previous frozen binaries remain unchanged.

036 final artifacts are under`/private/tmp/inkling-full-buffered-artifacts`
and committed results036, including gzip traces/resources with SHA manifest.
Resource lifetime includes prefill/load: private peak22.078GB vs24.536GBbaseline,
faults107292/s vs494348/s, minimum availableRAM819200B,swap peak14.551GB. This
shows transient pressure remains despite low decode faults. Machine-wide disk
2.940GB/s is not exclusively attributable to model. Resource analyzer exactly
reproduces the prior033 baseline aggregates and keys on PID+creation time.

040 artifacts under`/private/tmp/inkling-full-owned-shared-artifacts` and
committed040 results. Medianattention0.388156,MLP3.800657,outside0.024941s/token.
Private peak26.093GB,minavailable188MB,swap peak16.092GB; lifetimefaults126252/s
include prefill/soft faults. Decode gains despite additional private memory.

042 artifacts under`/private/tmp/inkling-full-uncached-artifacts` andresults042,
including raw compressed traces/resources with SHAmanifest. Medianattention
0.363591,MLP1.495291,outside0.025032s/token. Privatepeak26.093GB; sampled lifetime
kernel41.82%,machine reads4.320GB/s,minimumavailable70.6MB,swappeak16.491GB.
Lifetimefaults199889/s include prefills/softfaults; fasterdecode changes their
share, so don't compare as decode-only fault rates. Uncached11.6876GB/token,
4.44% of routed selections computed from mappings; notphysical cache-hit rate.

Let044 then045 finish and compare full rates/layer timings/resources. Choose
winning full profile and run a final3repetitions across3cases before reporting a
new repeated record. No046 final campaign exists yet. No native build/probe
queued. No new export/A100 job needed. Do not stop protected services.

Earlier resident knobs improve component rates only. Prefetch parallel/batched
variants lost (023); serial-hint mapped copy beat allocating buffered reads
(024). N-gram prefix-only analysis of the three short baseline continuations
(029) yields at most1.016x optimistic call reduction with1.40–3.51x verification
rows; n>=2 accepts no drafts. Defer that drafter here, not a conclusion about
other draft models or longer/repetitive workloads.

Current layout traffic is~36.5GB/token.25tok/s would require~0.91TB/s unless
weights are reused across tokens; do not imply ordinary kernel tuning proves
this feasible. See docs/perf/INKLING_SCALING.md. Shared experts4.077GB,
routed expert31,850,496B ×16,384, fixed nonexpert files23.042GB. File sizes are
not actual resident-memory or measured per-token traffic.

## A100 rental and export cost

All future exports must use user-designated **ubuntu@129.146.170.51**,8xA100
SXM4-40GB. SSH aliasinkling-export, key`~/.ssh/amx-bench_ed25519`.
Provider **Lambda.ai**, user confirmed **no attached persistent filesystem**.
All GPU test jobs ended; no raw checkpoint was downloaded. Source config only
2,415B; exports empty. Current PTL tests need no rental/new export.

**Export work is ready for rental release.** Verified controller backup:
`/Users/tatef/Workspaces/inkling-export-backups/20260913/inkling-export-release-20260913.tar.gz`
345,278B, SHA743ebc8229913500e5eda01bea4994128503e7ea2eaf819cb633b913d7b2a5f2.
Includes deployed code, task logs, config, exact package freeze; extracted copy
under snapshot. Rebuild recipe/package lock/results are committed. See
**EXPORT_HOST.md** and027. No private keys copied.

No Lambda account/API access found, no instance termination performed or
explicitly authorized. User was told they can terminate129.146.170.51 in the
Lambda console now. Lambda requires termination to stop billing; guest
shutdown still bills, suspend unsupported, local disk is erased. Do not claim
billing stopped. https://docs.lambda.ai/public-cloud/on-demand/creating-managing-instances/

Default export-remote.py profile: cuda:all,8 processes,1 worker,64MiBchunks,
host-local flock; full source required for multiprocess mode, source retained.
Pass --processes1 for original streaming/partial modes.48 GPU/exporter tests
passed;64 production-sized synthetic experts, all CPU-byte-exact9 samples.
Eight-process median58.980 experts/s,2.60x prior GPU pool; scaled expert stage
4.67min/$1.17. Full export budget15–30min/$4–8 with source local; first1.905TB
source download+export2–3h/$30–45. **Extrapolations, not timed full exports.**
Cross-batch per-expert4.62x minerCUDA/10.93x minerCPU is not matched full speedup.
Fresh549GB PTL delivery at103.7MB/s adds~88min/~$22 if rental serves it; rental
route unmeasured. Current model is already on PTL and has no such dependency.

## Reusable-buffer implementation

CASCADIA_INKLING_REUSE_READ_BUFFERS and CASCADIA_INKLING_SKIP_BULK_PREFETCH
are opt-in/defaultoff. Pool retains allocations, not expert contents, capped at
256MiB idle process-wide. Leases own buffers across Rayon I/O/compute; the mutex
is not held during either. Full successful reads overwrite all bytes; errors
cannot expose stale contents. Direct mapped execution takes precedence and
prefill retains its prior hints.218 local tests and220 MSVC tests passed.
Native full-read-buffers.exe is QUALIFIED and completed036.

## Cache analysis and target limit

037 causal cache models and offline bounds are saved; eight tests pass, including
an exhaustive tiny optimal-paging oracle. Best tested8GiB policies simulate
7.96–8.77GB routed reads/token. This is not evidence that adding private cache
outperforms the OS cache. Extra private storage competes with fixed weights,
scratch and protected services.

037_full_span_traffic_bound.json allows perfect reuse across all63 continuation
positions regardless of execution order. With optimistic initial32GiB routed
cache,25tok/s still requires46–56GB/s. Native NVMe PCIe5x4 properties imply
15.754GB/s maximum before packet overhead. Disk-only ceilings8.54/7.01/7.55tok/s
exclude all compute/fixed/shared/draft work. This applies to the current packed
representation/workloads/SSD, not hypothetical new compression. User was told
25tok/s is not attainable through ordinary tuning of this export on this SSD.

## Owned shared expert implementation

CASCADIA_INKLING_OWN_SHARED=1 retains just the shared expert bins as owned packed
int4 bytes (4.077GB full model), using the same kernel/arithmetic. Routed experts
and default behavior are unchanged.227 local tests and229 native tests pass.
Fixturehash5122e042f9b1fb30 on ARMdebug,1f7cd0eb14a22662 on MSVCrelease; do not
mix architectures. Actual owned bytes0/20736 for tiny fixture. This is not
physical page locking; its full memory/performance tradeoff is measured by040.
Controller expected_metrics gates ensure the candidate is actually enabled.


## Uncached and pipeline implementation

Opt-inCASCADIA_INKLING_UNCACHED_READS requires ReuseBuffers1/Reads0. Aligned
padded Vec slices; complete cached retry on unsupported input/I/O. No new unsafe
Rust or physical pinning. File lengths checked before/after direct I/O. Counters
report actual completed uncached bytes and all fallback attempts.229 local tests
plus six focused buffer checks and233 native tests pass. Fixturehash5122e042f9b1fb30
on ARMdebug and1f7cd0eb14a22662 onMSVCrelease. Do not mix architectures.
Native aligned byte and actual int4 kernel canaries pass; tiny fixture correctly
falls back because its bins are unaligned. Full042 validates actual uncached path.

CASCADIA_INKLING_PIPELINE_READS overlaps each expert's read with its compute,
requires parallel experts/reusable buffers, keeps indexed gate order.221 local
and233 native tests pass. Five local fixture modes preservehash5122e042f9b1fb30,
actual pipelinecounts0/63off/on and0 with reuse disabled,directmaps orserial.
Nativefixture modes/wrapper preserve1f7cd0eb14a22662 withcounts0/63. Qualified
full-pipeline.exe is now under matched full evaluation044/045. Archives
/private/tmp/inkling-pipeline-source.{tar,json};nativepipeline-source.*.

No native qualifier remains queued/running. Do NOT overlap anotherfull/build with
sequentialpair20333. After its completion, inspect both final artifacts and choose
best settings for a >=3rep final confirmation. Preserve all frozen binaries.


Update01:08UTC:044 completed/Autolabverified,slowest0.5377145739tok/s across3cases,
actualpipelinecount0,uncachedbytes2154558652416,fallbacks0. **045 is nowRUNNING**
under the same sequentialtool20333,nativePID2368,created1789348029.3876903.
Do not launch045 again. Control artifacts copied to/private/tmp/inkling-full-
pipeline-control-artifacts. After045 choosewinner,prepare046final3repetitions.
034 versus042 route traces match all192case/layerpairs and108288 routedselections
includingprefill;037 cache/bandwidth analysis applies to the current routes.
