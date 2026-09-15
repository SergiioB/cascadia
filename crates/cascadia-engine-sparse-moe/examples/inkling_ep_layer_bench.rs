//! Real expert-weight phase benchmark, NOT full-model inference.
//! --export DIR --frames JSON --out JSON [--reference-out BIN | --reference BIN]
//! [--workers IP:PORT,... --placement JSON] [--samples N]
//! Frames contain {layer, ids, seed}; deterministic synthetic normalized inputs
//! and equal expert weights isolate expert execution and transport costs.

use cascadia_engine_sparse_moe::dist::ExpertDispatchBody;
use cascadia_engine_sparse_moe::dsv4::loader::ExpertsMode;
use cascadia_engine_sparse_moe::inkling::ep::{load_expert_bank_with_placement, EpClient};
use cascadia_engine_sparse_moe::inkling::ep_placement::{EpPlacement, EpWorkerCost};
use cascadia_engine_sparse_moe::inkling::loader::read_manifest;
use serde::Deserialize;
use std::{path::PathBuf, sync::Arc, time::Instant};

#[derive(Deserialize)]
struct Frame {
    layer: usize,
    ids: Vec<usize>,
    seed: u32,
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
            "--workers",
            "--placement",
            "--samples",
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
    let samples = flags
        .get("--samples")
        .map(|s| s.parse::<usize>())
        .transpose()?
        .unwrap_or(3);
    if samples == 0 {
        return Err("samples must be positive".into());
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
    let local_plan = EpPlacement {
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
    let bank = if remote.is_none() {
        Some(load_expert_bank_with_placement(
            &dir,
            0,
            1,
            ExpertsMode::Mmap,
            Some(&local_plan),
        )?)
    } else {
        None
    };
    // Isolate transport using a padded expert slot: the worker returns a zero
    // hidden row without reading weights. Same sockets/framing as inference.
    for (wi, connection) in connections.iter().enumerate() {
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
            let mut seed = f.seed;
            (0..m.hidden_size)
                .map(|_| {
                    seed = seed.wrapping_mul(1664525).wrapping_add(1013904223);
                    ((seed >> 8) as f32 / 16777216.0 - 0.5) * 0.25
                })
                .collect()
        })
        .collect();
    let evaluate = |i: usize| -> Result<Vec<f32>, String> {
        let f = &frames[i];
        let x = &inputs[i];
        if f.ids.len() != m.top_k + m.n_shared_experts
            || f.ids
                .iter()
                .any(|&id| id >= m.num_experts + m.n_shared_experts)
        {
            return Err("invalid frame experts".into());
        }
        let weight = 1.0 / f.ids.len() as f32;
        if let Some(c) = &remote {
            return c.dispatch(
                f.layer as u32,
                x,
                &[f.ids.iter().map(|&id| (id, weight)).collect()],
            );
        }
        let body = ExpertDispatchBody {
            layer: f.layer as u32,
            rows: 1,
            k: f.ids.len() as u32,
            hidden: x.clone(),
            hidden_shape: [1, m.hidden_size as u32, 1],
            ids: f.ids.iter().map(|&id| id as i32).collect(),
            ids_shape: [1, f.ids.len() as u32, 1],
        };
        let raw = bank.as_ref().unwrap().serve(&body)?;
        let mut out = vec![0.; m.hidden_size];
        for y in raw.chunks_exact(m.hidden_size) {
            for (o, &v) in out.iter_mut().zip(y) {
                *o += weight * v;
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
    if let Some(path) = flags.get("--reference") {
        if std::fs::read(path)? != reference {
            return Err("expert outputs differ from local reference".into());
        }
    }
    if let Some(path) = flags.get("--reference-out") {
        use std::io::Write;
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)?
            .write_all(&reference)?;
    }
    let mut timings = Vec::new();
    for sample in 0..samples {
        for i in 0..frames.len() {
            let start = Instant::now();
            let out = evaluate(i)?;
            let elapsed = start.elapsed().as_secs_f64() * 1000.;
            let expected = &reference[i * m.hidden_size * 4..(i + 1) * m.hidden_size * 4];
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
    let result = serde_json::json!({"scope":"real_expert_phase_with_synthetic_inputs","full_model_inference":false,
        "hidden":m.hidden_size,"intermediate":m.moe_intermediate,"model_layers_in_export":m.num_layers,
        "frames":frames.len(),"samples":samples,"workers":connections.len(),"reference_verified":flags.contains_key("--reference"),
        "self_consistency_verified":true,"workers_arg":flags.get("--workers"),"timings":timings,"wire_probes":wire_probes,
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
