# CLAUDE.md

This file provides guidance to Claude when working with collatz-rs.

## Overview

Rust CLI that finds Collatz chain record-setters up to 10^N.

Chain length = steps to reach 1 (not counting the starting number).
Vector memoization: `cache[n] = chain_length(n) + 1` (0 = not computed).

## Build

```bash
make collatz   # cargo build --release
make lint      # cargo fmt --check + cargo clippy
make test      # lint + cargo test
```

## Code Layout (`src/main.rs`)

- `collatz_next(n: u64) -> u64` — single Collatz step; uses `n.is_multiple_of(2)` per clippy
- `chain_length(n: u64, cache: &mut [u32], limit: u64) -> u32` — walk, back-fill, return
- `generate_records<W, E>(limit, out, err) -> io::Result<Vec<(u64, u32)>>` — scans 1..=limit, yields records
- `prompt_n<R, W>(reader, out) -> io::Result<u64>` — interactive N prompt, loops until valid input
- `run<R, W, E>(cli, reader, out, err, dir) -> io::Result<i32>` — orchestration
- `main()` — thin wrapper; excluded from tarpaulin with `#[cfg(not(tarpaulin_include))]`

## Important Behavior

- **Cache:** `Vec<u32>` of size limit+1. At N=9 (1B entries) = 4GB. Warns for N>9 but proceeds.
- **Path values > limit:** counted toward chain length but not stored in cache.
- **N range:** 1–12. N=10–12 may take hours.
- **Output file:** `collatz_1e{N}.txt` — one record per line: `<n> <chain_length>`.

## Testing

Coverage floor: ≥90% (enforced via `cargo tarpaulin --fail-under 90` in CI).
Current coverage: 96.72% (59/61 lines covered, macOS tarpaulin).

| Area               | Tests |
|--------------------|-------|
| `collatz_next`     | 2     |
| `chain_length`     | 6     |
| `generate_records` | 2     |
| `run`              | 7     |

## Cargo.toml notes

- `[lints.rust] unexpected_cfgs` must include `cfg(tarpaulin_include)` to suppress the unknown-cfg warning from clippy when using `#[cfg(not(tarpaulin_include))]` on `fn main()`.
