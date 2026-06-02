# ADR 0013: Hypothesis and proptest for property-based testing

- **Date:** 2026-05-18
- **Status:** Accepted

## Context

Unit tests with hand-chosen inputs miss boundary cases that property-based testing finds automatically. Mathematical functions — factorial, primes, π digits — have well-defined properties: recurrence relations, monotonicity, invertibility, invariants. These are ideal targets for property-based testing.

Example discovery: Hypothesis found a real bug in amicable/perfect-numbers oracles where `assertLess` was used when the contract requires `assertLessEqual`. Hypothesis reliably generates the boundary value (`result == limit`) which hand-chosen inputs rarely hit. The mutation testing ADR describes the gap coverage leaves; property testing closes part of that gap automatically.

## Decision

Add property-based tests to all sub-projects:

**Python: Hypothesis**

```python
from hypothesis import given, settings
from hypothesis import strategies as st

@given(st.integers(min_value=1, max_value=50))
@settings(deadline=None)
def test_recurrence(self, n):
    self.assertEqual(calculate_factorial(n), n * calculate_factorial(n - 1))
```

`@settings(deadline=None)` is required for all math functions. Large-number computation (factorial(50), pi digits, prime generation) exceeds Hypothesis's default 200ms per-example deadline on CI machines. Without `deadline=None`, tests pass locally (fast hardware) and fail in CI with `DeadlineExceeded`.

**Rust: proptest**

```rust
proptest! {
    #[test]
    fn test_factorial_recurrence(n in 1u64..=20u64) {
        assert_eq!(factorial(n), n * factorial(n - 1));
    }
}
```

Input ranges must be bounded — `0u64..=1_000u64` or tighter for expensive algorithms. Unbounded ranges produce multi-second runs or overflow.

**Properties to test (priority order):**

1. Recurrence relations: `f(n) == f(n-1) * n` (factorial), `f(n) == f(n-1) + f(n-2)` (Fibonacci-like)
2. Invariants: result is positive, result is monotonically non-decreasing
3. Roundtrips: `decode(encode(x)) == x`
4. Idempotency: `f(f(x)) == f(x)` where applicable

Property tests are additive — they do not replace boundary or error-path tests.

## Consequences

- Hypothesis finds boundary cases automatically (discovered `assertLess` vs `assertLessEqual` bug in amicable numbers)
- `deadline=None` required everywhere for Python — CI machines are slower than local
- Rust proptest input bounds required — unbounded ranges produce excessive runtimes
- Property tests run as part of `make test` alongside unit tests — no separate target needed
- `hypothesis` and `proptest` added as dev dependencies in all sub-projects

## Related

- ADR 0012: Python mutation testing with mutmut
- ADR 0015: Pyright type checking for Python sub-projects
- `.claude/standards/tdd.md`: property-based test requirements and oracle correctness
- `.claude/standards/python.md`: Hypothesis deadline and oracle guidance
