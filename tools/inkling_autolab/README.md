# Inkling on Panther Lake with Autolab

This project runs reproducible, sequential experiments against the production
Inkling engine on **tate-07**, `100.82.253.76` (SSH alias
`cascadia-tate-07-ts`, user `devcloud`). The controller runs on macOS/Linux;
the benchmark runs natively on Windows with MSVC. Source baseline: `9aaebff0`
on `feat/inkling`, from `/Users/tatef/Workspaces/tahoma-inkling`.

**Scope:** synthetic resident 975B-sized decoder layer, including attention,
convolutions, normalization, 256-row routing and six selected + two shared int4
experts. Eight distinct 31.85 MB bins are generated deterministically. The other
router entries are suppressed. The active weights exceed the CPU cache. This
measures production code at real dimensions, but omits checkpoint-dependent
routing, the full expert population, disk paging, embeddings, the head, and the
66-layer chain. `layer_tokens_per_s` is **not model tokens/s**. It must never be
reported as full-model throughput or multiplied into a model speed claim.

Inspection on 2026-09-12/13: Core Ultra X7 358H (16 cores/16 threads), 64 GB RAM,
Windows 11 Pro; ~3.5 GB disk free, no Inkling checkpoint in a bounded scan of 20,095 directories.
The current 512 GB export cannot be deployed with that storage capacity.
Full-model tokens/s remains an explicit blocked research question.

## Setup

Install the sibling Autolab checkout in an isolated Python environment:

```sh
python3 -m venv /tmp/inkling-autolab-venv
/tmp/inkling-autolab-venv/bin/pip install -e /path/to/autolab pytest
```

The current agent supplies the research decisions using `JOURNAL.md` and
`research_plan.yaml`; Autolab supplies campaign execution, SQLite persistence,
and resumption. This works in a Codex session without the Claude stop hook or
another LLM/API credential. `run_campaign.py` is the experiment executor, not a
background LLM agent. Continue the hypothesize → execute → analyze → revise loop
in the session; do not claim unattended agent work continues after it ends.

The remote source/target/binaries all live under the task-owned directory
`C:\Users\devcloud\inkling-autolab`. Upload a source archive, extract into
`repo`, upload `build.bat` and `run-bench.ps1`, then run `build.bat` over SSH.
Save the resulting `target\release\examples\inkling_bench.exe` as
`bin\baseline.exe` before compiling candidates. Preserve each compared binary
under its own name and record its SHA-256.

```sh
/tmp/inkling-autolab-venv/bin/python -u tools/inkling_autolab/run_campaign.py \
  tools/inkling_autolab/campaigns/001_threads.yaml
```

Campaigns use the SSH backend with **explicit `user: devcloud`**, and absolute
Windows command paths. Omit `runner.working_dir`: Autolab currently resolves
relative paths on the local controller, including Windows drive paths.

## Measurement and promotion rules

- Run only one campaign/build at a time on tate-07. The controller takes an
  exclusive lock. Check for other agents' inference/build jobs before starting.
- The launcher sets the benchmark's priority to High and explicitly applies
  its affinity mask, preventing Windows background scheduling from dominating.
  It changes only its own child process and cleans that process up on error.
- Warm up 16 positions, measure 32 positions, repeat five times, use median
  latency. Reset state between repeats. Record every sample, environment,
  dimensions, binary variant, and the full-output hash.
- Scheduling and SIMD changes must preserve the fixed reference output hash.
  Missing/non-finite metrics, nonzero exit, hash disagreement, or an incomplete
  sweep prevent promotion. Run the Inkling fixtures and the changed-kernel tests
  on the actual x86 host as well.
- Confirm winners with interleaved baseline/candidate process runs. Explore
  nearby thread counts/affinity and independent hypotheses. A <3% change within
  run-to-run spread is inconclusive; it is not a new performance record.
- Each finite grid disables Autolab's proximity-based early stopping by using a
  window larger than the grid. Close the campaign only after every configuration.
- Keep `results.db` local; portable raw records are exported to `results/*.json`.
  Keep failed trials as evidence, with a new campaign name for a revised retry.
- Never delete another agent's models/builds/caches, stop their workload, or
  change global machine settings. The full-checkpoint capacity problem is not
  permission to reclaim other projects' storage.

Autolab source used for this session: `3993e2c4`; its pre-existing local change
to `src/autolab/runners/ssh.py` was retained untouched. Campaign/loop/SSH tests:
21 passed before the campaign. No Autolab backend modification was needed.

Results and final launch recommendations are recorded in `JOURNAL.md`.


## Confirmed resident profile (2026-09-13)

Final confirmation uses the same binary for every setting: six independent
process groups, rotating order, seven timing samples per process; exact output
hash in all 18 runs:

| Configuration | Median ms per layer-token | Range across processes |
|---|---:|---:|
| Original adaptive algorithm, rows 1/1 | 47.106 | 47.013–47.665 |
| Direct mmap, rows 1/1 | 18.230 | 18.063–18.714 |
| Direct + bf16 rows 2 / int4 rows 4 | 17.456 | 17.246–17.492 |

The combined resident-layer speedup is **2.699x**; the row tiles add **1.044x**
over direct reads. All six paired groups favor the tiles. These are layer
latencies, not full-model throughput. See `results/012_final_profile.json`
and `012_summary.json` for the data.

The selected resident profile uses:

```powershell
$env:RAYON_NUM_THREADS = '16'
$env:CASCADIA_INKLING_SEQ_READS = '1'
$env:CASCADIA_INKLING_SERIAL_EXPERTS = '0'
$env:CASCADIA_BF16_GEMV_ROWS = '2'
$env:CASCADIA_INT4_GEMV_ROWS = '4'
```

The two new row knobs accept 1/2/4, default to 1, and are read once per process.
They apply to the shared sparse-MoE kernels; the int4 tile only dispatches on
AVX2/FMA without the AVX-512 path. Both preserve the original per-row accumulation
and bf16 rounding bits. Defaults remain appropriate for comparison on other CPUs;
this experiment only establishes performance on this PTL resident workload.
Direct reads must be retested for a paged full checkpoint. Expert pinning remains
off: 64 GB cannot hold the complete export.

Rejected: smaller thread pools, tested affinity subsets, stand-alone bf16 tiling
(<1%), and concurrent attention projections (slower). The projection source was
removed; its patch and failed performance hypothesis remain in the journal.

OpenVINO CPU/GPU probes preserve the source quantization grid and bf16 boundaries,
with an independent f64-dot oracle allowing <=0.5% relative RMS and <=3% worst
error / reference RMS. The eight-expert GPU asynchronous probe reaches 3.268 ms;
this is exploratory component evidence. It is not integrated into the production
Inkling backend and includes no full expert-population paging or recompilation.

## Full-model measurement after checkpoint provisioning

`inkling_decode_bench` loads every layer, all expert mappings, embeddings and the
head through the production loader and runs autoregressive greedy generation.
It refuses a non-975B architecture unless `--allow-fixture` is explicit. Fixture
runs emit a separate metric. Generation stops at EOS; the first output token is
accounted to prefill. Decode includes complete model calls, argmax, and correctness
hash overhead. The primary rate is the **slowest case/repetition**, including the
first decode run, so no hot-cache trial can hide a slow one.

1. Finish the all-files SHA-256 transfer from `miner:/mnt/external_ssd/inkling/out`.
   The authorized cleanup reclaimed 822 GB; the complete 549 GB export now fits.
   `model-ready.json` is written only after every file matches its source digest.
2. Prepare `large-cases.json`: an array of `{name, prompt_ids}` for at least three
   representative long completions, tokenized with the checkpoint's tokenizer.
   Run `bin/full-decode.exe --export MODEL --cases CASES --tokens 64 --samples 3
   --out BASELINE.json` under original row settings and controlled priority.
   A baseline without expected IDs is explicitly not correctness-verified. Inspect
   its output and use each case's generated IDs as `greedy_ids` in the cases file.
3. Copy `full-model-campaign.template.yaml` into `campaigns/` with a fresh name,
   actual model/cases paths, and the baseline output hash as `expected_hash`.
   Run it through `run_campaign.py`. It compares direct/adaptive reads and row
   tiles on the actual checkpoint. Completed results must match the baseline
   logits hash and expected greedy IDs. Do not use a fixture hash here.

The controller can mark the 25 tok/s target reached only for a verified
`full_large_model_decode` campaign, with the full-model flag, matching baseline
hash, expected greedy IDs, >=32 measured decode steps per case, and >=3 repetitions.
Its selected rate must be >=25 tok/s. The synthetic layer and GPU component rates
cannot satisfy that gate. **No such full-model measurement exists in this session.**

The complete export is 549 GB (511 GiB); RAM is 64 GB. Cleanup resolved disk
capacity and checkpoint transfer is underway. The present batch-one
engine streams tens of GB per token; 25 tok/s requires a substantially different
strategy such as validated speculation/quantization. The measured component gains
do not establish that strategy or an achievable full-model target.


## Deployment and queued baseline (2026-09-13)

The user authorized removal of unused tate-07 disk artifacts. The two
`results/013_disk_cleanup*` reports record exactly what was removed and protected.
822 GB was reclaimed; 825 GB was free before the new model copy. Active Qwen3.6
OVMS, its model/cache, source trees, installed tools and unique logs were retained.

`transfer-server.py` on miner exposes only the export, binds to its Tailscale IP,
checks PTL's source IP plus an ephemeral token, and expires after 96 hours.
`transfer-client.py --workers 8` runs natively on PTL, resumes temporary files,
checks source/destination SHA-256 and atomically publishes the all-files marker.
It stops pending files on permanent errors. HTTP bypasses environment proxies;
Tailscale encrypts the transport. Token files are runtime-only, never committed.
No SSH private key was copied and no public Funnel was configured.

`queue-full-baseline.py` waits for verified deployment, checks the frozen binary,
uses the checkpoint tokenizer/template (thinking off), verifies the documented
Paris smoke answer, then runs 3 prompts × 64 tokens × 3 repetitions with original
adaptive/row settings. It saves logs, raw generated IDs, decoded text and baseline
reference cases. It cannot claim correctness verification or the 25 tok/s target.
Review its output before configuring the next Autolab campaign. `run-full.ps1`
now accepts `-Out` to retain the benchmark's structured report.

The transfer and this finite baseline job run independently of the controller
Mac. They do not make new research decisions after the session ends. Inspect
`transfer-state.json`, `baseline-queue-state.json`, `transfer.log` and
`large-baseline.log` under the PTL task root. See HANDOFF for live process IDs,
resumption and cleanup of the temporary transfer service.

## Optional CUDA export (2026-09-13)

`tools/export_inkling.py --device cuda:0 --workers 4` accelerates int4 conversion
with bounded 64 MiB input chunks. The portable artifact format is unchanged;
CPU remains the default. See `docs/architectures/inkling.md` for dependencies,
streaming export and `--verify-cuda` qualification instructions.

On miner's existing RTX 4060 Ti 8 GB, all 43 exporter tests passed. One original
975B expert exactly reproduces the frozen export and quantizes 4.23x faster,
including host/device copies. Eight synthetic production-sized experts convert
and fsync 2.37x faster (five repetitions; CPU eight workers, CUDA four workers).
These are subset measurements; a full 975B re-export has not been timed.
Raw reports are `results/015_cuda_*.json`. Reproduce the selected subset trial:

```sh
python tools/inkling_autolab/cuda-export-bench.py \
  --config /data/inkling-int4/source_config.json --work-dir /data/scratch \
  --out /data/cuda-export-result.json --workers 8 --cuda-workers 4 --samples 5
```

The benchmark creates and removes its own temporary source/output directory,
checks every output SHA-256 against CPU and refuses to overwrite its report.
No CUDA exporter process remains running. PTL transfer/baseline jobs are separate.

## Default export host and direct PTL access

The user designated **ubuntu@129.146.170.51** for all future exports in this
loop. It has eight A100-SXM4-40GB GPUs, about 1.7 TiB RAM, and 5.7 TiB free disk
at setup. SSH uses the controller's existing `~/.ssh/amx-bench_ed25519`; alias
`inkling-export` is configured on this controller. No private key was copied.

The isolated root is `/home/ubuntu/inkling-export`, with `venv`, `repo`, `source`,
`exports`, `scratch` and `logs`. Python 3.12.14, PyTorch 2.14.0+cu130 and
Transformers 5.16.1 are installed; the initial 43 tests and subsequent 45 tests
including the multi-GPU pool passed on this host. Existing host services remain.
The general exporter still defaults to CPU; this task's remote launcher selects
CUDA from `export-host.json`:

```sh
python tools/inkling_autolab/export-remote.py -- \
  --model /home/ubuntu/inkling-export/source/Inkling \
  --out /home/ubuntu/inkling-export/exports/Inkling-int4
```

Paths are remote. `--print-command` shows the invocation, and forwarded
`--device cuda:all` selects the available-device pool. The remote `flock` permits
one launcher invocation at a time. Raw source weights have not been downloaded;
the current frozen export is still on miner and does not need regeneration for
PTL kernel tests. Do not keep this $15/hour host running solely for PTL transfer.

The user also authorized direct PTL SSH through `guest@192.55.48.214` to
`devcloud@192.168.22.2`, using `~/.ssh/cascadia_ed25519` for both hops. Controller
aliases `inkling-ptl-jump` and `inkling-ptl-direct` implement that route.
`jump-tunnels.py` maintains two loopback forwards: miner localhost:18868 to
controller localhost:18868, then PTL localhost:18868 through the jump host.
The read-only source endpoint requires a separate ephemeral token and binds
only to miner localhost. The native client retains SHA-256 verification and
resume semantics. This faster route depends on the controller remaining awake;
the supervisor reconnects and exits after verified deployment or 96 hours.

See HANDOFF for current process IDs and endpoint/token cleanup. A 32 MiB scp
probe and a real expert copy passed exact SHA checks; a two-minute bulk window
measured 20.5 MB/s with eight streams, versus the prior 2.67 MB/s Tailscale copy.

The selected A100 export profile is `cuda:all` with four workers: 22.656 experts/s
in a 64-expert warm-source trial. Matched eight-expert conversion is 1.58x faster
than miner CUDA and 3.73x faster than the original miner CPU path. At ~$15/hour,
plan **15–30 minutes / $4–8** when raw weights are local, or roughly **2–3 hours /
$30–45** for a first download plus export. The pinned checkpoint is 1.905 TB;
eight download streams measured 196–323 MB/s in short range probes. These are
estimates, not full-model export/download timings. Retaining source storage
between exports avoids paying again for the initial download.

Final transfer profile: **eight independent jump transports, 32 HTTP workers**,
round-robin PTL loopback ports 18868–18875, all to the same authenticated source.
This sustained **103.70 MB/s**, versus 46.38 MB/s with four transports. More HTTP
workers within one outer SSH transport did not help. Three detached supervisors
maintain the selected forwards; current PIDs and restart arguments are in HANDOFF.
