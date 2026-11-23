# zeta: certified verification of the Riemann Hypothesis up to height T

- **Date:** 2026-11-23
- **Sub-project:** `zeta/` (new), Rust only: crate `zeta/zeta-rs`, binary `zeta`
- **Revised:** 2026-11-23, after Multi-Lens Review rounds 1–3 (see the review section at the end)

## Summary

`zeta N` proves a finite-range theorem: every nontrivial zero ρ of the Riemann zeta
function with 0 < Im ρ ≤ T = 10^N lies on the critical line Re s = 1/2 and is simple.
It also reports how many such zeros there are. Every number the proof depends on is an
interval enclosure computed with directed rounding, so the claim holds even though the
computation is done in floating point.

This is the same kind of result as `goldbach/`: a bound in, exhaustive work, counts and
witnesses out. It is evidence for the Riemann Hypothesis, never a proof of it. The output
must never say "RH holds"; it says "RH verified up to T".

With `--refine`, the CLI also narrows each zero's interval as far as certified arithmetic
allows and shows the statistical pattern of the gaps between consecutive zeros against the
GUE prediction from random matrix theory (Montgomery–Odlyzko).

## Why this sub-project

The repo already counts primes (`prime/`), twin primes (`twin-primes/`) and Goldbach
pairs (`goldbach/`). The zeros of ζ are the other side of the same object: Riemann's
explicit formula writes the prime-counting function as a main term plus one oscillating
term per zero, and RH is the statement that every such term has the smallest possible
amplitude. Verifying zeros up to a height is the standard computational evidence for RH,
and it is done here with certified arithmetic so the printed claim is a theorem for the
range, not a numerical impression.

Prior work in this repo: none. `git grep -il -e riemann -e zeta -- docs/ '*.md'` returned
nothing on 2026-11-23, so this design was not previously proposed or rejected.

## Mathematical background

- **Hardy's Z function.** Z(t) = e^{iθ(t)} ζ(1/2 + it) is real for real t, and |Z(t)| =
  |ζ(1/2 + it)|. A sign change of Z between a and b proves an odd number of zeros of ζ,
  hence at least one, on the critical line with imaginary part in (a, b).
- **Riemann–Siegel theta.** θ(t) = Im ln Γ(1/4 + it/2) − (t/2) ln π, computed from the
  Stirling series with an explicit remainder bound. θ decreases to a minimum of about
  −3.531 near t ≈ 6.29 and increases after that.
- **Gram points.** For n ≥ −1, g_n is the unique t > 2π with θ(g_n) = nπ (unique because
  θ stays below −π on (2π, 6.29] and increases after; g₋₁ ≈ 9.667). Gram point g_n is
  _good_ when (−1)^n Z(g_n) > 0. A _Gram block_ is an interval [g_j, g_k) between
  consecutive good Gram points; it contains k − j Gram intervals.
- **Rosser's rule.** A Gram block of k − j intervals usually contains at least k − j
  zeros. It is known to fail occasionally, so it is used only as a search guide, never as a
  step in the proof.
- **Counting function.** N(T) is the number of zeros of ζ with 0 < Im ρ ≤ T, counted with
  multiplicity, in the whole critical strip whether on the line or not.
- **Turing's method.** At a good Gram point g_M, the number of sign changes located in each
  of the Gram blocks after g_M, combined with Trudgian's bound |∫_{t₁}^{t₂} S(t) dt| ≤ 2.067
  - 0.059 ln t₂, which holds for t₂ > t₁ ≥ 168π ≈ 527.8 (Trudgian 2011), proves N(g_M) ≤
    M + 1. Turing's method is therefore applied only at g_M ≥ 168π, and the exact inequality,
    including how many blocks after g_M it needs, is pinned from the source in V2.

## The proof

1. **Sample points are exact.** Every point at which Z's sign is used is an exact `f64`
   value t. Its sign is certified by evaluating Z on the degenerate interval [t, t] with
   interval arithmetic; a point whose enclosure does not exclude 0 is discarded, never used.
2. **Gram boundaries are certified points.** For each Gram point g_n used as a block
   boundary, the CLI finds two `f64` values b_n < c_n such that:
   - θ(b_n) − nπ < 0 and θ(c_n) − nπ > 0 are both certified, which proves g_n ∈ (b_n, c_n)
     because θ is increasing above 6.29; and
   - Z's sign is certified over the whole interval [b_n, c_n], which proves the interval
     holds no zero and gives g_n's sign, and so whether g_n is good.

   The point b_n, with that sign, is then inserted into every vector that counts sign changes
   across the boundary. A Gram point whose bracket cannot be certified is not a usable
   boundary; its block merges with the next one.

3. **Choose M.** M is the smallest index such that g_M ≥ max(T, 168π), g_M has a certified
   bracket, g_M is good, and Turing's method establishes N(g_M) ≤ M + 1 at that g_M. Up to 11
   candidates are tried (the first and 10 retries) before the run exits 3 with
   `Turing bound not established`. For N = 2 this means M sits just above 168π, not just above
   100; the claim is still printed only for T.
4. **Isolate.** Gram blocks covering [b₋₁, b_M] are processed in parallel. Each block
   returns its certified sample points as (t, sign) pairs, using Rosser's expected count only
   to decide where to subdivide and when to search a neighbouring block.
5. **Count L in one pass.** After every block has finished, all (t, sign) pairs in
   [b₋₁, b_M], including the boundary points b₋₁ and b_M, are collected into one vector and
   sorted by t. Pairs with identical t and identical sign are kept once. Identical t with
   different signs, or a NaN t, is an implementation fault: exit 6. L is the number of
   adjacent pairs whose signs differ. Each such pair brackets at least one zero on the line in
   a distinct open interval inside (b₋₁, b_M) ⊂ (0, g_M), so no zero is counted twice.
6. **Turing's counts in one pass.** Turing's method uses its own vector, built the same way
   from the points in [b_M, end of its last block], with every certified boundary point b_k in
   that range included. Because each boundary is a point of the vector, a sign change is a
   pair of adjacent points within one block, and it is credited to the block that contains
   both points. A pair whose points lie in different blocks is an implementation fault: exit 6.
   Rosser's expected counts are never credited.
7. **Compare.** L ≤ N(g_M) ≤ M + 1 holds for any correct implementation.
   - If L = M + 1, every zero up to g_M is on the line, and since N counts multiplicity, each
     is simple. The claim is printed for T.
   - If L < M + 1, nothing is claimed. The CLI names the Gram blocks it could not resolve and
     exits 3.
   - If L > M + 1, the implementation is wrong (the inequality cannot fail). The CLI prints
     `internal error: L > M+1` and exits 6.

## Approach: interval arithmetic on MPFR

Three approaches were considered:

- **A. Point MPFR with a hand-derived error budget.** Fastest, but soundness rests on an
  error analysis of every operation remaining correct through every future refactor.
  Rejected.
- **B. Interval arithmetic on MPFR directed rounding (chosen).** Every operation returns
  `[lo, hi]` with `lo` rounded toward −∞ and `hi` toward +∞, so the true value is always
  enclosed. MPFR's elementary functions are correctly rounded for exact inputs, which is
  what makes this sound. rug 1.30.0 exposes the needed operations (`cos_round`,
  `sin_round`, `ln_round`, `exp_round`, `sqrt_round`, `ln_gamma_round`, and
  `AddAssignRound` and its siblings). Truncation bounds (Gabcke, Euler–Maclaurin, Stirling)
  are added by widening. A sign is certified exactly when both bounds are finite and the
  interval excludes 0; any NaN or infinite bound means "not certified". Cost is about 2–4×
  point arithmetic. No new dependency, and `unsafe_code = "forbid"` holds.
- **C. Delegate to FLINT/Arb** (`acb_dirichlet_hardy_z` and Platt's zero isolation). The
  most trusted implementation, but it adds a C library to every installer, needs a `-sys`
  binding, and makes the proof Arb's rather than this crate's. Rejected.

Z(t) is evaluated two ways:

- **Riemann–Siegel** (main sum of ⌊√(t/2π)⌋ terms plus the C₀ correction, widened by
  Gabcke's remainder bound 0.127·t^(−3/4)), used only when the **lower bound** of the t
  enclosure is ≥ 200.
- **Euler–Maclaurin** summation of ζ(1/2 + it) with its rigorous remainder bound,
  used otherwise. O(t) terms, which is trivial below 200 and covers the first 79 zeros.

The same rule applies to every truncation bound: its validity condition is checked against
the worst-case end of the argument's enclosure, never its midpoint.

The two paths share `interval.rs` and `theta.rs`, so comparing them is a canary for gross
formula and build faults, not a proof of independence. An error in θ would move both
together, and at the Riemann–Siegel enclosure width near t = 200 (about 4·10⁻³) the canary
cannot see small errors.

## Components

Modules in `zeta/zeta-rs/src/`, each testable on its own:

| Module        | Responsibility                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Depends on          |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| `interval.rs` | `Interval { lo, hi }` over `rug::Float`: `+ − × ÷`, `sqrt`, `ln`, `exp`, `cos`, `sin`, `widen(ε)`, `excludes_zero()`, `sign() -> Option<Sign>`. `lo` is rounded toward −∞ and `hi` toward +∞. `excludes_zero()` is true only when both bounds are finite and `lo > 0` or `hi < 0`. For `cos`/`sin`: an argument wider than π returns [−1, 1]; otherwise, with m the midpoint and r = max(hi − m, m − lo) rounded toward +∞, f(m) is evaluated twice (rounded down and rounded up) and the result is widened by r. | `rug`               |
| `theta.rs`    | θ(t) enclosure from the Stirling series plus remainder bound; certified Gram bracket (b_n, c_n) for θ(g) = nπ, restricted to t > 2π.                                                                                                                                                                                                                                                                                                                                                                              | `interval`          |
| `zfun.rs`     | `riemann_siegel(t)`, `euler_maclaurin(t)` and `z(t)`, which dispatches on the lower bound of t.                                                                                                                                                                                                                                                                                                                                                                                                                   | `interval`, `theta` |
| `isolate.rs`  | One Gram block in, certified (t, sign) points out. Uses Rosser's expected count to decide when to subdivide (maximum depth 40) and raises precision when a sign is uncertain.                                                                                                                                                                                                                                                                                                                                     | `zfun`              |
| `turing.rs`   | Establishes N(g_M) ≤ M + 1 from its own sorted point vector and Trudgian's bound; refuses a g_M below 168π, a bad g_M, and a g_M without a certified bracket; credits a sign change only to the block holding both of its points.                                                                                                                                                                                                                                                                                 | `zfun`, `theta`     |
| `verify.rs`   | Orchestration: block list, parallel isolation, collection and sort, the one-pass count of L, comparison with M + 1, `Verdict`. Generic over a `ZSource` trait so tests can inject fakes.                                                                                                                                                                                                                                                                                                                          | all above           |
| `config.rs`   | `VerifyConfig` with private fields: Gabcke multiplier, precision cap and subdivision-depth cap. `VerifyConfig::new` rejects a multiplier that is not finite or is below 1, and caps above the defaults, so a configuration can only make certification harder.                                                                                                                                                                                                                                                    | —                   |
| `spacing.rs`  | `--refine` only: bisection of each zero's interval on certified `f64` points until no certified point fits between the ends; normalised spacings; histogram against the Wigner surmise; KS distance.                                                                                                                                                                                                                                                                                                              | `zfun`              |
| `main.rs`     | clap CLI, `run()` and `prompt_n()` in goldbach's shape, thin `main` excluded from tarpaulin. `run()` takes no configuration and always uses `VerifyConfig::default()`; a `run_with(config, skip_self_check)` exists only under `cfg(test)`.                                                                                                                                                                                                                                                                       | `verify`, `spacing` |

## Parallelism and memory

Gram blocks are independent, so isolation runs on a rayon pool built with
`ThreadPoolBuilder::build`, which returns `Err` rather than panicking when a thread cannot
be spawned. All blocks run, their point vectors are collected, and the one-pass count runs
after the last block. Nothing is evicted, so no point can arrive after a region has been
counted. If the pool cannot be built, the CLI prints `Parallel mode unavailable ({error});
falling back to serial.` (the descartes-rs wording) and processes the same blocks serially.
The output is byte-identical either way. The global pool and plain `par_iter` are not used.
A panic inside a worker is caught at the pool boundary and reported as
`internal error: worker panicked`, exit 6.

Memory is the sample-point vector: about 3 points per zero at 16 bytes each, so roughly
1 GB at N = 7 and well under 100 MB at N ≤ 6 (estimates, measured in V3).

## CLI

```
zeta [N] [--refine]
```

- `N` is 2 to 7, giving T = 10^N. Missing N prompts for it, as `goldbach` does.
- `--refine` adds a refined bracket per zero and the spacing histogram.
- N = 7 prints on stderr, before starting: `Warning: N=7 writes about 1.5 GB (about 2 GB with --refine) and may take many hours.`
- Progress goes to stderr as `progress: <done>/<total> Gram blocks, t = <t>`, where t is the
  highest boundary below which every block has finished. A line is printed when at least 1%
  more of the blocks have finished and at least 2 s have passed since the previous line, plus
  one final line, so a sub-second run prints a single line.

Approximate work (estimates, to be replaced by V3's measurements): N = 3 under 1 s, N = 5
about a minute, N = 6 tens of minutes, N = 7 many hours, all on the 48-thread `claude`.

### Output file

`zeta_1eN.txt` is written only for a verified run. Its first line is a header and each
following line is one zero with 0 < t ≤ T, in order:

```
# n a b            (default)
# n a b t_n w_n    (with --refine)
```

- `n a b` means exactly one zero lies on the line with imaginary part in (a, b); this holds
  because L = M + 1. `a` and `b` are printed with 30 significant digits, `a` rounded down
  and `b` rounded up, so the printed interval contains the certified one.
- With `--refine`, (a, b) is the narrowest certified bracket found, `t_n` is its midpoint and
  `w_n` = b − a is its width. No precision beyond w_n is claimed. Gabcke's bound and `f64`
  spacing limit w_n to roughly 10⁻³ near t = 200 and 10⁻⁵ near t = 10⁴ (measured in round 3),
  which is finer than the histogram's 0.15-wide bins need.

The output file is opened only after the verdict is verified. It is written to
`zeta_1eN.tmp.txt` in the same directory (inside the repo's `zeta_1e*.txt` gitignore pattern)
and renamed to `zeta_1eN.txt` when complete. A write failure removes the temporary file and
exits 4. Each run first removes a stale `zeta_1eN.tmp.txt` left by an interrupted run. No
output file is created on any other exit.

### Standard output and error

Verified (exit 0), on stdout:

```
Self-check: Riemann–Siegel and Euler–Maclaurin agree on [200, 300] (8 points)
Turing bound: N(g_M) <= M+1 established at g_M = <value>
Isolating zeros in 0 < t <= 1000 (<k> threads)...

RH verified: all 649 nontrivial zeros with 0 < Im s <= 1000 lie on Re s = 1/2 and are simple
Gram blocks: <b>   Rosser exceptions: <r>   max precision: <p> bits
Saved zeta_1e3.txt
Elapsed: <s> s
```

Not verified (exit 3), on stdout:

```
RH NOT verified up to 1000: 647 of 649 zeros isolated
Uncertified Gram blocks: [g_412, g_414]  (<reason>)
No claim is made for this range.
```

With `--refine`, a histogram of normalised spacings δ_n = (t_{n+1} − t_n)·ln(t_n/2π)/2π
over s ∈ [0, 3] in 0.15-wide bins, the Wigner surmise p(s) = (32/π²) s² e^(−4s²/π)
beside each bin, the KS distance, and the largest bracket width w_n. The output states that
the Wigner surmise approximates the exact GUE spacing law to within about 1%, and that
independent random points (Poisson) would instead peak at s = 0.

Warnings, progress lines and the serial-fallback message go to stderr.

### Exit codes

The Rust CLIs so far use 0, 1 and clap's 2. zeta adds 3–6 because "not verified" must be
distinguishable from an error; `zeta-rs/CLAUDE.md` documents this as zeta's own convention.

| Code | Meaning                                                                                                                |
| ---- | ---------------------------------------------------------------------------------------------------------------------- |
| 0    | Verified                                                                                                               |
| 1    | Input error, N out of range, or end of input at the prompt                                                             |
| 2    | clap usage error                                                                                                       |
| 3    | Computed, not verified (uncertified blocks, or Turing bound not established)                                           |
| 4    | Output write failed                                                                                                    |
| 5    | Runtime self-check failed                                                                                              |
| 6    | Internal error: L > M + 1, a sign conflict at one t, a NaN t, a cross-block pair in Turing's region, or a worker panic |

## Error handling

The rule throughout: anything uncertain becomes "not verified", never "verified".

- **Uncertain sign at a sample point.** Precision steps 64 → 128 → 256 → 512 bits. When the
  enclosure width is dominated by a truncation bound, more bits cannot help, so a nearby
  exact point is tried instead. A point whose sign stays uncertain is discarded. Discarding
  points can only lose sign changes, never create one.
- **Fewer sign changes than Rosser's rule expects.** The block is subdivided recursively up
  to depth 40; on a Rosser failure the neighbouring blocks are searched too. Their points
  join the same collected vector. Unresolved blocks are reported and the run exits 3.
- **A zero straddling T.** The sign-change interval containing T is bisected until the zero
  lies on one side, for at most 60 bisections. If the side is still uncertain, the run exits
  3; it never guesses.
- **A Gram bracket that cannot be certified** (θ − nπ or Z's sign uncertain at either end,
  or the search leaves t > 2π). That Gram point is not a usable boundary. If g₋₁ itself has
  no certified bracket, L has no left boundary and the run exits 3.
- **Turing's method fails.** See step 3 of the proof: up to 11 candidates, then exit 3.
- **Self-check on [200, 300].** At 8 points, both Z paths are evaluated at 128 bits. The check
  fails if any pair of enclosures does not intersect, if the Euler–Maclaurin enclosure is
  wider than 10⁻¹⁰, or if the Riemann–Siegel enclosure is wider than 2 × Gabcke's bound at
  that t plus 10⁻¹⁰. On failure: stderr `self-check failed`, exit 5, before any verdict.
- **Implementation faults** (see exit 6 in the table). Each prints an `internal error: …`
  line naming the fault and exits 6; none is reported as merely "not verified".
- **End of input at the prompt.** As goldbach: a newline on stdout, then
  `Error: no input; pass SIZE as an argument (e.g. zeta 3).` on stderr, exit 1.

## Gate before planning: the C₀ floor at N = 7

With only the C₀ correction, Gabcke's error at t = 10⁷ is about 0.127·(10⁷)^(−3/4) ≈ 7·10⁻⁷.
More precision cannot shrink it. If any consecutive zero pair below 10⁷ has max |Z| between
its zeros below that floor, no sample point certifies the pair and N = 7 can never verify.
Measured so far: Lehmer's pair near 7005.06 peaks at |Z| = 0.00397 against a floor of
1.66·10⁻⁴, a 24× margin (mpmath `siegelz`, 30 digits). Two reviewers' unmeasured estimates
for the margin near 10⁷ disagree (about 6× and about 100×), which is why this is measured
rather than argued.

Before the implementation plan is written, a pilot scan settles this (V1). Zeros below 10⁷
come from the LMFDB zeros database. The 1,000 smallest normalised gaps are taken, max |Z|
is found on a fine grid in each gap with mpmath `siegelz` at 30 digits, and the minimum ratio
to 0.127·t^(−3/4) is recorded in the plan. A minimum ratio of 10 or more keeps C₀ only. A
ratio between 1 and 10 requires an amendment adding the C₁–C₄ corrections with their
published error bound before planning. A ratio below 1 removes N = 7 from this spec.

## Testing

All tests run in `make test` and the coverage job, and all logic is reachable from them, so
the per-PR mutation gate (which runs `cargo test`) sees every line. There is no `#[ignore]`
tier. Larger runs (N = 4 and up) are verification obligations run on `claude` and recorded
in the PR (V3, V7).

Ground truth comes from outside the crate:

1. **Odlyzko's zero table.** The first 649 zeros (all zeros up to 10³) are committed as
   `zeta/zeta-rs/tests/fixtures/odlyzko_1e3.txt`, with the source URL and retrieval date in
   its header. V7 checks N = 4 against the first 10,142.
2. **Published counts.** N(10²) = 29, N(10³) = 649, N(10⁴) = 10,142, N(10⁵) = 138,069,
   N(10⁶) = 1,747,146, N(10⁷) = 21,136,125.
3. **Two Z paths compared on [200, 300]**, as a canary.

### Tests

- **Verdict end to end.** For N = 2 and N = 3, the process exits 0, stdout contains the
  `RH verified` line with 29 and 649, the file has that many non-`#` lines, and the nth Odlyzko
  zero lies in the nth interval. With `--refine` at N = 3, each Odlyzko zero lies inside its
  refined bracket and every printed w_n equals b − a.
- **Fakes that lower L** (via `ZSource`): a double root (sign touch without change), a
  missing sign change, an irregular pattern after g_M, an always-uncertain sign, an empty
  block list, and an uncertifiable g₋₁ bracket. Each yields exit 3, and each test asserts the
  specific reason or named block.
- **Fakes for implementation faults**: an extra spurious sign change yields exit 6
  (`L > M+1`); two points at one t with different signs yield exit 6; a NaN t yields exit 6;
  a worker that panics yields exit 6. Tests also assert that L is counted only over
  [b₋₁, b_M] for the M at which Turing succeeded, and that a duplicate identical (t, sign) is
  counted once.
- **Gram brackets.** A fake shifted enclosure that contains nπ in θ's range but not g_n
  fails the endpoint certificate and is unusable; b_n < g_n < c_n holds for the real θ at
  n = −1, 0, 100 and 1000; b_n is strictly increasing in n.
- **Turing.** `turing.rs` refuses g_M < 168π, a bad g_M and a g_M without a certified
  bracket. A Turing-region fake with a pair spanning two blocks yields exit 6, and a spurious
  extra sign change in the Turing region does not raise any block's credit beyond the
  certified points. `zeta 2` chooses g_M ≥ 168π. Exhausting exactly 11 candidates yields
  exit 3 and a 12th is never tried.
- **Configuration-based negative controls**, through `run_with` with the real Z paths: the
  precision cap at 64 bits with point moving off, and Gabcke's bound × 10⁶ with the self-check
  skipped. Each yields exit 3 and no `zeta_1eN.txt`; each control's reason (an uncertified
  block, or `Turing bound not established`) is measured before the plan is written and then
  asserted.
- **Configuration safety.** `VerifyConfig::new` rejects a multiplier of 0.5, NaN and
  infinity, and caps above the defaults. `VerifyConfig` cannot be built by struct literal
  outside its module. `excludes_zero()` is false for any interval with a NaN or infinite
  bound. `run()` has no configuration parameter.
- **Self-check.** Each of R7's three conditions (no intersection, Euler–Maclaurin too wide,
  Riemann–Siegel too wide), injected through `run_with`, yields exit 5.
- **Interval properties (proptest).** Inputs are sampled inside random intervals with
  magnitudes up to |x| = 10⁹. Every operation's enclosure contains the value computed at four
  times the precision with outward rounding. Enclosure width shrinks as precision grows. A
  zero-width input to `cos` and `sin` still yields an enclosure that contains the
  high-precision value.
- **Lehmer's pair, block level.** `isolate()` on the single Gram block containing t ≈ 7005.06,
  with the real Z paths, isolates both of its zeros at the default depth, and with subdivision
  depth capped at 1 through `VerifyConfig` reports that block as unresolved. One block is
  cheap, so this runs in `make test` with no full N = 4 run.
- **Straddle exhaustion.** A fake whose sign at T stays uncertain exhausts 60 bisections and
  yields exit 3.
- **Parallel versus serial.** With the pool forced to fail, `zeta_1e3.txt` is byte-identical
  to the parallel run.
- **CLI.** `run()` is tested for exits 0, 1, 3, 4, 5 and 6, end of input at the prompt, N out
  of range, the warning on stderr, the progress line (with the time throttle set to 0 under
  `cfg(test)`, so the line count is deterministic), exit 4 from a writer that fails after
  some bytes (temporary file removed), and removal of a stale `zeta_1eN.tmp.txt` at start.
  BATS failure-mode tests cover the binary per the repo DoD. `scripts/cli_contract.py` is not
  used because it is Python-only.
- **Bench.** criterion bench of `z(t)` at t = 10⁴ and t = 10⁶.

## Repo integration

- All crate files rendered from `scripts/crate_templates/` (Makefile, `rustfmt.toml`,
  `.config/nextest.toml`, `install_deps.sh`, `zeta-rs.yml`, `release-zeta-rs.yml`), with no
  template change. The crate count becomes 13 everywhere it is stated, including the literal
  `CRATES` list in `scripts/render_crate_files.py` and the hard-coded 12 in
  `tests/test_crate_uniformity.py`.
- `Cargo.toml` matches the other crates: edition 2024, `unsafe_code = "forbid"`, the API
  lints, no `rust-version`, dependencies `rug` (features `integer`, `float`), `rayon`,
  `clap`.
- New-CLI checklist: README CLI and Coverage tables and badge, CI table, root `CLAUDE.md`
  sub-project lists, `scripts/pre-commit` and `scripts/pre-push` directory lists, mutation
  workflows, `zeta/zeta-rs/CLAUDE.md`, and `.gitignore` for `zeta_1e*.txt`.

## Follow-up (not in this spec)

Rebuild π(x) from the explicit formula using `zeta N --refine` zeros, with `prime/`'s
exact counts as ground truth. Recorded as a P4 Backlog row. A `--check` mode that
re-verifies the signs at each listed interval's endpoints is also left for later.

## Requirements

- **R1.** `zeta N` accepts N from 2 to 7 inclusive, computes with T = 10^N, and exits 1 for any other N.
- **R2.** On a verified run, stdout contains the line `RH verified: all <count> nontrivial zeros with 0 < Im s <= <T> lie on Re s = 1/2 and are simple` and the process exits 0.
- **R3.** No output of the CLI, in any path, contains the phrase `RH holds` or claims verification beyond T.
- **R4.** Every sample point is an exact `f64` t whose sign is certified by interval evaluation of Z on [t, t]; L is computed after all blocks finish, by sorting all certified points in [b₋₁, b_M] (including the boundary points) by t, keeping one copy of an identical (t, sign), and counting adjacent pairs with differing signs, where M is the index at which Turing's method succeeded; identical t with different signs, or a NaN t, exits 6; the verdict is verified only when L = M + 1, L < M + 1 prints `RH NOT verified up to <T>` and exits 3, and L > M + 1 prints `internal error: L > M+1` and exits 6.
- **R5.** Every value the verdict depends on (θ, Gram points, Z, truncation bounds) is computed as an interval whose lower bound is rounded toward −∞ and upper bound toward +∞, and a sign is used only when both bounds are finite and the interval excludes 0.
- **R6.** Z(t) uses Riemann–Siegel with Gabcke's remainder bound only when the lower bound of the t enclosure is ≥ 200, and Euler–Maclaurin with its remainder bound otherwise; every truncation bound's validity condition is checked against the worst-case end of its argument's enclosure.
- **R7.** Before any verdict, the CLI evaluates both Z paths at 128 bits at 8 points in [200, 300]; it prints `self-check failed` to stderr and exits 5 if any pair of enclosures fails to intersect, if an Euler–Maclaurin enclosure is wider than 10⁻¹⁰, or if a Riemann–Siegel enclosure is wider than 2 × 0.127·t^(−3/4) + 10⁻¹⁰.
- **R8.** `zeta_1eN.txt` starts with the header line `# n a b` (or `# n a b t_n w_n` with `--refine`), followed by one line per zero with 0 < t ≤ T in increasing order, where a is rounded down and b rounded up to 30 significant digits, and with `--refine` t_n is the midpoint of the narrowest certified bracket (a, b) and w_n = b − a.
- **R9.** The output file is opened only after a verified verdict, written to `zeta_1eN.tmp.txt` and renamed to `zeta_1eN.txt` when complete; a write failure removes the temporary file and exits 4; each run first removes a stale `zeta_1eN.tmp.txt`; no output file is created on exits 1, 3, 5 or 6.
- **R10.** Zero isolation runs on a rayon pool built with `ThreadPoolBuilder::build`; if the build fails, stderr shows `Parallel mode unavailable ({error}); falling back to serial.`, and the output file is byte-identical to the parallel run; a worker panic prints `internal error: worker panicked` and exits 6.
- **R11.** The global rayon pool (`rayon::current_num_threads`, `par_iter` outside the built pool) is not used.
- **R12.** `--refine` adds a spacing histogram over s ∈ [0, 3] in 0.15-wide bins with the Wigner surmise p(s) = (32/π²) s² e^(−4s²/π) beside each bin, the KS distance and the largest w_n.
- **R13.** End of input at the N prompt prints a newline to stdout, `Error: no input; pass SIZE as an argument (e.g. zeta 3).` to stderr, and exits 1.
- **R14.** N = 7 prints `Warning: N=7 writes about 1.5 GB (about 2 GB with --refine) and may take many hours.` to stderr before computation starts.
- **R15.** The crate is Rust only (`zeta/zeta-rs`), with no Python sub-project, every templated file is rendered from `scripts/crate_templates/` without a template change, and `tests/test_crate_uniformity.py` passes for 13 crates.
- **R16.** `zeta/zeta-rs/tests/fixtures/odlyzko_1e3.txt` holds the first 649 zeros with its source URL and retrieval date in a header, and tests assert, for N = 2 and N = 3, exit 0, the `RH verified` line with counts 29 and 649, that many non-`#` lines, and each table zero inside its interval (and, with `--refine` at N = 3, inside its refined bracket).
- **R17.** `ZSource` fakes for a double root, a missing sign change, an irregular pattern after g_M, an always-uncertain sign, an empty block list and an uncertifiable g₋₁ bracket each yield exit 3 with the specific reason asserted; fakes for an extra sign change, a sign conflict at one t, a NaN t and a panicking worker each yield exit 6; tests assert that L counts only points in [b₋₁, b_M] for Turing's M and counts a duplicated identical (t, sign) once.
- **R18.** Proptest samples inputs inside random intervals with magnitudes up to |x| = 10⁹ and asserts that every `Interval` operation's enclosure contains the value computed at four times the working precision with outward rounding, including zero-width inputs to `cos` and `sin`; the `cos`/`sin` radius is max(hi − m, m − lo) rounded toward +∞.
- **R19.** M is the smallest index such that g_M ≥ max(T, 168π), g_M has a certified bracket, g_M is good, and Turing's method succeeds at g_M, trying at most 11 candidates; `turing.rs` refuses g_M < 168π, a bad g_M and a g_M without a certified bracket; Turing's vector includes every certified boundary point in its range, credits each sign change to the block containing both of its points, and exits 6 on a pair spanning two blocks.
- **R20.** Through `run_with`, the 64-bit precision cap with point moving off and Gabcke's bound × 10⁶ with the self-check skipped each yield exit 3, no `zeta_1eN.txt`, and the reason measured for that control before the plan was written.
- **R21.** Progress lines `progress: <done>/<total> Gram blocks, t = <t>` go to stderr, with t the highest boundary below which every block has finished, printed when at least 1% more blocks have finished and at least 2 s have passed since the previous line, plus one final line.
- **R22.** A Gram point is a usable boundary only when θ(b_n) − nπ < 0, θ(c_n) − nπ > 0 and Z's sign over [b_n, c_n] are all certified for `f64` values 2π < b_n < c_n; b_n is then inserted, with that sign, into every vector that counts sign changes across it.
- **R23.** The sign-change interval containing T is bisected at most 60 times; if the zero's side of T is still uncertain, the run exits 3.
- **R24.** `VerifyConfig` has private fields; `VerifyConfig::new` rejects a multiplier that is not finite or is below 1 and precision or depth caps above the defaults; `run()` takes no configuration and uses `VerifyConfig::default()`; `run_with` and the self-check skip exist only under `cfg(test)`; no environment variable or CLI flag sets the configuration.
- **R25.** A test calls `isolate()` on the Gram block containing t ≈ 7005.06 with the real Z paths; at the default depth it returns certified points bracketing both zeros of Lehmer's pair, and with subdivision depth capped at 1 it reports the block unresolved.
- **V1.** Before the implementation plan is written, run the pilot scan described above on the 1,000 smallest normalised gaps below 10⁷ (zeros from the LMFDB database) and record the minimum ratio of max |Z| to 0.127·t^(−3/4) in the plan; below 10 requires an amendment adding C₁–C₄, below 1 removes N = 7.
- **V2.** Before implementation, pin against the primary sources and record in the plan: the exact form, constant and validity range of Gabcke's bound; the Euler–Maclaurin and Stirling remainder bounds used; the Turing inequality with Trudgian's constants, validity range and number of blocks needed after g_M; the Gram index of the first Rosser-rule failure; and the location of Lehmer's pair.
- **V3.** Run N = 5, 6 and 7 on `claude`; each verified count equals the published N(10^N) (138,069; 1,747,146; 21,136,125); record wall-clock time, peak RSS, the number of uncertified blocks before retry, and the precision histogram.
- **V4.** The N = 7 run passes through the first Rosser-rule failure pinned in V2 and still exits 0.
- **V5.** Run `zeta 3 --refine` and confirm the histogram's first bin is near empty and the KS distance to the Wigner surmise is below 0.1.
- **V6.** Time `make test` under tarpaulin on `ubuntu-latest`; no single test exceeds 30 s.
- **V7.** Run `zeta 4` and `zeta 4 --refine` on `claude`; the count is 10,142, and each of the first 10,142 Odlyzko zeros lies in its interval and in its refined bracket; record times.
- **N1.** The CLI never claims RH in general; no code path prints a verification claim beyond T.
- **N2.** No new native library beyond GMP and MPFR, and no `unsafe` code in the crate.
- **N3.** No arbitrary-range mode (`--from`/`--to`) in this spec.
- **N4.** No reconstruction of π(x) from the explicit formula in this spec.
- **N5.** No `--check` re-verification mode in this spec.
- **N6.** No partial output file on any failed run.
- **N7.** No `#[ignore]` test tier, and no change to the shared crate templates or `scripts/rust-check.sh`.

## Multi-Lens Review

Round 1 reviewed at commit: `b27bae1` (Step 7 self-review commit, before Step 8 dispatch). Round 2 re-ran all lenses against the round-1 revision (`f08fe7d`); round 3 re-ran all lenses against the round-2 revision (`a83faf2`); the spec body above is the round-3 revision.

### Goal-Fit

Finding: (1) Trudgian's ∫S bound holds only for t ≥ 168π ≈ 527.8 (Trudgian 2011 abstract; Brent 2021), but step 1 picks g_M ≥ T, so N = 2 (T = 100) applies Turing outside its proven range: an unsound "verified", or an exit 3 that contradicts R16. Fix: g_M ≥ max(T, 168π). (2) `--refine` and the spacing histogram have no consumer that changes a decision; their real consumer is the π(x) follow-up, so they could move there. (3) The self-check shares `interval.rs` and `theta.rs` between both Z paths, so a θ error is invisible to it; keep it as a canary and drop "independent implementations". (4) "Proof witness" overclaims while nothing re-checks the file; a cheap `--check` would make it true. Math corrections: g_n is unique only for t > 2π (θ dips to about −3.53 near 2π), and Rosser's rule says *at least* k − j zeros, not exactly. Premise checks run: rug 1.30.0 has `cos_round`, `sin_round`, `ln_round`, `exp_round`, `sqrt_round`, `ln_gamma_round` and `*AssignRound`; `rayon_core::ThreadPoolBuilder::build` returns `Err`, not a panic, on a failed spawn; `tests/test_crate_uniformity.py` and `render_crate_files.py` hard-code 12 crates.
Assumption: C₀-only Riemann–Siegel with Gabcke's bound (about 7·10⁻⁷ at t = 10⁷) certifies every sign up to 10⁷. Refuted if some close pair below 10⁷ has max |Z| between its zeros under that floor; settled by a pre-implementation scan of the smallest gaps in [10⁶, 10⁷] or by the extreme small-|Z| values in published verifications.
Disposition: Addressed (operator, 2026-11-23: "Address all"): 168π range fixed (R19); self-check now a canary with a width ceiling (R7); g_n uniqueness and Rosser wording corrected. Accepted (operator: "Keep in this spec"): `--refine` and the spacing histogram stay. Not put to the operator: the `--check` mode was deferred as N5 by the author; flagged for Step 9.

### Ergonomics

Finding: (1) N = 6/7 runs give no progress output, discard every certified interval on a late failure, and cannot be fixed by rerunning (deterministic, no knob). (2) R14 has no stated size: about 1.5 GB at N = 7, about 2 GB with `--refine`. (3) `scripts/cli_contract.py` runs only against Python programs, so the CLI-contract test cannot apply to a Rust-only crate. (4) The serial-fallback wording is misattributed; descartes-rs prints `Parallel mode unavailable ({error}); falling back to serial.` (5) Exit codes 3, 4 and 5 are new to the Rust CLIs (siblings use 0, 1 and clap's 2) and need documenting as a convention. (6) Full N = 4, and N = 4 with `--refine`, under tarpaulin may exceed nextest's 45 s per-test bound; the test plan needs a fast tier. (7) The output file has no column header.
Assumption: full N = 4 verification, and N = 4 `--refine`, fit inside 45 s per test in debug and the 30-minute tarpaulin job on `ubuntu-latest`; settled by timing those tests once `verify.rs` exists.
Disposition: Addressed (operator, 2026-11-23: "Address all"): progress line (R21), `zeta_1eN.partial.txt` on exit 3 (R9), stated sizes (R14), fast and release test tiers, header line (R8), exit codes documented as a zeta convention, `cli_contract.py` requirement replaced, descartes wording corrected (R10). Assumption carried as V6.

### Risk

Finding: Same Trudgian 168π range defect at N = 2 as Goal-Fit (1), with the same fix plus a V1 range item and a unit test that `turing.rs` refuses g_M < 168π. Measured: Lehmer's pair near 7005.06 has max |Z| = 0.00397 between its zeros against a Gabcke floor of 1.66·10⁻⁴ (24× margin, mpmath `siegelz` at 30 digits). Test verdicts: 6 expect verified, 5 expect not verified; the negative controls assert only "not verified", not the reason, and no fake covers L > M + 1. Checked sound: the simplicity argument, block-boundary counting, ln arguments, precision at 10⁷, the temp-file rename.
Assumption: Gabcke's C₀ floor is below the peak |Z| of every consecutive zero pair up to 10⁷ (same as Goal-Fit's); settled by `mpmath.siegelz` over the 50 smallest gaps from Odlyzko's zeros below 10⁷.
Disposition: Addressed (operator, 2026-11-23: "Address all" and "Pilot scan first"): Turing range fixed (R19); negative controls assert reasons and a raising-L fake exists (R17); the C₀-floor assumption is now the pre-plan gate V1.

### Adversarial Spec Review (comparison/judge designs only)

The verifier is an evaluator, so the gate ran. Findings:
- A1 (load-bearing): neighbour searches at Rosser exceptions can count one sign change twice as overlapping intervals, which can mask a missing zero and give L = M + 1. "Disjoint" is undefined in R4; L > M + 1 has no handling.
- A2: Trudgian 168π range at N = 2 (same as above).
- A3: "f(mid) ± width" for cos/sin is not an enclosure for a zero-width input unless f(mid) is rounded down for lo and up for hi; widen by an extra ulp.
- A4: dispatch "t ≥ 200" on an interval argument must use the lower bound; every truncation bound's validity check must use the worst-case end.
- A5: Turing may succeed at a later g_{M'} than the index L is counted to; R4 must tie them, and sign changes Turing uses beyond g_M must not count in L.
- A6: R7's "enclosures intersect" passes with a uselessly wide enclosure; it needs a width ceiling.
- A7: straddling T needs a stopping rule mapping to uncertified; printed endpoints must round outward.
- A8: the simplicity claim needs N counted with multiplicity, stated.
- B1: no real (non-fake) input is shown to produce "not verified".
- B2: every fake lowers L; none raises it (duplicate interval, extra sign change, Turing at a different index).
- B3: the Odlyzko containment test does not test the verdict logic, and R16 does not require exit 0 with the verified line.
- B4: nobody measures how often blocks are uncertified; no fallback beyond C₀ is defined for N = 7.
- B5: no test of Newton converging to the wrong root of θ(g) = −π.
Most important change: define L structurally as the number of certified sign alternations along one globally merged, strictly increasing sequence of certified sample points over (g₋₁, g_M]; neighbour searches add points, never intervals; L > M + 1 is an internal error with its own exit code.
Disposition: Addressed (operator, 2026-11-23: "Address all"): L defined on one merged sample sequence with exit 6 for L > M+1 (R4); directed-rounding cos/sin (Components, R18); lower-bound dispatch (R6); one index for Turing and L (R4); self-check width ceiling (R7); straddle stopping rule (R23) and outward-rounded endpoints (R8); multiplicity stated; real-input controls (R20); raising-L fakes (R17); verdict asserted end to end (R16); Newton root guard (R22); uncertified-block counts recorded (V3); C₀ fallback gated by V1.

### Round 2 (reviewed at `f08fe7d`, the round-1 revision)

Every serious round-2 finding sat in text the round-1 revision added.

**Goal-Fit.** Finding: the round-1 self-check width ceiling (10⁻¹⁰ for both paths) can never pass, since the Riemann–Siegel enclosure carries Gabcke's 0.127·t^(−3/4) (2.4·10⁻³ at t = 200, measured), so every run would exit 5; the release-tier premise is false, since `cargo nextest run --release --run-ignored only` exits 4 on a crate with no ignored tests (measured in a scratch crate; the 12 existing crates have none); the partial file has no reader and its `n a b` lines overclaim. Simpler path named: cap at N = 6. Assumption: the C₀ floor margin up to 10⁷ (V1). Disposition: Addressed (operator, 2026-11-23: "Address all"): self-check ceiling applies to Euler–Maclaurin only, Riemann–Siegel bounded by 2 × Gabcke + 10⁻¹⁰ (R7); `make test-release` with `--no-tests=pass` (R25). Partial file deleted (operator: "Delete it"; N6). Accepted (operator: "Keep, gated by pilot"): N = 7 stays, gated by V1.

**Ergonomics.** Finding: the release-tier exit-4 defect (independently measured); the unnamed temp file is not gitignored and survives an interrupt; a stale partial file can outlive a later run; R20 controls pass on an empty computation; the header line breaks `wc -l` counts; the warning stream is unstated. Assumption: N = 3 end to end fits the fast tier under tarpaulin (V6). Disposition: Addressed (operator: "Address all"): temp file `zeta_1eN.tmp.txt` inside the gitignore glob with stale removal (R9); partial file gone (N6); R20 asserts reasons; counts are of non-`#` lines (R16); warnings and progress on stderr (R14, R21).

**Risk.** Finding: the self-check exit-5 defect (mpmath probe, widths ≥ 3.5·10⁻³ at all 8 points); the cos/sin "one ulp" is ambiguous and, read as the result's ulp, under-encloses by about 10⁸ ulps near 10⁷, a false-verified path; the test-only knobs can reach production and a multiplier below 1 would be unsound; the partial file's `n a b` overclaims. Checked sound: L from g₋₁ against N from 0, straddle rule, Turing preconditions, exit 6. Assumption: the C₀ floor margin up to 10⁷ (V1). Disposition: Addressed (operator: "Address all" and "One-pass on f64 points"): radius r = max(hi − m, m − lo) rounded up and proptest to |x| = 10⁹ (R18); `VerifyConfig` widen-only by construction, no env or CLI path (R24); partial file deleted.

**Adversarial.** Findings: F1 the always-exit-5 self-check; F2 (unsound) chunk eviction against one global sequence lets a late neighbour-search point append two false alternations; F3 (unsound) Turing's counts lacked the single-sequence discipline; F4 R19 contradicted step 1 (no good-point or success condition); F5 R4 did not tie a point's sign to its whole t enclosure; F6 the partial file overclaims; F7 chunk edges, unbuildable fakes, weak R20, and untested R22/R23 paths. Most important change: count L and Turing's per-block counts in one ordered pass. Disposition: Addressed (operator: "One-pass on f64 points" and "Address all"): exact `f64` sample points with interval-certified signs, all blocks collected then counted in one pass, no eviction (R4); Turing's own sorted vector credited by position (R19); Gram boundaries certified over the whole enclosure (proof step 2); R19 rewritten with refusal tests; fakes rebuilt around the one-pass count (R17); straddle exhaustion and Newton failure tested; partial file deleted (N6).

### Round 3 (reviewed at `a83faf2`, the round-2 revision)

**Goal-Fit.** Finding: `--refine`'s |t_n − γ_n| < 10⁻¹² cannot be met: bisection stops where Gabcke's bound swamps Z (about 7·10⁻⁴ at t ≈ 200, 1.1·10⁻⁵ at t ≈ 10⁴, mpmath measured) and `f64` spacing exceeds 10⁻¹² above about 8192, so the release-tier `--refine` test could not pass; b_n rounded below the Gram enclosure leaves an uncertified sliver; `--no-tests=pass` would let zeta pass with no ignored tests; `scripts/rust-check.sh` has no mode for a release tier; a self-check skip on `VerifyConfig` contradicts R24. Assumption: C₀ margin near 10⁷ (estimated about 6×, unmeasured). Disposition: Addressed (operator, 2026-11-23: "Certified bracket", "Drop it", "Apply it"): `--refine` reports the narrowest certified bracket and its width (R8, R12); release tier dropped (N7); certified boundary points (R22); skip only under `cfg(test)` (R24).

**Ergonomics.** Finding: `rust-check.sh` accepts only `lint|test`, so the release step would exit 2 in all 13 crates, and changing it needs `test_rust_check.py` plus the crate matrix; the release tier adds about 30% to a 10.85 GB Actions cache, overwrites JUnit in 12 crates, and is invisible to cargo-mutants (which runs `cargo test`); temp-file removal tests on exits 3, 5 and 6 are vacuous because the file never exists there; progress every 1% is noisy at small N and its t is undefined under parallel completion. Assumption: release-tier N = 4 `--refine` within 45 s on 2 vCPUs. Disposition: Addressed (operator: "Drop it" and "Address all"): no `#[ignore]` tier, no template or wrapper change (N7), N = 4 as V7; file opened only after a verified verdict and exit-4 tested with a failing writer (R9); throttled progress with t defined (R21).

**Risk.** Finding: proof step 2's "same count" claim was false as written: [b_n, enclosure) was uncertified, safe for L but able to over-credit Turing; b_M was not required to be a sample point, so the last zero could fall between L's and Turing's vectors; de-duplication on identical t hid a sign conflict. Checked sound: the good test over an enclosure, enclosure ordering, b₋₁, f64 resolution (two zeros with no `f64` between them fail closed), the self-check RS bound, widen-only caps. Assumption: none it judged genuinely uncertain; V1 estimated at about 100–160× (unmeasured). Disposition: Addressed (operator: "Apply it"): certified bracket (b_n, c_n) with b_n inserted into both vectors (R22, R4, R19); sign conflict or NaN t exits 6 (R4).

**Adversarial.** Findings: F1 (unsound) "credit by position" was ambiguous for a pair straddling a boundary in Turing's region, so a later block's zero could be credited early and hide an off-line pair; F2 the uncertified b_n sliver; F3 "θ(g_n) encloses nπ" did not prove g_n lies in the enclosure, and a shifted enclosure could cover two zeros; F4 `VerifyConfig` could be built by struct literal or with a NaN multiplier, `excludes_zero()` might pass NaN, and the self-check skip had no confinement; F5 a sign conflict at one t, and a NaN t, were unhandled; F6 R20's controls likely produce a different reason than asserted; F7 `--no-tests=pass` masked a missing tier; F8 the 10⁻¹² `--refine` claim. Most important change: certify every Gram boundary as an `f64` bracket by endpoint signs, insert it into both vectors, and credit a sign change only to a block holding both of its points. Disposition: Addressed (operator: "Apply it", "Drop it", "Certified bracket", "Scoped round 4"): R22 bracket certificate and shifted-enclosure test; R19 crediting with exit 6 on a cross-block pair; R24 private fields, finite ≥ 1 multiplier, NaN-safe `excludes_zero()`, `run_with` only under `cfg(test)`; exit 6 for sign conflict, NaN t and worker panic (R4, R10, R17); R20 reasons measured before planning; release tier dropped (N7); Lehmer control moved to a block-level test (R25).
