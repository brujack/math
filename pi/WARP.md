# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Repository Overview

This is a Python project for high-precision mathematical calculations, currently focused on calculating π to arbitrary precision using the `mpmath` library. The repository contains a standalone script that performs interactive calculations with optimized performance for large digit counts.

## Dependencies

**Required:**

- Python 3.x
- `mpmath` library (for arbitrary-precision arithmetic)

**Installation:**

```bash
pip install mpmath
```

## Running the Code

### Main π Calculator

```bash
python3 pi.py
```

The script is interactive and will prompt for:

1. Number of decimal places (1-1,000,000+)
2. Display preference (show all digits or save to file)

**Output files:** Generated files follow the pattern `pi_{digits}_digits.txt`

### Performance Characteristics

- **Small calculations** (<10,000 digits): Fast, can display in terminal
- **Medium calculations** (10,000-1,000,000 digits): Automatic file saving with progress indicators
- **Large calculations** (>1,000,000 digits): Significant conversion time (non-linear growth)
  - 1M digits: ~2-5 seconds conversion
  - 10M digits: ~300-600 seconds conversion

The script includes:

- Progress bars with ETA for string conversion
- Countdown timers for file writing
- Chunked file I/O for large outputs
- Thread-based progress indicators

## Code Architecture

### Core Structure

**`pi.py`** - Single-file application with four main components:

1. **`calculate_pi_high_precision(digits)`**
   - Sets precision using `mpmath.mp.dps`
   - Uses mpmath's built-in π calculation
   - Returns high-precision `mpmath.mpf` object

2. **`show_pi_preview(pi_value, preview_digits)`**
   - Generates terminal preview (capped at 200 digits)
   - Formats output with integer/decimal separation

3. **`save_pi_to_file(pi_value, digits, filename)`**
   - **Most complex function** - handles large number conversion bottleneck
   - `ProgressIndicator` class: Threaded progress display with dynamic ETA estimation
   - `estimate_conversion_time()`: Empirical formula for time prediction based on digit count
   - Chunked file writing (1MB chunks) with progress tracking
   - Buffered I/O optimization (`buffering=8192*16`)

4. **`main()`**
   - Interactive CLI with input validation
   - Handles KeyboardInterrupt gracefully
   - Automatic file saving for >10,000 digits

### Key Implementation Details

**Precision Management:**

- Uses `digits + 50` extra precision for intermediate calculations
- Converts to string using `mpmath.nstr(value, digits+1, strip_zeros=False)`

**Performance Bottleneck:**

- String conversion from `mpmath.mpf` to text is the slowest operation (not the calculation itself)
- Conversion time grows non-linearly: O(n^1.5) to O(n^2) for very large numbers

**Threading:**

- Progress indicator runs in daemon thread
- Prevents blocking during long conversion operations

## Security

- Always run Snyk code scans for new Python code
- Fix any security issues found before committing
- Rescan after fixes to ensure no new issues introduced

## Development Notes

- This is a standalone script with no test suite
- No linting/formatting configuration present
- No build or compilation steps required
- The script is executable with shebang: `#!/usr/bin/env python3`
