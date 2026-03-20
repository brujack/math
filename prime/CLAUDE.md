# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This repository contains a Rust CLI for finding all prime numbers up to 10^N using a parallel segmented Sieve of Eratosthenes.

Current structure:

- `prime-rs/`: Rust implementation — segmented sieve + packed bitset + rayon

## Rust Implementation (`prime-rs/`)

The binary finds every prime up to 10^N.  Practical range: N ≤ 10 for reasonable runtimes and output file sizes (N=10 → ~455 M primes, ~5 GB text file).  N up to 18 is supported with a warning for N ≥ 11.

### Algorithm

Two-phase segmented Sieve of Eratosthenes:

**Phase 1** — simple sieve of `[2, √(10^N)]`
- Runs once; produces `small_primes` used to cross off composites in phase 2.
- For N=9: √(10^9) ≈ 31 623 → trivial (168 primes, ~4 KB).

**Phase 2** — segmented sieve of `(√(10^N), 10^N]`
- Range split into `SEG_SIZE`-number segments (2^19 = 524 288 numbers each).
- Each segment represented as a **packed bitset** (1 bit per odd number = 32 KB) — fits in L2 cache.
- Segments grouped into `BLOCK_SIZE`-number blocks (100 M numbers); each block is processed with `rayon::par_iter` across its segments.
- Primes are **streamed to file block-by-block** — peak RAM stays ≤ ~50 MB regardless of N.

### Build

```bash
cd prime-rs
make prime       # cargo build --release, copies binary to ~/Downloads/prime
./target/release/prime [N]
```

A `Makefile` is provided in `prime-rs/`:
- `make prime` — runs `cargo build --release` and copies the binary to `~/Downloads/prime`
- `make clean` — runs `cargo clean` and removes `~/Downloads/prime`

No external C libraries required (unlike the pi project); only `rayon` and `clap`.

### Code Layout (`prime-rs/src/main.rs`)

Constants:
- `SEG_SIZE` (`u64`, 2^19): number range covered by one sieve segment; governs the 32 KB bitset per segment.
- `BLOCK_SIZE` (`u64`, 100 M): numbers per sequential rayon batch; bounds peak RAM.

Sieve functions:
- `fn small_sieve(limit)`: simple Eratosthenes sieve of `[2, limit]`; returns `Vec<u64>` of primes.
- `fn sieve_segment(lo, limit, small_primes)`: sieves one segment `[lo, lo+SEG_SIZE) ∩ [lo, limit]` using a packed `Vec<u8>` bitset. `lo` must be odd and greater than all `small_primes`. Returns `Vec<u64>` of primes in the segment.

Driver:
- `fn find_primes<W: Write>(limit, out)`: orchestrates both phases; spawns a progress thread; returns total prime count.
  - Writes small primes directly after phase 1.
  - Iterates `block_lo` from `phase2_start` (first odd > `sqrt_limit`) to `limit` in `BLOCK_SIZE` steps.
  - Within each block: builds `seg_starts` Vec, runs `par_iter().map(sieve_segment).collect()`, writes results.

Helpers:
- `fn fmt_int(n)`: formats `u64` with thousands separators.
- `fn read_line()`, `fn prompt_digits()`: interactive prompt helpers.

### Bitset Representation

`sieve_segment` uses a packed `Vec<u8>` where:
- Bit index `i` represents the odd number `lo + 2*i`.
- Bit = 1 means composite; bit = 0 means prime candidate.
- For small prime `p`, consecutive odd multiples are `2p` apart in number space → index step = `p` (since each index unit covers 2 numbers).
- Access: `composite[idx >> 3] |= 1u8 << (idx & 7)` to mark; `composite[i >> 3] & (1u8 << (i & 7)) == 0` to test.

### Progress Output

A background thread wakes every 200 ms and prints to stderr:
```
  Phase 2:  XX%  (N / N numbers sieved)  X.X M/s
```
Uses `\r` to overwrite in place; a final line is printed after the thread is joined.

### Output Behaviour

- **N ≤ 6** (≤ 78 498 primes): buffered in a `Vec<u8>`, user prompted to display or save.
- **N > 6**: streamed directly to `primes_1eN.txt` via `BufWriter` (8 MB buffer).
- **N ≥ 11**: user warned about long runtime and large output file before proceeding.

### Important Implementation Details

- `phase2_start` must be the **first odd number strictly greater than `sqrt_limit`**:
  `sqrt_limit + 1 + (sqrt_limit & 1)` — note `sqrt_limit & 1`, NOT `(sqrt_limit + 1) & 1` (the latter is an off-by-one that produces an even `phase2_start`, causing even numbers to appear in output).
- `sieve_segment` is called with `block_hi` as its `limit` argument (not the global `limit`), so that each block's segments stop exactly at the block boundary.
- `block_lo` is always kept odd: after advancing `block_lo = block_hi + 1`, add 1 if even.
- The `find_primes` function is generic over `W: Write`, allowing output to either `Vec<u8>` (small N) or `BufWriter<File>` (large N) without duplication.

## Validation

No formal test suite.  Quick manual checks:

```bash
# Known counts:
# π(10^6)  =     78,498
# π(10^7)  =    664,579
# π(10^8)  =  5,761,455
# π(10^9)  = 50,847,534

./target/release/prime 6   # expect 78,498 primes, last = 999,983
./target/release/prime 7   # expect 664,579 primes
```

Sanity checks on output:
```bash
# No even numbers (except 2):
grep -c "[02468]$" primes_1e6.txt   # should print 1

# Last prime before 10^6:
tail -1 primes_1e6.txt              # should print 999983
```

## Editing Guidance

- Do not change `SEG_SIZE` without profiling — 2^19 is chosen to keep the 32 KB bitset in L2 cache.
- `BLOCK_SIZE` (100 M) controls RAM usage per block; reducing it lowers peak RAM at the cost of more sequential iterations.
- The `phase2_start` formula is subtle — see the important details note above before changing it.
- `sieve_segment` assumes `lo` is odd; callers must ensure this invariant.
- Generated output files (`primes_1eN.txt`) can be very large — do not commit them.
