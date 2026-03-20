# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This repository contains a small Python CLI for calculating π to high precision.  It uses the Chudnovsky algorithm with `gmpy2`/GMP (fast path) and falls back to `mpmath` if `gmpy2` is not installed.

Current structure:

- `pi.py`: interactive calculator script
- `install_deps.sh`: installs GMP, MPFR, and gmpy2 on macOS and Linux
- `pi_1000000_digits.txt`: sample/generated output file
- `pi_10000000_digits.txt`: sample/generated output file
- `WARP.md`: similar repository guidance for Warp

## Environment

Requirements:

- Python 3
- `mpmath` (required)
- `gmpy2` (optional but strongly recommended — 5–50x faster)

Install all dependencies (macOS and Linux):

```bash
bash install_deps.sh
```

Or manually:

```bash
# macOS
brew install gmp mpfr && pip install mpmath gmpy2

# Debian / Ubuntu
sudo apt install libgmp-dev libmpfr-dev && pip install mpmath gmpy2

# RHEL / Fedora
sudo dnf install gmp-devel mpfr-devel && pip install mpmath gmpy2
```

## Running The Script

Run the calculator with:

```bash
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
- `_calculate_pi_gmpy2(digits)`: runs binary splitting then computes π as `gmpy2.mpfr`; returns `(pi_mpfr, Q_int, T_int)`.
- `_gmpy2_str_from_QT(Q_int, T_int, digits)`: recomputes π from integer accumulators and converts to decimal string (used in subprocess).
- `_gmpy2_mpfr_to_str(pi_mpfr, digits)`: fast in-process string conversion for preview.

Module-level worker functions (must stay at module level for multiprocessing pickling):

- `_convert_gmpy2_worker(Q_int, T_int, digits)`: subprocess worker for the gmpy2 path; receives plain Python ints (always picklable).
- `_convert_mpmath_worker(pi_value, digits)`: subprocess worker for the mpmath fallback path.
- `_pwrite_all(fd, data, offset)`: writes bytes to a file descriptor at an absolute offset using `os.pwrite(2)`; thread-safe.
- `_progress_lock` (inside `save_pi_to_file`): `threading.Lock` that serialises `completed_chunks` updates and the progress `print` across the I/O worker threads.

String conversion:

- `_pi_to_str(pi_value, digits)`: unified dispatch — uses `_gmpy2_mpfr_to_str` for `gmpy2.mpfr`, otherwise `mpmath.nstr`.

Main functions:

- `calculate_pi_high_precision(digits)`: tries gmpy2 Chudnovsky first, falls back to mpmath; caches `(Q_int, T_int)` in `_gmpy2_QT_cache` for the subprocess.
- `show_pi_preview(pi_value, preview_digits)`: prints a short preview of the computed digits.
- `save_pi_to_file(pi_value, digits, filename)`: two-phase save — subprocess conversion then parallel pwrite file write.
- `main()`: interactive entry point and control flow.

Module-level constants / state:

- `_HAS_GMPY2`: `True` if gmpy2 imported successfully at startup.
- `_gmpy2_QT_cache`: `(Q_int, T_int)` from the most recent gmpy2 calculation; used to pass picklable data to the subprocess worker.
- `_CPU_COUNT`: result of `os.cpu_count()`.
- `_IO_WORKERS`: number of I/O worker threads (scales with cores, capped at 8).
- `_PWRITE_CHUNK`: chunk size per I/O worker (4 MiB).
- `_CHU_A`, `_CHU_B`, `_CHU_C3_OVER_24`: Chudnovsky series constants.

## Important Behavior

- **gmpy2 path (fast)**: uses the Chudnovsky binary-splitting algorithm with GMP big-integer arithmetic (`gmpy2.mpz`), then MPFR for the final floating-point value.  Each Chudnovsky term contributes ≈14.18 decimal digits; recursion depth is O(log N), well within Python's stack limit.
- **mpmath fallback**: sets precision to `digits + 50` and uses `mpmath.pi`.  Large runs are dominated by converting the `mpmath` value to a string, not by the calculation itself.
- **gmpy2.mpfr is a C extension type** and does not support arbitrary attribute assignment.  The `(Q_int, T_int)` accumulator ints are stored in `_gmpy2_QT_cache` (module-level) and passed as plain Python ints to the subprocess worker, avoiding any gmpy2 pickling uncertainty.
- String conversion runs in a `ProcessPoolExecutor` subprocess (1 worker) to bypass the GIL; the main thread polls `future.done()` to drive the progress display — no background thread is used.
- File writing uses `ThreadPoolExecutor` (`_IO_WORKERS` threads) with `os.pwrite(2)` so multiple threads can write non-overlapping chunks concurrently. The file is pre-allocated with `os.ftruncate()` before any writes.  A `threading.Lock` (`_progress_lock`) guards `completed_chunks` increments and the progress print inside `write_chunk` to prevent data races on the shared counter and interleaved terminal output.
- On macOS the `spawn` multiprocessing context is used; on Linux `fork` is used.
- The `if __name__ == "__main__":` guard checks `multiprocessing.current_process().name == "MainProcess"` to prevent `main()` from running in worker subprocesses (required on macOS where `spawn` re-executes the script in each worker).
- Very large output files can be slow to generate and should not be casually regenerated during routine edits.

## Editing Guidance

- Keep changes minimal and preserve the single-file CLI structure unless a refactor is clearly necessary.
- Preserve the current interactive behavior unless the task explicitly changes UX.
- Ensure every script in the repository supports `-h` and `--help` with accurate command-line usage text.
- Be careful with performance changes inside `save_pi_to_file`, since that function handles the main large-number bottleneck.
- `_convert_gmpy2_worker`, `_convert_mpmath_worker`, and `_pwrite_all` must remain at module level — moving them inside a function or class will break multiprocessing pickling.
- Do not remove the `current_process().name == "MainProcess"` check from the `if __name__ == "__main__":` block — it is required to prevent infinite subprocess spawning on macOS (where `spawn` re-executes the script in each worker).
- Do not attempt to set arbitrary attributes on `gmpy2.mpfr` objects — they are C extension types with fixed slots.  Use `_gmpy2_QT_cache` to pass data between the calculation and the subprocess worker.
- Avoid committing regenerated large output files unless the task explicitly requires updating them.

## Validation

There is no formal test suite in this repository.

Useful validation steps:

```bash
python3 pi.py
```

For quick manual verification, use a small value such as `10` or `50` digits.

## Notes

- There is no build system, packaging setup, or lint configuration in the repository.
- Existing `.txt` files are generated artifacts and may be large.
