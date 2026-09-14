//! Hot/cold overlapped decode, all-hot fast path: with every routed expert
//! non-resident-free (here, held EAGER so `as_mmap()` is `None`), the hot/cold
//! classifier marks every slot hot, `ncold == 0`, and the branch takes the
//! zero-overhead fast path — plain per-expert compute, no reader threads, no
//! buffer copies. `HOTCOLD=cold` still routes through the hot/cold dispatch
//! (it is not a no-op), so this is the deterministic coverage of the
//! `ncold == 0` arm that the mmap-backed forced/probe binaries never reach.
//!
//! Separate test binary so the process-global CASCADIA_GLM5_HOTCOLD flag (read
//! once via OnceLock) is on for the whole run.
//!
//! Requires the export fixture (run tools/glm5_ref/gen_fixtures.py).

use std::path::PathBuf;

use cascadia_engine_sparse_moe::glm::prof;
use cascadia_engine_sparse_moe::glm::stage::GlmRunner;
use cascadia_engine_sparse_moe::staged::StagedRunner;

#[test]
fn hotcold_allhot_fast_path_is_plain_compute() {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/glm5_export");
    // Eager experts are not mmap, so ForceCold classifies every slot HOT ->
    // ncold == 0. PROFILE populates the counters so we can prove it.
    std::env::set_var("CASCADIA_GLM5_EXPERTS", "eager");
    std::env::set_var("CASCADIA_GLM5_HOTCOLD", "cold");
    std::env::set_var("CASCADIA_GLM5_PROFILE", "1");
    let got = GlmRunner::load_staged(&dir, 32, 0, 1, 0, 0, Default::default())
        .unwrap()
        .generate_argmax(&[1, 2, 3, 4], 4);
    std::env::remove_var("CASCADIA_GLM5_EXPERTS");
    std::env::remove_var("CASCADIA_GLM5_HOTCOLD");
    std::env::remove_var("CASCADIA_GLM5_PROFILE");
    // The dispatch entered the hot/cold branch and classified every slot hot:
    // the all-hot fast path ran, deterministically, with no reader threads.
    let (hot, cold, fail) = prof::hotcold_counts();
    assert!(hot > 0, "all-hot fast path never classified a hot slot");
    assert_eq!(cold, 0, "eager experts must never be cold (cold={cold})");
    assert_eq!(fail, 0, "the fast path spawns no reads, so nothing can fail");
    // Fast path == plain eager compute: greedy is the eager reference the
    // glm5_expert_mmap parity test tracks against mmap.
    assert_eq!(
        got,
        vec![4u32, 10, 3, 15],
        "all-hot hot/cold path diverged from the eager reference"
    );
}
