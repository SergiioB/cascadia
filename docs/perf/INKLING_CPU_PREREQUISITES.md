# Inkling CPU prerequisites for GPU and expert routing

This change brings the CPU runtime used by the iGPU work in PR #155 and the
expert-routing work in PR #156 onto current `main`. It applies the native
runtime/test delta from `d690bf53` to `fdcc0433` while preserving the loader,
shape validation, encapsulation and transport fixes already merged in #154.
It does not import the autolab controller, CUDA exporter, deployment files,
generated run results or GPU backends.

## Runtime changes

- Optional mapped BF16 embeddings, owned packed shared experts and reusable
  bounded read buffers reduce copies and repeated expert-file reads.
- A bounded expert cache supports request-history reset, decay and recency
  admission; cache statistics are exposed for benchmark and GPU integration.
- Pipelined/prefill reads and bounded causal prediction reads can overlap I/O
  with compute. Predictions only fetch bytes: the real router still selects
  experts, and misses fall back to the original selected expert's read. Early,
  second and third prediction controls remain separate opt-in settings.
  Prediction reads require a nonzero expert cache; early mode takes precedence
  over the second/third-reader options to preserve the live-read bound.
- BF16 task grain and AVX2 int4 row tiling are selectable scheduling controls.
  They preserve the existing arithmetic rather than changing quantization.
- `inkling_decode_bench` measures full greedy generation with explicit fixture
  labeling, reference-ID checks, logits hashes, and optional layer/route traces.
  `inkling_bench` is a separate synthetic layer probe.

Storage/read/cache options default off unless explicitly enabled. Packed-byte
budgets are not physical page locking or a guarantee that weights remain in RAM.
The shared `dsv4` storage/math and `glm::AnyExpert` helpers are dependencies of
Inkling's CPU path; this PR does not change the GLM router or serving policy.

## Historical hardware result

The original promoted CPU profile measured **1.1161344306 decode tok/s** on the
complete 66-layer model on tate-07. This is a historical measurement of its
recorded Windows binary, not a new measurement of the integrated branch.
The exact source/binary hashes, environment, nine samples, output hash and
calculation remain in the archived
[reproduction record](https://github.com/labscommunity/cascadia/blob/fdcc043370ebc0dc56da414e94edf5b037f8b778/tools/inkling_autolab/INKLING_129_REPRODUCTION.md).
Keep new benchmark output outside tracked source, for example in `experiments/`.

## Validation

Integration checks on macOS ARM passed formatting, workspace clippy and the
full workspace suite: 1,004 tests passed, four intentionally ignored. Separate
promoted-profile and early-prediction fixture processes each generated 96 tokens
with the same IDs and full logits hash (`3018e9c864366f86`) as the default path.
Both exercised cache hits and successful prediction reads. These checks do not
re-measure full-model throughput, AVX2 kernels or Windows direct I/O on this Mac.

The native tests cover mapped versus owned embedding values and generation,
packed shared-expert equality, bounded read/cache behavior, observers that
preserve logits, and existing Inkling loading, reset, prefill, pipeline and
expert-parallel transport behavior. The tiny fixtures are correctness checks;
they do not predict full-model throughput.

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets
cargo build -p cascadia
cargo test --workspace --all-targets
```

Build the CLI before workspace tests because the end-to-end tests execute its
standalone binary. For a focused check:

```sh
cargo test -p cascadia-engine-sparse-moe --lib --test 'inkling_*'
```

Opt-in settings are cached per process. Run differing environment profiles in
separate processes when comparing their generated IDs and logits hashes.

## Merge order

1. Review and merge this CPU prerequisites PR into `main` first. Its source
   changes are the foundation for the two existing feature PRs.
2. Transplant **only the GPU changes after `fdcc043370ebc0dc56da414e94edf5b037f8b778`**
   from `feat/inkling-igpu` onto updated `main`. Resolve against current `main`'s
   APIs and rerun checks. Retarget #155 to `main` only after that transplant;
   do not merge #155 into the old autolab branch. Review and merge #155 next.
3. Transplant **only the expert-routing changes after
   `f660b51885204837b6bfe28fb44049767fb8a5d9`** from
   `feat/inkling-expert-routing` onto `main` after #155 lands. Preserve the final
   artifact cleanup in `8c919d73`, rerun checks, retarget #156 to `main`, and
   merge #156 last.

Save each current branch tip before rewriting a shared branch and account for
any later commits. Check the final file list: #155 should contain GPU changes,
and #156 should contain routing changes, without autolab output or archived
experiment directories. Merely changing the PR base is insufficient because
the original branches still carry the old autolab ancestry. This PR does not
merge or rewrite either downstream branch.
