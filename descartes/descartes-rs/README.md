# descartes-rs

Rust implementation of `descartes`: tangent circles by Descartes' theorem. Enumerate an integral Apollonian packing (every circle's curvature is an integer) up to curvature 10^K and draw it in braille, or give three mutually tangent circles and list every circle tangent to all three. The Python version is `../descartes.py`; see [`../README.md`](../README.md).

## Quick Start

```bash
cd descartes/descartes-rs
bash install_deps.sh                       # one time
make descartes                             # cargo build --release
descartes 3 --no-draw                      # after make install; else target/release/descartes
descartes 3 --root -11 21 24 28 --no-draw  # another reduced root
descartes --solve -1,0,0 2,0.5,0 3,0,0.6666666666666666 --no-draw
descartes --smoke                          # packing at SMOKE_SIZE = 2
descartes 3 --no-draw --svg p.svg          # also write p.svg
make test
```

`make install` copies the binary to `${XDG_BIN_HOME:-~/.local/bin}/descartes`.

## Options

| Flag                        | Meaning                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------ |
| `K`                         | exponent, curvature limit 10^K (1 to 8)                                                          |
| `--root A B C D`            | root quadruple with one negative value, each at most 10^8 in absolute value (default `-1 2 2 3`) |
| `--show`                    | also print each result line to stdout                                                            |
| `--yes`                     | confirm a large run (this program has none)                                                      |
| `--smoke`                   | quick check at K = 2                                                                             |
| `--solve K,X,Y K,X,Y K,X,Y` | three mutually tangent circles (curvature, centre x, centre y); prints the circles tangent to all three |
| `--precision P`             | `--solve` only: round the displayed table to P decimals (0-17)                                   |
| `--no-draw`                 | skip the braille drawing                                                                         |
| `--svg PATH`                | also write an SVG drawing to PATH (every mode)                                                   |

With no arguments at a terminal the program prompts for K; with stdin not a terminal it prints usage and exits 2. The drawing shows circles up to curvature `min(10^K, 2 x canvas width in braille dots)`; piped output uses a 60 x 24 canvas and a terminal's size is clamped to 1000 x 500.

## Examples

Real runs from an empty directory (`Elapsed` goes to stderr):

```text
$ descartes 3 --no-draw
Elapsed: 0.00s
root -1 2 2 3
circles 3328
distinct 324
Saved to descartes_1e3.txt
```

```text
$ descartes --solve -1,0,0 2,0.5,0 3,0,0.6666666666666666 --precision 4 --no-draw
kind      #  curvature  radius   x        y
given     1  -1.0000    -1.0000  0.0000   0.0000
given     2  2.0000     0.5000   0.5000   0.0000
given     3  3.0000     0.3333   0.0000   0.6667
solution  1  2.0000     0.5000   -0.5000  0.0000
solution  2  6.0000     0.1667   0.5000   0.6667
```

Without `--precision` numbers print in Rust `Display` form (`-1`, `0.5`); Python prints `repr` (`-1.0`, `0.5`). The packing output is identical in both.

### SVG output

```text
$ descartes 2 --no-draw --svg p.svg
root -1 2 2 3
circles 168
distinct 33
Saved to descartes_1e2.txt
Saved SVG to p.svg
SVG shows 168 of 168 circles (curvature <= 100)
```

`--svg PATH` works with every mode and is checked before any prompt. It exits 1 with `Error: cannot write SVG '<path>': directory '<dir>' does not exist` (missing parent, or a parent that is a file; an empty directory part means `.`), `Error: cannot write SVG '<path>': it is a directory`, or `Error: cannot write SVG '<path>': <reason>` when the open or write fails. The SVG opens before the `.txt` and before computing, so a refusal leaves no files. The drawing is 1000 x 1000 with a white background and black circles, showing circles with curvature at most `min(10^K, 1000 x |outer curvature|)` (SVG radius at least 0.5 of the 1000 units), so with the default root every K >= 3 writes the same SVG (3,328 circles plus the outer circle); circles with SVG radius of at least 20 carry their integer curvature, the outer circle is unlabelled (26 labels at K=3 on the default root). `--solve` draws the givens black and the solutions red dashed, fitted to the givens plus any enclosing (negative-curvature) solution. `--precision` does not change the SVG. A packing SVG carries the comment `<!-- circles with curvature <= <limit>; cut-off min(10^K, 1000 x |outer curvature|) -->` before the first `<circle>` (`--solve` has none). Packing prints two count lines after the braille: `braille draws <n> of <count> circles (curvature <= <limit>)` (when the braille drawing is printed) and `SVG shows <n> of <count> circles (curvature <= <limit>)` (with `--svg`); `n` excludes the bounding circle. Order of stdout for packing: `Saved to ...`, `Saved SVG to <path>`, the braille, `braille draws ...`, `SVG shows ...` (on a terminal `Elapsed` on stderr appears before the braille); for `--solve` the table, `Saved SVG to <path>`, then the braille.

The SVG matches the Python program's.

## Parallel packing

The packing search splits once: a breadth-first pass stops at `SEED_TARGET = 4096` seeds, then the seeds' subtrees are walked across rayon's thread pool. Runs go parallel only when `n >= PARALLEL_MIN_N = 100_000` (K 5 or more), seeds remain and more than one worker is available; the output is byte-identical to the serial run. Below the threshold, or when the frontier runs out of seeds, the walk never builds a pool; at K 5 or more the program builds its own rayon pool (not rayon's lazily built global one, which panics when the OS refuses a thread), and with one worker the walk runs serially. If the pool cannot be built (for example `ulimit -u` or a container pids limit is too low) the run falls back to serial, exits 0 with the same output, and prints two lines on stderr before `Elapsed:`: `Parallel mode unavailable (<error>); falling back to serial.` then `Raise the process or thread limit (ulimit -u, a container pids limit) to re-enable parallel mode.` When more than one worker ran, `Workers: <N>` is written to stderr immediately before `Elapsed:`. Set `RAYON_NUM_THREADS=<N>` to bound the worker count (`1` forces a serial run); the Python program uses `PYTHON_CPU_COUNT` for the same purpose.

## Known limits

`--solve` prints full-precision values that paste back into `--solve`, but pasting them back stops passing the `1e-9` tangency tolerance near curvature 2.6e7, and nearly collinear inputs are ill-conditioned: a triple that passes the input check can yield solutions that do not pass when pasted back.

## Exit codes

| Code | Meaning                                                                                                              |
| ---- | -------------------------------------------------------------------------------------------------------------------- |
| 0    | done                                                                                                                 |
| 1    | well-formed input with no answer (not a Descartes root, circles not tangent, end of input, an output file that cannot be opened) |
| 2    | input that cannot describe a problem (bad value, K or `--precision` out of range, a `--root` value above 10^8 in absolute value, usage) |

## Limits

`N_MAX` and `ROOT_MAX` are 10^8 (Python: `N_MAX` 10^6, K 1-6). `--precision` is 0-17.

## Mutation testing

`.cargo/mutants.toml` restricts cargo-mutants to `--lib --bins --test cli`: `tests/parity.rs` runs `../descartes.py`, which cargo-mutants' crate-only copy does not contain.
