//! Opt-in decode fast path parity: with the expert cache + pipelined reads +
//! predicted reads + reusable read buffers all enabled
//! (`CASCADIA_INKLING_{REUSE_READ_BUFFERS,PIPELINE_READS,PREDICT_READS}` on and
//! a nonzero `CASCADIA_INKLING_EXPERT_CACHE_MIB`), greedy decode over the tiny
//! int4 mmap export must be **token-identical** to the default path — the
//! #155/#156 regression surface. Every gate is a process-global `OnceLock` read
//! once (at layer construction / first decode), so this is a SEPARATE test
//! binary that sets the flags before the model is built.
//!
//! The cache / pipeline / predicted-read machinery only activates for mmap'd
//! int4 experts (`AnyExpert::as_mmap()` must be `Some`), so this drives the
//! `inkling_export` int4 fixture through `load_model_with(_, ExpertsMode::Mmap)`
//! — the same setup `inkling_loader.rs` uses for the real packed kernel. The
//! reference greedy ids are `reference.json`'s HF `generate(do_sample=False)`
//! tokens, which the default (flags-off) path already matches
//! (`inkling_loader::mmap_model_matches_the_reference_and_the_eager_model`).
//!
//! Non-vacuity: parity alone would still hold if the whole fast path silently
//! regressed to the plain mmap path, so the public diagnostics must also show
//! the cache served hits, the overlapped read/compute pipeline ran, and
//! predicted reads were dispatched.

use std::path::PathBuf;

use cascadia_engine_sparse_moe::dsv4::loader::ExpertsMode;
use cascadia_engine_sparse_moe::inkling::loader::load_model_with;
use cascadia_engine_sparse_moe::inkling::moe::pipeline_read_layer_count;
use cascadia_engine_sparse_moe::inkling::prediction_read_statistics;

fn export_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/inkling_export")
}

/// `(prompt_ids, greedy_ids)` from the tiny export's `reference.json`, or `None`
/// when the fixture is absent (mirrors `inkling_loader.rs`).
fn reference() -> Option<(Vec<u32>, Vec<u32>)> {
    let p = export_dir().join("reference.json");
    if !p.exists() {
        eprintln!("inkling_export/reference.json missing; skipping (run export_inkling.py --tiny)");
        return None;
    }
    let v: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap();
    let ids = |k: &str| -> Vec<u32> {
        v[k].as_array()
            .unwrap_or_else(|| panic!("reference.json: {k}"))
            .iter()
            .map(|x| x.as_u64().unwrap() as u32)
            .collect()
    };
    Some((ids("prompt_ids"), ids("greedy_ids")))
}

#[test]
fn opt_in_decode_cache_path_is_bit_identical_to_default() {
    // Turn the opt-in fast path on for the whole process. SEQ_READS and
    // SERIAL_EXPERTS are left unset so the pipelined, parallel expert path
    // stays enabled (both are required by `MoeLayer::new` to size the cache).
    std::env::set_var("CASCADIA_INKLING_REUSE_READ_BUFFERS", "1");
    std::env::set_var("CASCADIA_INKLING_PIPELINE_READS", "1");
    std::env::set_var("CASCADIA_INKLING_PREDICT_READS", "1");
    std::env::set_var("CASCADIA_INKLING_EXPERT_CACHE_MIB", "8");

    let Some((prompt, want)) = reference() else {
        return;
    };
    let mut mm = load_model_with(&export_dir(), 64, ExpertsMode::Mmap).expect("mmap model");
    let got = mm.greedy(&prompt, want.len());
    assert_eq!(
        got, want,
        "opt-in cache/pipeline/predicted-read decode diverged from the default path"
    );

    // Non-vacuity: prove the fast path actually executed.
    let cache = mm.expert_cache_stats();
    let pred = prediction_read_statistics();
    eprintln!(
        "decode fast path: cache {{cap {} hits {} misses {} admissions {}}} pipeline_layers {} \
         predicted {{scheduled {} successful {} useful {} unused {}}}",
        cache.capacity_bytes,
        cache.hits,
        cache.misses,
        cache.admissions,
        pipeline_read_layer_count(),
        pred.scheduled,
        pred.successful,
        pred.useful,
        pred.unused,
    );
    assert!(cache.capacity_bytes > 0, "expert cache was not configured");
    assert!(
        pipeline_read_layer_count() > 0,
        "overlapped read/compute pipeline never ran"
    );
    assert!(cache.hits > 0, "expert cache served no hits");
    assert!(pred.scheduled > 0, "no predicted reads were scheduled");
    assert!(
        pred.useful > 0,
        "no predicted read was consumed into the kernel"
    );
}
