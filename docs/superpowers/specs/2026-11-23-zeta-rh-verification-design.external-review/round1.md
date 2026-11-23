Tools: Read, Bash, SubagentHandback

The proof is sound, and the author should leave it as it is. Every sign is taken at an exact `f64` point. L and Turing's counts are each made in one sorted pass after all blocks finish. Gram boundaries are certified `f64` brackets that go into both vectors. Turing blocks are closed ranges with shared boundaries. L = M + 1 is the only route to "verified", and L > M + 1 exits 6. I traced uniqueness from n = −1, b_M shared by L and Turing, the worst-case bracket ends in Turing's inequality, and simplicity from multiplicity, and found no hole. The published counts (29, 649, 10,142, 138,069, 1,747,146, 21,136,125) and the Lehmer floor arithmetic (0.127·7005^(−3/4) = 1.66·10⁻⁴) check out. The design has stopped moving: what remains is test apparatus and wording.

## F1.1 The CLI tests ask `run()` for exits and a throttle it cannot produce

**Defect.** The Components row and R24 say `run()` takes no configuration and always uses the real Z, the real writer and the 2 s throttle. The Testing "CLI" bullet then tests `run()` for exits 3, 4, 5 and 6, with "the time throttle set to 0 under `cfg(test)`" and "a writer that fails after some bytes".

**Failure.** With the real Z at N = 2..7, `run()` cannot reach exit 5 (self-check) or exit 6 (fault). In tests it cannot reach exit 3 either. With the real writer it cannot fail after some bytes. There are two ways out, and both are bad:
- A planner follows the text and puts `cfg(test)` branches inside `run()`. Then the tested `run()` is not the shipped one, which is the very seam R24 removed.
- The planner silently drops those cases, and the exit mapping in `run()` goes uncovered.

**Fix.** Re-word the CLI bullet. `run()` covers exits 0 and 1, end of input at the prompt, N out of range and the N = 7 warning. `run_with` covers exits 3–6, the failing writer, the zero throttle and the stale-temp removal. R24 itself does not change.

## F1.2 R20's 64-bit control is almost certainly not a negative control

**Defect.** R20 requires that "precision cap 64 with point moving off" yields exit 3. 64 bits is also the starting precision, so the cap only stops the 64 → 512 escalation. Below 10³ that escalation never decides a sign.

**Why.** The numbers below are derived, not run.
- **Rounding.** At 64 bits the Riemann–Siegel phase t·ln n is at most about 3.4·10³ at t = 10³, so the error per term is about 3.4·10³·2⁻⁶³ ≈ 4·10⁻¹⁶.
- **Truncation.** The Gabcke width is 2·0.127·t^(−3/4): 1.4·10⁻³ at t = 10³ and 4.8·10⁻³ at t = 200.

The truncation term exceeds the rounding term by 10¹². Any point that 512 bits certifies, 64 bits certifies too. With point moving off, `isolate` still subdivides to depth 40 and picks fresh midpoints. The expected outcome is exit 0. The spec already plans to "measure the reason before the plan", but R20 hard-codes exit 3, so that measurement would contradict a requirement and no rule says what happens then.

R20 also never names N. For the Gabcke × 10⁶ control it matters: below 200 the Euler–Maclaurin path is unaffected, so at N = 2 that control can only fail through Turing (g_M ≥ 168π uses Riemann–Siegel). It does bite, as `Turing bound not established`.

**Fix.** Replace the precision control in R20 with one that binds on real Z, or drop it. A depth cap of 0 or 1 at N = 3 should bind, subject to the same pre-plan measurement. Name N for each control.

## F1.3 Trudgian's bound has lost its sign

**Defect.** Lines 54–56 read "≤ 2.067" and then a new line "- 0.059 ln t₂, which holds…". A Markdown line wrap turned "+" into a list marker. Rendered, the text is a bullet, or reads as 2.067 − 0.059 ln t₂. The bound is 2.067 **+** 0.059 ln t₂, as the spec's own round-1 text and Trudgian 2011 give it.

**Failure.** Someone who reads only the background writes a bound that shrinks with height. That is unsound, since it over-tightens Turing's inequality. V2 pins the bound from the source, which limits the damage, but the spec is the planner's first read.

**Fix.** Rejoin the line so that no line starts with `+`.

## F1.4 V8 models the mutation budget wrongly

**Defect.** The Testing section says a Z-breaking mutant "can run each end-to-end test to its 30 s timeout". The template Makefile runs `cargo mutants --in-diff … --timeout-multiplier 5 --minimum-test-timeout 30`, under cargo-mutants 27.1.0 per `mutation-pr.yml`.

As I recall, cargo-mutants times out a mutant's whole test run, not each test. The limit is max(30 s, 5 × the baseline test time). This is unmeasured, because cargo-mutants is not installed here; `cargo mutants --help` under `--timeout-multiplier` would confirm it.

**Failure.**
- The cost of a timed-out mutant is 5 × the baseline, which is 100 s if `cargo test` takes 20 s in debug. It is not 30 s per end-to-end test.
- On the first PR every line of the crate is in the diff, so every mutant runs.
- V8 times a Riemann–Siegel loop. It does not time the baseline `cargo test`, which is what sets the timeout.

**Fix.** V8 should measure the debug `cargo test` baseline of the prototype. It should then project (timed-out mutants × max(30, 5·baseline)) + (other mutants × baseline) against the 60-minute job, for the first PR where the whole crate is the diff.

## Smaller items

- **F1.5 Stale headers.** Line 5 says "after … rounds 1–3", and line 456 says "the spec body above is the round-3 revision". The body is the round-4 revision. The round-2 dispositions cite R25 as `make test-release`, but R25 is now the Lehmer block test.
- **F1.6 `--refine` columns.** R8 fixes the digits for a and b but not for t_n and w_n, so R14's "about 2 GB with --refine" cannot be checked. If t_n is printed at 30 digits, 21.1M lines of about 118 B come to about 2.5 GB. Pin both formats, then derive the figure.
- **F1.7 The CDF behind the KS distance.** R12 says "KS distance" but not which CDF. I measured the first 649 zeros (mpmath 1.4.1, Python 3.14.8, Linux 7.0.0-43):
  - against the correct GUE-surmise CDF, erf(√a·s) − (2/√π)·√a·s·e^(−a·s²) with a = 4/π: KS = 0.045, with the first bin empty (2.3 expected);
  - for 648 genuine Wigner samples, the 95th-percentile KS is 0.054;
  - with the GOE CDF 1 − e^(−4s²/π), the easy mistake (I made it first): KS = 0.245.

  V5's threshold of 0.1 therefore passes when right and catches that mistake. Pin the CDF in R12 so V5 tests the intended thing, and say what a V5 failure blocks.
- **F1.8 T inside g_M's bracket.** If b_M < T ≤ c_M, no sign-change interval of L contains T. That is correct, since [b_M, c_M] is certified zero-free, but the straddle rule does not state the case. The implementation must treat it as "no straddle", not as a fault.
- **F1.9 Error-handling wording.** The self-check bullet writes the Riemann–Siegel ceiling as "2 × Gabcke's bound at that t plus 10⁻¹⁰", while R7 writes 0.127·t^(−3/4). Under the × 10⁶ control (self-check skipped) they agree, but say once that the self-check uses the unscaled constant.

Not raised, though checked:
- Uniqueness of the Gram points for t > 2π.
- No zeros below b₋₁ (γ₁ = 14.13).
- Bracket widths at 10⁷ (`f64` ulp ≈ 1.9·10⁻⁹, Gram spacing ≈ 0.44).
- Phase precision at 10⁷ with 64 bits.
- The N(T) values.
- `mutation-rs` is indeed one 60-minute job (`.github/workflows/mutation-pr.yml:184`).
- No crate sets `panic = "abort"`, so catching a worker panic works in release.
- The prior-work grep matches only this spec and its own index rows.

No `Author response` table exists yet, so there are no accepted or not-accepted lines for this round.

F1.1 and F1.2 must be fixed before the plan, because the plan's test tasks would be built on them. F1.3 is a one-line fix. F1.4 changes V8's method. The rest can go into the same edit. None of these touches the proof, so another review round is not worth running; the first red tests will find the rest.

Recommend: stop
