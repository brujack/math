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

Main functions:

- `calculate_pi_high_precision(digits)`: sets `mpmath` precision and obtains π.
- `show_pi_preview(pi_value, preview_digits)`: prints a short preview of the computed digits.
- `save_pi_to_file(pi_value, digits, filename)`: handles long-running string conversion and chunked file writing with progress output.
- `main()`: interactive entry point and control flow.

## Important Behavior

- Precision is set to `digits + 50` to preserve accuracy during conversion.
- Large runs are dominated by converting the `mpmath` value to a string, not by calculating π itself.
- The script uses a background thread only for progress display during long conversion work.
- Very large output files can be slow to generate and should not be casually regenerated during routine edits.

## Editing Guidance

- Keep changes minimal and preserve the single-file CLI structure unless a refactor is clearly necessary.
- Preserve the current interactive behavior unless the task explicitly changes UX.
- Be careful with performance changes inside `save_pi_to_file`, since that function handles the main large-number bottleneck.
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
