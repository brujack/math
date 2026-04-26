# CLAUDE.md

This file provides guidance to Claude when working with twin-primes-rs.

## Overview

Rust CLI that finds all twin prime pairs (p, p+2) where both primes are less
than 10^N using a segmented Sieve of Eratosthenes.

## Algorithm

Two-phase segmented sieve:

**Phase 1** — `small_sieve(√(10^N))` produces small primes used to cross off
composites in phase 2.

**Phase 2** — range (√(10^N), 10^N] is processed in `SEG_SIZE` = 2^19-number
segments. Each segment is a packed bitset (1 bit per odd number, 32 KB).
`last_prime` is carried across segment boundaries to detect twin pairs that
span the boundary.

## Build

```bash
cd twin-primes/twin-primes-rs
make twin-primes   # cargo build --release, copies to ~/Downloads/twin-primes
make test          # lint + cargo test
```

## Code Layout (`src/main.rs`)

Constants:

- `SEG_SIZE` (`u64`, 2^19): segment size; keeps packed bitset in L2 cache.

Functions:

- `fn small_sieve(limit)` → `Vec<u64>`: simple Eratosthenes sieve of [2, limit].
- `fn sieve_segment(lo, limit, small_primes)` → `Vec<u64>`: sieves one segment [lo, lo+SEG_SIZE) ∩ [lo, limit]. `lo` must be odd.
- `fn find_twin_primes<W: Write>(limit, out)` → `io::Result<u64>`: orchestrates both phases; writes `p | p+2\n` pairs; returns count.
- `fn fmt_int(n)` → `String`: formats u64 with thousands separators.
- `fn main()`: parses CLI arg N (1–15), calls find_twin_primes, writes to `twin-primes_1e{N}.txt`.

## Important Implementation Details

- `last_prime` tracks the most recent prime seen across segment boundaries. At the start of each segment, check if `last_prime + 2 == first_prime_of_segment` to catch pairs spanning the boundary.
- Twin pair condition: both `p` and `p+2` must be **strictly less than** `limit` — the check is `w[1] < limit` (where `w[1]` is `p+2`).
- `lo` must always be odd. The formula `sqrt_limit + 1 + (sqrt_limit & 1)` guarantees this for the initial value. Since SEG_SIZE (2^19) is even, `lo += SEG_SIZE` preserves oddness.
- `find_twin_primes` returns early with 0 for `limit < 5` (no twin pairs possible).

## Testing

Tests in `#[cfg(test)] mod tests`. Run with `make test`.

### Test coverage (76% line coverage, 25 tests)

Below the project standard of >=90% — `write_twin_primes_file`, `prompt_exponent` / `read_line` (interactive stdin), and `main()` are integration-level uncovered.

Known twin prime counts:

- N=1 (limit=10): 2 pairs — (3,5),(5,7)
- N=2 (limit=100): 8 pairs
- N=3 (limit=1,000): 35 pairs
- N=4 (limit=10,000): 205 pairs

## Editing Guidance

- Do not change `SEG_SIZE` without profiling — 2^19 keeps the 32 KB bitset in L2.
- `sieve_segment` assumes `lo` is odd; callers must ensure this.
- Generated output files (`twin-primes_1e*.txt`) can be large — do not commit them.
- Write the failing test first for all new or changed functions.

## Keeping This File Up To Date

Update when:

- Function renamed or signature changed → update Code Layout
- Makefile target added/removed → update Build section + top-level CLAUDE.md
- Dependency added → update install_deps.sh + this file
- Test counts change → update Testing section
