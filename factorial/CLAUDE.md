# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This directory contains a Python CLI for computing N! (N factorial) to arbitrary precision using the prime swing algorithm. It uses `gmpy2`/GMP for fast arbitrary-precision arithmetic (fast path) and falls back to plain Python `int` if `gmpy2` is not installed.

Algorithm: `n! = swing(n) × (⌊n/2⌋!)²` (Luschny prime swing identity), where `swing(m) = ∏ p^e_p` and `e_p = Σ_{j≥1} (⌊m/p^j⌋ mod 2)`.

Current structure:

- `factorial.py`: interactive calculator script (Python, gmpy2/GMP fast path + plain int fallback)
- `install_deps.sh`: installs GMP, gmpy2, ruff, and coverage on macOS and Linux
- `test_factorial.py`: unit tests

## Algorithm

**Prime swing identity:** `n! = swing(n) × (⌊n/2⌋!)²`

The recursion bottoms out at `n ≤ 1` (returns 1). At each level:

1. `_sieve(n)` builds a bytearray sieve of Eratosthenes up to `n`, returns a sorted list of all primes ≤ n.
2. `_compute_swing(n, primes)` computes `swing(n)` by splitting the prime list into `_CPU_COUNT` equal chunks and dispatching each chunk to a subprocess worker via `ProcessPoolExecutor`. On macOS the `spawn` multiprocessing context is used; on Linux `fork` is used. A single-chunk fast path skips subprocess overhead when the prime list is small.
3. Each `_compute_swing_chunk(m, prime_chunk)` worker computes `∏ p^e_p` for its slice of primes and returns a plain Python `int` (always picklable).
4. `_tree_combine_int(partial_results)` merges the per-chunk products via pairwise tree reduction, keeping multiply operand sizes balanced for GMP efficiency.
5. `_factorial_rec(n, primes)` recurses: `result = half_factorial * half_factorial * swing`.

**Parallel strategy:** The prime list is divided into `_CPU_COUNT` equal-length chunks. Each chunk is sent to a subprocess. The main process tree-combines the `int` results. For small inputs (single chunk), `_compute_swing_chunk` is called directly with no subprocess overhead.

## Running The Script

A `Makefile` is provided in `factorial/`:

- `make run` -- runs `python3 factorial.py`
- `make lint` -- runs `ruff check .`
- `make test` -- runs lint then `python3 -m unittest test_factorial -v`
- `make coverage` -- runs tests and prints a line coverage report
- `make clean` -- removes `__pycache__` and `.coverage`

Run the calculator with:

```bash
make run
# or directly:
python3 factorial.py
# or with a CLI argument:
python3 factorial.py 1000
```

The script accepts an optional positional argument `n`. When omitted it prompts interactively. It always writes the result to `factorial_<n>.txt` in the current working directory.

## Code Layout

The project is centered in `factorial.py`.

Module-level constants:

- `_HAS_GMPY2`: `True` if `gmpy2` imported successfully at startup.
- `_gmpy2`: the `gmpy2` module when available, `None` otherwise.
- `_CPU_COUNT`: result of `os.cpu_count() or 1`.

Sieve:

- `_sieve(n)`: bytearray Sieve of Eratosthenes; returns a sorted `list[int]` of all primes ≤ n. Returns `[]` for `n < 2`.

Swing computation:

- `_compute_swing_chunk(m, prime_chunk)`: module-level subprocess worker. Computes `∏ p^e_p` for each prime in `prime_chunk` where `e_p` counts odd quotients in the sequence `⌊m/p⌋, ⌊m/p²⌋, …`. Breaks early when `p > m` (requires `prime_chunk` sorted ascending). Returns a plain `int`.
- `_tree_combine_int(values)`: pairwise tree reduction of a list of integers (`int` or `gmpy2.mpz`). Returns `1` for an empty list.
- `_compute_swing(m, primes)`: filters `primes` to those ≤ m, splits into `_CPU_COUNT` chunks, dispatches each to `_compute_swing_chunk` via `ProcessPoolExecutor` (spawn on macOS, fork on Linux). Uses single-chunk fast path when only one chunk results. Returns `int`.

Factorial recursion:

- `_factorial_rec(n, primes)`: recursive prime swing. Base case `n ≤ 1` returns `1`. Otherwise: `half_factorial = _factorial_rec(n // 2, primes)`, `swing = _compute_swing(n, primes)`, returns `half_factorial * half_factorial * swing`.

Public API:

- `calculate_factorial(n)`: validates `n ≥ 0` (raises `ValueError` for negative). Returns `1` for `n ≤ 1`. Otherwise sieves to `n` and calls `_factorial_rec`. Wraps result in `gmpy2.mpz` when available; returns plain `int` otherwise.

CLI:

- `parse_args(argv)`: `argparse`-based parser; optional positional `n` (int). Returns namespace.
- `get_target_n(args)`: returns `args.n` if provided (raises `ValueError` for negative); otherwise loops on interactive stdin input, retrying on non-integer or negative input.

Output:

- `_write_factorial_file(result, n)`: converts result to decimal string, writes to `factorial_<n>.txt` in the current working directory, prints digit count and write time, returns the filename.

Entry point:

- `main()`: calls `parse_args()`, `get_target_n()`, `calculate_factorial()`, `_write_factorial_file()`.

## Important Behavior

- **Output file always written**: `_write_factorial_file` is always called. There is no preview-only mode. The file `factorial_<n>.txt` is overwritten on each run (idempotent).
- **Return type depends on gmpy2**: `calculate_factorial` returns `gmpy2.mpz` when gmpy2 is installed, plain `int` otherwise. Tests use `int(result)` for comparison to be type-agnostic.
- **`_compute_swing` always returns plain `int`**: the `int()` cast at the end of `_compute_swing` ensures subprocess results are not accidentally wrapped in `gmpy2.mpz` before combining. This keeps chunk results picklable.
- **ProcessPoolExecutor context**: macOS uses `spawn` (re-executes the script in each worker); Linux uses `fork`. The `if __name__ == "__main__":` block checks `multiprocessing.current_process().name == "MainProcess"` to prevent `main()` from running inside worker subprocesses on macOS.
- **`_compute_swing_chunk` must stay at module level**: moving it inside a function or class breaks `ProcessPoolExecutor` pickling.
- **Single-chunk fast path**: when `len(chunks) == 1`, `_compute_swing` calls `_compute_swing_chunk` directly without spawning a subprocess. This avoids process-spawn overhead for small inputs.

## Keeping This File Up To Date

**Update this file whenever you change the code.** Future Claude sessions rely on it -- stale docs are worse than none. Specifically:

- New or renamed function / constant -> update Code Layout
- Makefile target added or removed -> update the Makefile bullet list here and in `README.md`
- Dependency added -> update Environment section and `install_deps.sh`
- Test class added or coverage % changes -> update the Testing coverage table
- Behaviour or algorithm change -> update Important Behavior

Also update the top-level `CLAUDE.md` if the change affects the repository overview or quick-reference targets.

## Editing Guidance

- **Write the failing test first** for all new or changed functions, then add the minimum implementation. Tests go in `test_factorial.py`.
- `_compute_swing_chunk` must remain at module level -- moving it inside a function or class breaks `ProcessPoolExecutor` pickling.
- Do not remove the `current_process().name == "MainProcess"` check from the `if __name__ == "__main__":` block -- it is required to prevent infinite subprocess spawning on macOS (where `spawn` re-executes the script in each worker).
- Keep changes minimal and preserve the single-file CLI structure unless a refactor is clearly necessary.
- Preserve the always-write-to-file behavior unless the task explicitly changes it.
- Do not commit generated `factorial_*.txt` output files -- they can be large.

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass. Never write implementation before the test. Tests must be added in the same commit as the code they cover.

Every test must cover more than the happy path. Three categories are required for every function:

- **Boundary value tests** -- empty/zero/null input, single vs multiple elements, min/max valid values, one above/below valid range
- **Error path tests** -- what happens on failure, dependency failure, partial failure
- **State transition tests** -- before/after assertions, no unintended side effects, idempotency

### Python (`test_factorial.py`)

Run the full suite:

```bash
make test      # python3 -m unittest test_factorial -v
make coverage  # run tests + print coverage report
```

Or directly:

```bash
python3 -m unittest test_factorial -v
python3 -m pytest test_factorial.py -v   # if pytest is installed
```

gmpy2-dependent tests are automatically skipped when gmpy2 is not installed.

#### Test coverage (94% line coverage, 55 tests)

| Class                                | Tests | Notes                                                                        |
| ------------------------------------ | ----- | ---------------------------------------------------------------------------- |
| `TestSieve`                          | 5     | n<2 empty, n=2, small primes, no composites, count to 100                    |
| `TestComputeSwingChunk`              | 8     | empty, all-exceed-m, boundary, per-prime contributions, mixed chunk          |
| `TestTreeCombineInt`                 | 5     | empty, single, two, four, odd-length                                         |
| `TestComputeSwingFallback`           | 1     | OSError triggers serial fallback, result correct, message printed            |
| `TestComputeSwing`                   | 8     | swing(0..6), empty primes, identity check, return type                       |
| `TestCalculateFactorial`             | 9     | 0!..20! vs `FACTORIAL_REF`, negative raises, gmpy2 type (skipped without it) |
| `TestParseArgs`                      | 3     | no args, positional, --help exits                                            |
| `TestGetTargetN`                     | 5     | from args, zero, negative raises, interactive valid, retry on bad input      |
| `TestOutputFile`                     | 4     | file created, filename correct, content digits, idempotent overwrite         |
| `TestProcessPoolPermissionError`     | 1     | PermissionError triggers serial fallback in `_compute_swing`                 |
| `TestProcessPoolSemaphoreExhaustion` | 2     | OSError and errno.ENOSPC trigger serial fallback in `_compute_swing`         |
| `TestMissingGmpy2`                   | 1     | plain int path used when `_HAS_GMPY2` is False                               |
| `TestFileWritePermissionError`       | 1     | `main()` exits 1 on `PermissionError` when writing output file               |
| `TestKeyboardInterruptDuringCompute` | 1     | `main()` exits 1 on KeyboardInterrupt during `calculate_factorial`           |

#### Adding new tests

- Add tests to `test_factorial.py` alongside any new or changed function.
- Use `@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")` on classes that require gmpy2.
- Correctness tests should verify against the `FACTORIAL_REF` constant (known exact values for 0, 1, 2, 3, 4, 5, 10, 20).
- Use `_quiet_factorial(n)` (defined in the test file) to suppress stdout when calling `calculate_factorial` inside tests.

## Notes

- Generated output files (`factorial_*.txt`) are large artifacts -- do not commit them.
