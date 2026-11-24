# zeta: certified verification of the Riemann Hypothesis up to height T

- **Date:** 2026-11-23
- **Sub-project:** `zeta/` (new), Rust only: crate `zeta/zeta-rs`, binary `zeta`
- **Revised:** 2026-11-23, after Multi-Lens Review rounds 1–4 and External Review round 1 (see the review sections at the end)

- **Approved:** 2026-11-23
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
  of the Gram blocks after g_M, combined with Trudgian's bound that |∫_{t₁}^{t₂} S(t) dt| is at most 2.067 plus
  0.059·ln t₂, which holds for t₂ > t₁ ≥ 168π ≈ 527.8 (Trudgian 2011), proves N(g_M) ≤
    M + 1. Turing's method is therefore applied only at g_M ≥ 168π, and the exact inequality,
    including how many blocks after g_M it needs, is pinned from the source in V2.

## The proof

1. **Sample points are exact.** Every point at which Z's sign is used is an exact `f64`
   value t. Its sign is certified by evaluating Z on the degenerate interval [t, t] with
   interval arithmetic; a point whose enclosure does not exclude 0 is discarded, never used.
2. **Gram boundaries are certified points.** For each Gram point g_n used as a block
   boundary, the CLI finds two `f64` values b_n < c_n such that:
   - θ(b_n) − nπ < 0 and θ(c_n) − nπ > 0 are both certified, which proves g_n ∈ (b_n, c_n)
     because θ is continuous and g_n is the only t > 2π with θ(t) = nπ; and
   - Z's sign is certified over the whole interval [b_n, c_n], which proves the interval
     holds no zero and gives g_n's sign, and so whether g_n is good.

   The point b_n, with that sign, is then inserted into every vector that counts sign changes
   across the boundary. A Gram point whose bracket cannot be certified is not a usable
   boundary; below b_M its block merges with the next one, and in Turing's region it fails the
   current g_M candidate (amended 2026-11-23, see Amendments).

3. **Choose M.** (Amended 2026-11-23, see Amendments: b_M > 168π strictly, and Turing's
   block count and merge rule as in amended R19.) M is the smallest index such that
   g_M ≥ max(T, 168π), g_M has a certified
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
   that range included. Turing block j is the closed range [b_j, b_k] of points, and each
   boundary point b_k belongs to both neighbouring blocks. A sign change is a pair of adjacent
   points, and it is credited to block j exactly when both points lie in [b_j, b_k]. Because
   every boundary is a point of the vector, every adjacent pair lies in exactly one block; a
   pair that does not is an implementation fault: exit 6. Rosser's expected counts are never
   credited. Every Gram-dependent quantity in Turing's inequality uses the worst-case end of
   its bracket: the 168π test uses b_M, and the inequality's upper height uses c of its last
   block.
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
| `config.rs` | `VerifyConfig` with private fields: Gabcke multiplier, precision cap, subdivision-depth cap and whether uncertain points may be moved. `VerifyConfig::new` rejects a multiplier that is not finite or is below 1, a precision cap below 64 or above the default, and a depth cap above the default; turning point moving off is allowed. Every setting can only make certification harder, and `VerifyConfig::default()` passes `new`'s own validation. | — |
| `spacing.rs` | `--refine` only: bisection of each zero's interval on certified `f64` points; it stops when the midpoint's sign stays uncertain at 512 bits after 8 nearby `f64` tries, or when no `f64` lies strictly between the ends. Then normalised spacings, histogram against the Wigner surmise, KS distance. | `zfun` |
| `main.rs` | clap CLI, `run()` and `prompt_n()` in goldbach's shape, thin `main` excluded from tarpaulin. `run()` takes no configuration and always uses `VerifyConfig::default()`, the real Z, the real output writer, the 2 s progress throttle and the real pool. The library's entry points take the `ZSource`, configuration, writer, throttle and pool policy as explicit parameters; `run()` passes the production values. `run_with(config, z_source, writer, throttle, pool_policy, skip_self_check)` lives in `main.rs` under `cfg(test)`, so `main.rs`'s unit tests reach the exit-code mapping. | `verify`, `spacing` |

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
- N = 7 prints on stderr, before starting: `Warning: N=7 writes about 1.5 GB (about 2.2 GB with --refine) and may take many hours.`
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
- With `--refine`, (a, b) is the narrowest certified bracket found, `t_n` is its midpoint
  (15 significant digits) and `w_n` = b − a is its width (3 significant digits). At about
  104 bytes per line the N = 7 file is about 2.2 GB. No precision beyond w_n is claimed. Gabcke's bound and `f64`
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
  3; it never guesses. If T lies in g_M's bracket [b_M, c_M], which is certified zero-free,
  no interval straddles T and nothing is bisected.
- **A Gram bracket that cannot be certified** (θ − nπ or Z's sign uncertain at either end,
  or the search leaves t > 2π). That Gram point is not a usable boundary. If g₋₁ itself has
  no certified bracket, L has no left boundary and the run exits 3.
- **Turing's method fails.** See step 3 of the proof: up to 11 candidates, then exit 3.
- **Self-check on [200, 300].** At 8 points, both Z paths are evaluated at 128 bits. The check
  fails if any pair of enclosures does not intersect, if the Euler–Maclaurin enclosure is
  wider than 10⁻¹⁰ or narrower than twice its own stated remainder bound, or if the
  Riemann–Siegel enclosure is wider than 2 × Gabcke's bound at that t plus 10⁻¹⁰ or narrower
  than 2 × Gabcke's bound. The self-check always uses the unscaled constant 0.127, whatever
  `VerifyConfig`'s multiplier is. The floors catch an implementation that drops a truncation
  bound.
  On failure: stderr `self-check failed`, exit 5, before any verdict.
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
the per-PR mutation gate (which runs `cargo test`) sees every line. `mutation-rs` is one
60-minute job, and cargo-mutants times out a mutant's whole test run at max(30 s, 5 × the baseline test time);
V8 measures this before planning. If the projected time exceeds 50 minutes, zeta's
`.cargo/mutants.toml` skips the end-to-end tests by name (crate-local configuration, not a
template change), and every line those tests alone reach gets a unit test through a fake or
the single-block real-Z test. There is no `#[ignore]`
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
  refined bracket, every printed w_n equals b − a, every w_n is below 10⁻², and every refined
  bracket is strictly narrower than the zero's unrefined interval.
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
  fails the endpoint certificate and is unusable. For n = −1, 0, 100 and 1000, b_n < g_n < c_n
  holds where g_n comes from a committed fixture `tests/fixtures/gram_points.txt` computed with
  mpmath at 30 digits (source and command in its header), not from the crate's own θ. b_n is
  strictly increasing in n. A fake whose Z sign over [b_n, c_n] is uncertain makes that Gram
  point unusable and its block merges with the next, both below g_M (L still correct) and in
  Turing's region, where it fails the current g_M candidate rather than merging (amended
  2026-11-23).
- **Turing.** `turing.rs` refuses g_M < 168π (tested against b_M), a bad g_M and a g_M
  without a certified bracket. A sign change whose left point is a shared boundary b_k is
  credited to block k only. Known-answer tests, built from the inequality pinned in V2: at a
  fixed g_M, one block-count pattern that just establishes N(g_M) ≤ M + 1 and one that just
  fails to. `zeta 2` chooses g_M ≥ 168π. Exhausting exactly 11 candidates yields exit 3 and a
  12th is never tried.
- **Configuration-based negative controls**, through `run_with` with the real Z paths: at
  N = 3, subdivision depth capped at 1 with point moving off; at N = 2, Gabcke's bound × 10⁶
  with the self-check skipped (this binds through Turing, since g_M ≥ 168π uses
  Riemann–Siegel). Each yields exit 3 and no `zeta_1eN.txt`, and each control's reason (an
  uncertified block, or `Turing bound not established`) is measured before the plan is
  written and then asserted. A precision cap is not used as a control: below 10³ the
  truncation bound exceeds 64-bit rounding error by about 10¹², so the cap changes no sign.
  If a measured control verifies instead of exiting 3, it is replaced by one that binds
  before the plan is written, recorded as an amendment.
- **Configuration safety.** `VerifyConfig::new` rejects a multiplier of 0.5, NaN and
  infinity, a precision cap of 0, 1 and 63, and caps above the defaults;
  `VerifyConfig::default()` passes `new`'s validation. `VerifyConfig` cannot be built by struct literal
  outside its module. `excludes_zero()` is false for any interval with a NaN or infinite
  bound. `run()` has no configuration parameter.
- **Self-check.** Each of R7's five conditions (no intersection, Euler–Maclaurin too wide or
  too narrow, Riemann–Siegel too wide or too narrow), injected through a `ZSource` passed to
  `run_with`, yields exit 5.
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
- **CLI.** `run()` is tested for exit 0, exit 1, end of input at the prompt, N out of range
  and the N = 7 warning on stderr. `run_with` is tested for exits 3, 4, 5 and 6 (each through
  a `ZSource` fake or injected self-check result), the progress line with a zero throttle so
  the line count is deterministic, exit 4 from a writer that fails after some bytes (temporary
  file removed), and removal of a stale `zeta_1eN.tmp.txt` at start.
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
- **R7.** Before any verdict, the CLI evaluates both Z paths at 128 bits at 8 points in [200, 300]; it prints `self-check failed` to stderr and exits 5 if any pair of enclosures fails to intersect, if an Euler–Maclaurin enclosure is wider than 10⁻¹⁰ or narrower than twice its stated remainder bound, or if a Riemann–Siegel enclosure is wider than 2 × 0.127·t^(−3/4) + 10⁻¹⁰ or narrower than 2 × 0.127·t^(−3/4).
- **R8.** `zeta_1eN.txt` starts with the header line `# n a b` (or `# n a b t_n w_n` with `--refine`), followed by one line per zero with 0 < t ≤ T in increasing order, where a is rounded down and b rounded up to 30 significant digits, and with `--refine` t_n is the midpoint of the certified bracket (a, b) after bisection stops (midpoint sign uncertain at 512 bits after 8 nearby `f64` tries, or no `f64` strictly between the ends), printed with 15 significant digits, and w_n = b − a, printed with 3 significant digits.
- **R9.** The output file is opened only after a verified verdict, written to `zeta_1eN.tmp.txt` and renamed to `zeta_1eN.txt` when complete; a write failure removes the temporary file and exits 4; each run first removes a stale `zeta_1eN.tmp.txt`; no output file is created on exits 1, 3, 5 or 6.
- **R10.** Zero isolation runs on a rayon pool built with `ThreadPoolBuilder::build`; if the build fails, stderr shows `Parallel mode unavailable ({error}); falling back to serial.`, and the output file is byte-identical to the parallel run; a worker panic prints `internal error: worker panicked` and exits 6.
- **R11.** The global rayon pool (`rayon::current_num_threads`, `par_iter` outside the built pool) is not used.
- **R12.** `--refine` adds a spacing histogram over s ∈ [0, 3] in 0.15-wide bins with the Wigner surmise p(s) = (32/π²) s² e^(−4s²/π) beside each bin, the largest w_n, and the KS distance between the observed spacings and the surmise's CDF F(s) = erf(√a·s) − (2/√π)·√a·s·e^(−a·s²) with a = 4/π.
- **R13.** End of input at the N prompt prints a newline to stdout, `Error: no input; pass SIZE as an argument (e.g. zeta 3).` to stderr, and exits 1.
- **R14.** N = 7 prints `Warning: N=7 writes about 1.5 GB (about 2.2 GB with --refine) and may take many hours.` to stderr before computation starts.
- **R15.** The crate is Rust only (`zeta/zeta-rs`), with no Python sub-project, every templated file is rendered from `scripts/crate_templates/` without a template change, and `tests/test_crate_uniformity.py` passes for 13 crates.
- **R16.** `zeta/zeta-rs/tests/fixtures/odlyzko_1e3.txt` holds the first 649 zeros with its source URL and retrieval date in a header, and tests assert, for N = 2 and N = 3, exit 0, the `RH verified` line with counts 29 and 649, that many non-`#` lines, and each table zero inside its interval (and, with `--refine` at N = 3, inside its refined bracket, with every w_n below 10⁻² and every refined bracket strictly narrower than the unrefined interval).
- **R17.** `ZSource` fakes for a double root, a missing sign change, an irregular pattern after g_M, an always-uncertain sign, an empty block list and an uncertifiable g₋₁ bracket each yield exit 3 with the specific reason asserted; fakes for an extra sign change, a sign conflict at one t, a NaN t and a panicking worker each yield exit 6; tests assert that L counts only points in [b₋₁, b_M] for Turing's M and counts a duplicated identical (t, sign) once.
- **R18.** Proptest samples inputs inside random intervals with magnitudes up to |x| = 10⁹ and asserts that every `Interval` operation's enclosure contains the value computed at four times the working precision with outward rounding, including zero-width inputs to `cos` and `sin`; the `cos`/`sin` radius is max(hi − m, m − lo) rounded toward +∞.
- **R19.** M is the smallest index such that g_M ≥ max(T, 168π), g_M has a certified bracket, g_M is good, and Turing's method succeeds at g_M, trying at most 11 candidates; `turing.rs` refuses g_M < 168π, a bad g_M and a g_M without a certified bracket; Turing's vector includes every certified boundary point in its range; Turing block j is the closed range [b_j, b_k] with each b_k shared by both neighbours; a sign change is credited to block j exactly when both of its points lie in [b_j, b_k], and an adjacent pair lying in no single block exits 6; the 168π test uses b_M and the inequality's upper height uses c of the last block; known-answer tests at a fixed g_M cover one just-establishing and one just-failing block-count pattern.
- **R20.** Through `run_with`, subdivision depth capped at 1 with point moving off at N = 3, and Gabcke's bound × 10⁶ with the self-check skipped at N = 2, each yield exit 3, no `zeta_1eN.txt`, and the reason measured for that control before the plan was written; a control measured to verify is replaced by a binding one before planning.
- **R21.** Progress lines `progress: <done>/<total> Gram blocks, t = <t>` go to stderr, with t the highest boundary below which every block has finished, printed when at least 1% more blocks have finished and at least 2 s have passed since the previous line, plus one final line.
- **R22.** A Gram point is a usable boundary only when θ(b_n) − nπ < 0, θ(c_n) − nπ > 0 and Z's sign over [b_n, c_n] are all certified for `f64` values 2π < b_n < c_n; b_n is then inserted, with that sign, into every vector that counts sign changes across it.
- **R23.** The sign-change interval containing T is bisected at most 60 times; if the zero's side of T is still uncertain, the run exits 3.
- **R24.** `VerifyConfig` has private fields (Gabcke multiplier, precision cap, depth cap, point moving); `VerifyConfig::new` rejects a multiplier that is not finite or is below 1, a precision cap below 64 or above the default, and a depth cap above the default; `VerifyConfig::default()` passes that validation; `run()` takes no configuration and uses the defaults with the real Z, writer, throttle and pool; `run_with` and the self-check skip exist only in `main.rs` under `cfg(test)`; no environment variable or CLI flag sets the configuration.
- **R25.** A test calls `isolate()` on the Gram block containing t ≈ 7005.06 with the real Z paths; at the default depth it returns certified points bracketing both zeros of Lehmer's pair, and with subdivision depth capped at 1 it reports the block unresolved.
- **V1.** Before the implementation plan is written, run the pilot scan described above on the 1,000 smallest normalised gaps below 10⁷ (zeros from the LMFDB database) and record the minimum ratio of max |Z| to 0.127·t^(−3/4) in the plan; below 10 requires an amendment adding C₁–C₄, below 1 removes N = 7.
- **V2.** Before implementation, pin against the primary sources and record in the plan: the exact form, constant and validity range of Gabcke's bound; the Euler–Maclaurin and Stirling remainder bounds used; the Turing inequality with Trudgian's constants, validity range and number of blocks needed after g_M; the Gram index of the first Rosser-rule failure; and the location of Lehmer's pair.
- **V3.** Run N = 5, 6 and 7 on `claude`; each verified count equals the published N(10^N) (138,069; 1,747,146; 21,136,125); record wall-clock time, peak RSS, the number of uncertified blocks before retry, and the precision histogram.
- **V4.** The N = 7 run passes through the first Rosser-rule failure pinned in V2 and still exits 0.
- **V5.** Run `zeta 3 --refine` and confirm the histogram's first bin is near empty and the KS distance to the R12 CDF is below 0.1 (round-1 external review measured 0.045 on the first 649 zeros); a failure blocks merging until the spacing code or the CDF is corrected.
- **V6.** Time `make test` under tarpaulin on `ubuntu-latest`; no single test exceeds 30 s.
- **V7.** Run `zeta 4` and `zeta 4 --refine` on `claude`; the count is 10,142, and each of the first 10,142 Odlyzko zeros lies in its interval and in its refined bracket; record times.
- **V8.** Before the implementation plan is written, build a prototype with the Riemann–Siegel and Euler–Maclaurin loops on 64-bit `rug` intervals, time its debug `cargo test` baseline B for the planned N = 2 and N = 3 tests, estimate zeta's mutant count from the per-line rate of goldbach, pi and descartes, and project the first PR's `mutation-rs` time as (timed-out mutants × max(30 s, 5·B)) + (other mutants × B), because cargo-mutants 27.1.0 times out a mutant's whole test run at that limit; above 50 minutes, the end-to-end tests are skipped in zeta's `.cargo/mutants.toml` and their lines covered by unit tests.
- **N1.** The CLI never claims RH in general; no code path prints a verification claim beyond T.
- **N2.** No new native library beyond GMP and MPFR, and no `unsafe` code in the crate.
- **N3.** No arbitrary-range mode (`--from`/`--to`) in this spec.
- **N4.** No reconstruction of π(x) from the explicit formula in this spec.
- **N5.** No `--check` re-verification mode in this spec.
- **N6.** No partial output file on any failed run.
- **N7.** No `#[ignore]` test tier, and no change to the shared crate templates or `scripts/rust-check.sh`.

## Amendments

- R19 -> M is the smallest index such that b_M > 168π, g_M ≥ T, g_M has a certified bracket, g_M is good, and Turing's method succeeds at g_M, trying at most 11 candidates; Turing's region is K consecutive Gram blocks after g_M, each with at least as many located sign changes as Gram intervals, where K satisfies Trudgian 2011 Theorem 2.1 (eq. 2.1, a = 2.067, b = 0.059) evaluated at c of the last block, adding blocks until it holds; a Gram point in Turing's region without a certified bracket fails that candidate rather than merging blocks; `turing.rs` refuses b_M ≤ 168π, a bad g_M and a g_M without a certified bracket; Turing's vector includes every certified boundary point in its range; Turing block j is the closed range [b_j, b_k] with each b_k shared by both neighbours; a sign change is credited to block j exactly when both of its points lie in [b_j, b_k], and an adjacent pair lying in no single block exits 6; known-answer tests at a fixed g_M cover one just-establishing and one just-failing block-count pattern. — V2 pinned Trudgian 2011 Theorems 2.1 and 2.2, which need t₁ > 168π strictly, and Brent 1979's Gram block definition, under which a block merged across an unverified Gram point is outside the theorem.
- R22 -> A Gram point is a usable boundary only when θ(b_n) − nπ < 0, θ(c_n) − nπ > 0 and Z's sign over [b_n, c_n] are all certified for `f64` values 2π < b_n < c_n; b_n is then inserted, with that sign, into every vector that counts sign changes across it; below b_M an unusable Gram point merges its block with the next, and in Turing's region it fails the current g_M candidate. — V2: merging is sound for L but outside Brent's Gram-block hypotheses for Turing's count.
- V1 reviewed: measured 2026-11-23 over all 21,136,123 consecutive zero pairs below 10⁷ (f64 C Riemann–Siegel with C₀–C₂ scan, every candidate confirmed with mpmath `siegelz` at 30 digits; decade counts 29, 649, 10,142, 138,069, 1,747,146 and 21,136,125 reproduced; the first Rosser failure at g_13999525 and Lehmer's pair reproduced): minimum ratio 12.05 at the pair 4316832.467101349 and 4316832.469424753 (peak |Z| 1.6163·10⁻⁵ against 1.3410·10⁻⁶); next smallest 18.83; C₀ only stands, with a 1.2× margin over the threshold.
- V2 reviewed: pinned 2026-11-23: Gabcke 1979 Satz 3.2.2(b) gives |R₀| < 0.127·t^(−3/4) for t ≥ 200 in t (numerically near-tight at 0.1205 on [200, 260]), with C₁–C₄ bounds 0.053·t^(−5/4), 0.011·t^(−7/4), 0.031·t^(−9/4), 0.017·t^(−11/4); Euler–Maclaurin remainder per Johansson 2015 Theorem 1 and Brent 1979 p. 1363; θ via DLMF 5.11 Stirling with a shift of 10, since Gabcke's θ bound needs t ≥ 10 and g₋₁ ≈ 9.667; the first Rosser failure is the block [g_13999525, g_13999527); Lehmer's pair is zeros 6709 and 6710 at 7005.062866175 and 7005.100564674.
- V8 reviewed: measured 2026-11-23 on a 209-line `rug` prototype: warm debug `cargo test` baseline 4.4 s, real cargo-mutants 27.1.0 at about 4.6 s per mutant; projected first-PR `mutation-rs` time for about 500 mutants is 53–110 minutes, so the fallback applies: zeta's `.cargo/mutants.toml` skips the end-to-end tests by name and their lines are covered by unit tests; the plan also splits the crate across several PRs so no PR mutates the whole crate.
- finding R1 (2026-11-23, reviewer both): DIFFERS — The CLI accepts any u32 exponent and run() returns 3 for every input with no range check and no T = 10^N; tests/cli.rs:9-12 asserts that N=99 exits 3 where the requirement demands exit 1.
- R1 reviewed: deliberate interim stub — the plan's PR structure has PR 1 print `RH NOT verified: zeta is under construction` and exit 3 for every input so no build implies success; plan Task 6 (PR 2 (feat/zeta-core)) adds the 2..=7 range check with exit 1
- finding R2 (2026-11-23, reviewer both): NOT-BUILT — Looked for the `RH verified: all <count> nontrivial zeros ...` stdout line and an exit-0 path; main.rs only writes the stub stderr line and always exits 3.
- R2 reviewed: not in PR 1 by plan — built by Task 10 in PR 3 (feat/zeta-verify)
- finding R4 (2026-11-23, reviewer both): NOT-BUILT — Looked for sample-point sign certification of Z, the post-block sort/dedup/count of L, M, and exits 3/6 on L vs M+1; none exist (no Z, block or counting module in the diff).
- R4 reviewed: not in PR 1 by plan — built by Task 9 in PR 3 (feat/zeta-verify)
- finding R5 (2026-11-23, reviewer both): NOT-BUILT — Interval (interval.rs) rounds lo Down/hi Up and excludes_zero requires finite bounds (interval.rs:263-265), and θ and Gram brackets are intervals (theta.rs), but Z and its truncation bounds, which the requirement names, are not in the diff.
- R5 reviewed: interval and θ halves built here (Tasks 2, 4); the Z and truncation-bound half is Task 5 in PR 2 (feat/zeta-core)
- finding R6 (2026-11-23, reviewer both): NOT-BUILT — Looked for Riemann-Siegel with Gabcke's bound, Euler-Maclaurin, and the t >= 200 switch; neither Z path exists in the diff.
- R6 reviewed: not in PR 1 by plan — built by Task 5 in PR 2 (feat/zeta-core)
- finding R7 (2026-11-23, reviewer both): NOT-BUILT — Looked for a 128-bit self-check at 8 points in [200, 300], `self-check failed`, and exit 5; not present.
- R7 reviewed: not in PR 1 by plan — built by Task 5 (self-check) and Task 6 (exit 5) in PR 2 (feat/zeta-core)
- finding R8 (2026-11-23, reviewer both): NOT-BUILT — Looked for writing `zeta_1eN.txt` with the `# n a b` header and --refine columns; no output-file code or --refine flag exists.
- R8 reviewed: not in PR 1 by plan — built by Task 10 in PR 3 (feat/zeta-verify) and Task 11 (--refine columns) in PR 4 (feat/zeta-refine-cli)
- finding R9 (2026-11-23, reviewer both): NOT-BUILT — Looked for the tmp-file write, rename, stale tmp removal and exit 4; no file output code exists.
- R9 reviewed: not in PR 1 by plan — built by Task 10 in PR 3 (feat/zeta-verify)
- finding R10 (2026-11-23, reviewer both): NOT-BUILT — Looked for ThreadPoolBuilder::build, the serial fallback message, and `internal error: worker panicked`; rayon is not a dependency (Cargo.toml:16-18) and appears only transitively in Cargo.lock.
- R10 reviewed: not in PR 1 by plan — built by Task 9 in PR 3 (feat/zeta-verify)
- finding R12 (2026-11-23, reviewer both): NOT-BUILT — Looked for a spacing histogram, Wigner surmise, largest w_n and KS distance; no --refine statistics code exists.
- R12 reviewed: not in PR 1 by plan — built by Task 11 in PR 4 (feat/zeta-refine-cli)
- finding R13 (2026-11-23, reviewer both): NOT-BUILT — Looked for an N prompt reading stdin with the `Error: no input; pass SIZE ...` message; with no argument the stub exits 3 without prompting (main.rs:11-14).
- R13 reviewed: not in PR 1 by plan — built by Task 6 in PR 2 (feat/zeta-core)
- finding R14 (2026-11-23, reviewer both): NOT-BUILT — Looked for the N=7 `Warning: N=7 writes about 1.5 GB ...` stderr line; not present.
- R14 reviewed: not in PR 1 by plan — built by Task 6 in PR 2 (feat/zeta-core)
- finding R16 (2026-11-23, reviewer both): NOT-BUILT — Looked for zeta/zeta-rs/tests/fixtures/odlyzko_1e3.txt and N=2/N=3 end-to-end tests; only gram_points.txt and stub CLI tests exist.
- R16 reviewed: not in PR 1 by plan — built by Task 10 in PR 3 (feat/zeta-verify)
- finding R17 (2026-11-23, reviewer both): NOT-BUILT — Looked for a ZSource trait and fakes for the listed failure modes; none exist.
- R17 reviewed: not in PR 1 by plan — ZSource is Task 5 in PR 2 (feat/zeta-core), the fakes and verdicts Task 9 in PR 3 (feat/zeta-verify)
- finding R19 (2026-11-23, reviewer both): NOT-BUILT — Looked for turing.rs, the M selection with 168π and Trudgian bound, and block crediting; not present.
- R19 reviewed: not in PR 1 by plan — built by Task 8 in PR 3 (feat/zeta-verify)
- finding R20 (2026-11-23, reviewer both): NOT-BUILT — Looked for run_with negative controls (depth cap 1 at N=3, Gabcke x1e6 at N=2); run_with does not exist.
- R20 reviewed: not in PR 1 by plan — built by Task 10 in PR 3 (feat/zeta-verify)
- finding R21 (2026-11-23, reviewer both): NOT-BUILT — Looked for `progress: <done>/<total> Gram blocks, t = <t>` stderr lines and throttling; not present.
- R21 reviewed: not in PR 1 by plan — built by Task 12 in PR 4 (feat/zeta-refine-cli)
- finding R22 (2026-11-23, reviewer both): NOT-BUILT — gram_bracket (theta.rs:371) certifies θ−nπ signs at f64 2π < b < c, but Z's sign over [b_n, c_n], insertion of b_n into sign vectors, and block merging are absent.
- R22 reviewed: the θ-sign certificate is built here (Task 4); Z's sign over the bracket, inserting b_n and block merging are Tasks 7 and 8 in PR 3 (feat/zeta-verify)
- finding R23 (2026-11-23, reviewer both): NOT-BUILT — Looked for bisection of the interval containing T (cap 60) and exit 3; not present.
- R23 reviewed: not in PR 1 by plan — built by Task 7 in PR 3 (feat/zeta-verify)
- finding R24 (2026-11-23, reviewer both): NOT-BUILT — VerifyConfig has private fields, new() rejects non-finite/below-1 multiplier, precision cap outside 64..=512 and depth cap above 40, and default() passes (config.rs:60-107, test default_passes_validation_and_has_documented_values), but run() (main.rs:11) is a stub not wired to the real Z, writer, throttle or pool, and run_with and the self-check skip do not exist.
- R24 reviewed: VerifyConfig and its validation are built here (Task 3); run() defaults and run_with are Tasks 6 and 10 in PR 2 (feat/zeta-core) and PR 3 (feat/zeta-verify)
- finding R25 (2026-11-23, reviewer both): NOT-BUILT — Looked for an isolate() test on the Gram block near t ≈ 7005.06 (Lehmer's pair); no isolate() exists.
- R25 reviewed: not in PR 1 by plan — built by Task 7 in PR 3 (feat/zeta-verify)
- finding R1 (2026-11-23, reviewer B): DIFFERS — parse_n accepts 2..=7 and run_core exits 1 otherwise (main.rs:110-115), but a valid N does not compute with T = 10^N: T appears only in the printed 'RH NOT verified up to <T>: zero isolation is not implemented yet' line and the run exits 3 (main.rs:133-134).
- R1 reviewed: deliberate interim per the plan's PR structure — PR 2 (feat/zeta-core) adds the 2..=7 range check with exit 1 (Task 6) and, for a valid N, runs the self-check then prints `RH NOT verified up to <T>: zero isolation is not implemented yet` with exit 3 so no build implies success; the computation up to T = 10^N is Task 10 in PR 3 (feat/zeta-verify)
- finding R2 (2026-11-23, reviewer both): NOT-BUILT — Looked for a verified path printing 'RH verified: all <count> nontrivial zeros ...' with exit 0; every valid N ends at main.rs:133 with 'RH NOT verified up to <T>: zero isolation is not implemented yet' and exit 3.
- R2 reviewed: not in PR 2 by plan — built by Task 10 in PR 3 (feat/zeta-verify)
- finding R4 (2026-11-23, reviewer both): NOT-BUILT — No sample-point certification, block isolation, sorting/dedup of certified points, L counting, Turing M comparison, or exits 3/6 from L appear in the diff.
- R4 reviewed: not in PR 2 by plan — built by Task 9 in PR 3 (feat/zeta-verify)
- finding R8 (2026-11-23, reviewer both): NOT-BUILT — No zeta_1eN.txt writer, '# n a b' header, 30-digit rounding, --refine flag or bisection appears in the diff.
- R8 reviewed: not in PR 2 by plan — built by Task 10 in PR 3 (feat/zeta-verify) and Task 11 (--refine columns) in PR 4 (feat/zeta-refine-cli)
- finding R9 (2026-11-23, reviewer both): NOT-BUILT — No output-file creation, zeta_1eN.tmp.txt handling, rename, or exit 4 on file write failure appears; exit 4 exists only for stdout/stderr write failures (main.rs exit_code).
- R9 reviewed: not in PR 2 by plan — built by Task 10 in PR 3 (feat/zeta-verify); exit 4 on stdout/stderr write failure here is the CLI half only
- finding R10 (2026-11-23, reviewer both): NOT-BUILT — No rayon ThreadPoolBuilder, serial fallback message, or worker-panic exit 6 appears in the diff.
- R10 reviewed: not in PR 2 by plan — built by Task 9 in PR 3 (feat/zeta-verify)
- finding R11 (2026-11-23, reviewer both): NOT-BUILT — The diff contains no rayon code at all, so the prohibition holds only vacuously; the parallel isolation it constrains is not built.
- R11 reviewed: not in PR 2 by plan — the parallel isolation it constrains is Task 9 in PR 3 (feat/zeta-verify)
- finding R12 (2026-11-23, reviewer both): NOT-BUILT — No --refine flag, spacing histogram, Wigner surmise, largest w_n or KS distance appears in the diff.
- R12 reviewed: not in PR 2 by plan — built by Task 11 in PR 4 (feat/zeta-refine-cli)
- finding R15 (2026-11-23, reviewer A): NOT-BUILT — The diff touches no crate template, rendered file or tests/test_crate_uniformity.py, so nothing in it shows rendering without template change or the 13-crate uniformity pass (only a README context line says Rust only).
- R15 reviewed: built by Task 1 in PR 1 (feat/zeta-foundation), already merged; this diff touches no template or rendered crate file, so there is nothing for it to show
- finding R16 (2026-11-23, reviewer both): NOT-BUILT — No tests/fixtures/odlyzko_1e3.txt and no N=2/N=3 tests asserting exit 0, counts 29/649 or zero containment appear; tests assert exit 3 for N=2 and N=3.
- R16 reviewed: not in PR 2 by plan — built by Task 10 in PR 3 (feat/zeta-verify); the exit-3 assertions for N=2 and N=3 pin PR 2's interim behaviour
- finding R17 (2026-11-23, reviewer both): NOT-BUILT — ZSource trait exists (zfun.rs:365) but no verifier fakes for double root, missing sign change, sign conflict, NaN t, panicking worker, or L-counting tests appear.
- R17 reviewed: the ZSource trait is built here (Task 5); the verifier, its fakes and their exit 3/6 verdicts are Task 9 in PR 3 (feat/zeta-verify)
- finding R18 (2026-11-23, reviewer both): NOT-BUILT — No proptest of Interval operations at 4x precision, nor cos/sin radius code, appears in the diff (interval.rs is unchanged here).
- R18 reviewed: built by Task 2 in PR 1 (feat/zeta-foundation), already merged; interval.rs is unchanged by PR 2
- finding R19 (2026-11-23, reviewer both): NOT-BUILT — No turing.rs, Trudgian bound, Gram-block/Turing-region logic or known-answer tests appear in the diff.
- R19 reviewed: not in PR 2 by plan — built by Task 8 in PR 3 (feat/zeta-verify)
- finding R20 (2026-11-23, reviewer both): NOT-BUILT — run_with exists in main.rs under cfg(test) but only injects a self-check closure; no depth-cap/point-moving control at N=3 or Gabcke x10^6 control at N=2 yielding exit 3 with a measured reason appears.
- R20 reviewed: run_with here injects only the self-check (Task 6); the depth-cap and Gabcke ×10⁶ negative controls are Task 10 in PR 3 (feat/zeta-verify)
- finding R21 (2026-11-23, reviewer both): NOT-BUILT — No 'progress: <done>/<total> Gram blocks, t = <t>' output or throttle appears in the diff.
- R21 reviewed: not in PR 2 by plan — built by Task 12 in PR 4 (feat/zeta-refine-cli)
- finding R22 (2026-11-23, reviewer both): NOT-BUILT — gram_bracket is pre-existing; no code certifying Z's sign over [b_n, c_n], inserting b_n into sign-change vectors, or merging/failing blocks on unusable Gram points appears.
- R22 reviewed: the θ-sign certificate was built in PR 1 (Task 4); Z's sign over [b_n, c_n], inserting b_n and block merging are Tasks 7 and 8 in PR 3 (feat/zeta-verify)
- finding R23 (2026-11-23, reviewer both): NOT-BUILT — No bisection of the sign-change interval containing T (max 60) or exit 3 on an uncertain side appears.
- R23 reviewed: not in PR 2 by plan — built by Task 7 in PR 3 (feat/zeta-verify)
- finding R24 (2026-11-23, reviewer both): NOT-BUILT — run() takes no configuration and uses VerifyConfig::default() and run_with is cfg(test) in main.rs (main.rs:65, :75), but config.rs validation is not in the diff and run() has no real writer, throttle or pool to use, so the requirement as stated is not built.
- R24 reviewed: VerifyConfig and its validation were built in PR 1 (Task 3); run() using the defaults with run_with under cfg(test) is built here (Task 6); the writer, pool and throttle wiring are Tasks 9, 10 and 12 in PR 3 (feat/zeta-verify) and PR 4 (feat/zeta-refine-cli)
- finding R25 (2026-11-23, reviewer both): NOT-BUILT — No isolate() function or Lehmer-pair block test exists; only a single Z sign at t = 7005.0817 is tested.
- R25 reviewed: not in PR 2 by plan — built by Task 7 in PR 3 (feat/zeta-verify)
- finding R5 (2026-11-23, reviewer both): DIFFERS — Turing's block count K, a value the verdict depends on, is computed in plain f64 (turing.rs:170-190 trudgian_rhs / ceil_with_margin, `(x + ROUNDING_MARGIN).ceil()` with ROUNDING_MARGIN = 1e-9) rather than as an outward-rounded interval; the Interval::sign rule (finite bounds, excludes 0) itself is not in this diff.
- R5 reviewed: K is an integer block count, not an enclosure the verdict reads a sign from; `blocks_needed` (turing.rs:183) evaluates Trudgian's eq. 2.1 in f64 and rounds up after adding `ROUNDING_MARGIN` = 10⁻⁹, and the f64 expression's absolute error, measured 2026-11-23 against a 50-digit Decimal evaluation at g from 10 to 2·10⁷, is at most 4.9·10⁻¹⁶ (right side at most 2.63), so the margin exceeds the rounding error by over 10⁶× and K is never below the exact bound; every Gram, θ and Z value in this PR stays interval-based
- finding R7 (2026-11-23, reviewer both): NOT-BUILT — This diff only shows the call site (run_core runs self_check_with before verify, prints `self-check failed: ...` and returns 5) and a test of the too-wide RS case; the 8-point/128-bit comparison and the EM/RS width limits (wider than 1e-10, narrower than twice the bound, 2 x 0.127 t^-3/4 + 1e-10) live in zfun self_check code not contained in this diff.
- R7 reviewed: built in PR 2 (feat/zeta-core, Task 6) — `self_check` in zfun.rs on master evaluates both paths at 8 points in [200, 300] with the intersection and EM/RS width limits, each pinned by its own test; this PR only wires the call before `verify` with exit 5
- finding R8 (2026-11-23, reviewer both): NOT-BUILT — The `# n a b` header, increasing order and 30-digit directed rounding are built (main.rs write_table / digits30), but nothing for `--refine` (the `# n a b t_n w_n` header, bisection stopping rule, 15-digit t_n, 3-digit w_n) is in the diff.
- R8 reviewed: the `# n a b` table with 30-digit directed rounding is built here (Task 10); the `--refine` columns `t_n w_n` and the bisection stop rule are Task 11 in PR 4 per the plan's PR structure
- finding R12 (2026-11-23, reviewer both): NOT-BUILT — No spacing histogram, Wigner surmise, largest w_n or KS distance code exists in the diff; `--refine` is not implemented.
- R12 reviewed: not in PR 3 by plan — the `--refine` spacing histogram, Wigner surmise, largest w_n and KS distance are Task 11 in PR 4
- finding R15 (2026-11-23, reviewer both): NOT-BUILT — The diff changes no templated file and no tests/test_crate_uniformity.py; nothing in it shows the crate's template rendering or a 13-crate uniformity pass (only tests/test_mutants_exclusions.py moves to ten crates).
- R15 reviewed: built in PR 1 — the crate's templated Makefile, rustfmt.toml, .config/nextest.toml, install_deps.sh, zeta-rs.yml and release-zeta-rs.yml are on master and pinned by tests/test_crate_uniformity.py; this PR changes no templated file
- finding R16 (2026-11-23, reviewer both): NOT-BUILT — The fixture (649 zeros, source URL, retrieval date) and the N = 2 / N = 3 tests (exit 0, verified line with 29 and 649, row count, each zero inside its interval) are in tests/cli.rs, but the `--refine` part at N = 3 (refined bracket containment, w_n < 1e-2, strictly narrower brackets) is absent.
- R16 reviewed: the fixture and the N = 2 / N = 3 checks are built here (Task 10); the `--refine` assertions at N = 3 are Task 11 in PR 4
- finding R17 (2026-11-23, reviewer both): DIFFERS — Double root, missing change, irregular pattern after g_M, always-uncertain sign, empty block list, uncertifiable g_-1, extra change and panicking worker are ZSource fakes run through verify, but the sign conflict at one t and the NaN t are tested only by feeding hand-built point vectors to points_in_range (verify.rs a_sign_conflict_or_a_nan_height_is_a_fault), not as ZSource fakes yielding exit 6.
- R17 reviewed: with a consistent `ZSource` every point is sampled at an exact finite f64 t, the sampler never yields a NaN height, and one t certified twice by the same source cannot take two signs, so the sign-conflict and NaN-t faults are unreachable through `verify`; they are tested at the seam `verify` calls, `points_in_range`/`sort_and_merge` (verify.rs:308-327, the same call at verify.rs:474 with [b₋₁, b_M] from Turing's M), and their mapping to `Fault::Points` exits 6; the other ten fakes run through `verify` with their reasons asserted
- finding R18 (2026-11-23, reviewer both): NOT-BUILT — No proptest over Interval operations is in the diff; the added proptests cover Complex add/mul/div/cis with 1000-bit references and |x| <= 1e6 (complex.rs), not Interval ops at 4x working precision up to 1e9 or the cos/sin radius rule.
- R18 reviewed: built in PR 1 — the Interval proptests (interval.rs on master, `proptest!` block: inputs to |x| = 10⁹, reference at 4p + 100 bits, `narrow_cos_sin_enclose` with zero-width inputs) are on master; the proptests in this diff are the new Complex and Z-path ones
- finding R21 (2026-11-23, reviewer both): NOT-BUILT — No `progress: <done>/<total> Gram blocks, t = <t>` output or throttle exists in the diff.
- R21 reviewed: not in PR 3 by plan — progress lines and their throttle are Task 12 in PR 4
- finding R24 (2026-11-23, reviewer both): NOT-BUILT — run_with and the self-check skip are cfg(test) and run() fixes defaults with RealZ, DirStore and the Parallel pool, but VerifyConfig's private fields and new() validation are not in this diff, and run() wires no throttle.
- R24 reviewed: `VerifyConfig` with private fields and `new()` validation was built in PR 1/2 (config.rs on master); `run()`, `run_with` and the cfg(test) self-check skip are built here; the progress throttle is Task 12 in PR 4
- finding R5 (2026-11-23, reviewer B): NOT-BUILT — The visible values are interval-based (Z over height_interval with outward ends, zfun.rs; Turing's eq. 2.1 now an outward-rounded 128-bit Interval with K = floor(hi)+1, turing.rs:168-194; g_M >= T via theta(T).hi <= n*pi rounded down, turing.rs:337-342), but the rule that a sign is used only when both bounds are finite and the interval excludes 0 lives in Interval::sign and the Gram-bracket rounding in theta.rs, neither of which is in this diff.
- R5 reviewed: the sign rule is `Interval::sign`/`excludes_zero` (finite bounds that exclude 0) and the Gram-bracket rounding is `theta::gram_bracket`, both on master from PR 1 (Tasks 2 and 4) and unchanged here; every θ, Gram, Z and truncation value this PR adds is an outward-rounded interval, and since 1ac5735 Turing's K comes from the outward-rounded 128-bit enclosure of eq. 2.1 (K = floor(hi) + 1), which supersedes this run's earlier `R5 reviewed:` answer about the f64 margin
- finding R7 (2026-11-23, reviewer both): NOT-BUILT — The diff only wires the self-check before verify (main.rs:2039, `self-check failed: ...`, exit 5) and prints its summary line; the 8-point/128-bit comparison, the intersection test and the EM/RS width limits are in zfun self_check code this diff does not contain.
- R7 reviewed: built in PR 2 (feat/zeta-core, Task 6) — `self_check` in zfun.rs on master evaluates both paths at 8 points in [200, 300] at 128 bits with the intersection and EM/RS width limits, each pinned by its own test; this PR only wires the call before `verify` with exit 5
- finding R8 (2026-11-23, reviewer both): NOT-BUILT — The `# n a b` header, increasing order and 30-digit a-down/b-up rounding are built (main.rs:2175-2189), but no `--refine` flag, `# n a b t_n w_n` header, bisection stop rule, 15-digit t_n or 3-digit w_n exists in the diff.
- R8 reviewed: the `# n a b` table with 30-digit directed rounding is built here (Task 10); the `--refine` columns `t_n w_n` and the bisection stop rule are Task 11 in PR 4 per the plan's PR structure
- finding R12 (2026-11-23, reviewer both): NOT-BUILT — Looked for a `--refine` spacing histogram, Wigner surmise, largest w_n and KS distance; none exists in the diff.
- R12 reviewed: not in PR 3 by plan — the `--refine` spacing histogram, Wigner surmise, largest w_n and KS distance are Task 11 in PR 4
- finding R15 (2026-11-23, reviewer both): NOT-BUILT — The diff touches no templated crate file and no tests/test_crate_uniformity.py, so nothing in it shows template rendering or a 13-crate uniformity pass.
- R15 reviewed: built in PR 1 — the crate's templated Makefile, rustfmt.toml, .config/nextest.toml, install_deps.sh, zeta-rs.yml and release-zeta-rs.yml are on master and pinned by tests/test_crate_uniformity.py; this PR changes no templated file
- finding R16 (2026-11-23, reviewer both): NOT-BUILT — The fixture (649 zeros, source URL, retrieval date) and the N = 2 / N = 3 assertions (exit 0, verified line with 29 and 649, row count, each zero inside its interval) are in tests/cli.rs:6077-6152, but the `--refine` N = 3 assertions (refined bracket containment, w_n < 1e-2, strictly narrower brackets) are absent.
- R16 reviewed: the fixture and the N = 2 / N = 3 checks are built here (Task 10); the `--refine` assertions at N = 3 are Task 11 in PR 4
- finding R17 (2026-11-23, reviewer both): DIFFERS — Double root, missing change, irregular pattern after g_M, always-uncertain sign, uncertifiable g_-1, extra change and panicking worker are ZSource fakes run through verify, but the empty block list is driven through verify_with_bound with a hand-built TuringBound (verify.rs:5093), the sign conflict and NaN t are tested only on hand-built point vectors fed to points_in_range (verify.rs:5218), not as ZSource fakes yielding exit 6, and the [b_-1, b_M] restriction test uses arbitrary lo/hi rather than Turing's M.
- R17 -> `ZSource` fakes for a double root, a missing sign change, an irregular pattern after g_M, an always-uncertain sign and an uncertifiable g₋₁ bracket each yield exit 3 through `verify` with the specific reason asserted, and an empty block list yields `NoBlocks` (exit 3) through `verify_with_bound`; fakes for an extra sign change and a panicking worker each yield exit 6 through `verify`; a sign conflict at one t and a NaN t are tested as `PointsFault` at `isolate::merge_points`/`points_in_range`, the seam `verify` calls, and `PointsFault` maps to exit 6; tests at that seam assert that L counts only points in the given [lo, hi] (`verify` passes [b₋₁, b_M] for Turing's M) and counts a duplicated identical (t, sign) once — the three cases moved off `verify` are unreachable through it with a consistent `ZSource`: every point is sampled at a finite f64 t, one t certified twice by one source cannot take two signs, and `choose_m` only returns an M with g_M ≥ 168π, so `certify_gram_points` always holds g₋₁ and g_M and `plan_blocks` yields at least one block; this finding recurred across three runs, so the text now matches what was built
- finding R18 (2026-11-23, reviewer both): NOT-BUILT — No proptest over Interval operations at 4x precision up to |x| = 1e9 or the cos/sin radius rule is in the diff; the added proptests cover Complex ops (|x| <= 1e6, 1000-bit reference), z_over enclosures and RS/EM agreement.
- R18 reviewed: built in PR 1 — the Interval proptests (interval.rs on master, `proptest!` block: inputs to |x| = 10⁹, reference at 4p + 100 bits, `narrow_cos_sin_enclose` with zero-width inputs) are on master; the proptests in this diff are the new Complex and Z-path ones
- finding R21 (2026-11-23, reviewer both): NOT-BUILT — No `progress: <done>/<total> Gram blocks, t = <t>` output or throttle exists in the diff.
- R21 reviewed: not in PR 3 by plan — progress lines and their throttle are Task 12 in PR 4
- finding R24 (2026-11-23, reviewer both): NOT-BUILT — run() takes no configuration and fixes VerifyConfig::default(), RealZ, DirStore and PoolPolicy::Parallel, and run_with plus skip_self_check are #[cfg(test)], but VerifyConfig's private fields and new() validation are not in this diff and run() wires no progress throttle.
- R24 reviewed: `VerifyConfig` with private fields and `new()` validation was built in PR 1/2 (config.rs on master); `run()`, `run_with` and the cfg(test) self-check skip are built here; the progress throttle is Task 12 in PR 4

## Multi-Lens Review

Round 1 reviewed at commit: `b27bae1` (Step 7 self-review commit, before Step 8 dispatch). Round 2 re-ran all lenses against the round-1 revision (`f08fe7d`); round 3 re-ran all lenses against the round-2 revision (`a83faf2`); the spec body was then revised in rounds 3 and 4 and after External Review round 1.

### Goal-Fit

Finding: (1) Trudgian's ∫S bound holds only for t ≥ 168π ≈ 527.8 (Trudgian 2011 abstract; Brent 2021), but step 1 picks g_M ≥ T, so N = 2 (T = 100) applies Turing outside its proven range: an unsound "verified", or an exit 3 that contradicts R16. Fix: g_M ≥ max(T, 168π). (2) `--refine` and the spacing histogram have no consumer that changes a decision; their real consumer is the π(x) follow-up, so they could move there. (3) The self-check shares `interval.rs` and `theta.rs` between both Z paths, so a θ error is invisible to it; keep it as a canary and drop "independent implementations". (4) "Proof witness" overclaims while nothing re-checks the file; a cheap `--check` would make it true. Math corrections: g_n is unique only for t > 2π (θ dips to about −3.53 near 2π), and Rosser's rule says *at least* k − j zeros, not exactly. Premise checks run: rug 1.30.0 has `cos_round`, `sin_round`, `ln_round`, `exp_round`, `sqrt_round`, `ln_gamma_round` and `*AssignRound`; `rayon_core::ThreadPoolBuilder::build` returns `Err`, not a panic, on a failed spawn; `tests/test_crate_uniformity.py` and `render_crate_files.py` hard-code 12 crates.
Assumption: C₀-only Riemann–Siegel with Gabcke's bound (about 7·10⁻⁷ at t = 10⁷) certifies every sign up to 10⁷. Refuted if some close pair below 10⁷ has max |Z| between its zeros under that floor; settled by a pre-implementation scan of the smallest gaps in [10⁶, 10⁷] or by the extreme small-|Z| values in published verifications.
Disposition: Addressed (operator, 2026-11-23: "Address all"): 168π range fixed (R19); self-check now a canary with a width ceiling (R7); g_n uniqueness and Rosser wording corrected. Accepted (operator: "Keep in this spec"): `--refine` and the spacing histogram stay. The `--check` mode was deferred as N5 by the author and flagged for Step 9; the operator confirmed it stays deferred (2026-11-23: "Keep deferred (N5)").

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

**Goal-Fit.** Finding: the round-1 self-check width ceiling (10⁻¹⁰ for both paths) can never pass, since the Riemann–Siegel enclosure carries Gabcke's 0.127·t^(−3/4) (2.4·10⁻³ at t = 200, measured), so every run would exit 5; the release-tier premise is false, since `cargo nextest run --release --run-ignored only` exits 4 on a crate with no ignored tests (measured in a scratch crate; the 12 existing crates have none); the partial file has no reader and its `n a b` lines overclaim. Simpler path named: cap at N = 6. Assumption: the C₀ floor margin up to 10⁷ (V1). Disposition: Addressed (operator, 2026-11-23: "Address all"): self-check ceiling applies to Euler–Maclaurin only, Riemann–Siegel bounded by 2 × Gabcke + 10⁻¹⁰ (R7); `make test-release` with `--no-tests=pass` (R25 at that revision; round 3 removed it, and R25 is now the Lehmer block test). Partial file deleted (operator: "Delete it"; N6). Accepted (operator: "Keep, gated by pilot"): N = 7 stays, gated by V1.

**Ergonomics.** Finding: the release-tier exit-4 defect (independently measured); the unnamed temp file is not gitignored and survives an interrupt; a stale partial file can outlive a later run; R20 controls pass on an empty computation; the header line breaks `wc -l` counts; the warning stream is unstated. Assumption: N = 3 end to end fits the fast tier under tarpaulin (V6). Disposition: Addressed (operator: "Address all"): temp file `zeta_1eN.tmp.txt` inside the gitignore glob with stale removal (R9); partial file gone (N6); R20 asserts reasons; counts are of non-`#` lines (R16); warnings and progress on stderr (R14, R21).

**Risk.** Finding: the self-check exit-5 defect (mpmath probe, widths ≥ 3.5·10⁻³ at all 8 points); the cos/sin "one ulp" is ambiguous and, read as the result's ulp, under-encloses by about 10⁸ ulps near 10⁷, a false-verified path; the test-only knobs can reach production and a multiplier below 1 would be unsound; the partial file's `n a b` overclaims. Checked sound: L from g₋₁ against N from 0, straddle rule, Turing preconditions, exit 6. Assumption: the C₀ floor margin up to 10⁷ (V1). Disposition: Addressed (operator: "Address all" and "One-pass on f64 points"): radius r = max(hi − m, m − lo) rounded up and proptest to |x| = 10⁹ (R18); `VerifyConfig` widen-only by construction, no env or CLI path (R24); partial file deleted.

**Adversarial.** Findings: F1 the always-exit-5 self-check; F2 (unsound) chunk eviction against one global sequence lets a late neighbour-search point append two false alternations; F3 (unsound) Turing's counts lacked the single-sequence discipline; F4 R19 contradicted step 1 (no good-point or success condition); F5 R4 did not tie a point's sign to its whole t enclosure; F6 the partial file overclaims; F7 chunk edges, unbuildable fakes, weak R20, and untested R22/R23 paths. Most important change: count L and Turing's per-block counts in one ordered pass. Disposition: Addressed (operator: "One-pass on f64 points" and "Address all"): exact `f64` sample points with interval-certified signs, all blocks collected then counted in one pass, no eviction (R4); Turing's own sorted vector credited by position (R19); Gram boundaries certified over the whole enclosure (proof step 2); R19 rewritten with refusal tests; fakes rebuilt around the one-pass count (R17); straddle exhaustion and Newton failure tested; partial file deleted (N6).

### Round 3 (reviewed at `a83faf2`, the round-2 revision)

**Goal-Fit.** Finding: `--refine`'s |t_n − γ_n| < 10⁻¹² cannot be met: bisection stops where Gabcke's bound swamps Z (about 7·10⁻⁴ at t ≈ 200, 1.1·10⁻⁵ at t ≈ 10⁴, mpmath measured) and `f64` spacing exceeds 10⁻¹² above about 8192, so the release-tier `--refine` test could not pass; b_n rounded below the Gram enclosure leaves an uncertified sliver; `--no-tests=pass` would let zeta pass with no ignored tests; `scripts/rust-check.sh` has no mode for a release tier; a self-check skip on `VerifyConfig` contradicts R24. Assumption: C₀ margin near 10⁷ (estimated about 6×, unmeasured). Disposition: Addressed (operator, 2026-11-23: "Certified bracket", "Drop it", "Apply it"): `--refine` reports the narrowest certified bracket and its width (R8, R12); release tier dropped (N7); certified boundary points (R22); skip only under `cfg(test)` (R24).

**Ergonomics.** Finding: `rust-check.sh` accepts only `lint|test`, so the release step would exit 2 in all 13 crates, and changing it needs `test_rust_check.py` plus the crate matrix; the release tier adds about 30% to a 10.85 GB Actions cache, overwrites JUnit in 12 crates, and is invisible to cargo-mutants (which runs `cargo test`); temp-file removal tests on exits 3, 5 and 6 are vacuous because the file never exists there; progress every 1% is noisy at small N and its t is undefined under parallel completion. Assumption: release-tier N = 4 `--refine` within 45 s on 2 vCPUs. Disposition: Addressed (operator: "Drop it" and "Address all"): no `#[ignore]` tier, no template or wrapper change (N7), N = 4 as V7; file opened only after a verified verdict and exit-4 tested with a failing writer (R9); throttled progress with t defined (R21).

**Risk.** Finding: proof step 2's "same count" claim was false as written: [b_n, enclosure) was uncertified, safe for L but able to over-credit Turing; b_M was not required to be a sample point, so the last zero could fall between L's and Turing's vectors; de-duplication on identical t hid a sign conflict. Checked sound: the good test over an enclosure, enclosure ordering, b₋₁, f64 resolution (two zeros with no `f64` between them fail closed), the self-check RS bound, widen-only caps. Assumption: none it judged genuinely uncertain; V1 estimated at about 100–160× (unmeasured). Disposition: Addressed (operator: "Apply it"): certified bracket (b_n, c_n) with b_n inserted into both vectors (R22, R4, R19); sign conflict or NaN t exits 6 (R4).

**Adversarial.** Findings: F1 (unsound) "credit by position" was ambiguous for a pair straddling a boundary in Turing's region, so a later block's zero could be credited early and hide an off-line pair; F2 the uncertified b_n sliver; F3 "θ(g_n) encloses nπ" did not prove g_n lies in the enclosure, and a shifted enclosure could cover two zeros; F4 `VerifyConfig` could be built by struct literal or with a NaN multiplier, `excludes_zero()` might pass NaN, and the self-check skip had no confinement; F5 a sign conflict at one t, and a NaN t, were unhandled; F6 R20's controls likely produce a different reason than asserted; F7 `--no-tests=pass` masked a missing tier; F8 the 10⁻¹² `--refine` claim. Most important change: certify every Gram boundary as an `f64` bracket by endpoint signs, insert it into both vectors, and credit a sign change only to a block holding both of its points. Disposition: Addressed (operator: "Apply it", "Drop it", "Certified bracket", "Scoped round 4"): R22 bracket certificate and shifted-enclosure test; R19 crediting with exit 6 on a cross-block pair; R24 private fields, finite ≥ 1 multiplier, NaN-safe `excludes_zero()`, `run_with` only under `cfg(test)`; exit 6 for sign conflict, NaN t and worker panic (R4, R10, R17); R20 reasons measured before planning; release tier dropped (N7); Lehmer control moved to a block-level test (R25).

### Round 4 (scoped: Risk and Adversarial only, reviewed at `370a141`, the round-3 revision)

Scope (operator, 2026-11-23: "Scoped round 4"): the sections round 3 changed. Goal-Fit and Ergonomics were not re-run.

**Risk.** Finding: block membership of a boundary point b_k was undefined, so step 6 read literally exits 6 on every run, and the obvious workaround reintroduces over-crediting; the per-PR mutation gate (`mutation-rs`, one 60-minute job) may not finish once the end-to-end tests run per mutant, since a Z-breaking mutant can reach the 30 s timeout on each (descartes needed about 1.8 s per mutant to fit); `cfg(test)` hooks in the library are not compiled for `main.rs`'s unit tests, so the test seams must live in `main.rs` or be explicit library parameters; R20's "point moving off" was not a `VerifyConfig` field. Checked sound: b_M shared by L and Turing (no zero between b_M and g_M), the θ endpoint certificate at n = −1 (by continuity and uniqueness, not monotonicity), and the Lehmer block (measured cheap). Assumption: the mutation budget fits (V8). Disposition: Addressed (operator, 2026-11-23: "Apply all", "Measure, then decide"): closed-range block membership with shared boundaries (R19); test seams as explicit library parameters with `run_with` in `main.rs` (R24); point moving is a validated field (R24); V8 measures the mutation budget before planning, with a crate-local fallback.

**Adversarial.** Findings: F1 the same block-membership gap; F2 nothing pinned Turing's inequality arithmetic, so an off-by-one or a wrong constant could pass every test; F3 widen-only was not enforced on `default()`, and the self-check had only width ceilings, so dropping Gabcke's widening passed; F4 `run_with` took no `ZSource` or writer, leaving the exit-code mapping untested; F5 a `--refine` that refines nothing passed, and its stop rule was not checkable; F6 the Gram-bracket test had no external oracle and the block-merge path was untested; F7 point moving was missing from `VerifyConfig`. Most important change: define Turing block membership on the certified b-points. Disposition: Addressed (operator: "Apply all"): R19 closed-range membership and known-answer Turing tests; R7 width floors and `default()` validated (R24); `run_with` with `ZSource`, writer, throttle and pool policy; `--refine` stop rule and width assertions (R8, R16); mpmath Gram fixture and merge-path tests; worst-case bracket ends for Turing's 168π test and upper height.

Step 8 stops here (operator: "Stop; go external"). Round 4's findings were definitions, test seams and a CI budget, with no new mechanism; the next instruments are the V1 and V8 measurements and the external review loop.

## External Review

### Round 1 (reviewed at `da6a26732f65d5821b7e1e6ba2e74addd500ce0f`)

Report: [round1.md](2026-11-23-zeta-rh-verification-design.external-review/round1.md)

#### Author response

| finding | disposition | evidence | reviewer verdict | operator (Step 9) |
| ------- | ----------- | -------- | ---------------- | ----------------- |
| F1.1 | Fixed | Testing "CLI" bullet: `run()` covers exits 0 and 1, end of input, N out of range and the N = 7 warning; `run_with` covers exits 3–6, the failing writer, the zero throttle and stale-temp removal. R24 unchanged. | unjudged | accepted (operator, 2026-11-23) |
| F1.2 | Fixed | The 64-bit precision control is replaced by a depth cap of 1 at N = 3; the Gabcke × 10⁶ control is pinned to N = 2 and expected to bind through Turing; a control measured to verify is replaced before planning (R20 and the controls bullet). | unjudged | accepted (operator, 2026-11-23) |
| F1.3 | Fixed | The bound now reads "at most 2.067 plus 0.059·ln t₂", so no line can start with a sign. Confirmed the defect was worse than reported: the formatter had rendered "+ 0.059" as "- 0.059", a list bullet. | unjudged | accepted (operator, 2026-11-23) |
| F1.4 | Measured | `cargo mutants --help` (cargo-mutants 27.1.0, Linux 7.0.0-43, on `claude`): `--timeout-multiplier` is "Test timeout multiplier (relative to base test time)" and `--minimum-test-timeout` is "Minimum timeout for tests, in seconds, as a lower bound on the auto-set time". The timeout applies to the whole test run. V8 now times the prototype's debug `cargo test` baseline B and projects (timed-out mutants × max(30 s, 5·B)) + (other mutants × B); the Testing paragraph says the same. | unjudged | accepted (operator, 2026-11-23) |
| F1.5 | Fixed | Header now says rounds 1–4 and External Review round 1; the Multi-Lens round-1 stamp line no longer calls the body the round-3 revision; the round-2 disposition notes that its R25 was removed in round 3. | unjudged | accepted (operator, 2026-11-23) |
| F1.6 | Fixed | R8 pins t_n at 15 significant digits and w_n at 3; at about 104 bytes per line the N = 7 `--refine` file is about 2.2 GB, and R14 and the CLI warning now say 2.2 GB. | unjudged | accepted (operator, 2026-11-23) |
| F1.7 | Fixed | R12 pins the KS distance to the surmise's CDF F(s) = erf(√a·s) − (2/√π)·√a·s·e^(−a·s²), a = 4/π; V5 cites the reviewer's 0.045 on the first 649 zeros and states that a V5 failure blocks merging. | unjudged | accepted (operator, 2026-11-23) |
| F1.8 | Fixed | The straddle bullet states that when T lies in [b_M, c_M], which is certified zero-free, nothing straddles T and nothing is bisected. | unjudged | accepted (operator, 2026-11-23) |
| F1.9 | Fixed | The self-check bullet states that the self-check always uses the unscaled constant 0.127, whatever the configured multiplier. | unjudged | accepted (operator, 2026-11-23) |

Stopped: reviewer recommended stopping in round 1

## Spec alignment (2026-11-23)

- spec: docs/superpowers/specs/2026-11-23-zeta-rh-verification-design.md
- anchor: 7a8eb970dac6252aab057836cf612ed1aba0850f
- in scope: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15, R16, R17, R18, R19, R20, R21, R22, R23, R24, R25
- out of scope: none

### Findings

| ID | Reviewer | Verdict | Reason | Amendment |
| --- | --- | --- | --- | --- |
| R5 | B | NOT-BUILT | The visible values are interval-based (Z over height_interval with outward ends, zfun.rs; Turing's eq. 2.1 now an outward-rounded 128-bit Interval with K = floor(hi)+1, turing.rs:168-194; g_M >= T via theta(T).hi <= n*pi rounded down, turing.rs:337-342), but the rule that a sign is used only when both bounds are finite and the interval excludes 0 lives in Interval::sign and the Gram-bracket rounding in theta.rs, neither of which is in this diff. | - R5 reviewed: the sign rule is `Interval::sign`/`excludes_zero` (finite bounds that exclude 0) and the Gram-bracket rounding is `theta::gram_bracket`, both on master from PR 1 (Tasks 2 and 4) and unchanged here; every θ, Gram, Z and truncation value this PR adds is an outward-rounded interval, and since 1ac5735 Turing's K comes from the outward-rounded 128-bit enclosure of eq. 2.1 (K = floor(hi) + 1), which supersedes this run's earlier `R5 reviewed:` answer about the f64 margin |
| R7 | both | NOT-BUILT | The diff only wires the self-check before verify (main.rs:2039, `self-check failed: ...`, exit 5) and prints its summary line; the 8-point/128-bit comparison, the intersection test and the EM/RS width limits are in zfun self_check code this diff does not contain. | - R7 reviewed: built in PR 2 (feat/zeta-core, Task 6) — `self_check` in zfun.rs on master evaluates both paths at 8 points in [200, 300] at 128 bits with the intersection and EM/RS width limits, each pinned by its own test; this PR only wires the call before `verify` with exit 5 |
| R8 | both | NOT-BUILT | The `# n a b` header, increasing order and 30-digit a-down/b-up rounding are built (main.rs:2175-2189), but no `--refine` flag, `# n a b t_n w_n` header, bisection stop rule, 15-digit t_n or 3-digit w_n exists in the diff. | - R8 reviewed: the `# n a b` table with 30-digit directed rounding is built here (Task 10); the `--refine` columns `t_n w_n` and the bisection stop rule are Task 11 in PR 4 per the plan's PR structure |
| R12 | both | NOT-BUILT | Looked for a `--refine` spacing histogram, Wigner surmise, largest w_n and KS distance; none exists in the diff. | - R12 reviewed: not in PR 3 by plan — the `--refine` spacing histogram, Wigner surmise, largest w_n and KS distance are Task 11 in PR 4 |
| R15 | both | NOT-BUILT | The diff touches no templated crate file and no tests/test_crate_uniformity.py, so nothing in it shows template rendering or a 13-crate uniformity pass. | - R15 reviewed: built in PR 1 — the crate's templated Makefile, rustfmt.toml, .config/nextest.toml, install_deps.sh, zeta-rs.yml and release-zeta-rs.yml are on master and pinned by tests/test_crate_uniformity.py; this PR changes no templated file |
| R16 | both | NOT-BUILT | The fixture (649 zeros, source URL, retrieval date) and the N = 2 / N = 3 assertions (exit 0, verified line with 29 and 649, row count, each zero inside its interval) are in tests/cli.rs:6077-6152, but the `--refine` N = 3 assertions (refined bracket containment, w_n < 1e-2, strictly narrower brackets) are absent. | - R16 reviewed: the fixture and the N = 2 / N = 3 checks are built here (Task 10); the `--refine` assertions at N = 3 are Task 11 in PR 4 |
| R17 | both | DIFFERS | Double root, missing change, irregular pattern after g_M, always-uncertain sign, uncertifiable g_-1, extra change and panicking worker are ZSource fakes run through verify, but the empty block list is driven through verify_with_bound with a hand-built TuringBound (verify.rs:5093), the sign conflict and NaN t are tested only on hand-built point vectors fed to points_in_range (verify.rs:5218), not as ZSource fakes yielding exit 6, and the [b_-1, b_M] restriction test uses arbitrary lo/hi rather than Turing's M. | - R17 -> `ZSource` fakes for a double root, a missing sign change, an irregular pattern after g_M, an always-uncertain sign and an uncertifiable g₋₁ bracket each yield exit 3 through `verify` with the specific reason asserted, and an empty block list yields `NoBlocks` (exit 3) through `verify_with_bound`; fakes for an extra sign change and a panicking worker each yield exit 6 through `verify`; a sign conflict at one t and a NaN t are tested as `PointsFault` at `isolate::merge_points`/`points_in_range`, the seam `verify` calls, and `PointsFault` maps to exit 6; tests at that seam assert that L counts only points in the given [lo, hi] (`verify` passes [b₋₁, b_M] for Turing's M) and counts a duplicated identical (t, sign) once — the three cases moved off `verify` are unreachable through it with a consistent `ZSource`: every point is sampled at a finite f64 t, one t certified twice by one source cannot take two signs, and `choose_m` only returns an M with g_M ≥ 168π, so `certify_gram_points` always holds g₋₁ and g_M and `plan_blocks` yields at least one block; this finding recurred across three runs, so the text now matches what was built |
| R18 | both | NOT-BUILT | No proptest over Interval operations at 4x precision up to \|x\| = 1e9 or the cos/sin radius rule is in the diff; the added proptests cover Complex ops (\|x\| <= 1e6, 1000-bit reference), z_over enclosures and RS/EM agreement. | - R18 reviewed: built in PR 1 — the Interval proptests (interval.rs on master, `proptest!` block: inputs to \|x\| = 10⁹, reference at 4p + 100 bits, `narrow_cos_sin_enclose` with zero-width inputs) are on master; the proptests in this diff are the new Complex and Z-path ones |
| R21 | both | NOT-BUILT | No `progress: <done>/<total> Gram blocks, t = <t>` output or throttle exists in the diff. | - R21 reviewed: not in PR 3 by plan — progress lines and their throttle are Task 12 in PR 4 |
| R24 | both | NOT-BUILT | run() takes no configuration and fixes VerifyConfig::default(), RealZ, DirStore and PoolPolicy::Parallel, and run_with plus skip_self_check are #[cfg(test)], but VerifyConfig's private fields and new() validation are not in this diff and run() wires no progress throttle. | - R24 reviewed: `VerifyConfig` with private fields and `new()` validation was built in PR 1/2 (config.rs on master); `run()`, `run_with` and the cfg(test) self-check skip are built here; the progress throttle is Task 12 in PR 4 |

### Reviewed

- V1 reviewed: measured 2026-11-23 over all 21,136,123 consecutive zero pairs below 10⁷ (f64 C Riemann–Siegel with C₀–C₂ scan, every candidate confirmed with mpmath `siegelz` at 30 digits; decade counts 29, 649, 10,142, 138,069, 1,747,146 and 21,136,125 reproduced; the first Rosser failure at g_13999525 and Lehmer's pair reproduced): minimum ratio 12.05 at the pair 4316832.467101349 and 4316832.469424753 (peak |Z| 1.6163·10⁻⁵ against 1.3410·10⁻⁶); next smallest 18.83; C₀ only stands, with a 1.2× margin over the threshold.
- V2 reviewed: pinned 2026-11-23: Gabcke 1979 Satz 3.2.2(b) gives |R₀| < 0.127·t^(−3/4) for t ≥ 200 in t (numerically near-tight at 0.1205 on [200, 260]), with C₁–C₄ bounds 0.053·t^(−5/4), 0.011·t^(−7/4), 0.031·t^(−9/4), 0.017·t^(−11/4); Euler–Maclaurin remainder per Johansson 2015 Theorem 1 and Brent 1979 p. 1363; θ via DLMF 5.11 Stirling with a shift of 10, since Gabcke's θ bound needs t ≥ 10 and g₋₁ ≈ 9.667; the first Rosser failure is the block [g_13999525, g_13999527); Lehmer's pair is zeros 6709 and 6710 at 7005.062866175 and 7005.100564674.
- V8 reviewed: measured 2026-11-23 on a 209-line `rug` prototype: warm debug `cargo test` baseline 4.4 s, real cargo-mutants 27.1.0 at about 4.6 s per mutant; projected first-PR `mutation-rs` time for about 500 mutants is 53–110 minutes, so the fallback applies: zeta's `.cargo/mutants.toml` skips the end-to-end tests by name and their lines are covered by unit tests; the plan also splits the crate across several PRs so no PR mutates the whole crate.
- R1 reviewed: deliberate interim stub — the plan's PR structure has PR 1 print `RH NOT verified: zeta is under construction` and exit 3 for every input so no build implies success; plan Task 6 (PR 2 (feat/zeta-core)) adds the 2..=7 range check with exit 1
- R2 reviewed: not in PR 1 by plan — built by Task 10 in PR 3 (feat/zeta-verify)
- R4 reviewed: not in PR 1 by plan — built by Task 9 in PR 3 (feat/zeta-verify)
- R5 reviewed: interval and θ halves built here (Tasks 2, 4); the Z and truncation-bound half is Task 5 in PR 2 (feat/zeta-core)
- R6 reviewed: not in PR 1 by plan — built by Task 5 in PR 2 (feat/zeta-core)
- R7 reviewed: not in PR 1 by plan — built by Task 5 (self-check) and Task 6 (exit 5) in PR 2 (feat/zeta-core)
- R8 reviewed: not in PR 1 by plan — built by Task 10 in PR 3 (feat/zeta-verify) and Task 11 (--refine columns) in PR 4 (feat/zeta-refine-cli)
- R9 reviewed: not in PR 1 by plan — built by Task 10 in PR 3 (feat/zeta-verify)
- R10 reviewed: not in PR 1 by plan — built by Task 9 in PR 3 (feat/zeta-verify)
- R12 reviewed: not in PR 1 by plan — built by Task 11 in PR 4 (feat/zeta-refine-cli)
- R13 reviewed: not in PR 1 by plan — built by Task 6 in PR 2 (feat/zeta-core)
- R14 reviewed: not in PR 1 by plan — built by Task 6 in PR 2 (feat/zeta-core)
- R16 reviewed: not in PR 1 by plan — built by Task 10 in PR 3 (feat/zeta-verify)
- R17 reviewed: not in PR 1 by plan — ZSource is Task 5 in PR 2 (feat/zeta-core), the fakes and verdicts Task 9 in PR 3 (feat/zeta-verify)
- R19 reviewed: not in PR 1 by plan — built by Task 8 in PR 3 (feat/zeta-verify)
- R20 reviewed: not in PR 1 by plan — built by Task 10 in PR 3 (feat/zeta-verify)
- R21 reviewed: not in PR 1 by plan — built by Task 12 in PR 4 (feat/zeta-refine-cli)
- R22 reviewed: the θ-sign certificate is built here (Task 4); Z's sign over the bracket, inserting b_n and block merging are Tasks 7 and 8 in PR 3 (feat/zeta-verify)
- R23 reviewed: not in PR 1 by plan — built by Task 7 in PR 3 (feat/zeta-verify)
- R24 reviewed: VerifyConfig and its validation are built here (Task 3); run() defaults and run_with are Tasks 6 and 10 in PR 2 (feat/zeta-core) and PR 3 (feat/zeta-verify)
- R25 reviewed: not in PR 1 by plan — built by Task 7 in PR 3 (feat/zeta-verify)
- R1 reviewed: deliberate interim per the plan's PR structure — PR 2 (feat/zeta-core) adds the 2..=7 range check with exit 1 (Task 6) and, for a valid N, runs the self-check then prints `RH NOT verified up to <T>: zero isolation is not implemented yet` with exit 3 so no build implies success; the computation up to T = 10^N is Task 10 in PR 3 (feat/zeta-verify)
- R2 reviewed: not in PR 2 by plan — built by Task 10 in PR 3 (feat/zeta-verify)
- R4 reviewed: not in PR 2 by plan — built by Task 9 in PR 3 (feat/zeta-verify)
- R8 reviewed: not in PR 2 by plan — built by Task 10 in PR 3 (feat/zeta-verify) and Task 11 (--refine columns) in PR 4 (feat/zeta-refine-cli)
- R9 reviewed: not in PR 2 by plan — built by Task 10 in PR 3 (feat/zeta-verify); exit 4 on stdout/stderr write failure here is the CLI half only
- R10 reviewed: not in PR 2 by plan — built by Task 9 in PR 3 (feat/zeta-verify)
- R11 reviewed: not in PR 2 by plan — the parallel isolation it constrains is Task 9 in PR 3 (feat/zeta-verify)
- R12 reviewed: not in PR 2 by plan — built by Task 11 in PR 4 (feat/zeta-refine-cli)
- R15 reviewed: built by Task 1 in PR 1 (feat/zeta-foundation), already merged; this diff touches no template or rendered crate file, so there is nothing for it to show
- R16 reviewed: not in PR 2 by plan — built by Task 10 in PR 3 (feat/zeta-verify); the exit-3 assertions for N=2 and N=3 pin PR 2's interim behaviour
- R17 reviewed: the ZSource trait is built here (Task 5); the verifier, its fakes and their exit 3/6 verdicts are Task 9 in PR 3 (feat/zeta-verify)
- R18 reviewed: built by Task 2 in PR 1 (feat/zeta-foundation), already merged; interval.rs is unchanged by PR 2
- R19 reviewed: not in PR 2 by plan — built by Task 8 in PR 3 (feat/zeta-verify)
- R20 reviewed: run_with here injects only the self-check (Task 6); the depth-cap and Gabcke ×10⁶ negative controls are Task 10 in PR 3 (feat/zeta-verify)
- R21 reviewed: not in PR 2 by plan — built by Task 12 in PR 4 (feat/zeta-refine-cli)
- R22 reviewed: the θ-sign certificate was built in PR 1 (Task 4); Z's sign over [b_n, c_n], inserting b_n and block merging are Tasks 7 and 8 in PR 3 (feat/zeta-verify)
- R23 reviewed: not in PR 2 by plan — built by Task 7 in PR 3 (feat/zeta-verify)
- R24 reviewed: VerifyConfig and its validation were built in PR 1 (Task 3); run() using the defaults with run_with under cfg(test) is built here (Task 6); the writer, pool and throttle wiring are Tasks 9, 10 and 12 in PR 3 (feat/zeta-verify) and PR 4 (feat/zeta-refine-cli)
- R25 reviewed: not in PR 2 by plan — built by Task 7 in PR 3 (feat/zeta-verify)
- R5 reviewed: K is an integer block count, not an enclosure the verdict reads a sign from; `blocks_needed` (turing.rs:183) evaluates Trudgian's eq. 2.1 in f64 and rounds up after adding `ROUNDING_MARGIN` = 10⁻⁹, and the f64 expression's absolute error, measured 2026-11-23 against a 50-digit Decimal evaluation at g from 10 to 2·10⁷, is at most 4.9·10⁻¹⁶ (right side at most 2.63), so the margin exceeds the rounding error by over 10⁶× and K is never below the exact bound; every Gram, θ and Z value in this PR stays interval-based
- R7 reviewed: built in PR 2 (feat/zeta-core, Task 6) — `self_check` in zfun.rs on master evaluates both paths at 8 points in [200, 300] with the intersection and EM/RS width limits, each pinned by its own test; this PR only wires the call before `verify` with exit 5
- R8 reviewed: the `# n a b` table with 30-digit directed rounding is built here (Task 10); the `--refine` columns `t_n w_n` and the bisection stop rule are Task 11 in PR 4 per the plan's PR structure
- R12 reviewed: not in PR 3 by plan — the `--refine` spacing histogram, Wigner surmise, largest w_n and KS distance are Task 11 in PR 4
- R15 reviewed: built in PR 1 — the crate's templated Makefile, rustfmt.toml, .config/nextest.toml, install_deps.sh, zeta-rs.yml and release-zeta-rs.yml are on master and pinned by tests/test_crate_uniformity.py; this PR changes no templated file
- R16 reviewed: the fixture and the N = 2 / N = 3 checks are built here (Task 10); the `--refine` assertions at N = 3 are Task 11 in PR 4
- R17 reviewed: with a consistent `ZSource` every point is sampled at an exact finite f64 t, the sampler never yields a NaN height, and one t certified twice by the same source cannot take two signs, so the sign-conflict and NaN-t faults are unreachable through `verify`; they are tested at the seam `verify` calls, `points_in_range`/`sort_and_merge` (verify.rs:308-327, the same call at verify.rs:474 with [b₋₁, b_M] from Turing's M), and their mapping to `Fault::Points` exits 6; the other ten fakes run through `verify` with their reasons asserted
- R18 reviewed: built in PR 1 — the Interval proptests (interval.rs on master, `proptest!` block: inputs to |x| = 10⁹, reference at 4p + 100 bits, `narrow_cos_sin_enclose` with zero-width inputs) are on master; the proptests in this diff are the new Complex and Z-path ones
- R21 reviewed: not in PR 3 by plan — progress lines and their throttle are Task 12 in PR 4
- R24 reviewed: `VerifyConfig` with private fields and `new()` validation was built in PR 1/2 (config.rs on master); `run()`, `run_with` and the cfg(test) self-check skip are built here; the progress throttle is Task 12 in PR 4
- R5 reviewed: the sign rule is `Interval::sign`/`excludes_zero` (finite bounds that exclude 0) and the Gram-bracket rounding is `theta::gram_bracket`, both on master from PR 1 (Tasks 2 and 4) and unchanged here; every θ, Gram, Z and truncation value this PR adds is an outward-rounded interval, and since 1ac5735 Turing's K comes from the outward-rounded 128-bit enclosure of eq. 2.1 (K = floor(hi) + 1), which supersedes this run's earlier `R5 reviewed:` answer about the f64 margin
- R7 reviewed: built in PR 2 (feat/zeta-core, Task 6) — `self_check` in zfun.rs on master evaluates both paths at 8 points in [200, 300] at 128 bits with the intersection and EM/RS width limits, each pinned by its own test; this PR only wires the call before `verify` with exit 5
- R8 reviewed: the `# n a b` table with 30-digit directed rounding is built here (Task 10); the `--refine` columns `t_n w_n` and the bisection stop rule are Task 11 in PR 4 per the plan's PR structure
- R12 reviewed: not in PR 3 by plan — the `--refine` spacing histogram, Wigner surmise, largest w_n and KS distance are Task 11 in PR 4
- R15 reviewed: built in PR 1 — the crate's templated Makefile, rustfmt.toml, .config/nextest.toml, install_deps.sh, zeta-rs.yml and release-zeta-rs.yml are on master and pinned by tests/test_crate_uniformity.py; this PR changes no templated file
- R16 reviewed: the fixture and the N = 2 / N = 3 checks are built here (Task 10); the `--refine` assertions at N = 3 are Task 11 in PR 4
- R18 reviewed: built in PR 1 — the Interval proptests (interval.rs on master, `proptest!` block: inputs to |x| = 10⁹, reference at 4p + 100 bits, `narrow_cos_sin_enclose` with zero-width inputs) are on master; the proptests in this diff are the new Complex and Z-path ones
- R21 reviewed: not in PR 3 by plan — progress lines and their throttle are Task 12 in PR 4
- R24 reviewed: `VerifyConfig` with private fields and `new()` validation was built in PR 1/2 (config.rs on master); `run()`, `run_with` and the cfg(test) self-check skip are built here; the progress throttle is Task 12 in PR 4

### Verifications

- V1: Recorded in the plan (Pre-plan measurements): minimum ratio 12.05 at 4316832.467; C0 only stands.
- V2: Recorded in the plan appendix (formulas pinned from primary sources).
- V3: Partial (PR 3 orchestrator release runs on claude): zeta 5 verifies 138,069 zeros, exit 0, 6.3 s wall, 280 s CPU, 48 threads; N = 6 and 7, peak RSS, retry counts and precision histogram not yet recorded.
- V4: no evidence recorded
- V5: no evidence recorded
- V6: no evidence recorded
- V7: no evidence recorded
- V8: Recorded in the plan: baseline 4.4 s, 53-110 min projection; PR 3 adds the e2e_ skip to zeta's .cargo/mutants.toml and the crate is split across PRs.
