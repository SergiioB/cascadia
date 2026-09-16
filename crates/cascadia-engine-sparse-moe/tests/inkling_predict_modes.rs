//! Predicted-read reader-mode precedence + mutual exclusion. The tiers are
//! gated by process-global `OnceLock`s, so this is a SEPARATE test binary that
//! turns the EARLY tier on together with the SECOND and THIRD tiers, then proves
//! the guard: EARLY takes precedence, so SECOND (and therefore THIRD, which
//! additionally needs a nonzero cache) never activate. The visible consequence
//! is that only ONE predicted-read worker is ever started
//! (`prediction_read_worker_count() == 1`) and the second/third readers schedule
//! nothing, even though their env flags are set — combining flags cannot expand
//! the bound past EARLY's "current + next" two live reads.
//!
//! EARLY mode is also bit-identical to the default path (predicted reads only
//! prefetch bytes the kernel would read anyway), so greedy decode over the tiny
//! int4 mmap export still matches `reference.json`'s HF tokens. The fast path
//! only engages for mmap'd int4 experts, so this uses the same
//! `load_model_with(_, ExpertsMode::Mmap)` setup as `inkling_loader.rs`.

use std::path::PathBuf;

use cascadia_engine_sparse_moe::dsv4::loader::ExpertsMode;
use cascadia_engine_sparse_moe::inkling::loader::load_model_with;
use cascadia_engine_sparse_moe::inkling::moe::pipeline_read_layer_count;
use cascadia_engine_sparse_moe::inkling::{
    prediction_read_statistics, prediction_read_worker_count, second_prediction_read_statistics,
    third_prediction_read_statistics,
};

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
fn early_predict_mode_takes_precedence_and_stays_bit_identical() {
    // The base fast path, plus EARLY and the SECOND/THIRD tiers. EARLY must
    // suppress SECOND and THIRD despite their flags being set.
    std::env::set_var("CASCADIA_INKLING_REUSE_READ_BUFFERS", "1");
    std::env::set_var("CASCADIA_INKLING_PIPELINE_READS", "1");
    std::env::set_var("CASCADIA_INKLING_PREDICT_READS", "1");
    std::env::set_var("CASCADIA_INKLING_EXPERT_CACHE_MIB", "8");
    std::env::set_var("CASCADIA_INKLING_EARLY_PREDICT_READS", "1");
    std::env::set_var("CASCADIA_INKLING_SECOND_PREDICT_READS", "1");
    std::env::set_var("CASCADIA_INKLING_THIRD_PREDICT_READS", "1");

    let Some((prompt, want)) = reference() else {
        return;
    };
    let mut mm = load_model_with(&export_dir(), 64, ExpertsMode::Mmap).expect("mmap model");
    let got = mm.greedy(&prompt, want.len());
    assert_eq!(
        got, want,
        "EARLY predicted-read decode diverged from the default path"
    );

    let cache = mm.expert_cache_stats();
    let pred = prediction_read_statistics();
    let second = second_prediction_read_statistics();
    let third = third_prediction_read_statistics();
    eprintln!(
        "early mode: workers {} cache {{hits {} admissions {}}} pipeline_layers {} \
         predicted {{scheduled {} useful {}}} second.scheduled {} third.scheduled {}",
        prediction_read_worker_count(),
        cache.hits,
        cache.admissions,
        pipeline_read_layer_count(),
        pred.scheduled,
        pred.useful,
        second.scheduled,
        third.scheduled,
    );

    // Non-vacuity: the fast path (cache + pipeline + predicted reads) ran.
    assert!(cache.capacity_bytes > 0, "expert cache was not configured");
    assert!(
        pipeline_read_layer_count() > 0,
        "overlapped read/compute pipeline never ran"
    );
    assert!(cache.hits > 0, "expert cache served no hits");
    assert!(pred.scheduled > 0, "no predicted reads were scheduled");

    // The guard: EARLY takes precedence, so exactly one reader worker exists and
    // the SECOND/THIRD tiers stay dormant even with their flags on.
    assert_eq!(
        prediction_read_worker_count(),
        1,
        "EARLY precedence broken: a SECOND/THIRD predicted-read worker was started"
    );
    assert_eq!(
        second.scheduled, 0,
        "SECOND predicted reads ran while EARLY was enabled"
    );
    assert_eq!(
        third.scheduled, 0,
        "THIRD predicted reads ran while EARLY was enabled"
    );
}
