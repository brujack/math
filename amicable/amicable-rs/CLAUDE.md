# CLAUDE.md

## Repository Overview

Rust CLI that finds all amicable pairs (a, b) with a < b and b ≤ 10^N.
Injectable I/O pattern: `run<W,E>(stdout, stderr, out_path, limit)`.
`fn main()` is a thin clap wrapper excluded from tarpaulin.

## Running

```bash
make amicable  # cargo build --release
make lint      # cargo fmt --check + clippy -D warnings
make test      # lint + cargo test
```

## Code Layout

- `proper_divisor_sum_sieve(limit)` — returns Vec<u32>, length limit+1
- `run<W,E>(stdout, stderr, out_path, limit)` — builds sieve, scans pairs, writes to stdout + file
- `main()` — clap arg parse; excluded from tarpaulin via #[cfg(not(tarpaulin_include))]

## Important Behavior

- **Valid N range:** 1–8 (clap enforces via `.range(1..=8)`). Python CLI caps at 7 due to memory; Rust uses Vec<u32> so N=8 (400MB) is fine.
- **Output file:** `amicable_1eN.txt` written to current directory.

## Coverage

≥90% on Linux CI. macOS tarpaulin typically runs ~10pp higher.
Set the `--fail-under` gate from the actual CI Linux figure, not local macOS.
