# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This directory contains a Python CLI for generating all perfect squares with at most 10^N decimal digits. N=1 is the only valid value (10-digit squares); any other value exits with an error.

Current structure:

- `sq.py` — interactive generator script (Python stdlib only, no external deps)
- `sq-rs/` — Rust implementation (no big-integer library needed)
- `install_deps.sh` — rendered from `scripts/crate_templates/python/install_deps.sh`: GMP + MPFR (Homebrew, apt or dnf/yum) and every pinned Python package
- `test_sq.py` — unit tests

## Running the Script

```bash
make run       # python3 sq.py
make lint      # ruff check .
make test      # lint, pytest test_sq.py -v, then ../scripts/cli_contract.py sq.py
make coverage  # run tests and print coverage report
```

Or directly:

```bash
python3 sq.py            # interactive prompt (terminal only; non-TTY exits 2)
python3 sq.py 1          # write sq_1e1.txt
python3 sq.py 1 --show   # also print each `square | root` line
python3 sq.py --smoke    # quick check at SMOKE_SIZE (1)
```

## Code Layout

- `generate_squares(max_digits)` — generator that yields `(sq, root)` tuples for every perfect square with at most `max_digits` decimal digits. Uses `k*k < 10^max_digits` stopping criterion; limit precomputed once before the loop.
- `SMOKE_SIZE = 1`, `LARGE_RUN_THRESHOLD = None` — CLI contract constants read by `scripts/cli_contract.py` (pinned by `TestCliContractConstants`).
- `parse_args(argv=None)` — `argparse` with optional `size`, `--show`, `--yes`, `--smoke`; `--smoke` takes no SIZE and forces `size=SMOKE_SIZE`, `show=False`; a bare run on a non-TTY exits 2.
- `refuse_large_run(size, yes)` — exits 1 naming `--yes` when `size >= LARGE_RUN_THRESHOLD` without `--yes`; a no-op here because there is no threshold.
- `get_exponent(args)` — returns validated `args.size`, or prompts interactively. Valid value: 1 only. Calls `sys.exit(1)` for any other value; EOF at the prompt exits 1 with a message to pass SIZE as an argument.
- `main(argv=None)` — top-level entry: parses args, validates, buffers output, saves to `sq_1e1.txt`, prints the buffer only with `--show`.

## Important Behavior

- **Output:** always buffered in a `StringIO` and always saved to `sq_1eN.txt`. `--show` prints the buffer (each `square | root` line exactly as written) to stdout; there is no display prompt.
- **Valid N:** 1 only. `get_exponent` exits with code 1 for any other value.
- **Closed stdin:** nothing reads stdin when SIZE is given; a bare non-TTY run exits 2; EOF at the interactive N prompt exits 1 with a message to pass SIZE as an argument.
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
make coverage  # pytest --cov, fails under 90%
```

### Test coverage

99% line coverage (`sq.py`), 53 tests.

| Class                          | Tests                                                                                                                                  |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `TestGenerateSquares`          | 11 — boundary (empty, 1-digit, 2-digit, 10-digit), correctness (perfect square, increasing), count, last value, exclusion, idempotency |
| `TestParseArgs`                | 8 — size, no-arg on TTY, non-TTY bare run exits 2, invalid integer, `--show`, `--yes`, `--smoke` (clears show), `--smoke` with SIZE exits 2 |
| `TestGetExponent`              | 7 — valid (1), zero exits, too-high exits, negative exits; exit-code assertions for each failure path                                  |
| `TestGetExponentInteractive`   | 4 — interactive prompt: valid, retries on too-high/zero/non-integer                                                                    |
| `TestMain`                     | 8 — file-only, `--show` echoes every line as written and before the summary, refusal before any write, `--smoke`, invalid size writes nothing, idempotent overwrite, exact count        |
| `TestSquaresProperties`        | 3 — property tests: all perfect squares, all positive, strictly increasing                                                             |
| `TestEntryPoint`               | 1 — module runs via subprocess (exercises `if __name__ == "__main__"`)                                                                 |
| `TestClosedStdin`              | 3 — subprocess with stdin closed: SIZE runs, bare run exits 2; EOF after a bad answer                                                   |
| `TestEofAtSizePrompt`          | 1 — EOF at the N prompt exits 1 naming the remedy, newline on stdout                                                                   |
| `TestCliContractConstants`     | 2 — `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD` pinned                                                                                       |
| `TestRefuseLargeRun`           | 3 — no threshold never refuses; refuses at boundary; allows one below and with `--yes`                                                  |
| `TestFileWritePermissionError` | 1 — `main()` exits 1 on `PermissionError` when writing output file                                                                     |
| `TestKeyboardInterrupt`        | 1 — `main()` exits 1 on KeyboardInterrupt during generation                                                                            |

## Equivalent mutants

`cosmic-ray.toml` is rendered from a template and carries no prose; these mutants cannot be killed by any valid input:

- `max_digits = 10**x` in `main()`: `get_exponent` accepts only `x == 1`, so `10*x` and `10//x` give 10. (`10/x` gives 10.0, which `main()` prints as `10.0`, so it is killable by asserting that line.)
- `__name__ == "__main__"` guard: `<=` and `is` behave identically (`"sq" > "__main__"` lexicographically, so `<=` is False on import; CPython interns the literal).
- `print("=" * 40)` in `main()`: the banner width is cosmetic.

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Add or remove a Makefile target → update Running section and `README.md`
- Change the valid exponent range → update Important Behavior
- Add test classes or change coverage → update Testing table
