//! Full-decoder correctness trace, reusable with any EP worker count.
//! Records every layer residual and every output logit, then compares on the
//! reference token trajectory. A passing greedy check also proves that free
//! generation would follow that trajectory for the tested prompts/positions.

use cascadia_engine_sparse_moe::{
    dsv4::loader::ExpertsMode,
    inkling::{
        ep::EpClient,
        ep_placement::EpPlacement,
        loader::{load_model_with_remote, read_manifest},
        model::argmax,
    },
};
use serde::{Deserialize, Serialize};
use std::{
    fs::{File, OpenOptions},
    io::{BufReader, BufWriter, Read, Write},
    path::PathBuf,
    sync::Arc,
    time::Instant,
};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
struct Case {
    name: String,
    prompt_ids: Vec<u32>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
struct Tensor {
    case: String,
    step: usize,
    layer: Option<usize>,
    rows: usize,
    width: usize,
}

#[derive(Deserialize, Serialize)]
struct Reference {
    version: u32,
    full_model: bool,
    model_manifest: serde_json::Value,
    cases: Vec<Case>,
    tokens: usize,
    generated_ids: Vec<Vec<u32>>,
    tensors: Vec<Tensor>,
    payload_bytes: u64,
    payload_fnv1a64: String,
}

#[derive(Serialize)]
struct ErrorMetric {
    tensor: Tensor,
    relative_rms: f64,
    max_abs: f64,
    different_bits: usize,
    passed: bool,
}

struct Trace<W: Write = BufWriter<File>> {
    output: W,
    reference: Option<BufReader<File>>,
    expected: Vec<Tensor>,
    tensors: Vec<Tensor>,
    errors: Vec<ErrorMetric>,
    tolerance: f64,
    bytes: u64,
    hash: u64,
    expected_hash: Option<String>,
    reference_hash: u64,
}

fn fnv(hash: &mut u64, bytes: &[u8]) {
    for &b in bytes {
        *hash = (*hash ^ u64::from(b)).wrapping_mul(0x100000001b3);
    }
}

impl<W: Write> Trace<W> {
    fn push(&mut self, tensor: Tensor, values: &[f32]) -> Result<(), Box<dyn std::error::Error>> {
        if values.len() != tensor.rows * tensor.width || values.iter().any(|x| !x.is_finite()) {
            return Err(format!("invalid/nonfinite tensor: {tensor:?}").into());
        }
        let bytes: Vec<u8> = values.iter().flat_map(|x| x.to_le_bytes()).collect();
        self.output.write_all(&bytes)?;
        self.bytes += bytes.len() as u64;
        fnv(&mut self.hash, &bytes);
        if let Some(reader) = self.reference.as_mut() {
            if self.expected.get(self.tensors.len()) != Some(&tensor) {
                return Err("reference tensor order/shape mismatch".into());
            }
            let mut original = vec![0; bytes.len()];
            reader.read_exact(&mut original)?;
            fnv(&mut self.reference_hash, &original);
            let (mut error, mut norm, mut max_abs, mut different_bits) = (0f64, 0f64, 0f64, 0usize);
            for (&actual, b) in values.iter().zip(original.chunks_exact(4)) {
                let expected = f32::from_le_bytes(b.try_into()?);
                if !expected.is_finite() {
                    return Err("nonfinite reference".into());
                }
                let delta = f64::from(actual) - f64::from(expected);
                error += delta * delta;
                norm += f64::from(expected).powi(2);
                max_abs = max_abs.max(delta.abs());
                different_bits += usize::from(actual.to_bits() != expected.to_bits());
            }
            let relative_rms = (error / norm.max(1e-30)).sqrt();
            let passed = if self.tolerance == 0. {
                different_bits == 0
            } else {
                relative_rms <= self.tolerance
            };
            self.errors.push(ErrorMetric {
                tensor: tensor.clone(),
                relative_rms,
                max_abs,
                different_bits,
                passed,
            });
        }
        self.tensors.push(tensor);
        Ok(())
    }

    fn finish(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        self.output.flush()?;
        if let Some(reader) = self.reference.as_mut() {
            if self.expected.len() != self.tensors.len() || reader.read(&mut [0])? != 0 {
                return Err("reference tensor count/payload length mismatch".into());
            }
            if self.expected_hash.as_deref() != Some(&format!("{:016x}", self.reference_hash)) {
                return Err("reference payload checksum mismatch".into());
            }
        }
        Ok(())
    }
}

/// Compare immutable captures without executing the model again. A teacher-
/// forced candidate is reusable only when its actual greedy choices equal
/// the supplied input trajectory, so its saved states are self-consistent.
fn compare_saved(
    reference: PathBuf,
    candidate: PathBuf,
    trajectory: Option<PathBuf>,
    output: PathBuf,
    tolerance: f64,
    fixture: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    let load = |dir: &PathBuf| -> Result<Reference, Box<dyn std::error::Error>> {
        let r: Reference = serde_json::from_slice(&std::fs::read(dir.join("trace.json"))?)?;
        if r.version != 1
            || (!fixture && !r.full_model)
            || r.cases.is_empty()
            || r.tokens == 0
            || r.generated_ids.len() != r.cases.len()
            || r.generated_ids.iter().any(|ids| ids.len() != r.tokens)
            || std::fs::metadata(dir.join("tensors.f32"))?.len() != r.payload_bytes
        {
            return Err("invalid saved trace metadata/payload size".into());
        }
        Ok(r)
    };
    let r = load(&reference)?;
    let c = load(&candidate)?;
    if r.model_manifest != c.model_manifest
        || r.cases != c.cases
        || r.tokens != c.tokens
        || r.full_model != c.full_model
        || r.tensors != c.tensors
    {
        return Err("saved traces have different models/cases/tensor identities".into());
    }
    let report: serde_json::Value =
        serde_json::from_slice(&std::fs::read(candidate.join("report.json"))?)?;
    if report["teacher_forced"] == true {
        let t =
            load(&trajectory.ok_or("teacher-forced candidate requires --candidate-trajectory")?)?;
        if t.model_manifest != c.model_manifest
            || t.cases != c.cases
            || t.generated_ids != c.generated_ids
        {
            return Err("candidate greedy IDs differ from its forced input trajectory; re-run against the intended reference".into());
        }
    }
    let mut actual = BufReader::new(File::open(candidate.join("tensors.f32"))?);
    let mut trace = Trace {
        output: std::io::sink(),
        reference: Some(BufReader::new(File::open(reference.join("tensors.f32"))?)),
        expected: r.tensors,
        tensors: vec![],
        errors: vec![],
        tolerance,
        bytes: 0,
        hash: 0xcbf29ce484222325,
        expected_hash: Some(r.payload_fnv1a64),
        reference_hash: 0xcbf29ce484222325,
    };
    for tensor in &c.tensors {
        let mut bytes = vec![0; tensor.rows * tensor.width * 4];
        actual.read_exact(&mut bytes)?;
        let values = bytes
            .chunks_exact(4)
            .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
            .collect::<Vec<_>>();
        trace.push(tensor.clone(), &values)?;
    }
    trace.finish()?;
    if actual.read(&mut [0])? != 0
        || trace.bytes != c.payload_bytes
        || format!("{:016x}", trace.hash) != c.payload_fnv1a64
    {
        return Err("candidate payload checksum/length mismatch".into());
    }
    let greedy = r.generated_ids == c.generated_ids;
    let numerical = trace.errors.iter().all(|e| e.passed);
    serde_json::to_writer_pretty(
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?,
        &serde_json::json!({"version":1,"full_model":r.full_model,"saved_trace_comparison":true,
            "reference":reference,"candidate":candidate,"tokens_per_case":r.tokens,
            "reference_generated_ids":r.generated_ids,"generated_ids":c.generated_ids,
            "greedy_match":greedy,"numerical_match":numerical,"correctness_verified":greedy && numerical,
            "relative_rms_tolerance":tolerance,"tensor_errors":trace.errors,
            "candidate_payload_fnv1a64":c.payload_fnv1a64,"payload_checksums_verified":true}),
    )?;
    if !greedy || !numerical {
        return Err("saved trace correctness comparison failed".into());
    }
    println!("saved_trace_correctness_verified=true");
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let (mut export, mut cases_path, mut output, mut reference_path, mut placement_path) =
        (None, None, None, None, None);
    let mut workers = Vec::<String>::new();
    let (mut candidate, mut trajectory) = (None, None);
    let (mut tokens, mut tolerance, mut fixture) = (4usize, 0f64, false);
    let mut args = std::env::args().skip(1);
    while let Some(flag) = args.next() {
        if flag == "--allow-fixture" {
            fixture = true;
            continue;
        }
        let v = args.next().ok_or("missing flag value")?;
        match flag.as_str() {
            "--export" => export = Some(PathBuf::from(v)),
            "--cases" => cases_path = Some(PathBuf::from(v)),
            "--out" => output = Some(PathBuf::from(v)),
            "--reference" => reference_path = Some(PathBuf::from(v)),
            "--candidate" => candidate = Some(PathBuf::from(v)),
            "--candidate-trajectory" => trajectory = Some(PathBuf::from(v)),
            "--ep-placement" => placement_path = Some(PathBuf::from(v)),
            "--ep-workers" => workers = v.split(',').map(str::to_owned).collect(),
            "--tokens" => tokens = v.parse()?,
            "--max-relative-rms" => tolerance = v.parse()?,
            _ => return Err(format!("unknown flag {flag}").into()),
        }
    }
    if tokens == 0 || !tolerance.is_finite() || tolerance < 0. {
        return Err("invalid tokens/tolerance".into());
    }
    if let Some(candidate) = candidate {
        return compare_saved(
            reference_path.ok_or("--reference required")?,
            candidate,
            trajectory,
            output.ok_or("--out required (new JSON file)")?,
            tolerance,
            fixture,
        );
    }
    let export = export.ok_or("--export required")?;
    let output = output.ok_or("--out required (new directory)")?;
    let cases: Vec<Case> =
        serde_json::from_slice(&std::fs::read(cases_path.ok_or("--cases required")?)?)?;
    let manifest_json: serde_json::Value =
        serde_json::from_slice(&std::fs::read(export.join("manifest.json"))?)?;
    let m = read_manifest(&export)?;
    let full_model = m.num_layers == 66
        && m.hidden_size == 6144
        && m.vocab_size == 201024
        && m.num_experts == 256
        && m.n_shared_experts == 2
        && m.top_k == 6
        && m.moe_intermediate == 3072
        && m.dense_layers == [0, 1]
        && m.dense_intermediate == 24576
        && m.num_attention_heads == 64
        && m.num_kv_heads == 8
        && m.head_dim == 128;
    if !full_model && !fixture {
        return Err("requires complete 975B architecture; fixtures need --allow-fixture".into());
    }
    if cases.is_empty()
        || cases.iter().any(|c| {
            c.prompt_ids.is_empty() || c.prompt_ids.iter().any(|&t| t as usize >= m.vocab_size)
        })
    {
        return Err("empty or invalid validation cases".into());
    }
    let reference: Option<Reference> = reference_path
        .as_ref()
        .map(|p| -> Result<_, Box<dyn std::error::Error>> {
            let r: Reference = serde_json::from_slice(&std::fs::read(p.join("trace.json"))?)?;
            if r.version != 1
                || r.model_manifest != manifest_json
                || r.cases != cases
                || r.tokens != tokens
                || r.full_model != (full_model && !fixture)
                || r.generated_ids.len() != cases.len()
                || r.generated_ids.iter().any(|ids| {
                    ids.len() != tokens || ids.iter().any(|&t| t as usize >= m.vocab_size)
                })
                || std::fs::metadata(p.join("tensors.f32"))?.len() != r.payload_bytes
            {
                return Err("reference model/cases/token count/payload mismatch".into());
            }
            Ok(r)
        })
        .transpose()?;
    if placement_path.is_some() && workers.is_empty() {
        return Err("placement requires workers".into());
    }
    let rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()?;
    let mut connections = Vec::new();
    for address in &workers {
        let (host, port) = address.rsplit_once(':').ok_or("expected host:port")?;
        let mut client =
            cascadia_transport::ActivationClient::new(host.trim_matches(['[', ']']), port.parse()?);
        rt.block_on(client.connect_with_timeout(std::time::Duration::from_secs(30)))?;
        connections.push(Arc::new(tokio::sync::Mutex::new(client)));
    }
    let remote = if connections.is_empty() {
        None
    } else {
        let mut ep = EpClient::new(
            connections.clone(),
            rt.handle().clone(),
            m.hidden_size,
            m.num_experts,
            m.n_shared_experts,
        );
        if let Some(path) = &placement_path {
            ep = ep.with_placement(Arc::new(EpPlacement::read(path, &m, workers.len())?), &m)?;
        }
        Some(Arc::new(ep))
    };
    let max_seq = cases
        .iter()
        .map(|c| c.prompt_ids.len())
        .max()
        .unwrap()
        .checked_add(tokens)
        .ok_or("sequence size overflow")?;
    let start = Instant::now();
    let mut model = load_model_with_remote(&export, max_seq, ExpertsMode::Mmap, remote)?;
    println!(
        "model_loaded layers={} workers={} seconds={:.3}",
        model.layers().len(),
        workers.len(),
        start.elapsed().as_secs_f64()
    );
    std::fs::create_dir(&output)?;
    let create = |name| {
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output.join(name))
    };
    let mut progress = BufWriter::new(create("progress.jsonl")?);
    let mut trace = Trace {
        output: BufWriter::new(create("tensors.f32")?),
        reference: reference_path
            .as_ref()
            .map(|p| File::open(p.join("tensors.f32")).map(BufReader::new))
            .transpose()?,
        expected: reference
            .as_ref()
            .map_or_else(Vec::new, |r| r.tensors.clone()),
        expected_hash: reference.as_ref().map(|r| r.payload_fnv1a64.clone()),
        tensors: Vec::new(),
        errors: Vec::new(),
        tolerance,
        bytes: 0,
        hash: 0xcbf29ce484222325,
        reference_hash: 0xcbf29ce484222325,
    };
    let mut generated = Vec::new();
    for (ci, case) in cases.iter().enumerate() {
        model.reset();
        let mut ids = Vec::new();
        for step in 0..tokens {
            let rows = if step == 0 { case.prompt_ids.len() } else { 1 };
            let input_ids: Vec<u32> = if step == 0 {
                case.prompt_ids.clone()
            } else {
                vec![reference
                    .as_ref()
                    .map_or(ids[step - 1], |r| r.generated_ids[ci][step - 1])]
            };
            let mut hidden: Vec<f32> = input_ids
                .iter()
                .flat_map(|&t| model.embed_token(t))
                .collect();
            for (li, layer) in model.layers_mut().iter_mut().enumerate() {
                hidden = if step == 0 {
                    layer.forward_prefill(&hidden, rows)
                } else {
                    layer.forward_token(&hidden)
                };
                trace.push(
                    Tensor {
                        case: case.name.clone(),
                        step,
                        layer: Some(li),
                        rows,
                        width: m.hidden_size,
                    },
                    &hidden,
                )?;
                writeln!(
                    progress,
                    "{}",
                    serde_json::json!({"case":case.name,"step":step,"layer":li,"elapsed_seconds":start.elapsed().as_secs_f64(),
                        "relative_rms":trace.errors.last().map(|e|e.relative_rms),
                        "different_bits":trace.errors.last().map(|e|e.different_bits),
                        "tensor_passed":trace.errors.last().map(|e|e.passed)})
                )?;
                progress.flush()?;
            }
            let logits = model.head_logits(&hidden[(rows - 1) * m.hidden_size..]);
            trace.push(
                Tensor {
                    case: case.name.clone(),
                    step,
                    layer: None,
                    rows: 1,
                    width: logits.len(),
                },
                &logits,
            )?;
            let next = argmax(&logits) as u32;
            ids.push(next);
            println!(
                "case={} step={step} token={next} elapsed_seconds={:.3}",
                case.name,
                start.elapsed().as_secs_f64()
            );
        }
        generated.push(ids);
    }
    trace.finish()?;
    let greedy_match = reference.as_ref().map(|r| r.generated_ids == generated);
    let numerical_match = reference
        .as_ref()
        .map(|_| trace.errors.iter().all(|e| e.passed));
    let passed = greedy_match == Some(true) && numerical_match == Some(true);
    let tokenizer = export.join("tokenizer.json");
    let generated_text = if tokenizer.is_file() {
        let tokenizer = tokenizers::Tokenizer::from_file(tokenizer).map_err(|e| e.to_string())?;
        Some(
            generated
                .iter()
                .map(|ids| tokenizer.decode(ids, false).map_err(|e| e.to_string()))
                .collect::<Result<Vec<_>, _>>()?,
        )
    } else {
        None
    };
    serde_json::to_writer_pretty(
        create("report.json")?,
        &serde_json::json!({
            "version":1,"full_model":full_model && !fixture,"reference_comparison":reference.is_some(),
            "teacher_forced":reference.is_some(),"stops_at_eos":false,"workers":workers,"placement":placement_path,
        "tokens_per_case":tokens,"generated_ids":generated,"generated_text":generated_text,"greedy_match":greedy_match,
            "numerical_match":numerical_match,"correctness_verified":passed,"relative_rms_tolerance":tolerance,
            "elapsed_seconds":start.elapsed().as_secs_f64(),"tensor_errors":trace.errors,
            "environment":std::env::vars().filter(|(k,_)| k.starts_with("CASCADIA_INKLING_") || k=="RAYON_NUM_THREADS").collect::<std::collections::BTreeMap<_,_>>()
        }),
    )?;
    let new_reference = Reference {
        version: 1,
        full_model: full_model && !fixture,
        model_manifest: manifest_json,
        cases,
        tokens,
        generated_ids: generated,
        tensors: trace.tensors,
        payload_bytes: trace.bytes,
        payload_fnv1a64: format!("{:016x}", trace.hash),
    };
    serde_json::to_writer_pretty(create("trace.json")?, &new_reference)?;
    // Drop the model/client before the runtime so workers see a clean close.
    drop(model);
    for client in &connections {
        rt.block_on(async {
            client.lock().await.close().await;
        });
    }
    drop(connections);
    if reference.is_some() && !passed {
        return Err("correctness comparison failed; see report.json".into());
    }
    println!("correctness_verified={passed}");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn saved_comparison_checks_forced_trajectory_and_candidate_checksum() {
        let root = tempfile::tempdir().unwrap();
        let reference = root.path().join("reference");
        let candidate = root.path().join("candidate");
        let payload = [1f32, 0.]
            .into_iter()
            .flat_map(f32::to_le_bytes)
            .collect::<Vec<_>>();
        let mut hash = 0xcbf29ce484222325;
        fnv(&mut hash, &payload);
        let mut r = Reference {
            version: 1,
            full_model: false,
            model_manifest: serde_json::json!({"fixture":true}),
            cases: vec![Case {
                name: "a".into(),
                prompt_ids: vec![0],
            }],
            tokens: 1,
            generated_ids: vec![vec![0]],
            tensors: vec![Tensor {
                case: "a".into(),
                step: 0,
                layer: None,
                rows: 1,
                width: 2,
            }],
            payload_bytes: 8,
            payload_fnv1a64: format!("{hash:016x}"),
        };
        for dir in [&reference, &candidate] {
            std::fs::create_dir(dir).unwrap();
            std::fs::write(dir.join("trace.json"), serde_json::to_vec(&r).unwrap()).unwrap();
            std::fs::write(dir.join("tensors.f32"), &payload).unwrap();
            std::fs::write(dir.join("report.json"), br#"{"teacher_forced":false}"#).unwrap();
        }
        let compare = |trajectory, name| {
            compare_saved(
                reference.clone(),
                candidate.clone(),
                trajectory,
                root.path().join(name),
                0.,
                true,
            )
        };
        compare(None, "ok.json").unwrap();
        std::fs::write(candidate.join("report.json"), br#"{"teacher_forced":true}"#).unwrap();
        assert!(compare(None, "missing.json")
            .unwrap_err()
            .to_string()
            .contains("trajectory"));
        compare(Some(reference.clone()), "forced.json").unwrap();
        r.generated_ids[0][0] = 1;
        std::fs::write(
            candidate.join("trace.json"),
            serde_json::to_vec(&r).unwrap(),
        )
        .unwrap();
        assert!(compare(Some(reference.clone()), "wrong.json")
            .unwrap_err()
            .to_string()
            .contains("forced input"));
        r.generated_ids[0][0] = 0;
        std::fs::write(
            candidate.join("trace.json"),
            serde_json::to_vec(&r).unwrap(),
        )
        .unwrap();
        std::fs::write(
            candidate.join("tensors.f32"),
            [2f32, 0.]
                .into_iter()
                .flat_map(f32::to_le_bytes)
                .collect::<Vec<_>>(),
        )
        .unwrap();
        assert!(compare(Some(reference.clone()), "corrupt.json")
            .unwrap_err()
            .to_string()
            .contains("checksum"));
    }

    fn with_reference(run: impl FnOnce(&mut Trace, Tensor)) {
        let dir = tempfile::tempdir().unwrap();
        let bytes: Vec<u8> = [1f32, -2.].into_iter().flat_map(f32::to_le_bytes).collect();
        let path = dir.path().join("reference.f32");
        std::fs::write(&path, &bytes).unwrap();
        let mut hash = 0xcbf29ce484222325;
        fnv(&mut hash, &bytes);
        let tensor = Tensor {
            case: "check".into(),
            step: 0,
            layer: Some(2),
            rows: 1,
            width: 2,
        };
        let mut trace = Trace {
            output: BufWriter::new(File::create(dir.path().join("actual.f32")).unwrap()),
            reference: Some(BufReader::new(File::open(path).unwrap())),
            expected: vec![tensor.clone()],
            tensors: vec![],
            errors: vec![],
            tolerance: 0.,
            bytes: 0,
            hash: 0xcbf29ce484222325,
            expected_hash: Some(format!("{hash:016x}")),
            reference_hash: 0xcbf29ce484222325,
        };
        run(&mut trace, tensor);
    }

    #[test]
    fn exact_comparison_rejects_changed_values() {
        with_reference(|trace, tensor| {
            trace.push(tensor, &[1., -2.001]).unwrap();
            trace.finish().unwrap();
            assert!(!trace.errors[0].passed);
            assert_eq!(trace.errors[0].different_bits, 1);
        });
    }

    #[test]
    fn changed_tensor_order_and_nonfinite_values_are_rejected() {
        with_reference(|trace, mut tensor| {
            tensor.layer = Some(3);
            assert!(trace
                .push(tensor, &[1., -2.])
                .unwrap_err()
                .to_string()
                .contains("order/shape"));
        });
        with_reference(|trace, tensor| {
            assert!(trace.push(tensor, &[f32::NAN, -2.]).is_err());
        });
    }

    #[test]
    fn missing_tensors_and_corrupt_reference_checksum_are_rejected() {
        with_reference(|trace, _| assert!(trace.finish().is_err()));
        with_reference(|trace, tensor| {
            trace.expected_hash = Some("bad checksum".into());
            trace.push(tensor, &[1., -2.]).unwrap();
            assert!(trace.errors[0].passed);
            assert!(trace.finish().unwrap_err().to_string().contains("checksum"));
        });
    }
}
