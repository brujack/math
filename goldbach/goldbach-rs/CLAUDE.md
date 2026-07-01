# CLAUDE.md

This file provides guidance to Claude when working with goldbach-rs.

## Overview

Rust CLI that finds all Goldbach pairs for even numbers up to 10^N.

For each even n from 4 to 10^N, streams every pair (p, q) with p ≤ q and p + q = n
to `goldbach_1eN.txt`.

## Build

```bash
make goldbach   # cargo build --release
make lint       # cargo fmt --check + cargo clippy
make test       # lint + cargo test
```

## Code Layout (`src/main.rs`)

- `build_sieve(limit: u64) -> Vec<u64>` — packed bitset of odd composites 3..=limit; bit i → number 2i+3; 1=composite, 0=prime
- `is_prime(n: u64, sieve: &[u64]) -> bool` — O(1) lookup; special-cases 0,1,2, even n; requires n ≤ limit
- `goldbach_pairs<W: Write>(limit, sieve, out) -> io::Result<u64>` — streams all pairs, returns total count
- `prompt_n<R, W>(reader, out) -> io::Result<u64>` — interactive N prompt, validates 1..=8
- `run<R, W, E>(cli, reader, out, err, dir) -> io::Result<i32>` — orchestration
- `main()` — thin wrapper; excluded from tarpaulin with `#[cfg(not(tarpaulin_include))]`

## Important Behavior

- **Sieve:** bit index i represents odd number 2i+3. Never call `is_prime(n, sieve)` with n > sieve's limit — will panic.
- **Pair scan:** for each even n, check p=2 first (is n-2 prime?), then odd p from 3 to n/2.
- **N range:** 1–8. Warns N>6 (output may exceed 20 GB). No hard cap.
- **Output file:** `goldbach_1e{N}.txt` — one pair per line: `n p q` with p ≤ q.
- **Output volume:** N=5 ≈ 285 MB, N=6 ≈ 20 GB, N=7 ≈ 1.4 TB, N=8 ≈ 110 TB.

## Testing

Coverage floor: ≥90% (enforced via `cargo tarpaulin --fail-under 90` in CI).
Current local coverage: 97.30% (72/74 lines).

| Area             | Tests |
| ---------------- | ----- |
| `build_sieve`    | 4     |
| `is_prime`       | 3     |
| `goldbach_pairs` | 4     |
| `run`            | 10    |
