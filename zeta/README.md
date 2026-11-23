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

The current build is a stub. It accepts an optional exponent N, never claims
verification, and for every input prints this line to stderr and exits with code 3:

```text
RH NOT verified: zeta is under construction
```

A failed write to stderr exits with code 1.

The library already has the certified building blocks:

- `Interval` — MPFR interval arithmetic with directed rounding (lower bound rounded down,
  upper bound rounded up); a sign is certified only when the interval excludes 0
- `VerifyConfig` — verification settings, which can only be made stricter than the defaults
- certified Riemann–Siegel θ(t) by the Stirling series with an explicit remainder bound,
  and Gram-point brackets with certified signs at both ends

## Usage

```bash
./target/release/zeta        # exits 3: under construction
./target/release/zeta 3      # exits 3: under construction
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
