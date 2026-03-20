# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This repository contains a small Python CLI for calculating π to high precision with `mpmath`.

Current structure:

- `pi.py`: interactive calculator script
- `pi_1000000_digits.txt`: sample/generated output file
- `pi_10000000_digits.txt`: sample/generated output file
- `WARP.md`: similar repository guidance for Warp

## Environment

Requirements:

- Python 3
- `mpmath`

Install dependency:

```bash
python3 -m pip install mpmath
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

Module-level worker functions (must stay at module level for multiprocessing pickling):

- `_convert_pi_worker(pi_value, digits)`: subprocess worker that runs `mpmath.nstr()` outside the GIL.
- `_pwrite_all(fd, data, offset)`: writes bytes to a file descriptor at an absolute offset using `os.pwrite(2)`; thread-safe.

Main functions:

- `calculate_pi_high_precision(digits)`: sets `mpmath` precision and obtains π.
- `show_pi_preview(pi_value, preview_digits)`: prints a short preview of the computed digits.
- `save_pi_to_file(pi_value, digits, filename)`: two-phase save — subprocess conversion then parallel pwrite file write.
- `main()`: interactive entry point and control flow.

Module-level constants:

- `_CPU_COUNT`: result of `os.cpu_count()`.
- `_IO_WORKERS`: number of I/O worker threads (scales with cores, capped at 8).
- `_PWRITE_CHUNK`: chunk size per I/O worker (4 MiB).

## Important Behavior

- Precision is set to `digits + 50` to preserve accuracy during conversion.
- Large runs are dominated by converting the `mpmath` value to a string, not by calculating π itself.
- String conversion runs in a `ProcessPoolExecutor` subprocess (1 worker) to bypass the GIL; the main thread polls `future.done()` to drive the progress display — no background thread is used.
- File writing uses `ThreadPoolExecutor` (`_IO_WORKERS` threads) with `os.pwrite(2)` so multiple threads can write non-overlapping chunks concurrently. The file is pre-allocated with `os.ftruncate()` before any writes.
- On macOS the `spawn` multiprocessing context is used; on Linux `fork` is used.
- The `if __name__ == "__main__":` guard checks `multiprocessing.current_process().name == "MainProcess"` to prevent `main()` from running in worker subprocesses (required on macOS where `spawn` re-executes the script in each worker).
- Very large output files can be slow to generate and should not be casually regenerated during routine edits.

## Editing Guidance

- Keep changes minimal and preserve the single-file CLI structure unless a refactor is clearly necessary.
- Preserve the current interactive behavior unless the task explicitly changes UX.
- Ensure every script in the repository supports `-h` and `--help` with accurate command-line usage text.
- Be careful with performance changes inside `save_pi_to_file`, since that function handles the main large-number bottleneck.
- `_convert_pi_worker` and `_pwrite_all` must remain at module level — moving them inside a function or class will break multiprocessing pickling.
- Do not add the `if __name__ == "__main__":` guard to worker subprocesses or remove the `current_process().name` check — both are required to prevent infinite subprocess spawning on macOS.
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
