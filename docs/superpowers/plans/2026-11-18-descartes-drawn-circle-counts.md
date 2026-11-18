# descartes drawn circle counts Implementation Plan

spec: docs/superpowers/specs/2026-11-18-descartes-drawn-circle-counts-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Disclose the SVG curvature cut-off (help, docs, an SVG comment) and end each packing run with `braille draws ...` / `SVG shows ...` count lines, identically in Python and Rust.

**Architecture:** A new `svg_limit(root, k)` is the only source of the SVG cut-off; `svg_packing` returns `(text, n)` and writes a comment line before the first `<circle>`. The CLIs print the count lines after the drawing. Python first (Tasks 1-2), then Rust (Tasks 3-4), then parity (Task 5) and docs (Task 6).

**Tech Stack:** Python 3 stdlib + unittest; Rust (clap, nextest); bats.

## Global Constraints

- Line formats, exact: `braille draws <n> of <count> circles (curvature <= <limit>)` and `SVG shows <n> of <count> circles (curvature <= <limit>)`; both are the last stdout lines of a packing run, after the braille drawing, `braille draws` first.
- `svg_limit(root, k) = min(10^k, 1000 * |root[0]|)` as an integer (`root[0]` is the outer curvature of a reduced root: `root_centres(root)[0][0] == root[0]`, checked for `(-1,2,2,3)`, `(-11,21,24,28)`, `(-2,3,6,7)`). Using the integer `root[0]` removes the Python float (`1000 * abs(-1.0)`) at its source.
- SVG comment, exact, at line index 3 (before the first `<circle>`), packing only: `<!-- circles with curvature <= <limit>; cut-off min(10^K, 1000 x |outer curvature|) -->`.
- Help sentence, exact (whitespace-normalised), appended after the existing braille sentence: `The SVG shows circles with curvature at most min(10^K, 1000 x |outer curvature|), radius at least 0.5 of its 1000 units, so with the default root every K from 3 up writes the same SVG.`
- N1-N4: SVG circles and labels unchanged (only the comment is new); `.txt`, `root`/`circles`/`distinct`/`Saved to`/`Saved SVG to` lines and `--solve` output unchanged; canvas sizing unchanged; no new flag.
- Every changed line owns its mutants (Python `mutation-py`, Rust `mutation-rs`, 0 survivors). Rust kills must come from `--lib --bins --test cli`; `tests/parity.rs` is outside cargo-mutants.
- Tasks run sequentially: `descartes-rs/tests/parity.rs` runs `../descartes.py` inside `cargo test`, so a parallel Python edit would make the Rust gate flaky.
- Line numbers below are as of master `c1ad8d4`; re-grep before editing.

## Verification (session level)

After Task 6, from the feature worktree:

1. `make -C descartes test` and `make -C descartes/descartes-rs test` exit 0; `make test` at the repo root exits 0.
2. V1: in a scratch dir, `for k in 1 2 3 4 5 6; do python3 <wt>/descartes/descartes.py $k --yes --no-draw --svg p$k.svg; done` and the same with the Rust release binary for K=1..8 (`--yes`). Expect: exactly one `SVG shows` line per run; `cmp p3.svg p$k.svg` silent for every K >= 3 within each language; each line's `n` equals `$(( $(grep -c '<circle' p$k.svg) - 1 ))` (3328 for K >= 3); the Python and Rust K=3 files differ at most within parity's thousandths tolerance.
3. Edge cases: root `-11 21 24 28` K=1 `--svg` prints `SVG shows 0 of 0 circles (curvature <= 10)` and no `braille draws`; `--no-draw` prints no `braille draws`; `--solve ... --svg` stdout is byte-identical to master's.
4. V2: PR CI green including `mutation-pr`.

---

### Task 1: Python svg_limit, svg_packing count and SVG comment

```yaml-task
id: 1
description: Add svg_limit, make svg_packing return (text, n) with the cut-off comment, and update its callers and tests in Python
role: executor
model: sonnet
tdd: required
requirements: [R5, R10]
acceptance:
  - cmd: 'cd descartes && python3 -m unittest test_descartes.TestSvgLimit test_descartes.TestSvgPacking'
    exit_code: 0
  - cmd: make -C descartes test
    exit_code: 0
  - cmd: 'cd descartes && pyright'
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_equivalent
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py, descartes/mutants-equivalent.toml]
depends_on: []
```

**Files:** `descartes/descartes.py` (`svg_packing` ~line 561, `_run_packing` ~line 891), `descartes/test_descartes.py` (`TestSvgPacking` ~2872, `TestSvgCli` ~3079), `descartes/mutants-equivalent.toml` (the `svg_packing` `px` entry anchors `above` on the `enumerate([outer, *visible(root, limit)])` line; re-confirm the mutant is still equivalent and update the anchor).

**Interfaces:**

- Produces: `svg_limit(root: tuple[int, int, int, int], k: int) -> int`; `svg_packing(root, k) -> tuple[str, int]` where the int is `len(visible(root, svg_limit(root, k)))`.

Steps:

- [ ] Write `TestSvgLimit`: `svg_limit(DEFAULT_ROOT, 1) == 10`, `== 1000` at K=3 and K=4, `svg_limit((-11, 21, 24, 28), 5) == 11000`, and `isinstance(..., int)` for each (`assertIs(type(v), int)`; the K=4 case is the one a float would fail). Run it: fails with `AttributeError`.
- [ ] Implement `svg_limit` (`return min(10**k, 1000 * abs(root[0]))`, docstring naming the 0.5-unit radius) and use it in `svg_packing`.
- [ ] Add to `TestSvgPacking`: `text, n = svg_packing(DEFAULT_ROOT, 3)`: `n == 3328`, `n == text.count("<circle") - 1`; `text.splitlines()[3] == "<!-- circles with curvature <= 1000; cut-off min(10^K, 1000 x |outer curvature|) -->"`; K=1 line contains `<= 10;`; K=3 and K=4 texts are equal; `svg_solve(...)` output contains no `<!--`. Root `-11 21 24 28` K=1 gives `n == 0`.
- [ ] Return `(_svg_document(elements), n)` with the comment inserted after `_SVG_HEAD`; walk `visible` once. Update `_run_packing` to unpack (`text, _n = svg_packing(...)` for now; Task 2 uses `n`) and the existing tests that treat the result as a string (`~2881` first-lines test: the outer `<circle>` moves to index 4; `~3079` compares the written file with `svg_packing(...)[0]`).
- [ ] Re-confirm the equivalents entry; run the acceptance commands; commit with `caveman:caveman-commit`.

### Task 2: Python count lines and help sentence

```yaml-task
id: 2
description: Print braille draws and SVG shows count lines after the drawing and add the SVG help sentence in descartes.py
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R4, R6]
acceptance:
  - cmd: 'cd descartes && python3 -m unittest test_descartes.TestCountLines'
    exit_code: 0
  - cmd: make -C descartes test
    exit_code: 0
  - cmd: 'cd descartes && pyright'
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_equivalent
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py, descartes/mutants-equivalent.toml]
depends_on: [1]
```

**Files:** `descartes/descartes.py` (`parse_args` epilog ~659, `_draw_packing` ~861, `_run_packing` ~870-904), `descartes/test_descartes.py`.

**Interfaces:**

- Consumes: `svg_limit`, `svg_packing -> (text, n)` from Task 1.
- Produces: `_draw_packing(root, n, count) -> None` printing the drawing then `braille draws ...`; stdout order per Global Constraints.

Steps:

- [ ] Write `TestCountLines(CliTestCase)` using `run_main` (piped, 60 x 24): K=3 `--no-draw --svg p.svg` last line `SVG shows 3328 of 3328 circles (curvature <= 1000)`; K=4 `--svg p.svg` last two lines `braille draws 524 of 67166 circles (curvature <= 240)`, `SVG shows 3328 of 67166 circles (curvature <= 1000)`; K=1 `--svg` last two `braille draws 8 of 8 circles (curvature <= 10)`, `SVG shows 8 of 8 circles (curvature <= 10)`; `--root -11 21 24 28` K=1 `--svg`: last line `SVG shows 0 of 0 circles (curvature <= 10)` and no line starts `braille draws`; K=2 `--no-draw` has no `braille draws`; K=2 without `--svg` has no `SVG shows`; `--solve -1,0,0 2,0.5,0 3,0,0.6666666666666666 --svg s.svg` stdout has neither; `--help` stdout, whitespace-normalised, contains the help sentence. Run: fails.
- [ ] Implement: `_draw_packing` gains `count`, prints the drawing then the braille line with its existing `limit` and `len(visible(...))`; `_run_packing` prints `SVG shows ...` last (after `_draw_packing`, or after `Saved SVG to` when nothing is drawn); epilog sentence.
- [ ] Update tests the order change breaks: `~2391` (`len(lines) == 4 + PIPE_HEIGHT` → `+ 1` for the braille line), `~2417` (`rows = out.splitlines()[4:]` → `[4:-1]`), `~2615` `run_capturing_render` (`out.endswith("drawn\n")`, used by ~7 tests: the braille line now follows). Re-run the full file.
- [ ] Run the acceptance commands; commit.

### Task 3: Rust svg_limit, svg_packing count and SVG comment

```yaml-task
id: 3
description: Add pub svg_limit, make svg_packing return (text, n) with the cut-off comment, update call sites, tests and the mutants.toml anchor in descartes-rs
role: executor
model: sonnet
tdd: required
requirements: [R5, R10]
acceptance:
  - cmd: 'cd descartes/descartes-rs && cargo test --lib svg_limit'
    exit_code: 0
    stdout_match: 'svg_limit'
  - cmd: make -C descartes/descartes-rs test
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_exclusions
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/src/lib.rs, descartes/descartes-rs/src/main.rs, descartes/descartes-rs/.cargo/mutants.toml]
depends_on: [2]
```

**Files:** `descartes/descartes-rs/src/lib.rs` (`svg_packing` ~635-651, tests incl. the first-lines test ~2789 and 9 `svg_packing(...).unwrap()` sites), `src/main.rs` (`run_packing` ~431: destructure only), `.cargo/mutants.toml` (`src/lib.rs:656:60` anchor for `svg_solve`'s `k < 0` exclusion moves; recompute line:col).

**Interfaces:**

- Produces: `pub fn svg_limit(root: [i64; 4], k: u32) -> i64` (`10_i64.pow(k).min(1000 * root[0].abs())`); `pub fn svg_packing(root: [i64; 4], k: u32) -> Result<(String, usize), DescartesError>`.

Steps:

- [ ] Write lib tests `svg_limit_*`: default root K=1 → 10, K=3 and K=4 → 1000, `[-11, 21, 24, 28]` K=5 → 11000. `svg_packing_counts_and_comments`: K=3 `n == 3328 == text.matches("<circle").count() - 1`, line 3 is the comment with `<= 1000;`, K=1 `<= 10;`, K=3 text == K=4 text; root `-11 21 24 28` K=1 `n == 0`; `svg_solve` output has no `<!--`. Run: fails to compile.
- [ ] Implement; insert the comment after `SVG_HEAD` in the packing body; collect `visible` once and return its length. Update the 9 call sites, the first-lines test (outer `<circle>` now index 4) and `main.rs` (`let (text, _n) = ...`).
- [ ] Update the `mutants.toml` anchor; run the acceptance commands; commit.

### Task 4: Rust count lines and help sentence

```yaml-task
id: 4
description: Print braille draws and SVG shows count lines after the drawing and add the SVG help sentence in descartes-rs main.rs
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R4, R6]
acceptance:
  - cmd: 'cd descartes/descartes-rs && cargo test --bins count_lines'
    exit_code: 0
    stdout_match: 'count_lines'
  - cmd: make -C descartes/descartes-rs test
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/src/main.rs, descartes/descartes-rs/tests/cli.rs]
depends_on: [3]
```

**Files:** `src/main.rs` (`EPILOG` ~38, `run_packing` ~399-458, tests module using `piped(&args)` ~575 and `has_line`), `tests/cli.rs` (`~153` asserts `lines.last() == Some("Saved SVG to out.svg")`).

**Interfaces:**

- Consumes: `svg_limit`, `svg_packing -> (String, usize)` from Task 3.

Steps:

- [ ] Write `count_lines_*` tests in `main.rs` mirroring Task 2's cases exactly (same strings, same order, same absent-line cases, `--help` sentence via the epilog constant or `--help` output). Run: fails.
- [ ] Implement: after `draw(...)` in `run_packing` print `braille draws {n} of {count} circles (curvature <= {limit})` with the existing `limit` and `circles.len() - 1`; then, with `--svg`, `SVG shows {n} of {count} circles (curvature <= {svg_limit})` as the last line; extend `EPILOG`.
- [ ] Update `cli.rs:153` to the new last line and any other assertion the order change breaks; run the acceptance commands; commit.

### Task 5: Parity covers the count lines

```yaml-task
id: 5
description: Compare the braille draws and SVG shows lines between Python and Rust in parity.rs
role: executor
model: sonnet
tdd: required
requirements: [R9]
acceptance:
  - cmd: 'cd descartes/descartes-rs && cargo test --test parity count_lines'
    exit_code: 0
    stdout_match: 'count_lines'
  - cmd: make -C descartes/descartes-rs test
    exit_code: 0
max_retries: 2
files_touched: [descartes/descartes-rs/tests/parity.rs]
depends_on: [4]
```

**Files:** `descartes/descartes-rs/tests/parity.rs` (`stable_lines` ~37 compares lines by prefix).

Steps:

- [ ] Add a test `count_lines_match_python` that runs both programs piped with `3 --svg <tmp>/p.svg` and `4 --svg <tmp>/q.svg`, and asserts the `braille draws ` and `SVG shows ` lines are equal (exactly one each). Prove it can fail: temporarily change the Rust format string, see the test fail, restore.
- [ ] Run the acceptance commands; commit.

### Task 6: Docs and the 2026-11-17 spec correction

```yaml-task
id: 6
description: Docs-only (no behaviour change) — state the SVG cut-off, comment, count lines and stdout order in the four descartes docs and correct the 230 KB figure
role: executor
model: sonnet
tdd: not-applicable
requirements: [R7, R8]
acceptance:
  - cmd: 'for f in descartes/README.md descartes/descartes-rs/README.md descartes/CLAUDE.md descartes/descartes-rs/CLAUDE.md; do command grep -qF "1000 x |outer curvature|" "$f" && command grep -qF "SVG shows" "$f" && command grep -qF "braille draws" "$f" && command grep -qF "plus the outer circle" "$f" && ! command grep -qF "315,079" "$f" && ! command grep -qF "4 x canvas width" "$f" || exit 1; done'
    exit_code: 0
  - cmd: 'command grep -qF "315,079 bytes" docs/superpowers/specs/2026-11-17-svg-output-and-prompt-reprompt-design.md && command grep -qF "corrected 2026-11-18" docs/superpowers/specs/2026-11-17-svg-output-and-prompt-reprompt-design.md && ! command grep -qF "230 KB);" docs/superpowers/specs/2026-11-17-svg-output-and-prompt-reprompt-design.md'
    exit_code: 0
max_retries: 2
files_touched: [descartes/README.md, descartes/descartes-rs/README.md, descartes/CLAUDE.md, descartes/descartes-rs/CLAUDE.md, docs/superpowers/specs/2026-11-17-svg-output-and-prompt-reprompt-design.md]
depends_on: [5]
```

Each doc's `--svg` paragraph states: cut-off `min(10^K, 1000 x |outer curvature|)` (radius at least 0.5 of 1000 units); the default root writes the same SVG (3,328 circles plus the outer circle) for every K >= 3; the comment line; the count lines; stdout order `Saved to`, `Saved SVG to`, braille, `braille draws`, `SVG shows`, with `Elapsed` (stderr) before the braille on a terminal. Reword `4 x canvas width` to `2 x canvas width in braille dots`. Update the "Real output" blocks from real runs (`python3 descartes.py 2 --no-draw --svg p.svg` in a scratch dir; Rust `cargo run --release -q -- 2 --no-draw --svg p.svg`). No doc states an SVG byte count. In the 2026-11-17 spec replace `about 230 KB` with `315,079 bytes (corrected 2026-11-18; the earlier "about 230 KB" was not a measurement of this format)`. These files are not read by any suite, so the gates are scoped; the orchestrator runs root `make test` after this task.

## Non-goal check

Fresh reviewer (Opus), 2026-11-18, against N1-N4 of the spec:

- N1 CLEAR — `svg_limit` uses `root[0]`, shown equal to the float outer curvature for three roots, so the cut-off and circle set are unchanged; the outer `<circle>` moving to index 4 is only the comment's effect. Resolution: none needed.
- N2 CLEAR — test edits follow from count lines placed after `Saved SVG to`; existing lines are unchanged and `--solve` stdout is asserted unchanged. Resolution: none needed.
- N3 CLEAR — `4 + PIPE_HEIGHT` and `[4:-1]` edits count output lines, not canvas rows; the `4 x canvas width` rewording is docs-only. Resolution: none needed.
- N4 CLEAR — no flag added. Resolution: none needed.
