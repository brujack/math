# CLAUDE.md

This file provides guidance to Claude when working with code in this directory.

## Repository Overview

This directory contains a Rust CLI for finding all perfect numbers up to 10^N.

Uses the Lucas-Lehmer Mersenne primality test and the multiplicative sigma
formula. Valid N range: 1–54 (covers all 10 known perfect numbers).

## Build

```bash
cd perfect-numbers-rs
make perfect-numbers  # cargo build --release
make lint             # cargo fmt --check + clippy
make test             # lint + cargo test
```

## Code Layout (`src/main.rs`)

- `is_prime(n: u64)` — trial division; only called for p ≤ 90
- `lucas_lehmer(p: u64)` — Lucas-Lehmer test using `rug::Integer` modular squaring
- `verify_perfect(p: u64)` — σ formula: σ(n) = (2^p−1)×2^p = 2n
- `generate_perfect_numbers(limit: &Integer)` — collects all (p, n) with n ≤ limit (test-only)
- `read_line_from<R: BufRead>` — reads one trimmed line
- `prompt_n_with<R, W, E>` — interactive N prompt, loops until valid
- `run<R, W, E>(cli, reader, out, err, dir)` — orchestration; returns `io::Result<i32>`
- `main()` — thin stdio wrapper; excluded from tarpaulin with `#[cfg(not(tarpaulin_include))]`

## Testing

Coverage floor: ≥90% (enforced via `cargo tarpaulin --fail-under 90` in CI).

| Area                       | Tests | Notes                                                                                        |
| -------------------------- | ----- | -------------------------------------------------------------------------------------------- |
| `is_prime`                 | 6     | 0, 1, 2, 4, small primes, composites                                                         |
| `lucas_lehmer`             | 2     | known Mersenne primes; known failures                                                        |
| `verify_perfect`           | 1     | p=2..19                                                                                      |
| `generate_perfect_numbers` | 5     | empty, N=1, N=4, N=6 boundary, N=54 (all 10)                                                 |
| `run`                      | 6     | N=0 exit 1, N=55 exit 1, N=1 creates file, no-arg prompts, reject-0-then-accept, N=4 finds 4 |
| injection                  | 2     | stdout failure, stderr failure                                                               |
| `tests/cli.rs`             | 4     | arg=0 exit 1, arg=1 creates file, no-arg prompts, unwritable dir                             |

## Keeping This File Up To Date

Update whenever you change a function signature, add tests, or change coverage %.
