# ADR-0007: Prime Swing Algorithm for Factorial

**Date:** 2026-04-24
**Status:** Accepted

## Context

N! grows extremely fast — 10^6! has ~5.5 million digits. A naive sequential
multiplication requires O(N) big-integer multiplies, each more expensive than
the last as the result grows. Faster algorithms exploit the prime factorisation
of N! directly.

Candidates considered:
- **Naive multiplication**: O(N · M(D)) where M(D) is the cost of multiplying
  two D-digit numbers. Too slow for large N.
- **Divide-and-conquer binary splitting**: O(M(D) · log²N). Parallelisable,
  but requires careful management of the partial product tree.
- **Prime swing (Luschny)**: Decomposes N! into `n! = swing(n) × (⌊n/2⌋!)²`
  where `swing(n)` is computed directly from the prime sieve. Theoretically
  optimal for large N; all swing values at each recursion level are independent.

## Decision

Use the **prime swing algorithm** for both Python and Rust implementations.

The key identity: `swing(m) = ∏ p^e_p` where `e_p = Σ_{j≥1} (⌊m/pʲ⌋ mod 2)`.
This allows swing(m) to be computed in a single pass over the prime sieve with
no floating-point arithmetic. The recursion `n! = swing(n) × (⌊n/2⌋!)²`
naturally parallelises — all swing computations at each level are independent.

## Consequences

- Faster than divide-and-conquer for large N due to fewer large-integer
  multiplications.
- Requires a prime sieve up to N — O(N) space, precomputed once.
- More complex to implement than naive multiplication; the bit-counting loop
  for `e_p` is non-obvious.
- Both Python and Rust implementations share the same algorithm, so correctness
  can be cross-validated.

## Related

- [ADR-0002: Python + Rust dual implementation](0002-python-rust-dual-implementation.md)
- [ADR-0003: Parallel segmented sieve](0003-parallel-segmented-sieve-for-primes.md)
- [ADR-0005: rayon for shared-memory parallelism](0005-rayon-for-shared-memory-parallelism.md)
