# Inkling / Panther Lake Autolab restart handoff

Updated 2026-09-13. Target is **25 decode tok/s for large975B Inkling on ONE
PTL machine**, not a component rate, aggregate throughput or remote inference.
**Target has not been reached.** Continue in this session autonomously.

## Ownership and locations

- Our worktree: `/private/tmp/tahoma-inkling-panther-autolab`.
- Branch: `perf/inkling-panther-autolab`, pushed through `3576be3f` before this
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

Current state (refresh native processes before any new benchmark):

- Baseline queue3856/full-decode7340 and sampler2208 have ended.
- Native mapped qualification7892 ended successfully:216 MSVC tests passed.
- Buffer reuse probe completed30 byte-verified samples. No production pool yet.
- First diagnostic campaign034 is being launched; see `.autolab/state.json`
  and controller log `/private/tmp/inkling-full-direct-campaign.log`.
- New bounded sampler uses `host-trials-resources.jsonl`, follow-trials mode,
 6 hours, stop marker `stop-trials-sampler`. Sampler4208,parent1420.
  Full trial PID5044,created1789339116.8486328; controller tool session87212.

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
head remains resident. No full-model memory/speed result yet.217 local tests
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

## Next full trials

`campaigns/034_full_direct_diagnostics.yaml` tests direct mapped execution,
rows1/1, embedding mapping off. Same three reference cases,64 tokens,1 rep;
expected full hashce0fbb9a116d3d09. Routing, layer timings, result and persistent
stdout log use034-direct* under the native root. One rep is diagnostic and
cannot satisfy the3-repetition target. Timeout3600s. Autolab runner saves
portable results and rejects hash/ID failures. Only one campaign at a time.

`compare-full.ps1` uses the same qualified binary for baseline(reads0/rows1/1),
direct(reads1/rows1/1), tiles(reads1/rows2/4), mapped(tiles+mapped embedding).
All four fixture wrapper arms passed. Optional -Log refuses existing logs,
saves native progress and replays stdout for Autolab metric parsing.

When034 ends, copy JSON/routes/layers, analyze via analyze-routing.py and
analyze-layer-profile.py --require-full, then choose the next candidate from
measured bottlenecks. Do not invent cache/speculative speedups. Confirm the
winning candidate over3 reps before promoting a full record. Stop the sampler
by creating its marker when the campaign sequence ends; it never stops jobs.
No Lambda/new export needed for current tests. Target remains unmet.

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

## Read-buffer candidate under preparation

Local opt-in CASCADIA_INKLING_REUSE_READ_BUFFERS and
CASCADIA_INKLING_SKIP_BULK_PREFETCH prepared while034 runs. Pool caches only
allocations, never expert contents, capped256MiB idle process-wide. Defaults
remainoff. Direct-mapped execution takes precedence; prefill unchanged.
218 local tests passed plus byte/greedy/full-logits fixture checks. Test results
and source in035. Native **full-read-buffers.exe NOT YET BUILT/QUALIFIED**;
`test-read-buffers.bat` is prepared. No competing native build during034.
After034 ends, deploy/build/qualify then measure only if bottlenecks justify it.
