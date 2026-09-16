# Inkling expert routing

The driver owns attention, routers, sequence state, dense layers, embedding
and the output head. Workers own assigned MoE experts. Each layer dispatches
selected experts concurrently, then restores their outputs to original row
and gate order before applying routing weights in FP32.

[Full-model validation](INKLING_FULL_MODEL_EP_VALIDATION.md) records exact
output parity between three and twelve iGPU worker processes on three physical
Panther Lake NUCs. It also explains the remaining CPU/GPU precision differences
and the checks required on twelve physical machines. No 25 tok/s result is
claimed. The earlier single-machine measurements remain in
[INKLING_SINGLE_BOX_BENCH.md](INKLING_SINGLE_BOX_BENCH.md).

## Placement and execution

`inkling/ep_placement.rs` validates complete expert coverage, owner indices,
replicas, dimensions, cost coefficients and per-worker packed-weight budgets.
Within each transport frame, all rows for a selected expert go to one eligible
owner. Selection considers ownership constraints and estimated read, compute
and dispatch costs; ties use worker index. These configured costs are estimates,
not measured throughput or automatic adaptation. Without an explicit placement,
ownership remains `expert_id % worker_count`.

The compact fused path uses K=1 GPU graphs and returns individual expert outputs.
All three compressed GEMMs and Swish execute on GPU. The driver applies original
weights and sums in original gate order, avoiding placement-dependent FP32
partial sums. `CASCADIA_INKLING_EP_FUSED_PARTIAL_SUMS=1` opts into the older
partial-sum path; it is excluded from the exact topology qualification.

Version-2 shards divide up-projection scales by 16. Host FP32 arithmetic restores
that factor before routing multiplication. This avoids two FP16 overflow cases
found during full-model generation. It does not make GPU arithmetic identical
to the original BF16 CPU path. The original packed weights remain unchanged.

A failed worker fails the request. Replies are drained on errors to preserve
frame alignment. There is no automatic failover, live resharding, expert dropping
or multi-driver scheduling.

## Prepare workers

Create a JSON array in the same order as the driver's endpoints. Each worker
needs `name`, `expert_capacity_bytes`, `read_us`, `compute_us`, and `dispatch_us`.
Reserve OS, KV, driver tensors, buffers and device allocations separately; packed
storage capacity is not a GPU-memory budget or proof that weights are resident.
Use costs measured on the intended storage, kernel and network.

```sh
python3 tools/inkling_ep_plan.py --manifest /models/inkling/manifest.json \
  --workers workers.json --out /tmp/inkling-placement
```

This creates `placement.json`, `storage.json`, and `worker-N.files`. Routed
experts have one owner by default; shared experts are replicated on every
worker. `--routed-replicas` and `--shared-replicas` control replication. Copy each
worker's listed files and the identical placement; keep all shells, dense bins,
embedding, head and tokenizer on the driver. Use the same checkpoint and verify
source hashes everywhere: the transport does not negotiate them.

For fused GPU workers, build owned shards from the packed export and a recipe
extracted from a compatible fused layer IR. These commands show one layer on
worker 0; repeat for every owned MoE layer and worker:

```sh
python3 tools/inkling_ep_fused_export.py recipe \
  --ir-layer /models/inkling/moe_ov/layer_02 --out /tmp/fused-recipe.json
python3 tools/inkling_ep_fused_export.py build \
  --recipe /tmp/fused-recipe.json --export /models/inkling-shard \
  --placement /models/placement.json --index 0 --layer 2 \
  --up-scale-exponent 4 --out /models/fused-k8/layer_02
python3 tools/inkling_ep_fused_export.py compact \
  --src /models/fused-k8/layer_02 --out /models/fused-k1/layer_02
```

The compact graph hardlinks the same blob. Source/derived hashes, expert IDs,
placement hash and scale metadata accompany each shard. The transactional
`inkling_ep_rebalance.py` can update existing isolated shards; stop their workers
first and preserve its journal until completion or rollback.

Start a GPU worker with the same placement and count as the driver:

```sh
CASCADIA_INKLING_EP_FUSED=1 \
CASCADIA_INKLING_EP_FUSED_DIR=/models/fused-k1 \
CASCADIA_INKLING_EP_FUSED_STREAM=1 \
CASCADIA_INKLING_EP_FUSED_CACHE_MB=2400 \
CASCADIA_INKLING_EP_REQUIRE_GPU=1 \
CASCADIA_INKLING_EP_FUSED_F16_WIRE=1 \
cascadia worker --model /models/inkling-shard --engine sparse-moe \
  --rank 0 --total 1 --ep-worker-index 0 --ep-worker-count 12 \
  --listen 0.0.0.0:9200 --ep-placement /models/placement.json
```

Streaming keeps compiled graphs while OpenVINO streams expert weights into
resident slots; cache admission is not a hard device-memory limit. Keep an
external memory guard. `REQUIRE_GPU` forbids CPU expert fallback.

Lossless wire replies encode FP16 values plus a power-of-two scale only when
**every value round-trips to its exact original FP32 bits**, including signed
zero. Otherwise they use FP32. All peers must support `ExpertResult` status 2
before enabling this option. It cuts raw decode tensor replies from 12 MiB to
6 MiB/token for this model; that is a byte count, not a throughput prediction.

For CPU workers, omit GPU flags. `CASCADIA_INKLING_EP_STREAM_CPU=1` uses bounded
reads; `CASCADIA_INKLING_EP_OWN_EXPERTS=1` instead retains assigned packed weights
and requires an explicit capacity-checked placement. Do not combine owned CPU
weights with the fused GPU path. The diagnostic
`CASCADIA_INKLING_EP_CPU_F16_REFERENCE=1` requires streamed CPU experts and models
FP16 boundaries; it does not replace the original CPU control.

Then launch the driver, listing every endpoint in placement order:

```sh
cascadia run /models/inkling --engine sparse-moe --api 127.0.0.1:8000 \
  --ep-workers "$EP_ENDPOINTS" --ep-placement /models/placement.json
```

Driver attention/head GPU settings are independent of expert routing and must
be qualified separately. The completed topology test kept those operations on
CPU. `CASCADIA_INKLING_MMAP_SHELLS=1` and `CASCADIA_INKLING_MMAP_HEAD=1` map the
original BF16 driver projections to reduce retained memory without changing bits.

## Build, test and measure

```sh
cargo test -p cascadia-engine-sparse-moe --test inkling_ep --test inkling_loader
cargo test -p cascadia-engine-sparse-moe --example inkling_ep_validate
python3 -m unittest discover -s tools/tests -p 'test_inkling_ep_*.py'
cargo build -p cascadia-engine-sparse-moe \
  --example inkling_decode_bench --example inkling_ep_worker
python3 tools/inkling_ep_smoke.py --bin-dir target/debug/examples \
  --workers 12 --stream-cpu-workers --out /tmp/ep-smoke-NEW
```

The native smoke test needs the tiny Inkling export fixture; it creates partial
worker exports and compares full greedy generation and logits against local
execution over real TCP. Python tests generate small synthetic inputs and do
not need benchmark archives, remote hosts or model downloads. OpenVINO-linked
paths require a real hardware check; the Windows build helpers are
`inkling_ep_build_windows.bat` and `inkling_ep_build_gpu_windows.bat`.

Use `inkling_decode_bench --ep-workers ... --ep-placement ...` for performance
runs after correctness passes. Preserve cold/warm state, reference IDs/logits,
source/binary identities and all worker settings. Driver cache/read counters
cover only the driver; `--warm-ov` does not warm remote experts. Measure actual
network latency/bandwidth and calibrate placement costs before comparing rates.

Generated logs, source snapshots, deployment dumps and historical per-layer
reports are kept on the
[evidence archive branch](https://github.com/labscommunity/cascadia/tree/archive/inkling-ep-validation-20260915/docs/perf).
Keep new experiment output outside tracked source, such as `experiments/`.
