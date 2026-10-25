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
- `install_deps.sh` — rendered from `scripts/crate_templates/python/install_deps.sh`: GMP + MPFR (Homebrew, apt or dnf/yum) and every pinned Python package
- `test_perfect_numbers.py` — unit tests

## Running the Script

```bash
make run       # python3 perfect_numbers.py
make lint      # ruff check .
make test      # lint, then pytest test_perfect_numbers.py -v
make coverage  # run tests and print coverage report
```

Or directly:

```bash
python3 perfect_numbers.py        # interactive prompt (terminal only; bare non-TTY run exits 2)
python3 perfect_numbers.py 8      # find perfect numbers up to 10^8
python3 perfect_numbers.py 8 --show   # also print each perfect number
python3 perfect_numbers.py --smoke    # quick check at SMOKE_SIZE (6)
```

## Code Layout

- `is_prime(n)` — trial division up to √n; only called for p ≤ 90
- `lucas_lehmer(p)` — Lucas-Lehmer test: s₀=4; sᵢ=sᵢ₋₁²−2 mod Mₚ; Mₚ prime iff s\_{p-2}=0
- `verify_perfect(p)` — confirms σ(n) = (2^p−1)×2^p = 2n using multiplicative formula
- `generate_perfect_numbers(limit)` — generator yielding (p, n) pairs for all perfect n ≤ limit
- `SMOKE_SIZE = 6`, `LARGE_RUN_THRESHOLD = None` — CLI contract constants (`scripts/cli_contract.py`, run by `make test`)
- `parse_args(argv)` — argparse: optional positional N, `--show`, `--yes` (no-op here), `--smoke`
- `refuse_large_run(size, yes)` — exits 1 naming `--yes` past the threshold (none for this program)
- `get_exponent(args)` — validates `args.size` in [1, 54]; interactive prompt if none; EOF at the prompt exits 1
- `main(argv)` — entry point: prints each p tested, saves to `perfect-numbers_1eN.txt`; `--show` prints each perfect number after the summary

## Important Behavior

- **Valid N range:** 1–54. N=54 covers all 10 known perfect numbers (up to ~1.91×10^53).
- **Output file:** `perfect-numbers_1eN.txt` — one perfect number per line, decimal string.
- **No external dependencies:** uses Python built-in arbitrary-precision integers throughout.
- **Algorithm:** tests all primes p up to (N×log₂10+1)/2 ≈ N×1.66; Lucas-Lehmer for each.

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass.

```bash
make test      # lint + unittest
make coverage  # pytest --cov, fails under 90%
```

### Test coverage (≥90% target)

63 tests total, 38 subtests.

| Class                          | Tests | Notes                                                                                        |
| ------------------------------ | ----- | -------------------------------------------------------------------------------------------- |
| `TestIsPrime`                  | 9     | 0, 1, negative, 2, even composite, small primes, composites, 89, 91                          |
| `TestLucasLehmer`              | 3     | p=2 special case; pass: [3,5,7,13,17,19,31,61,89]; fail: [11,23,29,37,41]                    |
| `TestVerifyPerfect`            | 2     | known exponents p=2..19; algebraic sigma==2n check                                           |
| `TestGeneratePerfectNumbers`   | 8     | empty, N=1, N=4, N=8, N=54 (all 10), ascending order, exact boundary at 6 and 28             |
| `TestGetExponent`              | 15    | valid min/max/mid, exit on 0/55/negative (with exit-code assertions), interactive boundaries |
| `TestCliContractConstants`     | 2     | SMOKE_SIZE = 6, LARGE_RUN_THRESHOLD is None                                                  |
| `TestParseArgs`                | 6     | size, --show, --smoke, --smoke with SIZE (exit 2), bare non-TTY (exit 2), bare TTY           |
| `TestRefuseLargeRun`           | 4     | no threshold, at/below threshold, --yes                                                      |
| `TestInteractiveEof`           | 1     | EOF at prompt exits 1 with message                                                           |
| `TestShow`                     | 5     | --show prints numbers before summary, absent without it, refusal before write, smoke                                     |
| `TestMain`                     | 4     | N=1 file, N=4 file, KeyboardInterrupt exits 1, PermissionError exits 1                       |
| `TestPerfectNumbersProperties` | 3     | property tests: positive, below limit, even-composites not prime                             |
| `TestEntryPointGuard`          | 1     | module runs via subprocess                                                                   |

## Equivalent mutants

`cosmic-ray.toml` is rendered from a template and carries no prose; these mutants cannot be killed by any valid input:

- `lucas_lehmer`: `s == 0` to `s <= 0` (`s` is a residue mod `mp`, never negative); `p == 2` to `p <= 2` (callers never pass `p < 2`, `is_prime` rejects them).
- `verify_perfect`: `sigma == 2 * n` to `<=` or `>=` still returns True, because Euler's identity gives `sigma == 2n` for every Mersenne exponent; a mutation that makes `mp` 0 gives `0 == 0`. (`<`, `>` and `!=` return False and are killable.)
- `is_prime`: `n == 2` to `n <= 2` (`n < 2` returned earlier); `n % 2 == 0` and `n % i == 0` to `<= 0` (remainders are non-negative); `i += 2` to `i += 1` (`n` is odd here, so even `i` never divides it); `i * i <= n` to `i + i <= n` (extra iterations only).
- `generate_perfect_numbers`: `limit < 6` to `limit < 5` (`limit == 5` enters the loop, and `p = 2` gives 6 > 5, so it yields nothing, as before).
- `__name__ == "__main__"` guard: `<=` and `is` behave identically.
- `print("=" * 40)` in `main()`: the banner width is cosmetic.

## Keeping This File Up To Date

Update whenever you:

- Add or rename a function → update Code Layout
- Add or remove a Makefile target → update Running section
- Add test classes or change coverage → update Testing table
