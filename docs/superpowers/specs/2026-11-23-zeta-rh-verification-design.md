# zeta: certified verification of the Riemann Hypothesis up to height T

- **Date:** 2026-11-23
- **Sub-project:** `zeta/` (new), Rust only: crate `zeta/zeta-rs`, binary `zeta`
- **Revised:** 2026-11-23, after Multi-Lens Review round 1 (see the review section at the end)

## Summary

`zeta N` proves a finite-range theorem: every nontrivial zero ρ of the Riemann zeta
function with 0 < Im ρ ≤ T = 10^N lies on the critical line Re s = 1/2 and is simple.
It also reports how many such zeros there are. Every number the proof depends on is an
interval enclosure computed with directed rounding, so the claim holds even though the
computation is done in floating point.

This is the same kind of result as `goldbach/`: a bound in, exhaustive work, counts and
witnesses out. It is evidence for the Riemann Hypothesis, never a proof of it. The output
must never say "RH holds"; it says "RH verified up to T".

With `--refine`, the CLI also locates each zero to 10⁻¹² and shows the statistical
pattern of the gaps between consecutive zeros against the GUE prediction from random
matrix theory (Montgomery–Odlyzko).

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
  |ζ(1/2 + it)|. A sign change of Z between a and b proves at least one zero of ζ on the
  critical line with imaginary part in (a, b).
- **Riemann–Siegel theta.** θ(t) = Im ln Γ(1/4 + it/2) − (t/2) ln π, computed from the
  Stirling series with an explicit remainder bound. θ is not monotone below t ≈ 6.29 and
  dips to about −3.53 near t = 2π.
- **Gram points.** For t > 2π, θ is increasing and g_n is the unique t > 2π with θ(g_n)
  = nπ, for n ≥ −1 (g₋₁ ≈ 9.67). Gram point g_n is _good_ when (−1)^n Z(g_n) > 0. A _Gram
  block_ is an interval [g_j, g_k) between consecutive good Gram points; it contains k − j
  Gram intervals.
- **Rosser's rule.** A Gram block of k − j intervals usually contains at least k − j
  zeros. It is known to fail occasionally, so it is used only as a search guide, never as a
  step in the proof.
- **Counting function.** N(T) is the number of zeros of ζ with 0 < Im ρ ≤ T, counted with
  multiplicity, in the whole critical strip whether on the line or not.
- **Turing's method.** At a good Gram point g_M, the sign pattern of Z over the following
  Gram blocks, combined with Trudgian's bound |∫_{t₁}^{t₂} S(t) dt| ≤ 2.067 + 0.059 ln t₂,
  which holds for t₂ > t₁ ≥ 168π ≈ 527.8 (Trudgian 2011), proves N(g_M) ≤ M + 1. Turing's
  method is therefore applied only at g_M ≥ 168π.

## The proof

1. **Choose M.** M is the smallest index with g_M ≥ max(T, 168π), g_M a good Gram point
   whose sign is certified, and Turing's method establishing N(g_M) ≤ M + 1 at that same
   g_M. Successive good Gram points are tried, at most 10, before giving up. For N = 2 this
   means M sits just above 168π, not just above 100; the claim is still printed only for T.
2. **Build one sample sequence.** Over (g₋₁, g_M], the CLI builds a single, globally
   merged, strictly increasing sequence of sample points t_i, each carrying a certified sign
   of Z(t_i). Gram points, subdivision points from every block, and points added by
   neighbour searches are all inserted into this one sequence. Searches add points; they
   never add intervals. Sample points Turing evaluates beyond g_M are not part of the
   sequence.
3. **Count L.** L is the number of sign alternations between consecutive points of that
   sequence. Each alternation is a sign change of Z on a distinct open interval, so it proves
   a distinct zero on the line. Because L is counted on one sequence, one zero can never be
   counted twice.
4. **Compare.** L ≤ N(g_M) ≤ M + 1 always holds for a correct implementation.
   - If L = M + 1, every zero up to g_M is on the line, and since N counts multiplicity,
     each is simple. The claim is then printed for T.
   - If L < M + 1, nothing is claimed. The CLI names the Gram blocks it could not resolve
     and exits 3.
   - If L > M + 1, the implementation is wrong (the inequality cannot fail). The CLI prints
     `internal error: L > M+1` and exits 6. It is never reported as merely "not verified".

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
  are added by widening. A sign is certified exactly when the final enclosure excludes 0.
  Cost is about 2–4× point arithmetic. No new dependency, and `unsafe_code = "forbid"`
  holds.
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

The two paths share `interval.rs` and `theta.rs`, so comparing them is a canary for formula
and build faults, not a proof of independence. An error in θ would move both together.

## Components

Modules in `zeta/zeta-rs/src/`, each testable on its own:

| Module        | Responsibility                                                                                                                                                                                                                                                                                                                                                                                                       | Depends on          |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| `interval.rs` | `Interval { lo, hi }` over `rug::Float`: `+ − × ÷`, `sqrt`, `ln`, `exp`, `cos`, `sin`, `widen(ε)`, `excludes_zero()`, `sign() -> Option<Sign>`. `lo` is rounded toward −∞ and `hi` toward +∞. For `cos`/`sin`: an argument wider than π returns [−1, 1]; otherwise f is evaluated at the midpoint twice, once rounded down and once rounded up, and the result is widened by the argument's half-width plus one ulp. | `rug`               |
| `theta.rs`    | θ(t) enclosure from the Stirling series plus remainder bound; Gram point g_n by interval Newton iteration on θ(g) = nπ, restricted to t > 2π.                                                                                                                                                                                                                                                                        | `interval`          |
| `zfun.rs`     | `riemann_siegel(t)`, `euler_maclaurin(t)` and `z(t)`, which dispatches on the lower bound of t.                                                                                                                                                                                                                                                                                                                      | `interval`, `theta` |
| `isolate.rs`  | One Gram block in, certified sample points out. Uses Rosser's expected count to decide when to subdivide (maximum depth 40) and raises precision when a sign is uncertain.                                                                                                                                                                                                                                           | `zfun`              |
| `turing.rs`   | Establishes N(g_M) ≤ M + 1 from the sign pattern after g_M and Trudgian's bound; refuses any g_M < 168π.                                                                                                                                                                                                                                                                                                             | `zfun`, `theta`     |
| `verify.rs`   | Orchestration: block list, parallel isolation in chunks, merging all sample points into one sequence, counting L, comparing with M + 1, `Verdict`. Generic over a `ZSource` trait so tests can inject fakes.                                                                                                                                                                                                         | all above           |
| `spacing.rs`  | `--refine` only: bisection of each zero's interval to 10⁻¹², normalised spacings, histogram against the Wigner surmise, KS distance.                                                                                                                                                                                                                                                                                 | `zfun`              |
| `main.rs`     | clap CLI, `run()` and `prompt_n()` in goldbach's shape, thin `main` excluded from tarpaulin.                                                                                                                                                                                                                                                                                                                         | `verify`, `spacing` |

## Parallelism

Gram blocks are independent, so isolation runs on a rayon pool built with
`ThreadPoolBuilder::build`, which returns `Err` rather than panicking when a thread cannot
be spawned. Blocks are processed in chunks of 10,000: a parallel pass over the chunk, then
an ordered merge of that chunk's sample points into the global sequence, then the next
chunk. A neighbour search that reaches past a chunk edge adds its points to the global
sequence like any other. Memory is bounded by the chunk size, not by N. If the pool cannot
be built, the CLI prints `Parallel mode unavailable ({error}); falling back to serial.`
(the descartes-rs wording) and processes the same blocks serially. The output is
byte-identical either way. The global pool and plain `par_iter` are not used.

## CLI

```
zeta [N] [--refine]
```

- `N` is 2 to 7, giving T = 10^N. Missing N prompts for it, as `goldbach` does.
- `--refine` adds a refined zero value per line and the spacing histogram.
- N > 6 prints, before starting: `Warning: N=7 writes about 1.5 GB (about 2 GB with --refine) and may take many hours.`
- After each chunk, stderr shows `progress: <done>/<total> Gram blocks, t = <t>` so a slow
  run can be told from a hung one.

Approximate work (estimates, to be replaced by V3's measurements): N = 3 under 1 s, N = 5
about a minute, N = 6 tens of minutes, N = 7 many hours, all on the 48-thread `claude`.

### Output files

`zeta_1eN.txt` is written only for a verified run. Its first line is a header and each
following line is one zero with 0 < t ≤ T, in order:

```
# n a b            (default)
# n a b t_n        (with --refine)
```

- `n a b` means exactly one zero lies on the line with imaginary part in (a, b). `a` and `b`
  are printed with 30 significant digits, `a` rounded down and `b` rounded up, so the
  printed interval contains the certified one.
- With `--refine`, `t_n` satisfies |t_n − γ_n| < 10⁻¹² and is printed with 12 decimals.

Zeros in (T, g_M] are proven but not listed. The file is first written to a temporary file
in the same directory and renamed to `zeta_1eN.txt` only when the verdict is verified, so
a file by that name always lists a complete, proven set.

On exit 3, the certified intervals found so far are kept as `zeta_1eN.partial.txt`, with
the header `# NOT VERIFIED: partial list of certified zeros on the line`, so a long run's
work is not lost. That file never carries the proof name. On exits 4, 5 and 6 no file is
kept.

### Standard output

Verified (exit 0):

```
Self-check: Riemann–Siegel and Euler–Maclaurin agree on [200, 300] (8 points)
Turing bound: N(g_M) <= M+1 established at g_M = <value>
Isolating zeros in 0 < t <= 1000 (<k> threads)...

RH verified: all 649 nontrivial zeros with 0 < Im s <= 1000 lie on Re s = 1/2 and are simple
Gram blocks: <b>   Rosser exceptions: <r>   max precision: <p> bits
Saved zeta_1e3.txt
Elapsed: <s> s
```

Not verified (exit 3):

```
RH NOT verified up to 1000: 647 of 649 zeros isolated
Uncertified Gram blocks: [g_412, g_414]  (<reason>)
No claim is made for this range.
Saved partial list: zeta_1e3.partial.txt
```

With `--refine`, a histogram of normalised spacings δ_n = (t_{n+1} − t_n)·ln(t_n/2π)/2π
over s ∈ [0, 3] in 0.15-wide bins, the Wigner surmise p(s) = (32/π²) s² e^(−4s²/π)
beside each bin, and the KS distance. The output states that the Wigner surmise
approximates the exact GUE spacing law to within about 1%, and that independent random
points (Poisson) would instead peak at s = 0.

### Exit codes

The Rust CLIs so far use 0, 1 and clap's 2. zeta adds 3–6 because "not verified" must be
distinguishable from an error; `zeta-rs/CLAUDE.md` documents this as zeta's own convention.

| Code | Meaning                                                                      |
| ---- | ---------------------------------------------------------------------------- |
| 0    | Verified                                                                     |
| 1    | Input error, N out of range, or end of input at the prompt                   |
| 2    | clap usage error                                                             |
| 3    | Computed, not verified (uncertified blocks, or Turing bound not established) |
| 4    | Output write failed                                                          |
| 5    | Runtime self-check failed                                                    |
| 6    | Internal error: L > M + 1                                                    |

## Error handling

The rule throughout: anything uncertain becomes "not verified", never "verified".

- **Uncertain sign of Z(t).** Precision steps 64 → 128 → 256 → 512 bits. When the enclosure
  width is dominated by a truncation bound, more bits cannot help, so the sample point is
  moved instead. A sign still uncertain after that is recorded as uncertain and the point
  is left out of the sequence.
- **Fewer alternations than Rosser's rule expects.** The block is subdivided recursively up
  to depth 40; on a Rosser failure the neighbouring blocks are searched too, adding points
  to the same global sequence. Unresolved blocks are reported and the run exits 3.
- **A zero straddling T.** The interval containing T is bisected until the zero lies on one
  side, for at most 60 bisections. If Z(T) stays uncertain after that, the run exits 3; it
  never guesses which side the zero is on.
- **Gram point Newton iteration fails to converge, or leaves t > 2π.** The block is
  uncertified.
- **Turing's method fails at g_M.** Up to 10 further good Gram points are tried, then the
  run exits 3 with `Turing bound not established`.
- **Self-check on [200, 300].** At 8 points, both Z paths are evaluated at 128 bits. The check
  fails if any pair of enclosures does not intersect, or if either enclosure is wider than
  10⁻¹⁰. On failure: stderr `self-check failed`, exit 5, before any verdict.
- **L > M + 1.** Exit 6, `internal error: L > M+1`.
- **End of input at the prompt.** As goldbach: a newline on stdout, then
  `Error: no input; pass SIZE as an argument (e.g. zeta 3).` on stderr, exit 1.

## Gate before planning: the C₀ floor at N = 7

With only the C₀ correction, Gabcke's error at t = 10⁷ is about 0.127·(10⁷)^(−3/4) ≈ 7·10⁻⁷.
More precision cannot shrink it. If any consecutive zero pair below 10⁷ has max |Z| between
its zeros below that floor, no sample point certifies the pair and N = 7 can never verify.
Measured so far: Lehmer's pair near 7005.06 peaks at |Z| = 0.00397 against a floor of
1.66·10⁻⁴, a 24× margin (mpmath `siegelz`, 30 digits).

Before the implementation plan is written, a pilot scan settles this (V1). The
smallest-gap zero pairs below 10⁷ are found and the ratio of max |Z| between them to
0.127·t^(−3/4) is computed. A minimum ratio of 10 or more keeps C₀ only. Otherwise the spec
is amended to add the C₁–C₄ corrections with their published error bound before planning.

## Testing

Ground truth comes from outside the crate:

1. **Odlyzko's zero table.** The first 10,142 zeros (all zeros up to 10⁴, accuracy about
   3·10⁻⁹) are committed as `zeta/zeta-rs/tests/fixtures/odlyzko_1e4.txt`, with the
   source URL and retrieval date in its header.
2. **Published counts.** N(10²) = 29, N(10³) = 649, N(10⁴) = 10,142, N(10⁵) = 138,069,
   N(10⁶) = 1,747,146, N(10⁷) = 21,136,125.
3. **Two Z paths compared on [200, 300]**, as a canary.

### Test tiers

- **Fast tier**, run by `make test` and the coverage job: N = 2 and N = 3 end to end, unit
  and property tests, all fakes, and the real-input negative controls. Each test stays well
  inside nextest's 45 s bound.
- **Release tier**, `#[ignore]` tests run in release mode by a CI step: the N = 4 count and
  Odlyzko containment, N = 4 `--refine`, and Lehmer's pair.

### Tests

- **Verdict end to end.** For N = 2 and N = 3, the process exits 0, stdout contains the
  `RH verified` line with 29 and 649, the file has that many zero lines, and the nth Odlyzko
  zero lies in the nth interval. The release tier does the same for N = 4 (10,142) and checks
  `--refine` values against the table to within 10⁻⁸.
- **Fakes that lower L** (via `ZSource`): a double root (sign touch without change), a
  missing sign change, an irregular Turing pattern, an always-uncertain sign, and an empty
  block list. Each yields exit 3, and the test asserts the specific reason or named block.
- **Fakes that would raise L**: a duplicated or overlapping interval, an extra spurious
  sign change, and a Turing success at a different index from the one counted. The duplicate
  and different-index cases still count correctly by construction. The extra sign change
  yields exit 6.
- **Real-input negative controls**, with the real Z paths and a test-only configuration:
  Gabcke's bound multiplied by 10⁶; precision capped at 64 bits with sample-point moving off;
  and subdivision depth capped at 1 on Lehmer's pair. Each yields exit 3 and no `zeta_1eN.txt`.
- **Turing range.** `turing.rs` refuses g_M < 168π, and `zeta 2` chooses g_M ≥ 168π.
- **Interval properties (proptest).** Inputs are sampled inside random intervals. Every
  operation's enclosure contains the value computed at four times the precision with
  outward rounding. Enclosure width shrinks as precision grows. A zero-width input to `cos`
  and `sin` still yields an enclosure that contains the high-precision value.
- **Theta and Gram points.** θ(g_n) encloses nπ; g_n is strictly increasing; g₋₁ > 2π;
  Newton never returns a root at or below 2π.
- **Parallel versus serial.** With the pool forced to fail, `zeta_1e3.txt` is byte-identical
  to the parallel run.
- **CLI.** `run()` is tested for exits 0, 1, 3, 4, 5 and 6, end of input at the prompt, N out
  of range, the progress line and the partial-file name. BATS failure-mode tests cover the
  binary per the repo DoD. `scripts/cli_contract.py` is not used because it is Python-only.
- **Bench.** criterion bench of `z(t)` at t = 10⁴ and t = 10⁶.

## Repo integration

- All crate files rendered from `scripts/crate_templates/` (Makefile, `rustfmt.toml`,
  `.config/nextest.toml`, `install_deps.sh`, `zeta-rs.yml`, `release-zeta-rs.yml`). The
  crate count becomes 13 everywhere it is stated, including the literal `CRATES` list in
  `scripts/render_crate_files.py` and the hard-coded 12 in `tests/test_crate_uniformity.py`.
- The release-tier CI step is added through the crate template, so every crate gets the same
  step and crates with no `#[ignore]` tests run nothing.
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
- **R4.** L is the number of sign alternations between consecutive points of one globally merged, strictly increasing sequence of certified-sign sample points over (g₋₁, g_M], where M is the index at which Turing's method established N(g_M) ≤ M + 1; sample points beyond g_M are excluded. The verdict is verified only when L = M + 1; L < M + 1 prints `RH NOT verified up to <T>` and exits 3; L > M + 1 prints `internal error: L > M+1` and exits 6.
- **R5.** Every value the verdict depends on (θ, Gram points, Z, truncation bounds) is computed as an interval whose lower bound is rounded toward −∞ and upper bound toward +∞, and a sign is used only when the interval excludes 0.
- **R6.** Z(t) uses Riemann–Siegel with Gabcke's remainder bound only when the lower bound of the t enclosure is ≥ 200, and Euler–Maclaurin with its remainder bound otherwise; every truncation bound's validity condition is checked against the worst-case end of its argument's enclosure.
- **R7.** Before any verdict, the CLI evaluates both Z paths at 128 bits at 8 points in [200, 300]; if any pair of enclosures fails to intersect or either enclosure is wider than 10⁻¹⁰, it prints `self-check failed` to stderr and exits 5.
- **R8.** `zeta_1eN.txt` starts with the header line `# n a b` (or `# n a b t_n` with `--refine`), followed by one line per zero with 0 < t ≤ T in increasing order, where a is rounded down and b rounded up to 30 significant digits and t_n has 12 decimals.
- **R9.** `zeta_1eN.txt` is written to a temporary path in the same directory and renamed only on a verified verdict; on exit 3 the certified intervals are kept as `zeta_1eN.partial.txt` whose first line is `# NOT VERIFIED: partial list of certified zeros on the line`; on exits 4, 5 and 6 no output file is kept; a write failure exits 4.
- **R10.** Zero isolation runs on a rayon pool built with `ThreadPoolBuilder::build` over chunks of 10,000 Gram blocks; if the build fails, stderr shows `Parallel mode unavailable ({error}); falling back to serial.`, and the output file is byte-identical to the parallel run.
- **R11.** The global rayon pool (`rayon::current_num_threads`, `par_iter` outside the built pool) is not used.
- **R12.** `--refine` adds a spacing histogram over s ∈ [0, 3] in 0.15-wide bins with the Wigner surmise p(s) = (32/π²) s² e^(−4s²/π) beside each bin and the KS distance.
- **R13.** End of input at the N prompt prints a newline to stdout, `Error: no input; pass SIZE as an argument (e.g. zeta 3).` to stderr, and exits 1.
- **R14.** N = 7 prints `Warning: N=7 writes about 1.5 GB (about 2 GB with --refine) and may take many hours.` before computation starts.
- **R15.** The crate is Rust only (`zeta/zeta-rs`), with no Python sub-project, and every templated file is rendered from `scripts/crate_templates/` so `tests/test_crate_uniformity.py` passes for 13 crates.
- **R16.** `zeta/zeta-rs/tests/fixtures/odlyzko_1e4.txt` holds the first 10,142 zeros with its source URL and retrieval date in a header; fast-tier tests assert, for N = 2 and N = 3, exit 0, the `RH verified` line with counts 29 and 649, that many zero lines, and each table zero inside its interval; a release-tier `#[ignore]` test asserts the same for N = 4 with 10,142.
- **R17.** `ZSource` fakes for a double root, a missing sign change, an irregular Turing pattern, an always-uncertain sign and an empty block list each yield exit 3 with the specific reason asserted; fakes for a duplicated interval and for a Turing success at a different index still count correctly; a fake with an extra sign change yields exit 6.
- **R18.** Proptest samples inputs inside random intervals and asserts that every `Interval` operation's enclosure contains the value computed at four times the working precision with outward rounding, including zero-width inputs to `cos` and `sin`.
- **R19.** Turing's method is applied only at g_M ≥ 168π: M is the smallest index with g_M ≥ max(T, 168π), and `turing.rs` refuses any smaller g_M.
- **R20.** Real-input negative controls with a test-only configuration (Gabcke's bound × 10⁶; precision capped at 64 bits with sample-point moving off; subdivision depth 1 on Lehmer's pair) each yield exit 3 and no `zeta_1eN.txt`.
- **R21.** After each chunk, stderr shows `progress: <done>/<total> Gram blocks, t = <t>`.
- **R22.** Gram points are computed only for t > 2π, and Newton iteration that leaves t > 2π marks the block uncertified.
- **R23.** The interval containing T is bisected at most 60 times; if the zero's side of T is still uncertain, the run exits 3.
- **V1.** Before the implementation plan is written, run a pilot scan of the smallest-gap zero pairs below 10⁷ and record the minimum ratio of max |Z| between them to 0.127·t^(−3/4); a ratio below 10 requires an amendment adding C₁–C₄ corrections before planning.
- **V2.** Before implementation, pin against the primary sources and record in the plan: the exact form, constant and validity range of Gabcke's bound; the Euler–Maclaurin and Stirling remainder bounds used; the Turing inequality with Trudgian's constants and validity range; the Gram index of the first Rosser-rule failure; and the location of Lehmer's pair.
- **V3.** Run N = 5, 6 and 7 on `claude`; each verified count equals the published N(10^N) (138,069; 1,747,146; 21,136,125); record wall-clock time, peak RSS, the number of uncertified blocks before retry, and the precision histogram.
- **V4.** The N = 7 run passes through the first Rosser-rule failure pinned in V2 and still exits 0.
- **V5.** Run `zeta 3 --refine` and confirm the histogram's first bin is near empty and the KS distance to the Wigner surmise is below 0.1.
- **V6.** Time the fast tier under tarpaulin on `ubuntu-latest`; no single test exceeds 30 s.
- **N1.** The CLI never claims RH in general; no code path prints a verification claim beyond T.
- **N2.** No new native library beyond GMP and MPFR, and no `unsafe` code in the crate.
- **N3.** No arbitrary-range mode (`--from`/`--to`) in this spec.
- **N4.** No reconstruction of π(x) from the explicit formula in this spec.
- **N5.** No `--check` re-verification mode in this spec.

## Multi-Lens Review

Round 1 reviewed at commit: `b27bae1` (Step 7 self-review commit, before Step 8 dispatch). The spec body above is the round-1 revision; round 2 re-runs all lenses against it.

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
