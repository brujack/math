# ADR-0002: Python + Rust Dual Implementation Strategy

**Date:** 2026-03-20
**Status:** Accepted

## Context

Python's arbitrary-precision `int` and `mpmath`/`gmpy2` libraries are ergonomic for mathematical work, but the GIL limits true parallelism and Python overhead becomes significant at very large digit counts (50M+). Rust with GMP bindings removes both constraints but requires more setup. The question was whether to pick one language or maintain both.

## Decision

Maintain **both** a Python and a Rust implementation for `pi` and `fib`. Python targets ≤50M digits where development speed and readability matter most. Rust targets 50M+ digits where GIL-free parallelism and GMP performance are decisive. Both implement the same underlying algorithm. `prime` is Rust-only because the segmented sieve's memory layout and parallelism requirements make a pure-Python version impractical at scale.

## Consequences

- Users can run the Python version without a Rust toolchain for moderate digit counts.
- Rust versions require GMP/MPFR system libraries and a Rust toolchain — documented in per-project `install_deps.sh`.
- Two codebases per project means algorithm changes must be applied twice; bugs can diverge.
- Separate CI workflows and Makefiles keep the two implementations independently testable.
- The crossover point (~50M digits) is a guideline, not enforced — users choose.

## Related

- [ADR-0001: Chudnovsky algorithm for π](0001-chudnovsky-algorithm-for-pi.md)
- [ADR-0004: GMP/MPFR via rug crate](0004-gmp-rug-crate-for-arbitrary-precision.md)
- [ADR-0006: Per-project CI workflows](0006-per-project-ci-workflows-with-test-gate.md)
