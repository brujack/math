# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This directory contains a Python CLI for calculating Euler's number _e_ to high precision. It uses the Taylor series `e = sum(1/n! for n=0..N)` computed via binary splitting with `gmpy2`/GMP (fast path) and falls back to `mpmath` if `gmpy2` is not installed.

Current structure:

- `e.py`: interactive calculator script (Python, gmpy2/GMP + mpmath fallback)
- `e-rs/`: Rust implementation -- Taylor series + Rayon + rug/GMP/MPFR
- `install_deps.sh`: rendered from `scripts/crate_templates/python/install_deps.sh`: GMP + MPFR (Homebrew, apt or dnf/yum) and every pinned Python package
- `test_e.py`: unit tests

## Rust Implementation (`e-rs/`)

The Rust binary targets large digit workloads where the Python subprocess IPC overhead becomes significant.

Key differences from Python:

- Uses `rayon::join()` for recursive parallel binary splitting -- threads share memory, zero IPC/serialisation cost
- `rug` wraps GMP (`Integer`) and MPFR (`Float`) directly -- same C libraries as Python's gmpy2
- Parallel file I/O via `FileExt::write_at` (POSIX pwrite equivalent) dispatched by rayon

See `e-rs/CLAUDE.md` for detailed Rust guidance.

## Environment

Each implementation has its own installer:

```bash
bash e/install_deps.sh        # e.py -- GMP + MPFR and the pinned Python packages
bash e/e-rs/install_deps.sh   # e-rs -- GMP + MPFR, Rust toolchain, cargo-tarpaulin
```

Requirements summary:

| Dependency          | Required for                               |
| ------------------- | ------------------------------------------ |
| Python 3            | `e.py`, tests                              |
| `mpmath`            | `e.py` fallback path (required)            |
| `gmpy2`             | `e.py` fast path (optional, 5-50x speedup) |
| `ruff`              | `make lint`                                |
| `coverage`          | `make coverage`                            |
| GMP + MPFR (C libs) | `gmpy2`, `e-rs` via rug                    |
| Rust 1.85+          | `e-rs`                                     |
| `cargo-tarpaulin`   | `cargo tarpaulin` (Rust coverage)          |

## Running The Script

A `Makefile` is provided in `e/`:

- `make run` -- runs `python3 e.py`
- `make lint` -- runs `ruff check .`
- `make test` -- runs lint then `pytest test_e.py -v`
- `make coverage` -- runs tests and prints a line coverage report
- `make clean` -- removes `__pycache__` and `.coverage`

Run the calculator with:

```bash
make run
# or directly:
python3 e.py
```

CLI contract (shared harness `scripts/cli_contract.py`, run by `make test`):

```bash
python3 e.py 1000            # compute 1000 digits, always writes e_1000_digits.txt
python3 e.py 1000 --show     # also print the digit string (same text as the file's digit line)
python3 e.py --smoke         # quick check at SMOKE_SIZE (10000)
python3 e.py 2000000 --yes   # sizes >= LARGE_RUN_THRESHOLD (1,000,001) are refused (exit 1) without --yes
```

With no arguments at a terminal it prompts for the number of decimal places (a size >= `LARGE_RUN_THRESHOLD` asks `Continue with N digits? (y/n)`; EOF there reads as no and exits 0). EOF at the number prompt exits 1; a bare run with stdin not a terminal exits 2. The output file `e_<digits>_digits.txt` is always written; there is no "display all" prompt.

## Code Layout

The project is intentionally simple and centered in `e.py`.

Taylor series / gmpy2 functions (used when gmpy2 is installed):

- `_taylor_bs(a, b)`: recursive binary splitting for the Taylor series of e; returns `(P, Q)` as `gmpy2.mpz`.
- `_bs_chunk_worker(a, b)`: module-level subprocess worker that computes `_taylor_bs(a, b)` and returns plain Python ints for pickling safety.
- `_tree_combine(pq_list)`: merges a list of `(P, Q)` results via pairwise tree reduction (more GMP-efficient than a linear fold for equal-sized chunks).
- `_calculate_e_gmpy2(digits)`: splits `[0, N)` into `_CPU_COUNT` chunks, dispatches them to a `ProcessPoolExecutor`, tree-combines the results, then computes the final e as `gmpy2.mpfr`; returns `(e_mpfr, P_int, Q_int)`.

String conversion:

- `_e_to_str(e_value, digits)`: unified dispatch -- uses gmpy2 MPFR `digits()` for `gmpy2.mpfr`, otherwise `mpmath.nstr`.
- `_gmpy2_str_from_PQ(P_int, Q_int, digits)`: recomputes e from integer accumulators and converts to decimal string (used in subprocess).

Module-level worker functions (must stay at module level for multiprocessing pickling):

- `_convert_gmpy2_worker(P_int, Q_int, digits)`: subprocess worker for the gmpy2 path; receives plain Python ints (always picklable).
- `_convert_mpmath_worker(e_value, digits)`: subprocess worker for the mpmath fallback path.
- `_pwrite_all(fd, data, offset)`: writes bytes to a file descriptor at an absolute offset using `os.pwrite(2)`; thread-safe.

CLI:

- `parse_args(argv)`: parses command-line arguments via `argparse`; returns a namespace with an optional `size` positional int plus `--show`, `--yes`, `--smoke` (`--smoke` sets `size=SMOKE_SIZE`).
- `refuse_large_run(size, yes)`: exits 1 naming `--yes` when `size >= LARGE_RUN_THRESHOLD` and `--yes` is absent.
- `get_target_digits(args)`: returns the digit count from CLI args if provided, otherwise loops on interactive stdin input; validates that the value is a positive integer; the argument path calls `refuse_large_run`.

Main functions:

- `calculate_e(digits)`: tries gmpy2 Taylor/binary-splitting first, falls back to mpmath; caches `(P_int, Q_int)` in `_gmpy2_PQ_cache` for the subprocess. Returns a `gmpy2.mpfr` (fast path) or `mpmath.mpf` (fallback path).
- `show_e_preview(e_value, preview_digits)`: prints a short preview of the computed digits.
- `save_e_to_file(e_value, digits, filename)`: two-phase save (returns the digit string) -- subprocess conversion then parallel pwrite file write.
- `main(argv=None)`: top-level entry point; calls `parse_args()`, `get_target_digits()`, `calculate_e()`, `show_e_preview()`, then always `save_e_to_file()` (returns the digit string, printed with `--show`).

Module-level constants / state:

- `_gmpy2`: the gmpy2 module, or `None` when the import failed. Code checks `_gmpy2 is not None` (pyright does not carry a caller's check into a callee); gmpy2-only functions call `_require_gmpy2()`, which raises `RuntimeError` when it is `None`. Tests simulate absence by patching `_gmpy2` to `None`.
- `_HAS_GMPY2`: `True` if gmpy2 imported successfully at startup; used only by tests for `skipUnless`, never by `e.py` logic.
- `_gmpy2_PQ_cache`: `(P_int, Q_int)` from the most recent gmpy2 calculation; used to pass picklable data to the subprocess worker.
- `_CPU_COUNT`: result of `os.cpu_count()`.
- `_IO_WORKERS`: number of I/O worker threads (scales with cores, capped at 8).
- `_PWRITE_CHUNK`: chunk size per I/O worker (4 MiB).

## Important Behavior

- **gmpy2 path (fast)**: uses the Taylor series binary-splitting algorithm with GMP big-integer arithmetic (`gmpy2.mpz`), then MPFR for the final floating-point value. The series computation is parallelised across all available CPU cores: `[0, N)` is split into `_CPU_COUNT` equal chunks (minimum 100 terms each), each chunk is computed in a subprocess, and the results are merged in the main process via `_tree_combine` (pairwise tree reduction keeps intermediate GMP multiply sizes balanced).
- **mpmath fallback**: sets precision to `digits + 50` and uses `mpmath.e`. Large runs are dominated by converting the `mpmath` value to a string, not by the calculation itself.
- **gmpy2.mpfr is a C extension type** and does not support arbitrary attribute assignment. The `(P_int, Q_int)` accumulator ints are stored in `_gmpy2_PQ_cache` (module-level) and passed as plain Python ints to the subprocess worker, avoiding any gmpy2 pickling uncertainty.
- String conversion runs in a `ProcessPoolExecutor` subprocess (1 worker) to bypass the GIL; the main thread polls `future.done()` to drive the progress display -- no background thread is used.
- File writing uses `ThreadPoolExecutor` (`_IO_WORKERS` threads) with `os.pwrite(2)` so multiple threads can write non-overlapping chunks concurrently. The file is pre-allocated with `os.ftruncate()` before any writes. A `threading.Lock` (`_progress_lock`) guards `completed_chunks` increments and the progress print.
- On macOS the `spawn` multiprocessing context is used; on Linux `fork` is used.
- The `if __name__ == "__main__":` guard checks `multiprocessing.current_process().name == "MainProcess"` to prevent `main()` from running in worker subprocesses (required on macOS where `spawn` re-executes the script in each worker).

## Keeping This File Up To Date

**Update this file whenever you change the code.** Future Claude sessions rely on it -- stale docs are worse than none. Specifically:

- New or renamed function / constant -> update Code Layout
- Makefile target added or removed -> update the Makefile bullet list here and in `README.md`
- Dependency added -> update Environment section and `scripts/crate_templates/python/install_deps.sh`, then `python3 scripts/render_crate_files.py --write`
- Test class added or coverage % changes -> update the Testing coverage table here and in `README.md`
- Behaviour or algorithm change -> update Important Behavior

Also update the top-level `CLAUDE.md` if the change affects the repository overview or quick-reference targets.

## Editing Guidance

- **Write the failing test first** for all new or changed functions, then add the minimum implementation. Tests go in `test_e.py`.
- Keep changes minimal and preserve the single-file CLI structure unless a refactor is clearly necessary.
- Preserve the current interactive behavior unless the task explicitly changes UX.
- Ensure every script in the repository supports `-h` and `--help` with accurate command-line usage text.
- `_convert_gmpy2_worker`, `_convert_mpmath_worker`, `_bs_chunk_worker`, and `_pwrite_all` must remain at module level -- moving them inside a function or class will break multiprocessing pickling.
- Do not remove the `current_process().name == "MainProcess"` check from the `if __name__ == "__main__":` block -- it is required to prevent infinite subprocess spawning on macOS (where `spawn` re-executes the script in each worker).
- Do not attempt to set arbitrary attributes on `gmpy2.mpfr` objects -- they are C extension types with fixed slots. Use `_gmpy2_PQ_cache` to pass data between the calculation and the subprocess worker.
- Avoid committing regenerated large output files unless the task explicitly requires updating them.

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass. Never write implementation before the test. Tests must be added in the same commit as the code they cover.

Every test must cover more than the happy path. Three categories are required for every function:

- **Boundary value tests** -- empty/zero/null input, single vs multiple elements, min/max valid values, one above/below valid range
- **Error path tests** -- what happens on failure, dependency failure, partial failure
- **State transition tests** -- before/after assertions, no unintended side effects, idempotency

### Python (`test_e.py`)

Run the full suite:

```bash
make test      # pytest test_e.py -v
make coverage  # run tests + print coverage report
```

Or directly:

```bash
pytest test_e.py -v
python3 -m pytest test_e.py -v   # if pytest is installed
```

gmpy2-dependent tests are automatically skipped when gmpy2 is not installed.

#### Test coverage (94% line coverage, 103 tests)

| Class                                | Tests | Notes                                                                   |
| ------------------------------------ | ----- | ----------------------------------------------------------------------- |
| `TestTreeCombine`                    | 7     | Pure Python -- always runs; includes empty-list boundary                |
| `TestTaylorBS`                       | 7     | Skipped without gmpy2                                                   |
| `TestBsChunkWorker`                  | 3     | Skipped without gmpy2                                                   |
| `TestEToStr`                         | 6     | Format + known-digit checks                                             |
| `TestEAccuracy`                      | 4     | End-to-end vs reference e                                               |
| `TestMpmathFallback`                 | 2     | Always runs                                                             |
| `TestCalculateEParallel`             | 1     | Skipped without gmpy2                                                   |
| `TestCalculateEGmpy2PhaseAFallback`  | 1     | OSError triggers serial fallback in `_calculate_e_gmpy2`                |
| `TestGetTargetDigits`                | 5     | Argument parsing; includes minimum value (digits=1)                     |
| `TestParseArgs`                      | 7     | CLI flag parsing                                                        |
| `TestShowEPreview`                   | 4     | stdout capture                                                          |
| `TestSaveEToFile`                    | 5     | File write + content checks                                             |
| `TestETostrEdgeCases`                | 1     | Negative-mpfr sign-strip branch in `_e_to_str`                          |
| `TestShowEPreviewNoDecimal`          | 1     | Else branch when preview string lacks `.`                               |
| `TestGmpy2WorkerFunctions`           | 2     | Direct dispatch of `_gmpy2_str_from_PQ` and `_convert_gmpy2_worker`     |
| `TestConvertMpmathWorker`            | 1     | Direct dispatch of `_convert_mpmath_worker`                             |
| `TestPwriteAllStall`                 | 1     | Stall path in `_pwrite_all` (returns 0)                                 |
| `TestSaveEEstimateAndProgress`       | 1     | Exercises `estimate_conversion_time` tiers via patched ProcessPool      |
| `TestSaveEToFilePhaseAFallback`      | 1     | OSError triggers serial fallback in `save_e_to_file`                    |
| `TestGetTargetDigitsInteractive`     | 5     | Interactive prompt: valid, retries, large-N decline + accept            |
| `TestMain`                           | 15    | Always-save, --show, large-run refusal/--yes, error handlers            |
| `TestCliContractConstants`           | 2     | Pins SMOKE_SIZE and LARGE_RUN_THRESHOLD                                 |
| `TestRefuseLargeRun`                 | 1     | Threshold boundaries                                                    |
| `TestEntryPointGuard`                | 1     | Module runs via subprocess (`if __name__ == "__main__"` block)          |
| `TestProcessPoolPermissionError`     | 1     | PermissionError triggers serial fallback in `save_e_to_file`            |
| `TestProcessPoolSemaphoreExhaustion` | 2     | OSError and errno.ENOSPC trigger serial fallback in `save_e_to_file`    |
| `TestMissingGmpy2`                   | 1     | mpmath path used when `_gmpy2` is patched to None                       |
| `TestRequireGmpy2`                   | 3     | `_require_gmpy2` raises without gmpy2, returns the module with it       |
| `TestSaveEToFileWithoutGmpy2`        | 1     | `save_e_to_file` takes the mpmath path when `_gmpy2` is None            |
| `TestFileWritePermissionError`       | 1     | `main()` exits 1 on `PermissionError` when creating output file         |

#### Type checking

`pyrightconfig.json` runs pyright at `standard` with `stubPath` `../typings`: gmpy2 ships no stubs, so the vendored `typings/gmpy2/__init__.pyi` (exact, never claiming more than gmpy2 does at runtime; no `Any`, and `object` only for `__eq__`/`__ne__` `other`, both guarded by `tests/test_gmpy2_stub.py`, including string annotations) types the names e and pi use. Add a name to the stub before using a new gmpy2 attribute. Run `cd e && pyright`.

#### Adding new tests

- Add tests to `test_e.py` alongside any new or changed function.
- Use `@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")` on classes that require gmpy2.
- Accuracy tests should verify against the `E_REF` constant (first 50 known decimal places of e).
- Use `_quiet_e(digits)` (defined in the test file) to suppress stdout when calling `calculate_e` inside tests.

## Notes

- Existing `.txt` files are generated artifacts and may be large.
