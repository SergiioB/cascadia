//! Complete autoregressive Inkling decode, separate from the synthetic layer probe.
//!
//! --export DIR --cases cases.json [--tokens 64] [--samples 3] [--out result.json]
//! [--route-trace routes.json] captures routed expert IDs without changing logits.
//! [--layer-profile profile.json] records attention/MLP branch timings per layer.
//! cases.json: [{"name":"case", "prompt_ids":[...], "greedy_ids":[...]}].
//! Omit greedy_ids only when recording an initial baseline (not correctness-verified).
//! The large 975B architecture is required unless --allow-fixture is explicit.
//! Fixture runs emit fixture_decode_tokens_per_s and can never satisfy the target.
//! Generation stops at EOS. The first generated token belongs to prefill; decode
//! throughput counts only subsequent tokens, with complete layers/head/argmax.

use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Instant;

use cascadia_engine_sparse_moe::dsv4::loader::ExpertsMode;
use cascadia_engine_sparse_moe::inkling::loader::{load_model_with, read_manifest};
use cascadia_engine_sparse_moe::inkling::model::{argmax, Model};
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
struct Case {
    name: String,
    prompt_ids: Vec<u32>,
    #[serde(default)]
    greedy_ids: Option<Vec<u32>>,
}

#[derive(Serialize)]
struct Sample {
    case: String,
    repetition: usize,
    prefill_seconds: f64,
    decode_seconds: f64,
    decode_steps: usize,
    generated_ids: Vec<u32>,
}

#[derive(Serialize)]
struct LayerRoutes {
    layer: usize,
    routed_experts_per_position: Vec<Vec<usize>>,
}

#[derive(Serialize)]
struct RoutingSample {
    case: String,
    repetition: usize,
    prefill_positions: usize,
    decode_positions: usize,
    layers: Vec<LayerRoutes>,
}

#[derive(Serialize)]
struct TimingEvent {
    rows: usize,
    prefill: bool,
    attention_seconds: f64,
    mlp_seconds: f64,
    total_seconds: f64,
}

#[derive(Serialize)]
struct TimedLayer {
    layer: usize,
    events: Vec<TimingEvent>,
}

#[derive(Serialize)]
struct TimingSample {
    case: String,
    repetition: usize,
    layers: Vec<TimedLayer>,
}

fn hash_logits(hash: &mut u64, logits: &[f32]) {
    for value in logits {
        assert!(value.is_finite(), "non-finite logits");
        for byte in value.to_bits().to_le_bytes() {
            *hash = (*hash ^ u64::from(byte)).wrapping_mul(0x100000001b3);
        }
    }
}

fn generate(model: &mut Model, case: &Case, tokens: usize, eos: &[u32], hash: &mut u64) -> Sample {
    model.reset();
    let start = Instant::now();
    let logits = model.prefill(&case.prompt_ids);
    let mut next = argmax(&logits) as u32;
    let prefill_seconds = start.elapsed().as_secs_f64();
    hash_logits(hash, &logits);
    let mut generated_ids = vec![next];
    let start = Instant::now();
    while generated_ids.len() < tokens && !eos.contains(&next) {
        let logits = model.forward_token(next);
        hash_logits(hash, &logits);
        next = argmax(&logits) as u32;
        generated_ids.push(next);
    }
    let decode_seconds = start.elapsed().as_secs_f64();
    if let Some(expected) = &case.greedy_ids {
        assert_eq!(&generated_ids, expected, "greedy mismatch: {}", case.name);
    }
    Sample {
        case: case.name.clone(),
        repetition: 0,
        prefill_seconds,
        decode_seconds,
        decode_steps: generated_ids.len() - 1,
        generated_ids,
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut export = None;
    let mut cases_path = None;
    let mut out = None;
    let mut route_trace = None;
    let mut layer_profile = None;
    let mut tokens = 64usize;
    let mut repetitions = 3usize;
    let mut allow_fixture = false;
    let mut it = std::env::args().skip(1);
    while let Some(flag) = it.next() {
        if flag == "--allow-fixture" {
            allow_fixture = true;
            continue;
        }
        let value = it.next().ok_or_else(|| format!("{flag} needs a value"))?;
        match flag.as_str() {
            "--export" => export = Some(PathBuf::from(value)),
            "--cases" => cases_path = Some(PathBuf::from(value)),
            "--tokens" => tokens = value.parse()?,
            "--samples" => repetitions = value.parse()?,
            "--out" => out = Some(PathBuf::from(value)),
            "--route-trace" => route_trace = Some(PathBuf::from(value)),
            "--layer-profile" => layer_profile = Some(PathBuf::from(value)),
            _ => return Err(format!("unknown argument: {flag}").into()),
        }
    }
    assert!(
        tokens >= 2 && repetitions >= 1,
        "need >=2 tokens and >=1 samples"
    );
    if let Some(path) = &route_trace {
        assert!(!path.exists(), "refusing to overwrite a routing trace");
        assert!(
            out.as_ref() != Some(path),
            "trace and result need distinct paths"
        );
    }
    if let Some(path) = &layer_profile {
        assert!(!path.exists(), "refusing to overwrite a layer profile");
        assert!(
            out.as_ref() != Some(path) && route_trace.as_ref() != Some(path),
            "profile, trace and result need distinct paths"
        );
    }
    let export = export.ok_or("--export is required")?;
    let cases: Vec<Case> =
        serde_json::from_slice(&std::fs::read(cases_path.ok_or("--cases is required")?)?)?;
    assert!(!cases.is_empty(), "need at least one prompt");
    let manifest = read_manifest(&export)?;
    let large = manifest.num_layers == 66
        && manifest.hidden_size == 6144
        && manifest.vocab_size == 201024
        && manifest.num_attention_heads == 64
        && manifest.num_kv_heads == 8
        && manifest.head_dim == 128
        && manifest.dense_layers == [0, 1]
        && manifest.dense_intermediate == 24576
        && manifest.moe_intermediate == 3072
        && manifest.num_experts == 256
        && manifest.top_k == 6
        && manifest.n_shared_experts == 2;
    assert!(
        large || allow_fixture,
        "expected the complete large Inkling architecture"
    );
    let full_model = large && !allow_fixture;
    let correctness_verified = cases.iter().all(|c| c.greedy_ids.is_some());
    for c in &cases {
        assert!(!c.prompt_ids.is_empty(), "empty prompt: {}", c.name);
        assert!(c
            .prompt_ids
            .iter()
            .all(|&t| (t as usize) < manifest.vocab_size));
    }
    let max_seq = cases
        .iter()
        .map(|c| c.prompt_ids.len())
        .max()
        .unwrap()
        .checked_add(tokens)
        .ok_or("sequence length overflow")?;
    let load = Instant::now();
    let mut model = load_model_with(&export, max_seq, ExpertsMode::Mmap)?;
    assert_eq!(model.layers().len(), manifest.num_layers);
    println!("load_seconds={}", load.elapsed().as_secs_f64());
    println!("full_model={}", u8::from(full_model));
    let mut captures = Vec::new();
    if route_trace.is_some() {
        for (li, layer) in model.layers_mut().iter_mut().enumerate() {
            if let Some(moe) = layer.moe_mut() {
                let routes = Arc::new(Mutex::new(Vec::new()));
                let target = Arc::clone(&routes);
                moe.set_route_observer(Some(Arc::new(move |gate| {
                    target.lock().unwrap().push(gate.idx.clone());
                })));
                captures.push((li, routes));
            }
        }
    }
    let mut routing_samples = Vec::new();
    let mut timers = Vec::new();
    if layer_profile.is_some() {
        for layer in model.layers_mut() {
            let events = Arc::new(Mutex::new(Vec::new()));
            let target = Arc::clone(&events);
            layer.set_timing_observer(Some(Arc::new(move |timing| {
                target.lock().unwrap().push(TimingEvent {
                    rows: timing.rows,
                    prefill: timing.prefill,
                    attention_seconds: timing.attention.as_secs_f64(),
                    mlp_seconds: timing.mlp.as_secs_f64(),
                    total_seconds: timing.total.as_secs_f64(),
                });
            })));
            timers.push(events);
        }
    }
    let mut timing_samples = Vec::new();
    let mut samples = Vec::new();
    let mut reference_hash = None;
    for rep in 0..repetitions {
        let mut hash = 0xcbf29ce484222325;
        for case in &cases {
            let mut sample = generate(&mut model, case, tokens, &manifest.eos_token_ids, &mut hash);
            sample.repetition = rep;
            assert!(
                sample.decode_steps > 0,
                "{} ended during prefill; choose a longer prompt",
                case.name
            );
            println!("sample_json={}", serde_json::to_string(&sample)?);
            if route_trace.is_some() {
                let layers = captures
                    .iter()
                    .map(|(li, routes)| {
                        let rows = std::mem::take(&mut *routes.lock().unwrap());
                        assert_eq!(rows.len(), case.prompt_ids.len() + sample.decode_steps);
                        LayerRoutes {
                            layer: *li,
                            routed_experts_per_position: rows,
                        }
                    })
                    .collect();
                routing_samples.push(RoutingSample {
                    case: case.name.clone(),
                    repetition: rep,
                    prefill_positions: case.prompt_ids.len(),
                    decode_positions: sample.decode_steps,
                    layers,
                });
            }
            if layer_profile.is_some() {
                let layers = timers
                    .iter()
                    .enumerate()
                    .map(|(li, events)| {
                        let events = std::mem::take(&mut *events.lock().unwrap());
                        assert_eq!(events.len(), 1 + sample.decode_steps);
                        assert!(events[0].prefill && events[0].rows == case.prompt_ids.len());
                        assert!(events[1..]
                            .iter()
                            .all(|event| !event.prefill && event.rows == 1));
                        TimedLayer { layer: li, events }
                    })
                    .collect();
                timing_samples.push(TimingSample {
                    case: case.name.clone(),
                    repetition: rep,
                    layers,
                });
            }
            samples.push(sample);
        }
        if let Some(expected) = reference_hash {
            assert_eq!(hash, expected, "non-repeatable logits");
        } else {
            reference_hash = Some(hash);
        }
    }
    // Conservative primary metric: slowest complete case/repetition, including
    // the first decode and all validation/hash overhead. No warm-cache exclusions.
    let rate = samples
        .iter()
        .map(|s| s.decode_steps as f64 / s.decode_seconds)
        .fold(f64::INFINITY, f64::min);
    let steps = samples.iter().map(|s| s.decode_steps).min().unwrap();
    let hash = format!("{:016x}", reference_hash.unwrap());
    let scope = if full_model {
        "full_large_model_decode"
    } else {
        "fixture_model_decode"
    };
    println!("scope={scope}");
    println!("output_hash={hash}");
    println!("correctness_verified={}", u8::from(correctness_verified));
    println!("decode_steps_min={steps}");
    println!("repetitions={repetitions}");
    let metric = if full_model {
        "decode_tokens_per_s"
    } else {
        "fixture_decode_tokens_per_s"
    };
    println!("{metric}={rate}");
    if let Some(out) = out {
        std::fs::write(
            out,
            serde_json::to_vec_pretty(&serde_json::json!({
                "scope": scope, "export": export, "manifest": {"layers":manifest.num_layers,
                    "hidden":manifest.hidden_size, "experts":manifest.num_experts},
                "output_hash":hash, "correctness_verified":correctness_verified,
                "slowest_case_decode_tokens_per_s":rate, "samples":samples
            }))?,
        )?;
    }
    if let Some(path) = route_trace {
        let file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)?;
        serde_json::to_writer_pretty(
            file,
            &serde_json::json!({
                "scope": "routing_diagnostics", "generation_scope": scope,
                "full_model": full_model, "correctness_verified": correctness_verified,
                "output_hash": hash, "export": export,
                "manifest": {"layers": manifest.num_layers, "routed_experts": manifest.num_experts,
                    "shared_experts": manifest.n_shared_experts, "top_k": manifest.top_k,
                    "hidden": manifest.hidden_size, "intermediate": manifest.moe_intermediate},
                "samples": routing_samples,
            }),
        )?;
    }
    if let Some(path) = layer_profile {
        let file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)?;
        serde_json::to_writer_pretty(
            file,
            &serde_json::json!({
                "scope": "layer_timing_diagnostics", "generation_scope": scope,
                "full_model": full_model, "correctness_verified": correctness_verified,
                "output_hash": hash, "export": export, "layers": manifest.num_layers,
                "branch_times_include_norms_convs_residuals": true,
                "head_and_embedding_excluded_from_layer_times": true,
                "observer_overhead_included_in_benchmark_time": true,
                "samples": timing_samples,
            }),
        )?;
    }
    Ok(())
}
