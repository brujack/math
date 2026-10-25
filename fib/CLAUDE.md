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
make test      # lint, then pytest test_fib.py -v
make coverage  # run tests and print coverage report
```

Or directly:

```bash
python3 fib.py                # interactive prompt (terminal only; a bare non-TTY run exits 2)
python3 fib.py 3              # generate Fibonacci numbers with up to 1,000 digits
python3 fib.py 3 --show       # also print each number to stdout
python3 fib.py 4 --yes        # X >= 4 is refused without --yes
python3 fib.py --smoke        # quick check at X=3
```

## Code Layout

- `generate_fibonacci(max_digits)` — generator that yields every Fibonacci number with at most `max_digits` decimal digits. Uses `b < 10^max_digits` stopping criterion; limit precomputed once before the loop.
- `SMOKE_SIZE = 3`, `LARGE_RUN_THRESHOLD = 4` — pinned by `TestCliContractConstants`.
- `parse_args(argv: list[str] | None = None)` — `size` (X), `--show`, `--yes`, `--smoke`; bare non-TTY run exits 2; `--smoke` with a size exits 2.
- `refuse_large_run(size, yes)` — exits 1 naming `--yes` when `size >= LARGE_RUN_THRESHOLD` and `--yes` is absent.
- `get_exponent(args)` — returns validated exponent from `args.size`, or prompts interactively. Valid range: 1–5. Calls `sys.exit(1)` for out-of-range args and calls `refuse_large_run` on the argument path.
- `ask_yes(prompt)` — y/n prompt; returns `True` only for `y`/`yes` (any case, trimmed). End of input prints a newline and reads as no.
- `main(argv: list[str] | None = None)` — top-level entry: parses args, validates, always writes `fib_1eX.txt`, `--show` prints each number.

## Important Behavior

- **Small output (X ≤ 2):** result buffered in a `StringIO`, then written to `fib_1eX.txt`.
- **Large output (X ≥ 3):** streamed directly to `fib_1eX.txt` with 8 MB write buffer.
- **No display prompt:** the file is always written; `--show` also prints each number line.
- **Large-run gate:** X ≥ 4 on the argument path is refused (exit 1) unless `--yes`; the interactive path prints a warning and asks `Continue? (y/n)`, EOF reads as no.
- **Closed stdin:** the interactive X prompt exits 1 with a message to pass SIZE as an argument; a bare non-TTY run exits 2.
- **Int-string cap:** `main()` calls `sys.set_int_max_str_digits(0)`; without it Python 3.11+ raises `ValueError` on any value over 4,300 digits. Tested with a mocked generator, never a real X=4 run (about 15 s, 239 MB).
- **Stopping criterion:** `b < 10^max_digits` (precomputed once). Equivalent to `len(str(b)) <= max_digits` but avoids per-iteration string conversion.
- **Contract harness:** `make test` runs `python3 ../scripts/cli_contract.py fib.py` after pytest.

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

99% line coverage (`fib.py`), 71 tests. The CLI-contract classes are `TestParseArgs`, `TestCliContractConstants`, `TestRefuseLargeRun`; large-run proceed/refuse is covered with a mocked `generate_fibonacci`.

| Class                          | Tests                                                                                                           |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `TestGenerateFibonacci`        | 9 — sequence correctness, known values, Fibonacci property, max_digits=0 empty                                  |
| `TestParseArgs`                | 7 — no-arg on a TTY, size, `--show`/`--yes`, non-integer exits, bare non-TTY exits 2, `--smoke` sets size and clears show, `--smoke` with size exits 2 |
| `TestCliContractConstants`     | 2 — pins `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD`                                                                 |
| `TestRefuseLargeRun`           | 3 — one below threshold passes, at threshold exits 1 naming `--yes`, at threshold with `--yes` passes          |
| `TestGetExponent`              | 8 — boundary validation, sys.exit for out-of-range and negative; exact exit-code assertion; large without `--yes` exits 1 |
| `TestGetExponentInteractive`   | 6 — interactive prompt: valid, low/high boundary, retries on out-of-range/zero/non-integer                      |
| `TestMain`                     | 20 — file always written, `--show` echo (before the summary), buffered (X=2), streaming (X=3), `--smoke`, mocked large-run proceed/refuse, refusal before any file write, interactive X≥4 abort/proceed with a mocked generator, X=4 past the 4,300-digit cap, rerun overwrites |
| `TestFibonacciProperties`      | 3 — property tests: all positive, recurrence holds, strictly increasing after first two                         |
| `TestEntryPoint`               | 1 — module runs via subprocess (exercises `if __name__ == "__main__"`)                                          |
| `TestClosedStdin`              | 5 — subprocess with stdin closed: small X saves, X≥4 refused without prompting, bare run exits 2; EOF at the X prompt exits 1 with the SIZE message, also after a bad answer |
| `TestAskYes`                   | 5 — EOF reads as no, yes forms, other answers are no, Ctrl-C propagates, EOF newline on stdout at the X prompt |
| `TestFileWritePermissionError` | 1 — `main()` exits 1 on `PermissionError` when writing output file                                              |
| `TestKeyboardInterrupt`        | 1 — `main()` exits 1 on KeyboardInterrupt during generation                                                     |

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Add or remove a Makefile target → update Running section and `README.md`
- Change the valid exponent range or large-N threshold → update Important Behavior
- Add test classes or change coverage → update Testing table
