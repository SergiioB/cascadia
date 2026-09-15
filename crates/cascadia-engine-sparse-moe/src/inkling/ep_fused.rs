//! Resident fused GPU shards. A bounded IR-byte cache is an admission budget,
//! not a bound on driver allocations; deployment must also reserve host/GPU RAM.

use super::{loader::InklingManifest, ov_moe::OvMoe};
use crate::dist::{ExpertDispatchBody, EXPERT_PAD, MAX_BATCH_COUNT};
use serde::Deserialize;
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    sync::Mutex,
};

#[derive(Debug, Clone, Deserialize)]
pub struct FusedShardManifest {
    pub version: u32,
    pub layer: u32,
    pub hidden_size: usize,
    pub moe_intermediate: usize,
    pub k: usize,
    pub expert_ids: Vec<usize>,
    /// Optional read-only view of a parent IR. Global-to-local indices retain
    /// the parent expert order; only these assigned experts may be requested.
    #[serde(default)]
    pub view_expert_ids: Option<Vec<usize>>,
    pub padded_experts: usize,
    pub ir_bytes: u64,
    /// Version 2 attenuates the IR's up projection by 2^-n. Compensate in
    /// routing weights after the down GEMM, preventing FP16 intermediate overflow.
    #[serde(default)]
    pub up_scale_exponent: u8,
}

impl FusedShardManifest {
    fn validate(
        &self,
        model: &InklingManifest,
        layer: usize,
        owned: &[usize],
    ) -> Result<(), String> {
        if !((self.version == 1 && self.up_scale_exponent == 0)
            || (self.version == 2 && (1..=8).contains(&self.up_scale_exponent)))
            || self.layer as usize != layer
            || self.hidden_size != model.hidden_size
            || self.moe_intermediate != model.moe_intermediate
            || (self.k != 1 && self.k != model.top_k + model.n_shared_experts)
            || self.view_expert_ids.as_deref().unwrap_or(&self.expert_ids) != owned
            || !self.expert_ids.windows(2).all(|p| p[0] < p[1])
            || !owned.windows(2).all(|p| p[0] < p[1])
            || owned
                .iter()
                .any(|id| self.expert_ids.binary_search(id).is_err())
            || self
                .expert_ids
                .iter()
                .any(|id| *id >= model.num_experts + model.n_shared_experts)
            || self.padded_experts <= self.expert_ids.len()
            || owned.is_empty()
            || self.ir_bytes == 0
        {
            return Err(format!(
                "fused layer {layer}: shard metadata does not match model/ownership"
            ));
        }
        Ok(())
    }

    /// Preserve global routing, compensating only for versioned IR scaling.
    /// Only unused slots use the dedicated
    /// dummy expert, so scatter padding cannot overwrite a real expert weight.
    pub fn map_request(
        &self,
        body: &ExpertDispatchBody,
        weights: &[f32],
    ) -> Result<(Vec<i32>, Vec<f32>), String> {
        let (rows, k, h) = (body.rows as usize, body.k as usize, self.hidden_size);
        if body.layer != self.layer
            || rows == 0
            || rows > MAX_BATCH_COUNT as usize
            || k == 0
            || k > self.k
            || body.hidden_shape != [body.rows, h as u32, 1]
            || body.hidden.len() != rows * h
            || body.ids_shape != [body.rows, body.k, 1]
            || body.ids.len() != rows * k
            || weights.len() != rows * k
            || weights.iter().any(|w| !w.is_finite())
            || body.hidden.iter().any(|x| !x.is_finite())
        {
            return Err("invalid fused dispatch dimensions or nonfinite values".into());
        }
        let dummy = self.expert_ids.len() as i32;
        let mut ids = vec![dummy; rows * self.k];
        let mut mapped_weights = vec![0.; rows * self.k];
        for r in 0..rows {
            for j in 0..k {
                let id = body.ids[r * k + j];
                let weight = weights[r * k + j];
                if id == EXPERT_PAD {
                    if weight != 0. {
                        return Err("padded expert has nonzero weight".into());
                    }
                    continue;
                }
                if id < 0 || body.ids[r * k..r * k + j].contains(&id) {
                    return Err("negative or duplicate fused expert id".into());
                }
                if self
                    .view_expert_ids
                    .as_ref()
                    .is_some_and(|ids| ids.binary_search(&(id as usize)).is_err())
                {
                    return Err(format!("fused view does not own expert {id}"));
                }
                let local = self
                    .expert_ids
                    .binary_search(&(id as usize))
                    .map_err(|_| format!("fused shard does not own expert {id}"))?;
                ids[r * self.k + j] = local as i32;
                let compensated = weight * 2.0f32.powi(self.up_scale_exponent as i32);
                if !compensated.is_finite() {
                    return Err("fused routing compensation overflow".into());
                }
                mapped_weights[r * self.k + j] = compensated;
            }
        }
        Ok((ids, mapped_weights))
    }
}

struct Cached {
    runtime: OvMoe,
    used: u64,
    bytes: u64,
}

/// Keep weighted sums out of the plugin's FP16 output. K=1 returns the raw
/// expert result and applies its routing weight in f32. K>1 normalizes each
/// row's weights by a common power of two, then restores that factor in f32.
fn output_scaling(k: usize, exponent: u8, weights: &[f32]) -> Result<(Vec<f32>, Vec<f32>), String> {
    let scale = 2.0f32.powi(exponent as i32);
    if k == 1 {
        return Ok((vec![1.; weights.len()], vec![scale; weights.len()]));
    }
    let mut gpu = Vec::with_capacity(weights.len());
    let mut restore = Vec::with_capacity(weights.len() / k);
    for row in weights.chunks_exact(k) {
        let norm = row.iter().map(|w| w.abs() as f64).sum::<f64>().max(1.);
        let factor = 2.0f64.powf(norm.log2().ceil()) as f32;
        if !factor.is_finite() {
            return Err("fused output scaling exceeds f32 range".into());
        }
        gpu.extend(row.iter().map(|w| w / factor));
        restore.push(factor);
    }
    Ok((gpu, restore))
}

#[derive(Default)]
struct State {
    cache: HashMap<u32, Cached>,
    clock: u64,
    calls: u64,
    rows: u64,
    selected_expert_rows: u64,
    ordered_replies: u64,
    errors: u64,
    evictions: u64,
    profiles: HashMap<u32, String>,
}

pub struct FusedExpertBank {
    dir: PathBuf,
    layers: HashMap<u32, FusedShardManifest>,
    device: String,
    gpu_name: String,
    budget: u64,
    max_k: usize,
    max_rows: usize,
    stream: bool,
    state: Mutex<State>,
}

impl FusedExpertBank {
    pub fn load(
        dir: &Path,
        model: &InklingManifest,
        ownership: &[Vec<usize>],
        budget: u64,
    ) -> Result<Self, String> {
        let device =
            std::env::var("CASCADIA_INKLING_OV_MOE_DEVICE").unwrap_or_else(|_| "GPU".into());
        if device != "GPU" && !device.starts_with("GPU.") {
            return Err("fused EP requires a concrete GPU device".into());
        }
        let mut layers = HashMap::new();
        let stream = super::env_flag("CASCADIA_INKLING_EP_FUSED_STREAM");
        for (li, owned) in ownership
            .iter()
            .enumerate()
            .filter(|(_, ids)| !ids.is_empty())
        {
            let root = dir.join(format!("layer_{li:02}"));
            let meta: FusedShardManifest = serde_json::from_slice(
                &std::fs::read(root.join("shard.json")).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?;
            meta.validate(model, li, owned)?;
            let bytes = std::fs::metadata(root.join("openvino_model.bin"))
                .map_err(|e| e.to_string())?
                .len();
            if stream && meta.k != 1 {
                return Err("streaming fused EP requires compact K=1 graphs".into());
            }
            if bytes != meta.ir_bytes
                || admission_bytes(&meta, stream) > budget
                || !root.join("openvino_model.xml").is_file()
            {
                return Err(format!("fused layer {li}: missing IR, size mismatch, or exceeds IR cache budget {budget}"));
            }
            layers.insert(li as u32, meta);
        }
        let max_rows = std::env::var("CASCADIA_INKLING_EP_FUSED_ROWS")
            .unwrap_or_else(|_| "32".into())
            .parse::<usize>()
            .ok()
            .filter(|n| (1..=MAX_BATCH_COUNT as usize).contains(n))
            .ok_or("fused expanded-row chunk size must be 1..256")?;
        let gpu_name =
            cascadia_ov_genai_shim::device_full_name(&device).map_err(|e| e.to_string())?;
        Ok(Self {
            dir: dir.into(),
            layers,
            device,
            gpu_name,
            budget,
            max_k: model.top_k + model.n_shared_experts,
            max_rows,
            stream,
            state: Mutex::new(State::default()),
        })
    }

    /// Raw K=1 expert outputs use the ordinary EP reply shape. The driver
    /// applies weights in original gate order, independent of shard placement.
    pub fn serve_raw(&self, body: &ExpertDispatchBody) -> Result<Vec<f32>, String> {
        let weights: Vec<f32> = body
            .ids
            .iter()
            .map(|id| if *id == EXPERT_PAD { 0. } else { 1. })
            .collect();
        self.serve_compact(body, &weights, true)
    }

    /// K=1 graphs batch actual (token,expert) pairs as GPU rows. This avoids
    /// computing repeated dummy slots on workers assigned fewer than eight
    /// experts. The GPU still runs one fused compressed MoE graph per chunk.
    pub fn serve(&self, body: &ExpertDispatchBody, weights: &[f32]) -> Result<Vec<f32>, String> {
        self.serve_compact(body, weights, false)
    }

    fn serve_compact(
        &self,
        body: &ExpertDispatchBody,
        weights: &[f32],
        raw: bool,
    ) -> Result<Vec<f32>, String> {
        let meta = self
            .layers
            .get(&body.layer)
            .ok_or("fused shard has no requested layer")?;
        if meta.k != 1 {
            if raw {
                return Err("ordered fused replies require compact K=1 graphs".into());
            }
            return self.serve_one(body, weights);
        }
        let validation = FusedShardManifest {
            k: self.max_k,
            ..meta.clone()
        };
        validation.map_request(body, weights)?;
        let h = meta.hidden_size;
        let slots: Vec<usize> = body
            .ids
            .iter()
            .enumerate()
            .filter(|&(s, &id)| id != EXPERT_PAD && weights[s] != 0.)
            .map(|(s, _)| s)
            .collect();
        let mut out = vec![
            0.;
            if raw {
                body.ids.len() * h
            } else {
                body.rows as usize * h
            }
        ];
        let chunks = if self.stream {
            let mut grouped = std::collections::BTreeMap::<i32, Vec<usize>>::new();
            for &slot in &slots {
                grouped.entry(body.ids[slot]).or_default().push(slot);
            }
            grouped
                .values()
                .flat_map(|group| group.chunks(self.max_rows).map(<[usize]>::to_vec))
                .collect::<Vec<_>>()
        } else {
            slots.chunks(self.max_rows).map(<[usize]>::to_vec).collect()
        };
        // Streaming batches contain one unique expert, so repeated prompt rows
        // reuse its one resident slot. Retain outputs to reduce in ORIGINAL
        // routing order, preserving f32 addition order despite grouped I/O.
        let mut delayed = Vec::<(usize, Vec<f32>)>::new();
        for chunk in &chunks {
            let n = chunk.len() as u32;
            let mut expanded = ExpertDispatchBody {
                layer: body.layer,
                rows: n,
                k: 1,
                hidden: Vec::with_capacity(chunk.len() * h),
                hidden_shape: [n, h as u32, 1],
                ids: Vec::with_capacity(chunk.len()),
                ids_shape: [n, 1, 1],
            };
            let mut expanded_weights = Vec::with_capacity(chunk.len());
            for &slot in chunk {
                let r = slot / body.k as usize;
                expanded
                    .hidden
                    .extend_from_slice(&body.hidden[r * h..(r + 1) * h]);
                expanded.ids.push(body.ids[slot]);
                expanded_weights.push(weights[slot]);
            }
            // Keep every chunk of a large frame at the same GPU shape. The
            // fixed shape also bounds scratch space and avoids unnecessary
            // shape transitions between a full chunk and its tail.
            if !self.stream && slots.len() > self.max_rows && chunk.len() < self.max_rows {
                let last_row = expanded.hidden[expanded.hidden.len() - h..].to_vec();
                let last_id = *expanded.ids.last().unwrap();
                for _ in chunk.len()..self.max_rows {
                    expanded.hidden.extend_from_slice(&last_row);
                    expanded.ids.push(last_id);
                    expanded_weights.push(0.);
                }
                expanded.rows = self.max_rows as u32;
                expanded.hidden_shape[0] = self.max_rows as u32;
                expanded.ids_shape[0] = self.max_rows as u32;
            }
            let values = self.serve_one(&expanded, &expanded_weights)?;
            for (&slot, value) in chunk.iter().zip(values.chunks_exact(h)) {
                if raw {
                    out[slot * h..(slot + 1) * h].copy_from_slice(value);
                    continue;
                }
                if self.stream {
                    delayed.push((slot, value.to_vec()));
                    continue;
                }
                let r = slot / body.k as usize;
                for (o, &v) in out[r * h..(r + 1) * h].iter_mut().zip(value) {
                    *o += v;
                }
            }
        }
        delayed.sort_unstable_by_key(|(slot, _)| *slot);
        for (slot, value) in delayed {
            let r = slot / body.k as usize;
            for (o, v) in out[r * h..(r + 1) * h].iter_mut().zip(value) {
                *o += v;
            }
        }
        if out.iter().any(|x| !x.is_finite()) {
            return Err("nonfinite fused partial sum".into());
        }
        let mut state = self.state.lock().unwrap();
        state.selected_expert_rows += slots.len() as u64;
        state.ordered_replies += u64::from(raw);
        Ok(out)
    }

    fn serve_one(&self, body: &ExpertDispatchBody, weights: &[f32]) -> Result<Vec<f32>, String> {
        let meta = self
            .layers
            .get(&body.layer)
            .ok_or("fused shard has no requested layer")?;
        let (ids, mapped_weights) = meta.map_request(body, weights)?;
        let (gpu_weights, restore) =
            output_scaling(meta.k, meta.up_scale_exponent, &mapped_weights)?;
        // Serialize admission and inference so evicted models cannot remain
        // live in concurrent callers outside the accounting lock.
        let mut state = self.state.lock().unwrap();
        state.clock += 1;
        let clock = state.clock;
        if !state.cache.contains_key(&body.layer) {
            let bytes = admission_bytes(meta, self.stream);
            while state.cache.values().map(|c| c.bytes).sum::<u64>() + bytes > self.budget {
                let oldest = *state.cache.iter().min_by_key(|(_, c)| c.used).unwrap().0;
                state.cache.remove(&oldest);
                state.evictions += 1;
            }
            let runtime = OvMoe::new(
                self.dir.clone(),
                self.device.clone(),
                meta.hidden_size,
                meta.k,
                meta.expert_ids.len(),
                None,
                self.stream.then(|| stream_offload(meta).to_string()),
            )
            .requiring_fusion();
            state.cache.insert(
                body.layer,
                Cached {
                    runtime,
                    used: clock,
                    bytes,
                },
            );
        }
        let entry = state.cache.get_mut(&body.layer).unwrap();
        entry.used = clock;
        let mut result = entry.runtime.forward(
            body.layer,
            &body.hidden,
            body.rows as usize,
            &ids,
            &gpu_weights,
        );
        if let Some(values) = &mut result {
            let bf16_output = super::env_flag("CASCADIA_INKLING_EP_FUSED_BF16_OUTPUT");
            for (row, value) in values.chunks_exact_mut(meta.hidden_size).enumerate() {
                for v in value {
                    *v *= restore[row];
                    if meta.k == 1 {
                        if bf16_output {
                            *v = half::bf16::from_f32(*v).to_f32();
                        }
                        *v *= weights[row];
                    }
                }
            }
        }
        let profiles = entry.runtime.fusion_profiles();
        state.profiles.extend(profiles);
        match result {
            Some(values) if values.iter().all(|x| x.is_finite()) => {
                state.calls += 1;
                state.rows += body.rows as u64;
                Ok(values)
            }
            Some(values) => {
                state.errors += 1;
                let nonfinite = values.iter().filter(|x| !x.is_finite()).count();
                let message = format!(
                    "fused GPU nonfinite output: layer={} ids={:?} rows={} nonfinite={nonfinite}",
                    body.layer, body.ids, body.rows
                );
                eprintln!("{message}");
                if let Some(dir) = std::env::var_os("CASCADIA_INKLING_EP_DIAGNOSTICS_DIR") {
                    let path = PathBuf::from(dir).join(format!(
                        "failed-layer-{}-pid-{}-call-{}.json",
                        body.layer,
                        std::process::id(),
                        state.calls
                    ));
                    let save = || -> Result<(), Box<dyn std::error::Error>> {
                        let file = std::fs::OpenOptions::new()
                            .write(true)
                            .create_new(true)
                            .open(&path)?;
                        serde_json::to_writer(
                            std::io::BufWriter::new(file),
                            &serde_json::json!({
                            "layer":body.layer,"rows":body.rows,"k":body.k,"hidden":body.hidden,
                            "ids":body.ids,"weights":weights,"nonfinite_outputs":nonfinite,
                            "message":message}),
                        )?;
                        Ok(())
                    };
                    if let Err(e) = save() {
                        eprintln!("fused diagnostic write failed: {e}");
                    }
                }
                Err(message)
            }
            _ => {
                state.errors += 1;
                Err("required fused GPU execution failed; all fallback forbidden".into())
            }
        }
    }

    pub fn stats(&self) -> serde_json::Value {
        let s = self.state.lock().unwrap();
        serde_json::json!({"device":self.device,"gpu_name":self.gpu_name,"fused_required":true,
            "calls":s.calls,"rows":s.rows,"selected_expert_rows":s.selected_expert_rows,"errors":s.errors,"evictions":s.evictions,
            "cached_layers":s.cache.len(),"cached_ir_bytes":s.cache.keys().map(|l|self.layers[l].ir_bytes).sum::<u64>(),
            "cached_admission_bytes":s.cache.values().map(|c|c.bytes).sum::<u64>(),
            "streaming":self.stream,"admission_is_runtime_estimate":self.stream,
            "f32_output_weighting":true,"ordered_replies":s.ordered_replies,"bf16_output":super::env_flag("CASCADIA_INKLING_EP_FUSED_BF16_OUTPUT"),
            "ir_cache_budget_bytes":self.budget,"expanded_row_chunk":self.max_rows,"fusion_profiles":s.profiles,
            "graph_k":self.layers.iter().map(|(l,m)|(l.to_string(),m.k)).collect::<HashMap<_,_>>(),
            "up_scale_exponent":self.layers.iter().map(|(l,m)|(l.to_string(),m.up_scale_exponent)).collect::<HashMap<_,_>>(),
            "cached_runtime_call_ns":s.cache.values().map(|c|c.runtime.stats().call_ns).sum::<u64>(),
            "cached_runtime_compiles":s.cache.values().map(|c|c.runtime.stats().compiles).sum::<u64>(),
            "cached_runtime_compile_ns":s.cache.values().map(|c|c.runtime.stats().compile_ns).sum::<u64>()})
    }
}

/// Keep at least one expert slot even for the small asymmetric alpha shard.
fn stream_offload(meta: &FusedShardManifest) -> usize {
    100usize
        .saturating_sub(100usize.div_ceil(meta.padded_experts))
        .clamp(1, 99)
}

fn admission_bytes(meta: &FusedShardManifest, stream: bool) -> u64 {
    if !stream {
        return meta.ir_bytes;
    }
    let slots = (meta.padded_experts * (100 - stream_offload(meta)) / 100).max(1) as u64;
    // Admission estimate only: two copies of slot weights plus graph/request
    // overhead. The external guard remains responsible for measured memory.
    2 * meta.ir_bytes.div_ceil(meta.padded_experts as u64) * slots + (8 << 20)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> (FusedShardManifest, ExpertDispatchBody, Vec<f32>) {
        let meta = FusedShardManifest {
            version: 1,
            layer: 2,
            hidden_size: 2,
            moe_intermediate: 2,
            k: 4,
            expert_ids: vec![0, 3, 8],
            view_expert_ids: None,
            padded_experts: 4,
            ir_bytes: 100,
            up_scale_exponent: 0,
        };
        let body = ExpertDispatchBody {
            layer: 2,
            rows: 2,
            k: 2,
            hidden: vec![1., 2., 3., 4.],
            hidden_shape: [2, 2, 1],
            ids: vec![8, 0, 3, EXPERT_PAD],
            ids_shape: [2, 2, 1],
        };
        (meta, body, vec![0.75, -0.125, 0.2, 0.])
    }

    #[test]
    fn padding_never_aliases_real_ids_and_weights_are_not_renormalized() {
        let (meta, body, weights) = fixture();
        let (ids, mapped) = meta.map_request(&body, &weights).unwrap();
        assert_eq!(ids, vec![2, 0, 3, 3, 1, 3, 3, 3]);
        assert_eq!(mapped, vec![0.75, -0.125, 0., 0., 0.2, 0., 0., 0.]);
    }

    #[test]
    fn scaled_ir_compensates_signed_routes_and_preserves_padding() {
        let (mut meta, body, weights) = fixture();
        meta.version = 2;
        meta.up_scale_exponent = 4;
        let (_, mapped) = meta.map_request(&body, &weights).unwrap();
        assert_eq!(mapped, vec![12., -2., 0., 0., 3.2, 0., 0., 0.]);
        let mut overflow = weights;
        overflow[0] = f32::MAX;
        assert!(meta.map_request(&body, &overflow).is_err());
    }

    #[test]
    fn output_scaling_retains_large_signed_results_outside_fp16_range() {
        let (gpu, restore) = output_scaling(1, 4, &[1600.]).unwrap();
        assert_eq!(gpu, vec![1.]);
        // Raw down = 1,800; routing = 100. Only the f32 result is 180,000.
        assert_eq!((1800. / 16.) * restore[0] * 100., 180_000.);
        let weights = [1600., -800., 0., 0.];
        let (gpu, restore) = output_scaling(4, 4, &weights).unwrap();
        assert!(gpu.iter().map(|w| w.abs()).sum::<f32>() <= 1.);
        assert_eq!(
            gpu.iter().map(|w| w * restore[0]).collect::<Vec<_>>(),
            weights
        );
        assert!(output_scaling(2, 0, &[f32::MAX, f32::MAX]).is_err());
    }

    #[test]
    fn readonly_view_preserves_parent_indices_and_rejects_unassigned_experts() {
        let (mut meta, mut body, weights) = fixture();
        let mut model: InklingManifest = serde_json::from_str(include_str!(
            "../../tests/fixtures/inkling_export/manifest.json"
        ))
        .unwrap();
        model.hidden_size = 2;
        model.moe_intermediate = 2;
        model.num_experts = 7;
        model.n_shared_experts = 2;
        model.top_k = 2;
        meta.view_expert_ids = Some(vec![0, 8]);
        assert!(meta.validate(&model, 2, &[0, 8]).is_ok());
        assert!(meta.validate(&model, 2, &[0, 3]).is_err());
        assert!(meta.map_request(&body, &weights).is_err()); // parent owns 3, view does not
        body.ids[2] = 8;
        let (ids, _) = meta.map_request(&body, &weights).unwrap();
        assert_eq!(ids, [2, 0, 3, 3, 2, 3, 3, 3]);
        meta.view_expert_ids = Some(vec![8, 0]);
        assert!(meta.validate(&model, 2, &[8, 0]).is_err());
        meta.view_expert_ids = Some(vec![0, 7]);
        assert!(meta.validate(&model, 2, &[0, 7]).is_err());
    }

    #[test]
    fn malformed_or_unowned_routes_are_rejected_before_gpu_execution() {
        let (meta, body, weights) = fixture();
        let mut bad = body.clone();
        bad.ids[0] = 7;
        assert!(meta.map_request(&bad, &weights).is_err());
        bad.ids[0] = 0;
        assert!(meta.map_request(&bad, &weights).is_err());
        let mut w = weights.clone();
        w[3] = 0.1;
        assert!(meta.map_request(&body, &w).is_err());
        w[3] = f32::NAN;
        assert!(meta.map_request(&body, &w).is_err());
        bad = body.clone();
        bad.k = u32::MAX;
        assert!(meta.map_request(&bad, &weights).is_err());
        bad = body.clone();
        bad.hidden_shape = [1, 4, 1];
        assert!(meta.map_request(&bad, &weights).is_err());
    }
}
