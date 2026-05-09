# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This directory contains a Python CLI for generating all Fibonacci numbers with at most 10^X decimal digits.

Current structure:

- `fib.py` — interactive generator script (Python built-in integers, no external deps)
- `fib-rs/` — Rust implementation using rug/GMP for large digit counts
- `install_deps.sh` — installs ruff and coverage
- `test_fib.py` — unit tests

## Running the Script

```bash
make run       # python3 fib.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_fib -v
make coverage  # run tests and print coverage report
```

Or directly:

```bash
python3 fib.py        # interactive prompt
python3 fib.py 3      # generate Fibonacci numbers with up to 1,000 digits
```

## Code Layout

- `generate_fibonacci(max_digits)` — generator that yields every Fibonacci number with at most `max_digits` decimal digits. Uses `b < 10^max_digits` stopping criterion; limit precomputed once before the loop.
- `parse_args()` — parses CLI via `argparse`; returns `Namespace` with optional `exponent` int.
- `get_exponent(args)` — returns validated exponent from args, or prompts interactively. Valid range: 1–5. Calls `sys.exit(1)` for out-of-range CLI args.
- `main()` — top-level entry: parses args, validates, warns for X ≥ 4, buffers or streams output.

## Important Behavior

- **Small output (X ≤ 2):** result buffered in a `StringIO`, user prompted to display or save to `fib_1eX.txt`.
- **Large output (X ≥ 3):** streamed directly to `fib_1eX.txt` with 8 MB write buffer.
- **Large-N warning:** X ≥ 4 prints a warning and requires `y/yes` confirmation.
- **Stopping criterion:** `b < 10^max_digits` (precomputed once). Equivalent to `len(str(b)) <= max_digits` but avoids per-iteration string conversion.

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass. Never write implementation before the test. Tests must be added in the same commit as the code they cover.

Every test must cover more than the happy path. Three categories are required for every function:

- **Boundary value tests** — empty/zero/null input, single vs multiple elements, min/max valid values, one above/below valid range
- **Error path tests** — what happens on failure, dependency failure, partial failure
- **State transition tests** — before/after assertions, no unintended side effects, idempotency

```bash
make test      # lint + unittest
make coverage  # coverage run + report
```

### Test coverage

99% line coverage (`fib.py`), 32 tests.

| Class                          | Tests                                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------------------ |
| `TestGenerateFibonacci`        | 9 — sequence correctness, known values, Fibonacci property, max_digits=0 empty             |
| `TestParseArgs`                | 3 — no-arg, with-arg, invalid non-integer exits                                            |
| `TestGetExponent`              | 6 — boundary validation, sys.exit for out-of-range and negative                            |
| `TestGetExponentInteractive`   | 6 — interactive prompt: valid, low/high boundary, retries on out-of-range/zero/non-integer |
| `TestMain`                     | 5 — small-X display + save branches, X=3 streaming, X≥4 warning aborts on "n"/blank        |
| `TestEntryPoint`               | 1 — module runs via subprocess (exercises `if __name__ == "__main__"`)                     |
| `TestFileWritePermissionError` | 1 — `main()` exits 1 on `PermissionError` when writing output file                         |
| `TestKeyboardInterrupt`        | 1 — `main()` exits 1 on KeyboardInterrupt during generation                                |

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Add or remove a Makefile target → update Running section and `README.md`
- Change the valid exponent range or large-N threshold → update Important Behavior
- Add test classes or change coverage → update Testing table
