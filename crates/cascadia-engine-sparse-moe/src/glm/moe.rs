//! GLM-5.2 MoE block: `out = Σ_{i∈topk} w_i·expert_i(x) + shared(x)`.
//!
//! Router logits are computed in f32 (no bf16 rounding — a plain
//! f32 `matmul`), scored by the sigmoid + `noaux_tc` gate ([`crate::glm::gate`]),
//! whose weights already carry `routed_scaling_factor`. Each routed expert and
//! the always-on shared expert is a SwiGLU FFN ([`crate::glm::ffn`]).
//! Accumulation order: routed experts in gate order, then the shared
//! expert.
//!
//! The first `first_k_dense_replace` (3) layers are dense (no routing) — that
//! path just calls `ffn::swiglu` directly and does not use this module.

use std::sync::{Arc, Mutex};

use super::ffn::{swiglu, swiglu_f32w, swiglu_mmap};
use super::gate::moe_gate;
use super::ov_expert::OvExperts;
use super::prof;
use super::residency::UsageStats;
use crate::dsv4::expert_mmap::MmapExpert;
use crate::dsv4::math::linear_f32;

/// One expert's SwiGLU weights (bf16 bits) — the synthetic-golden / shell path.
pub struct ExpertW {
    pub wg: Vec<u16>, // [inter, hidden]
    pub wu: Vec<u16>, // [inter, hidden]
    pub wd: Vec<u16>, // [hidden, inter]
}

/// How an expert's weights are held, per its numeric contract:
/// - `Bf16`: bf16-bit weights (goldens; the shell's native dtype).
/// - `EagerF32`: int4-dequantized f32 weights (the on-disk `int4_bin` path).
///   int4 values are not exactly bf16-representable, so they stay f32 and run
///   through [`swiglu_f32w`] (same op order / bf16 activation boundaries as
///   `swiglu`, only the weight dtype differs).
pub enum AnyExpert {
    Bf16(ExpertW),
    EagerF32 {
        wg: Vec<f32>,
        wu: Vec<f32>,
        wd: Vec<f32>,
    },
    /// File-backed int4 bin, rows dequantized on the fly. The complete routed
    /// table need not be resident (eager f32 uses much more memory).
    Mmap(MmapExpert),
    /// An owned copy of the packed int4 bytes. The mapping supplies the same
    /// validated kernel layout but is not read or prefetched during compute.
    /// Private pages can still be paged out by the OS; this is not page locking.
    OwnedInt4 {
        layout: MmapExpert,
        bytes: Vec<u8>,
    },
}

/// Light-R1 read path: explicit concurrent whole-expert reads instead of
/// mmap-fault-on-touch. Opt-in via `CASCADIA_GLM5_R1READ` (measured ~1.4× on
/// NVMe; a no-op / possibly worse on slow disks). Read once.
fn r1_read() -> bool {
    use std::sync::OnceLock;
    static E: OnceLock<bool> = OnceLock::new();
    *E.get_or_init(|| crate::glm::env_flag("CASCADIA_GLM5_R1READ"))
}

/// Hot/cold split mode for the overlapped decode path (`CASCADIA_GLM5_HOTCOLD`).
#[derive(Clone, Copy, PartialEq, Debug)]
enum HotCold {
    /// Residency-probe each routed expert; only mostly-non-resident ones take
    /// the background-read path. The production setting (`=1`).
    Probe,
    /// Treat every mmap routed expert as cold, forcing the background-read +
    /// overlap machinery on every slot (`=cold`) — deterministic coverage for
    /// tests and an upper bound for read-path benchmarks.
    ForceCold,
}

/// Parse `CASCADIA_GLM5_HOTCOLD`. Off-values follow [`crate::glm::env_flag`]
/// (unset/empty/`0`/`false`/`no`/`off`); `cold` forces the read path; anything
/// else enables residency-probed splitting.
fn parse_hotcold(v: Option<&str>) -> Option<HotCold> {
    let v = v.map(str::trim).unwrap_or("");
    if v.is_empty()
        || v == "0"
        || v.eq_ignore_ascii_case("false")
        || v.eq_ignore_ascii_case("no")
        || v.eq_ignore_ascii_case("off")
    {
        None
    } else if v.eq_ignore_ascii_case("cold") {
        Some(HotCold::ForceCold)
    } else {
        Some(HotCold::Probe)
    }
}

/// Hot/cold overlapped decode: split each token's routed experts into HOT
/// (resident) and COLD (mostly non-resident). HOT experts compute straight
/// from their resident mmap pages while COLD experts' bins are read
/// concurrently on background I/O threads, so the cold READS overlap the hot +
/// shared compute (exposed ≈ `max(hot+shared compute, cold reads)`); the cold
/// experts' own GEMVs then run in the drain, so the total is that max plus the
/// cold compute — the win is hiding the reads, not the cold compute.
/// (Probe mode does the residency split; ForceCold treats every mmap expert as
/// cold — see [`HotCold`].) Opt-in via `CASCADIA_GLM5_HOTCOLD`; supersedes
/// `CASCADIA_GLM5_R1READ` when both are set (R1 reads every routed bin up-front
/// and serializes reads before compute; this path skips resident bins entirely
/// and overlaps).
///
/// The split-and-overlap design follows FreeToken (Yang et al.,
/// arXiv:2608.16157), which divides expert cache-misses between the transfer
/// and host-compute paths and runs both branches concurrently; on Cascadia's
/// UMA fleet the two bandwidth pools are page-cache-resident compute vs NVMe
/// reads. Read once.
fn hot_cold() -> Option<HotCold> {
    use std::sync::OnceLock;
    static E: OnceLock<Option<HotCold>> = OnceLock::new();
    *E.get_or_init(|| parse_hotcold(std::env::var("CASCADIA_GLM5_HOTCOLD").ok().as_deref()))
}

/// Warn ONCE per process that hot/cold cold reads are falling back to the mmap
/// kernel. Output stays bit-identical, so without this a systematically
/// failing overlap (bad model store, I/O errors, thread exhaustion) is
/// invisible — the operator asked for the overlap and silently isn't getting
/// it. Once is enough: this fires in the decode hot path, per token-layer.
fn warn_hotcold_fallback(n: usize, err: Option<&str>) {
    use std::sync::Once;
    static W: Once = Once::new();
    W.call_once(|| {
        eprintln!(
            "[glm5] hotcold: {n} cold read(s) fell back to the mmap kernel ({}); \
             output is correct but those experts are not overlapped",
            err.unwrap_or("reader failure"),
        );
    });
}

impl AnyExpert {
    /// One expert's SwiGLU FFN for token `x`. `inter` is this expert's
    /// intermediate width (routed = `moe_inter`, shared = `moe_inter·n_shared`).
    pub fn forward(&self, x: &[f32], hidden: usize, inter: usize) -> Vec<f32> {
        match self {
            AnyExpert::Bf16(e) => swiglu(x, &e.wg, &e.wu, &e.wd, hidden, inter),
            AnyExpert::EagerF32 { wg, wu, wd } => swiglu_f32w(x, wg, wu, wd, hidden, inter),
            AnyExpert::Mmap(m) => swiglu_mmap(m, x),
            AnyExpert::OwnedInt4 { layout, bytes } => layout.swiglu_from(bytes, x),
        }
    }
}

impl AnyExpert {
    /// Copy packed bytes once, avoiding repeated expert-file reads. Other
    /// storage variants already own their weights and pass through unchanged.
    pub fn into_owned_int4(self) -> std::io::Result<Self> {
        match self {
            Self::Mmap(layout) => {
                let bytes = layout.read_bytes()?;
                if bytes.len() != layout.bin_len() {
                    return Err(std::io::Error::new(
                        std::io::ErrorKind::InvalidData,
                        "expert size changed while loading owned bytes",
                    ));
                }
                Ok(Self::OwnedInt4 { layout, bytes })
            }
            other => Ok(other),
        }
    }

    pub fn owned_int4_bytes(&self) -> usize {
        match self {
            Self::OwnedInt4 { bytes, .. } => bytes.len(),
            _ => 0,
        }
    }

    /// The mmap'd int4 expert, if this is the `Mmap` variant (for pinning).
    pub fn as_mmap(&self) -> Option<&MmapExpert> {
        match self {
            AnyExpert::Mmap(m) => Some(m),
            _ => None,
        }
    }

    /// On-disk int4 bytes this expert streams at 0% cache hit. Only the `Mmap`
    /// variant touches the disk; eager/bf16 and owned-int4 experts are already
    /// resident, so 0.
    #[inline]
    pub fn int4_bytes(&self) -> usize {
        match self {
            AnyExpert::Mmap(m) => m.bin_len(),
            _ => 0,
        }
    }

    /// `madvise(WILLNEED)` hint (mmap experts only; no-op otherwise).
    #[inline]
    pub fn prefetch(&self) {
        if let AnyExpert::Mmap(m) = self {
            m.prefetch();
        }
    }
}

impl From<ExpertW> for AnyExpert {
    fn from(e: ExpertW) -> Self {
        AnyExpert::Bf16(e)
    }
}

pub struct MoeWeights {
    /// Router projection `[n_experts, hidden]`, kept f32 (logits are not
    /// bf16-rounded).
    pub router_w: Vec<f32>,
    /// `e_score_correction_bias` `[n_experts]`.
    pub router_bias: Vec<f32>,
    /// `n_experts` routed experts, each `moe_inter`-wide.
    pub experts: Vec<AnyExpert>,
    /// The shared expert (`moe_inter · n_shared`-wide).
    pub shared: AnyExpert,
}

pub struct MoeLayer {
    pub hidden: usize,
    pub n_experts: usize,
    pub top_k: usize,
    pub moe_inter: usize,
    pub shared_inter: usize,
    pub scale: f32, // routed_scaling_factor
    w: MoeWeights,
    /// Optional routing recorder (learned-pin). None on the golden path.
    usage: Option<Arc<Mutex<UsageStats>>>,
    /// This layer's GLOBAL index (for the usage histogram key AND the OV IR
    /// `layer_NN` lookup).
    layer_idx: u32,
    /// Optional OpenVINO expert backend (iGPU / NPU / CPU), shared across all
    /// layers. `Some` only when `CASCADIA_GLM5_OV_EXPERTS=1` and the model ships
    /// an `experts_ov/` dir; then each routed / shared expert runs its compiled
    /// OV IR instead of the Rust int4 kernel. `None` keeps the default path.
    ov: Option<Arc<OvExperts>>,
}

impl MoeLayer {
    /// Rows per batch-union block. Bounds the intermediate expert-output storage
    /// (`ROW_BLOCK · top_k · hidden` f32) while keeping enough rows per block for
    /// heavy expert overlap. Correctness is independent of this value.
    const ROW_BLOCK: usize = 128;

    #[allow(clippy::too_many_arguments)]
    pub fn new(
        hidden: usize,
        n_experts: usize,
        top_k: usize,
        moe_inter: usize,
        shared_inter: usize,
        scale: f32,
        w: MoeWeights,
    ) -> Self {
        assert_eq!(w.router_w.len(), n_experts * hidden);
        assert_eq!(w.router_bias.len(), n_experts);
        assert_eq!(w.experts.len(), n_experts);
        Self {
            hidden,
            n_experts,
            top_k,
            moe_inter,
            shared_inter,
            scale,
            w,
            usage: None,
            layer_idx: 0,
            ov: None,
        }
    }

    /// Attach the learned-pin routing recorder + this layer's global index.
    pub fn attach_usage(&mut self, layer_idx: u32, usage: Arc<Mutex<UsageStats>>) {
        self.layer_idx = layer_idx;
        self.usage = Some(usage);
    }

    /// Attach the shared OpenVINO expert backend (opt-in). When set, routed and
    /// shared experts run their compiled OV IRs (keyed by this layer's global
    /// `layer_idx`) instead of the Rust int4 kernel. No-op unless the loader
    /// built an [`OvExperts`] from the env + `experts_ov/` dir.
    pub fn attach_ov(&mut self, ov: Arc<OvExperts>) {
        self.ov = Some(ov);
    }

    /// The routed experts (for pinning enumeration).
    pub fn experts(&self) -> &[AnyExpert] {
        &self.w.experts
    }

    /// The shared expert (always active — a top pin candidate).
    pub fn shared(&self) -> &AnyExpert {
        &self.w.shared
    }

    /// Prefetch the experts this layer is most likely to fire next — the shared
    /// expert (always active) + the `n` hottest routed experts from the
    /// learned-pin histogram (if attached). Best-effort `madvise(WILLNEED)`; no
    /// effect on output. Issued for the NEXT layer while the current one
    /// computes, so the expert reads overlap compute instead of stalling.
    pub fn prefetch_hot(&self, n: usize) {
        self.w.shared.prefetch();
        if let Some(u) = &self.usage {
            if let Ok(g) = u.lock() {
                for e in g.hottest_for(self.layer_idx, n) {
                    if let Some(exp) = self.w.experts.get(e as usize) {
                        exp.prefetch();
                    }
                }
            }
        }
    }

    /// Predict this layer's routed experts for a proxy hidden `x` — the SAME
    /// router GEMV + `noaux_tc` top-k as [`Self::forward_token`], but returning
    /// only the selected ids (no expert compute, no KV, no profiler mutation).
    /// Byte-identical selection to `forward_token` for identical `x`; recall <
    /// 100% comes only from `x` being a proxy for the true next-layer input.
    pub fn predict_topk(&self, x: &[f32]) -> Vec<u32> {
        debug_assert_eq!(x.len(), self.hidden);
        let mut logits = vec![0.0f32; self.n_experts];
        linear_f32(
            x,
            &self.w.router_w,
            self.n_experts,
            self.hidden,
            &mut logits,
        );
        moe_gate(&logits, &self.w.router_bias, self.top_k, self.scale, true).idx
    }

    /// Predict this layer's routed experts from `proxy` for the async prefetch
    /// worker, recording them for the recall metric and returning the ids for the
    /// caller to residency-gate + enqueue (the worker does the warming).
    pub fn predict_experts(&self, proxy: &[f32]) -> Vec<u32> {
        let pred = self.predict_topk(proxy);
        prof::note_predicted(self.layer_idx, &pred);
        pred
    }

    /// Miss-only gate: is routed expert `eid` currently NOT resident (worth
    /// warming)? Probes the working set; a mostly-resident expert returns false
    /// so the prefetch worker never spends bandwidth re-reading a hot expert.
    /// Non-mmap experts are always "resident" (already in RAM) -> never enqueued.
    pub fn expert_cold(&self, eid: u32) -> bool {
        match self
            .w
            .experts
            .get(eid as usize)
            .and_then(AnyExpert::as_mmap)
        {
            Some(m) => {
                let (resident, probed) = m.resident_pages_sampled(8);
                probed > 0 && resident * 2 < probed // < ~50% resident -> cold
            }
            None => false,
        }
    }

    /// In Probe mode the residency probe (`mincore` / `QueryWorkingSetEx`) may be
    /// unavailable — an unsupported target, or a failing syscall — in which case
    /// `resident_pages_sampled` returns `(0, 0)`, `expert_cold` reports every
    /// expert resident, and the whole hot/cold split silently becomes a no-op
    /// (all-hot, no overlap). Warn once so the operator who opted into the
    /// overlap knows it is not happening. ForceCold does not probe, so skip it.
    fn warn_if_probe_unavailable(&self, mode: HotCold) {
        use std::sync::Once;
        static W: Once = Once::new();
        if mode != HotCold::Probe {
            return;
        }
        W.call_once(|| {
            if self.residency_probe_dead() {
                eprintln!(
                    "[glm5] hotcold: residency probe unavailable on this platform; \
                     running all-hot (no read overlap)"
                );
            }
        });
    }

    /// True when the residency probe (`mincore` / `QueryWorkingSetEx`) is dead
    /// on this platform: an mmap routed expert exists but its working-set query
    /// samples nothing (`probed == 0`), so `expert_cold` reports every expert
    /// resident and any miss-only gate (hot/cold, prefill streaming) silently
    /// stands down. No mmap experts -> nothing to probe, not dead.
    pub fn residency_probe_dead(&self) -> bool {
        self.w
            .experts
            .iter()
            .find_map(AnyExpert::as_mmap)
            .is_some_and(|m| m.resident_pages_sampled(8).1 == 0)
    }

    /// This layer's routed-expert bin table for the LOOKAHEAD worker (paths + sizes;
    /// `None` per expert on the non-mmap path).
    pub fn expert_bins(&self) -> super::lookahead::LayerBins {
        let routed = self
            .w
            .experts
            .iter()
            .map(|e| {
                e.as_mmap()
                    .map(|m| (m.bin_path().to_path_buf(), m.bin_len() as u64))
            })
            .collect();
        super::lookahead::LayerBins { routed }
    }

    /// MoE for one token `x` (`[hidden]`). Returns `[hidden]`.
    pub fn forward_token(&self, x: &[f32]) -> Vec<f32> {
        assert_eq!(x.len(), self.hidden);
        let t_router = std::time::Instant::now();
        // router logits (f32) -> sigmoid + noaux_tc gate.
        let mut logits = vec![0.0f32; self.n_experts];
        linear_f32(
            x,
            &self.w.router_w,
            self.n_experts,
            self.hidden,
            &mut logits,
        );
        let gate = moe_gate(&logits, &self.w.router_bias, self.top_k, self.scale, true);
        // record the routing for learned-pin (no-op when no recorder attached).
        if let Some(u) = &self.usage {
            if let Ok(mut g) = u.lock() {
                for &e in &gate.idx {
                    g.record(self.layer_idx, e);
                }
            }
        }
        prof::add(prof::ROUTER, t_router);

        // Decode-profiler residency accounting: the 0%-hit streaming baseline
        // (on-disk int4 bytes) for this layer's routed + shared experts, plus
        // the cross-token reuse set. Branch-independent — counts what WOULD be
        // read regardless of which compute path runs. No-op unless
        // CASCADIA_GLM5_PROFILE is set.
        if prof::enabled() {
            for &e in &gate.idx {
                prof::note_selection(self.layer_idx, e);
                let ex = &self.w.experts[e as usize];
                prof::note_expert_bytes(ex.int4_bytes());
                // Probe residency BEFORE compute faults the pages in, so it
                // reflects whether this token's access hit RAM.
                if let Some(m) = ex.as_mmap() {
                    let (res, probed) = m.resident_pages_sampled(8);
                    prof::note_residency(res, probed);
                }
            }
            prof::note_expert_bytes(self.w.shared.int4_bytes());
            if let Some(m) = self.w.shared.as_mmap() {
                let (res, probed) = m.resident_pages_sampled(8);
                prof::note_residency(res, probed);
            }
        }

        // routed experts in gate order, then the shared expert.
        let t_exp = std::time::Instant::now();
        let mut out = vec![0.0f32; self.hidden];
        // Set only by the hot/cold path, which computes the shared expert
        // during the overlap window; every other path computes it below.
        let mut shared_pre: Option<Vec<f32>> = None;
        if let Some(ov) = &self.ov {
            // OpenVINO backend (opt-in): each routed expert runs its compiled OV
            // IR on the configured device (iGPU / NPU / CPU). `routed` returns the
            // UNSCALED bf16 output (or `None` -> fall back to the Rust kernel for
            // that expert); the gate weight is applied here in f32, matching the
            // Rust path's `out += wj * expert(x)` — so prefill and decode agree.
            for (&e, &wj) in gate.idx.iter().zip(&gate.weight) {
                let y = ov
                    .routed(self.layer_idx as usize, e as usize, x)
                    .unwrap_or_else(|| {
                        self.w.experts[e as usize].forward(x, self.hidden, self.moe_inter)
                    });
                for (o, &yi) in out.iter_mut().zip(&y) {
                    *o += wj * yi;
                }
            }
        } else if let Some(mode) = hot_cold() {
            // Hot/cold overlapped reads (FreeToken-style, arXiv:2608.16157):
            // classify each routed expert hot/cold (Probe residency-probes,
            // ForceCold marks every mmap expert cold), read the COLD bins on
            // background I/O threads (whole-bin sequential into an owned buffer
            // we compute from directly — same read as R1; warming the page
            // cache is only a side effect), and compute the HOT experts + the
            // shared expert from resident pages meanwhile. Expert outputs
            // land in per-slot buffers and are accumulated in gate order
            // below, so the result is bit-identical to every other path.
            let k = gate.idx.len();
            let mut ys: Vec<Option<Vec<f32>>> = Vec::with_capacity(k);
            ys.resize_with(k, || None);
            let is_cold: Vec<bool> = gate
                .idx
                .iter()
                .map(|&e| match mode {
                    // Non-mmap experts are RAM-resident; never "cold".
                    HotCold::ForceCold => self.w.experts[e as usize].as_mmap().is_some(),
                    HotCold::Probe => self.expert_cold(e),
                })
                .collect();
            let ncold = is_cold.iter().filter(|&&c| c).count();
            prof::note_hotcold(k - ncold, ncold);
            self.warn_if_probe_unavailable(mode);
            if ncold == 0 {
                // Everything resident: plain mmap compute — no threads, no
                // buffer copies. The zero-overhead steady state.
                for (slot, &e) in gate.idx.iter().enumerate() {
                    ys[slot] =
                        Some(self.w.experts[e as usize].forward(x, self.hidden, self.moe_inter));
                }
            } else {
                // Cold reads that fail fall back to mmap (bit-identical), so a
                // systematically failing overlap is otherwise invisible behind
                // correct output — count the fallbacks and keep the first error.
                let mut cold_fail = 0usize;
                let mut cold_err: Option<String> = None;
                std::thread::scope(|s| {
                    // Launch the cold reads first so NVMe is busy for the
                    // whole hot-compute window. One thread per cold bin: the
                    // reads are I/O-bound, so they must NOT ride the rayon
                    // pool the hot GEMVs are saturating.
                    let mut readers = Vec::with_capacity(ncold);
                    for (slot, &e) in gate.idx.iter().enumerate() {
                        if !is_cold[slot] {
                            continue;
                        }
                        let ex = &self.w.experts[e as usize];
                        // A cold classification always implies an mmap expert;
                        // the `None` arm is defensive, computing hot rather than
                        // panicking if that ever stops holding.
                        match ex.as_mmap() {
                            Some(m) => {
                                match std::thread::Builder::new()
                                    .spawn_scoped(s, move || m.read_bytes())
                                {
                                    Ok(h) => readers.push((slot, h)),
                                    // The OS refused a thread (fd/thread
                                    // exhaustion — the resource-pressured
                                    // regime this path targets). Read inline
                                    // (still off the GEMV, just not overlapped)
                                    // rather than let the spawn panic take down
                                    // the whole decode.
                                    Err(_) => {
                                        ys[slot] = Some(match m.read_bytes() {
                                            Ok(b) => m.swiglu_from(&b, x),
                                            Err(e) => {
                                                cold_fail += 1;
                                                cold_err.get_or_insert_with(|| e.to_string());
                                                ex.forward(x, self.hidden, self.moe_inter)
                                            }
                                        })
                                    }
                                }
                            }
                            None => ys[slot] = Some(ex.forward(x, self.hidden, self.moe_inter)),
                        }
                    }
                    for (slot, &e) in gate.idx.iter().enumerate() {
                        if !is_cold[slot] {
                            ys[slot] = Some(self.w.experts[e as usize].forward(
                                x,
                                self.hidden,
                                self.moe_inter,
                            ));
                        }
                    }
                    // The shared expert fires every token and is the
                    // always-active pin candidate — extra hot compute to hide
                    // the reads behind.
                    shared_pre = Some(self.w.shared.forward(x, self.hidden, self.shared_inter));
                    // Drain the reads; a failed read or a panicked reader
                    // thread falls back to the mmap kernel for that expert
                    // (same value, just faults) and is counted so the fallback
                    // is not silent.
                    for (slot, h) in readers {
                        let ex = &self.w.experts[gate.idx[slot] as usize];
                        let buf = match h.join() {
                            Ok(Ok(b)) => Some(b),
                            Ok(Err(e)) => {
                                cold_fail += 1;
                                cold_err.get_or_insert_with(|| e.to_string());
                                None
                            }
                            Err(_) => {
                                cold_fail += 1;
                                cold_err.get_or_insert_with(|| "reader thread panicked".into());
                                None
                            }
                        };
                        ys[slot] = Some(match (buf, ex.as_mmap()) {
                            (Some(b), Some(m)) => m.swiglu_from(&b, x),
                            _ => ex.forward(x, self.hidden, self.moe_inter),
                        });
                    }
                });
                if cold_fail > 0 {
                    prof::note_hotcold_fail(cold_fail);
                    warn_hotcold_fallback(cold_fail, cold_err.as_deref());
                }
            }
            // Accumulate in gate order — the exact op order of forward_token's
            // other branches, so hot/cold stays bit-identical.
            for (slot, &wj) in gate.weight.iter().enumerate() {
                let y = ys[slot].take().expect("every routed slot computed");
                for (o, &yi) in out.iter_mut().zip(&y) {
                    *o += wj * yi;
                }
            }
        } else if r1_read() {
            // Light-R1: read the routed experts' whole bins up-front and
            // CONCURRENTLY (off the compute path, at full sequential bandwidth),
            // then compute from the buffers — instead of faulting mmap pages in
            // mid-GEMV one expert at a time. Bit-identical to the mmap path.
            use rayon::prelude::*;
            let bufs: Vec<Option<Vec<u8>>> = gate
                .idx
                .par_iter()
                .map(|&e| {
                    self.w.experts[e as usize]
                        .as_mmap()
                        .and_then(|m| m.read_bytes().ok())
                })
                .collect();
            for (slot, (&e, &wj)) in gate.idx.iter().zip(&gate.weight).enumerate() {
                let ex = &self.w.experts[e as usize];
                let y = match (bufs[slot].as_ref(), ex.as_mmap()) {
                    (Some(b), Some(m)) => m.swiglu_from(b, x),
                    _ => ex.forward(x, self.hidden, self.moe_inter),
                };
                for (o, &yi) in out.iter_mut().zip(&y) {
                    *o += wj * yi;
                }
            }
        } else {
            for (&e, &wj) in gate.idx.iter().zip(&gate.weight) {
                let y = self.w.experts[e as usize].forward(x, self.hidden, self.moe_inter);
                for (o, &yi) in out.iter_mut().zip(&y) {
                    *o += wj * yi;
                }
            }
        }
        let s = match shared_pre {
            // Hot/cold path: already computed during the read-overlap window.
            Some(s) => s,
            None => match &self.ov {
                Some(ov) => ov
                    .shared(self.layer_idx as usize, x)
                    .unwrap_or_else(|| self.w.shared.forward(x, self.hidden, self.shared_inter)),
                None => self.w.shared.forward(x, self.hidden, self.shared_inter),
            },
        };
        for (o, &si) in out.iter_mut().zip(&s) {
            *o += si;
        }
        prof::add(prof::EXPERTS, t_exp);
        out
    }

    /// Batch-union MoE for `rows` tokens (`xs` is `[rows, hidden]`), returning
    /// `[rows, hidden]`. **Bit-identical** to calling [`Self::forward_token`] per
    /// row — same router, same per-row gate-order accumulation — but each unique
    /// routed expert is visited once and computes all of its assigned rows back
    /// to back, so its int4 weights (an mmap page fault or a dequant) are paid
    /// for once and stay hot. This is the prefill / batched-verify path; at high
    /// node counts it cuts the NVMe traffic that dominates, since a prompt's
    /// tokens route to heavily overlapping experts. Rows are processed in blocks
    /// so the intermediate storage stays bounded (dedup is within a block).
    pub fn forward_batch(&self, xs: &[f32], rows: usize) -> Vec<f32> {
        assert_eq!(xs.len(), rows * self.hidden);
        let mut out = vec![0.0f32; rows * self.hidden];
        let mut lo = 0;
        while lo < rows {
            let hi = (lo + Self::ROW_BLOCK).min(rows);
            self.forward_block(xs, lo, hi, &mut out);
            lo = hi;
        }
        out
    }

    /// Batch-union over rows `[lo, hi)`, writing into `out[lo..hi]`.
    fn forward_block(&self, xs: &[f32], lo: usize, hi: usize, out: &mut [f32]) {
        let (hidden, k) = (self.hidden, self.top_k);
        let nblk = hi - lo;

        // 1. Route every row in the block; record the (expert -> occurrences)
        //    map and the per-slot expert/weight, exactly as forward_token would.
        let mut slot_w = vec![0.0f32; nblk * k]; // gate weight per (blockrow, slot)
        let mut occ: Vec<Vec<u32>> = vec![Vec::new(); self.n_experts]; // expert -> [blockrow*k+slot]
        let mut logits = vec![0.0f32; self.n_experts];
        for br in 0..nblk {
            let x = &xs[(lo + br) * hidden..(lo + br + 1) * hidden];
            // `linear_f32` overwrites every element, so no pre-zeroing needed.
            linear_f32(x, &self.w.router_w, self.n_experts, hidden, &mut logits);
            let gate = moe_gate(&logits, &self.w.router_bias, k, self.scale, true);
            if let Some(u) = &self.usage {
                if let Ok(mut g) = u.lock() {
                    for &e in &gate.idx {
                        g.record(self.layer_idx, e);
                    }
                }
            }
            for (slot, (&e, &wj)) in gate.idx.iter().zip(&gate.weight).enumerate() {
                let s = br * k + slot;
                slot_w[s] = wj;
                occ[e as usize].push(s as u32);
            }
        }

        // 2. Dedup compute: one visit per unique routed expert, its rows hot.
        let mut ey = vec![0.0f32; nblk * k * hidden]; // expert output per (blockrow, slot)
        for (e, slots) in occ.iter().enumerate() {
            if slots.is_empty() {
                continue;
            }
            for &s in slots {
                let br = (s as usize) / k;
                let x = &xs[(lo + br) * hidden..(lo + br + 1) * hidden];
                let y = match &self.ov {
                    // Unscaled expert output; the gate weight is applied in the
                    // gate-order accumulation pass below (matching forward_token).
                    // `None` -> fall back to the Rust kernel for this expert.
                    Some(ov) => ov
                        .routed(self.layer_idx as usize, e, x)
                        .unwrap_or_else(|| self.w.experts[e].forward(x, hidden, self.moe_inter)),
                    None => self.w.experts[e].forward(x, hidden, self.moe_inter),
                };
                ey[s as usize * hidden..(s as usize + 1) * hidden].copy_from_slice(&y);
            }
        }

        // 3. Per row: accumulate experts in gate order, then shared — the exact
        //    op order of forward_token, so the result is bit-for-bit identical.
        for br in 0..nblk {
            let x = &xs[(lo + br) * hidden..(lo + br + 1) * hidden];
            let o = &mut out[(lo + br) * hidden..(lo + br + 1) * hidden];
            for slot in 0..k {
                let s = br * k + slot;
                let wj = slot_w[s];
                let y = &ey[s * hidden..(s + 1) * hidden];
                for (oo, &yi) in o.iter_mut().zip(y) {
                    *oo += wj * yi;
                }
            }
            // Shared expert through OV too (or Rust fallback) — mirrors
            // forward_token so prefill stays bit-identical to per-token decode.
            let sh = match &self.ov {
                Some(ov) => ov
                    .shared(self.layer_idx as usize, x)
                    .unwrap_or_else(|| self.w.shared.forward(x, hidden, self.shared_inter)),
                None => self.w.shared.forward(x, hidden, self.shared_inter),
            };
            for (oo, &si) in o.iter_mut().zip(&sh) {
                *oo += si;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A zeroed EagerF32 expert of the given shape (predict_topk never touches
    /// expert weights, so shape is all that matters for building a `MoeLayer`).
    fn zero_expert(hidden: usize, inter: usize) -> AnyExpert {
        AnyExpert::EagerF32 {
            wg: vec![0.0; inter * hidden],
            wu: vec![0.0; inter * hidden],
            wd: vec![0.0; hidden * inter],
        }
    }

    /// `predict_topk` must reproduce `forward_token`'s selection exactly: same
    /// router GEMV orientation (`[n_experts, hidden]` row-major), same `noaux_tc`
    /// top-k. Craft a router whose expert order is unambiguous and assert the ids.
    #[test]
    fn predict_topk_selects_the_router_topk() {
        let (hidden, n_experts, top_k, inter) = (4usize, 6usize, 2usize, 2usize);
        // Row e = router_w[e*hidden .. e*hidden+hidden]; with x=[1,0,0,0] the
        // logit for expert e is exactly column 0 = router_w[e*hidden].
        let col0 = [0.1f32, 0.9, 0.2, 0.8, 0.3, 0.05];
        let mut router_w = vec![0.0f32; n_experts * hidden];
        for (e, &v) in col0.iter().enumerate() {
            router_w[e * hidden] = v;
        }
        let w = MoeWeights {
            router_w,
            router_bias: vec![0.0; n_experts],
            experts: (0..n_experts).map(|_| zero_expert(hidden, inter)).collect(),
            shared: zero_expert(hidden, inter),
        };
        let layer = MoeLayer::new(hidden, n_experts, top_k, inter, inter, 1.0, w);

        // Highest logits are expert 1 (0.9) then expert 3 (0.8); gate returns ids
        // in descending-score order.
        let pred = layer.predict_topk(&[1.0, 0.0, 0.0, 0.0]);
        assert_eq!(pred, vec![1, 3]);

        // A different one-hot input must re-rank: x=[0,1,0,0] reads column 1,
        // which is all-zero here, so it selects the two lowest ids (tie-break).
        let pred2 = layer.predict_topk(&[0.0, 1.0, 0.0, 0.0]);
        assert_eq!(pred2, vec![0, 1]);
    }

    /// `CASCADIA_GLM5_HOTCOLD` parsing: off-values match `env_flag`'s off set,
    /// `cold` forces the read path, anything else probes.
    #[test]
    fn hotcold_env_parse() {
        for off in [
            None,
            Some(""),
            Some("  "),
            Some("0"),
            Some("false"),
            Some("no"),
            Some("OFF"),
        ] {
            assert_eq!(parse_hotcold(off), None, "{off:?} must disable");
        }
        for cold in ["cold", "COLD", " cold "] {
            assert_eq!(parse_hotcold(Some(cold)), Some(HotCold::ForceCold));
        }
        for on in ["1", "true", "probe", "yes"] {
            assert_eq!(
                parse_hotcold(Some(on)),
                Some(HotCold::Probe),
                "{on:?} must probe"
            );
        }
    }
}
