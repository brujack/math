# zeta

Certified verification of the Riemann Hypothesis up to height 10^N. **Under construction:** verification works for N = 2–7; `--refine` and progress output are still to come.

`zeta N` proves a finite-range theorem: every nontrivial zero ρ of the
Riemann zeta function with 0 < Im ρ ≤ T = 10^N lies on the critical line Re s = 1/2 and is
simple. It also reports how many such zeros there are. Every number the proof depends
on is an interval enclosure computed with directed rounding (MPFR), so the claim holds even
though the computation runs in floating point.

This is evidence for the Riemann Hypothesis, never a proof of it: the output says "RH
verified up to T", never "RH holds".

No Python implementation — Rust only.

## Status

For N from 2 to 7 the CLI runs the self-check of its Hardy Z evaluator, then the one-pass
verification. When every zero up to T = 10^N is isolated, it writes `zeta_1eN.txt`
(header `# n a b`, then one line per zero with the certified interval (a, b), a rounded
down and b rounded up to 30 significant digits) and prints to stdout:

```text
Self-check: Riemann–Siegel and Euler–Maclaurin agree on [200, 300] (8 points)
Turing bound: N(g_M) <= M+1 established at g_M = <value>
Isolating zeros in 0 < t <= <T> (<k> threads)...

RH verified: all <count> nontrivial zeros with 0 < Im s <= <T> lie on Re s = 1/2 and are simple
Gram blocks: <b>   Rosser exceptions: <r>   max precision: <p> bits
Saved zeta_1eN.txt
Elapsed: <s> s
```

`<value>` is g_M to 6 decimals (a `[lo, hi]` pair when its certified bracket is wider than that). These lines are printed together once the table is saved, so a failed save is never preceded
by a verified claim.

The table is written to `zeta_1eN.tmp.txt` and renamed on completion; no `zeta_1eN.txt` is
created on any other exit. When the proof cannot be completed it prints
`RH NOT verified up to <T>: <reason>` (for example `647 of 649 zeros isolated`, then the
unresolved Gram blocks and `No claim is made for this range.`) and exits 3;
no claim is made for that range. N = 7 also prints a warning about output size and run time
to stderr. `--refine` and progress output are not implemented yet.

| Exit | Meaning |
| ---- | ------- |
| 0 | Verified up to T |
| 1 | Bad input: N outside 2–7, not a number, or end of input at the prompt |
| 3 | Not verified: any uncertain result (an unresolved Gram block, too few zeros isolated, Turing's bound not established, a zero's side of T uncertain, no certified left boundary or Gram block); no output file |
| 4 | A write to stdout, stderr or the output file failed (a failed table write removes the temporary file; if only stdout fails after the table was saved, the table stays) |
| 5 | Self-check failed: the Riemann–Siegel and Euler–Maclaurin paths disagree at a test point |
| 6 | Internal fault during verification (a Z fault, a NaN height, a sign conflict, a worker panic) |

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
./target/release/zeta 3      # verifies the 649 zeros up to 1000, writes zeta_1e3.txt, exits 0
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
