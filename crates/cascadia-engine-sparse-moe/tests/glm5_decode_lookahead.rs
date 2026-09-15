//! Decode-side lookahead parity: with CASCADIA_GLM5_LOOKAHEAD=1 the decode
//! loop runs the router-proxy predictor and enqueues layer i+1's non-resident
//! experts for the shared lookahead worker to warm. Warming is read-only
//! page-cache traffic racing the compute thread's own mmap access, so greedy
//! generation must be **token-identical** to the plain mmap reference.
//!
//! Guards the decode-path guard refactor introduced with prefill streaming:
//! the branch changed from `if let Some(lookahead)` to
//! `if let (true, Some(lookahead)) = (self.lookahead_decode, ...)`, and no test
//! set CASCADIA_GLM5_LOOKAHEAD before. This catches a panic or output
//! divergence in that guarded decode path.
//!
//! Separate test binary so the process-global CASCADIA_GLM5_LOOKAHEAD flag
//! (read at load) is on for the whole run.
//!
//! Requires the export fixture (run tools/glm5_ref/gen_fixtures.py).

use std::path::PathBuf;

use cascadia_engine_sparse_moe::glm::stage::GlmRunner;
use cascadia_engine_sparse_moe::staged::StagedRunner;

#[test]
fn decode_lookahead_matches_mmap_reference() {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/glm5_export");
    // Force mmap experts (so the lookahead path is actually exercised) +
    // decode lookahead on.
    std::env::set_var("CASCADIA_GLM5_EXPERTS", "mmap");
    std::env::set_var("CASCADIA_GLM5_LOOKAHEAD", "1");
    let got = GlmRunner::load_staged(&dir, 32, 0, 1, 0, 0, Default::default())
        .unwrap()
        .generate_argmax(&[1, 2, 3, 4], 4);
    std::env::remove_var("CASCADIA_GLM5_EXPERTS");
    std::env::remove_var("CASCADIA_GLM5_LOOKAHEAD");
    // Same reference as glm5_expert_mmap's mmap path → decode lookahead is inert
    // on output.
    assert_eq!(
        got,
        vec![4u32, 10, 3, 15],
        "decode lookahead diverged from the mmap reference"
    );
}
