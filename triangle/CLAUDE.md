# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

A Python CLI that solves a triangle from any three of its sides and angles, reports area and perimeter, and draws it in braille. There is no Rust crate.

Current structure:

- `triangle.py` — solver, braille renderer and CLI (standard library only)
- `test_triangle.py` — unit tests
- `install_deps.sh`, `Makefile`, `pyrightconfig.json`, `cosmic-ray.toml` — rendered from `scripts/crate_templates/python/`; edit the template, never this copy

## Running the Script

```bash
make run       # python3 triangle.py
make lint      # ruff check . and ruff format --check .
make test      # lint, pytest test_triangle.py -v, then scripts/cli_contract.py
make coverage  # pytest --cov, fails under 90%
```

```bash
python3 triangle.py                        # prompts for a b c A B C at a terminal (empty = unknown); bare non-TTY run exits 2
python3 triangle.py -a 3 -b 4 -c 5         # solve from flags
python3 triangle.py -a 6 -b 8 -A 30 --no-draw   # SSA, two solutions
python3 triangle.py --radians --precision 6 ...
python3 triangle.py --smoke                # solve and draw 3-4-5
```

Flags: `-a -b -c` sides, `-A -B -C` angles (degrees; radians with `--radians`), `--precision N` (default 4), `--no-draw`, `--smoke`.

Real output for `-a 3 -b 4 -c 5` (the table; the braille drawing follows it):

```text
a                   3.0000  given
b                   4.0000  given
c                   5.0000  given
A                  36.8699  derived
B                  53.1301  derived
C                  90.0000  derived
area                6.0000
perimeter          12.0000
```

Real output for `-a 6 -b 8 -A 30 --no-draw`:

```text
Solution 1
a                   6.0000  given
b                   8.0000  given
c                  11.4003  derived
A                  30.0000  given
B                  41.8103  derived
C                 108.1897  derived
area               22.8007
perimeter          25.4003
Solution 2
a                   6.0000  given
b                   8.0000  given
c                   2.4561  derived
A                  30.0000  given
B                 138.1897  derived
C                  11.8103  derived
area                4.9121
perimeter          16.4561
```

## Code Layout

- `solve(values, radians=False)` — returns `Solved(solutions, extras)`. Covers SSS, SAS, ASA, AAS and SSA; SSA yields 0, 1 or 2 solutions. Raises `TriangleInputError` (exit 2) for unusable input and `NoTriangle` (exit 1) when no triangle fits.
- `Triangle`, `Extra`, `Solved` — frozen dataclasses. Values beyond the determining set come back as `Extra(name, given, solved)`.
- `render(t, width, height)` — braille drawing: 2x4 dots per cell, drawn so a length is the same number of dots in x and y, vertices labelled A, B, C. Piped output uses a fixed 60 x 20 canvas; a terminal uses its size.
- `main(argv)` — parses args, prompts when needed, prints the table, extras and drawing, returns the exit code.

## Important Behavior

- **Extras are reported, not judged:** a value given beyond the determining set is never replaced or rejected; it prints `extra <name> given <x> solved <y> diff <d>`.
- **Exit codes:** 0 solved, 1 no triangle fits, 2 unusable input or bare non-TTY run.
- **Closed-form CLI contract:** `CONTRACT_ARGS = ["-a", "3", "-b", "4", "-c", "5"]` and `CONTRACT_EXPECT = "6.0000"` (the area); `make test` runs `python3 ../scripts/cli_contract.py triangle.py` after pytest. A closed-form program declares these instead of `SMOKE_SIZE`.
- **Numerics:** SSS uses Kahan's stable angle and Heron formulas. SAS, SSA and AAS never re-derive an angle from computed sides, which can round onto a + b for a near-flat triangle: their angles come from `atan2` forms that do not cancel, and their area is half the product of two sides and the included angle. In SSA, when the larger derived angle is at least pi/4, `_close_angles` takes it as pi minus the other two, so an ill-conditioned triangle still sums to pi. Only the determining set sets the scale, so an extreme extra cannot push the real sides out of range. `solve` first scales the sides by a power of two so the longest lies in [0.5, 1); the scale is exact, so ordinary results are bit-identical and only the final sides, area and perimeter can leave the double range. A result a double cannot hold, or holds only as a subnormal, exits 2 (`values out of floating-point range ...`), and so do sides too far apart to share one scale (`the sides differ by more than a double can carry ...`). An angle below the smallest normal double in radians is refused (`angle X is too small for a double`).

## Testing

**TDD is required.** Write the failing test first, then the minimum implementation. Tests go in the same commit as the code.

Every test must cover more than the happy path: boundary values, error paths and state transitions.

```bash
make test      # lint + pytest + CLI contract
make coverage  # pytest --cov, fails under 90%
```
