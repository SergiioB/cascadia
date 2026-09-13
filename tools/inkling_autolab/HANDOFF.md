# Restart handoff — Inkling / Panther Lake Autolab

Updated 2026-09-13 after A100 qualification and direct-route transfer work. A native checkpoint transfer
and a finite baseline job waiting for it are running on PTL. No Autolab
controller is currently running. The user authorized autonomous testing on
**tate-07, 100.82.253.76**, plus commit/push as t8, without coauthor trailers.
Latest target: **25 full-model decode tokens/s for large Inkling on this one PTL
box**. It has NOT been reached. Do not equate layer/component rates with it.

## Latest steering and live state (supersedes older deployment sections)

The user designated **ubuntu@129.146.170.51, 8x A100-SXM4-40GB**, for all future
exports and requested cost estimates at ~$15/hour. Use `export-remote.py` and
`export-host.json`, default **cuda:all / eight processes / one worker each / 64 MiB chunks**.
The working controller identity is `~/.ssh/amx-bench_ed25519`; alias
`inkling-export` is installed. About 1.7 TiB RAM and 5.7 TiB free disk at setup.
The isolated root `/home/ubuntu/inkling-export` holds `repo`, `venv`, `source`,
`exports`, `scratch`, `logs`. Python 3.12.14, Torch 2.14.0+cu130, Transformers
5.16.1; all **45 exporter tests passed in 27.13 s** across the eight GPUs.
The GPU pool preserves per-device byte parity and staging ownership. Existing
host Jupyter/container/monitoring services were retained. No private keys copied.

Autolab campaigns 017 (eight experts) and 018 (64 experts) completed, all CPU
byte checks passed and hashes match across arms. Best 64-expert rate is
**22.656 experts/s**, or a scaled 12.1-minute expert stage. Matched eight-expert
conversion is **1.58x miner CUDA / 3.73x original miner CPU**. Planning estimate:
**15–30 minutes / $4–8** with raw weights local; **2–3 hours / $30–45** for first
download plus export. Raw checkpoint size 1,904,604,285,204 bytes. Eight HTTP
streams measured 196–323 MB/s in bounded probes. Full export/download have NOT
been timed, and cold I/O or download variance can change these estimates.

New experiment 021 supersedes the thread-pool conversion profile: independent
process medians for 64 experts are 3.620183 / 1.745651 / 1.085111 s at 1 / 4 / 8
processes. Every output matches the saved CPU oracle in all nine samples.
Eight processes: **58.980 experts/s**, 2.603x the previous pool, scaled **4.67
minute/$1.17 expert stage**. Full export still unmeasured; retain the overall
15–30 minute local-source budget. Across different batch sizes, per-expert rate
is 4.62x miner CUDA / 10.93x miner CPU; this is not a full-export comparison.

`--processes 8` requires Linux, `--device cuda:all`, a complete source and full
--model/--out. It partitions CPU affinity and disjoint layer bins; source
shards stay intact. Parent-only finalization publishes shells/sidecars/manifest.
Output flock and parent-death cleanup prevent overlap/strays. Use forwarded
`--processes 1` for original streaming/tiny/validation modes. **48 tests passed
in 39.34 s**, including full tiny byte parity, staged resume, truncated-output
repair and failed child preventing manifest publication.

All A100 test/benchmark jobs have ended and all eight GPUs were observed idle
(0 MiB). Raw checkpoint weights were NOT downloaded; synthetic test sources and
outputs were removed automatically. The venv is 5.4 GiB; config is 8 KiB. The
current PTL loop needs the already-exported miner checkpoint, so it does not
need this rental kept running between future exports. Provider billing controls
have not been accessed; do not assume guest shutdown stops charges.

The user authorized direct PTL access with the **cascadia** key for both hops:
`ssh -J guest@192.55.48.214 devcloud@192.168.22.2`.
Controller aliases `inkling-ptl-jump` and `inkling-ptl-direct` use
`~/.ssh/cascadia_ed25519`. Hostname confirmed `pdx88-pa0794`.

Direct transfer is live. The old Tailscale native client PID 7060 and subsequent
one-tunnel clients 11176 / 10512 were stopped with path/PID checks; partials were
preserved. Current native Python **PID 4740**, parent cmd **9040**, has **32 workers**
and cycles `http://127.0.0.1:18868` through `18875`. Latest observed state:
**10,078 files / 341,801,616,008 bytes verified**, no errors (later than the
historical snapshots below). The baseline queue **PID 3856** still waits for the
all-files marker. Do not run a competing full benchmark.

Source endpoint on miner: `/tmp/inkling-jump-transfer/transfer-server.py`,
**PID 203817**, binds **127.0.0.1:18868**, permits localhost plus an ephemeral
token from `/tmp/inkling-jump-transfer/token`; expires in 96 hours or success.
Token also exists on controller `/private/tmp/inkling-jump-transfer/token` and
PTL task root `transfer-jump-token`. Never print/commit tokens.

Three detached controller supervisors maintain the SSH forwards:

- **PID 85720**, `/private/tmp/inkling-jump-transfer`: original miner local
  forward and PTL port 18868. It was launched with the default one-PTL-tunnel
  arguments. Source SSH is LAN; PTL SSH uses the direct jump route.
- **PID 88185**, `/private/tmp/inkling-jump-extra-tunnels`: three extra PTL
  reverse forwards on ports 18869–18871; arguments `--port 18869 --ptl-tunnels 3
  --no-source-tunnel --state-dir /private/tmp/inkling-jump-extra-tunnels`.
- **PID 89290**, `/private/tmp/inkling-jump-eight-tunnels`: four further PTL
  reverse forwards on ports 18872–18875; arguments `--port 18872 --ptl-tunnels 4
  --no-source-tunnel --state-dir /private/tmp/inkling-jump-eight-tunnels`.

`jump-tunnels.py` reconnects its own SSH children, uses flock to prevent duplicate
supervisors, and exits on the verified marker or after 96 hours. These forwards
depend on the controller being awake. Status/child PIDs are in each directory's
`tunnels-state.json`; logs are alongside. No private key leaves the controller.

Single jump transport measured 20.51 MB/s with eight HTTP workers; 32 workers
regressed to 18.13 MB/s. Four transports reached 46.38 MB/s; **eight reached
103.70 MB/s**, near the Ethernet limit. Retain eight/32 workers. About 1.26 hours
remained at the final short-window rate. The prior DERP
bulk rate was 2.67 MB/s. Source is an actual SanDisk Extreme Pro USB SSD.
See JOURNAL hypothesis 17 and results 019 for integrity gates and measurements.
Baseline/OVMS/node/CA remained running with unchanged PIDs.

The retired source Tailscale server **PID 199701** was stopped after the direct
path was stable, with an exact /proc command identity check. Its old token files
remain historical task state; the endpoint is no longer serving.
Old copy logs/state on PTL are `transfer-derp.log`, `transfer-state-derp.json`,
`transfer-jump8.log`, `transfer-state-jump8.json`, `transfer-jump32.log`, and
`transfer-state-jump32.json`. Do not restart any archived copy concurrently.

Next: let the verified copy finish, collect
the full PTL baseline once deployment completes, and resume correctness-gated
full-model experiments. CUDA export timing is not PTL tokens/s.

Routing diagnostics are now prepared for the next real-model experiment:

- `MoeLayer::set_route_observer` is opt-in and defaults off. The benchmark's
  `--route-trace FILE` records routed IDs per layer/position and rejects an
  existing trace path. Captures include prefill/decode boundaries and hash.
- PTL **`bin/full-routing.exe`**, SHA-256
  `c97b3dca07da990c8dddbd809857ec38d1c42f32d22723412077b873531aff49`.
  The canonical `full-decode.exe` is unchanged. `run-full.ps1` defaults to it;
  select diagnostics with `-Binary full-routing.exe -RouteTrace PATH`.
- **75 Inkling tests passed**, all eight MSVC test targets. Traced/untraced
  diagnostic and frozen baseline match eight HF fixture IDs and logits hash
  `1f7cd0eb14a22662`. Wrapper fixture invocation passed as well. Raw validation
  is in `results/020_*`, remote `test-routing.log` and `routing-validation.json`.
- `analyze-routing.py` reports routed working sets, whole-expert LRU estimates
  and window-union miss lower bounds. Three analytical tests passed. Use
  `--require-full` for real conclusions; checked-in traces are tiny fixtures.
- Export file metadata: fixed shell/edge/dense 23,041,852,040 bytes; shared
  experts 4,076,863,488; each routed bin 31,850,496 (16,384 routed bins total).
  These are storage sizes, not actual resident RAM. KV/other services need RAM.
- q11 remains active: no real route trace yet. Wait for/review baseline, use
  reference IDs and hash for the next run, then inspect reuse before choosing
  a new cache/prefetch policy. Keep one full benchmark at a time.
- Later copy status: **5,646 files / 200,640,217,736 bytes verified**, no errors,
  same transfer PID 4740 and waiting queue 3856. Existing OVMS PID 6728 has
  a ~20,023,873,536-byte working set; account for it in cache budgets and do
  not stop it. Analyzer budgets include 8/12 GiB for constrained memory.

## Additional active diagnostics and latest rejected experiment

Native host sampler **PID 2208**, parent cmd **8336**, runs `sample-host.py`
from `host-sampler.cmd`, writes `host-resources.jsonl` and `host-sampler.log`.
It samples every 10 s, identifies full binaries by task bin directory, never
stops any process, and exits on terminal baseline state/no full process or 96 h.
Working-set/commit/page-fault/CPU counters are per process; physical disk counts
are machine-wide. Initial available memory ~39.6 GB, no full model yet.
Keep sampling overhead included when interpreting baseline timings. q13 active.

Experiment 023 rejected batched/parallel Windows prefetch. Eight real experts,
six rotating disjoint cohorts: no prefetch 65.021 ms, existing serial calls
66.508 ms, parallel 96.951 ms, one range batch 86.745 ms (page-in plus native
copy). About 254 MB disk reads per 255 MB cohort, all copy hashes exact. No
cache flush; concurrent transfer is a confounder. No production change made.
`results/023_windows_prefetch_sets.json`, native `prefetch-set-probe.log/json`.
Probe exited successfully; q14 answered. The full baseline is still queued.

## Prepared combined routing and layer timing diagnostic

`bin/full-profile.exe` SHA-256
`437c7134198fd99b167e45ab76e4cd1c963bc7af8d17e43215de985c13ea6386` adds
`--layer-profile FILE`, also supports `--route-trace FILE`. **76 Inkling tests
passed**; unobserved/combined-trace/wrapper fixture runs reproduce all eight HF
IDs and hash `1f7cd0eb14a22662`. Frozen `full-decode.exe` is unchanged.
`run-full.ps1 -Binary full-profile.exe -LayerProfile FILE -RouteTrace FILE`
selects both diagnostics. `analyze-layer-profile.py --profile FILE --benchmark
FILE --out FILE --require-full` checks matching scope/hash/sample identities,
complete layers/positions, and duration sums. Branch times include norms/convs/
residuals. Outside-layer time includes head, embeddings, argmax, hashes and
observer overhead; do not call it head time alone. Raw fixture reports/validation
are `results/025_*`; native build log `test-profile.log`. Build/tests ended.
q16 awaits actual full-model timing alongside q11's routes.

Experiment 024: serial hints + buffered reads 112.698 ms versus reads alone
104.155 ms, but serial hints + preallocated mapped copy 63.475 ms. This compares
allocation/copy behavior as well as I/O; prefer testing the existing direct-map
full-model profile first, without adding another production switch. Every
cohort read ~255 MB from disk, exact copy hashes, prior probe files excluded.
`results/024_windows_buffered_prefetch.json`; q15 awaits full-model evidence.

## Current outcome and blocker

The autonomous research loop is operational in this Codex session. Autolab is
the sequential experiment executor, SQLite history and resumption mechanism;
the session supplies research decisions. No Claude hook or separate API key is
needed. Do not claim the research agent runs after the session ends.

Campaigns 001–010 completed; 011 is a read-only Windows residency diagnostic.
Campaign 012 completed: all selected settings confirmed using the same final binary.
Use `JOURNAL.md`, `results/012_final_profile.json` and `.autolab/state.json`
for its completion and exact final numbers. If interrupted, resume 012; SQLite
skips completed experiments and reruns a trial interrupted before it was stored.

Final campaign 012: adaptive rows 1/1 47.106 ms/layer-token, direct rows 1/1
18.230 ms, direct + bf16 rows 2/int4 rows 4 17.456 ms. Six rotating process
groups, all output hashes exact. Combined 2.699x resident-layer gain; tiles alone
1.044x and win all six groups (1.034–1.075x). Earlier frozen-binary comparison
009 measured 2.753x / 1.070x; use the conservative final same-binary numbers.
Smaller pools/affinity subsets and parallel projections lost. Retained two opt-in
AVX2 row kernels; original defaults remain 1/1. Removed parallel-projection
production code; saved the rejected patch/evidence. Kernel commit: 18c3edf9; campaigns/full-decode harness: 83d07a27. Both pushed
as t8 without coauthors.

OpenVINO eight-expert probe: GPU async 3.268 ms vs CPU async 9.541 ms.
Independent f64-dot oracle passed for all eight distinct experts at two inputs.
This is exploratory, allows summation differences, is not a production GPU
backend and omits attention, routing, full expert-population paging and churn.

The user has now explicitly authorized clearing unused disk artifacts. This
supersedes the earlier storage blocker: cleanup reclaimed **821,909,577,728
bytes (822 GB)**, leaving **825,192,165,376 bytes (825 GB / 768.5 GiB)** before
copying the export. Reports `results/013_disk_cleanup*` list every removed and
protected path. Active Qwen3.6 OVMS and cascadia node/CA remained running with
unchanged PIDs and HTTP 200 model listing. Source trees, toolchains, unique logs
and current Inkling artifacts remain. Small metadata/config/recipes from removed
exports are archived in the PTL task's two `cleanup-20260913*` folders.

The complete unchanged export was found at **miner:/mnt/external_ssd/inkling/out**:
**548,985,140,942 bytes, 16,654 files**, including 66 shells, 16,514 expert bins
(two dense), embedding/head and tokenizer assets. Source SSH alias `miner` is
tatef@192.168.0.235:1990 with the existing Mac identity; do not copy private keys.
No new export is needed for the current kernels. Native verified transfer is
underway to `C:\Users\devcloud\inkling-autolab\model`. This path currently
contains partial data; do not run the model until `model-ready.json` exists.

PTL still has 64 GB RAM and one 1.024 TB SSD, with a 1 Gb/s physical Ethernet
adapter. Disk capacity is resolved; full-model residency is not. The current
engine reads ~36.5 GB of weights per token. 25 tok/s would require ~0.91 TB/s of
effective weight bandwidth even before other overhead, or a substantially
different validated strategy. Do not claim that storage or the component gain
establishes 25 tok/s feasibility.

A new `inkling_decode_bench` example is built on PTL as `bin/full-decode.exe`.
It loads every layer/expert/edge table and measures autoregressive decode;
separates prefill, stops at EOS, checks finite/repeated logits and supplied
reference greedy IDs. Non-975B models require `--allow-fixture` and emit a
separate fixture metric. See README full-model instructions and
`full-model-campaign.template.yaml`. The controller's target gate requires a
verified full model, baseline hash, expected greedy IDs, >=32 decode steps,
>=3 repetitions, and the slowest case/repetition >=25 tok/s. A complete
checkpoint is now available at the source; PTL measurement awaits transfer.

## Locations and ownership

- Main checkout `/Users/tatef/Workspaces/tahoma`, branch
  `perf/prefill-layer-streaming`; other agents' `glm5_run.rs` and `ngram_sim.rs`
  changes are not ours. Leave alone.
- Original Inkling `/Users/tatef/Workspaces/tahoma-inkling`, `feat/inkling`,
  baseline `9aaebff02a2f68a48913ff67061d90c13121ae35`, PR #154. Docs report
  1.5 full model tok/s on a resident 1.5 TB Mac Pro. Do not rewrite this branch.
- Our isolated worktree **`/private/tmp/tahoma-inkling-panther-autolab`**.
- Our branch **`origin/perf/inkling-panther-autolab`** at
  `https://github.com/labscommunity/cascadia.git`.
- Git identity `Tate Berenbaum <t8@users.noreply.github.com>`; no coauthors.
- Autolab `/Users/tatef/Workspaces/autolab`, `3993e2c4`; its pre-existing dirty
  `src/autolab/runners/ssh.py` is unrelated and untouched.
- Venv `/private/tmp/inkling-autolab-venv`, editable Autolab + pytest. Use its
  Python (system Python lacks yaml).
- Root pointer `tmp/INKLING_AUTOLAB_HANDOFF.md` in the main checkout.

## Host and process rules

SSH: `ssh -o BatchMode=yes -o ConnectTimeout=10 cascadia-tate-07-ts`.
Alias uses `devcloud@100.82.253.76`, `~/.ssh/id_ed25519`.
Actual hostname `pdx88-pa0794`, Windows 11 Pro, Core Ultra X7 358H,
16 cores/threads; AVX2/FMA yes, AVX-512 no. PowerShell default shell, no WSL.

Our root `C:\Users\devcloud\inkling-autolab` contains `repo`, `target`, `bin`,
`synthetic-experts` (8 bins, 255 MB) and launchers. Other services include OVMS
and cascadia-swe-node; do not stop them. Only stop a task process whose executable
path is under our root, or our precisely named Python probe. Do not broad-kill
Python, Cargo, or inference servers. One benchmark/build at a time.

`build.bat` calls vcvars64 at `C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat`,
uses task-only CARGO_TARGET_DIR and explicit stable MSVC toolchain. **Audited
compiler: rustc 1.98.1 (48a229cea), LLVM 22.1.8.** Earlier 1.95 metadata was not
an explicit MSVC query and was corrected; campaign 012 uses one binary for all
arms to remove compiler/binary ambiguity. Build/test scripts should continue to
record `rustc +stable-x86_64-pc-windows-msvc -vV` with new builds.

Frozen binaries: baseline.exe, bf16-rows.exe, int4-rows.exe, projections.exe,
final.exe, full-decode.exe. Never overwrite a frozen comparison baseline.
Hashes are in raw results and `results/final_validation.json`.
`run-bench.ps1` sets child High priority, affinity 0xffff, explicit Rayon pool,
read/schedule/row knobs, fixed output hash, and cleans up its own child on error.
Full real-model runs must retest adaptive vs direct reads under actual paging.

## Validation and resumption

222 MSVC tests passed: full library, DSV4/GLM shared math/expert tests and all
74 Inkling tests. Full decode fixture: 8/8 HF greedy IDs, three repetitions,
hash `1f7cd0eb14a22662`, full_model=0. Clippy completed with existing library
warnings and three benchmark style suggestions. Controller tests: 8 passed.
Autolab campaign/loop/SSH tests: 21 passed during setup. Format/diff checks passed.

Before running, inspect git status and our remote processes. To resume a grid:

```sh
cd /private/tmp/tahoma-inkling-panther-autolab
/private/tmp/inkling-autolab-venv/bin/python -u tools/inkling_autolab/run_campaign.py \
  tools/inkling_autolab/campaigns/012_final_profile.yaml
```

The runner takes flock to prevent simultaneous campaigns, saves raw JSON even
on interruption, and refuses promotion on failure, missing/non-finite metrics,
hash mismatch, numerical oracle failure or incomplete sweep. Campaign regexes
need `(?m)` for multiline stdout; explicit SSH user devcloud; no remote working_dir
(the Autolab version resolves it on the controller). CLI 0 alone is insufficient;
use the wrapper's verified result. New hypotheses get new campaign names.

If /tmp is cleared, recreate an isolated worktree from our pushed branch and
the venv. Rehydrate ResultsDB by `store_result(record)` for each record in the
committed campaign JSON arrays, excluding metadata/summary objects and the older
003 partial snapshot (use complete 003 instead). The remote task files persist.
Do not apply saved candidate patches: the accepted kernels are already in the
branch, and the rejected projection patch is intentionally not applied.

The rg shim hung repeatedly; it was tried first. Use git grep/git ls-files or
bounded Python search if it still hangs. Latest permission profile has unrestricted
filesystem/network and approval policy never; do not pass sandbox_permissions.

Finish deployment and inspect the queued full-model baseline before resuming
Autolab optimization. Do not rerun resident sweeps as a substitute for real-model
measurement. Quantization/speculation/GPU integration must be checked against
real weights and correctness before claiming full-model gains.


## Live deployment jobs and next steps

The initial Mac-relayed rclone copy was stopped. Its logs/config (no embedded
private keys) are in `/private/tmp/inkling-*`; do not restart it concurrently.
Current copy runs natively on PTL with eight streams. It bypasses HTTP proxies
and SHA-256 checks every source/destination file, resumes `.inkling-partial`,
and atomically writes `model-ready.json` only on full success. Permanent transfer
errors cancel pending files. Client/server code is committed alongside this file.

Temporary source server on miner:

- Script `/tmp/inkling-direct-transfer/server.py`, PID **199701**.
- Binds only **100.103.4.77:18867**, permits PTL source **100.82.253.76**,
  requires an ephemeral token from `/tmp/inkling-direct-transfer/token`.
- No public Funnel/SSH authorization/firewall settings were changed.
- Exits after successful copy or 96 hours; removes its token on orderly exit.
- Inspect `/tmp/inkling-direct-transfer/server.log` and `pid` if interrupted.
- Runtime token also exists on the controller under
  `/private/tmp/inkling-direct-transfer/token` and target `transfer-token`.
  Never print/commit it. Delete the local token after the server/transfer ends.

PTL files under `C:\Users\devcloud\inkling-autolab`:

- `transfer-client.py`, `transfer.log`, `transfer-state.json`; parent cmd PID
  **7232** launched with Win32_Process.Create and survives SSH/controller exit.
  Python PID **7060** is recorded in transfer-state.json. Do not duplicate it.
- `queue-full-baseline.py`, `baseline-queue.log`, `baseline-queue-state.json`.
  Native Python PID **3856**, parent cmd **7388**, confirmed waiting.
  This finite job waits up to 96 hours for verified copy, checks the frozen
  full-decode SHA-256, runs the documented Paris smoke test, then records
  3 long prompts × 64 tokens × 3 repetitions, original adaptive rows 1/1.
  `--prepare-only` passed with prompt lengths Paris=25, water_cycle=30,
  binary_search=32, short_story=31. Transformers 5.2 returns BatchEncoding;
  the script explicitly extracts input_ids. PowerShell `-Out` retains JSON.
- Full output: `large-smoke.json`, `large-smoke-text.json`,
  `large-baseline.json`, `large-baseline-text.json`,
  `large-cases.baseline-reference.json`. Initial baseline has no supplied
  reference IDs and is therefore NOT correctness-verified. The queue does not
  promote changes or claim target attainment.

After baseline completion, review the generated text and raw samples, save the
results in this worktree, and seed the next full-model Autolab campaign with
the baseline greedy IDs and logits hash. Compare actual paged adaptive/direct
reads and then tiles. Keep one benchmark at a time; do not launch another full
campaign while the native baseline is running. A finite queue is not an
autonomous research agent continuing after the session.

If stopped, resume transfer with the existing live endpoint/token and the same
client; completed files are rechecked and temporary files resume. If the server
expired, recreate only this task's endpoint with a fresh shared ephemeral token
and re-upload the client token. Native jobs use the existing qwen38 Python venv.
Do not overwrite existing baseline JSON on rerun; archive/inspect the failed
attempt first and launch a fresh named measurement.

Bulk copy measured ~2.7 MB/s with eight streams (about 57 hours remaining at
that short-window rate). Direct PTL-to-miner transport did not improve bulk
throughput. Endpoint expiry/queue wait were extended to 96 hours. Consider a
faster network route before paying for more export CPU.

Removed the stopped rclone copy's eight abandoned `.partial` files (573,833,216
logical bytes); active `.inkling-partial` files were retained. The additional
audit is `results/013_abandoned_transfer_cleanup.json`.

## CUDA exporter work completed in this session

The user explicitly requested CUDA acceleration for future exports. Added
`tools/inkling_cuda.py` and opt-in `--device cuda[:N]`, `--cuda-chunk-mib 64`,
`--verify-cuda` to `tools/export_inkling.py`. CPU defaults and the artifact
format are unchanged. Startup byte parity runs before output creation; a shared
lock bounds GPU work across I/O workers. The CUDA scale divisor must stay a
device tensor: Python scalar division takes PyTorch's reciprocal-multiply
shortcut and changes quantization rounding. See JOURNAL hypothesis 15.

Validation used the existing idle **RTX 4060 Ti 8 GB on miner**, not rented
hardware. Isolated venv `/home/tatef/inkling-cuda-export/venv` has Python 3.12,
PyTorch 2.14.0+cu130, Transformers 5.16.1, numpy, safetensors and pytest.
Source copy `/home/tatef/inkling-cuda-export/repo/tools`; final test log
`/home/tatef/inkling-cuda-export/tests-final.log`: **43 passed in 17.43 s**.
Existing CPU export venvs and `/mnt/external_ssd/inkling/out` were untouched.
All CUDA test/benchmark processes ended; GPU observed idle (32 MiB, 0%).

Selected warm-source eight-expert conversion/write measurement: CPU eight
workers median **1.483070 s**, CUDA four workers **0.626925 s**, **2.366x**,
five alternating repetitions; every output file SHA-256 exact. Keep 64 MiB
chunks; 128 MiB lost. Peak PyTorch allocation about 206 MB, excluding context
and reserved allocator memory. `cuda-export-bench.py` reproduces the trial.

One original layer 2 expert 0 (113 MB bf16 source, fetched by HTTP Range at
revision `828496eeae4c243ff1a22f7f28ff83694f2f7bc9`) quantizes **4.233x** faster
including copies and matches the existing exported bin byte for byte. Source
`/home/tatef/inkling-cuda-export/real-expert-0.safetensors`, provenance
`real-expert-source.json`, helpers `fetch-real-sample.py` and `real-check.py` in
the same directory remain for reproduction. Reports `results/015_cuda_*.json`
are committed. Temporary synthetic sources/outputs were removed automatically.
The isolated GPU venv and real sample are retained for ongoing exporter work;
miner OS disk had about 43 GiB free after installation.

No whole-975B export timing or PTL inference gain is implied. No re-export is
needed for existing inference kernels. Resume the pending PTL baseline first.
Latest deployment observation: transfer PID 7060 copying with no errors,
**19 / 16,654 files, 5,147,657,460 / 548,985,140,942 bytes SHA-256 verified**;
queue PID 3856 waiting. OVMS 6728, node 8356 and CA 6344 remain running.
