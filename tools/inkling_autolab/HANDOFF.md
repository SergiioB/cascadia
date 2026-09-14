# Inkling / Panther Lake Autolab restart handoff

Updated 2026-09-14 00:18 UTC. Target is **25 decode tok/s for large975B Inkling on ONE
PTL machine**, not a component rate, aggregate throughput or remote inference.
**Target has not been reached.** Continue in this session autonomously.

## Ownership and locations

- Our worktree: `/private/tmp/tahoma-inkling-panther-autolab`.
- Branch: `perf/inkling-panther-autolab`, pushed through `47867911` before this
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

Current live state (2026-09-14 00:18 UTC; refresh before any action):

- **040_full_owned_shared_diagnostics is RUNNING**, controller session69544,
  log`/private/tmp/inkling-full-owned-shared-campaign.log`.
- Full-owned-shared.exe SHA0bd35a624e3fb7e5f0b78bfdf4202f548095ebb90b6f71137bb8d9683b7b96cb.
- Three cases x1 repetition,63 decode steps each; same036 knobs plusOwnShared1.
  Expectedfullhashce0fbb9a116d3d09 and actual owned bytes4076863488.
  Native`040-owned-shared*.json` and`.log`. SSH keepalives enabled.
- **036 completed and independently verified**: nine samples, slowest
  **0.1969341563127117tok/s**,45.52% over baseline; range0.196934–0.200669.
  Exact reference IDs and full-logits hash match. Median attention0.368731,
  MLP4.628557,outside-layers0.024826seconds/token. Target25 remains unmet.
- The036 native process9472 and wrappers exited, but its original SSH client
  did not return. Closed exact local SSH23331 after copying native artifacts.
  Autolab036 transport failure is retained; do not rerun it or rewrite history.
  **036_completed_artifact_verification.json** records verified actual results.
- Native038 uncached probe COMPLETE: cached38.7819ms vsuncached31.7165ms per
  255MB =1.2228x read throughput, all96 expert SHAs/canaries pass. No full gain.
- Native039 shared-storage qualification COMPLETE:229 tests plus plain/owned
  and production wrapper fixtures allhash1f7cd0eb14a22662,ownedbytes0/20736.
- Sampler4208,parent1420 remains active with`host-trials-resources.jsonl`,
  six-hour limit from22:38 UTC, stop marker`stop-trials-sampler`.
- No other native task build/probe active. Prepare uncached-read code locally
  while040 runs; no native build until it ends. Preserve all frozen binaries.

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

Finish040 and assess actual owned bytes, reference hash/IDs, layer timings and
memory. Prepare opt-in uncached reads from038 evidence with safe aligned scratch
and cached fallback; native qualification must wait for040. Reconfirm a winning
full configuration with >=3 repetitions before reporting a new repeated record.
Stop the sampler with its marker when the campaign sequence ends. No new export
or A100 job is needed. Do not stop protected services.

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


## Queued uncached production candidate41

Opt-inCASCADIA_INKLING_UNCACHED_READS requires ReuseBuffers1/Reads0. Aligned
padded Vec slices; cached full-read retry on unsupported input/I/O. No new
unsafe Rust; ordinary private memory, not physical pinning.229 local tests plus
six focused checks pass; fixturehash5122e042f9b1fb30. Native tests pending.

Four source SHAs checked/deployed. **Qualifier parent8796** waits for040 final
verified3samples/ownedbytes and no activefull. Stateuncached-qualification-state.json,
loguncached-qualification.log; futurefull-uncached.exe. Build/tests once, preserve
all four frozen binaries, then SHA-checked staged wrapper installation. Do NOT
start another full trial/build until it is terminal. Source archive/manifest
/private/tmp/inkling-uncached-source.{tar,json}, nativeuncached-source.*.

Prepared042_full_uncached_diagnostics is NOT launched; same040 profile plus
UncachedReads1, threecases/one repetition. Gates require ownedbytes4076863488,
full model,mapped embedding,actualuncached_read_effective1 andfallbacks0.
After native qualification, validate production wrapper fixture, then run042.
040 nativePID11216,created1789345010.6515927. Firstwatercase0.2373318713tok/s,
remaining cases pending. Keep036 as verified repeated record until reconfirmation.


## Local-only pipeline candidate43

CASCADIA_INKLING_PIPELINE_READS overlaps each expert's read with its compute,
requires parallel experts/reusable buffers, keeps indexed gate order.221 local
tests plus five fixture modes pass hash5122e042f9b1fb30; actual pipeline counts
0/63off/on and0 under each escape hatch. Native/full validation pending.
**NOT deployed or queued.** Native041 still uses staged06bc834f uncached source
and wrapper. After042 results, decide its cached/uncached setting before native
pipeline qualification; preserve full-uncached.exe and prior frozen binaries.
