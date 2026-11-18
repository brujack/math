# descartes: disclose the drawing cut-offs and report drawn circle counts

- **Status:** Draft (revised after Step 8 round 1)
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

Measured 2026-11-18 on `claude` (Python, default root, `--no-draw --svg`): the K=3, K=4 and K=5 files are
byte-identical (`cmp` silent), each 315,079 bytes with 3,329 `<circle>` elements (the outer circle plus
3,328) and 26 `<text>` labels; K=2 has 169 `<circle>` elements. The `.txt` output and the `circles` line do
grow with K: `pack` returns 8 at K=1, 168 at K=2, 3,328 at K=3, 67,166 at K=4 and 1,359,170 at K=5.
Population: these figures are for the default root and the Python program only. Rust matches the Python SVG
by `tests/parity.rs` (default root K=1/2/3), so the cap is the same there; Rust at K >= 4 is checked by V1.

The defect is that the cap is undisclosed. `--help` states the braille cut-off
(`min(10^K, 2 x canvas width in braille dots)`) but not the SVG one; neither `README.md` nor `CLAUDE.md`
mentions it, and the SVG file itself records nothing. A user who sees an unchanged file has no way to tell a
cap from a bug.

Scaling the cap with K was considered and rejected by the operator: the 2026-11-17 spec measured the circle
count growing about 2.5x per doubling of the limit (500: 1,324; 1000: 3,328; 2000: 8,258), so an uncapped
SVG would be about 67,000 circles (roughly 6 MB) at K=4 and GB-scale at K=6, and the circles past the cap
are thinner than their own stroke. The 2026-11-17 spec also stated the K=3 file as "about 230 KB"; the
measured figure is 315,079 bytes, so that figure is corrected there.

## Design

### Count lines

The packing mode ends its stdout with one line per drawing, giving what that drawing holds out of what was
computed:

- With `--svg`: `SVG shows <n> of <count> circles (curvature <= <limit>)`, where
  `limit = svg_limit(root, K) = min(10^K, 1000 x |k_outer|)`.
- When the braille drawing is printed (not `--no-draw`, and `count > 0`):
  `braille draws <n> of <count> circles (curvature <= <limit>)`, where
  `limit = min(10^K, 2 x canvas width in braille dots)`, the cut-off `_draw_packing` already uses. The verb is
  "draws", not "shows": on a small canvas many of these circles round to a single dot.

`count` is the existing `circles <count>` value. `n` is the number of circles from `visible(root, limit)`,
which excludes the bounding circle exactly as `count` does, so a drawing that holds every computed circle
prints `n == count`. `limit` is an integer in both languages (Python's `1000 * abs(k0)` is a float because
`root_centres` returns `-1.0`, so `svg_limit` returns `int(...)`; Rust already casts `as i64`).

The count lines come after the drawing, as the last stdout lines, so they stay on screen when the shell
prompt returns. Stdout order in packing mode: (`--show` lines), `root`, `circles`, `distinct`,
`Saved to <file>`, `Saved SVG to <path>` (with `--svg`), the braille drawing (when drawn), `SVG shows ...`
(with `--svg`), `braille draws ...` (when drawn). On a terminal the stderr line `Elapsed: <s>s` appears
between `Saved SVG to` (or `Saved to`) and the drawing, as it does today. `--solve` output is unchanged: it
has no packing total to report against.

### Terminal canvas height

At a terminal the canvas height today is `max(lines - 1, 1)`, one row spared for the prompt. It becomes
`max(lines - 1 - m, 1)`, where `m` is the number of count lines printed after the drawing (1 without
`--svg`, 2 with it). The piped canvas stays 60 x 24, the width and the braille cut-off do not change, and
`--solve`'s drawing keeps `max(lines - 1, 1)` because it prints no count line.

### One source for each value

`svg_limit(root, k)` (Rust `svg_limit`) is the only place the SVG cut-off is computed. `svg_packing`
returns the SVG text together with `n`, so the walk runs once and the printed `n` is the drawn one (Python
`svg_packing(root, k) -> tuple[str, int]`, Rust the matching tuple). The braille line is printed from
`_draw_packing` (Rust: the matching block in `run_packing`) using the `limit` and circle list it already
computes.

### SVG comment

The packing SVG gains one line after the fixed header, before the first `<circle>`:
`<!-- circles with curvature <= <limit>; cut-off min(10^K, 1000 x |outer curvature|) -->`, with `<limit>`
from `svg_limit`. It carries no K and no count, so every K >= 3 file on the default root stays
byte-identical to the others; it records the cap in the file where the symptom was seen. The `--solve` SVG
gets no comment. `tests/parity.rs` already compares every SVG token, so the comment is covered there.

### Disclosure

- `--help` epilog (both languages) gains, after the braille sentence: `The SVG shows circles with curvature
  at most min(10^K, 1000 x |outer curvature|), radius at least 0.5 of its 1000 units, so with the default
  root every K from 3 up writes the same SVG.`
- `descartes/README.md`, `descartes/descartes-rs/README.md`, `descartes/CLAUDE.md` and
  `descartes/descartes-rs/CLAUDE.md` state the SVG cut-off formula, that the default root writes the same
  SVG (3,328 circles) for every K >= 3, the SVG comment, the two count lines, the stdout order with the
  `Elapsed` placement, and the terminal canvas height rule; the braille cut-off is written
  `min(10^K, 2 x canvas width in braille dots)` everywhere (the READMEs' `4 x canvas width` is reworded);
  their "Real output" blocks show the new lines. No doc states the SVG byte count.
- The 2026-11-17 spec's "about 230 KB" is replaced with `315,079 bytes` and a dated correction note.

### Error handling

No new failure paths. The count lines are printed only after the SVG write, the computation and the drawing
succeed, so every existing error case keeps its current stdout (a failed SVG write still prints no result
lines).

### Files touched

`descartes.py`, `test_descartes.py`, `mutants-equivalent.toml` (only if an entry's anchor line changes),
`descartes-rs/src/lib.rs`, `descartes-rs/src/main.rs`, `descartes-rs/tests/cli.rs`,
`descartes-rs/tests/parity.rs`, `descartes-rs/.cargo/mutants.toml` (its `src/lib.rs:656:60` anchor shifts
when `svg_limit` lands above `svg_solve`; `tests/test_mutants_exclusions.py` fails until updated),
`tests/scripts/descartes.bats`, the four docs above, and the 2026-11-17 spec.

## Testing

TDD in both languages, one behaviour at a time:

- Default root K=3, `--no-draw --svg`: the last stdout line is
  `SVG shows 3328 of 3328 circles (curvature <= 1000)`.
- Default root K=4, piped (60 x 24 canvas), `--svg`: after the 24 braille rows,
  `SVG shows 3328 of 67166 circles (curvature <= 1000)` then
  `braille draws 524 of 67166 circles (curvature <= 240)` as the last two lines.
- Default root K=1, piped, `--svg`: `SVG shows 8 of 8 circles (curvature <= 10)` and
  `braille draws 8 of 8 circles (curvature <= 10)`.
- Root `-11 21 24 28`, K=1, `--svg`: `SVG shows 0 of 0 circles (curvature <= 10)` and no braille line.
- `--no-draw`: no `braille draws` line; no `--svg`: no `SVG shows` line; `--solve --svg`: stdout unchanged.
- `svg_limit` returns an `int` (Python `isinstance(..., int)`): 1000 for the default root at K=3 and K=4,
  10 at K=1, 11000 for root `-11 21 24 28` at K=5.
- `svg_packing` returns `n` equal to the number of `<circle` elements minus 1.
- The SVG comment line is the line before the first `<circle>`:
  `<!-- circles with curvature <= 1000; cut-off min(10^K, 1000 x |outer curvature|) -->` at K=3 and K=4,
  `<= 10` at K=1; the `--solve` SVG contains no `<!--`.
- Terminal canvas (Python patched `isatty`/terminal size, Rust `on_terminal`): an 80 x 30 terminal draws 28
  braille rows without `--svg` and 27 with it; a 2-row terminal with `--svg` draws 1 row; `--solve` on an
  80 x 30 terminal still draws 29 rows.
- `--help` contains the new epilog sentence in both languages.
- Existing exact-stdout tests are updated to the new order, including Python `test_descartes.py:2391`
  (`len(lines) == 4 + PIPE_HEIGHT`) and `:2417` (`rows = out.splitlines()[4:]`), Rust `src/main.rs` and
  `tests/cli.rs`, and `tests/scripts/descartes.bats`.
- `tests/parity.rs` compares the `SVG shows` and `braille draws` lines between Python and Rust.

The Rust kills for changed-line mutants must come from `--lib --bins --test cli` (the args in
`.cargo/mutants.toml`); `tests/parity.rs` is outside cargo-mutants' run.

## Requirements

- **R1.** With `--svg` in packing mode, stdout contains `SVG shows <n> of <count> circles (curvature <= <limit>)`, with `limit = min(10^K, 1000 x |k_outer|)` printed as an integer, `n` the number of non-bounding circles in the SVG and `count` the `circles` value, in both Python and Rust.
- **R2.** When the braille drawing is printed in packing mode, stdout contains `braille draws <n> of <count> circles (curvature <= <limit>)`, with `limit = min(10^K, 2 x canvas width in braille dots)` and `n` the number of non-bounding circles passed to the renderer, in both Python and Rust.
- **R3.** The count lines are the last stdout lines of a packing run, after the braille drawing, in the order `SVG shows` then `braille draws`; no `braille draws` line is printed with `--no-draw` or when `count` is 0; no `SVG shows` line is printed without `--svg`; `--solve` stdout is unchanged.
- **R4.** The default root prints `SVG shows 3328 of 3328 circles (curvature <= 1000)` at K=3; `SVG shows 3328 of 67166 circles (curvature <= 1000)` and, piped, `braille draws 524 of 67166 circles (curvature <= 240)` at K=4; `SVG shows 8 of 8 circles (curvature <= 10)` and, piped, `braille draws 8 of 8 circles (curvature <= 10)` at K=1; root `-11 21 24 28` at K=1 with `--svg` prints `SVG shows 0 of 0 circles (curvature <= 10)` and no braille line; tests in both languages assert each of these.
- **R5.** The SVG cut-off is computed only by `svg_limit` (Python `svg_limit(root, k)`, Rust `svg_limit`), which returns an integer: 1000 for the default root at K=3 and K=4, 10 at K=1, and 11000 for root `-11 21 24 28` at K=5; `svg_packing` returns the SVG text together with `n`, and that `n` is what `SVG shows` prints.
- **R6.** The `--help` epilog in both languages contains the sentence `The SVG shows circles with curvature at most min(10^K, 1000 x |outer curvature|), radius at least 0.5 of its 1000 units, so with the default root every K from 3 up writes the same SVG.` (whitespace-normalised).
- **R7.** `descartes/README.md`, `descartes/descartes-rs/README.md`, `descartes/CLAUDE.md` and `descartes/descartes-rs/CLAUDE.md` each state the SVG cut-off `min(10^K, 1000 x |outer curvature|)`, that the default root writes the same SVG of 3,328 circles for every K >= 3, the SVG comment, the stdout order `Saved to`, `Saved SVG to`, braille, `SVG shows`, `braille draws` with `Elapsed` (stderr) before the braille, and the terminal canvas height `max(lines - 1 - m, 1)`; they write the braille cut-off as `min(10^K, 2 x canvas width in braille dots)` and state no SVG byte count.
- **R8.** `docs/superpowers/specs/2026-11-17-svg-output-and-prompt-reprompt-design.md` no longer says `about 230 KB`; it says `315,079 bytes` with a correction note dated 2026-11-18.
- **R9.** `descartes/descartes-rs/tests/parity.rs` compares the `SVG shows` and `braille draws` lines between Python and Rust.
- **R10.** The packing SVG's line immediately before its first `<circle>` element is `<!-- circles with curvature <= <limit>; cut-off min(10^K, 1000 x |outer curvature|) -->` with `<limit>` from `svg_limit`, in both languages; the `--solve` SVG contains no `<!--`.
- **R11.** At a terminal the packing canvas height is `max(lines - 1 - m, 1)` with `m` the number of count lines printed (1 without `--svg`, 2 with it): an 80 x 30 terminal draws 28 braille rows without `--svg` and 27 with it, a 2-row terminal with `--svg` draws 1 row; the `--solve` canvas stays `max(lines - 1, 1)` (29 rows on 80 x 30); tests in both languages assert these.
- **V1.** Run both CLIs at the default root with `--svg` for K=1 to 6 (Rust also 7 and 8): every run prints exactly one `SVG shows` line; every K >= 3 SVG is byte-identical to K=3; each `SVG shows` line's `n` equals that SVG's `grep -c '<circle'` minus 1 (3328 for K >= 3); and the Rust K=3 SVG is byte-identical to the Python K=3 SVG or differs only within parity's tolerance.
- **V2.** CI is green on the PR, including `mutation-pr` with 0 survivors on changed lines in both languages.
- **N1.** The SVG circles and labels do not change: same cut-off formula, same `<circle>` and `<text>` elements for every input; the only SVG change is the R10 comment line.
- **N2.** The `.txt` output, the `root`/`circles`/`distinct`/`Saved to`/`Saved SVG to` lines and the `--solve` output do not change.
- **N3.** The braille cut-off formula, the canvas width and the piped 60 x 24 canvas do not change; the terminal canvas height changes only as R11 states.
- **N4.** No new command-line flag.

## Multi-Lens Review

Reviewed at commit: `e97c815` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: (1) The `braille shows` line fixes nothing reported: the braille cut-off is already in `--help` and the drawing is on screen; it fails both reads-it questions and is the expensive half (terminal-canvas tests, four exact-stdout suites, parity). (2) `SVG shows` is the mechanism that changes a decision, but it is stdout-only while the symptom was seen in the files; a fixed comment such as `<!-- circles with curvature <= 1000 -->` (no K, no count, so K >= 3 files stay byte-identical) is excluded by N1 without being weighed. (3) R7's `315,079 bytes` in four docs is untested and goes stale on any SVG format change; keep it only in R8's correction. (4) V1's "`<count>` equals `circles`" compares a value with itself; use `grep -c '<circle'` minus 1 equals `n`. Premise verified: s3/s4/s5 all 315,079 bytes, `cmp` identical, `circles` 3328/67166/1359170; all R4/R5 values reproduce.
Assumption: the operator reads stdout when comparing SVG sizes; if K=1..6 ran in a loop with stdout discarded, `SVG shows` never reaches them and only `--help`/README or an in-file comment works. Settled by asking the operator how the runs were invoked.
Disposition: Addressed (operator, 2026-11-18) — (1) braille line kept as the operator asked, reworded `braille draws`; (2) SVG comment added (R10, N1 reworded); (3) byte count removed from the four docs, kept only in R8; (4) V1 now checks `grep -c '<circle'` minus 1 against `n`.

### Ergonomics

Finding: (1) At an interactive terminal the drawing is `lines - 1` rows (`descartes.py:850`, `main.rs:184`), so any line printed before it, `braille shows` and `SVG shows` included, scrolls off when the prompt returns (measured: 30-row terminal, 34 output lines). N3 forbids sparing the extra row that would keep it on screen; one of the two must give. (2) On a terminal `Elapsed:` (stderr) interleaves between `SVG shows` and `braille shows`; R7's documented order and "Real output" blocks should say so. (3) The braille cut-off is worded `2 x canvas width in braille dots` in `--help` and `4 x canvas width in cells` in the spec; pick one. (4) At K=3, `3328 of 3328` reads as complete and gives no hint K=4 writes the same file; only `--help` covers that. V1 should require one `SVG shows` line per run.
Assumption: the operator's runs were drawn at a terminal; if they were `--no-draw` or piped, finding 1 is moot. Settled by asking how the runs were invoked.
Disposition: Addressed (operator, 2026-11-18) — (1) count lines moved after the drawing and the terminal canvas shrinks by their number (R3, R11, N3 reworded); (2) `Elapsed` placement documented (R7); (3) braille cut-off worded `2 x canvas width in braille dots` everywhere; (4) accepted, `--help` and the SVG comment cover K=3; V1 requires one `SVG shows` line per run.

### Risk

Finding: No load-bearing flaw; every R4/R5 number reproduces and no R contradicts an N. (1) Python `min(10**k, 1000*abs(k0))` is `int` at K <= 3 and `float` at K >= 4 (`k0` is `-1.0`), so an f-string prints `curvature <= 1000.0`; R5's `11000` passes on `11000.0`. Require an `int` return. (2) `descartes-rs/.cargo/mutants.toml` pins `src/lib.rs:656:60`; inserting `svg_limit` above it shifts the anchor (caught by `tests/test_mutants_exclusions.py`, but the spec should name the file). (3) The spec does not say how the SVG `n` is obtained; a second `visible` call doubles the walk; have `svg_packing` return the count. (4) On the 60 x 24 pipe canvas most of the 524 braille circles round to radius 0 dots, so "shows" overstates; "draws" is accurate. (5) Mutation exposure on the moved limit line is killed by the R4/R5 cases; parity.rs is outside cargo-mutants' test args, so `cli.rs`/`main.rs`/lib tests must carry the kills. Python tests that break: `test_descartes.py:2391` and `:2417`.
Assumption: no uncertain assumption found (nearest: Rust prints the same `n`/`limit` at K >= 4, settled by V1).
Disposition: Addressed (operator, 2026-11-18) — (1) `svg_limit` returns an int, tested by `isinstance` (R5); (2) `.cargo/mutants.toml` named under Files touched; (3) `svg_packing` returns `n` (R5); (4) reworded `braille draws`; (5) noted under Testing.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
