# CLAUDE.md

This file provides guidance to Claude when working with code in this directory.

## Repository Overview

Python CLI that finds Collatz chain record-setters up to 10^N.

Chain length = steps to reach 1 (not counting the starting number).
`chain_length(1)=0`, `chain_length(2)=1`, `chain_length(27)=111`.

A record-setter is a number whose chain length strictly exceeds all prior numbers'.

## Running the Script

```bash
make run       # python3 collatz.py (interactive)
make lint      # ruff check .
make test      # lint + pytest test_collatz.py -v + shared CLI contract harness
make coverage  # pytest --cov, fails under 90%
```

Or directly:

```bash
python3 collatz.py          # interactive prompt (terminal only)
python3 collatz.py 6        # scan 1..10^6, write collatz_1e6.txt
python3 collatz.py 6 --show # also echo each record
python3 collatz.py --smoke  # quick check at N=5
```

## Code Layout

- `collatz_next(n)` — single Collatz step: n//2 if even, 3n+1 if odd
- `collatz_length(n, cache)` — walk from n, back-fill cache, return chain length
- `generate_records(limit)` — allocates `array.array('I', ...)`, yields (n, length) for each record
- `SMOKE_SIZE = 5`, `LARGE_RUN_THRESHOLD = None` — CLI contract constants (no large-run confirmation here)
- `parse_args(argv)` — optional positional `size` (N), `--show`, `--yes`, `--smoke`; bare non-TTY run exits 2
- `refuse_large_run(size, yes)` — no-op while the threshold is None
- `get_exponent(args)` — validates N in [1,12]; warns N>7; interactive prompt if absent (EOF exits 1 with a stderr message)
- `main(argv)` — buffers records, always saves `collatz_1eN.txt`, prints `Saved <k> records to ...`; echoes records only with `--show`

## Important Behavior

- **Cache sentinel:** `cache[n] = chain_length(n) + 1`; 0 = not computed. cache[1] seeded to 1.
- **Back-fill:** values > limit are traversed but not cached; they count toward chain length.
- **N range:** 1–12. Python warns N>7 (~40 MB+). N>8 is impractical (Python OOM or too slow).
- **Stdout:** records are echoed only with `--show`; `tests` in `make test` also run `../scripts/cli_contract.py collatz.py`.
- **Output file:** `collatz_1eN.txt` — one record per line: `<n> <chain_length>`.

## Testing

```bash
make test      # lint + unittest
make coverage  # pytest --cov, fails under 90%
```

| Class                 | Tests |
|-----------------------|-------|
| `TestCollatzNext`     | 3     |
| `TestCollatzLength`   | 6     |
| `TestGenerateRecords` | 4     |
| `TestGetExponent`     | 11    |
| `TestMain`            | 9     |
| `TestParseArgs`       | 6     |
| `TestRefuseLargeRun`  | 4     |
| `TestCliContractConstants` | 2 |

**Current coverage: 98% (187 statements, 4 uncovered).** Lines 90-91 (interactive warning for N>7) and 129 (if __name__ block) are unreachable during unit tests — acceptable exclusions.
