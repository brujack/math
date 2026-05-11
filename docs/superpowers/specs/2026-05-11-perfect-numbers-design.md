# Perfect Numbers Design

**Date:** 2026-05-11
**Status:** Pending

---

## Context

A perfect number is a positive integer equal to the sum of its proper divisors (e.g., 6 = 1+2+3). All known even perfect numbers have the form 2^(p−1) × (2^p − 1) where 2^p − 1 is a Mersenne prime (Euler's theorem). No odd perfect numbers are known. This project finds all even perfect numbers up to 10^N by testing candidate Mersenne primes with the Lucas-Lehmer primality test and verifying each result using the multiplicative σ formula.

---

## Scope

- **Valid N range:** 1–54 (N=54 covers the 10th perfect number, ~1.91×10^53, derived from Mersenne prime p=89)
- **Languages:** Python + Rust (same pattern as fib, sq, e, factorial)
- **Not in scope:** odd perfect numbers (none known; conjecture is they don't exist), Mersenne primes beyond p=89

---

## Project Structure

```
perfect-numbers/
├── perfect_numbers.py
├── test_perfect_numbers.py
├── Makefile
├── install_deps.sh
├── CLAUDE.md
├── README.md
└── perfect-numbers-rs/
    ├── src/main.rs
    ├── Cargo.toml
    ├── Makefile
    ├── install_deps.sh
    └── CLAUDE.md
```

---

## Algorithm

### Step 1 — Candidate prime bound

For a given N, derive the maximum p to test: 2^(2p−1) ≤ 10^N implies p ≤ (N × log₂(10) + 1) / 2 ≈ N × 1.661. For N=54 this gives p ≤ 90. All primes p up to this bound are tested.

### Step 2 — Lucas-Lehmer primality test

For each prime p, determine whether M_p = 2^p − 1 is a Mersenne prime using the Lucas-Lehmer test:

```
s₀ = 4
sᵢ = sᵢ₋₁² − 2  mod  M_p    for i = 1, 2, …, p−2
M_p is prime  iff  s_{p−2} = 0
```

For p=89, this requires 87 modular squarings of numbers up to ~10^27. Python's native `pow(s*s - 2, 1, mp)` (or equivalently `(s*s - 2) % mp`) handles this exactly with arbitrary-precision integers. Rust uses `rug::Integer` (GMP).

### Step 3 — Construct and verify

If Lucas-Lehmer passes, construct n = 2^(p−1) × M_p. Filter to n ≤ 10^N.

Verify n is perfect using the multiplicative σ formula:

```
σ(2^(p−1) × M_p) = σ(2^(p−1)) × σ(M_p)
                  = (2^p − 1) × (M_p + 1)
                  = (2^p − 1) × 2^p
                  = 2 × 2^(p−1) × M_p
                  = 2n  ✓
```

This is exact arithmetic — no approximation. The verification passes for every valid Mersenne prime by construction, making any failure a signal of an arithmetic bug.

---

## Python Implementation

**File:** `perfect_numbers.py`

No external dependencies — Python's built-in `int` handles arbitrary precision through p=89.

Functions:

| Function                   | Signature                              | Description                                                                                                   |
| -------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `is_prime`                 | `(n: int) -> bool`                     | Trial division up to √n; only called for p ≤ 90, always fast                                                  |
| `lucas_lehmer`             | `(p: int) -> bool`                     | Runs the recurrence using `pow`-based modular arithmetic                                                      |
| `verify_perfect`           | `(p: int) -> bool`                     | Computes σ(n) via the closed-form formula; returns True iff σ(n) == 2n                                        |
| `generate_perfect_numbers` | `(limit: int) -> Iterator[(int, int)]` | Yields (p, n) pairs for all perfect numbers n ≤ limit                                                         |
| `get_exponent`             | `(args) -> int`                        | Validates N in [1, 54]; interactive prompt if no CLI arg; `sys.exit(1)` for out-of-range                      |
| `main`                     | `() -> None`                           | Entry point; saves to `perfect-numbers_1eN.txt`; error handlers for `KeyboardInterrupt` and `PermissionError` |

**install_deps.sh** installs `ruff` and `coverage` only (no GMP needed).

---

## Rust Implementation

**File:** `perfect-numbers-rs/src/main.rs`

Uses `rug::Integer` for arbitrary-precision arithmetic (same GMP dependency as pi-rs, e-rs, factorial-rs).

Functions:

| Function                   | Signature                                  | Description                                                    |
| -------------------------- | ------------------------------------------ | -------------------------------------------------------------- |
| `is_prime`                 | `(n: u64) -> bool`                         | Trial division; only called for p ≤ 90                         |
| `lucas_lehmer`             | `(p: u64) -> bool`                         | Recurrence using `rug::Integer` modular squaring               |
| `verify_perfect`           | `(p: u64) -> bool`                         | σ formula in big-integer arithmetic                            |
| `generate_perfect_numbers` | `(limit: &Integer) -> Vec<(u64, Integer)>` | Collects all (p, n) with n ≤ limit                             |
| `run<R, W, E>`             | standard injectable-IO pattern             | Orchestration; returns `io::Result<i32>`; always saves to file |
| `main`                     | thin wrapper                               | Locks stdio, calls `run`, exits with returned code             |

**Cli struct:** one optional positional `exponent: Option<u32>`.

**Cargo.toml dependencies:** `rug` (features = ["integer"]), `clap`, `tempfile` (dev).

**install_deps.sh** installs GMP + MPFR (required by rug), Rust toolchain, `cargo-tarpaulin`.

---

## Output Format

**File `perfect-numbers_1eN.txt`:** one perfect number per line, decimal string, no metadata:

```
6
28
496
8128
33550336
```

**Console output** during the run (both Python and Rust):

```
Perfect Number Finder
========================================
Finding perfect numbers up to 10^8 = 100,000,000

p=2: M_2=3 [Mersenne prime] -> 6 (1 digit, verified)
p=3: M_3=7 [Mersenne prime] -> 28 (2 digits, verified)
p=5: M_5=31 [Mersenne prime] -> 496 (3 digits, verified)
p=7: M_7=127 [Mersenne prime] -> 8128 (4 digits, verified)
p=11: M_11=2047 [not prime]
p=13: M_13=8191 [Mersenne prime] -> 33550336 (8 digits, verified)
p=17: M_17=131071 [Mersenne prime] -> 8589869056 (10 digits, exceeds limit)

Found 5 perfect numbers up to 10^8
Saved to perfect-numbers_1e8.txt
```

---

## Testing

### Python

| Test class                   | Coverage                                                                                       |
| ---------------------------- | ---------------------------------------------------------------------------------------------- |
| `TestIsPrime`                | 0, 1, 2, small primes, composites, large prime, boundary                                       |
| `TestLucasLehmer`            | pass: p=2,3,5,7,13,17,19,31; fail: p=11,23,29,37                                               |
| `TestVerifyPerfect`          | p=2,3,5,7,13,17,19; verify σ(n)=2n exactly                                                     |
| `TestGeneratePerfectNumbers` | N=1 → [6], N=4 → first 5, N=0 → empty, N=54 → 10 results                                       |
| `TestGetExponent`            | valid bounds (1, 54), exit on 0, exit on 55, interactive prompt                                |
| `TestMain`                   | N=1 saves file, N=54 file has 10 lines, `KeyboardInterrupt` exits 1, `PermissionError` exits 1 |

### Rust

Unit tests in `#[cfg(test)] mod tests`:

- `is_prime`: known primes and composites up to 100
- `lucas_lehmer`: same pass/fail set as Python
- `verify_perfect`: first 7 known Mersenne exponents
- `generate_perfect_numbers`: N=1, N=8, empty limit
- `run`: N=0 → exit 1, N=1 → creates file, no-arg → prompt

Integration tests in `tests/cli.rs`:

- `cli_arg_zero_exits_one`
- `cli_arg_one_creates_file`
- `cli_no_arg_prompts`
- `cli_unwritable_output_dir`

**Coverage floor:** ≥90% line coverage for Rust (enforced via `cargo tarpaulin --fail-under 90`).

---

## CI

Add two workflow files following the existing pattern:

- `.github/workflows/perfect-numbers-py.yml` — test job (lint + unittest)
- `.github/workflows/perfect-numbers-rs.yml` — test job (lint + cargo test + tarpaulin) → build job (artifact upload)

Add paths-filter entries to the existing `auto-merge.yml` ci-gate.

Add both directories to the loops in `scripts/pre-commit` and `scripts/pre-push`.

Add badge to `README.md`.

---

## Known Perfect Numbers (Reference)

| p   | Digits in n | Perfect number n                                       |
| --- | ----------- | ------------------------------------------------------ |
| 2   | 1           | 6                                                      |
| 3   | 2           | 28                                                     |
| 5   | 3           | 496                                                    |
| 7   | 4           | 8128                                                   |
| 13  | 8           | 33550336                                               |
| 17  | 10          | 8589869056                                             |
| 19  | 12          | 137438691328                                           |
| 31  | 19          | 2305843008139952128                                    |
| 61  | 37          | 2658455991569831744654692615953842176                  |
| 89  | 54          | 191561942608236107294793378084303638130997321548169216 |
