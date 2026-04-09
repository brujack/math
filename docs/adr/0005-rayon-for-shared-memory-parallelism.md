# ADR-0005: rayon for Shared-Memory Parallelism in Rust

**Date:** 2026-03-20
**Status:** Accepted

## Context

Both the Chudnovsky binary-splitting tree (π) and the segmented sieve (primes) decompose into independent sub-problems that can run concurrently. Options considered: manual `std::thread` spawning, Tokio (async), and rayon (data parallelism).

## Decision

Use **rayon** for all intra-process parallelism in Rust implementations. Rayon's `par_iter()` and `join()` primitives distribute work across a shared thread pool with zero inter-process communication overhead. All data stays in the same process address space — no serialization, no channels, no IPC.

## Consequences

- Near-linear throughput scaling with available CPU cores on embarrassingly parallel workloads.
- Zero IPC overhead — threads share the same heap; no data copying between workers.
- Work-stealing scheduler handles uneven sub-problem sizes automatically (important for binary splitting, where leaf nodes vary in cost).
- Not suitable for distributed or GPU computation — rayon is single-machine, CPU-only.
- Thread count defaults to the number of logical CPUs; can be overridden via `RAYON_NUM_THREADS` env var.

## Related

- [ADR-0001: Chudnovsky algorithm for π](0001-chudnovsky-algorithm-for-pi.md)
- [ADR-0003: Parallel segmented sieve for primes](0003-parallel-segmented-sieve-for-primes.md)
- [ADR-0004: GMP/MPFR via rug crate](0004-gmp-rug-crate-for-arbitrary-precision.md)
