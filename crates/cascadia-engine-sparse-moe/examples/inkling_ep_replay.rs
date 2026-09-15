//! Replay recorded expert IDs through the production replica selector.
//! --manifest FILE --placement FILE --routes FILE --out FILE
//! Reports routing load, not inference speed: no weights or network are used.

use cascadia_engine_sparse_moe::inkling::ep_placement::EpPlacement;
use cascadia_engine_sparse_moe::inkling::loader::InklingManifest;
use serde::Deserialize;
use std::path::PathBuf;

#[derive(Deserialize)]
struct Trace {
    output_hash: String,
    full_model: bool,
    samples: Vec<Sample>,
}
#[derive(Deserialize)]
struct Sample {
    prefill_positions: usize,
    decode_positions: usize,
    layers: Vec<Layer>,
}
#[derive(Deserialize)]
struct Layer {
    layer: usize,
    routed_experts_per_position: Vec<Vec<usize>>,
}

fn summary(mut v: Vec<f64>) -> serde_json::Value {
    v.sort_by(f64::total_cmp);
    let percentile = |p: f64| v[((v.len() - 1) as f64 * p).ceil() as usize];
    serde_json::json!({"mean": v.iter().sum::<f64>() / v.len() as f64,
        "p50": percentile(0.5), "p99": percentile(0.99), "max": v.last()})
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut flags = std::collections::HashMap::new();
    let mut args = std::env::args().skip(1);
    while let Some(k) = args.next() {
        if !["--manifest", "--placement", "--routes", "--out"].contains(&k.as_str()) {
            return Err(format!("unknown argument {k}").into());
        }
        if flags
            .insert(k, PathBuf::from(args.next().ok_or("flag requires value")?))
            .is_some()
        {
            return Err("duplicate flag".into());
        }
    }
    for key in ["--manifest", "--placement", "--routes", "--out"] {
        if !flags.contains_key(key) {
            return Err(format!("missing {key}").into());
        }
    }
    let m: InklingManifest = serde_json::from_slice(&std::fs::read(&flags["--manifest"])?)?;
    let p: EpPlacement = serde_json::from_slice(&std::fs::read(&flags["--placement"])?)?;
    p.validate(&m, p.workers.len())?;
    let trace: Trace = serde_json::from_slice(&std::fs::read(&flags["--routes"])?)?;
    let w = p.workers.len();
    let (mut baseline, mut placed, mut baseline_fanout, mut placed_fanout) =
        (Vec::new(), Vec::new(), Vec::new(), Vec::new());
    let mut route_ns = 0u128;
    for sample in &trace.samples {
        for layer in &sample.layers {
            if layer.routed_experts_per_position.len()
                != sample.prefill_positions + sample.decode_positions
            {
                return Err("trace position count mismatch".into());
            }
            for ids in layer
                .routed_experts_per_position
                .iter()
                .skip(sample.prefill_positions)
            {
                if ids.len() != m.top_k || ids.iter().any(|&id| id >= m.num_experts) {
                    return Err("trace top-k or expert ID mismatch".into());
                }
                let rows = vec![ids
                    .iter()
                    .copied()
                    .chain(m.num_experts..m.num_experts + m.n_shared_experts)
                    .map(|id| (id, 1.0))
                    .collect::<Vec<_>>()];
                let start = std::time::Instant::now();
                let owners = p.assign(layer.layer, &rows)?;
                route_ns += start.elapsed().as_nanos();
                let (mut old, mut new) = (vec![0usize; w], vec![0usize; w]);
                for &(id, _) in &rows[0] {
                    old[id % w] += 1;
                    new[owners[id]] += 1;
                }
                baseline.push(*old.iter().max().unwrap() as f64);
                placed.push(*new.iter().max().unwrap() as f64);
                baseline_fanout.push(old.iter().filter(|&&n| n != 0).count() as f64);
                placed_fanout.push(new.iter().filter(|&&n| n != 0).count() as f64);
            }
        }
    }
    if placed.is_empty() {
        return Err("trace contains no decode routes".into());
    }
    let result = serde_json::json!({
        "scope": "recorded_decode_route_load_only", "inference_executed": false,
        "source_routes": flags["--routes"], "source_output_hash":trace.output_hash, "source_full_model":trace.full_model,
        "workers":w, "layer_dispatches":placed.len(), "samples":trace.samples.len(),
        "selector_mean_us":route_ns as f64 / placed.len() as f64 / 1000.0,
        "max_experts_per_worker": {"modulo":summary(baseline), "placement":summary(placed)},
        "involved_workers": {"modulo":summary(baseline_fanout), "placement":summary(placed_fanout)},
        "limitation":"Routing load only; replicas consume additional memory. Network, kernels, residency and token throughput are not measured."
    });
    let f = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&flags["--out"])?;
    serde_json::to_writer_pretty(f, &result)?;
    println!("{}", serde_json::to_string_pretty(&result)?);
    Ok(())
}
