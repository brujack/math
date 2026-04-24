# ADR-0008: Recursive Squaring Over Iterative Level-Product for Factorial

**Date:** 2026-04-24
**Status:** Accepted

## Context

The prime swing identity can be expressed in two equivalent forms:

**Iterative level-product form** (original spec):

```
n! = ∏ swing(⌊n/2^k⌋) ^ (2^k)   for k = 0, 1, 2, … until ⌊n/2^k⌋ < 2
```

**Recursive squaring form** (implemented):

```
n! = swing(n) × (⌊n/2⌋!)²
```

The spec specified the iterative form. During implementation the recursive form was chosen instead.

## Decision

Use the **recursive squaring form** in both Python and Rust.

The iterative form requires raising each swing value to a power of `2^k`. For the
deepest recursion level (k ≈ log₂(n)), `2^k ≈ n` — meaning the final swing value
(which equals 1 for small arguments) must be raised to the n-th power. Even though
swing(1) = 1 makes this a no-op in practice, the general case requires big-integer
exponentiation with an exponent that is itself a large integer (`2^k` for k near 60
would be a ~19-digit exponent). This is more expensive than squaring.

The recursive form eliminates exponentiation entirely: the squaring step
`half * half` is always a single big-integer multiply of two equal-sized operands,
which is the cheapest possible multiply for those operand sizes. GMP (underlying both
`gmpy2` and `rug`) is highly optimised for this case.

Additionally, the recursive form is simpler to implement (no level-list construction,
no exponent calculation) and has the same asymptotic complexity.

## Consequences

- Slightly simpler code; no level list or exponent calculation required.
- The squaring step is a single multiply of two equal-sized integers — optimal
  for GMP.
- Level-level parallelism (computing all swing values concurrently across levels)
  is not directly expressed by the recursive structure. In practice this is not a
  bottleneck: the dominant cost is within-level parallelism (swing chunk computation
  via `ProcessPoolExecutor` / `rayon::par_chunks`), which both forms support equally.
- Recursion depth is O(log₂ n) ≈ 23 levels for n = 10^7, well within stack limits.

## Related

- [ADR-0007: Prime swing algorithm for factorial](0007-prime-swing-factorial.md)
