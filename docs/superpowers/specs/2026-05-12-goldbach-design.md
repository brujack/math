# Goldbach Pairs — Design Spec

**Date:** 2026-05-12
**Status:** Approved

---

## Overview

For every even number n from 4 to 10^N, find all pairs of primes (p, q) with
p ≤ q and p + q = n. Stream every pair to `goldbach_1eN.txt`, one line per pair.

Goldbach's conjecture (unproven) states every even integer > 2 is the sum of two
primes. This tool verifies the conjecture up to 10^N and produces the complete
pair listing.

---

## Project Structure

```
goldbach/
  goldbach-rs/
    src/main.rs
    Cargo.toml
    rustfmt.toml
    Makefile
    install_deps.sh
    CLAUDE.md
  CLAUDE.md
  README.md
```

Rust only — no Python directory. Matches the `prime/` project pattern (output
volume makes Python impractical).

---

## Algorithm

**Full bitset sieve, then linear pair scan.**

1. Build a packed bitset covering odd numbers 3..=limit.
   - One bit per odd number. Bit index `i` represents `2i + 3`.
   - Word index: `i / 64`. Bit within word: `i % 64`.
   - Composite bits are set to 1 during sieve construction; 0 = prime.
   - Sieve construction: standard Sieve of Eratosthenes over odd numbers only.

2. Define `is_prime(n, sieve)`:
   - n < 2 → false
   - n == 2 → true
   - n even and n > 2 → false
   - n odd → check sieve bit

3. For each even n from 4..=limit (step 2):
   - If `is_prime(n − 2, sieve)`: emit `n 2 n−2`
   - For odd p from 3..=(n/2): if `is_prime(p)` and `is_prime(n−p)`: emit `n p n−p`

4. Stream all output through `BufWriter<File>`. Peak RAM = sieve only.

**Sieve memory:**

| N   | Sieve size |
| --- | ---------- |
| 6   | 6 MB       |
| 7   | 62 MB      |
| 8   | 625 MB     |

---

## Output Format

One line per pair, space-separated, p ≤ q, ordered by n ascending then p ascending:

```
4 2 2
6 3 3
8 3 5
10 3 7
10 5 5
12 5 7
...
100 3 97
100 11 89
100 17 83
100 29 71
100 41 59
100 47 53
...
```

File name: `goldbach_1eN.txt` in the working directory.

**Output volume warning:**

| N   | Approx pairs | Approx file size |
| --- | ------------ | ---------------- |
| 5   | 19 M         | ~285 MB          |
| 6   | 1.3 B        | ~20 GB           |
| 7   | 96 B         | ~1.4 TB          |
| 8   | 7.4 T        | ~110 TB          |

N ≤ 6 is practical. N > 6 is warned at runtime; the program proceeds if the user
chooses to.

Nothing is written to stdout except: a header line, a "writing to file…" note,
and a final summary (`Found X pairs. Saved to goldbach_1eN.txt`).

---

## N Range

Valid: 1–8. Warn for N > 6 that output will likely exceed 20 GB and may take
hours or days. The program proceeds regardless — the user's call.

---

## Rust Implementation

**File:** `goldbach/goldbach-rs/src/main.rs`
**Dependencies:** clap 4 (derive), tempfile (dev only). No GMP — all values fit in u64.

### Functions

- `build_sieve(limit: u64) -> Vec<u64>` — packed bitset of odd composites up to limit; returns sieve words
- `is_prime(n: u64, sieve: &[u64]) -> bool` — O(1) lookup; handles n=0,1,2 and even n as special cases
- `goldbach_pairs<W: Write>(limit: u64, sieve: &[u64], file: &mut W) -> io::Result<u64>` — streams all pairs to `file`, returns total pair count
- `prompt_n<R: BufRead, W: Write>(reader, out) -> io::Result<u64>` — interactive N prompt, validates 1..=8, loops on invalid
- `run<R: BufRead, W: Write, E: Write>(cli, reader, out, err, dir) -> io::Result<i32>` — orchestrates everything, returns exit code
- `main()` — thin wrapper; excluded from tarpaulin with `#[cfg(not(tarpaulin_include))]`

### Cargo.toml

```toml
[package]
name = "goldbach"
version = "0.1.0"
edition = "2021"
description = "Find all Goldbach pairs for even numbers up to 10^N"

[[bin]]
name = "goldbach"
path = "src/main.rs"

[dependencies]
clap = { version = "4", features = ["derive"] }

[dev-dependencies]
tempfile = "3"

[lints.rust]
unexpected_cfgs = { level = "warn", check-cfg = ['cfg(tarpaulin_include)'] }

[profile.release]
opt-level     = 3
lto           = "thin"
codegen-units = 1
```

### Makefile targets

```
goldbach    cargo build --release
lint        ../../scripts/rust-check.sh lint
test        lint + ../../scripts/rust-check.sh test
clean       cargo clean
```

---

## Testing

**Coverage floor:** ≥90% via `cargo tarpaulin --fail-under 90`.

### Known values

- limit=10 → 5 pairs: `(4,2,2), (6,3,3), (8,3,5), (10,3,7), (10,5,5)`
- n=100 → 6 pairs: `(100,3,97), (100,11,89), (100,17,83), (100,29,71), (100,41,59), (100,47,53)`

### Test table

| Area             | Tests                                                                                                                                                 |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build_sieve`    | limit=2 (edge), limit=10 (primes 3,5,7 correct), limit=100 (π(100)=25 primes)                                                                         |
| `is_prime`       | 0,1 → false; 2 → true; 3,5,7 → true; 4,6,9 → false; large prime; large composite                                                                      |
| `goldbach_pairs` | limit=4 (one pair), limit=10 (5 pairs, exact content), pair count return value, output format spot-check                                              |
| `run`            | N=0 → exit 1; N=9 → exit 1; N=1 creates file with correct content; N=2 correct pair count; no-arg prompts; stdout failure → Err; stderr failure → Err |
| `FailWriter`     | injected write failure in tests                                                                                                                       |

---

## CI

One new workflow: `.github/workflows/goldbach-rs.yml`

- Trigger: `pull_request` to `master`; paths: `goldbach/goldbach-rs/**` and the workflow file
- `test` job: checkout@v5, dtolnay/rust-toolchain@stable, Swatinem/rust-cache@v2, `make test`, install cargo-tarpaulin, `cargo tarpaulin --fail-under 90`
- `build` job: `needs: [test]`, `cargo build --release`, `actions/upload-artifact@v5` (7-day retention, artifact name `goldbach`)
- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true`; no GMP install step
- Badge added to `README.md`; `goldbach/goldbach-rs` added to `scripts/pre-commit` and `scripts/pre-push` loops
- Root `CLAUDE.md` updated: Repository Overview table, Dependency Installation table, CI table, Quick Reference

---

## Files Added or Modified

| Action   | Path                                   |
| -------- | -------------------------------------- |
| New      | `goldbach/goldbach-rs/src/main.rs`     |
| New      | `goldbach/goldbach-rs/Cargo.toml`      |
| New      | `goldbach/goldbach-rs/rustfmt.toml`    |
| New      | `goldbach/goldbach-rs/Makefile`        |
| New      | `goldbach/goldbach-rs/install_deps.sh` |
| New      | `goldbach/goldbach-rs/CLAUDE.md`       |
| New      | `goldbach/CLAUDE.md`                   |
| New      | `goldbach/README.md`                   |
| New      | `.github/workflows/goldbach-rs.yml`    |
| Modified | `scripts/pre-commit`                   |
| Modified | `scripts/pre-push`                     |
| Modified | `README.md`                            |
| Modified | `CLAUDE.md`                            |
| Modified | `docs/superpowers/README.md`           |
