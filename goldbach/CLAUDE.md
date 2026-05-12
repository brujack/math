# CLAUDE.md

This file provides guidance to Claude when working with code in this directory.

## Repository Overview

Rust CLI that finds all Goldbach pairs for even numbers up to 10^N.

A Goldbach pair for even n is (p, q) with p ≤ q and p + q = n, both prime.
Goldbach's conjecture (unproven) states every even n > 2 has at least one pair.

No Python implementation — output volume makes Python impractical.

- `goldbach-rs/` — Rust implementation using packed bitset sieve

## Code Layout

### `goldbach-rs/src/main.rs`

- `main()` — thin CLI wrapper; sources Goldbach computation from `run()`
- `run<W, E>(dir: &str, out: &mut W, err: &mut E)` — injectable I/O pattern; computes and streams Goldbach pairs via BufWriter
- Sieve construction — packed bitset for primes up to sqrt(10^N)
- Pair iteration — for each even k, walk primes p ≤ k/2, check if k-p is also prime
- Output format — one pair per line: `k: p, q` where p + q = k

## Testing

All tests in `src/main.rs` via `#[cfg(test)] mod tests`.

Test categories:

- **Boundary values:** n=2 (smallest even), single pairs, exact boundary n=limit
- **Error paths:** I/O failures, invalid arguments, out-of-range N
- **State:** output count and format verification, idempotency (same input same output)

Run: `make test`

**Coverage floor: ≥90% line coverage via `cargo tarpaulin` in CI.** See parent `CLAUDE.md` for patterns to keep Rust crates above 90% after cargo fmt changes.

## Makefile Targets

- `make goldbach` — `cargo build --release`
- `make lint` — `cargo fmt --check`, then `cargo clippy --all-targets -- -D warnings`
- `make test` — lint, then `cargo test`

## Implementation Notes

**Practical limits:** Output grows to ~20 GB at N=6. Tests use N≤3 for speed; release builds support N≤6.

**Bitset optimization:** Packed u64 bitset keeps memory footprint low and iteration fast (two bits per number).

**Prime marking:** Sieve of Eratosthenes; pairs found by checking both p and (k-p) in the bitset.
