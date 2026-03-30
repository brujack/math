# Fibonacci Sequence Project — Design Spec

**Date:** 2026-03-30
**Status:** Approved

---

## Overview

Add a Fibonacci sequence calculator to the math repo as a new top-level project `fib/`. The project mirrors the existing `pi/` structure: a Python script and a Rust binary, each implemented independently with their own Makefile, tests, and CI workflow.

**Goal:** Generate all Fibonacci numbers whose decimal digit count is at most 10^X, where X is user-supplied (1–5). Output is written one number per line to `fib_1eX.txt`.

---

## Directory Structure

```
fib/
├── CLAUDE.md
├── README.md
├── Makefile              # run, lint, test, coverage targets
├── install_deps.sh       # installs ruff, coverage (Python deps only)
├── fib.py
├── test_fib.py
└── fib-rs/
    ├── CLAUDE.md
    ├── README.md
    ├── Makefile          # fib, lint, test targets
    ├── install_deps.sh   # installs Rust toolchain, cargo-tarpaulin
    ├── Cargo.toml        # deps: clap, rug, num-format (or manual fmt_int)
    └── src/
        └── main.rs
```

Top-level `CLAUDE.md` and `README.md` get a new `fib/` row in their project tables.

---

## User Interface & Input

Both implementations follow the prime-rs pattern:

- **CLI argument:** `fib [X]` — optional positional integer
- **Interactive fallback:** if no argument, prompt `Enter X (finds all Fibonacci numbers with up to 10^X digits, max 5):`
- **Valid range:** 1–5; values outside this range are rejected with an error message
- **Large-N warning:** for X ≥ 4, print a warning about output size and require `y/yes` confirmation before proceeding
- **Small output (X ≤ 2):** buffer in memory, offer to display on screen or save to file
- **Large output (X ≥ 3):** stream directly to `fib_1eX.txt`

Output: one Fibonacci number per line, no index prefix. Final summary: `Found N Fibonacci numbers with up to 10^X digits`.

---

## Algorithm

**Simple iteration** in both languages:

```
a, b = 0, 1
while digit_count(b) <= 10^X:
    write(b)
    a, b = b, a + b
```

This is optimal for this task: every Fibonacci number in the sequence must be produced, so no skipping is possible. Memory usage is O(d) where d = 10^X (two big integers of at most d digits at any time).

Digit count is checked each iteration via `len(str(n))` (Python) or `n.to_string().len()` (Rust/rug). The digit count grows monotonically so no additional optimization is needed.

---

## Implementation Details

### Python (`fib/fib.py`)

- Uses Python's built-in arbitrary-precision `int` — no third-party libraries required for computation
- CLI via `argparse` (consistent with `pi.py`)
- Output via buffered write or direct file stream depending on X
- `install_deps.sh` installs `ruff` and `coverage` only

### Rust (`fib/fib-rs/src/main.rs`)

- Uses `rug::Integer` (wraps libGMP, already installed for `pi-rs`) for arbitrary-precision arithmetic
- `clap` for CLI argument parsing (same as prime-rs)
- `fmt_int` helper (same comma-formatting pattern as prime-rs) for the summary count
- `install_deps.sh` installs Rust toolchain and `cargo-tarpaulin`

---

## Testing

### Python (`fib/test_fib.py`)

Uses `unittest`, same as `test_pi.py`. Tests cover:

- Core computation function: known Fibonacci values for small indices
- Digit-count boundary: correct stopping point for X=1 (numbers with ≤ 10 digits)
- Output format: one number per line, no extra whitespace
- Input validation: rejects out-of-range X

### Rust (`src/main.rs` `#[cfg(test)]` block)

Tests cover:

- Known Fibonacci values (F(0)–F(10))
- Correct count for small digit limits
- Digit-count helper correctness
- `fmt_int` formatting

---

## CI

Two new workflow files:

| Workflow | File | Jobs |
|----------|------|------|
| fib.py | `.github/workflows/fib-py.yml` | test |
| fib-rs | `.github/workflows/fib-rs.yml` | test → build + artifact |

Both follow existing patterns:
- Run on every push and pull request to `master`
- Node.js 24 (`actions/checkout@v5`, `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true`)
- `fib-rs` build job uploads the release binary as an artifact (7-day retention)
- Badges for both workflows added to the top of the top-level `README.md`

---

## Output Files

Generated files (`fib_1e*.txt`) are large artifacts and must not be committed. Already covered by `.gitignore` patterns if they exist; otherwise add `fib_1e*.txt` to `.gitignore`.

---

## Constraints & Limits

| X | Max digit count | Approx Fibonacci numbers | Approx output size |
|---|----------------|--------------------------|-------------------|
| 1 | 10 | ~47 | tiny |
| 2 | 100 | ~478 | tiny |
| 3 | 1,000 | ~4,785 | ~2.4 MB |
| 4 | 10,000 | ~47,847 | ~240 MB |
| 5 | 100,000 | ~478,468 | ~24 GB |

Warning + confirmation required for X ≥ 4.
