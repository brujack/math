# Prime Number Sieve

Find every prime number up to 10^N using a **parallel segmented Sieve of Eratosthenes** implemented in Rust with rayon.

| | |
|---|---|
| **Implementation** | Rust (`prime-rs/`) |
| **Algorithm** | Segmented Sieve of Eratosthenes |
| **Parallelism** | `rayon::par_iter` across sieve segments |
| **Memory** | Packed bitset — 32 KB per segment (fits in L2 cache) |
| **Output** | Streams to file — peak RAM ≤ ~50 MB regardless of N |

---

## Dependencies

Only Rust is required (no external C libraries):

```bash
# macOS
brew install rust

# Or via rustup (all platforms)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

---

## Build

```bash
cd prime-rs
make prime       # cargo build --release, copies binary to ~/Downloads/prime
```

Or manually:

```bash
cd prime-rs
cargo build --release
./target/release/prime [N]
```

### Makefile targets

| Target | Description |
|--------|-------------|
| `make prime` | Build release binary and copy to `~/Downloads/prime` |
| `make clean` | Remove build artifacts and `~/Downloads/prime` |

### Tests

```bash
cd prime-rs
cargo test
```

22 tests, 56% line coverage.  Covers `fmt_int`, `small_sieve` (empty, known lists, π(100)=25, π(1000)=168), `sieve_segment` (known range, no even numbers, empty-when-lo-exceeds-limit), and `find_primes` end-to-end (exact output for small inputs, π(10^6)=78,498, last prime = 999,983, no even non-2 primes).

Uncovered lines are the progress thread, interactive `prompt_digits` / `read_line`, and `main()` — all integration-level only.

Check coverage (requires `cargo-tarpaulin`):

```bash
cargo install cargo-tarpaulin   # one-time install
cargo tarpaulin --out Stdout
```

---

## Usage

```
./target/release/prime [N]
```

Run without arguments for interactive prompts, or pass N directly:

```bash
./target/release/prime 9    # all primes up to 1,000,000,000
```

### Flags

| Flag | Description |
|------|-------------|
| `N` | Find all primes up to 10^N (positional, optional; max 18) |
| `-h` | Show brief help |
| `--help` | Show full help |

### Output behaviour

| N | Primes found | Behaviour |
|---|-------------|-----------|
| ≤ 6 | ≤ 78,498 | Buffered in memory; user prompted to display or save |
| 7–10 | up to ~455 M | Streamed to `primes_1eN.txt` automatically |
| ≥ 11 | billions | Warning shown; user must confirm before proceeding |

---

## Example

```
$ ./target/release/prime 9
Prime Number Sieve (Rust/Rayon)
========================================
Finding all primes up to 10^9 = 1,000,000,000
Backend: segmented sieve / packed bitset / rayon (20 threads)
  Phase 1: sieve [2, 31,623] … 3,401 primes  (0.001s)
  Phase 2: 100%  (999,968,378 numbers sieved)  847.3 M/s

Found 50,847,534 primes up to 10^9
Saved to primes_1e9.txt
Total time: 1.18s
```

---

## Algorithm

### Phase 1 — simple sieve

Eratosthenes sieve over `[2, √(10^N)]` finds all *small primes* needed to mark composites in phase 2.  For N=9: √(10^9) ≈ 31 623 → 3 401 small primes, trivial cost.

### Phase 2 — segmented sieve

The range `(√(10^N), 10^N]` is processed in two levels:

**Segments** (innermost, 2^19 = 524 288 numbers each):
- Represented as a packed bitset: 1 bit per odd number = 32 KB per segment.
- For each small prime `p`: find first odd multiple ≥ segment start, then step by `p` in bit-index space (= `2p` in number space) to mark composites.
- 32 KB fits comfortably in L2 cache — this is the performance-critical loop.

**Blocks** (outermost, 100 M numbers each):
- Each block's segments are dispatched to rayon via `par_iter`, so all cores sieve concurrently.
- After each block completes, its primes are written to the output file before the next block starts — bounding peak RAM to ~50 MB.

### Prime counting function π(10^N)

| N | Primes up to 10^N | Approx. output file size |
|---|-------------------|--------------------------|
| 6 | 78,498 | < 1 MB |
| 7 | 664,579 | ~5 MB |
| 8 | 5,761,455 | ~50 MB |
| 9 | 50,847,534 | ~500 MB |
| 10 | 455,052,511 | ~5 GB |
| 11 | 4,118,054,813 | ~50 GB |

---

## Performance

The dominant cost at large N is the sieve itself; file I/O is overlapped with the next block's computation via buffered writes.

Key performance factors:
- **Packed bitset**: 8× smaller working set vs. `bool` array → better cache utilisation.
- **Rayon work-stealing**: segments are distributed across all cores automatically; no manual load balancing needed.
- **Block streaming**: peak RAM is constant regardless of N; no full-range allocation.

---

## Output Files

Files named `primes_1eN.txt` are generated artifacts — one prime per line.  They can be very large and should not be committed to version control.
