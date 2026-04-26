# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This repository contains a small Python CLI for calculating π to high precision. It uses the Chudnovsky algorithm with `gmpy2`/GMP (fast path) and falls back to `mpmath` if `gmpy2` is not installed.

Current structure:

- `pi.py`: interactive calculator script (Python, gmpy2/GMP + mpmath fallback)
- `pi-rs/`: Rust implementation — Chudnovsky + Rayon + rug/GMP/MPFR (best for >50M digits)
- `install_deps.sh`: installs GMP, MPFR, and gmpy2 on macOS and Linux
- `pi_1000000_digits.txt`: sample/generated output file
- `pi_10000000_digits.txt`: sample/generated output file
- `WARP.md`: similar repository guidance for Warp

## Rust Implementation (`pi-rs/`)

The Rust binary targets >50M digit workloads where the Python subprocess IPC overhead becomes significant.

Key differences from Python:

- Uses `rayon::join()` for recursive parallel binary splitting — threads share memory, zero IPC/serialisation cost
- `rug` wraps GMP (`Integer`) and MPFR (`Float`) directly — same C libraries as Python's gmpy2
- Parallel file I/O via `FileExt::write_at` (POSIX pwrite equivalent) dispatched by rayon

Build (requires GMP + MPFR — run `install_deps.sh` first):

```bash
cd pi-rs
make pi          # builds release binary and copies it to ~/Downloads/pi
./target/release/pi [digits]
```

A `Makefile` is provided in `pi-rs/`:

- `make pi` — runs `cargo build --release` and copies the binary to `~/Downloads/pi`
- `make lint` — runs `cargo clippy -- -D warnings`
- `make test` — runs lint then `cargo test`
- `make clean` — runs `cargo clean` and removes `~/Downloads/pi`

### Rust Code Layout (`pi-rs/src/main.rs`)

- `BS_PAR_THRESHOLD`: switch from `rayon::join()` to serial recursion below this range size (512 terms); rayon work-stealing handles load-balancing
- `BS_LEAF_COUNT` (`static AtomicU64`): counts completed leaf nodes during `bs()`; read every 200 ms by the series progress thread to display percentage
- `struct Pqt { p, q, t: Integer }`: accumulator for a Chudnovsky range `[a, b)`
- `fn bs(a, b)`: recursive binary splitting; uses `rayon::join()` above threshold, serial recursion below
- `fn bs_leaf(a)`: leaf computation with `rug::Integer`; increments `BS_LEAF_COUNT` on every call
- `fn bs_merge(l, r)`: combines two adjacent ranges
- `fn compute_pi(digits)`: resets `BS_LEAF_COUNT`, spawns a progress thread that prints series completion % every 200 ms, runs `bs(0, n)`, joins the thread, then builds `rug::Float` and calls `pi_to_string`
- `fn pi_to_string(pi, digits)`: uses `pi.to_string_radix(10, Some(digits+5))`, trims to exact decimal places
- `fn write_pi_file`: `#[cfg(unix)]` — pre-allocates with `file.set_len()`, spawns a progress thread reporting write % and MB/s every 200 ms, parallel pwrite via rayon `par_chunks` (each chunk updates an `Arc<AtomicU64>` byte counter), joins thread and prints final MB/s
- `fn fmt_int(n)`: formats with thousands separators

### rug Arithmetic Note

`rug::Integer` operator overloading uses lazy "incomplete" types: `&Integer * &Integer` returns `MulIncomplete<'_>`, not `Integer`. Always wrap with `Integer::from(...)` before using the result in further operations:

```rust
// Correct:
Integer::from(&l.p * &r.p)
Integer::from(&r.q * &l.t) + Integer::from(&l.p * &r.t)
// Wrong (will not compile):
&l.p * &r.p + &l.q * &r.q
```

## Environment

Each implementation has its own installer:

```bash
bash pi/install_deps.sh        # pi.py — GMP + MPFR, mpmath, gmpy2, coverage
bash pi/pi-rs/install_deps.sh  # pi-rs — GMP + MPFR, Rust toolchain, cargo-tarpaulin
```

Requirements summary:

| Dependency          | Required for                                |
| ------------------- | ------------------------------------------- |
| Python 3            | `pi.py`, tests                              |
| `mpmath`            | `pi.py` fallback path (required)            |
| `gmpy2`             | `pi.py` fast path (optional, 5–50× speedup) |
| `coverage`          | `make coverage`                             |
| GMP + MPFR (C libs) | `gmpy2`, `pi-rs` via rug                    |
| Rust 1.85+          | `pi-rs`                                     |
| `cargo-tarpaulin`   | `cargo tarpaulin` (Rust coverage)           |

## Running The Script

A `Makefile` is provided in `pi/`:

- `make run` — runs `python3 pi.py`
- `make lint` — runs `ruff check .`
- `make test` — runs lint then `python3 -m unittest test_pi -v`
- `make coverage` — runs tests and prints a line coverage report
- `make clean` — removes `__pycache__` and `.coverage`

Run the calculator with:

```bash
make run
# or directly:
python3 pi.py
```

The script is interactive. It prompts for:

1. The number of decimal places to compute.
2. Whether to print the result directly or save it to a file.

For values greater than `10000`, the script saves output automatically to a file named like `pi_<digits>_digits.txt`.

## Code Layout

The project is intentionally simple and centered in `pi.py`.

Chudnovsky / gmpy2 functions (used when gmpy2 is installed):

- `_chudnovsky_bs(a, b)`: recursive binary splitting; returns `(P, Q, T)` as `gmpy2.mpz`.
- `_bs_chunk_worker(a, b)`: module-level subprocess worker that computes `_chudnovsky_bs(a, b)` and returns plain Python ints for pickling safety.
- `_tree_combine(pqt_list)`: merges a list of `(P, Q, T)` results via pairwise tree reduction (more GMP-efficient than a linear fold for equal-sized chunks).
- `_calculate_pi_gmpy2(digits)`: splits `[0, N)` into `_CPU_COUNT` chunks, dispatches them to a `ProcessPoolExecutor`, tree-combines the results, then computes the final π as `gmpy2.mpfr`; returns `(pi_mpfr, Q_int, T_int)`.
- `_gmpy2_str_from_QT(Q_int, T_int, digits)`: recomputes π from integer accumulators and converts to decimal string (used in subprocess).
- `_gmpy2_mpfr_to_str(pi_mpfr, digits)`: fast in-process string conversion for preview.

Module-level worker functions (must stay at module level for multiprocessing pickling):

- `_convert_gmpy2_worker(Q_int, T_int, digits)`: subprocess worker for the gmpy2 path; receives plain Python ints (always picklable).
- `_convert_mpmath_worker(pi_value, digits)`: subprocess worker for the mpmath fallback path.
- `_pwrite_all(fd, data, offset)`: writes bytes to a file descriptor at an absolute offset using `os.pwrite(2)`; thread-safe.
- `_progress_lock` (inside `save_pi_to_file`): `threading.Lock` that serialises `completed_chunks` updates and the progress `print` across the I/O worker threads.

String conversion:

- `_pi_to_str(pi_value, digits)`: unified dispatch — uses `_gmpy2_mpfr_to_str` for `gmpy2.mpfr`, otherwise `mpmath.nstr`.

CLI:

- `parse_args()`: parses command-line arguments via `argparse`; returns a namespace with an optional `digits` positional int.
- `get_target_digits(args)`: returns the digit count from CLI args if provided, otherwise loops on interactive stdin input; validates that the value is a positive integer.

Main functions:

- `calculate_pi_high_precision(digits)`: tries gmpy2 Chudnovsky first, falls back to mpmath; caches `(Q_int, T_int)` in `_gmpy2_QT_cache` for the subprocess. Returns a `gmpy2.mpfr` (fast path) or `mpmath.mpf` (fallback path).
- `show_pi_preview(pi_value, preview_digits)`: prints a short preview of the computed digits.
- `save_pi_to_file(pi_value, digits, filename)`: two-phase save — subprocess conversion then parallel pwrite file write.
- `main()`: top-level entry point; calls `parse_args()`, `get_target_digits()`, `calculate_pi_high_precision()`, and either `show_pi_preview()` or `save_pi_to_file()` based on digit count.

Module-level constants / state:

- `_HAS_GMPY2`: `True` if gmpy2 imported successfully at startup.
- `_gmpy2_QT_cache`: `(Q_int, T_int)` from the most recent gmpy2 calculation; used to pass picklable data to the subprocess worker.
- `_CPU_COUNT`: result of `os.cpu_count()`.
- `_IO_WORKERS`: number of I/O worker threads (scales with cores, capped at 8).
- `_PWRITE_CHUNK`: chunk size per I/O worker (4 MiB).
- `_CHU_A`, `_CHU_B`, `_CHU_C3_OVER_24`: Chudnovsky series constants.

## Important Behavior

- **gmpy2 path (fast)**: uses the Chudnovsky binary-splitting algorithm with GMP big-integer arithmetic (`gmpy2.mpz`), then MPFR for the final floating-point value. Each Chudnovsky term contributes ≈14.18 decimal digits; recursion depth is O(log N), well within Python's stack limit. The series computation is parallelised across all available CPU cores: `[0, N)` is split into `_CPU_COUNT` equal chunks (minimum 100 terms each), each chunk is computed in a subprocess, and the results are merged in the main process via `_tree_combine` (pairwise tree reduction keeps intermediate GMP multiply sizes balanced).
- **mpmath fallback**: sets precision to `digits + 50` and uses `mpmath.pi`. Large runs are dominated by converting the `mpmath` value to a string, not by the calculation itself.
- **gmpy2.mpfr is a C extension type** and does not support arbitrary attribute assignment. The `(Q_int, T_int)` accumulator ints are stored in `_gmpy2_QT_cache` (module-level) and passed as plain Python ints to the subprocess worker, avoiding any gmpy2 pickling uncertainty.
- String conversion runs in a `ProcessPoolExecutor` subprocess (1 worker) to bypass the GIL; the main thread polls `future.done()` to drive the progress display — no background thread is used.
- File writing uses `ThreadPoolExecutor` (`_IO_WORKERS` threads) with `os.pwrite(2)` so multiple threads can write non-overlapping chunks concurrently. The file is pre-allocated with `os.ftruncate()` before any writes. A `threading.Lock` (`_progress_lock`) guards `completed_chunks` increments and the progress print inside `write_chunk` to prevent data races on the shared counter and interleaved terminal output.
- On macOS the `spawn` multiprocessing context is used; on Linux `fork` is used.
- The `if __name__ == "__main__":` guard checks `multiprocessing.current_process().name == "MainProcess"` to prevent `main()` from running in worker subprocesses (required on macOS where `spawn` re-executes the script in each worker).
- Very large output files can be slow to generate and should not be casually regenerated during routine edits.

## Keeping This File Up To Date

**Update this file whenever you change the code.** Future Claude sessions rely on it — stale docs are worse than none. Specifically:

- New or renamed function / constant → update Code Layout
- Makefile target added or removed → update the Makefile bullet list here and in `README.md`
- Dependency added → update Environment section and `install_deps.sh`
- Test class added or coverage % changes → update the Testing coverage table here and in `README.md`
- Behaviour or algorithm change → update Important Behavior

Also update the top-level `CLAUDE.md` if the change affects the repository overview or quick-reference targets.

## Editing Guidance

- **Write the failing test first** for all new or changed functions, then add the minimum implementation. Tests go in `test_pi.py`.
- Keep changes minimal and preserve the single-file CLI structure unless a refactor is clearly necessary.
- Preserve the current interactive behavior unless the task explicitly changes UX.
- Ensure every script in the repository supports `-h` and `--help` with accurate command-line usage text.
- Be careful with performance changes inside `save_pi_to_file`, since that function handles the main large-number bottleneck.
- `_convert_gmpy2_worker`, `_convert_mpmath_worker`, `_bs_chunk_worker`, and `_pwrite_all` must remain at module level — moving them inside a function or class will break multiprocessing pickling.
- Do not remove the `current_process().name == "MainProcess"` check from the `if __name__ == "__main__":` block — it is required to prevent infinite subprocess spawning on macOS (where `spawn` re-executes the script in each worker).
- Do not attempt to set arbitrary attributes on `gmpy2.mpfr` objects — they are C extension types with fixed slots. Use `_gmpy2_QT_cache` to pass data between the calculation and the subprocess worker.
- Avoid committing regenerated large output files unless the task explicitly requires updating them.

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass. Never write implementation before the test. Tests must be added in the same commit as the code they cover — both Python and Rust.

Every test must cover more than the happy path. Three categories are required for every function:

- **Boundary value tests** — empty/zero/null input, single vs multiple elements, min/max valid values, one above/below valid range
- **Error path tests** — what happens on failure, dependency failure, partial failure
- **State transition tests** — before/after assertions, no unintended side effects, idempotency

### Python (`test_pi.py`)

Run the full suite:

```bash
make test      # python3 -m unittest test_pi -v
make coverage  # run tests + print coverage report
```

Or directly:

```bash
python3 -m unittest test_pi -v
python3 -m pytest test_pi.py -v   # if pytest is installed
```

gmpy2-dependent tests are automatically skipped when gmpy2 is not installed.

#### Test coverage (93% line coverage, 77 tests)

| Class                            | Tests | Notes                                                                   |
| -------------------------------- | ----- | ----------------------------------------------------------------------- |
| `TestTreeCombine`                | 7     | Pure Python — always runs; includes empty-list boundary                 |
| `TestPwriteAll`                  | 4     | POSIX pwrite — always runs                                              |
| `TestPwriteAllStall`             | 1     | Error path — always runs                                                |
| `TestChudnovskyBS`               | 7     | Skipped without gmpy2                                                   |
| `TestBsChunkWorker`              | 3     | Skipped without gmpy2                                                   |
| `TestGmpy2Conversions`           | 5     | Skipped without gmpy2                                                   |
| `TestConvertGmpy2Worker`         | 2     | Skipped without gmpy2                                                   |
| `TestConvertMpmathWorker`        | 3     | Always runs                                                             |
| `TestMpmathFallback`             | 2     | Always runs                                                             |
| `TestPiToStr`                    | 6     | Format + known-digit checks                                             |
| `TestPiAccuracy`                 | 4     | End-to-end vs reference π                                               |
| `TestShowPiPreview`              | 4     | stdout capture                                                          |
| `TestSavePiToFile`               | 5     | File write + content checks                                             |
| `TestCalculatePiParallel`        | 1     | Skipped without gmpy2                                                   |
| `TestGetTargetDigits`            | 5     | Argument parsing; includes minimum value (digits=1)                     |
| `TestParseArgs`                  | 3     | CLI flag parsing                                                        |
| `TestPiToStrNegativeSign`        | 1     | Negative-mpfr sign-strip branch in `_gmpy2_mpfr_to_str`                 |
| `TestShowPiPreviewNoDecimal`     | 1     | Else branch when preview string lacks `.`                               |
| `TestGetTargetDigitsInteractive` | 5     | Interactive prompt: valid, retries, large-N decline + accept            |
| `TestSavePiEstimateAndProgress`  | 1     | Exercises `estimate_conversion_time` tiers via patched ProcessPool      |
| `TestMain`                       | 5     | Display/save branches, ValueError, KeyboardInterrupt, generic exception |
| `TestEntryPointGuard`            | 1     | Module runs via subprocess (`if __name__ == "__main__"` block)          |

#### Adding new tests

- Add tests to `test_pi.py` alongside any new or changed function.
- Use `@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")` on classes that require gmpy2.
- Accuracy tests should verify against the `PI_REF` constant (first 50 known decimal places of π).
- Use `_quiet_pi(digits)` (defined in the test file) to suppress stdout when calling `calculate_pi_high_precision` inside tests.

### Rust (`pi-rs/`)

Tests live in a `#[cfg(test)] mod tests` block at the bottom of `src/main.rs`.

Run the full suite:

```bash
cd pi-rs
cargo test
```

Check coverage (requires `cargo-tarpaulin`):

```bash
cargo install cargo-tarpaulin   # one-time install
cargo tarpaulin --out Stdout
```

#### Test coverage (39% line coverage, 19 tests)

Below the project standard of >=90% — `write_pi_file` (parallel pwrite I/O), `prompt_digits` / `read_line` (interactive stdin), and `main()` are integration-level uncovered.

| Area                   | Tests | Notes                                                                          |
| ---------------------- | ----- | ------------------------------------------------------------------------------ |
| `fmt_int`              | 5     | zero, sub-thousand, thousands, millions, billions                              |
| `bs_leaf`              | 4     | base case, index-1 formulas, even/odd sign, counter delta                      |
| `bs_merge`             | 1     | result matches manual merge of two leaves                                      |
| `bs` split consistency | 2     | n=4 and n=8 split/merge round-trip                                             |
| `pi_to_string`         | 5     | format, exact length, no exponent notation, known digits, single decimal place |
| `compute_pi`           | 2     | end-to-end accuracy at 10 and 50 decimal places                                |

Uncovered lines: `write_pi_file` (parallel pwrite I/O), `prompt_digits` / `read_line` (interactive stdin), `main()` — all integration-level only.

#### Adding new tests

- Add tests to the `#[cfg(test)] mod tests` block in `src/main.rs`.
- Use `const PI_REF: &str = "3.14159265358979323846264338327950288419716939937510"` for accuracy assertions.
- `BS_LEAF_COUNT` is a global atomic — check deltas, not absolute values, since tests run in parallel threads.

## Notes

- Existing `.txt` files are generated artifacts and may be large.
