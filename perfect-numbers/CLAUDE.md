# CLAUDE.md

This file provides guidance to Claude when working with code in this directory.

## Repository Overview

This directory contains a Python CLI for finding all perfect numbers up to 10^N.

A perfect number equals the sum of its proper divisors (e.g., 6 = 1+2+3).
All known even perfect numbers have the form 2^(p-1) × (2^p − 1) where
2^p − 1 is a Mersenne prime (Euler's theorem). This program uses the
Lucas-Lehmer primality test to find Mersenne primes and the multiplicative
sigma formula to verify perfect-ness.

Current structure:

- `perfect_numbers.py` — interactive CLI (Python, built-in integers, no external deps)
- `perfect-numbers-rs/` — Rust implementation using rug/GMP for big-integer arithmetic
- `install_deps.sh` — installs ruff and coverage
- `test_perfect_numbers.py` — unit tests

## Running the Script

```bash
make run       # python3 perfect_numbers.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_perfect_numbers -v
make coverage  # run tests and print coverage report
```

Or directly:

```bash
python3 perfect_numbers.py        # interactive prompt
python3 perfect_numbers.py 8      # find perfect numbers up to 10^8
```

## Code Layout

- `is_prime(n)` — trial division up to √n; only called for p ≤ 90
- `lucas_lehmer(p)` — Lucas-Lehmer test: s₀=4; sᵢ=sᵢ₋₁²−2 mod Mₚ; Mₚ prime iff s\_{p-2}=0
- `verify_perfect(p)` — confirms σ(n) = (2^p−1)×2^p = 2n using multiplicative formula
- `generate_perfect_numbers(limit)` — generator yielding (p, n) pairs for all perfect n ≤ limit
- `parse_args()` — argparse with optional positional N
- `get_exponent(args)` — validates N in [1, 54]; interactive prompt if no CLI arg
- `main()` — entry point: prints each p tested, saves to `perfect-numbers_1eN.txt`

## Important Behavior

- **Valid N range:** 1–54. N=54 covers all 10 known perfect numbers (up to ~1.91×10^53).
- **Output file:** `perfect-numbers_1eN.txt` — one perfect number per line, decimal string.
- **No external dependencies:** uses Python built-in arbitrary-precision integers throughout.
- **Algorithm:** tests all primes p up to (N×log₂10+1)/2 ≈ N×1.66; Lucas-Lehmer for each.

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass.

```bash
make test      # lint + unittest
make coverage  # coverage run + report
```

### Test coverage (≥90% target)

| Class                        | Tests | Notes                                                                     |
| ---------------------------- | ----- | ------------------------------------------------------------------------- |
| `TestIsPrime`                | 9     | 0, 1, negative, 2, even composite, small primes, composites, 89, 91       |
| `TestLucasLehmer`            | 3     | p=2 special case; pass: [3,5,7,13,17,19,31,61,89]; fail: [11,23,29,37,41] |
| `TestVerifyPerfect`          | 2     | known exponents p=2..19; algebraic sigma==2n check                        |
| `TestGeneratePerfectNumbers` | 6     | empty, N=1, N=4, N=8, N=54 (all 10), ascending order                      |
| `TestGetExponent`            | 8     | valid min/max/mid, exit on 0/55/negative, interactive prompt              |
| `TestMain`                   | 4     | N=1 file, N=4 file, KeyboardInterrupt exits 1, PermissionError exits 1    |

## Keeping This File Up To Date

Update whenever you:

- Add or rename a function → update Code Layout
- Add or remove a Makefile target → update Running section
- Add test classes or change coverage → update Testing table
