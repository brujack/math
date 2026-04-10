# Perfect Squares Calculator — Design

**Date:** 2026-04-10  
**Status:** Approved

## Overview

Add a `sq/` project to the math repo that generates all perfect squares whose decimal value has at most 10^N digits, following the same dual-language structure as `fib/`.

Valid input: N=1 only (10-digit squares). N≥2 is rejected with an error — the count of squares with 10^2 = 100 digits is ~10^50, which is not feasible to enumerate.

---

## Project Layout

```
sq/
  sq.py              # Python implementation + interactive CLI
  test_sq.py         # Python unit tests
  Makefile           # run, lint, test, coverage targets
  install_deps.sh    # installs ruff, coverage
  CLAUDE.md          # project-specific guidance

  sq-rs/
    src/main.rs      # Rust implementation + unit tests
    Cargo.toml       # deps: clap only (no GMP)
    Makefile         # sq, lint, test, clean targets
    install_deps.sh  # Rust toolchain only
    CLAUDE.md        # project-specific guidance
```

Top-level `CLAUDE.md` and `README.md` updated to include `sq/` in the project table and CI badge list.

---

## Algorithm

**Core function:** `generate_squares(max_digits)`

- Precompute `limit = 10^max_digits` (the smallest integer with more than `max_digits` digits).
- Iterate `k = 1, 2, 3, …`; yield/write `k²` while `k² < limit`.
- Stop when `k² ≥ limit`.

For N=1: `max_digits = 10`, `limit = 10^10 = 10,000,000,000`.  
- First square: 1² = 1  
- Last square: 99,999² = 9,999,800,001 (10 digits) ✓  
- Excluded: 100,000² = 10,000,000,000 (11 digits) ✗  
- Total: 99,999 perfect squares

All values fit in u64 (max u64 ≈ 1.8×10^19). No big-integer library needed.

**Stopping criterion:**
- Python: `k * k < limit`
- Rust: `k.checked_mul(k).map_or(false, |sq| sq < limit)` — explicit about the invariant

---

## CLI

Matches the fib pattern:

- Optional positional argument `N`. Interactive prompt if omitted.
- Valid range: N=1 only. Any other value prints an error message and exits with code 1.
- Output: ~99,999 lines × ~10 chars ≈ 1 MB — always buffer in memory, then prompt user to display or save to `sq_1e1.txt`.

```
Enter N (finds all perfect squares with up to 10^N digits, max 1): 1
Generating all perfect squares with up to 10^1 = 10 digits
Found 99,999 perfect squares
Display all 99,999 perfect squares? (y/n):
```

---

## Dependencies

| Component | Dependencies |
|-----------|-------------|
| `sq.py` | None (Python stdlib only) |
| `sq-rs` | `clap` only — no GMP, no rug |

---

## Testing

**Mandatory categories for `generate_squares(max_digits)`:**

Boundary:
- `max_digits=0` → limit=1, k²=1 ≥ 1 immediately → empty sequence
- `max_digits=1` → yields 1, 4, 9 (three 1-digit squares, stops before 10)
- Boundary at max_digits=10: 99,999² is included; 100,000² is excluded
- Count for max_digits=10: exactly 99,999 squares

Correctness:
- Each yielded value is a perfect square (integer square root check)
- Output is strictly increasing

Error path (Rust):
- `generate_squares` with a `FailWriter` → error propagates as `io::Result::Err`

**CLI / arg parsing:**
- N=1 → valid, returns 1
- N=0 → exits with error
- N=2 → exits with error (exceeds max)
- N=-1 → exits with error
- Non-integer arg → exits with error

**State transition:**
- Calling `generate_squares` twice with the same input produces identical output (idempotent, no side effects)

---

## CI

**`.github/workflows/sq-py.yml`**
- Triggers: `push: branches-ignore: master`, `pull_request: branches: master`
- Job `test`: installs `ruff` + `coverage`; runs `make test` from `sq/`

**`.github/workflows/sq-rs.yml`**
- Same triggers
- Job `test`: Rust toolchain; runs `make test` from `sq/sq-rs/`
- Job `build` (`needs: [test]`): `cargo build --release`; uploads `sq` binary as artifact (7-day retention)

No GMP/MPFR install step required (unlike pi-rs and fib-rs).

Two new CI badges added to `README.md`.

---

## Documentation Updates

| File | Update |
|------|--------|
| `CLAUDE.md` (top-level) | Add `sq/` row to Repository Overview and CI tables |
| `README.md` | Add `sq/` row to project table; add two CI badges |
| `sq/CLAUDE.md` | New file — Python project guidance |
| `sq/sq-rs/CLAUDE.md` | New file — Rust project guidance |
