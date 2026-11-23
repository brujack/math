# zeta: Certified RH Verification Implementation Plan

spec: docs/superpowers/specs/2026-11-23-zeta-rh-verification-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Rust-only `zeta` CLI, which proves that every nontrivial zero of ζ with 0 < Im s ≤ 10^N (N = 2–7) lies on the critical line and is simple, using certified interval arithmetic.

**Architecture:** A library crate `zeta/zeta-rs` (modules `interval`, `config`, `theta`, `zfun`, `isolate`, `turing`, `verify`, `spacing`) plus a thin `main.rs` in goldbach's shape. Signs of Hardy's Z are certified with MPFR directed rounding through `rug`; zeros are counted in one sorted pass over exact `f64` sample points; Turing's method bounds the total count. The work ships as three PRs so no PR mutates the whole crate (V8).

**Tech Stack:** Rust edition 2024, `rug` 1.30 (`integer`, `float`), `rayon`, `clap` 4, `proptest`, `criterion`, `tempfile`; cargo-nextest; cargo-mutants 27.1.0.

## Global Constraints

- The spec's effective Requirements block (`python3 ~/.claude/scripts/spec_contract.py docs/superpowers/specs/2026-11-23-zeta-rh-verification-design.md`) is the contract; R19 and R22 are as amended on 2026-11-23.
- Every crate file the templates render comes from `scripts/crate_templates/` via `python3 scripts/render_crate_files.py --write`; never hand-edit a rendered file (operator rule, all crates identical).
- `Cargo.toml`: edition 2024, `license = "MIT"`, `[lints.rust] unsafe_code = "forbid"`, `missing_debug_implementations = "warn"`, `unexpected_cfgs` for `tarpaulin_include`, `[lints.clippy] wrong_self_convention = "warn"`, no `rust-version`; copy descartes-rs's `[profile.release]`.
- No `unsafe`, no native library beyond GMP/MPFR (N2); no `#[ignore]` tests and no change to the shared crate templates or `scripts/rust-check.sh` (N7).
- A sign is certified only when both interval bounds are finite and exclude 0 (R5).
- The pinned formulas in the appendix (from V2) are the only formulas to implement; do not substitute others from memory.
- Commit messages: `caveman:caveman-commit`; this repo is public, so no private paths or audit text in commits or PR bodies.

## Pre-plan measurements (spec V1, V2, V8, recorded 2026-11-23)

- **V1:** minimum ratio of max |Z| between consecutive zeros to 0.127·t^(−3/4) below 10⁷ is 12.05, at the pair 4316832.467101349 / 4316832.469424753 (peak 1.6163·10⁻⁵ against 1.3410·10⁻⁶); next 18.83. C₀ only stands. The scan reproduced every decade count up to N(10⁷) = 21,136,125, the first Rosser failure at [g_13999525, g_13999527), and Lehmer's pair (ratio 23.92).
- **V2:** see the appendix. Discrepancies already amended into the spec: Trudgian's range is strict (b_M > 168π); Turing's block count follows Trudgian 2011 eq. 2.1; a Gram point in Turing's region without a certified bracket fails the candidate. θ uses DLMF 5.11 Stirling with a shift of 10 (Gabcke's θ bound needs t ≥ 10 and g₋₁ ≈ 9.667).
- **V8:** prototype warm debug `cargo test` baseline B = 4.4 s; cargo-mutants took about 4.6 s per mutant; a whole-crate first PR (about 500 mutants) projects to 53–110 minutes. Therefore (a) the crate ships in three PRs, and (b) `zeta/zeta-rs/.cargo/mutants.toml` skips the end-to-end tests by name (Task 10), with every line they alone reach covered by unit tests.

## Verification Planning

- **Whole change:** after PR 3 merges, `make -C zeta/zeta-rs zeta && zeta/zeta-rs/target/release/zeta 3` prints `RH verified: all 649 nontrivial zeros with 0 < Im s <= 1000 lie on Re s = 1/2 and are simple`, exits 0 and writes `zeta_1e3.txt` with 649 non-`#` lines.
- **Expected:** counts 29 (N = 2), 649 (N = 3), 10,142 (N = 4, V7); exit 3 with a named block for every negative control; exit 6 for every implementation-fault fake.
- **Edge cases:** N = 1 and N = 8 exit 1; end of input at the prompt; the self-check failure paths; a write failure (exit 4); the pool forced to fail (byte-identical output); T inside g_M's bracket.
- **Post-merge obligations (orchestrator, on `claude`, recorded in the last PR):** V3 (N = 5, 6, 7 counts, time, RSS, uncertified-before-retry, precision histogram), V4 (N = 7 passes the Rosser failure), V5 (`zeta 3 --refine` KS below 0.1), V6 (`make test` per-test time under tarpaulin on `ubuntu-latest`, from the coverage job log), V7 (`zeta 4` and `zeta 4 --refine` against the first 10,142 Odlyzko zeros).

## PR structure (orchestrator)

- **PR 1** `feat/zeta-foundation`: Tasks 1–4 (crate, interval, config, θ and Gram brackets). Split from the original Tasks 1–6 on 2026-11-23 because mutation of `interval.rs` and `theta.rs` alone took about 14 minutes locally and `mutation-rs` is one 60-minute CI job. Open with `gh pr create --draft`; `gh pr ready` only after Phase 3 passes. In this PR `zeta N` prints `RH NOT verified: zeta is under construction` to stderr and exits 3.
- **PR 2** `feat/zeta-core`: Tasks 5–6, rebased onto master after PR 1 merges (`git rebase --onto origin/master <PR 1 tip> feat/zeta-core`). After PR 2, `zeta N` runs the self-check and prints `RH NOT verified up to <T>: zero isolation is not implemented yet` with exit 3; Task 10 replaces this.
- **PR 3** `feat/zeta-verify`: Tasks 7–10, branched from master after PR 2 merges.
- **PR 4** `feat/zeta-refine-cli`: Tasks 11–12, branched from master after PR 3 merges.
- No PR's binary ever claims verification before Task 10 (R3).

---

### Task 1: Scaffold the crate and register it as the 13th

```yaml-task
id: 1
description: Create zeta/zeta-rs (Cargo.toml, empty lib, minimal main), render its templated files, and update every place that pins the crate count or lists crates
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
  - cmd: make test
    exit_code: 0
  - cmd: make lint
    exit_code: 0
  - cmd: test "$(wc -c < CLAUDE.md)" -le 30000
    exit_code: 0
max_retries: 3
files_touched: [CLAUDE.md, zeta/zeta-rs/Cargo.toml, zeta/zeta-rs/Cargo.lock, zeta/zeta-rs/src/lib.rs, zeta/zeta-rs/src/main.rs, zeta/zeta-rs/Makefile, zeta/zeta-rs/rustfmt.toml, zeta/zeta-rs/.config/nextest.toml, zeta/zeta-rs/install_deps.sh, .github/workflows/zeta-rs.yml, .github/workflows/release-zeta-rs.yml, .github/workflows/benchmarks.yml, .github/workflows/release-sbom-monitor-schedule.yml, zeta/zeta-rs/benches/zeta.rs, scripts/render_crate_files.py, scripts/cargo-deny-all.sh, scripts/pre-commit, scripts/pre-push, tests/test_crate_uniformity.py, tests/scripts/cargo_deny_all.bats, tests/test_deny_policy.py, tests/test_release_workflows.py, tests/test_rust_ci_jobs.py, tests/test_gmp_cache_workflow.py, tests/scripts/makefile.bats, tests/scripts/crate_build_target.bats, tests/test_mutation_workflows.py, tests/test_rust_workflows_no_system_gmp.py, zeta/zeta-rs/CLAUDE.md, .gitignore]
depends_on: []
requirements: [R15]
```

**Files:** as listed. Before editing, run `git grep -n -e '\b12\b' -e descartes -- tests scripts .github` and update every crate-count pin and crate list that the new crate changes (the list above is the expected set; add any other pinning test to this task, per writing-plans self-review item 11).

- [ ] Add `"zeta"` to both `CRATES` lists in `scripts/render_crate_files.py`; run `--write`.
- [ ] Change the hard-coded 12 to 13 in `tests/test_crate_uniformity.py` and `EXPECTED_CRATES=13` in `scripts/cargo-deny-all.sh` (and its bats fixture).
- [ ] Add `zeta/zeta-rs` to the `dirs` lists in `scripts/pre-commit` and `scripts/pre-push`, `zeta/zeta-rs:zeta` to `benchmarks.yml`, a `zeta` entry to `release-sbom-monitor-schedule.yml`, and `zeta_1e*.txt` to `.gitignore`.
- [ ] `Cargo.toml` per Global Constraints, `[[bin]] zeta`, `[lib] zeta`, deps `clap` (derive) only, since `cargo-machete` rejects an unused dependency (Task 2 adds `rug`, Task 9 adds `rayon`); a minimal `zeta/zeta-rs/CLAUDE.md` like the other crates' (the uniformity test requires one; Task 12 completes it); dev-deps `tempfile`, `proptest`, `criterion = "0.8"`; `[[bench]] zeta`.
- [ ] Root `CLAUDE.md`: every "12 crates" / "12 Rust installers" / "all 12" statement becomes 13, `zeta/` Rust joins the sub-project list and the Rust crate list. The file is at 29,999 bytes against a 30,000 cap, so trim an equal number of bytes elsewhere without dropping a rule (shorten wording, never delete a rule line).
- [ ] `src/main.rs`: thin `main` under `#[cfg(not(tarpaulin_include))]`; a unit test that `--help` parses. `benches/zeta.rs`: a placeholder bench Task 5 fills.

**Interfaces:** Produces the crate skeleton every later task extends.

### Task 2: Interval arithmetic with directed rounding

```yaml-task
id: 2
description: Implement interval.rs, an MPFR interval type whose operations enclose the true value, with proptest containment tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/interval.rs, zeta/zeta-rs/src/lib.rs, zeta/zeta-rs/Cargo.toml, zeta/zeta-rs/Cargo.lock, tests/test_release_workflows.py, tests/test_gmp_cache_workflow.py]
depends_on: [1]
requirements: [R5, R18]
```

- [ ] Add `rug = { version = "1.30", features = ["integer", "float"] }` to `Cargo.toml` and refresh `Cargo.lock`. zeta now locks `gmp-mpfr-sys`: add `zeta` to `gmp_crates` in `tests/test_release_workflows.py`, set its `no_lgpl` pin (about line 677) back to 7, and make the `test_gmp_cache_workflow.py` comment say 7 of the 13 (verify with `grep -L gmp-mpfr-sys */*-rs/Cargo.lock | wc -l`). The acceptance gate adds `make test`.
- [ ] `pub struct Interval { lo: Float, hi: Float }` (`#[derive(Debug, Clone)]`), constructors `point(f64, prec)`, `new(lo, hi)`; `add`, `sub`, `mul`, `div` (error when the divisor contains 0), `sqrt`, `ln` (error when lo ≤ 0), `exp`, `cos`, `sin`, `widen(&Float)`, `excludes_zero()`, `sign() -> Option<Sign>`, `width()`.
- [ ] `lo` uses `Round::Down`, `hi` uses `Round::Up` (`*_round` methods, `AddAssignRound` and siblings).
- [ ] `excludes_zero()` is true only when both bounds are finite and `lo > 0` or `hi < 0`.
- [ ] `cos`/`sin`: argument wider than π returns [−1, 1]; otherwise m = midpoint, r = max(hi − m, m − lo) rounded up, f(m) evaluated rounded down and rounded up, result widened by r.
- [ ] Tests, written first: proptest over random intervals with magnitudes up to 10⁹, each operation's enclosure contains the value computed at 4× precision with outward rounding; zero-width `cos`/`sin` inputs; width shrinks as precision grows; `excludes_zero()` false for NaN and infinite bounds; error paths for `div` and `ln`.

**Interfaces:** Produces `zeta::interval::{Interval, Sign, IntervalError}`; `new`, `div`, `ln` and `sqrt` return `Result<_, IntervalError>` (`sqrt` errors when lo < 0); a NaN from an indeterminate form widens that bound to its infinity.

### Task 3: Widen-only configuration

```yaml-task
id: 3
description: Implement config.rs, VerifyConfig with private fields whose constructor only allows settings that make certification harder
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/config.rs, zeta/zeta-rs/src/lib.rs]
depends_on: [1]
requirements: [R24]
```

- [ ] Private fields: `gabcke_multiplier: f64` (default 1.0), `precision_cap: u32` (default 512), `depth_cap: u32` (default 40), `move_points: bool` (default true); getters only.
- [ ] `VerifyConfig::new(...) -> Result<Self, ConfigError>` rejects a multiplier that is not finite or is below 1, a precision cap below 64 or above 512, a depth cap above 40.
- [ ] Tests, first: rejects 0.5, NaN, ±∞, precision 0, 1, 63 and 513, depth 41; accepts 1.0 and turning point moving off; `VerifyConfig::default()` passes `new`'s validation. A compile-fail check is not needed: fields are private, so a struct literal outside `config.rs` does not compile.

**Interfaces:** Produces `zeta::config::VerifyConfig`.

### Task 4: θ, Gram points and certified Gram brackets

```yaml-task
id: 4
description: Implement theta.rs with a certified θ(t) enclosure and certified Gram brackets (b_n, c_n), tested against an mpmath fixture
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/theta.rs, zeta/zeta-rs/src/lib.rs, zeta/zeta-rs/src/interval.rs, zeta/zeta-rs/tests/fixtures/gram_points.txt]
depends_on: [2]
requirements: [R22]
```

- [ ] θ(t) = Im ln Γ(1/4 + it/2) − (t/2) ln π with the DLMF 5.11 Stirling series and its remainder bound (appendix §3), shifting z by 10 via the recurrence; returns an `Interval`.
- [ ] `Interval::atan` (increasing, endpoint images rounded outward) in `interval.rs`: arg z = atan(y/x) for Re z > 0 and each shift term Im Ln(z+k) = atan(y/(x+k)) need it.
- [ ] `gram_bracket(n, prec) -> Option<(f64, f64)>`: finds `f64` values 2π < b < c with θ(b) − nπ < 0 and θ(c) − nπ > 0 both certified; returns `None` when it cannot certify or the search leaves t > 2π.
- [ ] Fixture `tests/fixtures/gram_points.txt`: g_n for n = −1, 0, 100, 1000 at 30 digits, generated with mpmath (`mp.dps = 40`; `findroot(lambda t: siegeltheta(t) - n*pi, guess)`), command and mpmath version in its header.
- [ ] Tests, first: b < g_n < c for the fixture values; b_n strictly increasing over n = −1..1000; a shifted fake enclosure that contains nπ in θ's range but not g_n fails the endpoint certificate; θ's enclosure at t = 9.667 and t = 2π is narrower than 10⁻²⁰ at 128 bits.

**Interfaces:** Consumes `Interval`. Produces `zeta::theta::{theta, gram_bracket}`.

### Task 5: Hardy Z by Riemann–Siegel and Euler–Maclaurin, and the self-check

```yaml-task
id: 5
description: Implement zfun.rs (riemann_siegel, euler_maclaurin, z with lower-bound dispatch) and the R7 self-check function, with the bench filled in
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/zfun.rs, zeta/zeta-rs/src/complex.rs, zeta/zeta-rs/src/theta.rs, zeta/zeta-rs/src/lib.rs, zeta/zeta-rs/benches/zeta.rs]
depends_on: [3, 4]
requirements: [R6, R7]
```

- [ ] Move theta.rs's private complex-interval type to `src/complex.rs` (`pub(crate)`), shared by θ and Euler–Maclaurin; θ's behaviour and tests unchanged.
- [ ] `riemann_siegel(t, prec, &VerifyConfig)` per appendix §1 (C₀ only), widened by `multiplier × 0.127·t^(−3/4)`; refuses (returns `None`) when the t enclosure's lower bound is below 200.
- [ ] `euler_maclaurin(t, prec)` per appendix §2 (Johansson 2015 Theorem 1), returning Z(t) as an `Interval`.
- [ ] `z(t, prec, cfg)` dispatches on the lower bound of t: ≥ 200 Riemann–Siegel, otherwise Euler–Maclaurin.
- [ ] `self_check(z_source) -> Result<(), SelfCheckFailure>`: 8 points in [200, 300] at 128 bits; fails on non-intersection, Euler–Maclaurin width > 10⁻¹⁰ or < 2 × its stated remainder bound, Riemann–Siegel width > 2 × 0.127·t^(−3/4) + 10⁻¹⁰ or < 2 × 0.127·t^(−3/4), always with the unscaled constant.
- [ ] Tests, first: Z at the first zeros' neighbours has the sign Odlyzko's table implies; Z near Lehmer's pair (zeros 7005.062866175, 7005.100564674) is positive at 7005.0817 (the peak); each of the five self-check conditions fails on an injected `ZSource`; dispatch uses the lower bound (an interval straddling 200 goes to Euler–Maclaurin).
- [ ] Bench `z(t)` at t = 10⁴ and t = 10⁶.

**Interfaces:** Produces `zeta::zfun::{ZEvaluator, RealZ, ZSource, ZPaths, ZError, ZFault, SelfCheckFailure, self_check, gabcke_bound, SELF_CHECK_PREC}`. `trait ZSource { fn z(&self, t: f64, prec: u32) -> Result<Option<Interval>, ZFault>; }`: a refusal (height out of range, ambiguous N, singular C₀, precision rung not held) is `Ok(None)`; a fault (imaginary part of e^{iθ}ζ excludes 0, θ or interval error, NaN height) is `Err` and maps to exit 6 in the verifier (inside the self-check any Z-path error is exit 5). `RealZ::new(&VerifyConfig)` holds one `ZEvaluator` per rung 64/128/256/512 up to the precision cap; `ZEvaluator` tabulates ln k and 1/√k up to its max height (default 1e8). The self-check takes paths built with `VerifyConfig::default()` at `SELF_CHECK_PREC`.

### Task 6: CLI front end for PR 1

```yaml-task
id: 6
description: Implement the CLI argument and prompt handling, the N = 7 warning and the self-check exit in main.rs, ending with an explicit not-implemented exit 3
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/main.rs, zeta/zeta-rs/tests/cli.rs, zeta/zeta-rs/src/theta.rs, tests/scripts/zeta.bats]
depends_on: [5]
requirements: [R1, R3, R13, R14]
```

- [ ] Replace PR 1's interim stub (`RH NOT verified: zeta is under construction`, exit 3) and update `tests/cli.rs` to the new behaviour. Carried from PR 1 review: re-add public-API asserts that `gram_bracket(-2, 128)` and `gram_bracket(i64::MIN, 128)` return None in theta.rs's guard test. The self-check uses `ZEvaluator::new(SELF_CHECK_PREC, &VerifyConfig::default())` (the `ZPaths` implementor).
- [ ] `run<R, W, E>(cli, reader, out, err) -> io::Result<i32>` and `prompt_n` in goldbach's shape: N 2–7 else exit 1; end of input prints a newline to stdout and `Error: no input; pass SIZE as an argument (e.g. zeta 3).` to stderr, exit 1; N = 7 prints `Warning: N=7 writes about 1.5 GB (about 2.2 GB with --refine) and may take many hours.` to stderr.
- [ ] Runs `self_check(RealZ)`; on failure `self-check failed` to stderr, exit 5. Then prints `RH NOT verified up to <T>: zero isolation is not implemented yet` and exits 3.
- [ ] Tests, first: each branch above; a test that no output of any path contains `RH holds`. BATS `tests/scripts/zeta.bats`: missing/invalid/too large N exit 1, with `[[ -x "$RUST_BIN" ]] || skip`.

**Interfaces:** Produces `run(cli, reader, out, err)` (always the real self-check), `#[cfg(test)] run_with(..., self_check)`, `prompt_n`, `exit_code` (an output write or flush failure exits 4; a read error at the prompt exits 1). PR 2 ends here.

### Task 7: Block isolation and the straddle rule

```yaml-task
id: 7
description: Implement isolate.rs, returning certified (t, sign) points per Gram block with Rosser-guided subdivision, plus the straddle bisection at T
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/isolate.rs, zeta/zeta-rs/src/lib.rs]
depends_on: [6]
requirements: [R23, R25]
```

- [ ] `isolate_block(block, z_source, cfg) -> BlockPoints` with exact `f64` sample points; signs certified on [t, t]; precision steps 64→128→256→512 (capped by `cfg`); a point whose sign stays uncertain is moved to a nearby `f64` (when `cfg.move_points()`) or discarded; subdivision to `cfg.depth_cap()`; reports the block unresolved when the alternations stay short of Rosser's expected count.
- [ ] `resolve_straddle(lo, hi, T, z_source)`: at most 60 bisections; `Uncertain` when the side of T is still unknown; no bisection when T lies in g_M's bracket.
- [ ] Tests, first: Lehmer's block [g_6707, g_6709) with real Z returns points bracketing both zeros at default depth and is unresolved at depth cap 1; a fake whose sign at T stays uncertain exhausts 60 bisections; discarding points never creates an alternation (property test over random sign sequences).

**Interfaces:** Consumes `ZSource`, `VerifyConfig`, `gram_bracket`. Produces `isolate_block`, `resolve_straddle`, `BlockPoints`.

### Task 7b (id 13): Certified Gram boundaries (R22)

Added 2026-11-23 by the Task 7 spec review: no task built Z's sign over [b_n, c_n], so every block boundary would rest on an uncertified bracket.

```yaml-task
id: 13
description: Add a Z enclosure over an interval of t, certify_boundary(n) returning b_n, its certified sign and a ZeroFreeBracket that only this function can build, and record isolate.rs and boundary.rs in the crate CLAUDE.md
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/zfun.rs, zeta/zeta-rs/src/boundary.rs, zeta/zeta-rs/src/lib.rs, zeta/zeta-rs/CLAUDE.md]
depends_on: [7]
requirements: [R5, R22]
```

- [ ] `ZSource` gains an interval evaluation (Z enclosed over every t in [lo, hi], refusing as the point path does); `RealZ` implements it through the existing Riemann–Siegel and Euler–Maclaurin paths with an interval t.
- [ ] `boundary::certify_boundary(n, z, cfg) -> Result<Option<Boundary>, ZFault>`: `gram_bracket(n, prec)` certifies θ − nπ at both ends; Z's sign over [b_n, c_n] is certified through the precision ladder; `Ok(None)` when any part stays uncertain (an unusable Gram point, R22), `Err` only for a fault. `Boundary { point: (b_n, sign), bracket: ZeroFreeBracket }`; `ZeroFreeBracket` has private fields and no public constructor.
- [ ] Tests, first: g₋₁ and a mid-range n certify; a fake whose Z straddles 0 over the bracket gives `Ok(None)`; a fault propagates; the sign agrees with (−1)^n at a good Gram point and is opposite at a known bad one (g_126).
- [ ] `zeta-rs/CLAUDE.md` layout lines for `isolate.rs` and `boundary.rs`, and the 2^16-point block budget (effective depth 16 below the configured cap of 40).

**Interfaces:** Produces `boundary::{certify_boundary, Boundary, ZeroFreeBracket}` and `ZSource`'s interval method. Task 7's `resolve_straddle` then takes `Option<&ZeroFreeBracket>`.

### Task 8: Turing's method

```yaml-task
id: 8
description: Implement turing.rs with the Trudgian 2011 bound, closed-range block crediting and the candidate rules of amended R19, with known-answer tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/turing.rs, zeta/zeta-rs/src/lib.rs]
depends_on: [7, 13]
requirements: [R19]
```

- [ ] `establish(m, z_source, cfg) -> Result<TuringBound, TuringFailure>` per appendix §4: refuses b_M ≤ 168π, a bad g_M and a g_M without a certified bracket; K blocks from Trudgian eq. 2.1 evaluated at c of the last block, adding blocks until it holds; an uncertifiable Gram point in the region fails the candidate.
- [ ] Turing vector: sorted certified points over [b_M, end], every boundary point included; block j is the closed range [b_j, b_k]; an adjacent pair is credited to the block containing both points; a pair in no single block is `InternalFault` (exit 6 later).
- [ ] `choose_m(T, ...)`: smallest qualifying candidate, at most 11 tried.
- [ ] Tests, first: known-answer at a fixed g_M, one block-count pattern that just establishes and one that just fails; refusals; a sign change whose left point is the shared b_k is credited to block k only; exhausting 11 candidates fails and a 12th is never evaluated (counting fake).

**Interfaces:** Produces `turing::{establish, choose_m, TuringBound}`.

### Task 9: One-pass verification and the parallel pool

```yaml-task
id: 9
description: Implement verify.rs, the parallel isolation over Gram blocks and the one-pass count of L with every exit-3 and exit-6 outcome
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/verify.rs, zeta/zeta-rs/src/lib.rs, zeta/zeta-rs/Cargo.toml, zeta/zeta-rs/Cargo.lock]
depends_on: [8]
requirements: [R4, R10, R11, R17]
```

- [ ] `verify(T, z_source, cfg, pool_policy) -> Verdict` (`Verified{count, intervals}`, `NotVerified{reason, blocks}`, `InternalFault{reason}`): choose M, build blocks over [b₋₁, b_M], isolate on a pool built with `ThreadPoolBuilder::build` (serial fallback with `Parallel mode unavailable ({error}); falling back to serial.`; a worker panic becomes `InternalFault`), collect, sort, keep one identical (t, sign), count L.
- [ ] Rosser neighbour search (spec, Error handling; added 2026-11-23 by the Task 7 spec review): a block left unresolved is merged with its neighbouring block(s), whose expected counts add, and the union is re-isolated; points join the same collected vector. Fake test: a Rosser-failure pair (one block one change short, its neighbour one change over) verifies; a block still short after merging is `NotVerified`.
- [ ] Sign conflict at one t, NaN t, L > M + 1 → `InternalFault`; L < M + 1 → `NotVerified`.
- [ ] Add `rayon = "1"` to `Cargo.toml` and refresh `Cargo.lock`. No use of the global rayon pool.
- [ ] Tests, first: fakes for a double root, a missing sign change, an irregular pattern after g_M, an always-uncertain sign, an empty block list, an uncertifiable g₋₁ (each `NotVerified` with its reason); an extra sign change, a sign conflict, a NaN t, a panicking worker (each `InternalFault`); L counts only [b₋₁, b_M]; a duplicate (t, sign) counts once; serial and parallel give identical intervals.

**Interfaces:** Produces `verify::{verify, Verdict, PoolPolicy}`.

### Task 10: Full CLI, output file and end-to-end tests

```yaml-task
id: 10
description: Wire verify into run and run_with, write the output file through the temp file, add the N = 2 and N = 3 end-to-end tests with the Odlyzko fixture, and skip them in mutants.toml
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/main.rs, zeta/zeta-rs/tests/fixtures/odlyzko_1e3.txt, zeta/zeta-rs/.cargo/mutants.toml, tests/scripts/zeta.bats]
depends_on: [9]
requirements: [R2, R8, R9, R16, R20]
```

- [ ] Replace the PR 1 stub: map `Verdict` to stdout and exits 0/3/6, write `zeta_1eN.tmp.txt` only after `Verified`, rename on completion, exit 4 on a write failure (temp file removed), remove a stale temp file at start. Header `# n a b`; a rounded down and b rounded up at 30 significant digits.
- [ ] `run_with(config, z_source, writer, throttle, pool_policy, skip_self_check)` under `#[cfg(test)]` in `main.rs`; `run` passes the production values.
- [ ] Fixture: first 649 Odlyzko zeros with source URL and retrieval date in a header.
- [ ] Tests, first: N = 2 and N = 3 exit 0 with the verified line (29, 649), that many non-`#` lines, each fixture zero in its interval (test names start `e2e_`); exits 3–6 through `run_with`; controls: depth cap 1 with point moving off at N = 3, Gabcke × 10⁶ with self-check skipped at N = 2, each exit 3 with the reason measured first and then asserted (if one verifies, stop and report it as a blocker so the spec can be amended).
- [ ] `.cargo/mutants.toml`: skip tests named `e2e_` (cargo-mutants `additional_cargo_test_args`), with a comment citing spec V8.

**Interfaces:** Produces the complete verifying CLI. PR 3 ends here.

### Task 11: `--refine` and the spacing histogram

```yaml-task
id: 11
description: Implement spacing.rs and --refine (certified bracket bisection, t_n and w_n columns, histogram against the Wigner surmise and KS distance)
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/spacing.rs, zeta/zeta-rs/src/lib.rs, zeta/zeta-rs/src/main.rs]
depends_on: [10]
requirements: [R8, R12]
```

- [ ] Bisection on certified `f64` points; stop when the midpoint's sign stays uncertain at 512 bits after 8 nearby `f64` tries, or no `f64` lies strictly between the ends.
- [ ] Columns `# n a b t_n w_n`, t_n with 15 significant digits, w_n = b − a with 3.
- [ ] Histogram of δ_n = (t_{n+1} − t_n)·ln(t_n/2π)/2π over [0, 3] in 0.15 bins with p(s) = (32/π²) s² e^(−4s²/π); KS distance against F(s) = erf(√a·s) − (2/√π)·√a·s·e^(−a·s²), a = 4/π; the largest w_n.
- [ ] Tests, first (`e2e_` prefix for the N = 3 run): each fixture zero inside its refined bracket, w_n = b − a, every w_n below 10⁻², every refined bracket strictly narrower than the unrefined one; F(s) against a numerically integrated p(s) at 5 points.

### Task 12: Progress, docs and BATS

```yaml-task
id: 12
description: Add throttled progress output, the BATS failure-mode tests, and the zeta entries in README.md, root CLAUDE.md and zeta-rs/CLAUDE.md (including exit codes 3-6)
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C zeta/zeta-rs test
    exit_code: 0
  - cmd: make test
    exit_code: 0
  - cmd: python3 scripts/claude_md_budget.py HEAD
    exit_code: 0
max_retries: 3
files_touched: [zeta/zeta-rs/src/verify.rs, zeta/zeta-rs/src/main.rs, zeta/zeta-rs/CLAUDE.md, zeta/zeta-rs/README.md, README.md, CLAUDE.md, tests/scripts/zeta.bats]
depends_on: [11]
requirements: [R21]
```

- [ ] Progress to stderr: `progress: <done>/<total> Gram blocks, t = <t>` with t the highest boundary below which every block has finished, printed when ≥ 1% more blocks finished and ≥ 2 s since the last line, plus one final line; the throttle is a parameter (`run_with` passes 0).
- [ ] Tests, first: zero throttle gives a deterministic line count; the final line is always printed.
- [ ] Docs: README CLI and Coverage rows and badge; root `CLAUDE.md` sub-project and crate-count lines (stay under 30,000 bytes); `zeta-rs/CLAUDE.md` with layout, exit codes 0–6 as zeta's convention, and the V8 mutants note.
- [ ] BATS: binary present → `zeta 2` exits 0 and prints the verified line.

**Interfaces:** PR 4 ends here; the orchestrator then runs V3–V7.

---

## Appendix: formulas pinned in V2 (2026-11-23)

Copied from the V2 research write-up; sources and section numbers inline.
## 1. Gabcke's Riemann–Siegel remainder bound — CONFIRMED

**Source (primary, read):** W. Gabcke, *Neue Herleitung und explizite Restabschätzung der
Riemann-Siegel-Formel*, Dissertation, Göttingen 1979. Read in the 2015 re-typeset edition,
doi:10.53846/goediss-5113, hdl:11858/00-1735-0000-0022-6013-8. The eDiss server returned 403, so the
file was retrieved from the Wayback Machine:
`https://web.archive.org/web/20231207065247id_/https://ediss.uni-goettingen.de/bitstream/handle/11858/00-1735-0000-0022-6013-8/DissGab1979.pdf`.
The bound is stated in the Einleitung, p. 3, eq. (6)–(8), and proved as **Satz 3.2.2**, p. 55 (PDF
p. 63). R_K is defined in eq. (3.25)/(3.26), p. 53.

**Formula (Gabcke (3.26), Einleitung (6)):**

```
a := sqrt(t/(2π)),   N := floor(a),   z := 1 − 2(a − N)      (so z = 1 − 2p, p = frac(a))

Z(t) = 2 Σ_{n=1}^{N} cos(θ(t) − t ln n)/√n
       + (−1)^{N−1} a^{−1/2} Σ_{n=0}^{K} C_n(z) a^{−n}  +  R_K(t)

C_0(z) = F(z) = cos((π/2)(z² + 3/4)) / cos(π z)
```

- The prefactor is a^(−1/2) = (t/2π)^(−1/4), which matches the spec.
- C_0 in the spec's p-form is cos(2π(p² − p − 1/16)) / cos(2πp). It equals F(1 − 2p): numerator
  and denominator both flip sign under the substitution. max |C_0| = cos(π/8) ≈ 0.924, at p = 0 or 1
  (Gabcke p. 65, via Hiary 2016).
- The general term is C_n(z) = 2^(−2n) Σ_{k=0}^{⌊3n/4⌋} d_k^(n) π^(2n−2k)/(3n−4k)! · F^(3n−4k)(z),
  with the d_k^(n) recursion given on p. 1, eq. (3).

**Bound (Satz 3.2.2(b)): for t ≥ 200, in t itself (not t/2π):**

| K | bound on \|R_K(t)\| | K | bound on \|R_K(t)\| |
|---|---|---|---|
| 0 | 0.127 t^(−3/4) | 5 | 0.061 t^(−13/4) |
| 1 | 0.053 t^(−5/4) | 6 | 0.661 t^(−15/4) |
| 2 | 0.011 t^(−7/4) | 7 | 9.2 t^(−17/4) |
| 3 | 0.031 t^(−9/4) | 8 | 130 t^(−19/4) |
| 4 | 0.017 t^(−11/4) | 9 | 1837 t^(−21/4) |

- The general shape is |R_K(t)| < c(K)·t^(−(2K+3)/4).
- Gabcke states that the constants are optimal for K ≤ 4.
- Part (a) of the Satz gives cruder bounds for K ≤ 10 that do not use the power series of C_n:
  R_0 < 0.47, ..., R_10 < 25966 t^(−23/4).
- The inequalities are strict (<).
- R_K(t) is discontinuous at t = 2πM², where N jumps. The bound is stated for all t ≥ 200, so it
  holds pointwise on both sides of each jump.

**Corroboration:**
- G. A. Hiary, "An explicit van der Corput estimate for ζ(1/2+it)", arXiv:1507.01261v4, Lemma 2.1 and
  eq. (11): "|R_0(t)| < 0.127 t^{−3/4} for t ≥ 200", with the C_0 term written as β(2π/t)^{1/4}.
- Numeric check (`calc.py`): max |Z − (main sum + C_0 term)|·t^(3/4) over 601 points in [200, 260]
  is **0.1205**. This shows the bound is in t and nearly tight. If the bound were in t/2π, that
  maximum would be about 4× smaller.
- Do not mix in Brent 1979's bound. Brent quotes Titchmarsh's older |R_0| < (3/2)τ^(−3/4) with
  τ = t/2π, for τ > 125, and uses different normalisations.

**Consequence for V1:** the spec's floor at the Lehmer pair, 0.127·7005.06^(−3/4) = 1.66·10⁻⁴, is
correct.

**Confidence: high.**

## 2. Euler–Maclaurin for ζ(1/2 + it) — two rigorous bounds

**(a) Brent 1979 (primary, read from page images), p. 1362–1363, eq. (2.5).** This is the classical
Backlund bound, also given in Edwards §6.4. I did not read Edwards.

```
ζ(s) = Σ_{j=1}^{n−1} j^{−s} + ½ n^{−s} + n^{1−s}/(s−1) + Σ_{k=1}^{m} T_{k,n}(s) + E_{m,n}(s)

T_{k,n}(s) = B_{2k}/(2k)! · n^{1−s−2k} · Π_{j=0}^{2k−2} (s+j)

|E_{m,n}(s)| < | T_{m+1,n}(s) · (s+2m+1)/(σ+2m+1) |    for m ≥ 0, n ≥ 1, σ > −(2m+1)
```

In words: the error is the first omitted term times |s+2m+1|/(σ+2m+1).

**(b) Johansson (primary, read):** F. Johansson, "Rigorous high-precision computation of the Hurwitz
zeta function and its derivatives", *Numer. Algorithms* 69 (2015) 253–270, arXiv:1309.2877,
**Theorem 1**. This is the bound Arb/FLINT uses. Specialised to a = 1, no derivatives (x = 0),
β = 0, so C = 0, K = 1 and J_0 = 1/((B−1)A^(B−1)):

```
ζ(s) = Σ_{k=1}^{N} k^{−s} + (N+1)^{1−s}/(s−1)
       + (N+1)^{−s} [ ½ + Σ_{k=1}^{M} B_{2k}/(2k)! · (s)_{2k−1}/(N+1)^{2k−1} ] + R

|R| ≤ 4 |(s)_{2M}| / (2π)^{2M} · 1 / ((σ+2M−1)(N+1)^{σ+2M−1}),    requires N+1 > 1 and σ + 2M > 1
```

Here (s)_k = s(s+1)…(s+k−1) is the rising factorial.

**Parameter choice:** n or N+1 ≳ t + 2M keeps (|s|+2M)/(2π(N+1)) below 1/(2π).

| t | N | M | Johansson bound |
|---|---|---|---|
| 10 | 50 | 20 | 4·10⁻⁴⁸ |
| 100 | 140 | 20 | 4·10⁻³⁸ |
| 200 | 240 | 20 | 1.4·10⁻³⁵ |

Smaller N still works at lower accuracy: t = 200, N = 120, M = 20 gives 9·10⁻²⁴. Either choice
satisfies the self-check's 10⁻¹⁰ ceiling with a wide margin. Both bounds were checked numerically
against mpmath's ζ and held (actual error ≤ bound, e.g. 1.6·10⁻¹⁰ ≤ 7.5·10⁻¹⁰ at t = 199, n = 60,
m = 15).

**Confidence: high.** The formulas were read from the primary sources and checked numerically.

## 3. Stirling series for ln Γ(1/4 + it/2) and θ(t)

**Source (authoritative survey, read):** DLMF §5.11, eq. 5.11.1, and §5.11(ii) "Error Bounds",
https://dlmf.nist.gov/5.11 (original: Olver / Whittaker–Watson).

```
Ln Γ(z) = (z − ½) ln z − z + ½ ln(2π) + Σ_{k=1}^{n−1} B_{2k} / (2k(2k−1) z^{2k−1}) + R_n(z)

|R_n(z)| ≤ sec^{2n}(½ ph z) · |B_{2n}| / (2n(2n−1)|z|^{2n−1})        (complex z, |ph z| < π)
```

Ln Γ here is the principal branch: continuous, and real on the positive axis.

For z = 1/4 + it/2 with t > 0, ph z ∈ (0, π/2), so sec^{2n}(½ ph z) ≤ 2^n. Then
θ(t) = Im Ln Γ(1/4 + it/2) − (t/2) ln π. Gabcke Satz 4.2.3 uses the same principal-value
definition, with θ(0) = 0.

**Small t (spec's g₋₁ ≈ 9.667):**

| t | Best n | Bound with no shift |
|---|---|---|
| 2π | 8 | 1.35·10⁻⁷ |
| 9.667 | 12 | 6.2·10⁻¹¹ |
| 14.13 | 17 | 2.6·10⁻¹⁵ |

Shift with Ln Γ(z) = Ln Γ(z+m) − Σ_{k=0}^{m−1} Ln(z+k), using principal logs. This is exact for
Re z > 0, because every Ln(z+k) has argument in (−π/2, π/2) and both sides are analytic on the
right half-plane and agree on the real axis. With m = 10 and n = 35 the bound at t = 9.667 is
6.6·10⁻³². The shift is **not needed for soundness**, since the unshifted bound is valid. It is
**recommended**: it makes θ's error negligible against the Euler–Maclaurin path's 10⁻¹⁰ self-check
and lets 128-bit and higher precision mean something below t ≈ 20. The bound was checked
numerically against mpmath `loggamma` at t ∈ {6.3, 9.667, 20}, n ∈ {3, 6, 10}, and held in every
case.

**Alternatives, both primary and read:**
- Brent 1979 (2.3) bounds the θ series directly in t:
  θ = ½t ln(t/2π) − ½t − π/8 + Σ_{k=1}^{n} B_{2k}(1 − 2^{1−2k}) t^{1−2k} / (4k(2k−1)) + r_n(t), with
  |r_n(t)| < (2n)!/((2π)^{2n+2} t^{2n+1}) + exp(−πt), for all t > 0 and n ≥ 0. The exp(−πt) term
  floors it at 6.5·10⁻¹⁴ at g₋₁.
- Gabcke's 3-term form with |R_θ| < 1/(3322 t⁷) holds only for t ≥ 10 (see discrepancy 4).

**Confidence: high.**

## 4. Turing's method (Trudgian 2011, Lehman–Brent)

**Sources (primary, read):**
- T. Trudgian, "Improvements to Turing's method", *Math. Comp.* 80 (2011) 2259–2279. Read as
  arXiv:0903.1885v3: Theorem 2.1 and eq. (2.1), Theorem 2.2, Corollary 2.3, all on pp. 3–4.
- R. P. Brent, "On the zeros of the Riemann zeta function in the critical strip", *Math. Comp.* 33
  (1979) 1361–1372, https://maths-people.anu.edu.au/~brent/pd/rpb047.pdf (scanned, read as page
  images). §3, p. 1364: definitions, Theorems 3.1 and 3.2.

**Definitions (Brent p. 1364):**
- g_j is good iff (−1)^j Z(g_j) > 0.
- A Gram block of length k is B_j = [g_j, g_{j+k}), where g_j and g_{j+k} are good and
  g_{j+1}, …, g_{j+k−1} are all bad.
- B_j **satisfies Rosser's rule if Z has at least k zeros in B_j**. Sign changes give this lower
  bound.
- S(t) = N(t) − 1 − θ(t)/π, where N counts zeros with 0 < Im ≤ T, with multiplicity.
- Trudgian's footnote 2 gives a different, parity-based definition of a Gram block. Use Brent's.

**Trudgian Theorem 2.2:** if t₂ > t₁ > 168π, then |∫_{t₁}^{t₂} S(t) dt| ≤ 2.067 + 0.059 ln t₂.
- Note the strict inequality.
- Footnote 3 says 168π is not essential: Lemma 2.5 holds for t > 1. The theorem is stated with 168π,
  so use 168π.

**Theorem 2.1 (Lehman–Brent), for any (a, b) with |∫S| ≤ a + b ln t₂ on t₂ > t₁ > t₀:** if K
consecutive Gram blocks with union [g_n, g_p) satisfy Rosser's rule, where

```
K ≥ (b/6π) ln² g_p + ((a − b ln 2π)/6π) ln g_p        (eq. 2.1)
```

then **N(g_n) ≤ n + 1** and **N(g_p) ≥ p + 1**.
- With (a, b) = (2.067, 0.059): K ≥ 0.0031300 ln²g_p + 0.10391 ln g_p.
- Corollary 2.3 rounds this to 0.0031 ln²g_p + 0.11 ln g_p (see discrepancy 2).
- Lehman's (1.7, 0.114) gives Brent's (3.2): 0.0061 ln²g_p + 0.08 ln g_p.
- Brent's proof assumes g_n > 168π, which comes from Lehman's Theorem 4. Below 168π Brent cites the
  Haselgrove–Miller tables, which the spec avoids by requiring g_M > 168π.

**Applied to the spec:**
- n = M, and g_M must be good.
- The K blocks are the consecutive Gram blocks after g_M, each with at least as many certified sign
  changes as Gram intervals. Rosser's expected counts are never credited.
- The conclusion is the **inequality N(g_M) ≤ M + 1**. With L ≥ M + 1 sign changes in (g₋₁, g_M)
  this gives equality, as in the spec's step 7.

| g_p | exact RHS | ⇒ K |
|---|---|---|
| 168π ≈ 527.8 | 0.774 | 1 |
| 10³ | 0.867 | 1 |
| 10⁴ | 1.223 | 2 |
| 10⁵ | 1.611 | 2 |
| 10⁶ | 2.033 | 3 |
| 10⁷ | 2.488 | 3 |

**Confidence: high** for the statements. **Medium** on whether merged blocks qualify (discrepancy 3,
which needs Lehman 1970, not read).


## Non-goal check

Run 2026-11-23 by a fresh reviewer against the spec's effective N1–N7. All CLEAR; no plan revision or amendment needed.

| Non-goal | Verdict | Quote | Resolution |
|---|---|---|---|
| N1 | CLEAR | "a test that no output of any path contains `RH holds`" (Task 6); the PR 1 stub "never claims verification (R3)" | none |
| N2 | CLEAR | "`rug = { version = "1.30", features = ["integer", "float"] }`, `rayon = "1"`, `clap`" (Task 1); "`unsafe_code = "forbid"`" (Global Constraints) | none |
| N3 | CLEAR | the only flag added is `--refine` | none |
| N4 | CLEAR | Task 11 builds only a spacing histogram and a KS distance | none |
| N5 | CLEAR | the only `--check` is `render_crate_files.py --check`, a repo script | none |
| N6 | CLEAR | "write `zeta_1eN.tmp.txt` only after `Verified` … remove a stale temp file at start" (Task 10) | none |
| N7 | CLEAR | "no `#[ignore]` tests and no change to the shared crate templates or `scripts/rust-check.sh` (N7)"; Task 1 edits only the `CRATES` lists in the renderer; Task 10's `mutants.toml` skip is sanctioned by spec V8 | none |
