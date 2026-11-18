# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

Rust half of the `descartes` sub-project: tangent circles by Descartes' theorem. It enumerates an integral Apollonian packing up to curvature 10^K (K 1-8) and draws it in braille, or `--solve` lists the circles tangent to three given mutually tangent circles. It matches the Python program (`../descartes.py`) in exit codes, file name, caps and table layout; the differences are listed under Important Behavior. Plain `i64`/`f64`, no `rug`, `rayon` or arbitrary precision (spec N2, N4).

Injectable I/O pattern (ADR-0018): `run<R,W,E>(stdin, stdout, stderr, ...)` in `src/main.rs`; `fn main()` is a thin clap wrapper excluded from tarpaulin.

## Running

```bash
make descartes # cargo build --release (binary in target/release/descartes)
make install   # build, then copy to ${XDG_BIN_HOME:-~/.local/bin}/descartes
make lint      # cargo fmt --check + clippy -D warnings + cargo machete
make test      # lint + cargo nextest run
```

```bash
descartes 3 --no-draw                      # packing up to curvature 10^3
descartes 3 --root -11 21 24 28 --no-draw  # another reduced root
descartes --solve -1,0,0 2,0.5,0 3,0,0.6666666666666666 --no-draw
descartes --smoke                          # packing at SMOKE_SIZE = 2
descartes 3 --no-draw --svg p.svg          # also write p.svg
```

Flags: positional `K` (1-8), `--root A B C D`, `--show`, `--yes`, `--smoke`, `--solve K,X,Y K,X,Y K,X,Y`, `--precision P` (0-17, `--solve` only), `--no-draw`, `--svg PATH`.

Real output for `descartes 3 --no-draw` from a temporary directory (`Elapsed: 0.00s` goes to stderr):

```text
root -1 2 2 3
circles 3328
distinct 324
Saved to descartes_1e3.txt
```

Real output for `--solve -1,0,0 2,0.5,0 3,0,0.6666666666666666 --no-draw`:

```text
kind      #  curvature  radius               x     y
given     1  -1         -1                   0     0
given     2  2          0.5                  0.5   0
given     3  3          0.3333333333333333   0     0.6666666666666666
solution  1  2          0.5                  -0.5  0
solution  2  6          0.16666666666666666  0.5   0.6666666666666666
```

Real output for `descartes 2 --no-draw --svg p.svg` (stdout):

```text
root -1 2 2 3
circles 168
distinct 33
Saved to descartes_1e2.txt
Saved SVG to p.svg
SVG shows 168 of 168 circles (curvature <= 100)
```

## Code Layout

- `DescartesError { BadInput, NoSolution }` — exit 2 and exit 1, as in Python
- `descartes_fourth(k1, k2, k3)` — both fourth curvatures; radicand below `-1e-12 × (|k1k2|+|k2k3|+|k3k1|)` is `NoSolution`, otherwise clamped at 0 (R23, identical to Python)
- `validate_root`, `pack(root, n)`, `distinct(bitmap)` — root check and reduction, the reflection walk with an explicit stack and bitmap, the distinct curvatures
- `check_tangent`, `solve`, `root_centres`, `visible` — geometry (`1e-9` relative tangency tolerance per pair)
- `svg_limit(root, k)` — the SVG cut-off (saturating, total); `svg_packing -> (String, usize)`, `usize` the circles drawn excluding the outer circle
- `render` — braille drawing, 2x4 dots per cell
- `run_packing`, `run_solve`, `run` in `src/main.rs` — the CLI; `tests/cli.rs` runs the binary, `tests/parity.rs` compares it with `../descartes.py`

## Important Behavior

- **Exit codes** as Python: 0 done, 1 well-formed input with no answer (not a Descartes root, circles not tangent, end of input at the prompt, an output file that cannot be opened), 2 input that cannot describe a problem (bad value, a command-line K or `--precision` out of range, a `--root` value above 10^8 in absolute value, zero curvature in `--solve`, a mode-flag clash, a bare non-TTY run); at the prompt a non-integer answer prints `Invalid input: 'abc' is not an integer K.` and an out-of-range one prints `K must be between 1 and 8, got K.`, each to stderr, and the prompt asks again, while end of input still exits 1.
- **Caps (R20, R27, R28):** `N_MAX = 10^8` (K 1-8; Python's is 10^6, K 1-6); `ROOT_MAX = 10^8` bounds every `--root` curvature; the canvas is the terminal size clamped to 1 x 1 .. 1000 x 500 cells (piped: 60 x 24), so the braille curvature limit is `min(10^K, 2 x canvas width in braille dots)`; `--precision` is 0-17.
- **Differences from Python's output:** numbers print with Rust `Display`, so `-1` where Python's `repr` prints `-1.0` (the `--solve` table above vs `descartes/CLAUDE.md`); usage errors use clap's format (`error: K is required when stdin is not a terminal`, then `Usage: descartes [OPTIONS] [K]`) where Python prints argparse's `usage: descartes.py ...` block; the range errors read alike (`K must be between 1 and 8, got 9.`). The packing output (`root`, `circles`, `distinct`, file) is identical.
- **Known `--solve` paste-back limits:** full-precision output stops passing the `1e-9` tolerance near curvature 2.6e7, and nearly collinear inputs are ill-conditioned: a triple that passes the input check can yield solutions that do not pass when pasted back. `--help` states both.
- **`--svg PATH` (every mode):** Checked before any prompt. It exits 1 with `Error: cannot write SVG '<path>': directory '<dir>' does not exist` (missing parent, or a parent that is a file; an empty directory part means `.`), `Error: cannot write SVG '<path>': it is a directory`, or `Error: cannot write SVG '<path>': <reason>` when the open or write fails. The SVG opens before the `.txt` and before computing, so a refusal or a failed open leaves no files; a failed write leaves the `.txt`, which is already written. The directory part is Python's `os.path.dirname` (`nod/` has directory `nod`). In packing the SVG is written before any result line, so a failed write prints none of them (only the K prompt, when one was shown, precedes the error); `--solve` has already printed its table. The drawing is 1000 x 1000 with a white background and black circles, showing circles with curvature at most `min(10^K, 1000 x |outer curvature|)` (SVG radius at least 0.5 of the 1000 units), so with the default root every K >= 3 writes the same SVG (3,328 circles plus the outer circle); circles with SVG radius of at least 20 carry their integer curvature, the outer circle is unlabelled (26 labels at K=3 on the default root). `--solve` draws the givens black and the solutions red dashed, fitted to the givens plus any enclosing (negative-curvature) solution. `--precision` does not change the SVG. A packing SVG carries the comment `<!-- circles with curvature <= <limit>; cut-off min(10^K, 1000 x |outer curvature|) -->` before the first `<circle>` (`--solve` has none). Packing prints two count lines after the braille: `braille draws <n> of <count> circles (curvature <= <limit>)` (when the braille drawing is printed) and `SVG shows <n> of <count> circles (curvature <= <limit>)` (with `--svg`); `n` excludes the bounding circle. Order of stdout for packing: `Saved to ...`, `Saved SVG to <path>`, the braille, `braille draws ...`, `SVG shows ...` (on a terminal `Elapsed` on stderr appears before the braille); for `--solve` the table, `Saved SVG to <path>`, then the braille.
- **SVG parity:** `tests/parity.rs` compares the Python and Rust SVG by structure, numbers as integer thousandths with |delta| <= 1 (default root K=1/2/3, tie root K=5, `--solve`), and the two count lines exactly (default root K=3/4, drawn, with `--svg`).
- **Repeated flags keep the last value:** `--root`, `--solve` and `--precision` given twice use the second, as argparse does (clap `args_override_self`).
- **CI trigger:** `descartes-rs.yml` also runs on `descartes/*.py`, so a Python-only edit runs the parity test in CI and in `scripts/pre-push`.
- **`.cargo/mutants.toml`** sets `additional_cargo_test_args = ["--lib", "--bins", "--test", "cli"]`, excluding `tests/parity.rs`: it runs `../descartes.py`, which is absent from cargo-mutants' crate-only copy, so the parity test would fail the baseline. It also excludes one equivalent mutant: `<` → `<=` in `svg_solve`'s `k < 0` frame filter, since `solve` never returns a curvature-0 solution. Its pattern embeds `src/lib.rs:<line>:<col>`, so update it when that line moves; `tests/test_mutants_exclusions.py` checks the drift.

## Coverage

≥90% on Linux CI.
