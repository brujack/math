# ADR-0003: Parallel Segmented Sieve of Eratosthenes for Primes

**Date:** 2026-03-20
**Status:** Accepted

## Context

Finding all primes up to 10^N requires a sieve. A naive Sieve of Eratosthenes allocates O(N) memory — for N=10 (10 billion), that is ~10 GB of booleans, which is impractical. A segmented variant processes the number line in fixed-size chunks, keeping peak RAM bounded. The question was how to size segments and how to parallelise across chunks.

## Decision

Use a **parallel segmented Sieve of Eratosthenes** in Rust with:

- **32 KB packed bitset segments** — sized to fit in L2 cache, eliminating cache-miss overhead during inner sieve loops.
- **rayon** for parallel evaluation of independent segments across all available CPU cores.
- **Streaming output** — primes are written to file as each segment completes rather than accumulating in memory.

## Consequences

- Peak RAM is ~50 MB regardless of the sieve limit N, dominated by the small-prime precomputation buffer, not the segment storage.
- Near-linear throughput scaling with core count on multi-core machines.
- Streaming output means the output file is progressively written — useful for very large runs.
- The 32 KB segment size is a heuristic for typical L2 cache sizes; machines with smaller caches may benefit from tuning.
- Output is written in segment order, so primes are naturally sorted without a post-sort step.

## Related

- [ADR-0005: rayon for shared-memory parallelism](0005-rayon-for-shared-memory-parallelism.md)
