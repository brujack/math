# ADR-0001: Chudnovsky Algorithm with Binary Splitting for π

**Date:** 2026-03-20
**Status:** Accepted

## Context

The original `pi.py` used a simpler iterative series that became impractically slow beyond a few thousand digits. A faster algorithm was needed to reach millions or billions of digits in reasonable time. Candidates considered: Machin-like formulas, Bailey–Borwein–Plouffe (BBP), and Chudnovsky.

## Decision

Use the **Chudnovsky algorithm** with **binary splitting** for all π implementations (both Python and Rust). Binary splitting converts the series into a tree of rational number multiplications, enabling parallel evaluation and reducing the number of big-integer divisions.

## Consequences

- Fastest converging series for π known: each term adds ~14.18 decimal digits, far outpacing alternatives.
- Binary splitting makes the algorithm parallelisable — the tree of sub-products can be evaluated concurrently.
- More complex to implement than a naive loop; requires careful management of large numerator/denominator pairs.
- Used identically in both the Python (`pi/pi.py`) and Rust (`pi/pi-rs/`) implementations, so algorithm bugs surface in both.

## Related

- [ADR-0002: Python + Rust dual implementation](0002-python-rust-dual-implementation.md)
- [ADR-0005: rayon for shared-memory parallelism](0005-rayon-for-shared-memory-parallelism.md)
