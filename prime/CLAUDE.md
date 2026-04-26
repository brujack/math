# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This repository contains a Rust CLI for finding all prime numbers up to 10^N using a parallel segmented Sieve of Eratosthenes.

Current structure:

- `prime-rs/`: Rust implementation — segmented sieve + packed bitset + rayon

## Rust Implementation (`prime-rs/`)

The binary finds every prime up to 10^N. Practical range: N ≤ 10 for reasonable runtimes and output file sizes (N=10 → ~455 M primes, ~5 GB text file). N up to 18 is supported with a warning for N ≥ 11.

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
- `make lint` — runs `cargo clippy -- -D warnings`
- `make test` — runs lint then `cargo test`
- `make clean` — runs `cargo clean` and removes `~/Downloads/prime`

No external C libraries required (unlike the pi project); only `rayon` and `clap`.

Install the Rust toolchain and `cargo-tarpaulin` by running `prime/prime-rs/install_deps.sh`.

### Code Layout (`prime-rs/src/main.rs`)

Constants:

- `SEG_SIZE` (`u64`, 2^19): number range covered by one sieve segment; governs the 32 KB bitset per segment.
- `BLOCK_SIZE` (`u64`, 100 M): numbers per sequential rayon batch; bounds peak RAM.

Sieve functions:

- `fn small_sieve(limit)`: simple Eratosthenes sieve of `[2, limit]`; returns `Vec<u64>` of primes.
- `fn sieve_segment(lo, limit, small_primes)`: sieves one segment `[lo, lo+SEG_SIZE) ∩ [lo, limit]` using a packed `Vec<u8>` bitset. `lo` must be odd and greater than all `small_primes`. Returns `Vec<u64>` of primes in the segment.

Driver:

- `fn format_phase2_progress(n, phase2_total, elapsed)`: pure formatter for the phase-2 progress line; testable in isolation.
- `fn find_primes<W: Write>(limit, out)`: orchestrates both phases; spawns a progress thread; returns total prime count.
  - Writes small primes directly after phase 1.
  - Iterates `block_lo` from `phase2_start` (first odd > `sqrt_limit`) to `limit` in `BLOCK_SIZE` steps.
  - Within each block: builds `seg_starts` Vec, runs `par_iter().map(sieve_segment).collect()`, writes results.

Helpers:

- `fn fmt_int(n)`: formats `u64` with thousands separators.
- `fn read_line_from<R: BufRead>(reader)`: reads one trimmed line from any `BufRead`.
- `fn confirm_large_n_with<R, W, E>(reader, out, err, n)`: y/n confirmation for N ≥ 11; warning goes to `err`, prompt to `out`.
- `fn prompt_n_with<R, W, E>(reader, out, err)`: interactive prompt for N; loops until valid (1–18).
- `fn run<R, W, E>(cli, reader, out, err, dir)`: orchestration — handles both N≤6 (buffer/display-or-save) and N>7 (stream-to-file) paths with injectable I/O; returns process exit code.
- `fn main()`: thin stdio wrapper; locks stdin/stdout/stderr, calls `run`, exits with returned code.

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

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass. Never write implementation before the test. Tests must be added in the same commit as the code they cover.

Every test must cover more than the happy path. Three categories are required for every function:

- **Boundary value tests** — empty/zero/null input, single vs multiple elements, min/max valid values, one above/below valid range
- **Error path tests** — what happens on failure, dependency failure, partial failure
- **State transition tests** — before/after assertions, no unintended side effects, idempotency

Tests live in a `#[cfg(test)] mod tests` block at the bottom of `src/main.rs`.

Run the full suite:

```bash
cd prime-rs
cargo test
```

Check coverage (requires `cargo-tarpaulin`):

```bash
cargo install cargo-tarpaulin   # one-time install
cargo tarpaulin --out Stdout
```

### Test coverage (96.24% line coverage, 52 tests: 48 unit + 4 integration)

| Area                                    | Tests | Notes                                                                                                                              |
| --------------------------------------- | ----- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `fmt_int`                               | 5     | zero, sub-thousand, thousands, millions, large                                                                                     |
| `small_sieve`                           | 6     | empty, single prime, known lists, π(100)=25, π(1000)=168                                                                           |
| `sieve_segment`                         | 5     | known range, no even numbers, empty when lo > limit, lo == limit (prime)                                                           |
| `format_phase2_progress`                | 4     | zero, partial, complete, zero-total                                                                                                |
| `find_primes`                           | 9     | below-2, limit=2 exactly, up-to-10 exact output, π(100), π(1000), π(10^6)=78498, last prime, no even non-2, write error propagates |
| `read_line_from`                        | 3     | trims newline, empty, trims whitespace                                                                                             |
| `confirm_large_n_with`                  | 4     | "y", "yes", "n", other input                                                                                                       |
| `prompt_n_with`                         | 6     | valid, minimum=1, maximum=18, zero retry, non-numeric retry, above-max retry                                                       |
| `run`                                   | 6     | invalid N → exit 1, N=1 display y, N=1 save n, N=7 streams to file, N=11 decline, no-arg prompts                                   |
| `tests/cli.rs` (subprocess integration) | 4     | arg=0 exit 1, arg=1 + "y" displays, arg=1 + "n" saves, no-arg + "1\\ny\\n" prompts then displays                                   |

Uncovered lines (~7/186):

- Phase-2 progress-thread loop body (timing-dependent — only fires after a 200 ms tick)
- Block-advance `block_lo += 1` branch (only triggers when N ≥ 9, i.e. limit > BLOCK_SIZE = 100 M)
- Final phase-2 rate `else 0.0` branch (elapsed always > 0.001 ms for real sieves)
- Tarpaulin macro-expansion artifacts in `eprintln!` calls

### Adding new tests

- Add tests to the `#[cfg(test)] mod tests` block in `src/main.rs`.
- Use known prime counts (π(10^6)=78,498; π(10^7)=664,579; π(10^8)=5,761,455; π(10^9)=50,847,534) for accuracy assertions.
- `sieve_segment` requires `lo` to be odd — always pass an odd `lo` in tests.

## Keeping This File Up To Date

**Update this file whenever you change the code.** Future Claude sessions rely on it — stale docs are worse than none. Specifically:

- New or renamed function / constant → update Code Layout
- Makefile target added or removed → update the Makefile bullet list here and in `README.md`
- Dependency added → update `prime/prime-rs/install_deps.sh` and note it here
- Test class added or coverage % changes → update the Testing coverage table here and in `README.md`
- Behaviour or algorithm change → update Important Implementation Details

Also update the top-level `CLAUDE.md` if the change affects the repository overview or quick-reference targets.

## Editing Guidance

- Do not change `SEG_SIZE` without profiling — 2^19 is chosen to keep the 32 KB bitset in L2 cache.
- `BLOCK_SIZE` (100 M) controls RAM usage per block; reducing it lowers peak RAM at the cost of more sequential iterations.
- The `phase2_start` formula is subtle — see the important details note above before changing it.
- `sieve_segment` assumes `lo` is odd; callers must ensure this invariant.
- Generated output files (`primes_1eN.txt`) can be very large — do not commit them.
- **Write the failing test first** for all new or changed functions, then add the minimum implementation. Tests go in the `#[cfg(test)]` module.
