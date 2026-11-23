# zeta: certified verification of the Riemann Hypothesis up to height T

- **Date:** 2026-11-23
- **Sub-project:** `zeta/` (new), Rust only: crate `zeta/zeta-rs`, binary `zeta`

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
  Stirling series with an explicit remainder bound.
- **Gram points.** g_n is the unique solution of θ(g_n) = nπ for n ≥ −1. Gram point g_n is
  _good_ when (−1)^n Z(g_n) > 0. A _Gram block_ is an interval [g_j, g_k) between
  consecutive good Gram points; it contains k − j Gram intervals.
- **Rosser's rule.** A Gram block of k − j intervals usually contains exactly k − j zeros.
  It is known to fail occasionally, so it is used only as a search guide, never as a step
  in the proof.
- **Counting function.** N(T) is the number of zeros of ζ with 0 < Im ρ ≤ T, counted in
  the whole critical strip whether on the line or not.
- **Turing's method.** At a good Gram point g_M, the sign pattern of Z over the following
  Gram blocks, combined with an explicit bound on ∫ S(t) dt (Trudgian 2011), proves
  N(g_M) ≤ M + 1.

## The proof

1. Choose M: the smallest index with g_M ≥ T, g_M a good Gram point, and Turing's
   method establishing N(g_M) ≤ M + 1. Try at most 10 successive good Gram points before
   giving up.
2. Split (0, g_M] into Gram blocks and isolate zeros in each block by certified sign
   changes of Z. Let L be the number of disjoint certified sign-change intervals.
3. Every certified sign change is a distinct zero on the line, so L ≤ N(g_M) ≤ M + 1.
   If L = M + 1, all zeros up to g_M are on the line, and each is simple (one sign change
   per zero, with no room for a multiple zero in the count). The claim is then printed for
   T, using the zeros whose interval lies at or below T.
4. If L < M + 1, nothing is claimed. The CLI names the Gram blocks it could not resolve
   and exits 3.

## Approach: interval arithmetic on MPFR

Three approaches were considered:

- **A. Point MPFR with a hand-derived error budget.** Fastest, but soundness rests on an
  error analysis of every operation remaining correct through every future refactor.
  Rejected.
- **B. Interval arithmetic on MPFR directed rounding (chosen).** Every operation returns
  `[lo, hi]` with `lo` rounded down and `hi` rounded up, so the true value is always
  enclosed. MPFR's elementary functions are correctly rounded, which is what makes the
  enclosure sound. Truncation bounds (Gabcke, Euler–Maclaurin, Stirling) are added by
  widening. A sign is certified exactly when the final enclosure excludes 0. Cost is about
  2–4× point arithmetic. No new dependency (GMP and MPFR via `rug`, as `pi-rs` and `e-rs`
  already use), and `unsafe_code = "forbid"` holds.
- **C. Delegate to FLINT/Arb** (`acb_dirichlet_hardy_z` and Platt's zero isolation). The
  most trusted implementation, but it adds a C library to every installer (breaking the
  identical-installer rule unless declared as a parameter), needs a `-sys` binding, and
  makes the proof Arb's rather than this crate's. Rejected.

Z(t) is evaluated two ways:

- **t ≥ 200: Riemann–Siegel.** Main sum of ⌊√(t/2π)⌋ terms plus the C₀ correction,
  widened by Gabcke's remainder bound, which holds for t ≥ 200. O(√t) terms.
- **t < 200: Euler–Maclaurin** summation of ζ(1/2 + it) with its rigorous remainder bound.
  O(t) terms, which is trivial below 200 and covers the first 79 zeros.
- **Overlap check.** On [200, 300] both methods are evaluated at the same points and their
  enclosures must intersect. This cross-checks two independent implementations at runtime
  and in the test suite.

## Components

Modules in `zeta/zeta-rs/src/`, each testable on its own:

| Module        | Responsibility                                                                                                                                                                                                                                                                                        | Depends on          |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| `interval.rs` | `Interval { lo, hi }` over `rug::Float`: `+ − × ÷`, `sqrt`, `ln`, `exp`, `cos`, `sin`, `widen(ε)`, `excludes_zero()`, `sign() -> Option<Sign>`. Lower bounds round down, upper bounds round up. `cos`/`sin` of an argument wider than π return [−1, 1]; a narrower argument returns `f(mid) ± width`. | `rug`               |
| `theta.rs`    | θ(t) enclosure from the Stirling series plus remainder bound; Gram point g_n by interval Newton iteration on θ(g) = nπ.                                                                                                                                                                               | `interval`          |
| `zfun.rs`     | `riemann_siegel(t)`, `euler_maclaurin(t)` and `z(t)`, which dispatches on t ≥ 200.                                                                                                                                                                                                                    | `interval`, `theta` |
| `isolate.rs`  | One Gram block in, certified sign-change intervals out. Uses Rosser's expected count to decide when to subdivide (max depth 40) and raises precision when a sign is uncertain.                                                                                                                        | `zfun`              |
| `turing.rs`   | Establishes N(g_M) ≤ M + 1 from the sign pattern after g_M and Trudgian's bound.                                                                                                                                                                                                                      | `zfun`, `theta`     |
| `verify.rs`   | Orchestration: block list, parallel isolation in chunks, ordered merge, comparison of L with M + 1, `Verdict`. Generic over a `ZSource` trait so tests can inject fakes.                                                                                                                              | all above           |
| `spacing.rs`  | `--refine` only: bisection of each interval to 10⁻¹², normalised spacings, histogram against the Wigner surmise, KS distance.                                                                                                                                                                         | `zfun`              |
| `main.rs`     | clap CLI, `run()` and `prompt_n()` in goldbach's shape, thin `main` excluded from tarpaulin.                                                                                                                                                                                                          | `verify`, `spacing` |

## Parallelism

Gram blocks are independent, so isolation runs on a rayon pool built with
`ThreadPoolBuilder::build`. Blocks are processed in chunks of 10,000: a parallel pass over
the chunk, then an ordered write, then the next chunk. Memory is bounded by the chunk
size, not by N. If the pool cannot be built, the CLI prints `Parallel mode unavailable:
<err>` and `Running serially` (the descartes-rs wording) and processes the same blocks
serially. The output is byte-identical either way. The global pool and plain `par_iter`
are not used, because they panic when the OS refuses a thread.

## CLI

```
zeta [N] [--refine]
```

- `N` is 2 to 7, giving T = 10^N. Missing N prompts for it, as `goldbach` does. N > 6
  prints a warning with the expected file size and runtime before starting.
- `--refine` adds a refined zero value per line and the spacing histogram.

Approximate work (estimates, to be replaced by V2's measurements): N = 3 under 1 s, N = 5
about a minute, N = 6 tens of minutes, N = 7 many hours, all on the 48-thread `claude`.

### Output file `zeta_1eN.txt`

One line per zero with 0 < t ≤ T, in order:

- default: `n a b`, meaning exactly one zero lies on the line with imaginary part in
  (a, b); `a` and `b` are decimals with 30 significant digits;
- `--refine`: `n a b t_n`, where |t_n − γ_n| < 10⁻¹² and t_n is printed with 12 decimals.

Zeros in (T, g_M] are proven but not listed. The file is written to a temporary file in the
same directory and renamed to `zeta_1eN.txt` only when the verdict is verified. On any other outcome the temporary file is removed and no `zeta_1eN.txt` is written or replaced, so a file by that name is always a complete proof witness.

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
```

With `--refine`, a histogram of normalised spacings δ_n = (t_{n+1} − t_n)·ln(t_n/2π)/2π
over s ∈ [0, 3] in 0.15-wide bins, the Wigner surmise p(s) = (32/π²) s² e^(−4s²/π)
beside each bin, and the KS distance. The output states that the Wigner surmise
approximates the exact GUE spacing law to within about 1%, and that independent random
points (Poisson) would instead peak at s = 0.

### Exit codes

| Code | Meaning                                                                     |
| ---- | --------------------------------------------------------------------------- |
| 0    | Verified                                                                    |
| 1    | Input error, N out of range, or end of input at the prompt                  |
| 2    | clap usage error                                                            |
| 3    | Computed, not verified (uncertified blocks or Turing bound not established) |
| 4    | Output write failed                                                         |
| 5    | Runtime self-check failed (the two Z implementations disagree)              |

## Error handling

The rule throughout: anything uncertain becomes "not verified", never "verified".

- **Uncertain sign of Z(t).** Precision steps 64 → 128 → 256 → 512 bits. When the enclosure
  width is dominated by a truncation bound, more bits cannot help, so the sample point is
  moved instead. A sign still uncertain after that is recorded as uncertain.
- **Fewer sign changes than Rosser's rule expects.** The block is subdivided recursively up
  to depth 40; on a Rosser failure the neighbouring blocks are searched too. Unresolved
  blocks are reported and the run exits 3.
- **An interval straddling T.** It is bisected until it lies on one side, so the count up
  to T is exact.
- **Gram point Newton iteration fails to converge.** The block is uncertified.
- **Turing's method fails at g_M.** Up to 10 further good Gram points are tried, then the
  run exits 3 with `Turing bound not established`.
- **Self-check disagreement on [200, 300].** Exit 5, `self-check failed`, before any
  verdict.
- **End of input at the prompt.** As goldbach: a newline on stdout, then
  `Error: no input; pass SIZE as an argument (e.g. zeta 3).` on stderr, exit 1.

## Testing

Ground truth comes from outside the crate:

1. **Odlyzko's zero table.** The first 10,142 zeros (all zeros up to 10⁴, accuracy about
   3·10⁻⁹) are committed as `zeta/zeta-rs/tests/fixtures/odlyzko_1e4.txt`, with the
   source URL and retrieval date in its header.
2. **Published counts.** N(10²) = 29, N(10³) = 649, N(10⁴) = 10,142, N(10⁵) = 138,069,
   N(10⁶) = 1,747,146, N(10⁷) = 21,136,125.
3. **Two independent Z implementations**, compared on [200, 300].

Tests in the crate:

- **Counts and containment.** N = 2, 3, 4 produce 29, 649 and 10,142 intervals; the nth
  Odlyzko zero lies in the nth interval; with `--refine`, |t_n − γ_n| < 10⁻⁸ against the
  table.
- **Negative controls through `ZSource` fakes.** A double root (sign touch without
  change), a block missing one sign change, an irregular Turing pattern, and a source that
  always reports an uncertain sign each produce a not-verified verdict; none produces
  "verified".
- **Interval properties (proptest).** For random inputs, every operation's enclosure
  contains the value computed at four times the precision, and enclosure width shrinks as
  precision grows.
- **Theta and Gram points.** θ(g_n) encloses nπ; g_n is strictly increasing.
- **Lehmer's pair.** The two close zeros near t ≈ 7005.06 are both isolated, exercising
  subdivision.
- **Parallel versus serial.** With the pool forced to fail, `zeta_1e3.txt` is
  byte-identical to the parallel run.
- **CLI.** `run()` is tested for exits 0, 1, 3, 4 and 5, end of input at the prompt, and N
  out of range; `scripts/cli_contract.py` conformance; BATS failure-mode tests per the
  repo DoD.
- **Bench.** criterion bench of `z(t)` at t = 10⁴ and t = 10⁶.

## Repo integration

- All crate files rendered from `scripts/crate_templates/` (Makefile, `rustfmt.toml`,
  `.config/nextest.toml`, `install_deps.sh`, `zeta-rs.yml`, `release-zeta-rs.yml`); the
  crate count becomes 13 everywhere it is stated.
- `Cargo.toml` matches the other crates: edition 2024, `unsafe_code = "forbid"`, the API
  lints, no `rust-version`, dependencies `rug` (features `integer`, `float`), `rayon`,
  `clap`.
- New-CLI checklist: README CLI and Coverage tables and badge, CI table, root `CLAUDE.md`
  sub-project lists, `scripts/pre-commit` and `scripts/pre-push` directory lists, mutation
  workflows, `zeta/zeta-rs/CLAUDE.md`, and `.gitignore` for `zeta_1e*.txt`.

## Follow-up (not in this spec)

Rebuild π(x) from the explicit formula using `zeta N --refine` zeros, with `prime/`'s
exact counts as ground truth. Recorded as a P4 Backlog row.

## Requirements

- **R1.** `zeta N` accepts N from 2 to 7 inclusive, computes with T = 10^N, and exits 1 for any other N.
- **R2.** On a verified run, stdout contains the line `RH verified: all <count> nontrivial zeros with 0 < Im s <= <T> lie on Re s = 1/2 and are simple` and the process exits 0.
- **R3.** No output of the CLI, in any path, contains the phrase `RH holds` or claims verification beyond T.
- **R4.** A verified verdict is issued only when the number of disjoint certified sign-change intervals in (0, g_M] equals M + 1 and Turing's method has established N(g_M) ≤ M + 1; otherwise stdout contains `RH NOT verified up to <T>` and the process exits 3.
- **R5.** Every value the verdict depends on (θ, Gram points, Z, truncation bounds) is computed as an interval whose lower bound is rounded toward −∞ and upper bound toward +∞, and a sign is used only when the interval excludes 0.
- **R6.** Z(t) uses Riemann–Siegel with Gabcke's remainder bound for t ≥ 200 and Euler–Maclaurin with its remainder bound for t < 200.
- **R7.** Before any verdict, the CLI evaluates both Z implementations at 8 points in [200, 300]; if any pair of enclosures does not intersect it prints `self-check failed` to stderr and exits 5.
- **R8.** `zeta_1eN.txt` holds one line per zero with 0 < t ≤ T in increasing order, formatted `n a b` by default and `n a b t_n` with `--refine`, where a and b have 30 significant digits and t_n has 12 decimals.
- **R9.** The output file is written to a temporary path in the same directory and renamed to `zeta_1eN.txt` only on a verified verdict; on exit 3, 4 or 5 the temporary file is removed and no `zeta_1eN.txt` is created or replaced; a write failure exits 4.
- **R10.** Zero isolation runs on a rayon pool built with `ThreadPoolBuilder::build` over chunks of 10,000 Gram blocks; if the build fails, stderr shows `Parallel mode unavailable: <err>` and `Running serially`, and the output file is byte-identical to the parallel run.
- **R11.** The global rayon pool (`rayon::current_num_threads`, `par_iter` outside the built pool) is not used.
- **R12.** `--refine` adds a spacing histogram over s ∈ [0, 3] in 0.15-wide bins with the Wigner surmise p(s) = (32/π²) s² e^(−4s²/π) beside each bin and the KS distance.
- **R13.** End of input at the N prompt prints a newline to stdout, `Error: no input; pass SIZE as an argument (e.g. zeta 3).` to stderr, and exits 1.
- **R14.** N > 6 prints a warning naming the expected output size before computation starts.
- **R15.** The crate is Rust only (`zeta/zeta-rs`), with no Python sub-project, and every templated file is rendered from `scripts/crate_templates/` so `tests/test_crate_uniformity.py` passes for 13 crates.
- **R16.** `zeta/zeta-rs/tests/fixtures/odlyzko_1e4.txt` holds the first 10,142 zeros with its source URL and retrieval date in a header, and tests assert counts 29, 649 and 10,142 for N = 2, 3, 4 and that each table zero lies in its interval.
- **R17.** Tests inject `ZSource` fakes for a double root, a missing sign change, an irregular Turing pattern and an always-uncertain sign, and each yields a not-verified verdict.
- **R18.** Proptest asserts that every `Interval` operation's enclosure contains the value computed at four times the working precision.
- **V1.** Before implementation, pin against the primary sources and record in the plan: the exact form and constant of Gabcke's Riemann–Siegel remainder bound and its validity range; the Euler–Maclaurin and Stirling remainder bounds used; the Turing inequality and Trudgian's constants; the Gram index of the first Rosser-rule failure; and the location of Lehmer's pair.
- **V2.** Run N = 5, 6 and 7 on `claude`; each verified count equals the published N(10^N) (138,069; 1,747,146; 21,136,125); record wall-clock time and peak RSS.
- **V3.** The N = 7 run passes through the first Rosser-rule failure pinned in V1 and still exits 0.
- **V4.** Run `zeta 3 --refine` and confirm the histogram's first bin is near empty and the KS distance to the Wigner surmise is below 0.1.
- **N1.** The CLI never claims RH in general; no code path prints a verification claim beyond T.
- **N2.** No new native library beyond GMP and MPFR, and no `unsafe` code in the crate.
- **N3.** No arbitrary-range mode (`--from`/`--to`) in this spec.
- **N4.** No reconstruction of π(x) from the explicit formula in this spec.

## Multi-Lens Review

Reviewed at commit: `b27bae1` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: (1) Trudgian's ∫S bound holds only for t ≥ 168π ≈ 527.8 (Trudgian 2011 abstract; Brent 2021), but step 1 picks g_M ≥ T, so N = 2 (T = 100) applies Turing outside its proven range: an unsound "verified", or an exit 3 that contradicts R16. Fix: g_M ≥ max(T, 168π). (2) `--refine` and the spacing histogram have no consumer that changes a decision; their real consumer is the π(x) follow-up, so they could move there. (3) The self-check shares `interval.rs` and `theta.rs` between both Z paths, so a θ error is invisible to it; keep it as a canary and drop "independent implementations". (4) "Proof witness" overclaims while nothing re-checks the file; a cheap `--check` would make it true. Math corrections: g_n is unique only for t > 2π (θ dips to about −3.53 near 2π), and Rosser's rule says *at least* k − j zeros, not exactly. Premise checks run: rug 1.30.0 has `cos_round`, `sin_round`, `ln_round`, `exp_round`, `sqrt_round`, `ln_gamma_round` and `*AssignRound`; `rayon_core::ThreadPoolBuilder::build` returns `Err`, not a panic, on a failed spawn; `tests/test_crate_uniformity.py` and `render_crate_files.py` hard-code 12 crates.
Assumption: C₀-only Riemann–Siegel with Gabcke's bound (about 7·10⁻⁷ at t = 10⁷) certifies every sign up to 10⁷. Refuted if some close pair below 10⁷ has max |Z| between its zeros under that floor; settled by a pre-implementation scan of the smallest gaps in [10⁶, 10⁷] or by the extreme small-|Z| values in published verifications.
Disposition:

### Ergonomics

Finding: (1) N = 6/7 runs give no progress output, discard every certified interval on a late failure, and cannot be fixed by rerunning (deterministic, no knob). (2) R14 has no stated size: about 1.5 GB at N = 7, about 2 GB with `--refine`. (3) `scripts/cli_contract.py` runs only against Python programs, so the CLI-contract test cannot apply to a Rust-only crate. (4) The serial-fallback wording is misattributed; descartes-rs prints `Parallel mode unavailable ({error}); falling back to serial.` (5) Exit codes 3, 4 and 5 are new to the Rust CLIs (siblings use 0, 1 and clap's 2) and need documenting as a convention. (6) Full N = 4, and N = 4 with `--refine`, under tarpaulin may exceed nextest's 45 s per-test bound; the test plan needs a fast tier. (7) The output file has no column header.
Assumption: full N = 4 verification, and N = 4 `--refine`, fit inside 45 s per test in debug and the 30-minute tarpaulin job on `ubuntu-latest`; settled by timing those tests once `verify.rs` exists.
Disposition:

### Risk

Finding: Same Trudgian 168π range defect at N = 2 as Goal-Fit (1), with the same fix plus a V1 range item and a unit test that `turing.rs` refuses g_M < 168π. Measured: Lehmer's pair near 7005.06 has max |Z| = 0.00397 between its zeros against a Gabcke floor of 1.66·10⁻⁴ (24× margin, mpmath `siegelz` at 30 digits). Test verdicts: 6 expect verified, 5 expect not verified; the negative controls assert only "not verified", not the reason, and no fake covers L > M + 1. Checked sound: the simplicity argument, block-boundary counting, ln arguments, precision at 10⁷, the temp-file rename.
Assumption: Gabcke's C₀ floor is below the peak |Z| of every consecutive zero pair up to 10⁷ (same as Goal-Fit's); settled by `mpmath.siegelz` over the 50 smallest gaps from Odlyzko's zeros below 10⁷.
Disposition:

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
Disposition:
