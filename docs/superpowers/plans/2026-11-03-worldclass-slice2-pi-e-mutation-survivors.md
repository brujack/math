# Worldclass Slice 2: pi/e Mutation Survivors Implementation Plan

> **Status: DONE** (math#201, c7c8f6f)

spec: docs/superpowers/specs/2026-11-03-worldclass-slice2-pi-e-mutation-survivors-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the display and formatting logic in `pi/pi.py` and `e/e.py` into pure module-level functions with value-asserting tests, and close the real test gaps: multi-chunk pwrite, `_io_workers`, and `_format_mantissa`.

**Architecture:** Six functions become module-level in each file, with identical bodies. pi is done first; e then copies pi's function source verbatim. A root `ast` test keeps the copies identical from then on. Nothing moves to another module, because cosmic-ray's `module-path` is one file per project.

**Tech Stack:** Python 3, unittest, ruff, pyright, cosmic-ray (CI only).

## Global Constraints

- No change to the π or e algorithms, precision formulas or series term counts (N1).
- No code moves out of `pi/pi.py` or `e/e.py` (N2). No `pragma: no mutate`, cosmic-ray filter or config exclusion (N3).
- No change to the other six Python projects or the Rust crates (N4). No new dependencies (N5).
- Every printed string stays byte-identical to master `eaed2c4` (R3).
- Root `CLAUDE.md` must not grow past 30000 bytes (`wc -c CLAUDE.md`).
- Run sub-project commands from the sub-project dir: `cd pi && make test`. Unit suites take about 5 s.

## Verification Planning

- **Whole change:** `make -C pi test`, `make -C e test`, `make -C pi coverage`, `make -C e coverage`, `(cd pi && pyright)`, `(cd e && pyright)`, `make lint`, `make test-python`. All exit 0.
- **Discrimination:** Task 1 and Task 2 each apply two named mutations (pwrite offset, `_io_workers` clamp), see the suite go red, and revert.
- **Post-merge (V1):** dispatch `mutation-testing-python.yml` for `pi` and `e`. Record survivors, total mutants and kill rate beside the 2026-11-01 baseline: 710 survivors for pi, 735 for e. All 20 baseline shards succeeded in run 41279088956.

## Reference: the six mirrored functions

Task 1 adds these to `pi/pi.py` at module level, after the `_PWRITE_CHUNK` constant. Task 2 copies them byte for byte into `e/e.py`. The docstrings are generic, so the bodies are identical, and comments are free to differ (`ast` drops them). Each function's first comment line reads `# Mirrored in e/e.py (tests/test_pi_e_mirror.py); mutation scope is one file.` (`pi/pi.py` in the e copy).

```python
_BAR_FULL = "█"   # pi; e uses "#"
_BAR_EMPTY = "░"  # pi; e uses "."


def _io_workers(cpu_count):
    """Return the parallel I/O worker count for *cpu_count* CPUs: 2..8."""
    return max(2, min(8, cpu_count))


def estimate_conversion_time(digits, using_gmpy2):
    """Return a rough string-conversion time estimate in seconds."""
    # body: master's closure body verbatim, with `d` renamed to `digits`
    # and the free variable `using_gmpy2` now a parameter


def render_conversion_tick(digits, elapsed, estimated):
    """Return the conversion progress line show_one_tick prints."""
    # body: master's show_one_tick branches verbatim, `print(...)` -> `return ...`,
    # `self.estimated_duration` -> `estimated`, glyphs -> _BAR_FULL/_BAR_EMPTY


def render_write_progress(done, total_chunks, total_bytes, chunk, elapsed):
    """Return the file-write progress line write_chunk prints."""
    # body: master's write_chunk arithmetic + f-string verbatim, with
    # completed_chunks -> done, len(pi_bytes) -> total_bytes, _PWRITE_CHUNK -> chunk


def render_bar(completed, total, width, full, empty):
    """Return a progress bar of *width* cells, completed*width//total filled."""
    filled = completed * width // total
    return full * filled + empty * (width - filled)


def _format_mantissa(mantissa, exp, digits):
    """Format an mpfr.digits() mantissa as 'I.DDDD' with *digits* decimals."""
    if exp < 1:
        raise ValueError(f"_format_mantissa: exp must be >= 1, got {exp}")
    sign = ""
    if mantissa.startswith("-"):
        sign, mantissa = "-", mantissa[1:]
    return f"{sign}{mantissa[:exp]}.{mantissa[exp : exp + digits]}"
```

Golden strings, computed by running master's closure bodies verbatim with these inputs:

| Call                                                      | Expected (pi glyphs; e swaps `█`→`#`, `░`→`.`)                                                           |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `render_conversion_tick(1000, 1.25, 5.0)`                 | `'\rConverting 1,000 digits..  [███████░░░░░░░░░░░░░░░░░░░░░░░] 25.0% Elapsed: 1.2s \| ETA: 3.8s'`       |
| `render_conversion_tick(1234567, 7.6, 5.0)`               | `'\rConverting 1,234,567 digits... [Still converting...] Elapsed: 7.6s (longer than estimated)'`         |
| `render_conversion_tick(1000, 5.0, 5.0)`                  | `'\rConverting 1,000 digits..  [██████████████████████████████] 100.0% Elapsed: 5.0s \| ETA: 0.0s'`      |
| `render_conversion_tick(50, 0.0, 1.0)`                    | `'\rConverting 50 digits    [░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 0.0% Elapsed: 0.0s \| ETA: 1.0s'`           |
| `render_bar(3, 8, 30, _BAR_FULL, _BAR_EMPTY)`             | 11 full + 19 empty                                                                                       |
| `render_bar(8, 8, 30, ...)` / `render_bar(1, 8, 30, ...)` | 30 full / 3 full + 27 empty                                                                              |
| `render_write_progress(1, 3, 10_000_000, 4_194_304, 2.0)` | `'\rFile write progress: 33.3% \| Written: 4,194,304/10,000,000 chars \| ETA: 4.0s \| Rate: 2.0 MB/s'`   |
| `render_write_progress(3, 3, 10_000_000, 4_194_304, 4.0)` | `'\rFile write progress: 100.0% \| Written: 10,000,000/10,000,000 chars \| ETA: 0.0s \| Rate: 2.4 MB/s'` |
| `render_write_progress(1, 3, 10_000_000, 4_194_304, 0.0)` | `'\rFile write progress: 33.3% \| Written: 4,194,304/10,000,000 chars \| ETA: 0.0s \| Rate: 0.0 MB/s'`   |
| `render_write_progress(2, 3, 20, 7, 0.5)`                 | `'\rFile write progress: 66.7% \| Written: 14/20 chars \| ETA: 0.2s \| Rate: 0.0 MB/s'`                  |

(`\|` is table escaping; the strings contain a plain `|`.)

Estimate property points: digits ∈ {100_000, 100_001, 1_000_000, 1_000_001, 10_000_000, 10_000_001}. On master, gmpy2 gives [0.05, 0.1, 0.2, 5.0, 50, 100] and mpmath gives [1, 2, 2.5, 50, 500, 1000]. Assert, for both backends: every value > 0, the list is non-decreasing, and gmpy2 ≤ mpmath pointwise. No test restates a coefficient (R7).

---

### Task 1: Extract and test pi's display and formatting functions

```yaml-task
id: 1
description: Add the six mirrored functions and bar constants to pi/pi.py, rewire their call sites, and add value-asserting tests
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R4, R5, R6, R7, R10]
acceptance:
  - cmd: make -C pi test
    exit_code: 0
  - cmd: make -C pi coverage
    exit_code: 0
  - cmd: bash -c 'cd pi && pyright'
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [pi/pi.py, pi/test_pi.py]
depends_on: []
```

**Steps (TDD, one behaviour at a time, RED then GREEN):**

- [ ] Add class `TestMirroredHelpers` to `pi/test_pi.py`, with the golden rows above (pi glyphs), the `_io_workers` table (1→2, 2→2, 3→3, 8→8, 9→8) and the estimate properties. Add `_format_mantissa` cases:
  - `("314159", 1, 3)` gives `"3.141"`
  - `("-314159", 1, 3)` gives `"-3.141"`
  - `digits` 0 gives `"3."`
  - `digits` 1 gives `"3.1"`
  - `exp` 0 and `exp` -2 each raise `ValueError`

  Run them; they fail on ImportError.

- [ ] Add the six functions and constants (Reference section). Set `_IO_WORKERS = _io_workers(_CPU_COUNT)`.
- [ ] Rewire the call sites:
  - `save_pi_to_file`: delete the `estimate_conversion_time` closure and call `estimate_conversion_time(digits, using_gmpy2)`.
  - `show_one_tick`: keep the `start_time is None` guard and the `elapsed` read, then `print(render_conversion_tick(digits, elapsed, self.estimated_duration), end="", flush=True)`.
  - `write_chunk`: keep the slice, `_pwrite_all`, the lock and `completed_chunks += 1`, then `print(render_write_progress(completed_chunks, total_chunks, len(pi_bytes), _PWRITE_CHUNK, time.time() - write_start), end="", flush=True)`.
  - `_calculate_pi_gmpy2`: `bar = render_bar(completed, n_workers, bar_width, _BAR_FULL, _BAR_EMPTY)`.
  - `_gmpy2_str_from_QT` and `_gmpy2_mpfr_to_str`: compute `mantissa, exp` as today, then `return _format_mantissa(mantissa, exp, digits)`.
- [ ] Multi-chunk test (R4), in `TestSavePiEstimateAndProgress`:
  - Copy the existing `_FakePool`/`_FakeFuture` pattern so the future returns `s = "3." + "1415926535" * 3` (32 chars).
  - Run `save_pi_to_file(mpmath.mpf(3), 30, "chunk.txt")` with `patch("pi._PWRITE_CHUNK", 7)`.
  - Assert the file bytes equal `("π calculated to 30 decimal places using mpmath\n" + "=" * 60 + "\n\n").encode() + s.encode() + b"\n\nTotal decimal places: 30"`.
- [ ] R10: in `test_estimate_conversion_time_tiers`, keep the `io.StringIO()` buffer and assert `"Estimated conversion time:"` is in each tier's output.
- [ ] Discrimination controls, each in the working tree then reverted. Report both reds in your receipt:
  - (a) change `pi_offset + start` to `pi_offset` in `write_chunk` and confirm the R4 test fails;
  - (b) change `min(8, cpu_count)` to `min(9, cpu_count)` and confirm the `_io_workers` test fails.
- [ ] Run the acceptance gates. Do not commit; the orchestrator commits.

**Interfaces:**

- Produces: the module-level names `_BAR_FULL`, `_BAR_EMPTY`, `_io_workers`, `estimate_conversion_time`, `render_conversion_tick`, `render_write_progress`, `render_bar` and `_format_mantissa` in `pi/pi.py`, with the exact signatures above. Task 2 copies their source; Task 3 parses it.

### Task 2: Mirror the functions into e

```yaml-task
id: 2
description: Copy pi's six function bodies verbatim into e/e.py, rewire e's call sites, and add the same tests with e glyphs and labels
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R4, R5, R6, R7, R10]
acceptance:
  - cmd: make -C e test
    exit_code: 0
  - cmd: make -C e coverage
    exit_code: 0
  - cmd: bash -c 'cd e && pyright'
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [e/e.py, e/test_e.py]
depends_on: [1]
```

**Steps:** These mirror Task 1, with the following differences:

- **Glyphs:** `_BAR_FULL = "#"`, `_BAR_EMPTY = "."`, and goldens with `#`/`.`.
- **Function bodies:** copy the six bodies from `pi/pi.py` exactly, docstrings included. Only the constants' values differ.
- **Formatters:** `_e_to_str`'s gmpy2 branch and `_gmpy2_str_from_PQ` call `_format_mantissa`.
- **Tests:**
  - **Class names:** `TestMirroredHelpers` in `e/test_e.py`, and the R4 test in `TestSaveEEstimateAndProgress`.
  - **R4 header:** `"e calculated to 30 decimal places using mpmath\n"`, with `s = "2." + "7182818284" * 3`.
  - **R10:** applies to `test_estimate_conversion_time_branches`.
- **Discrimination:** controls (a) and (b) on `e_offset + start` and `_io_workers`.

Before handing back, run `diff <(sed -n '/^def _io_workers/,/^def _format_mantissa/p' pi/pi.py) <(sed -n '/^def _io_workers/,/^def _format_mantissa/p' e/e.py)` and report the output. Only comment lines may differ.

**Interfaces:**

- Consumes: Task 1's function source in `pi/pi.py`.
- Produces: the same names in `e/e.py`.

### Task 3: Mirror test, C901 figure, docs

```yaml-task
id: 3
description: Add tests/test_pi_e_mirror.py comparing ast.dump of the six mirrored functions, rewrite root CLAUDE.md's C901 figure, and document the mirror in pi/e CLAUDE.md
role: executor
model: sonnet
tdd: required
requirements: [R8, R9]
acceptance:
  - cmd: python3 -m unittest tests.test_pi_e_mirror -v
    exit_code: 0
  - cmd: make test-python
    exit_code: 0
  - cmd: make lint
    exit_code: 0
  - cmd: bash -c '[ "$(wc -c < CLAUDE.md)" -le 30000 ]'
    exit_code: 0
  - cmd: bash -c '! command grep -q "0 → 21" CLAUDE.md'
    exit_code: 0
max_retries: 3
files_touched: [tests/test_pi_e_mirror.py, CLAUDE.md, pi/CLAUDE.md, e/CLAUDE.md, docs/superpowers/README.md]
depends_on: [2]
```

**Steps:**

- [ ] Write `tests/test_pi_e_mirror.py`:
  - Add `MIRRORED = ("_io_workers", "estimate_conversion_time", "render_conversion_tick", "render_write_progress", "render_bar", "_format_mantissa")`.
  - Add a helper `mirror_mismatches(pi_tree, e_tree) -> list[str]`. It returns the names whose `ast.dump(node)` differ, plus any name missing from either tree (missing counts as a mismatch). Parse each file with `ast.parse`.
  - Test 1: the real files give `[]`.
  - Test 2 (negative): copy the pi tree, change one `ast.Constant` inside `render_bar`'s body, and assert `["render_bar"]` is returned.
  - Test 3: delete `_format_mantissa` from the e tree and assert it is reported.
  - The file needs no gmpy2 or mpmath; it only parses.
- [ ] Measure `ruff check --select C901 --ignore-noqa --isolated pi/pi.py e/e.py` and record both `save_*_to_file` scores in your receipt.
  - **If both are above 10:** keep both noqa comments. Edit root `CLAUDE.md` line 77, replacing `0 → 21` with `0 → <measured>` (use the larger score if they differ). The byte count must not grow.
  - **If both are 10 or less:** remove both noqa comments and delete line 77.
  - **If the two differ in kind (one above 10, one not):** stop and report a blocker.
- [ ] Add one paragraph to `pi/CLAUDE.md` and to `e/CLAUDE.md` naming the six mirrored functions. Say why they are duplicated: cosmic-ray's `module-path` is one file. Name `tests/test_pi_e_mirror.py` as the guard.
- [ ] Add a plan row to `docs/superpowers/README.md` next to the slice 1 row, status In Progress.

**Interfaces:**

- Consumes: the names from Tasks 1 and 2.

## Orchestrator steps

- Work in `.worktrees/wc-slice2` on branch `test/pi-e-mutation-survivors`. Commit after each task with `caveman:caveman-commit`. Run `rm -rf .cache` before commits.
- After Task 3: `make test`, `make -C pi test`, `make -C e test`, and `git diff --stat origin/master...HEAD` (only the eight `files_touched` paths plus the plan file).
- Open the PR with `gh pr create --draft`. Run Phase 3. Run `gh pr ready` only after Phase 3 passes.

## Non-goal check

Reviewer verdicts (fresh subagent, `nongoal-check.md`): N1 CLEAR, N2 CLEAR, N3 CLEAR, N4 CLEAR, N5 CLEAR. Close calls the reviewer noted: `estimate_conversion_time` keeps its body with only a parameter rename (N1); the mirror test only parses files, moving no code (N2); removing `# noqa: C901` is a ruff suppression, not a mutant exclusion (N3). No resolution needed.
