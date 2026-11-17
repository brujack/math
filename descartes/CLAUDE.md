# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

A Python CLI (and a Rust crate, `descartes-rs/`) with two modes: enumerate an integral Apollonian packing (circles tangent to a root quadruple of curvatures, found by Descartes reflection) up to curvature 10^K and draw it in braille, or `--solve` for the circles tangent to three given mutually tangent circles. The Rust crate's detail is in `descartes-rs/CLAUDE.md`; it takes K 1-8 and `N_MAX` 10^8 where Python takes K 1-6 and 10^6.

Current structure:

- `descartes-rs/` — the Rust crate (own `CLAUDE.md` and `README.md`)
- `descartes.py` — packing core, geometry, braille renderer and CLI (standard library only)
- `test_descartes.py` — unit tests
- `install_deps.sh`, `Makefile`, `pyrightconfig.json`, `cosmic-ray.toml` — rendered from `scripts/crate_templates/python/`; edit the template, never this copy
- `mutants-equivalent.toml` — the 28 true-equivalent mutants, each with the mechanism that guarantees it (matched by `tests/test_mutants_equivalent.py`)

## Running the Script

```bash
make run       # python3 descartes.py
make lint      # ruff check . and ruff format --check .
make test      # lint, pytest test_descartes.py -v, then scripts/cli_contract.py
make coverage  # pytest --cov, fails under 90%
```

```bash
python3 descartes.py                       # prompts for K at a terminal; bare non-TTY run exits 2
python3 descartes.py 3 --no-draw           # packing up to curvature 10^3
python3 descartes.py 3 --root -11 21 24 28 # another reduced root
python3 descartes.py --solve -1,0,0 2,0.5,0 3,0,0.6666666666666666 --no-draw
python3 descartes.py --smoke               # packing at SMOKE_SIZE = 2
```

Flags: positional `K` (1-6, curvature limit 10^K), `--root A B C D`, `--show`, `--yes`, `--smoke`, `--solve K,X,Y K,X,Y K,X,Y`, `--precision P` (0-17, `--solve` only), `--no-draw`.

Real output for `python3 descartes.py 3 --no-draw` (stdout; the elapsed line goes to stderr):

```text
root -1 2 2 3
circles 3328
distinct 324
Saved to descartes_1e3.txt
```

Real output for `--solve -1,0,0 2,0.5,0 3,0,0.6666666666666666 --no-draw`:

```text
kind      #  curvature  radius               x     y
given     1  -1.0       -1.0                 0.0   0.0
given     2  2.0        0.5                  0.5   0.0
given     3  3.0        0.3333333333333333   0.0   0.6666666666666666
solution  1  2.0        0.5                  -0.5  0.0
solution  2  6.0        0.16666666666666666  0.5   0.6666666666666666
```

## Code Layout

- `validate_root(root)` — checks a Descartes quadruple with exactly one negative value and reduces it to its root; `_check_reduced_root` rejects an unreduced or unsorted one at the `pack` boundary.
- `pack(root, n)` — walks the reflections with an explicit stack and a bitmap, returns `(count, bitmap)`; `distinct(bitmap)` lists the curvatures. `n` above `N_MAX = 10**6` raises `BadInput` (R20), so the core cannot be asked for an unbounded run whatever the caller.
- `descartes_fourth`, `root_centres`, `solve`, `check_tangent`, `visible` — geometry. The third root circle is placed in exact rationals so a collinear root keeps `y = 0`; `solve` checks tangency per pair with signed radii `r = 1/k` (`| |z_i - z_j| - |r_i + r_j| | <= 1e-9 x (|r_i| + |r_j|)`, pairs 1-2, 1-3, 2-3) and rejects NaN, infinite or zero-radius input as `BadInput`.
- `render(circles, width, height)` — braille drawing, 2x4 dots per cell, midpoint-circle rasterisation, one scale for x and y. Piped output uses a fixed 60 x 24 canvas; a terminal uses its size, one row short of the height.
- `main(argv)` — parses args, prompts when needed, runs packing or solve, returns through `sys.exit`.

## Important Behavior

- **Exit codes:** 0 done, 1 well-formed input with no answer (a root that fails the Descartes relation or lacks exactly one negative value, circles that are not mutually tangent, end of input at the prompt, an output file that cannot be opened), 2 input that cannot describe a problem (unparsable value, wrong count, non-integer root value, a root curvature above 10^8 in absolute value, a command-line K out of range, zero curvature in `--solve`, a mode-flag clash, `--precision` outside 0-17, a bare non-TTY run). Errors print `Error: <message>` to stderr and name the operation and the input. At the interactive prompt a non-integer answer prints `Invalid input: 'abc' is not an integer K.` and an out-of-range one prints `K must be between 1 and 6, got K.`, each to stderr, and the prompt asks again; only end of input exits (1).
- **Caps (R20, R27, R28):** `N_MAX = 10**6`; `ROOT_MAX = 10**8` bounds every `--root` curvature, which bounds the reduction loop (about 10^4 steps; an uncapped valid root ran for hours); the canvas is the terminal size clamped to 1 x 1 .. 1000 x 500 cells (`CANVAS_MAX_WIDTH`), which caps the drawing's curvature limit at `4 x width`, at most 4000 (20,360 circles for the default root); `--precision` is 0-17. Each bound keeps a hostile terminal or flag from exhausting memory.
- **Mode flags:** `--solve` with K, `--root`, `--smoke`, `--show` or `--yes`, and `--precision` without `--solve`, exit 2.
- **Elapsed:** `Elapsed: <seconds>s` goes to stderr only. The output file `descartes_1e<K>.txt` (with the root in the name unless it is the default) is opened before `pack` runs, so a path or permission error exits 1 before the computation.
- **CLI contract:** `SMOKE_SIZE = 2`, `LARGE_RUN_THRESHOLD = None`; `make test` runs `python3 ../scripts/cli_contract.py descartes.py` after pytest.
- **Known `--solve` paste-back limits:** `--solve` prints full-precision values, but pasting them back stops passing the `1e-9` tolerance at curvatures near 2.6e7 (measured ratio 1.88 of the tolerance), and nearly collinear inputs are ill-conditioned: a triple that passes the input check can yield solutions that do not pass when pasted back (the collinear `(-2,3,6)` triple with y perturbed by 1e-8 passes at 0.22 of the tolerance; its curvature-7 solutions fail at 7x). `--help` states both.
- **Mutation equivalents:** `mutants-equivalent.toml` names each equivalent by operator, function, source line, column and the line above; when an edit shifts or rewrites one of those lines the entry goes stale and `tests/test_mutants_equivalent.py` fails, so re-confirm it in the same PR.

## Testing

**TDD is required.** Write the failing test first, then the minimum implementation. Tests go in the same commit as the code.

Every test must cover more than the happy path: boundary values, error paths and state transitions. Every test of the `N_MAX` ceiling lowers `N_MAX` first, so a broken check fails in seconds rather than running a full packing.

```bash
make test      # lint + pytest + CLI contract
make coverage  # pytest --cov, fails under 90%
```
