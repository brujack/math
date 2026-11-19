# descartes

Two tools on tangent circles, built on Descartes' circle theorem. Enumerate an integral Apollonian packing (every circle's curvature is an integer) up to curvature 10^K and draw it in braille, or give three mutually tangent circles and list every circle tangent to all three.

## Background

A circle's **curvature** is `k = 1/r`; a circle that encloses the others gets a negative curvature. **Descartes' circle theorem**: four mutually tangent circles satisfy

```text
(k1 + k2 + k3 + k4)^2 = 2 (k1^2 + k2^2 + k3^2 + k4^2)
```

so three mutually tangent circles have exactly two circles tangent to all three: `k4 = k1 + k2 + k3 ± 2√(k1k2 + k2k3 + k3k1)`. The complex form of the theorem gives their centres the same way, which is what `--solve` computes.

The two solutions add up to `2(k1 + k2 + k3)`, so replacing one circle of a quadruple by the other solution (a **reflection**, `k' = 2(ka + kb + kc) - kd`) gives a new tangent quadruple. Starting from a **root quadruple** and reflecting into every gap without end fills the outer circle with an **Apollonian packing**. If the root's curvatures are integers, every circle's is. The default root `-1 2 2 3` is a unit circle holding two circles of radius 1/2 and one of radius 1/3.

**K** is the cut-off for that infinite process: packing mode counts every circle with curvature at most 10^K, which for the default root means radius at least 10^-K of the outer circle's. Measured on the default root:

| K | circles | distinct curvatures |
|---|---|---|
| 1 | 8 | 3 |
| 2 | 168 | 33 |
| 3 | 3,328 | 324 |
| 4 | 67,166 | 3,299 |
| 5 | 1,359,170 | 33,273 |
| 6 | 27,463,394 | 333,273 |

Each step of K multiplies the circle count by about 20, which is 10^1.3057; 1.3057 is the fractal (Hausdorff) dimension of the Apollonian packing. Distinct curvatures grow only about tenfold per step, because many circles share a curvature. `circles` excludes the outer circle; `distinct` is the number of different curvature values, written one per line to `descartes_1e<K>.txt`. Python takes K 1-6 and Rust 1-8 (about 1.1e10 circles at K=8).

Python (`descartes.py`, standard library, no external dependencies) and Rust (`descartes-rs/`, see [`descartes-rs/README.md`](descartes-rs/README.md)); the Rust version takes K 1 to 8 where Python takes 1 to 6.

## Quick Start

```bash
cd descartes
bash install_deps.sh                       # pinned Python packages (one time)
make run                                   # interactive prompt for K (terminal only)
python3 descartes.py 3 --no-draw           # packing up to curvature 10^3
python3 descartes.py 3 --root -11 21 24 28 # another reduced root
python3 descartes.py --solve -1,0,0 2,0.5,0 3,0,0.6666666666666666 --no-draw
python3 descartes.py --smoke               # packing at SMOKE_SIZE = 2
python3 descartes.py 3 --no-draw --svg p.svg  # also write p.svg
make test
```

## Options

| Flag                       | Meaning                                                              |
| -------------------------- | -------------------------------------------------------------------- |
| `K`                        | exponent, curvature limit 10^K (1 to 6)                              |
| `--root A B C D`           | root quadruple with one negative value, each at most 10^8 in absolute value (default `-1 2 2 3`) |
| `--show`                   | also print each result line to stdout                                |
| `--yes`                    | confirm a large run (this program has none)                          |
| `--smoke`                  | quick check at `SMOKE_SIZE` (2)                                      |
| `--solve K,X,Y K,X,Y K,X,Y` | three mutually tangent circles (curvature, centre x, centre y); prints the circles tangent to all three |
| `--precision P`            | `--solve` only: round the displayed table to P decimals (0-17)       |
| `--no-draw`                | skip the braille drawing                                             |
| `--svg PATH`               | also write an SVG drawing to PATH (every mode)                       |

With no arguments at a terminal the program prompts for K. With no arguments and stdin not a terminal it prints usage and exits 2. The drawing shows circles up to curvature `min(10^K, 2 x canvas width in braille dots)`, so its circle set depends on terminal width; piped output uses a 60 x 24 canvas.

## Examples

```text
$ python3 descartes.py 3 --no-draw
Elapsed: 0.00s
root -1 2 2 3
circles 3328
distinct 324
Saved to descartes_1e3.txt
```

(`Elapsed` is written to stderr.) The file holds one distinct curvature per line.

```text
$ python3 descartes.py --solve -1,0,0 2,0.5,0 3,0,0.6666666666666666 --precision 4 --no-draw
kind      #  curvature  radius   x        y
given     1  -1.0000    -1.0000  0.0000   0.0000
given     2  2.0000     0.5000   0.5000   0.0000
given     3  3.0000     0.3333   0.0000   0.6667
solution  1  2.0000     0.5000   -0.5000  0.0000
solution  2  6.0000     0.1667   0.5000   0.6667
```

### SVG output

```text
$ python3 descartes.py 2 --no-draw --svg p.svg
root -1 2 2 3
circles 168
distinct 33
Saved to descartes_1e2.txt
Saved SVG to p.svg
SVG shows 168 of 168 circles (curvature <= 100)
```

`--svg PATH` works with every mode and is checked before any prompt. It exits 1 with `Error: cannot write SVG '<path>': directory '<dir>' does not exist` (missing parent, or a parent that is a file; an empty directory part means `.`), `Error: cannot write SVG '<path>': it is a directory`, or `Error: cannot write SVG '<path>': <reason>` when the open or write fails. The SVG opens before the `.txt` and before computing, so a refusal leaves no files. The drawing is 1000 x 1000 with a white background and black circles, showing circles with curvature at most `min(10^K, 1000 x |outer curvature|)` (SVG radius at least 0.5 of the 1000 units), so with the default root every K >= 3 writes the same SVG (3,328 circles plus the outer circle); circles with SVG radius of at least 20 carry their integer curvature, the outer circle is unlabelled (26 labels at K=3 on the default root). `--solve` draws the givens black and the solutions red dashed, fitted to the givens plus any enclosing (negative-curvature) solution. `--precision` does not change the SVG. A packing SVG carries the comment `<!-- circles with curvature <= <limit>; cut-off min(10^K, 1000 x |outer curvature|) -->` before the first `<circle>` (`--solve` has none). Packing prints two count lines after the braille: `braille draws <n> of <count> circles (curvature <= <limit>)` (when the braille drawing is printed) and `SVG shows <n> of <count> circles (curvature <= <limit>)` (with `--svg`); `n` excludes the bounding circle. Order of stdout for packing: `Saved to ...`, `Saved SVG to <path>`, the braille, `braille draws ...`, `SVG shows ...` (on a terminal `Elapsed` on stderr appears before the braille); for `--solve` the table, `Saved SVG to <path>`, then the braille.

## Parallel packing

The packing search splits once: a breadth-first pass stops at `SEED_TARGET = 4096` seeds, then each seed's subtree is walked on its own. Runs go parallel only when `n >= PARALLEL_MIN_N = 100_000` (K 5 or more), seeds remain and more than one worker is available; the output is byte-identical to the serial run. When more than one worker ran, `Workers: <N>` is written to stderr immediately before `Elapsed:`. The worker count is the CPU count the process may use (`os.process_cpu_count` on Python 3.13+, else `os.cpu_count`); `PYTHON_CPU_COUNT=<N>` overrides it on 3.13+, and `PYTHON_CPU_COUNT=1` forces a serial run. If the process pool cannot start, the run falls back to serial and says so on stderr. The Rust twin bounds its threads with `RAYON_NUM_THREADS`.

## Known limits

`--solve` prints full-precision values that paste back into `--solve`, but pasting them back stops passing the `1e-9` tangency tolerance at curvatures near 2.6e7, and nearly collinear inputs are ill-conditioned: a triple that passes the input check can yield solutions that do not pass when pasted back.

## Exit codes

| Code | Meaning                                                                                     |
| ---- | ------------------------------------------------------------------------------------------- |
| 0    | done                                                                                        |
| 1    | well-formed input with no answer (not a Descartes root, circles not tangent, end of input, an output file or `--svg` path that cannot be written)  |
| 2    | input that cannot describe a problem (bad value, K or `--precision` out of range, a `--root` value above 10^8 in absolute value, usage) |
