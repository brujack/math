# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This directory contains a Python CLI for generating all perfect squares with at most 10^N decimal digits. N=1 is the only valid value (10-digit squares); any other value exits with an error.

Current structure:

- `sq.py` — interactive generator script (Python stdlib only, no external deps)
- `sq-rs/` — Rust implementation (no big-integer library needed)
- `install_deps.sh` — installs ruff and coverage
- `test_sq.py` — unit tests

## Running the Script

```bash
make run       # python3 sq.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_sq -v
make coverage  # run tests and print coverage report
```

Or directly:

```bash
python3 sq.py      # interactive prompt
python3 sq.py 1    # generate all perfect squares with up to 10 digits
```

## Code Layout

- `generate_squares(max_digits)` — generator that yields `(sq, root)` tuples for every perfect square with at most `max_digits` decimal digits. Uses `k*k < 10^max_digits` stopping criterion; limit precomputed once before the loop.
- `parse_args()` — parses CLI via `argparse`; returns `Namespace` with optional `exponent` int.
- `get_exponent(args)` — returns validated exponent from args, or prompts interactively. Valid value: 1 only. Calls `sys.exit(1)` for any other value.
- `main()` — top-level entry: parses args, validates, buffers output, prompts to display or save to `sq_1e1.txt`.

## Important Behavior

- **Output:** always buffered in a `StringIO` and always saved to `sq_1eN.txt`. User is then prompted to also display on screen.
- **Valid N:** 1 only. `get_exponent` exits with code 1 for any other value.
- **Stopping criterion:** `k*k < 10^max_digits` (precomputed limit). For N=1: limit=10^10, last included square is 99,999² = 9,999,800,001.
- **No external dependencies:** uses Python stdlib only.

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

| Class                 | Tests                                                                                                                     |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `TestGenerateSquares` | 10 — boundary (empty, 1-digit, 2-digit, 10-digit), correctness (perfect square, increasing), count, last value, exclusion |
| `TestParseArgs`       | 3 — no-arg, with-arg, invalid non-integer exits                                                                           |
| `TestGetExponent`     | 4 — valid (1), zero exits, too-high exits, negative exits                                                                 |

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Add or remove a Makefile target → update Running section and `README.md`
- Change the valid exponent range → update Important Behavior
- Add test classes or change coverage → update Testing table
