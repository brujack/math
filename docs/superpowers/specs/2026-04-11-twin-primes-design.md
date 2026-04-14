# Twin Primes Design Spec

## Overview

A standalone Rust binary that finds all twin prime pairs (p, p+2) where both primes are less than 10^N. Follows the same structure and conventions as `prime/prime-rs`.

## Project Structure

```
twin-primes/
└── twin-primes-rs/
    ├── src/
    │   └── main.rs
    ├── Makefile
    ├── install_deps.sh
    └── CLAUDE.md
```

## Algorithm

Segmented sieve of Eratosthenes operating over [2, 10^N) in fixed-size chunks (~1MB per segment). Memory usage is constant regardless of N.

**Sieve steps:**

1. Precompute small primes up to √(10^N) using a simple sieve
2. Process the range in segments; for each segment, cross off multiples of each small prime
3. Scan the sieved segment for primes p where p+2 is also prime in the segment — emit as a twin pair
4. Carry `last_prime` across segment boundaries: at the start of each new segment, check whether `last_prime + 2` is prime in the new segment

## CLI

```
twin-primes <N>
```

- `N` — positive integer; finds all twin prime pairs where both p and p+2 < 10^N
- Exits with a clear error message on bad/missing argument

## Output

File: `twin-primes_1e{N}.txt`  
Format: one pair per line — `p | p+2`

```
3 | 5
5 | 7
11 | 13
17 | 19
...
```

Stdout summary (not written to file):

```
Found 35 twin prime pairs up to 10^3
Saved to twin-primes_1e3.txt
```

## Error Handling

- Invalid/missing argument: print usage to stderr, exit code 1
- Write failure: propagated via `io::Result`, printed to stderr, exit code 1
- N=0 or N that produces an empty range: write empty file, report 0 pairs found

## Testing

Tests in `#[cfg(test)] mod tests` in `src/main.rs`, run with `make test`.

**Boundary value tests:**

- N=1: range [2, 10) → pairs: (3,5) and (5,7) — note 5 appears in two pairs
- N=2: range [2, 100) → 8 known pairs: (3,5), (5,7), (11,13), (17,19), (29,31), (41,43), (59,61), (71,73)
- N=0: empty range, 0 pairs
- Large N: verify count matches known values (e.g. N=4 → 205 pairs up to 10,000)

**Error path tests:**

- Missing argument → error exit
- Non-integer argument → error exit
- Write failure → propagated correctly using `FailWriter` pattern (same as `sq-rs`)

**State transition tests:**

- Output file created after run
- File line count matches reported pair count
- Running twice overwrites file cleanly (idempotent)
- No extra output files created

## CI

New workflow: `.github/workflows/twin-primes-rs.yml`

- Triggers: `push: branches-ignore: [master]` and `pull_request: branches: [master]`
- `test` job: `make test` (lint + cargo test)
- `build` job: `needs: [test]`, builds release binary, uploads as artifact (`twin-primes`, 7-day retention)

## Repo Updates Required

| File                                   | Change                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------- |
| `README.md`                            | Add CI badge; add row to project table                                    |
| `CLAUDE.md`                            | Add to Repository Overview table, CI table, Dependency Installation table |
| `scripts/pre-commit`                   | Add `twin-primes/twin-primes-rs` to lint loop                             |
| `twin-primes/twin-primes-rs/CLAUDE.md` | New file — implementation detail for the project                          |
| `docs/superpowers/README.md`           | Move backlog row to Specs; add plan row when plan is written              |
