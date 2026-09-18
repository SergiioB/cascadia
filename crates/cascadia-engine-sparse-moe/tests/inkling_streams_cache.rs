//! Multi-stream decode through the batched MoE path with the explicit expert
//! cache on: the second pass over the same streams must hit the cache, and
//! every token/logit must stay bit-identical to the eager (in-RAM) reference.
//! Own process: the cache is configured through process-wide env.

use std::path::PathBuf;

use cascadia_engine_sparse_moe::inkling::stage::InklingRunner;
use cascadia_engine_sparse_moe::staged::StagedRunner;

fn argmax(v: &[f32]) -> u32 {
    let mut b = 0;
    for (i, &x) in v.iter().enumerate() {
        if x > v[b] {
            b = i;
        }
    }
    b as u32
}

fn run_batched(
    r: &mut InklingRunner,
    prompts: &[Vec<u32>],
    n: usize,
) -> Vec<(Vec<u32>, Vec<Vec<f32>>)> {
    let hs = r.hidden_size();
    let mut st: Vec<(usize, Vec<u32>, Vec<Vec<f32>>)> = Vec::new();
    for p in prompts {
        let slot = r.open_stream().unwrap();
        let mut batch = Vec::new();
        for &t in p {
            batch.extend(r.embed_token(t));
        }
        let h = r.prefill_stream(slot, batch, p.len());
        let l = r.head_logits(&h[(p.len() - 1) * hs..]);
        st.push((slot, vec![argmax(&l)], vec![l]));
    }
    while st[0].1.len() < n {
        let slots: Vec<usize> = st.iter().map(|s| s.0).collect();
        let mut batch = Vec::new();
        for s in &st {
            batch.extend(r.embed_token(*s.1.last().unwrap()));
        }
        let h = r.decode_streams(batch, &slots);
        let logits = r.head_logits_rows(&h, slots.len());
        let vocab = logits.len() / slots.len();
        for (i, s) in st.iter_mut().enumerate() {
            let l = logits[i * vocab..(i + 1) * vocab].to_vec();
            s.1.push(argmax(&l));
            s.2.push(l);
        }
    }
    for s in &st {
        r.close_stream(s.0);
    }
    st.into_iter().map(|s| (s.1, s.2)).collect()
}

#[test]
fn batched_decode_with_expert_cache_is_bit_identical_and_hits_on_the_second_pass() {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/inkling_export");
    if !dir.join("reference.json").exists() {
        return;
    }
    // Cache profile (read once per process, so before any runner loads):
    // mmap experts, owned-buffer reads, explicit cache big enough for every
    // expert of every layer. The eager reference ignores these (no mmap).
    std::env::set_var("CASCADIA_INKLING_EXPERT_CACHE_MIB", "64");
    std::env::set_var("CASCADIA_INKLING_REUSE_READ_BUFFERS", "1");
    std::env::set_var("CASCADIA_INKLING_PIPELINE_READS", "1");
    std::env::set_var("CASCADIA_INKLING_PREFILL_READS", "1");
    std::env::set_var("CASCADIA_INKLING_SKIP_BULK_PREFETCH", "1");
    let v: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(dir.join("reference.json")).unwrap())
            .unwrap();
    let p1: Vec<u32> = v["prompt_ids"]
        .as_array()
        .unwrap()
        .iter()
        .map(|x| x.as_u64().unwrap() as u32)
        .collect();
    let p2: Vec<u32> = p1.iter().rev().copied().collect();
    let prompts = vec![p1.clone(), p2];
    let n = 8;

    // Reference: eager experts (RAM), no cache machinery.
    let mut eager =
        InklingRunner::load_staged(&dir, 64, 0, 1, 0, 0, Some("eager".into()), None).unwrap();
    assert!(eager.configure_streams(2));
    let want = run_batched(&mut eager, &prompts, n);
    let hf: Vec<u32> = v["greedy_ids"]
        .as_array()
        .unwrap()
        .iter()
        .map(|x| x.as_u64().unwrap() as u32)
        .collect();
    assert_eq!(
        &want[0].0[..hf.len()],
        &hf[..],
        "eager reference must match the HF greedy ids"
    );

    let mut cached =
        InklingRunner::load_staged(&dir, 64, 0, 1, 0, 0, Some("mmap".into()), None).unwrap();
    assert!(cached.configure_streams(2));
    let pass1 = run_batched(&mut cached, &prompts, n);
    let pass2 = run_batched(&mut cached, &prompts, n);
    for (name, got) in [("pass 1", &pass1), ("pass 2", &pass2)] {
        for (i, ((gt, gl), (wt, wl))) in got.iter().zip(&want).enumerate() {
            assert_eq!(
                gt, wt,
                "{name} stream {i}: tokens differ from the eager reference"
            );
            for (step, (a, b)) in gl.iter().zip(wl).enumerate() {
                assert_eq!(
                    a.iter().map(|x| x.to_bits()).collect::<Vec<_>>(),
                    b.iter().map(|x| x.to_bits()).collect::<Vec<_>>(),
                    "{name} stream {i} step {step}: logits differ"
                );
            }
        }
    }
    let stats = cached.expert_cache_stats_total();
    eprintln!("expert cache after two passes: {stats:?}");
    assert!(stats.hits > 0, "the second pass must hit the cache");
    assert!(stats.retained_bytes > 0, "misses must be admitted");
}
