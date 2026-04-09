# ADR-0004: GMP/MPFR via rug Crate for Arbitrary-Precision Rust Arithmetic

**Date:** 2026-03-20
**Status:** Accepted

## Context

Rust's primitive integer types (`u64`, `u128`) and floating-point types cap out well below the digit counts this repo targets. Pure-Rust big-integer crates (`num-bigint`, `ibig`) are correct but significantly slower than GMP, which is a battle-tested C library with assembly-optimised inner loops. The question was whether to use a pure-Rust solution for portability or bind to GMP for performance.

## Decision

Use the **`rug` crate** (safe Rust bindings to GMP and MPFR) for all arbitrary-precision integer and floating-point arithmetic in Rust implementations (`pi/pi-rs/`, `fib/fib-rs/`). `rug::Integer` for big integers, `rug::Float` for high-precision floats (π computation).

## Consequences

- Performance is within a small constant of hand-written C using GMP directly.
- Requires GMP and MPFR system libraries installed at build time — documented in each project's `install_deps.sh`.
- Not pure Rust: the build requires a C toolchain and system GMP headers. Cross-compilation is possible but non-trivial.
- `rug` API is ergonomic and safe; no `unsafe` code needed in application code.
- `prime-rs` does not use `rug` — it only needs packed `u64` bitsets, which Rust handles natively.

## Related

- [ADR-0002: Python + Rust dual implementation](0002-python-rust-dual-implementation.md)
- [ADR-0005: rayon for shared-memory parallelism](0005-rayon-for-shared-memory-parallelism.md)
