//! Real expert-weight phase benchmark, NOT full-model inference.
//! --export DIR --frames JSON --out JSON [--reference-out BIN | --reference BIN]
//! [--workers IP:PORT,... --placement JSON] [--samples N]
//! [--local-index N --placement JSON] probes one local fleet shard directly.
//! Frames contain {layer, ids, seed, weights?, extra_rows?}; deterministic
//! synthetic inputs isolate expert execution and transport costs. Optional
//! weights and extra rows exercise routing numerics and batched requests.

use cascadia_engine_sparse_moe::dist::ExpertDispatchBody;
use cascadia_engine_sparse_moe::dsv4::loader::ExpertsMode;
use cascadia_engine_sparse_moe::inkling::ep::{load_expert_bank_with_placement, EpClient};
use cascadia_engine_sparse_moe::inkling::ep_placement::{EpPlacement, EpWorkerCost};
use cascadia_engine_sparse_moe::inkling::loader::read_manifest;
use serde::Deserialize;
use std::{path::PathBuf, sync::Arc, time::Instant};

#[derive(Deserialize)]
struct FrameRow {
    ids: Vec<usize>,
    seed: u32,
    #[serde(default)]
    hidden: Option<Vec<f32>>,
    #[serde(default)]
    weights: Option<Vec<f32>>,
}

#[derive(Deserialize)]
struct Frame {
    layer: usize,
    #[serde(flatten)]
    first: FrameRow,
    #[serde(default)]
    extra_rows: Vec<FrameRow>,
}

impl Frame {
    fn rows(&self) -> impl Iterator<Item = &FrameRow> {
        std::iter::once(&self.first).chain(&self.extra_rows)
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let mut flags = std::collections::HashMap::new();
    while let Some(k) = args.next() {
        if ![
            "--export",
            "--frames",
            "--out",
            "--reference-out",
            "--reference",
            "--reference-rel-rms",
            "--workers",
            "--placement",
            "--samples",
            "--warm-passes",
            "--local-index",
        ]
        .contains(&k.as_str())
        {
            return Err(format!("unknown flag {k}").into());
        }
        flags.insert(k, args.next().ok_or("flag needs value")?);
    }
    for key in ["--export", "--frames", "--out"] {
        if !flags.contains_key(key) {
            return Err(format!("missing {key}").into());
        }
    }
    let dir = PathBuf::from(&flags["--export"]);
    let m = read_manifest(&dir)?;
    let frames: Vec<Frame> = serde_json::from_slice(&std::fs::read(&flags["--frames"])?)?;
    if frames.is_empty() {
        return Err("empty frames".into());
    }
    if frames.iter().flat_map(Frame::rows).any(|row| {
        row.hidden
            .as_ref()
            .is_some_and(|x| x.len() != m.hidden_size || x.iter().any(|v| !v.is_finite()))
    }) {
        return Err("invalid explicit hidden row".into());
    }
    let samples = flags
        .get("--samples")
        .map(|s| s.parse::<usize>())
        .transpose()?
        .unwrap_or(3);
    if samples == 0 {
        return Err("samples must be positive".into());
    }
    let warm_passes = flags
        .get("--warm-passes")
        .map(|v| v.parse::<usize>())
        .transpose()?
        .unwrap_or(1);
    if !(1..=10).contains(&warm_passes) {
        return Err("warm-passes must be 1..10".into());
    }
    let rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()?;
    let mut connections = Vec::new();
    let mut wire_probes = Vec::new();
    let remote = if let Some(workers) = flags.get("--workers") {
        for endpoint in workers.split(',') {
            let (host, port) = endpoint.rsplit_once(':').ok_or("worker needs host:port")?;
            let mut c = cascadia_transport::ActivationClient::new(host, port.parse()?);
            rt.block_on(c.connect_with_timeout(std::time::Duration::from_secs(15)))?;
            connections.push(Arc::new(tokio::sync::Mutex::new(c)));
        }
        let mut c = EpClient::new(
            connections.clone(),
            rt.handle().clone(),
            m.hidden_size,
            m.num_experts,
            m.n_shared_experts,
        );
        if let Some(path) = flags.get("--placement") {
            c = c.with_placement(
                Arc::new(EpPlacement::read(
                    std::path::Path::new(path),
                    &m,
                    connections.len(),
                )?),
                &m,
            )?;
        }
        Some(c)
    } else {
        None
    };
    // The local oracle's packed budget is explicit and bounded to 10 GiB.
    // It is a phase probe; loading more than that should fail instead of OOM.
    let mut local_plan = EpPlacement {
        version: 1,
        hidden_size: m.hidden_size,
        moe_intermediate: m.moe_intermediate,
        num_experts: m.num_experts,
        n_shared_experts: m.n_shared_experts,
        expert_bytes: 3 * m.hidden_size as u64 * m.moe_intermediate as u64 * 9 / 16,
        workers: vec![EpWorkerCost {
            name: "local".into(),
            expert_capacity_bytes: 10 << 30,
            read_us: 1.,
            compute_us: 0.,
            dispatch_us: 0.,
        }],
        layers: (0..m.num_layers)
            .map(|li| {
                if m.dense_layers.contains(&li) {
                    vec![]
                } else {
                    vec![vec![0]; m.num_experts + m.n_shared_experts]
                }
            })
            .collect(),
    };
    let local_index = flags
        .get("--local-index")
        .map(|s| s.parse::<u32>())
        .transpose()?
        .unwrap_or(0);
    if flags.contains_key("--local-index") {
        if remote.is_some() {
            return Err("local-index cannot be combined with remote workers".into());
        }
        let path = flags
            .get("--placement")
            .ok_or("local-index requires an explicit placement")?;
        local_plan = serde_json::from_slice(&std::fs::read(path)?)?;
        local_plan.validate(&m, local_plan.workers.len())?;
    }
    let bank = if remote.is_none() {
        Some(load_expert_bank_with_placement(
            &dir,
            local_index,
            local_plan.workers.len().try_into()?,
            ExpertsMode::Mmap,
            Some(&local_plan),
        )?)
    } else {
        None
    };
    // Isolate transport using a padded expert slot: the worker returns a zero
    // hidden row without reading weights. Same sockets/framing as inference.
    let fused = std::env::var("CASCADIA_INKLING_EP_FUSED").is_ok_and(|v| v == "1");
    for (wi, connection) in connections.iter().enumerate().filter(|_| !fused) {
        let mut us = Vec::new();
        for round in 0..34 {
            let start = Instant::now();
            rt.block_on(async {
                use cascadia_engine_sparse_moe::dist::*;
                send_expert_dispatch(
                    connection,
                    frames[0].layer as u32,
                    1,
                    1,
                    m.hidden_size as u32,
                    &vec![0.0; m.hidden_size],
                    &[EXPERT_PAD],
                )
                .await
                .map_err(std::io::Error::other)?;
                if recv_kind_client(connection)
                    .await
                    .map_err(std::io::Error::other)?
                    != Some(FrameKind::ExpertResult)
                {
                    return Err(std::io::Error::other("wire probe got unexpected reply"));
                }
                let (data, shape) = recv_expert_result_body_client(connection)
                    .await
                    .map_err(std::io::Error::other)?
                    .map_err(std::io::Error::other)?;
                if shape != [1, 1, m.hidden_size as u32] || data.iter().any(|&x| x != 0.0) {
                    return Err(std::io::Error::other("invalid wire probe result"));
                }
                Ok::<_, std::io::Error>(())
            })?;
            if round >= 2 {
                us.push(start.elapsed().as_secs_f64() * 1e6);
            }
        }
        wire_probes.push(serde_json::json!({"worker":wi,"payload_bytes_each_way":m.hidden_size*4,"round_trip_us":us}));
    }
    let inputs: Vec<Vec<f32>> = frames
        .iter()
        .map(|f| {
            f.rows()
                .flat_map(|row| {
                    if let Some(hidden) = &row.hidden {
                        return hidden.clone();
                    }
                    let mut seed = row.seed;
                    (0..m.hidden_size)
                        .map(move |_| {
                            seed = seed.wrapping_mul(1664525).wrapping_add(1013904223);
                            ((seed >> 8) as f32 / 16777216.0 - 0.5) * 0.25
                        })
                        .collect::<Vec<_>>()
                })
                .collect()
        })
        .collect();
    let mut offsets = vec![0usize];
    for input in &inputs {
        offsets.push(offsets.last().unwrap() + input.len() * 4);
    }
    let evaluate = |i: usize| -> Result<Vec<f32>, String> {
        let f = &frames[i];
        let x = &inputs[i];
        let routing: Vec<Vec<(usize, f32)>> = f
            .rows()
            .map(|row| {
                let valid_count = if flags.contains_key("--local-index") {
                    (1..=m.top_k + m.n_shared_experts).contains(&row.ids.len())
                } else {
                    row.ids.len() == m.top_k + m.n_shared_experts
                };
                if !valid_count
                    || row
                        .ids
                        .iter()
                        .any(|&id| id >= m.num_experts + m.n_shared_experts)
                {
                    return Err("invalid frame experts".to_string());
                }
                let weights = row
                    .weights
                    .clone()
                    .unwrap_or_else(|| vec![1.0 / row.ids.len() as f32; row.ids.len()]);
                if weights.len() != row.ids.len() || weights.iter().any(|w| !w.is_finite()) {
                    return Err("invalid frame routing weights".to_string());
                }
                Ok(row.ids.iter().copied().zip(weights).collect())
            })
            .collect::<Result<_, _>>()?;
        if let Some(c) = &remote {
            return c.dispatch(f.layer as u32, x, &routing);
        }
        let rows = routing.len();
        let k = routing[0].len();
        if routing.iter().any(|row| row.len() != k) {
            return Err("local frame rows need the same expert count".into());
        }
        let weights: Vec<f32> = routing.iter().flatten().map(|&(_, w)| w).collect();
        let body = ExpertDispatchBody {
            layer: f.layer as u32,
            rows: rows as u32,
            k: k as u32,
            hidden: x.clone(),
            hidden_shape: [rows as u32, m.hidden_size as u32, 1],
            ids: routing.iter().flatten().map(|&(id, _)| id as i32).collect(),
            ids_shape: [rows as u32, k as u32, 1],
        };
        if fused {
            return bank.as_ref().unwrap().serve_fused(&body, &weights);
        }
        let raw = bank.as_ref().unwrap().serve(&body)?;
        let mut out = vec![0.; rows * m.hidden_size];
        for (slot, y) in raw.chunks_exact(m.hidden_size).enumerate() {
            let row = slot / k;
            for (o, &v) in out[row * m.hidden_size..(row + 1) * m.hidden_size]
                .iter_mut()
                .zip(y)
            {
                *o += weights[slot] * v;
            }
        }
        Ok(out)
    };
    let mut reference = Vec::new();
    // One complete warm pass also produces/checks a full output reference.
    for i in 0..frames.len() {
        for v in evaluate(i)? {
            if !v.is_finite() {
                return Err("nonfinite output".into());
            }
            reference.extend_from_slice(&v.to_le_bytes());
        }
    }
    let mut reference_comparison = None;
    if let Some(path) = flags.get("--reference") {
        let expected = std::fs::read(path)?;
        if expected.len() != reference.len() {
            return Err("reference size differs".into());
        }
        let limit = flags
            .get("--reference-rel-rms")
            .map(|v| v.parse::<f64>())
            .transpose()?
            .unwrap_or(0.0);
        if !limit.is_finite() || !(0.0..=0.02).contains(&limit) {
            return Err("reference RMS limit must be 0..0.02".into());
        }
        let mut square_error = 0.0;
        let mut square_reference = 0.0;
        let mut max_abs = 0.0f64;
        for (a, b) in reference.chunks_exact(4).zip(expected.chunks_exact(4)) {
            let a = f32::from_le_bytes(a.try_into().unwrap()) as f64;
            let b = f32::from_le_bytes(b.try_into().unwrap()) as f64;
            if !b.is_finite() {
                return Err("nonfinite reference".into());
            }
            square_error += (a - b) * (a - b);
            square_reference += b * b;
            max_abs = max_abs.max((a - b).abs());
        }
        let rel_rms = (square_error / square_reference.max(1e-30)).sqrt();
        if (limit == 0.0 && expected != reference) || rel_rms > limit {
            return Err(
                format!("expert outputs differ: relative RMS {rel_rms}, limit {limit}").into(),
            );
        }
        reference_comparison = Some(
            serde_json::json!({"bit_exact":expected==reference,"relative_rms":rel_rms,"limit":limit,"max_abs":max_abs}),
        );
    }
    if let Some(path) = flags.get("--reference-out") {
        use std::io::Write;
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)?
            .write_all(&reference)?;
    }
    // Additional full passes make warm-up explicit; do not discard measured
    // outliers after the fact. Every warm output must retain the same bits.
    for _ in 1..warm_passes {
        for i in 0..frames.len() {
            let out = evaluate(i)?;
            let expected = &reference[offsets[i]..offsets[i + 1]];
            if !out
                .iter()
                .zip(expected.chunks_exact(4))
                .all(|(x, b)| x.to_le_bytes() == b)
            {
                return Err("output changed during additional warm-up".into());
            }
        }
    }
    let mut timings = Vec::new();
    for sample in 0..samples {
        for i in 0..frames.len() {
            let start = Instant::now();
            let out = evaluate(i)?;
            let elapsed = start.elapsed().as_secs_f64() * 1000.;
            let expected = &reference[offsets[i]..offsets[i + 1]];
            if !out
                .iter()
                .zip(expected.chunks_exact(4))
                .all(|(x, b)| x.to_le_bytes() == b)
            {
                return Err("output changed during timing".into());
            }
            timings.push(serde_json::json!({"sample":sample,"frame":i,"milliseconds":elapsed}));
        }
    }
    for c in &connections {
        rt.block_on(async { c.lock().await.close().await });
    }
    let scope = if frames
        .iter()
        .flat_map(Frame::rows)
        .any(|r| r.hidden.is_some())
    {
        "real_expert_phase_with_explicit_inputs"
    } else {
        "real_expert_phase_with_synthetic_inputs"
    };
    let result = serde_json::json!({"scope":scope,"full_model_inference":false,
        "hidden":m.hidden_size,"intermediate":m.moe_intermediate,"model_layers_in_export":m.num_layers,
        "frames":frames.len(),"rows_per_frame":frames.iter().map(|f|f.rows().count()).collect::<Vec<_>>(),"samples":samples,"warm_passes":warm_passes,"workers":connections.len(),"reference_verified":flags.contains_key("--reference"),
        "fused_MoE_sharding":fused,"self_consistency_verified":true,"workers_arg":flags.get("--workers"),"timings":timings,"wire_probes":wire_probes,
        "reference_comparison":reference_comparison,"local_backend":bank.as_ref().map(|b|b.backend_stats()),
        "limitation":"Only selected experts plus dispatch/gather; no attention, prefill, head or token generation. Not tok/s."});
    serde_json::to_writer_pretty(
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&flags["--out"])?,
        &result,
    )?;
    println!(
        "completed {} expert phase measurements",
        frames.len() * samples
    );
    Ok(())
}
