//! Capacity-checked expert placement and deterministic replica selection.
//!
//! Placement changes where E(x) runs, never which experts the gate selects.
//! Costs are measured/configured microseconds, not claimed model throughput.

use std::path::Path;

use serde::{Deserialize, Serialize};

use super::loader::InklingManifest;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EpWorkerCost {
    pub name: String,
    /// Budget for packed expert weights only; reserve shells, KV and runtime
    /// memory separately. This is checked capacity, not a residency guarantee.
    pub expert_capacity_bytes: u64,
    /// Cost of fetching one unique expert's weights for a dispatch frame.
    pub read_us: f64,
    /// Additional cost per input row using an expert.
    pub compute_us: f64,
    /// Round trip / launch cost, paid once per involved worker per frame.
    pub dispatch_us: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EpPlacement {
    pub version: u32,
    pub hidden_size: usize,
    pub moe_intermediate: usize,
    pub num_experts: usize,
    pub n_shared_experts: usize,
    pub expert_bytes: u64,
    /// Index order must match --ep-workers and --ep-worker-index.
    pub workers: Vec<EpWorkerCost>,
    /// Absolute layer -> expert id -> eligible worker indices. Dense layers
    /// have an empty table; every MoE expert has at least one owner.
    pub layers: Vec<Vec<Vec<usize>>>,
}

impl EpPlacement {
    pub fn read(path: &Path, model: &InklingManifest, workers: usize) -> Result<Self, String> {
        let plan: Self = serde_json::from_slice(
            &std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?,
        )
        .map_err(|e| format!("{}: {e}", path.display()))?;
        plan.validate(model, workers)?;
        Ok(plan)
    }

    pub fn validate(&self, model: &InklingManifest, workers: usize) -> Result<(), String> {
        if self.version != 1 {
            return Err(format!("unsupported EP placement version {}", self.version));
        }
        if self.hidden_size != model.hidden_size
            || self.moe_intermediate != model.moe_intermediate
            || self.num_experts != model.num_experts
            || self.n_shared_experts != model.n_shared_experts
            || self.layers.len() != model.num_layers
        {
            return Err("EP placement dimensions do not match the model manifest".into());
        }
        if workers == 0 || self.workers.len() != workers {
            return Err(format!(
                "EP placement has {} workers, expected {workers}",
                self.workers.len()
            ));
        }
        if self.expert_bytes == 0 {
            return Err("EP placement expert_bytes must be positive".into());
        }
        let mut names = std::collections::HashSet::new();
        for (wi, worker) in self.workers.iter().enumerate() {
            if worker.name.is_empty() || !names.insert(&worker.name) {
                return Err(format!("EP worker {wi}: names must be nonempty and unique"));
            }
            if !worker.read_us.is_finite()
                || worker.read_us <= 0.0
                || !worker.compute_us.is_finite()
                || worker.compute_us < 0.0
                || !worker.dispatch_us.is_finite()
                || worker.dispatch_us < 0.0
            {
                return Err(format!(
                    "EP worker {wi}: costs must be finite, read_us > 0, others >= 0"
                ));
            }
        }
        let mut bytes = vec![0u64; workers];
        for (li, table) in self.layers.iter().enumerate() {
            let expected = if model.dense_layers.contains(&li) {
                0
            } else {
                self.num_experts + self.n_shared_experts
            };
            if table.len() != expected {
                return Err(format!(
                    "EP layer {li}: {} experts, expected {expected}",
                    table.len()
                ));
            }
            for (id, owners) in table.iter().enumerate() {
                if owners.is_empty() {
                    return Err(format!("EP layer {li} expert {id}: no owner"));
                }
                for (j, &wi) in owners.iter().enumerate() {
                    if wi >= workers || owners[..j].contains(&wi) {
                        return Err(format!(
                            "EP layer {li} expert {id}: invalid/duplicate worker {wi}"
                        ));
                    }
                    bytes[wi] = bytes[wi]
                        .checked_add(self.expert_bytes)
                        .ok_or("EP placement byte count overflow")?;
                }
            }
        }
        for (wi, (&needed, worker)) in bytes.iter().zip(&self.workers).enumerate() {
            if needed > worker.expert_capacity_bytes {
                return Err(format!(
                    "EP worker {wi} ({}): {needed} expert bytes exceed budget {}",
                    worker.name, worker.expert_capacity_bytes
                ));
            }
        }
        Ok(())
    }

    pub fn owns(&self, layer: usize, expert: usize, worker: usize) -> bool {
        self.layers
            .get(layer)
            .and_then(|t| t.get(expert))
            .is_some_and(|owners| owners.contains(&worker))
    }

    /// One owner per selected unique expert for this frame. Keeping all rows
    /// using an expert together lets a worker read its weights once. Assign
    /// constrained experts first, then the busiest, so replicated shared/hot
    /// experts fill spare bandwidth instead of displacing fixed owners.
    ///
    /// Assumes a validated placement (via [`Self::validate`], run by
    /// [`Self::read`] and `EpClient::with_placement`): owner indices in the
    /// per-layer table are `< workers.len()`, so the `self.workers[wi]` cost
    /// lookups below cannot panic.
    pub fn assign(&self, layer: usize, rows: &[Vec<(usize, f32)>]) -> Result<Vec<usize>, String> {
        let table = self
            .layers
            .get(layer)
            .filter(|t| !t.is_empty())
            .ok_or_else(|| format!("EP layer {layer}: no MoE placement"))?;
        let mut counts = vec![0usize; table.len()];
        for row in rows {
            for &(id, _) in row {
                *counts
                    .get_mut(id)
                    .ok_or_else(|| format!("EP layer {layer}: invalid expert {id}"))? += 1;
            }
        }
        let mut ids: Vec<usize> = (0..table.len()).filter(|&id| counts[id] != 0).collect();
        ids.sort_by_key(|&id| (table[id].len(), std::cmp::Reverse(counts[id]), id));
        let mut load = vec![0.0f64; self.workers.len()];
        let mut active = vec![false; self.workers.len()];
        let mut assigned = vec![usize::MAX; table.len()];
        for id in ids {
            let cost = |wi: usize| {
                let w = &self.workers[wi];
                load[wi]
                    + w.read_us
                    + counts[id] as f64 * w.compute_us
                    + if active[wi] { 0.0 } else { w.dispatch_us }
            };
            let &wi = table[id]
                .iter()
                .min_by(|&&a, &&b| cost(a).total_cmp(&cost(b)).then(a.cmp(&b)))
                .ok_or_else(|| format!("EP layer {layer} expert {id}: no owner"))?;
            load[wi] = cost(wi);
            active[wi] = true;
            assigned[id] = wi;
        }
        Ok(assigned)
    }
}
