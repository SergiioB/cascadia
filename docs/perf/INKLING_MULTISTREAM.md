# Inkling multi-stream decode (continuous batching across a pipeline)

The sparse-MoE pipeline engine served one request at a time: rank 0 popped a
task, prefilled it, then drove one token per step through every rank while
every other rank sat idle waiting for that one frame. This note describes the
multi-stream scheduler that replaces it for Inkling, what it is built on, how
it was validated, and what it means for a 12-box installation.

## What changed

**Per-stream sequence slots in the layers.** `ShortConv` and `AttentionLayer`
keep a pool of parked sequence states (the conv history ring, the KV cache,
their cursors). `select(slot)` makes one of them live by swapping buffers —
O(1), no copying — so one set of weights serves many sequences.
`Layer::forward_rows(xs, rows, slots)` decodes one token per stream: the
attention projections run once for all rows (the weights are read once per
step), attention and the convs run per row on that row's slot, and the MoE
runs all rows as one batch-union (each expert is read once for every stream
that chose it — the aggregate-throughput lever). Per row the op sequence is
`forward_token`'s, so a stream decoded in a batch is bit-identical to the same
stream decoded alone on the CPU kernels (`tests/inkling_streams.rs`).

**Runner surface.** `StagedRunner` gains `configure_streams`, `open_stream`,
`open_stream_at`, `close_stream`, `stream_pos`, `prefill_stream`,
`decode_streams`, `head_logits_rows` (all default to "unsupported", so dsv4 /
glm5 / OpenVINO runners are untouched). The Inkling runner implements them;
the OpenVINO head takes all rows in one call.

**Single-stage scheduler** (`CASCADIA_STREAMS=N`). Each `step`: admit up to
`CASCADIA_STREAMS_ADMIT` (default 1) pending tasks — tokenize, take a slot,
prefill, sample the first token; emit every active stream's pending token
(one `Chunk::token` per stream per step; the runner fans them out by task
id); retire finished streams; run one batched forward for the survivors and
sample each stream's next token with its own history and rng. A forward
panic fails the batch's tasks, not the process. Aggregate tok/s is logged
every 16 steps.

**Pipeline wire.** Four appended frame kinds: `StreamOpen` (prefill a slot on
every rank; the last rank seeds a per-slot sampler and replies the first
token), `StreamDecode` (one row per stream with `(slot, pos)`; every rank
decodes them as one batch on its own slots; the last rank samples each row
with its slot's sampler), `StreamClose` (free the slot everywhere),
`StreamTokens` (the reply). Every rank sets the same `CASCADIA_STREAMS`;
rank 0 picks slot ids, workers open the same ids.

**Groups in flight.** Rank 0 splits its streams into G groups
(`CASCADIA_STREAMS_INFLIGHT`, default = the rank count) and serves one group
per step: receive that group's outstanding replies — the oldest frames on
the wire, so the single reply FIFO stays ordered — admit new streams into it,
emit its ready tokens, retire finished streams, send one decode micro-batch.
Mid ranks wait on readiness of both sockets (a cancel-safe `peek`) and treat
a frame from upstream and a reply from downstream as independent events, so
G frames are in flight and every rank is busy on a different group's rows.
The last rank stays sequential.

## Why groups pay: the cost model

A resident rank's cost per micro-batch is a fixed part (the attention
weights, kernel launches) plus a part that grows with rows (experts touched
grows sub-linearly: 8 distinct experts for 1 row, ~45 for 8, ~137 for 32, all
258 past ~100 rows; attention per row). With one frame through R ranks in
series, a step costs `R · cost(S)` for S tokens. With G groups of S/G rows in
flight, a step costs `max(cost(S/G), R · cost(S/G) / G)` for S/G tokens: for
G ≥ R every rank is busy and the throughput is `(S/G) / cost(S/G)` — better
than the serial `S / (R · cost(S))` exactly because smaller frames are cheaper
per row. If the cost were constant per frame the two would be equal; the gain
is real because it is not. `tests/inkling_streams_overlap.rs` charges
`10 ms + 5 ms/row` per micro-batch on a 4-rank loopback pipeline and measures
one group vs four: same tokens, 1.5–2× less wall time.

## Validation

| test | what it shows |
|---|---|
| `inkling_streams.rs` | streams decoded in a batch are bit-identical (logits and greedy ids) to each stream alone, including a stream admitted mid-flight and a slot reused after close; the single-sequence path is unchanged and still reproduces the HF reference ids |
| `inkling_streams_wire.rs` | 3-rank loopback pipeline, 5 tasks over 3 slots (admission, finish, reuse): every task's tokens equal the single-stage engine's |
| `inkling_streams_overlap.rs` | groups in flight overlap the ranks (above) |
| local API run (`cascadia run`, fixture, `CASCADIA_STREAMS=4`) | four concurrent `/v1/completions` return exactly what the one-task path returns |
| the crate's 439 tests | no regression |

Not yet measured: real-model aggregate tok/s on hardware (tate-07 was
unreachable at the time of writing; the single-box script is
`t07_ms_serve.ps1` with `CASCADIA_STREAMS=1/4/8/16`), and a 12-box run.

## What to expect on the 12-box pipeline

From the per-layer numbers in `INKLING_SINGLE_BOX_BENCH.md` (resident
ranks, 5–6 layers per box):

| streams in flight | per-stream tok/s (CPU / iGPU) | aggregate tok/s (CPU / iGPU) |
|---|---|---|
| 12 (one per rank) | 1.7 / 2.7 | 20 / 33 |
| 96 (8 per rank) | 0.45 / 1.0 | 43 / 96 |
| 384 (32 per rank) | 0.15 / 0.35 | 59 / 135 |

Rank RAM per stream slot: about 10 MB per layer at `CASCADIA_INKLING_MAX_SEQ`
1024 (33 MB for a global-attention layer at 4096), so 32 slots on a 6-layer
rank cost ~2 GB. Windows keeps the iGPU at three fused MoE layers per 64 GB
box; the CPU column needs no OpenVINO on the boxes at all.

## Where expert-parallel fits

The expert-parallel star (PR #156) moves every token's hidden state to up to
eight workers per MoE layer and their expert outputs back: ~24 MB per token
through the driver's one NIC. On 2.5 GbE that caps the star at roughly 12
tok/s aggregate however many streams are batched (~25 with FP16 both ways);
the pipeline moves 288 KB per token. Expert-parallel is therefore the wrong
topology for aggregate throughput. Its place is (a) single-stream latency on
a switched LAN with sub-millisecond round trips — the scaling note puts it at
~1.5–2× the pipeline, unmeasured — and (b) the RAM-starved regime where boxes
cannot hold their layers and reading a token's experts on several NVMes at
once is worth 64 network rounds. For the installation, run the pipeline with
streams; keep the star as a fallback if boxes turn out smaller than 64 GB.

## Deploying 12 boxes offline

Rank `r` of 12 needs only its layer slice: `manifest.json`, the tokenizer
files, `shells/layer_NN.safetensors`, `experts/layer_NN/`, optionally
`attn_ov/layer_NN/`, plus `embed.safetensors` on rank 0 and
`head.safetensors` (+ `head_ov/`) on rank 11 — 36 to 48 GB per box, from the
export on the miner's portable SSD. Each box runs

```
cascadia worker --rank r --total 12 --engine sparse-moe --model <slice dir> \
  --listen :91<r> --next <ip of r+1>:91<r+1> [--api :8000 on rank 0]
```

with the promoted CPU read profile (`tools/inkling_autolab/ptl-profile.ps1`),
`CASCADIA_STREAMS=<slots>` identical on every rank, and, where the iGPU is
used, `CASCADIA_INKLING_OV_ATTN=1 CASCADIA_INKLING_OV_ATTN_DIR=attn_ov_int8
CASCADIA_INKLING_OV_ATTN_DROP_RUST=1 CASCADIA_INKLING_OV_HEAD=1` (last rank).
Start the last rank first, rank 0 last. The `cascadia-array` control plane
does exactly this for a ring of Windows boxes (bundled DHCP + mDNS, USB
enrollment, artifact pull over LAN HTTP, reverse-order start, health polls);
what it lacks for Inkling is the per-rank slice packaging, an env profile in
the plan, and a concurrent load generator — see its `docs/INKLING.md`.
