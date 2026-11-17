# descartes

Two tools on tangent circles. Enumerate an integral Apollonian packing (every circle's curvature is an integer) up to curvature 10^K and draw it in braille, or give three mutually tangent circles and list every circle tangent to all three.

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

With no arguments at a terminal the program prompts for K. With no arguments and stdin not a terminal it prints usage and exits 2. The drawing shows circles up to curvature `min(10^K, 4 x canvas width)`, so its circle set depends on terminal width; piped output uses a 60 x 24 canvas.

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
```

`--svg PATH` works with every mode and is checked before any prompt. It exits 1 with `Error: cannot write SVG '<path>': directory '<dir>' does not exist` (missing parent, or a parent that is a file; an empty directory part means `.`), `Error: cannot write SVG '<path>': it is a directory`, or `Error: cannot write SVG '<path>': <reason>` when the open or write fails. The SVG opens before the `.txt` and before computing, so a refusal leaves no files. The drawing is 1000 x 1000 with a white background and black circles; circles with SVG radius of at least 20 carry their integer curvature, the outer circle is unlabelled (26 labels at K=3 on the default root). `--solve` draws the givens black and the solutions red dashed, fitted to the givens plus any enclosing (negative-curvature) solution. `--precision` does not change the SVG. Order of stdout: `Saved to ...`, then `Saved SVG to <path>`, then the braille; for `--solve` the table, `Saved SVG to <path>`, then the braille.

## Known limits

`--solve` prints full-precision values that paste back into `--solve`, but pasting them back stops passing the `1e-9` tangency tolerance at curvatures near 2.6e7, and nearly collinear inputs are ill-conditioned: a triple that passes the input check can yield solutions that do not pass when pasted back.

## Exit codes

| Code | Meaning                                                                                     |
| ---- | ------------------------------------------------------------------------------------------- |
| 0    | done                                                                                        |
| 1    | well-formed input with no answer (not a Descartes root, circles not tangent, end of input, an output file or `--svg` path that cannot be written)  |
| 2    | input that cannot describe a problem (bad value, K or `--precision` out of range, a `--root` value above 10^8 in absolute value, usage) |
