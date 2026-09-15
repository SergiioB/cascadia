# Inkling expert routing: implementation and qualification

For the subsequent fused GPU implementation and measured comparison, see
[INKLING_FUSED_EXPERT_SHARDING.md](INKLING_FUSED_EXPERT_SHARDING.md).
The later [full-model correctness qualification](INKLING_FULL_MODEL_EP_VALIDATION.md)
records exact GPU output parity between 3 and 12 workers on three physical NUCs.
The results and limitations below describe the earlier per-expert implementation.

Branch: `feat/inkling-expert-routing`, based on the completed iGPU branch at
`f660b51885204837b6bfe28fb44049767fb8a5d9`. Worktree:
`/Users/tatef/Workspaces/tahoma-inkling-ep`. Date: 2026-09-15.

This extends the existing Inkling EP transport with explicit, capacity-checked
expert placement and replica selection. The driver keeps all 66 layers'
attention/router/sequence state, dense MLPs, embedding and head. Workers hold
only their assigned MoE experts. Each layer's selected experts execute across
workers concurrently. More physical memory controllers can therefore serve a
token's expert reads at the same time; additional processes on one machine
share its bandwidth and do not provide that scaling.

**No new full-model tokens/s record is claimed here.** The implementation is
qualified with complete tiny-model inference on macOS and Windows/tate-07,
and the production routing algorithm was replayed on recorded 975B routes.
The subsequent [three-NUC LAN qualification](INKLING_NUC_EXPERT_PARALLEL.md)
passed complete tiny-model generation and measured a 2.10× mean speedup for one
resident real-weight MoE layer, including dispatch/gather. Actual full-model
multi-machine decode throughput remains unmeasured.

## Starting measurements

The completed iGPU work is documented in [INKLING_SINGLE_BOX_BENCH.md](INKLING_SINGLE_BOX_BENCH.md).
The best single-box hybrid result was **1.236 tok/s minimum / 1.263 median**
over nine runs: all attention projections and the output head on Arc B390,
Rust CPU experts with a 24 GiB cache. The int8 projections change some output
tokens, so this is separate from the exact CPU record **1.1161344306 tok/s**
([CPU reproduction](https://github.com/labscommunity/cascadia/blob/fdcc043370ebc0dc56da414e94edf5b037f8b778/tools/inkling_autolab/INKLING_129_REPRODUCTION.md)).
The resident fused GPU MoE result covered three MoE layers, with the remaining
expert layers on CPU; it was not a resident 975B GPU run.

## What changed

- `inkling/ep_placement.rs`: per-layer expert ownership, optional replicas,
  per-worker packed-weight budgets and calibrated cost coefficients. Rejects
  incomplete coverage, duplicate/out-of-range owners, incompatible dimensions,
  invalid costs and over-budget placements before loading experts.
- Each dispatch assigns **unique experts**, processing experts with fewer
  eligible owners first, then those serving more rows. It chooses the owner
  with the lowest estimated finish time:
  `assigned_cost + read_us + row_count * compute_us + first_dispatch_us`.
  Ties use worker index. Coefficients are configured estimates, not adaptive
  measurements or a tokens/s prediction. An expert's rows stay on one worker
  within a frame, allowing its weights to be read once.
- Workers receive only rows they use. Results are scattered back into original
  row/slot order. Gate choices, weights, top-k and the final accumulation order
  are unchanged. CPU experts retain bit-for-bit equality to the local CPU path.
- Workers group prefill work by expert, reusing one temporary read buffer across
  that expert's rows. `CASCADIA_INKLING_EP_OWN_EXPERTS=1` instead copies the
  assigned packed int4 weights once at startup and computes from those bytes;
  it requires an explicit capacity-checked placement. This avoids repeated
  whole-bin copies on resident Windows workers. Owned pages can still page out
  if the configured budget exceeds available physical memory.
- Workers can use the existing per-expert OpenVINO backend via
  `CASCADIA_INKLING_OV_EXPERTS=1`. It consumes existing per-expert IRs, with the
  backend's CPU fallback and cache limits. The subsequent
  [iGPU LAN qualification](INKLING_IGPU_EXPERT_ROUTING.md) verifies per-expert
  GPU execution with `CASCADIA_INKLING_EP_REQUIRE_GPU=1`, which forbids fallback.
  Distributed GPU phase outputs match the local GPU reference; CPU bit equality
  does not extend to different GPU numerics or mixed CPU/GPU replicas.
  Full fused 256-expert MoE IRs are not sharded by this change.
- `--ep-placement` is available on `cascadia run`, `cascadia worker`, and
  `inkling_decode_bench`. The benchmark loads no MoE bins on its driver and
  labels a 975B distributed run `full_large_model_expert_parallel_decode`.
  Its local cache/read counters cover the driver process only.

Default placement remains `expert_id % worker_count` when no plan is supplied.
The transport still gathers raw expert outputs and sums on the driver; there
is no lossy reduction, expert dropping, speculative routing, or weight update.
All worker replies are drained on an error, preserving frame alignment.

## Build and check

```sh
cargo test -p cascadia-engine-sparse-moe --test 'inkling_*'
cargo test -p cascadia-cli --lib --no-default-features
python3 -m unittest tools/tests/test_inkling_ep_plan.py
cargo build -p cascadia-engine-sparse-moe \
  --example inkling_decode_bench --example inkling_ep_worker
python3 tools/inkling_ep_smoke.py --bin-dir target/debug/examples --out /tmp/ep-smoke
python3 tools/inkling_ep_smoke.py --bin-dir target/debug/examples \
  --out /tmp/ep-smoke-owned --owned-workers
```

The smoke test creates partial fixture exports: driver without MoE bins, each
worker with only its assigned bins and manifest. It runs three separate worker
processes over real TCP, two complete greedy generations, and compares every
generated token and the complete logits hash to a local run. It stops only its
own child processes. Output directories must be new.

macOS qualification: 89 Inkling integration tests, 85 CLI tests, three Python
planner tests; mmap and owned-worker process tests produce the same local
reference hash `5122e042f9b1fb30`. Windows qualification uses
`tools/inkling_ep_qualify_windows.bat PYTHON_EXE NEW_RESULTS_DIR`: nine EP tests
and both process modes passed, with local reference hash `1f7cd0eb14a22662`;
see saved
artifacts under [inkling-ep](inkling-ep/). Hashes are compared **within each
platform**, since kernel numerics differ across architectures. These are
four-layer, hidden-size-64 fixtures, not partial 975B performance estimates.

On tate-07 this task uses `C:\Users\devcloud\inkling-ep-20260915`, its own source
and target directory. The existing `inkling-igpu`, `inkling-autolab` exports,
record binaries, OVMS and Cascadia services remain separate. No export or
Lambda instance is needed for these changes.

## Generate a placement and copy only assigned files

Prepare a workers JSON array, in the same order as the driver's endpoints.
Each entry has `name`, `expert_capacity_bytes`, `read_us`, `compute_us`, and
`dispatch_us`. Reserve OS, buffers, KV, shells and any device copies separately.
Use measurements from the actual worker storage/kernel and interconnect for
costs. The [12-worker example](inkling-ep/workers-12.example.json) uses
**illustrative costs**, twelve 48 GiB expert budgets, and no real host identities.

```sh
python3 tools/inkling_ep_plan.py --manifest /models/inkling/manifest.json \
  --workers workers.json --out /tmp/inkling-placement
```

The generator writes `placement.json`, `storage.json`, and `worker-N.files`.
Routed experts have one owner by default; shared experts are replicated on
every worker. `--routed-replicas N` and `--shared-replicas N` change that
tradeoff. Insufficient capacity fails instead of emitting a paging plan.
Every real 975B expert is 31,850,496 packed bytes. The example uses
47,552,790,528–47,584,641,024 bytes (about 44.3 GiB) per worker, including
the shared replicas. **One 64 GiB PTL cannot hold that entire placement.**

Copy the exact same `placement.json` to driver and workers. For a Unix worker,
for example:

```sh
rsync -av --files-from=/tmp/inkling-placement/worker-0.files \
  /models/inkling/ worker0:/models/inkling-shard/
scp /tmp/inkling-placement/placement.json worker0:/models/placement.json
```

Copy lists contain the original `manifest.json` and assigned int4 bins only;
no re-export is needed. If enabling GPU experts, separately copy the matching
assigned `experts_ov/layer_NN/expert_*/openvino_model.{xml,bin}` files and
configure that worker's OV cache budget. The packed-weight budget does not
bound OpenVINO allocations. Use the same source checkpoint/export and the same
plan everywhere; the protocol does not negotiate placement or weight hashes.

Start each worker, with its own index and the same count (example for index 0):

```sh
CASCADIA_INKLING_EP_OWN_EXPERTS=1 cascadia worker \
  --model /models/inkling-shard --engine sparse-moe --rank 0 --total 1 \
  --ep-worker-index 0 --ep-worker-count 12 --listen 0.0.0.0:9200 \
  --ep-placement /models/placement.json
```

Then the driver (`--ep-workers` must enumerate **all** endpoints in plan order):

```sh
cascadia run /models/inkling --engine sparse-moe --api 127.0.0.1:8000 \
  --ep-workers "$EP_ENDPOINTS" --ep-placement /models/placement.json
```

The driver can use the iGPU attention/head settings already qualified by the
other branch. Dense layers also remain on the driver. Local full-layer fused
MoE compilation is excluded when loading a driver without MoE weights.

## Benchmark and tune on physical workers

Use direct worker connections; an SSH jump host used for administration does
not itself create a fast worker-to-worker data path. Measure RTT tails and
available bandwidth on the actual endpoints before copying hundreds of GB.

```sh
cargo build --release -p cascadia-engine-sparse-moe --example inkling_decode_bench
target/release/examples/inkling_decode_bench --export /models/inkling \
  --cases cases.json --tokens 64 --samples 3 --out ep-result.json \
  --ep-workers "$EP_ENDPOINTS" --ep-placement /models/placement.json \
  --layer-profile ep-layers.json --route-trace ep-routes.json
```

Use the existing three reference prompts and 64 greedy tokens. Score the
slowest of nine samples, with 63 timed decode steps per sample; loading and
prefill are reported separately. Retain cold/warm state, exact source/binary
identities, worker environment, placement and endpoint list with every run.
For CPU qualification, compare token IDs **and** the logits hash with the
control. If intentionally changing GPU numerics, report divergence explicitly
as the existing iGPU benchmark does. `--warm-ov` warms driver backends only;
it does not establish that every remote expert is compiled/resident.

Compare modulo, shared replicas, and additional routed replicas at the same
physical worker count and resource budgets. Log worker compute with trace-level
`inkling::ep` events and driver dispatch times/payload sizes at debug level.
Recalibrate cost coefficients, then rerun on held-out prompts. No automatic
failover, live resharding or multi-driver scheduling is implemented in this
change. A failed worker fails the request rather than silently skipping experts.

## Recorded-route replay (not model execution)

The source is the nine-sample CPU record's
`tools/inkling_autolab/results/129-second-prefetch-confirmation-routes.json.gz`,
output hash `ce0fbb9a116d3d09`. The accompanying
[975B manifest](inkling-ep/manifest-975b.json) records the manifest fields read
from tate-07's complete export. Replay skips prefill and adds both shared
experts to every decode-layer route.

```sh
python3 tools/inkling_ep_plan.py --manifest docs/perf/inkling-ep/manifest-975b.json \
  --workers docs/perf/inkling-ep/workers-12.example.json --out /tmp/ep-plan12
gzip -dc tools/inkling_autolab/results/129-second-prefetch-confirmation-routes.json.gz > /tmp/routes129.json
cargo run -p cascadia-engine-sparse-moe --example inkling_ep_replay -- \
  --manifest docs/perf/inkling-ep/manifest-975b.json \
  --placement /tmp/ep-plan12/placement.json --routes /tmp/routes129.json --out /tmp/replay.json
```

[Saved replay](inkling-ep/replay-129-12workers.json), 36,288 decode-layer dispatches:

| Routing load | Modulo | Explicit placement + shared replicas |
|---|---:|---:|
| Mean experts on busiest worker | 2.2121 | 1.8743 |
| p99 experts on busiest worker | 4 | 3 |
| Maximum experts on busiest worker | 6 | 5 |
| Mean involved workers | 6.1385 | 6.9155 |

This is about 15.3% fewer experts on the busiest worker on average, with more
network fanout and extra stored replicas. The selector itself averaged 5.17 µs
per layer in this unoptimized macOS replay. These figures exclude weights,
network and kernels and cannot be converted directly into a tokens/s speedup
or a claim of reaching 25 tok/s.
