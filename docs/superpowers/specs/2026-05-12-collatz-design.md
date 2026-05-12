# Collatz Sequences — Design Spec

**Date:** 2026-05-12
**Status:** Approved

---

## Overview

For each positive integer up to 10^N, compute its Collatz chain length and identify
running record-setters — numbers whose chain length exceeds every prior number's.
Output one line per record to stdout and to `collatz_1eN.txt`.

A Collatz chain from n applies the rule: if n is even, n→n/2; if n is odd, n→3n+1.
Chain length is the number of steps to reach 1, not counting the starting number.
`chain_length(1)=0`, `chain_length(2)=1`, `chain_length(27)=111`.

---

## Project Structure

```
collatz/
  collatz.py
  test_collatz.py
  Makefile
  install_deps.sh
  README.md
  CLAUDE.md
  collatz-rs/
    src/main.rs
    Cargo.toml
    Makefile
    install_deps.sh
    CLAUDE.md
```

Follows the same layout as all other projects in this repo (pi, fib, factorial, etc.).

---

## Algorithm

**Vector memoization (bottom-up back-fill).**

Cache stores `cache[n] = chain_length(n) + 1` using 0 as the sentinel for "not yet
computed". Seed: `cache[1] = 1`.

For each `n` in `2..=limit`:

1. If `cache[n] != 0`, skip — already computed.
2. Walk the Collatz sequence from `n`, appending each value to a `path` list. Stop
   when the current value is 1 or is a cached value within `[1, limit]`.
3. Back-fill from the end of `path` to the front: each entry's cache value equals
   the next-known entry's cache value plus 1. Values in the path that exceed `limit`
   are counted toward the length but not stored in the cache.

Memory: 4 bytes × (limit + 1). At N=9 (1B entries) ≈ 4GB.

---

## N Range and Limits

| N     | Entries | Cache size | Python feasible? | Rust feasible? |
| ----- | ------- | ---------- | ---------------- | -------------- |
| 1–7   | ≤10M    | ≤40MB      | Yes              | Yes            |
| 8     | 100M    | 400MB      | Marginal         | Yes            |
| 9     | 1B      | 4GB        | No               | Yes            |
| 10–12 | 10B–1T  | 40GB–4TB   | No               | Slow (hours)   |

Valid range: 1–12. Python warns when N>7. Rust warns when N>9 but proceeds.

---

## Output Format

One line per record, written to stdout as discovered and saved to `collatz_1eN.txt`:

```
1 0
2 1
3 7
6 8
7 16
9 19
18 20
25 23
27 111
...
```

Fields: `<starting_number> <chain_length>`. The file contains only record-setters —
numbers whose chain length strictly exceeds every prior number's.

---

## Python Implementation

**File:** `collatz/collatz.py`
**Dependencies:** stdlib only (`array`, `argparse`, `sys`, `pathlib`). `install_deps.sh` installs `ruff` and `coverage`.

### Functions

- `collatz_next(n: int) -> int` — single Collatz step (n//2 if even, 3\*n+1 if odd)
- `collatz_length(n: int, cache: array) -> int` — walk from n, back-fill cache, return chain length
- `generate_records(limit: int)` — allocates `array.array('I', [0]*(limit+1))`, scans 1..limit, yields `(n, length)` each time a new record is set
- `parse_args()` — argparse with optional positional `N`
- `get_exponent(args) -> int` — validates N in [1, 12]; interactive prompt if absent; warns if N > 7
- `main()` — prints each record, saves file `collatz_1eN.txt`

**Cache type:** `array.array('I', ...)` — 4 bytes per entry (unsigned int). At N=7: 40MB; N=8: 400MB. Above N=8 Python will be impractically slow or OOM.

### Makefile targets

```
run      python3 collatz.py
lint     ruff check .
test     lint + python3 -m unittest test_collatz -v
coverage coverage run + report
clean    rm -rf __pycache__ .coverage
```

---

## Rust Implementation

**File:** `collatz/collatz-rs/src/main.rs`
**Dependencies:** none beyond stdlib (no GMP/rug needed — all Collatz values fit in u64, chain lengths fit in u32).

### Key types

- Cache: `Vec<u32>` allocated to `limit + 1` entries
- Walk accumulator: `Vec<u64>` — Collatz values can temporarily exceed `limit`
- Chain lengths: `u32` (max known chains for N≤12 stay well under u32::MAX)

### Functions

- `collatz_next(n: u64) -> u64` — single Collatz step
- `chain_length(n: u64, cache: &mut Vec<u32>, limit: u64) -> u32` — walk, back-fill, return
- `generate_records<W, E>(limit: u64, out: &mut W, err: &mut E)` — scans 1..=limit, tracks running max, writes each record line
- `parse_args() -> Option<u32>` — reads argv[1] if present
- `get_exponent<W, E>(args, out, err) -> u64` — validates N in [1, 12], interactive prompt if absent, warns N>9
- `run<W: Write, E: Write>(out: W, err: E, dir: &Path)` — orchestrates, writes file
- `main()` — thin wrapper: `run(stdout(), stderr(), cwd)`

`fn main()` is annotated `#[cfg(not(tarpaulin_include))]` to exclude it from coverage.

### Cargo.toml lints

```toml
[lints.rust]
unexpected_cfgs = { level = "warn", check-cfg = ['cfg(tarpaulin_include)'] }
```

### Makefile targets

```
collatz            cargo build --release
lint               cargo fmt --check + cargo clippy --all-targets -- -D warnings
test               lint + cargo test
clean              cargo clean
```

---

## Testing

### Python (`test_collatz.py`, ≥90% line coverage)

| Class                 | Key test cases                                                                          |
| --------------------- | --------------------------------------------------------------------------------------- |
| `TestCollatzNext`     | even input (6→3), odd input (3→10), n=2→1                                               |
| `TestCollatzLength`   | n=1 (0), n=2 (1), n=3 (7), n=27 (111), cache hit, value exceeding limit mid-walk        |
| `TestGenerateRecords` | limit=1 (only 1,0), limit=10 (known records), ascending n order, ascending length order |
| `TestGetExponent`     | valid 1, valid 7, valid 12, exit on 0, exit on 13, exit on negative, interactive prompt |
| `TestMain`            | N=1 file content, N=3 file content, KeyboardInterrupt exits 1, PermissionError exits 1  |

### Rust (`#[cfg(test)] mod tests`, ≥90% via tarpaulin --fail-under 90)

- `collatz_next`: even, odd
- `chain_length`: n=1, n=2, n=3, n=27, cache reuse (second call is O(1)), value exceeding limit mid-walk
- `generate_records`: limit=1, limit=10 (spot-check output lines)
- `run`: correct file written, bad N rejected

---

## CI

Two new workflow files:

| Workflow   | File                               | Jobs                    | Paths                   |
| ---------- | ---------------------------------- | ----------------------- | ----------------------- |
| collatz.py | `.github/workflows/collatz-py.yml` | test                    | `collatz/**`            |
| collatz-rs | `.github/workflows/collatz-rs.yml` | test → build + artifact | `collatz/collatz-rs/**` |

Both trigger on `pull_request` to `master` only. Badges added to `README.md`.

`scripts/pre-commit` and `scripts/pre-push` updated to include `collatz` and
`collatz/collatz-rs` in their directory loops.

---

## Files Added or Modified

| Action   | Path                                 |
| -------- | ------------------------------------ |
| New      | `collatz/collatz.py`                 |
| New      | `collatz/test_collatz.py`            |
| New      | `collatz/Makefile`                   |
| New      | `collatz/install_deps.sh`            |
| New      | `collatz/README.md`                  |
| New      | `collatz/CLAUDE.md`                  |
| New      | `collatz/collatz-rs/src/main.rs`     |
| New      | `collatz/collatz-rs/Cargo.toml`      |
| New      | `collatz/collatz-rs/Makefile`        |
| New      | `collatz/collatz-rs/install_deps.sh` |
| New      | `collatz/collatz-rs/CLAUDE.md`       |
| New      | `.github/workflows/collatz-py.yml`   |
| New      | `.github/workflows/collatz-rs.yml`   |
| Modified | `scripts/pre-commit`                 |
| Modified | `scripts/pre-push`                   |
| Modified | `README.md`                          |
| Modified | `CLAUDE.md`                          |
| Modified | `docs/superpowers/README.md`         |
