# Twin Primes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Rust binary `twin-primes` that finds all twin prime pairs (p, p+2) where both primes are less than 10^N, writing output to `twin-primes_1e{N}.txt` in the format `p | p+2`.

**Architecture:** Segmented sieve of Eratosthenes over [2, 10^N). Phase 1 computes small primes up to √(10^N) via a simple sieve. Phase 2 processes the remainder in fixed 2^19-number segments, carrying `last_prime` across segment boundaries to catch twin pairs that span a boundary. No parallelism needed — output is sequential and file-streamed.

**Tech Stack:** Rust 2021 edition, clap v4 (CLI), no external C libraries.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `twin-primes/twin-primes-rs/Cargo.toml` | Package manifest |
| Create | `twin-primes/twin-primes-rs/Makefile` | Build/test targets |
| Create | `twin-primes/twin-primes-rs/install_deps.sh` | Dependency installer |
| Create | `twin-primes/twin-primes-rs/src/main.rs` | All logic + tests |
| Create | `twin-primes/twin-primes-rs/CLAUDE.md` | Project guidance |
| Create | `twin-primes/README.md` | Project README |
| Create | `.github/workflows/twin-primes-rs.yml` | CI workflow |
| Modify | `README.md` | Add badge + table row + section |
| Modify | `CLAUDE.md` | Update Overview, CI, Dependency tables |
| Modify | `scripts/pre-commit` | Add lint loop + twin-primes/twin-primes-rs |
| Modify | `docs/superpowers/README.md` | Add plan row |

---

### Task 1: Project scaffold

**Files:**
- Create: `twin-primes/twin-primes-rs/Cargo.toml`
- Create: `twin-primes/twin-primes-rs/Makefile`
- Create: `twin-primes/twin-primes-rs/install_deps.sh`
- Create: `twin-primes/twin-primes-rs/src/main.rs`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p twin-primes/twin-primes-rs/src
```

- [ ] **Step 2: Create `twin-primes/twin-primes-rs/Cargo.toml`**

```toml
[package]
name = "twin-primes"
version = "0.1.0"
edition = "2021"
description = "Find all twin prime pairs up to 10^N — segmented sieve"

[[bin]]
name = "twin-primes"
path = "src/main.rs"

[dependencies]
clap = { version = "4", features = ["derive"] }

[profile.release]
opt-level     = 3
lto           = "thin"
codegen-units = 1
```

- [ ] **Step 3: Create `twin-primes/twin-primes-rs/Makefile`**

```makefile
.PHONY: twin-primes lint test clean

twin-primes:
	cargo build --release
	cp target/release/twin-primes ~/Downloads/twin-primes

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/twin-primes
```

- [ ] **Step 4: Create `twin-primes/twin-primes-rs/install_deps.sh`**

```bash
#!/usr/bin/env bash
# install_deps.sh — install dependencies for twin-primes-rs
#
# Installs:
#   Rust — rustup toolchain + cargo-tarpaulin (build, test, coverage)
#
# No external C libraries required.
#
# Supported platforms:
#   macOS (Apple Silicon & x86_64) — uses Homebrew / rustup
#   Debian / Ubuntu                — uses rustup
#   RHEL / Fedora / CentOS         — uses rustup

set -euo pipefail

install_rust() {
    if command -v cargo >/dev/null 2>&1; then
        echo "==> Rust already installed: $(rustc --version)"
        echo "==> Updating toolchain..."
        rustup update stable
    else
        echo "==> Installing Rust via rustup..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
        # shellcheck source=/dev/null
        source "${HOME}/.cargo/env"
        echo "==> Rust installed: $(rustc --version)"
    fi
}

install_cargo_tarpaulin() {
    if cargo tarpaulin --version >/dev/null 2>&1; then
        echo "==> cargo-tarpaulin already installed: $(cargo tarpaulin --version)"
    else
        echo "==> Installing cargo-tarpaulin (Rust coverage tool)..."
        echo "    This compiles from source and may take a few minutes."
        cargo install cargo-tarpaulin
    fi
}

echo "=== twin-primes-rs dependency installer ==="
echo ""

install_rust

echo ""
install_cargo_tarpaulin

echo ""
echo "==> Verifying installation..."
echo "  rustc     $(rustc --version)  OK"
echo "  cargo     $(cargo --version)  OK"
echo "  tarpaulin $(cargo tarpaulin --version)  OK"

echo ""
echo "All dependencies installed successfully."
echo ""
echo "  make twin-primes — build release binary"
echo "  make test        — run unit tests"
```

- [ ] **Step 5: Create minimal `twin-primes/twin-primes-rs/src/main.rs`**

```rust
fn main() {}
```

- [ ] **Step 6: Verify it compiles**

```bash
cd twin-primes/twin-primes-rs
cargo check
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add twin-primes/
git commit -m "feat: scaffold twin-primes-rs project"
```

---

### Task 2: fmt_int helper

**Files:**
- Modify: `twin-primes/twin-primes-rs/src/main.rs`

- [ ] **Step 1: Write the failing tests**

Replace `src/main.rs` with:

```rust
fn main() {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fmt_int_zero() {
        assert_eq!(fmt_int(0), "0");
    }

    #[test]
    fn test_fmt_int_below_thousand() {
        assert_eq!(fmt_int(999), "999");
    }

    #[test]
    fn test_fmt_int_thousands() {
        assert_eq!(fmt_int(1_000), "1,000");
        assert_eq!(fmt_int(10_000), "10,000");
    }

    #[test]
    fn test_fmt_int_millions() {
        assert_eq!(fmt_int(1_234_567), "1,234,567");
    }
}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd twin-primes/twin-primes-rs
cargo test 2>&1 | head -20
```

Expected: compile error — `fmt_int` not found.

- [ ] **Step 3: Implement fmt_int**

Add above `fn main()`:

```rust
fn fmt_int(n: u64) -> String {
    let s = n.to_string();
    let mut out = String::with_capacity(s.len() + s.len() / 3);
    for (i, ch) in s.chars().rev().enumerate() {
        if i > 0 && i % 3 == 0 {
            out.push(',');
        }
        out.push(ch);
    }
    out.chars().rev().collect()
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cargo test
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add twin-primes/twin-primes-rs/src/main.rs
git commit -m "feat: add fmt_int helper to twin-primes-rs"
```

---

### Task 3: small_sieve

**Files:**
- Modify: `twin-primes/twin-primes-rs/src/main.rs`

- [ ] **Step 1: Write the failing tests**

Add to the `mod tests` block:

```rust
    // --- small_sieve ---

    #[test]
    fn test_small_sieve_empty() {
        assert!(small_sieve(0).is_empty());
        assert!(small_sieve(1).is_empty());
    }

    #[test]
    fn test_small_sieve_two() {
        assert_eq!(small_sieve(2), vec![2u64]);
    }

    #[test]
    fn test_small_sieve_ten() {
        assert_eq!(small_sieve(10), vec![2u64, 3, 5, 7]);
    }

    #[test]
    fn test_small_sieve_thirty() {
        assert_eq!(
            small_sieve(30),
            vec![2u64, 3, 5, 7, 11, 13, 17, 19, 23, 29]
        );
    }

    #[test]
    fn test_small_sieve_count_100() {
        // π(100) = 25
        assert_eq!(small_sieve(100).len(), 25);
    }

    #[test]
    fn test_small_sieve_count_1000() {
        // π(1000) = 168
        assert_eq!(small_sieve(1000).len(), 168);
    }
```

- [ ] **Step 2: Run to confirm compile failure**

```bash
cargo test 2>&1 | head -5
```

Expected: compile error — `small_sieve` not found.

- [ ] **Step 3: Implement small_sieve**

Add above `fn fmt_int`:

```rust
fn small_sieve(limit: u64) -> Vec<u64> {
    let n = limit as usize;
    if n < 2 {
        return vec![];
    }
    let mut composite = vec![false; n + 1];
    composite[0] = true;
    composite[1] = true;
    let mut i = 2usize;
    while i * i <= n {
        if !composite[i] {
            let mut j = i * i;
            while j <= n {
                composite[j] = true;
                j += i;
            }
        }
        i += 1;
    }
    (2..=n).filter(|&i| !composite[i]).map(|i| i as u64).collect()
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cargo test
```

Expected: all tests pass (10 total).

- [ ] **Step 5: Commit**

```bash
git add twin-primes/twin-primes-rs/src/main.rs
git commit -m "feat: add small_sieve to twin-primes-rs"
```

---

### Task 4: sieve_segment

**Files:**
- Modify: `twin-primes/twin-primes-rs/src/main.rs`

- [ ] **Step 1: Add SEG_SIZE constant and write the failing tests**

Add at the top of `src/main.rs` (before any functions):

```rust
/// Number range covered by one sieve segment. 2^19 = 524,288 numbers.
/// Packed bitset (odd numbers only) = 32,768 bytes — fits in L2 cache.
const SEG_SIZE: u64 = 1 << 19;
```

Add to `mod tests`:

```rust
    // --- sieve_segment ---

    #[test]
    fn test_sieve_segment_small() {
        // Primes in [11, 30] given small primes [2,3,5,7].
        let sp = vec![2u64, 3, 5, 7];
        let result = sieve_segment(11, 30, &sp);
        assert_eq!(result, vec![11u64, 13, 17, 19, 23, 29]);
    }

    #[test]
    fn test_sieve_segment_known_range() {
        // Primes in [101, 200]; sqrt(200) < 15 so sieve with primes up to 14.
        let sp = small_sieve(14);
        let result = sieve_segment(101, 200, &sp);
        let expected = vec![
            101u64, 103, 107, 109, 113, 127, 131, 137, 139, 149,
            151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199,
        ];
        assert_eq!(result, expected);
    }

    #[test]
    fn test_sieve_segment_all_odd() {
        // All returned values must be odd (segment starts at odd lo).
        let sp = small_sieve(32);
        let result = sieve_segment(101, 200, &sp);
        assert!(result.iter().all(|&p| p % 2 == 1));
    }

    #[test]
    fn test_sieve_segment_lo_exceeds_limit() {
        // lo > limit → empty.
        let sp = vec![2u64, 3, 5];
        assert!(sieve_segment(101, 100, &sp).is_empty());
    }

    #[test]
    fn test_sieve_segment_single_prime() {
        // lo == limit == 31 (a prime): returns exactly [31].
        let sp = small_sieve(5);
        assert_eq!(sieve_segment(31, 31, &sp), vec![31u64]);
    }
```

- [ ] **Step 2: Run to confirm compile failure**

```bash
cargo test 2>&1 | head -5
```

Expected: compile error — `sieve_segment` not found.

- [ ] **Step 3: Implement sieve_segment**

Add after `small_sieve`:

```rust
/// Sieve odd numbers in [lo, lo + SEG_SIZE) ∩ [lo, limit] using `small_primes`.
///
/// Packed bitset: bit index i ↔ number lo + 2*i. 1 = composite, 0 = prime.
/// `lo` must be odd.
fn sieve_segment(lo: u64, limit: u64, small_primes: &[u64]) -> Vec<u64> {
    let hi = (lo + SEG_SIZE).min(limit + 1); // exclusive
    if lo >= hi {
        return vec![];
    }

    let n = (hi - lo).div_ceil(2) as usize;
    let n_bytes = n.div_ceil(8);
    let mut composite = vec![0u8; n_bytes];

    for &p in small_primes {
        if p == 2 {
            continue;
        }
        let rem = lo % p;
        let mut s = if rem == 0 { lo } else { lo + (p - rem) };
        if s % 2 == 0 {
            s += p;
        }
        if s >= hi {
            continue;
        }
        let mut idx = ((s - lo) / 2) as usize;
        let step = p as usize;
        while idx < n {
            composite[idx >> 3] |= 1u8 << (idx & 7);
            idx += step;
        }
    }

    (0..n)
        .filter(|&i| composite[i >> 3] & (1u8 << (i & 7)) == 0)
        .map(|i| lo + (i as u64) * 2)
        .collect()
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cargo test
```

Expected: all 15 tests pass.

- [ ] **Step 5: Commit**

```bash
git add twin-primes/twin-primes-rs/src/main.rs
git commit -m "feat: add sieve_segment to twin-primes-rs"
```

---

### Task 5: find_twin_primes

**Files:**
- Modify: `twin-primes/twin-primes-rs/src/main.rs`

Add `use std::io::{self, Write};` at the top of `src/main.rs`.

- [ ] **Step 1: Write the failing tests**

Add to `mod tests`:

```rust
    // --- FailWriter ---

    struct FailWriter;
    impl Write for FailWriter {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::new(io::ErrorKind::Other, "write failed"))
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    // --- find_twin_primes ---

    #[test]
    fn test_find_twin_primes_limit_below_5() {
        // No twin pairs possible when limit < 5.
        for limit in [0u64, 1, 2, 3, 4] {
            let mut buf: Vec<u8> = Vec::new();
            let count = find_twin_primes(limit, &mut buf).unwrap();
            assert_eq!(count, 0, "limit={}", limit);
            assert!(buf.is_empty(), "limit={}", limit);
        }
    }

    #[test]
    fn test_find_twin_primes_limit_5_no_pair() {
        // (3,5): 5 is not < 5 → 0 pairs.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(5, &mut buf).unwrap();
        assert_eq!(count, 0);
        assert!(buf.is_empty());
    }

    #[test]
    fn test_find_twin_primes_limit_6_one_pair() {
        // (3,5): both < 6 → 1 pair.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(6, &mut buf).unwrap();
        assert_eq!(count, 1);
        assert_eq!(String::from_utf8(buf).unwrap(), "3 | 5\n");
    }

    #[test]
    fn test_find_twin_primes_n1_exact_output() {
        // N=1, limit=10 → pairs: (3,5) and (5,7).
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(10, &mut buf).unwrap();
        assert_eq!(count, 2);
        assert_eq!(
            String::from_utf8(buf).unwrap(),
            "3 | 5\n5 | 7\n"
        );
    }

    #[test]
    fn test_find_twin_primes_n2_exact_output() {
        // N=2, limit=100 → 8 known pairs.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(100, &mut buf).unwrap();
        assert_eq!(count, 8);
        assert_eq!(
            String::from_utf8(buf).unwrap(),
            "3 | 5\n5 | 7\n11 | 13\n17 | 19\n29 | 31\n41 | 43\n59 | 61\n71 | 73\n"
        );
    }

    #[test]
    fn test_find_twin_primes_n3_count() {
        // N=3, limit=1000 → 35 pairs.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(1_000, &mut buf).unwrap();
        assert_eq!(count, 35);
    }

    #[test]
    fn test_find_twin_primes_n4_count() {
        // N=4, limit=10_000 → 205 pairs.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(10_000, &mut buf).unwrap();
        assert_eq!(count, 205);
    }

    #[test]
    fn test_find_twin_primes_output_lines_match_count() {
        // Line count in output must equal the returned count.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(1_000, &mut buf).unwrap();
        let lines = String::from_utf8(buf).unwrap();
        assert_eq!(lines.lines().count() as u64, count);
    }

    #[test]
    fn test_find_twin_primes_write_error_propagates() {
        let result = find_twin_primes(100, &mut FailWriter);
        assert!(result.is_err());
    }

    #[test]
    fn test_find_twin_primes_idempotent() {
        // Running twice produces identical output.
        let mut buf1: Vec<u8> = Vec::new();
        let mut buf2: Vec<u8> = Vec::new();
        find_twin_primes(1_000, &mut buf1).unwrap();
        find_twin_primes(1_000, &mut buf2).unwrap();
        assert_eq!(buf1, buf2);
    }
```

- [ ] **Step 2: Run to confirm compile failure**

```bash
cargo test 2>&1 | head -5
```

Expected: compile error — `find_twin_primes` not found.

- [ ] **Step 3: Implement find_twin_primes**

Add after `sieve_segment`:

```rust
/// Find all twin prime pairs (p, p+2) where both p and p+2 < limit.
/// Writes "p | p+2\n" per pair to `out`. Returns pair count.
fn find_twin_primes<W: Write>(limit: u64, out: &mut W) -> io::Result<u64> {
    if limit < 5 {
        return Ok(0);
    }

    let sqrt_limit = (limit as f64).sqrt() as u64 + 1;
    let small_primes = small_sieve(sqrt_limit);

    let mut count = 0u64;

    // Twin pairs within the small_primes range (both must be < limit).
    for w in small_primes.windows(2) {
        if w[1] - w[0] == 2 && w[1] < limit {
            writeln!(out, "{} | {}", w[0], w[1])?;
            count += 1;
        }
    }

    // Segmented sieve for (sqrt_limit, limit].
    // lo is always odd; SEG_SIZE is even so lo + SEG_SIZE stays odd.
    let mut last_prime: Option<u64> = small_primes.last().copied();
    let mut lo = sqrt_limit + 1 + (sqrt_limit & 1); // first odd > sqrt_limit

    while lo <= limit {
        let seg = sieve_segment(lo, limit, &small_primes);

        // Boundary: check if last prime from the previous segment + 2 equals
        // the first prime of this segment.
        if let (Some(lp), Some(&fp)) = (last_prime, seg.first()) {
            if fp == lp + 2 && fp < limit {
                writeln!(out, "{} | {}", lp, fp)?;
                count += 1;
            }
        }

        // Twin pairs within this segment.
        for w in seg.windows(2) {
            if w[1] - w[0] == 2 && w[1] < limit {
                writeln!(out, "{} | {}", w[0], w[1])?;
                count += 1;
            }
        }

        last_prime = seg.last().copied().or(last_prime);
        lo += SEG_SIZE;
    }

    Ok(count)
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cargo test
```

Expected: all 25 tests pass.

- [ ] **Step 5: Commit**

```bash
git add twin-primes/twin-primes-rs/src/main.rs
git commit -m "feat: implement find_twin_primes with segmented sieve"
```

---

### Task 6: main() and CLI

**Files:**
- Modify: `twin-primes/twin-primes-rs/src/main.rs`

- [ ] **Step 1: Add imports and CLI struct**

Replace the top of `src/main.rs` (before `const SEG_SIZE`) with:

```rust
use std::fs::File;
use std::io::{self, BufWriter, Write};

use clap::Parser;

#[derive(Parser)]
#[command(
    name = "twin-primes",
    about = "Find all twin prime pairs up to 10^N",
    long_about = "Find all twin prime pairs (p, p+2) where both primes are\n\
                  less than 10^N using a segmented Sieve of Eratosthenes.\n\n\
                  Output is written to twin-primes_1e{N}.txt, one pair per\n\
                  line in the format: p | p+2"
)]
struct Cli {
    /// N: finds every twin prime pair where both p and p+2 < 10^N (max 15)
    digits: u32,
}
```

- [ ] **Step 2: Replace `fn main()`**

```rust
fn main() {
    let cli = Cli::parse();
    let digits = cli.digits;

    if !(1..=15).contains(&digits) {
        eprintln!("Error: N must be between 1 and 15.");
        std::process::exit(1);
    }

    let limit: u64 = 10u64.pow(digits);
    let filename = format!("twin-primes_1e{}.txt", digits);

    println!("Twin Prime Sieve");
    println!("{}", "=".repeat(40));
    println!("Finding twin prime pairs where both p and p+2 < 10^{} = {}", digits, fmt_int(limit));

    let file = File::create(&filename).unwrap_or_else(|e| {
        eprintln!("Error: cannot create {}: {}", filename, e);
        std::process::exit(1);
    });
    let mut writer = BufWriter::new(file);

    let count = find_twin_primes(limit, &mut writer).unwrap_or_else(|e| {
        eprintln!("Error writing output: {}", e);
        std::process::exit(1);
    });

    writer.flush().unwrap_or_else(|e| {
        eprintln!("Error flushing output: {}", e);
        std::process::exit(1);
    });

    println!("Found {} twin prime pairs up to 10^{}", fmt_int(count), digits);
    println!("Saved to {}", filename);
}
```

- [ ] **Step 3: Run tests to confirm they still pass**

```bash
cargo test
```

Expected: all 25 tests pass.

- [ ] **Step 4: Build and do a manual smoke test**

```bash
cargo build --release
./target/release/twin-primes 2
```

Expected output:
```
Twin Prime Sieve
========================================
Finding twin prime pairs where both p and p+2 < 10^2 = 100
Found 8 twin prime pairs up to 10^2
Saved to twin-primes_1e2.txt
```

```bash
cat twin-primes_1e2.txt
```

Expected:
```
3 | 5
5 | 7
11 | 13
17 | 19
29 | 31
41 | 43
59 | 61
71 | 73
```

- [ ] **Step 5: Test error cases**

```bash
./target/release/twin-primes 0     # expect: Error: N must be between 1 and 15.
./target/release/twin-primes 16    # expect: Error: N must be between 1 and 15.
./target/release/twin-primes       # expect: clap usage error
```

- [ ] **Step 6: Commit**

```bash
git add twin-primes/twin-primes-rs/src/main.rs
git commit -m "feat: add main() CLI and file output to twin-primes-rs"
```

---

### Task 7: Project documentation

**Files:**
- Create: `twin-primes/twin-primes-rs/CLAUDE.md`
- Create: `twin-primes/README.md`

- [ ] **Step 1: Create `twin-primes/twin-primes-rs/CLAUDE.md`**

```markdown
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
```

- [ ] **Step 2: Create `twin-primes/README.md`**

```markdown
# twin-primes

Finds every twin prime pair (p, p+2) where both primes are less than 10^N.

## Implementation

- Rust (`twin-primes/twin-primes-rs/`) — segmented Sieve of Eratosthenes; packed bitset segments (32 KB each, fits in L2 cache); memory usage is constant regardless of N.

## Usage

```bash
cd twin-primes/twin-primes-rs
make twin-primes
./target/release/twin-primes <N>
```

Output is written to `twin-primes_1e{N}.txt`, one pair per line:

```
3 | 5
5 | 7
11 | 13
...
```

## Quick Reference

```bash
make twin-primes   # build release binary
make lint          # cargo clippy -- -D warnings
make test          # lint + cargo test
make clean         # remove build artifacts
```
```

- [ ] **Step 3: Commit**

```bash
git add twin-primes/twin-primes-rs/CLAUDE.md twin-primes/README.md
git commit -m "docs: add CLAUDE.md and README for twin-primes-rs"
```

---

### Task 8: CI workflow

**Files:**
- Create: `.github/workflows/twin-primes-rs.yml`

- [ ] **Step 1: Create `.github/workflows/twin-primes-rs.yml`**

```yaml
name: twin-primes-rs

on:
  push:
    branches-ignore:
      - master
  pull_request:
    branches:
      - master

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  test:
    name: Test twin-primes-rs
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: twin-primes/twin-primes-rs
    steps:
      - uses: actions/checkout@v5

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: twin-primes/twin-primes-rs

      - name: Run tests
        run: make test

  build:
    name: Build twin-primes-rs
    runs-on: ubuntu-latest
    needs: [test]
    defaults:
      run:
        working-directory: twin-primes/twin-primes-rs
    steps:
      - uses: actions/checkout@v5

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: twin-primes/twin-primes-rs

      - name: Build
        run: cargo build --release

      - name: Upload artifact
        uses: actions/upload-artifact@v7
        with:
          name: twin-primes
          path: twin-primes/twin-primes-rs/target/release/twin-primes
          retention-days: 7
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/twin-primes-rs.yml
git commit -m "ci: add twin-primes-rs workflow"
```

---

### Task 9: Repo-wide updates

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `scripts/pre-commit`
- Modify: `docs/superpowers/README.md`

- [ ] **Step 1: Update `README.md` — add badge to the top badge line**

In the badge block at the top of `README.md`, add after the `sq-rs` badge:

```markdown
[![twin-primes-rs](https://github.com/brujack/math/actions/workflows/twin-primes-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/twin-primes-rs.yml)
```

- [ ] **Step 2: Update `README.md` — add row to project table**

Add after the `sq/` row in the project table:

```markdown
| [`twin-primes/`](twin-primes/README.md) | Find all twin prime pairs up to 10^N | Rust | [![twin-primes-rs](https://github.com/brujack/math/actions/workflows/twin-primes-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/twin-primes-rs.yml) |
```

- [ ] **Step 3: Update `README.md` — add section**

Add after the `## sq` section:

```markdown
---

## twin-primes

Finds every twin prime pair (p, p+2) where both primes are less than 10^N.

- Rust implementation (`twin-primes/twin-primes-rs/`) — packed bitset segments (32 KB each, fits in L2 cache), constant memory usage regardless of N

See [`twin-primes/README.md`](twin-primes/README.md) for full details.
```

- [ ] **Step 4: Update top-level `CLAUDE.md` — Repository Overview table**

Add after the `sq/` row:

```markdown
| [`twin-primes/`](twin-primes/) | Rust | Find all twin prime pairs up to 10^N | [`twin-primes/twin-primes-rs/CLAUDE.md`](twin-primes/twin-primes-rs/CLAUDE.md) |
```

- [ ] **Step 5: Update top-level `CLAUDE.md` — Dependency Installation table**

Add after the `sq/sq-rs/install_deps.sh` row:

```markdown
| `twin-primes/twin-primes-rs/install_deps.sh` | Rust toolchain, `cargo-tarpaulin` |
```

- [ ] **Step 6: Update top-level `CLAUDE.md` — Quick Reference section**

Add after the `### Rust (sq/sq-rs/)` section:

```markdown
### Rust (`twin-primes/twin-primes-rs/`)

```bash
cd twin-primes/twin-primes-rs
make twin-primes  # cargo build --release
make lint         # cargo clippy -- -D warnings
make test         # lint, then cargo test
```
```

- [ ] **Step 7: Update top-level `CLAUDE.md` — CI table**

Change the CI section count from "Eight workflow files" to "Nine workflow files" and add the row:

```markdown
| twin-primes-rs | `.github/workflows/twin-primes-rs.yml` | test → build + artifact |
```

- [ ] **Step 8: Update `scripts/pre-commit` — add lint loop with all sub-projects**

Replace the entire contents of `scripts/pre-commit` with:

```bash
#!/usr/bin/env bash
set -e

# Run lint for each sub-project that has staged changes
for dir in pi pi/pi-rs prime/prime-rs fib fib/fib-rs sq sq/sq-rs twin-primes/twin-primes-rs; do
    if git diff --cached --name-only | grep -q "^${dir}/"; then
        printf "lint: %s\n" "${dir}"
        make -C "${dir}" lint
    fi
done

if command -v ggshield &>/dev/null; then
    ggshield secret scan pre-commit
fi
```

Then reinstall the hook locally:

```bash
cp scripts/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

- [ ] **Step 9: Update `docs/superpowers/README.md` — add plan row**

Add to the Plans table:

```markdown
| 2026-04-11 | Twin primes | In Progress | [plans/2026-04-11-twin-primes.md](plans/2026-04-11-twin-primes.md) |
```

- [ ] **Step 10: Commit all repo-wide updates**

```bash
git add README.md CLAUDE.md scripts/pre-commit docs/superpowers/README.md
git commit -m "chore: update repo docs and pre-commit for twin-primes-rs"
```
