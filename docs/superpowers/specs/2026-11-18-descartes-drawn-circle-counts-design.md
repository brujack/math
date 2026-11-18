# descartes: disclose the drawing cut-offs and report drawn circle counts

- **Status:** Draft
- **Date:** 2026-11-18
- **Scope:** `descartes/descartes.py`, `descartes/descartes-rs/` (both halves, identical behaviour)

## Context

The operator ran the packing for K=1 through K=6 with `--svg` and found that K=3 through K=6 all wrote an SVG
of exactly the same size, which looked like a calculation bug.

It is not a calculation bug. `svg_packing` (`descartes/descartes.py:570`) and its Rust twin
(`descartes-rs/src/lib.rs:638`) draw `visible(root, limit)` with `limit = min(10^K, 1000 * |k_outer|)`. The
2026-11-17 SVG spec chose this on purpose: the outer circle is radius 500 in a 1000-unit square, so the cap
stops at radius 0.5 units, and the reader zooms the vector file instead of re-running at a larger K. With
the default root (`k_outer = -1`) the limit is `min(10^K, 1000)`, so every K >= 3 draws the same circles.

Measured 2026-11-18 on `claude` (Python, default root, `--no-draw --svg`): the K=3 and K=4 files are
byte-identical (`cmp` silent), both 315,079 bytes with 3,329 `<circle>` elements (the outer circle plus
3,328) and 26 `<text>` labels; K=2 has 169 `<circle>` elements. The `.txt` output and the `circles` line do
grow with K: `pack` returns 8 at K=1, 168 at K=2, 3,328 at K=3 and 67,166 at K=4. Population: these
figures are for the default root only. Rust matches the Python SVG by `tests/parity.rs` (default root
K=1/2/3), so the cap is the same there; the Rust byte count was not measured separately.

The defect is that the cap is undisclosed. `--help` states the braille cut-off
(`min(10^K, 2 x canvas width in braille dots)`) but not the SVG one; neither `README.md` nor `CLAUDE.md`
mentions it. A user who sees an unchanged file has no way to tell a cap from a bug.

Scaling the cap with K was considered and rejected by the operator: the 2026-11-17 spec measured the circle
count growing about 2.5x per doubling of the limit (500: 1,324; 1000: 3,328; 2000: 8,258), so an uncapped
SVG would be about 67,000 circles (roughly 6 MB) at K=4 and GB-scale at K=6, and the circles past the cap
are thinner than their own stroke. The 2026-11-17 spec also stated the K=3 file as "about 230 KB"; the
measured figure is 315,079 bytes, so that figure is corrected here.

## Design

### Output lines

The packing mode prints one line per drawing, giving what that drawing shows out of what was computed.

- With `--svg`, immediately after `Saved SVG to <path>`:
  `SVG shows <n> of <count> circles (curvature <= <limit>)`, where `limit = min(10^K, 1000 x |k_outer|)`.
- When the braille drawing is printed (not `--no-draw`, and `count > 0`), immediately before its first line:
  `braille shows <n> of <count> circles (curvature <= <limit>)`, where
  `limit = min(10^K, 4 x canvas width in cells)`, the cut-off `_draw_packing` already uses.

`count` is the existing `circles <count>` value. `n` is the number of circles from `visible(root, limit)`,
which excludes the bounding circle exactly as `count` does, so a drawing that shows every computed circle
prints `n == count`. `limit` is printed as an integer.

Stdout order in packing mode becomes: `root`, `circles`, `distinct`, `Saved to <file>`, then
`Saved SVG to <path>` and `SVG shows ...` (with `--svg`), then `braille shows ...` and the braille (when
drawn). `--show` lines keep their place before `root`. `--solve` output is unchanged: it has no packing
total to report against.

### One source for each cut-off

The SVG cut-off moves into one function (Python `svg_limit(root, k)`, Rust `svg_limit`) called by both
`svg_packing` and the code that prints the `SVG shows` line. The braille line is printed from
`_draw_packing` (Rust: the matching block in `run_packing`) using the `limit` and circle list it already
computes. The printed limit therefore cannot drift from the drawn one.

### Disclosure

- `--help` epilog (both languages) gains, after the braille sentence: `The SVG shows circles with curvature
at most min(10^K, 1000 x |outer curvature|), radius at least 0.5 of its 1000 units, so with the default
root every K from 3 up writes the same SVG.`
- `descartes/README.md`, `descartes/descartes-rs/README.md`, `descartes/CLAUDE.md` and
  `descartes/descartes-rs/CLAUDE.md` state the SVG cut-off formula, that the default root writes the same
  SVG (3,328 circles, 315,079 bytes) for every K >= 3, the two new lines and the new stdout order, and
  their "Real output" blocks show the new lines.
- The 2026-11-17 spec's "about 230 KB" is replaced with `315,079 bytes` and a dated correction note.

### Error handling

No new failure paths. The lines are printed only after the SVG write and the computation succeed, so every
existing error case keeps its current stdout (a failed SVG write still prints no result lines).

## Testing

TDD in both languages, one behaviour at a time:

- Default root K=3, `--no-draw --svg`: the line after `Saved SVG to` is
  `SVG shows 3328 of 3328 circles (curvature <= 1000)`.
- Default root K=4, piped (60 x 24 canvas), `--svg`: `SVG shows 3328 of 67166 circles (curvature <= 1000)`
  then `braille shows 524 of 67166 circles (curvature <= 240)` immediately before the braille.
- Default root K=1, piped, `--svg`: `SVG shows 8 of 8 circles (curvature <= 10)` and
  `braille shows 8 of 8 circles (curvature <= 10)`.
- Root `-11 21 24 28`, K=1, `--svg`: `SVG shows 0 of 0 circles (curvature <= 10)` and no braille line.
- `--no-draw`: no `braille shows` line; no `--svg`: no `SVG shows` line; `--solve --svg`: stdout unchanged.
- A terminal canvas (Rust `on_terminal`, Python patched `isatty`/terminal size) prints the braille limit
  `4 x width`.
- `svg_limit`: `min(10^K, 1000 x |k_outer|)` for the default root and for a root whose `1000 x |k_outer|`
  is below `10^K` at a small K (root `-11 21 24 28`, K=5: limit 11000).
- `tests/parity.rs` compares the `SVG shows` and `braille shows` lines between Python and Rust.
- Existing exact-stdout tests (Python `test_descartes.py`, Rust `src/main.rs` and `tests/cli.rs`,
  `tests/scripts/descartes.bats`) are updated to the new order.
- `--help` contains the new epilog sentence in both languages.

## Requirements

- **R1.** With `--svg` in packing mode, the line immediately after `Saved SVG to <path>` is `SVG shows <n> of <count> circles (curvature <= <limit>)`, with `limit = min(10^K, 1000 x |k_outer|)`, `n` the number of non-bounding circles in the SVG and `count` the `circles` value, in both Python and Rust.
- **R2.** When the braille drawing is printed in packing mode, the line immediately before its first braille line is `braille shows <n> of <count> circles (curvature <= <limit>)`, with `limit = min(10^K, 4 x canvas width in cells)` and `n` the number of non-bounding circles drawn, in both Python and Rust.
- **R3.** No `braille shows` line is printed with `--no-draw` or when `count` is 0; no `SVG shows` line is printed without `--svg`; `--solve` stdout is unchanged.
- **R4.** The default root prints `SVG shows 3328 of 3328 circles (curvature <= 1000)` at K=3; `SVG shows 3328 of 67166 circles (curvature <= 1000)` and, piped, `braille shows 524 of 67166 circles (curvature <= 240)` at K=4; `SVG shows 8 of 8 circles (curvature <= 10)` and, piped, `braille shows 8 of 8 circles (curvature <= 10)` at K=1; root `-11 21 24 28` at K=1 with `--svg` prints `SVG shows 0 of 0 circles (curvature <= 10)` and no braille line; tests in both languages assert each of these.
- **R5.** The SVG cut-off is computed by one function (Python `svg_limit(root, k)`, Rust `svg_limit`) that both `svg_packing` and the `SVG shows` line use; `svg_limit` returns 11000 for root `-11 21 24 28` at K=5.
- **R6.** The `--help` epilog in both languages contains the sentence `The SVG shows circles with curvature at most min(10^K, 1000 x |outer curvature|), radius at least 0.5 of its 1000 units, so with the default root every K from 3 up writes the same SVG.` (whitespace-normalised).
- **R7.** `descartes/README.md`, `descartes/descartes-rs/README.md`, `descartes/CLAUDE.md` and `descartes/descartes-rs/CLAUDE.md` each state the SVG cut-off `min(10^K, 1000 x |outer curvature|)`, that the default root writes the same SVG of 3,328 circles and 315,079 bytes for every K >= 3, and the stdout order `Saved to`, `Saved SVG to`, `SVG shows`, `braille shows`, braille.
- **R8.** `docs/superpowers/specs/2026-11-17-svg-output-and-prompt-reprompt-design.md` no longer says `about 230 KB`; it says `315,079 bytes` with a correction note dated 2026-11-18.
- **R9.** `descartes/descartes-rs/tests/parity.rs` compares the `SVG shows` and `braille shows` lines between Python and Rust.
- **V1.** Run both CLIs at the default root with `--svg` for K=1 to 6 (Rust also 7 and 8): every K >= 3 SVG is byte-identical to K=3, each `SVG shows` line reads `3328 of <count>` for K >= 3, and its `<count>` equals that run's `circles` value.
- **V2.** CI is green on the PR, including `mutation-pr` with 0 survivors on changed lines in both languages.
- **N1.** The SVG content does not change: same cut-off formula, same circles, same bytes for every input.
- **N2.** The `.txt` output, the `root`/`circles`/`distinct`/`Saved to` lines and the `--solve` output do not change.
- **N3.** The braille cut-off formula and canvas sizing do not change.
- **N4.** No new command-line flag.
