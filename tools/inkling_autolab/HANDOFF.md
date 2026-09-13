# Inkling / Panther Lake Autolab restart handoff

Updated 2026-09-13. Target is **25 decode tok/s for large975B Inkling on ONE
PTL machine**, not a component rate, aggregate throughput or remote inference.
**Target has not been reached.** Continue in this session autonomously.

## Ownership and locations

- Our worktree: `/private/tmp/tahoma-inkling-panther-autolab`.
- Branch: `perf/inkling-panther-autolab`, pushed through `b1b87a4f` before this
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

Active native jobs (refresh before any action):

- **Baseline queue Python3856**, original parentcmd7388.
- **Long baseline full-decode.exe7340**, launcher10976, created1789332956.0200448.
- **Host sampler Python2208**, parentcmd8336, every10s to `host-resources.jsonl`.
- **Mapped embedding qualification Python7892**, parentcmd596, currently waiting
  for successful baseline completion AND its task lock. Read
  `mmap-qualification-state.json` before ANY competing full run/build.
- No Autolab controller campaign currently running. ResultsDB has90 experiments
  across13 completed campaigns. Later numbered reports are manual bounded
  experiments, not falsely inserted into that database.

Baseline status: `baseline-queue-state.json`; log `large-baseline.log` emits
one `sample_json=` per completed case. Three prompts ×64 generated tokens ×3
repetitions, roughly80–90 minutes total at current speed. Initial load29.913s.
Frozen `full-decode.exe` SHA256:
`f0bf021af04edd76f6fec5b77d8571225ba38f8f2315cbaac2bed189c04fc77a`.
Original profile reads0, BF16rows1, int4rows1, Rayon16, parallel experts,
affinity65535, High priority. Do not change this active process.

Smoke passed: exact **Paris**, hash8d8398585d6ee7ea, load37.309s,
prefill81.483s, decode27.521s /3 steps = **0.109008 tok/s**. Short smoke only.
First full-length pass,63 decode steps each: water_cycle **0.141965**,
binary_search **0.135469**, short_story **0.138188** tok/s. Water_cycle rep1
**0.140173**, binary_search rep1 **0.139875**, both with identical greedy IDs.
Seven of nine samples complete at last check; all repeated greedy IDs match.
The final binary_search and short_story repetitions remain pending.
No final repeatability hash/qualifying throughput result yet.

The queue will write `large-baseline.json`, `large-baseline-text.json`,
`large-cases.baseline-reference.json` and terminal
`baseline_recorded_needs_review`. Review text, exact repeated IDs/hash and
>=32 steps before configuring the full campaign. Initial baseline has no
supplied greedy IDs and therefore reports correctness_verified=false.

Resource sample (result028): ~5.29 CPU core-equivalents,84.7% in kernel,
2.108 GB/s machine-wide disk reads,518k process faults/s including soft faults.
Available RAM briefly7.58 MB, working-set peak43GB, pagefile use~3.54GB.
Machine I/O is not attributed exclusively to model; not all faults hit disk.
Do not sacrifice protected services to free memory.

## Prepared next tests

1. Let the baseline finish. Qualification7892 then builds/tests separate
   **full-mmap-embed.exe**, verifies frozen binary SHA and fixture hashes,
   writes `mmap-qualification-state.json`, then exits. It does not launch a
   full performance trial. Logs: `test-mmap-embed.log`, `mmap-qualification.log`.
   Failure stops the sequence; inspect it. Never overwrite a frozen binary.
2. Mapped embedding candidate (`4e9a427a`) is opt-in
   `CASCADIA_INKLING_MMAP_EMBED=1`, defaultoff. It maps the sparse ~2.47GB BF16
   embedding and keeps the head resident. Shape/range/alignment/lifetime checks;
   non-BF16/unaligned tensors use existing copied conversion. **217 local tests
   passed**, all8 HF greedy IDs ×3 reps match, full-logits hash5122e042f9b1fb30
   (ARM debug fixture only). Native MSVC qualification still pending.
   Frozen Windows fixture hash is **1f7cd0eb14a22662**. No measured full speedup.
3. `prefetch-set-probe.py --buffered --reuse-buffered --after-baseline --out FILE`
   compares fresh/reused bulk-read buffers and mapped-copy controls. Its guard
   requires baseline+qualification success and no active full binary. Eight
   31.85MB reusable buffers, setup outside steady-state timing, SHA checks and
   process fault counters. Use repeated --exclude-report for prior023/024
   cohorts. Local exact/short/truncated/trailing-byte checks and native overlap
   refusal passed. Source is deployed. **New component measurement not run.**
4. Validate the deployed `compare-full.ps1` against the fixture after native
   qualification. PowerShell syntax checks already passed. It uses the same
   full-mmap-embed.exe for named profiles: baseline(reads0/rows1/1),
   direct(reads1/rows1/1), tiles(reads1/rows2/4), mapped(tiles+mapped embed).
   The full-model campaign template parses as four experiments but still has
   a placeholder expected hash. Select only justified candidates in the actual
   new campaign, avoiding redundant80-minute controls.
5. Collect real **routing + layer timings** with a full model and reference IDs.
   `run-full.ps1 -Binary full-mmap-embed.exe -RouteTrace FILE -LayerProfile FILE`
   supports both; explicit -MmapEmbed0/1. Older qualified full-profile.exe also
   supports both (SHA437c7134198fd99b167e45ab76e4cd1c963bc7af8d17e43215de985c13ea6386).
   Keep all3 cases and64 tokens; Samples1 diagnostic retains the same aggregate
   baseline hash but cannot satisfy the3-repetition25tok/s target gate.
   `analyze-routing.py --require-full` and `analyze-layer-profile.py --require-full`
   are prepared; no real full routing/timing trace yet. Restart sampler after the original exits, with a NEW output filename plus
   `--follow-trials --stop-file C:/Users/devcloud/inkling-autolab/stop-trial-sampler
   --hours 6`. This mode survives idle gaps between trials. Create its unique
   stop marker when the campaign ends. Native isolated canary passed; report032.
6. Use Autolab run_campaign.py with actual reference cases/hash. Full target
   gate requires exact baseline hash, full975B scope, expected greedy IDs,
   >=32 decode steps, >=3 reps, slowest case/repetition >=25tok/s.
   Wrapper saves raw results and refuses failed/invalid/incomplete promotion.

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
