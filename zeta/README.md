# zeta

Certified verification of the Riemann Hypothesis up to height 10^N. **Under construction.**

When finished, `zeta N` will prove a finite-range theorem: every nontrivial zero ρ of the
Riemann zeta function with 0 < Im ρ ≤ T = 10^N lies on the critical line Re s = 1/2 and is
simple. It will also report how many such zeros there are. Every number the proof depends
on is an interval enclosure computed with directed rounding (MPFR), so the claim holds even
though the computation runs in floating point.

This is evidence for the Riemann Hypothesis, never a proof of it: the output says "RH
verified up to T", never "RH holds".

No Python implementation — Rust only.

## Status

The current build checks its input and its Hardy Z evaluator, but does not yet isolate
zeros, so it never claims verification. For N from 2 to 7 it runs the self-check, prints
this line to stdout and exits with code 3:

```text
RH NOT verified up to <T>: zero isolation is not implemented yet
```

N = 7 also prints a warning about output size and run time to stderr.

| Exit | Meaning |
| ---- | ------- |
| 0 | Verified up to T (arrives with the verifier) |
| 1 | Bad input: N outside 2–7, not a number, or end of input at the prompt |
| 3 | Not verified (today: zero isolation is not implemented yet) |
| 4 | A write to stdout, stderr or the output file failed |
| 5 | Self-check failed: the Riemann–Siegel and Euler–Maclaurin paths disagree at a test point |
| 6 | Internal fault during verification (arrives with the verifier) |

The library already has the certified building blocks:

- `Interval` — MPFR interval arithmetic with directed rounding (lower bound rounded down,
  upper bound rounded up); a sign is certified only when the interval excludes 0
- `VerifyConfig` — verification settings, which can only be made stricter than the defaults
- certified Riemann–Siegel θ(t) by the Stirling series with an explicit remainder bound,
  and Gram-point brackets with certified signs at both ends
- certified Hardy Z(t): Riemann–Siegel with Gabcke's remainder bound for t ≥ 200,
  Euler–Maclaurin below 200, and a self-check that compares the two paths at 8 points
  in [200, 300]

## Usage

```bash
./target/release/zeta        # prompts for N
./target/release/zeta 3      # self-check, then exits 3: zero isolation not implemented yet
```

## Build

```bash
cd zeta-rs
make zeta       # cargo build --release (binary in target/release/zeta)
make install    # build, then copy to ${XDG_BIN_HOME:-~/.local/bin}/zeta
make lint       # cargo fmt --check + clippy
make test       # lint + cargo test
```

## Design

- Spec: [`docs/superpowers/specs/2026-11-23-zeta-rh-verification-design.md`](../docs/superpowers/specs/2026-11-23-zeta-rh-verification-design.md)
- Plan: [`docs/superpowers/plans/2026-11-23-zeta-rh-verification.md`](../docs/superpowers/plans/2026-11-23-zeta-rh-verification.md)
