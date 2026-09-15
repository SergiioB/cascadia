# Full Inkling correctness qualification for expert parallel deployment

2026-09-15, branch `feat/inkling-expert-routing`.

This extends [fused expert sharding](INKLING_FUSED_EXPERT_SHARDING.md) from
individual MoE measurements to the complete 66-layer decoder. The qualification
compares every layer residual, every output logit, and greedy token IDs against
a saved single-machine CPU reference. The validator accepts any worker count;
the LAN operator currently targets the three authorized NUCs.

The complete three-NUC CPU run, `full-cpu-v7`, **passed all 48 token choices
and all 3,216 tensors bit for bit**. All 66 layers execute; every expert is
available across the workers. Its instrumented decode rate is 0.1101 tok/s
(9.0827 seconds/token), including tensor capture/comparison and restricted
CPU resources. This is not a new throughput record. Driver peak RSS was
3.749 GiB; each worker stayed below 0.194 GiB. Charlie performed 480.53 GB
of direct expert reads with zero read fallbacks. Protected services remained
unchanged. The complete reports are in `full-cpu-v7.json.gz`.

Full fused GPU qualification remains in progress. The first full run exposed
FP16 overflow that the smaller synthetic tests did not catch; the isolated
replay and correction below pass, but that alone is not a full-model pass.

## Model and placement

The source is `miner:/mnt/external_ssd/inkling/out`, the complete large Inkling
export: 548,985,140,942 unique bytes. It has 66 layers, 64 MoE layers, hidden
size 6,144, intermediate size 3,072, 256 routed experts and two shared experts
per MoE layer, and six selected routed experts per token. Layers 0 and 1 are
dense. The manifest declares a vocabulary capacity of 201,024; the exported
head emits 200,058 logits, all of which are captured in each comparison.

"Full model" means all decoder layers, attention, convolution/relative-position
state, routers, dense MLPs, embedding and output head execute. Each token uses
its normal selected experts; a sparse MoE does not activate every parameter
for every token. All experts remain available to the router. This is distinct
from the earlier single-layer tests using synthetic hidden vectors.

The full shards use a capacity-aware, uneven placement, with shared experts
replicated and assigned exactly once for each request:

| Host | Owned expert files | Packed expert GiB | Role |
|---|---:|---:|---|
| alpha | 1,465 | 43.456 | Expert worker |
| beta | 7,326 | 217.312 | Expert worker |
| charlie | 7,977 | 236.622 | Expert worker and decoder driver |

All three are 31.55 GiB Panther Lake machines. Their aggregate RAM cannot
hold the model resident. Packed weights are retained for the independent CPU
comparison; fused GPU blobs require additional disk space. K=1 and K=8 IRs
hardlink the same weight blob. Alpha finishes staging with about 90.6 GiB
free, above the enforced 80 GiB floor. Nothing in the existing service model
directories is deleted or replaced.

Deployment root on each NUC: `C:/Users/tatef/inkling-ep-lan-20260915`.
`full/` holds packed files and the complete manifest; `full-fused-compact/`
holds the 64 K=1 GPU graphs. These are separate from earlier layer fixtures.

The exact placement reproduces with the saved worker capacities:

```sh
python3 tools/inkling_ep_plan.py \
  --manifest docs/perf/inkling-ep-full/manifest.json \
  --workers docs/perf/inkling-ep-full/workers.json --out /tmp/inkling-plan-NEW
```

The output includes each worker's packed copy list. Add embedding, head, all
shells, dense bins and tokenizer files to the driver's copy list. Staging's
`--files` argument takes a JSON array of relative filenames; convert the
planner's newline-separated list before using that operator. For this streaming
deployment the expert budgets represent disk capacity, with GPU blobs reserved
separately. They are not resident memory budgets. The saved cost coefficients
are illustrative and must be calibrated before optimizing placement.

## Reference and correctness contract

`inkling_ep_validate` rejects a reduced architecture unless explicitly passed
`--allow-fixture`. It resets sequence state between the three saved prompts
(water cycle, binary search, story opening), executes batched prefill and then
16 greedy decoding positions for each, and saves:

- `trace.json`: exact manifest, prompt IDs, generated IDs, tensor identities,
  dimensions, order, payload length and checksum.
- `tensors.f32`: little-endian f32 values for every layer residual, including
  every prompt row, and the complete vocabulary logits at each generation step.
- `report.json`: token/text output, per-tensor numerical differences, relevant
  environment, full-model marker and explicit correctness verdict.
- `progress.jsonl`: per-layer progress for diagnosing an interrupted run.

The 16-token reference contains **3,216 tensors and 262,249,344 payload bytes**.
Comparison follows the reference token trajectory so differences remain
locatable after the first mismatch. A pass also requires identical greedy
choices at every tested position: by induction, free generation would follow
that same trajectory. A failed token comparison is never relabeled a pass
merely because the generated text looks plausible. Generation uses a fixed
number of positions and does not stop at EOS; the report states this.

The default tolerance is zero and requires identical f32 bits. GPU comparisons
use a separately declared relative RMS limit; both numerical and greedy checks
must pass. A reference-recording run has `correctness_verified=false` because
it has no comparison input. That does not indicate a failed recording.

The full reference was recorded on tate-07 using original CPU attention/head
arithmetic and bounded existing expert reads, four CPU cores, a 32 MiB cache
per MoE layer and the original local export. Its first 16 IDs for every prompt
exactly match the earlier campaign-033 CPU baseline. Example continuations:

```text
1. The sun heats bodies of water like oceans, lakes, and rivers
**Binary search** is an efficient algorithm for finding a specific value (the
The bottle arrived with the tide, wedged between barnacled rocks at
```

These short deterministic continuations test implementation parity, not broad
language-model accuracy, long-context quality or universal generation identity.

## Memory changes and independent checks

`CASCADIA_INKLING_MMAP_SHELLS=1` and `CASCADIA_INKLING_MMAP_HEAD=1` map the
original BF16 projections instead of retaining owned copies. Arithmetic and
weight bits are unchanged. On Windows, immutable tensor pages are released
from the process working set after use through `VirtualUnlock`; the mapping
remains valid. Microsoft's [VirtualUnlock documentation](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualunlock)
describes this behavior for pages that were not locked.

The independent full-model mapped check captured 804 tensors (three prompts,
four positions) and matched the original CPU reference **bit for bit**.
Peak RSS fell from 25.24 GiB for the recording to 9.37 GiB for the mapped run,
including its local expert execution. The distributed driver omits those
local MoE banks. `CASCADIA_INKLING_EP_STREAM_CPU=1` uses bounded bulk reads;
cohorts of eight prevent nested Rayon tasks retaining hundreds of read buffers
during prefill. Read errors fail the request.

`CASCADIA_INKLING_EP_FUSED_STREAM=1` keeps each compiled K=1 GPU graph while
OpenVINO streams expert weights into a small resident slot. Rows are grouped
by expert to reuse that slot, then reduced in original routing order. The
cache admission estimate is not a hard GPU allocation bound; the external
memory guard remains authoritative. CPU fallback is forbidden.

Alpha's 64-layer cache probe compiled 64 graphs, evicted none, peaked at
2.572 GiB RSS and retained more than 19.84 GiB available memory. It recorded
128 fused GPU calls, zero CPU calls/errors/fallbacks, and 0.003104 relative RMS
against CPU expert outputs (limit 0.005). This is a selected-expert synthetic
phase check, **not a full-model token-generation result**.

A second probe alternates eight-row prefill-shaped requests and decode across
all 64 graphs, varying expert IDs and nonuniform/zero/negative weights. Its
3,786 GPU calls pass at 0.003061 relative RMS with zero fallback/errors and
2.568 GiB peak RSS. The timed phase takes 80.16 seconds on streamed GPU versus
22.93 seconds on bounded CPU reads. These synthetic phases expose the cost of
streaming and shape transitions; they do not predict full-model throughput.

## FP16 overflow regression and version-2 shards

The first full GPU prefill fails at layer 8, shared expert 256, on alpha.
The exact 30-row request has finite hidden vectors and routing weights, but
two unweighted down-projection values are outside FP16's finite range (about
−94,909 at the extreme). Routing later reduces them to values within range.
The GPU returns two nonfinite outputs; the same request succeeds on CPU.
An FP32 inference hint fails compilation in this OpenVINO fused path, and
the worker refuses fallback.

Version-2 shards divide the up-projection scales by 16 and the worker
multiplies the original routing weights by 16. Since the up branch and down
projection are linear, this preserves the real-arithmetic expert function
while reducing the intermediate dynamic range. The gate/Swish calculation
and packed nibbles remain unchanged. FP16 rounding still applies: export
rejects a scale conversion exceeding 0.01% relative weight RMS, and the full
output comparison retains its original 0.5% limit and exact greedy criterion.

The captured request passes on the fused GPU after this change with relative
RMS **0.00252557**, no nonfinite outputs and zero CPU fallback. The unscaled
replay fails reproducibly. These artifacts include the exact input frames,
CPU output, source expert checksum and kernel profile, so another agent can
replay the failure without running the entire decoder.

Fresh exports can use `inkling_ep_fused_export.py build
--up-scale-exponent 4`. For the existing isolated deployment, stop its workers
and run on each host:

```powershell
C:/cascadia/fleet/venv/Scripts/python.exe inkling_ep_rebalance.py `
  --root C:/Users/tatef/inkling-ep-lan-20260915 --exponent 4 --seconds 2400
```

The updater backs up only the scale range, marks both hardlinked graphs
unusable during mutation, checksums the changed blob, and atomically publishes
version-2 metadata. Interrupted layers restore from their journal before retry.
The original packed model bins remain unchanged. Old workers reject version 2;
all workers must use the new binary before these shards are loaded. Tests
verify rollback after an injected write-stage failure and byte identity between
a fresh scaled export and an updated shard.

## Run the full three-NUC comparison

Build with `tools/inkling_ep_build_gpu_windows.bat`. Put the same executables
and private runtime DLLs in each isolated `bin-full/` directory. The complete
CPU reference and its SHA256 manifest live on charlie. The exact cases and
placement are in [inkling-ep-full](inkling-ep-full/).

```sh
python3 tools/inkling_ep_full_run.py \
  --label full-cpu-NEW --mode cpu \
  --placement docs/perf/inkling-ep-full/placement.json \
  --reference full-reference16-v4 --tokens 16 \
  --out /tmp/full-cpu-NEW

python3 tools/inkling_ep_full_run.py \
  --label full-gpu-NEW --mode fused-stream \
  --placement docs/perf/inkling-ep-full/placement.json \
  --reference full-reference16-v4 --tokens 16 --max-relative-rms 0.005 \
  --out /tmp/full-gpu-NEW
```

Use fresh labels: jobs, logs and output directories do not overwrite earlier
evidence. The operator checks completed staging, placement/manifest agreement,
executable and DLL hashes, packed-file identities against verified journals,
fused source/ownership/XML metadata, and the reference's full SHA256 hashes.
Blob hashes are recorded while constructing the IR; preflight checks blob
size rather than rereading hundreds of gigabytes for each run.

Private port 29475 admits only charlie and only the task worker executable.
In CPU mode, workers use cores 0–3 and charlie's driver uses cores 4–5.
In GPU mode, charlie gives cores 0–3 to its decoder and cores 4–5 to the GPU
worker; alpha/beta retain cores 0–3. Jobs run below normal
priority, keep at least 12 GiB available, and have bounded lifetimes. Existing
inference activity pauses only this task's child; a CI job or memory limit
stops it. Cleanup checks the executable and process creation time before
terminating any remaining task worker and removes only the task firewall rule.

The completion gate requires every guarded job to exit successfully, preserved
service process identities, full-model numerical/token parity, and final
backend evidence. GPU mode additionally requires a fused GPU profile for
every owned MoE layer, nonzero execution and zero CPU fallbacks/errors.

## Extending to 12 machines

Create a placement for the actual 12 hosts and their available capacity; do
not reuse the three-host placement. Stage and checksum every owned expert,
build each host's fused graphs from those same packed files, and verify the
same executable/runtime versions. The driver then uses all 12 ordered worker
endpoints and that placement with the same `inkling_ep_validate` command.
Its reference format and comparison are independent of worker count.
Use version-2 scaled shards for the fused path and retain each shard's source,
derived blob and scale metadata in the deployment inventory.

Run CPU EP first with tolerance zero, then fused GPU EP against the declared
reference and tolerance. Retain per-layer differences and worker fusion
profiles, rather than accepting just an exit code or aggregate throughput.
Re-run with longer prompts, representative production cases and free generation
before serving real traffic. Passing this bounded corpus does not establish
fault tolerance, concurrent serving or parity for untested contexts.

Local tests cover a complete tiny decoder over 12 real TCP workers, exact
logits and greedy output, reset, replicated shared experts, and a 293-row
prefill crossing the transport frame limit. Separate 3/12-worker fused-wire
tests cover weighted partial sums, negative weights and empty rows. These
tests validate routing behavior; **12 physical machines have not been tested**.

The separate-process CLI smoke test also passed with 12 workers using bounded
CPU reads: two complete tiny-model generations match the local oracle's IDs
and logits hash `5122e042f9b1fb30` on macOS. The driver has no MoE weights and
each worker has only its assigned bins. This exercises actual worker startup,
placement arguments and clean shutdown as well as dispatch.

```sh
cargo test -p cascadia-engine-sparse-moe --test inkling_ep --test inkling_loader
cargo test -p cascadia-engine-sparse-moe --example inkling_ep_validate
python3 -m unittest discover -s tools/tests -p test_inkling_ep_full.py
python3 -m unittest discover -s tools/tests -p test_inkling_ep_fused_export.py
cargo build -p cascadia-engine-sparse-moe \
  --example inkling_ep_worker --example inkling_decode_bench
python3 tools/inkling_ep_smoke.py --bin-dir target/debug/examples \
  --workers 12 --stream-cpu-workers --out /tmp/inkling-smoke-12-NEW
```

The tiny export must exist at the fixture path; older integration tests skip
when it is missing. Validator negative tests reject changed values, tensor
order/count errors, nonfinite values and reference checksum corruption. Operator
tests reject missing GPU coverage, fallback, output mismatch and missing service
preservation evidence.

## Artifacts and reconstruction

[inkling-ep-full](inkling-ep-full/) contains the exact placement/cases, model
manifest, CPU reference reports and SHA256 manifests, full mapped comparison,
cache probe reports, and the native source snapshot atop `dce74385`.
`build-v7-provenance.json` identifies the successful distributed CPU binary;
`build-v10-provenance.json` identifies the GPU overflow correction. Both source
snapshots apply atop `060feeb2`; `run-builds.json` maps full runs to their builds.
Large f32 payloads stay in the isolated remote reference directories and the
session's `/private/tmp/inkling-ep-full/` directory rather than in Git.
`build-provenance.json` identifies native binaries and the snapshot checksum.

The full model files can be resumed with `inkling_ep_full_stage.py`; it verifies
each transferred file against the source SHA256 and records its size, mtime and
hash. `inkling_ep_full_fused.py` waits for verified layer inputs and checks the
exporter's source hashes against that journal. Both default to 48 MiB/s and
allow up to 96 MiB/s, with the same service/memory/disk guards. The temporary
source is restricted to the three NUC addresses and has a bounded lease.
The temporary miner HTTP source and its three task firewall rules have now
been removed; all unrelated firewall rules were preserved. Staging is complete
on all NUCs, and the union of their verified packed files covers all
16,588 source files with matching replicated checksums.
