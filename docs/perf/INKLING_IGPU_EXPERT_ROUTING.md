# Inkling expert routing on three iGPUs

For the subsequent fused GPU implementation and measured comparison, see
[INKLING_FUSED_EXPERT_SHARDING.md](INKLING_FUSED_EXPERT_SHARDING.md).
The results and limitations below describe the earlier per-expert implementation.

2026-09-15, branch `feat/inkling-expert-routing`. This follows the
[CPU LAN qualification](INKLING_NUC_EXPERT_PARALLEL.md). The earlier 2.10×
CPU result did not establish GPU support or GPU performance.

**Per-expert OpenVINO iGPU routing is now physically qualified on alpha,
beta and charlie. The newer fused, full-layer MoE backend is still not
sharded by this implementation.** No full-975B GPU generation rate is claimed.

## GPU execution evidence and implementation

The worker's expert bank calls `OvExperts::expert` for selected experts, using
the exact same placement and transport as the CPU implementation. This path
uses `experts_ov/layer_NN/expert_*/openvino_model.{xml,bin}`. The driver applies
gate weights and sums raw expert results in the original order.

The old deployed executables had no `openvino` build feature. These runs use
new executables built with that feature, and private copies of the SDK's
runtime DLLs under each isolated deployment's `bin-gpu/`. No existing system
OpenVINO install or inference service was changed.

`CASCADIA_INKLING_EP_REQUIRE_GPU=1` now:

- Rejects a missing OpenVINO expert backend, non-GPU device selection, a failed
  device query, or missing XML/bin pairs for any owned expert.
- Queries the device's real name; all three reported
  `Intel(R) Graphics (iGPU)` for device `GPU`.
- Fails a dispatch if a GPU call fails. It never runs that expert on the CPU
  as a fallback. This applies to production `cascadia worker` as well as the
  benchmark worker because both load the same expert bank.

Backend counters record successful OpenVINO calls, cache hits/misses, fallbacks
and actual Rust CPU expert calls. The worker example prints start/final JSON;
the bank's load log includes backend information and `backend_stats()` exposes
the counters to callers. All worker and local-GPU runs recorded **zero CPU
calls and zero fallbacks**. Two unit tests check rejection of a CPU-only bank
and that a strict dispatch cannot execute its CPU fallback. Nine EP integration
tests still pass, including full tiny-model CPU routing parity.

## Measured scope and numerics

Same real int4 expert weights, placement, 36 layer-2 route frames and synthetic
hidden inputs as the CPU LAN experiment; six routed and two shared experts per
frame. No attention, dense layers, head, prefill or token generation runs in
this probe. Each worker has four CPU threads for host work, while alpha's
network driver uses two separate CPUs. The expert math runs on the iGPUs.

GPU precision is f32 with dynamic activation quantization disabled. The
per-expert backend rounds the output to bf16, while the Rust implementation
also rounds intermediate gate/up results. Against the CPU reference, the GPU
output therefore has **0.0029394 relative RMS (0.294%)**, maximum absolute
error 0.02734375. The preselected acceptance limit was 0.005 (0.5%). This is
numerical qualification of expert outputs, not proof of full-model greedy
token parity with CPU.

The distributed GPU output matches the local GPU reference **bit for bit**,
and every additional warm and timed output matches that GPU reference. In the
two-warm-pass experiment, workers reported 550, 450 and 440 successful GPU
expert calls respectively. Their sum, 1,440, equals
`(2 warm passes + 3 timed passes) * 36 frames * 8 experts`, covering every
selected expert. The one-GPU control also reports 1,440 GPU calls.

## Performance, including the initial outliers

Each row below represents 108 timed phase evaluations, excluding its explicitly
specified warm-up. Both raw runs are retained; no timed observations were dropped.

| Warm-up protocol | One iGPU mean / median | Three iGPUs mean / median | Ratio of means |
|---|---:|---:|---:|
| One complete warm pass | 4.790 / 4.767 ms | 11.131 / 3.998 ms | 0.43× |
| Two complete warm passes | 4.808 / 4.780 ms | 3.595 / 3.473 ms | **1.34×** |

The first distributed run had 396.77 and 383.17 ms at its first two timed
evaluations; its remaining two repetition means were 3.997 and 3.529 ms.
That first run was slower on average despite a better median. The follow-up
uses new processes and two explicit warm passes on both sides. Its distributed
p95 was 4.995 ms and maximum 5.471 ms. This supports a modest resident GPU
phase speedup under that warm protocol; it does not establish the underlying
cause of the initial spikes or guarantee similar latency for newly encountered
experts, cold requests or a full-model workload.

The routing cost coefficients remain illustrative, not calibrated to these
GPU timings. The 1.34× result includes LAN dispatch/gather. Do not compare it
to the earlier CPU 2.10× as if both were full-model measurements. The group
still has only about 95 GiB physical memory, well below the complete export's
roughly 549 GB before OS/service/runtime reserves.

## Configuration and reproduction

```text
CASCADIA_INKLING_OV_EXPERTS=1
CASCADIA_INKLING_OV_DEVICE=GPU
CASCADIA_INKLING_EP_REQUIRE_GPU=1
CASCADIA_INKLING_OV_CACHE=128
CASCADIA_INKLING_OV_CACHE_MB=6000
CASCADIA_INKLING_OV_PRECISION=f32
CASCADIA_INKLING_OV_DQ_GROUP=0
```

`CASCADIA_INKLING_EP_OWN_EXPERTS` was unset: retaining a second owned CPU
copy would consume memory unnecessarily. The packed-file placement budget
does not itself bound OpenVINO allocations; the GPU cache and process guard
provide additional limits.

Build with `tools/inkling_ep_build_gpu_windows.bat` and `INTEL_OPENVINO_DIR`
pointing to the SDK. Exact argument lists, environment, affinities and lease
limits are saved as each host's `gpu-*.job.json` in
[inkling-ep-igpu](inkling-ep-igpu/). The two-pass jobs add `--warm-passes 2`.
Use new job labels and output/reference paths when reproducing. Workers use
the same direct LAN endpoints and lifecycle as the CPU qualification.

The existing IRs came from
`tate-07:C:/Users/devcloud/inkling-igpu/model/experts_ov/layer_02`. Their blobs
contain the original packed weight bytes plus 36 bytes of scalar/shape data.
`inkling_ep_ir_recipe.py` records original XML, constant offsets, tiny scalar
data and the IR blob SHA256. `inkling_ep_repack_ir.py` reconstructs those bytes
from the already staged packed bins and **requires the SHA256 of every result
to match the original IR**. This avoids transferring the weight bytes again;
it performs no new export, dequantization or quantization and needs no Python
OpenVINO package. The compressed recipe is retained with the artifacts.
Reconstruction used below-normal priority, two host CPUs, a 48 MiB/s write
rate and the existing CI/memory/disk reserves.

Validate the saved proof and recompute the timing summaries with:

```sh
python3 tools/inkling_ep_igpu_report.py \
  --artifacts docs/perf/inkling-ep-igpu --out /tmp/inkling-igpu-routing.json
```

## Coexistence and remaining work

All jobs used the bounded guard. Existing OVMS/Cascadia/runner processes kept
their PIDs and creation times, and final OVMS live/ready checks returned 200
on every NUC. No benchmark processes/listeners or temporary firewall rules
remain. The GPU runtime and IR files remain under the isolated task root;
final free disk was 182.67 / 537.82 / 600.47 GiB. CPU and GPU artifacts are
separate, including the first GPU run with outliers.

This qualifies **per-expert GPU execution and routing**. It does not integrate
`OvMoe` or partition its fused 256-expert constants across owners. That next
implementation needs shard-local expert IDs/IRs, a batched GPU dispatch path,
explicit GPU memory accounting, and comparison against the fused single-iGPU
backend. The current bank retains one compiled IR per expert and separate
expert calls, which limits scaling. Full-model decode/quality and the 25 tok/s
target remain unverified.
