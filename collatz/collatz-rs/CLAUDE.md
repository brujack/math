# CLAUDE.md

This file provides guidance to Claude when working with collatz-rs.

## Overview

Rust CLI that finds Collatz chain record-setters up to 10^N.

Chain length = steps to reach 1 (not counting the starting number).
Vector memoization: `cache[n] = chain_length(n) + 1` (0 = not computed).

## Build

```bash
make collatz   # cargo build --release (binary in target/release/collatz)
make install   # build, then copy to ${XDG_BIN_HOME:-~/.local/bin}/collatz
make lint      # cargo fmt --check + cargo clippy
make test      # lint + cargo test
```

## Code Layout (`src/lib.rs`, `src/main.rs`)

- `warns_large_n(v: u64) -> bool` — `v > 9`; `run` prints the large-N warning when true
- `collatz_next(n: u64) -> u64` — single Collatz step; uses `n.is_multiple_of(2)` per clippy
- `chain_length(n: u64, cache: &mut [u32], limit: u64) -> u32` — walk, back-fill, return
- `generate_records<W, E>(limit, out, err) -> io::Result<Vec<(u64, u32)>>` — scans 1..=limit, yields records
- `prompt_n<R, W, E>(reader, out, err) -> io::Result<Result<u64, i32>>` — interactive N prompt, loops until valid input; inner `Err(code)` is the exit code (1 at end of input)
- `run<R, W, E>(cli, reader, out, err, dir) -> io::Result<i32>` — orchestration
- `main()` — thin wrapper; excluded from tarpaulin with `#[cfg(not(tarpaulin_include))]`

## Important Behavior

- **Cache:** `Vec<u32>` of size limit+1. At N=9 (1B entries) = 4GB. Warns for N>9 but proceeds.
- **Path values > limit:** counted toward chain length but not stored in cache.
- **End of input:** EOF at the number prompt prints a newline to stdout, then `Error: no input; pass SIZE as an argument (e.g. collatz 5).` to stderr and exits 1 (it used to re-prompt forever on closed stdin).
- **N range:** 1–12. N=10–12 may take hours.
- **Output file:** `collatz_1e{N}.txt` — one record per line: `<n> <chain_length>`.

## Testing

Coverage floor: ≥90% (enforced via `cargo tarpaulin --fail-under 90` in CI).
Current coverage: 98.46% (64/65 lines covered, Linux tarpaulin, 2026-11-17).

| Area               | Tests |
|--------------------|-------|
| `collatz_next`     | 2     |
| `chain_length`     | 6     |
| `generate_records` | 3     |
| `warns_large_n`    | 1     |
| `run`              | 7     |

## Cargo.toml notes

- `[lints.rust] unexpected_cfgs` must include `cfg(tarpaulin_include)` to suppress the unknown-cfg warning from clippy when using `#[cfg(not(tarpaulin_include))]` on `fn main()`.
