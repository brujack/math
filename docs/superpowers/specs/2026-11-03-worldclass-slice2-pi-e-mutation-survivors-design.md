# Worldclass slice 2: pi/e Python mutation survivors

- **Date:** 2026-11-03
- **Status:** Approved
- **Approved:** 2026-11-03
- **Scope:** `pi/pi.py`, `e/e.py`, `pi/test_pi.py`, `e/test_e.py`, a new root test, `pi/CLAUDE.md`, `e/CLAUDE.md`, and the C901 line in root `CLAUDE.md`
- **Revised:** 2026-11-03 after Step 8 round 1 (operator chose the hybrid scope)

## Problem

The 2026-11-01 run of `mutation-testing-python.yml` (run 41279088956, artifact
`mutants-survivors-python`) reported 710 survivors in `pi/pi.py` and 735 in `e/e.py`.
Those two files account for 1,445 of the 1,932 Python survivors across all eight
projects. The other six projects range from 31 (`sq`) to 130 (`factorial`).

Each survivor was mapped to its enclosing function with `ast` over the master tree at
`eaed2c4`. The population is every survivor line in the artifact for these two files:

| Function (pi / e)                            | pi  | e   | Kind      |
| -------------------------------------------- | --- | --- | --------- |
| `estimate_conversion_time` (closure)         | 160 | 160 | display   |
| `ProgressIndicator.show_one_tick` (closure)  | 117 | 117 | display   |
| `write_chunk` (closure)                      | 108 | 108 | mixed     |
| `_calculate_pi_gmpy2` / `_calculate_e_gmpy2` | 88  | 118 | mixed     |
| `save_pi_to_file` / `save_e_to_file` (body)  | 73  | 73  | mixed     |
| module level                                 | 37  | 36  | constants |
| everything else                              | 127 | 123 | mixed     |

Most survivors sit in display code: ETA estimates, progress bars and the write-rate
line. That code lives in closures inside 217-line `save_*_to_file` functions, and only
reaches stdout. Tests do reach it: `TestSavePiEstimateAndProgress.test_estimate_conversion_time_tiers`
(`pi/test_pi.py:943`) drives all four estimate tiers through `save_pi_to_file`. But it
sends stdout to a discarded `io.StringIO()` and asserts only that the file exists, and
`show_one_tick` reads the wall clock, so no test asserts any printed value. The two
`# noqa: C901` comments on `save_*_to_file` already carry
`TODO: split into gmpy2/mpmath helpers`.

The display survivors hide three real gaps:

1. **Multi-chunk pwrite never runs under test.** `_PWRITE_CHUNK` is 4 MiB. Every test
   writes far less than that, so `write_chunk` always runs once with `start == 0`. The
   survivors on the slice end (`pi.py:686`) and the `pwrite` offset (`pi.py:687`) are
   live: a wrong offset would corrupt any output file above 4 MiB (about 4.2 million
   digits), and nothing would notice. The `bytes_done` clamp (`pi.py:692`) feeds only the
   rate display.
2. **`_IO_WORKERS = max(2, min(8, _CPU_COUNT))`** has 4 survivors. It is evaluated once
   at import against the test machine's CPU count, so neither clamp is ever tested.
3. **Four copies of one formatter.** `_gmpy2_str_from_QT` and `_gmpy2_mpfr_to_str` in
   `pi.py`, and `_e_to_str` and `_gmpy2_str_from_PQ` in `e.py`, each repeat the same
   mantissa-to-string block (sign strip, `int_part`, `dec_part`). The copies disagree:
   pi slices `mantissa[exp : digits + 1]`, e slices `mantissa[exp : digits + exp]`. Both
   give the same result for `exp == 1`, which holds for every real π and e value. The
   `exp > 0` and sign branches survive mutation in every copy except the one
   `TestPiToStrNegativeSign` reaches.

### Premise checks (run before design)

- **Mutation scope is one file per project.** `pi/cosmic-ray.toml` has
  `module-path = "pi.py"`, and the template gives the same for every project. Code moved
  into another file would leave mutation scope, so survivors would vanish without being
  killed. That is why everything extracted here stays in `pi.py` and `e.py`.
- **No exclusion mechanism exists today.** `grep` found no `pragma: no mutate`, no
  cosmic-ray filter config and no prior spec or ADR on excluding mutants. The operator
  chose extraction over exclusion (question asked 2026-11-03), so this spec adds none.
- **The pattern is limited to pi and e.** Only `pi/pi.py` and `e/e.py` define
  `estimate_conversion_time`, `ProgressIndicator` or `write_chunk`. No other project
  needs a matching change under the all-projects-identical rule.
- **The unit suites are fast.** `python3 -m unittest test_pi` took 4.66 s and
  `test_e` took 5.63 s on `claude`, so more tests do not threaten cosmic-ray's 60 s
  per-mutant timeout.

## Design

All new functions are module-level in `pi.py` and in `e.py`. They have the same names
and signatures in both files, and the bodies differ only where the outputs already
differ (π versus e labels, `█░` versus `#.` bar glyphs).

### 1. Pure display functions

| Function                                                                 | Replaces                                          | Returns                         |
| ------------------------------------------------------------------------ | ------------------------------------------------- | ------------------------------- |
| `estimate_conversion_time(digits, using_gmpy2)`                          | the closure of the same name                      | `float` seconds                 |
| `render_conversion_tick(digits, elapsed, estimated)`                     | the two `print` bodies in `show_one_tick`         | the line `show_one_tick` prints |
| `render_write_progress(done, total_chunks, total_bytes, chunk, elapsed)` | the arithmetic and `print` body in `write_chunk`  | the line `write_chunk` prints   |
| `render_bar(completed, total, width, full, empty)`                       | `filled = ...; bar = ...` in `_calculate_*_gmpy2` | the bar string                  |

`ProgressIndicator.show_one_tick` keeps only the `start_time is None` guard, the clock
read and the `print`. `write_chunk` keeps the slice, the `_pwrite_all` call, the lock,
the counter and the `print`. Every printed string stays byte-identical. Golden strings
for the render functions are captured from master's code before the refactor, with
`time.time` patched so the closures produce deterministic output.

`show_one_tick` computes its bar from a percentage, `int(30 * pct / 100)`.
`_calculate_*_gmpy2` uses integer division, `completed * 30 // n_workers`. The two
formulas can round differently, so `render_bar` serves only `_calculate_*_gmpy2`, and
`render_conversion_tick` keeps its own formula. Merging the two would change output.

### 2. Formatter consolidation

Each module gets one `_format_mantissa(mantissa, exp, digits)` that holds the sign
strip and the slice `mantissa[exp : exp + digits]`, and raises `ValueError` when
`exp < 1`. Every π and e value has `exp == 1`, so `exp < 1` is outside the domain. The
old `exp > 0 else "0"` branch gave wrong output there instead (`0.0314` lost its leading
zero, and a negative `exp` returned `"0."` through negative indexing). The four
existing formatters call it. For every real π and e value this equals the current pi
slice, because `exp == 1`. The negative-sign path stays and remains tested, since
`TestPiToStrNegativeSign` passes a negative mpfr to `_gmpy2_mpfr_to_str`. The
existing slice is inconsistent; the old behaviour was correct only by accident, at
`exp == 1`.

### 3. Real-gap tests

- **Multi-chunk pwrite.** Patch `_PWRITE_CHUNK` to 7, and write a digit string whose
  length is not a multiple of 7 (several full chunks plus a partial last one). Assert
  the file is byte-identical to header + digits + footer.
- **`_io_workers(cpu_count)`.** A pure function replaces the module-level expression,
  and `_IO_WORKERS = _io_workers(_CPU_COUNT)` keeps the name. Test it at cpu counts
  1, 2, 3, 8 and 9.
- **`_format_mantissa`.** Test negative input, `exp == 1`, `exp == 0` and `exp == -2`
  (both raise `ValueError`), `digits == 1` and `digits == 0`.
- **`estimate_conversion_time` properties, not constants.** The coefficients are
  tuning guesses, so no test restates them. Tests assert three properties at every tier
  boundary (100,000, 1,000,000 and 10,000,000, plus one above each): the result is
  positive, it does not decrease as `digits` grows, and the gmpy2 estimate does not
  exceed the mpmath one. All three hold on master's values. The existing tier test also
  asserts that the captured stdout contains an `Estimated conversion time:` line.

### 4. Complexity comment

Ruff counts nested closures toward the enclosing function. A scratch prototype of the
split, run with `ruff check --select C901 --ignore-noqa`, scored `save_pi_to_file` at
12, down from 21 and still above 10. So both `# noqa: C901` comments stay. The root
`CLAUDE.md` line says removing one "reads as a 0 → 21 regression". Rewrite that figure
to the value measured on the branch, at an equal or smaller byte count, since the file
sits at its 30,000-byte cap. If the branch measures 10 or less, delete the comments and
the line instead.

### 5. Accepted equivalent mutants

These survivors stay, and no test is written for them. The reasons are recorded here
because cosmic-ray has no annotation this repo uses:

- **Precision margins.** `+ 100` bits, `+ 50` dps, `digits + 5` mantissa digits, and the
  `+ 10` / `+ 50` extra series terms. Raising a margin cannot change correct digits.
  Lowering it slightly is absorbed by the other margins at test sizes.
- **Series partition.** `chunk_size = max(100, ...)` and its ceiling division. The
  binary-split sum is exact, so any partition of the term range gives the same `Q`, `T`
  (or `P`, `Q`).
- **Start method.** `"fork" if sys.platform == "linux" else "spawn"`. Both produce the
  same result.
- **Entry guards.** `if __name__ == "__main__"` and the
  `current_process().name == "MainProcess"` check.
- **Cosmetic arguments.** `flush=True` and `end=""` on `print` calls.
- **ETA tuning constants.** The coefficients and floors in `estimate_conversion_time`
  are guesses about conversion speed, not specifications. A test that restates them
  detects only change. The property tests in §3 kill mutants that break ordering or
  sign; mutants that keep the ordering survive by design.
- **First-tier slope.** In the first tier the slope never wins the `max()` (gmpy2
  `d * 5e-8` is at most 0.005, below 0.05; mpmath `0.1 + d * 5e-6` is at most 0.6, below
  1.0), so mutants that only lower the slope are equivalent.

### 6. Keeping pi and e in sync

The extracted functions must stay mirrored across two files, because mutation scope is
one file per project. Nothing checks that today: `tests/test_crate_uniformity.py`
covers only rendered templates, and §2's slice drift shows what happens without a
check. A new root test parses `pi/pi.py` and `e/e.py` with `ast` and asserts that each
mirrored function's `ast.dump` is equal, with no normaliser. The only literal that
differs today is the bar glyph pair in `render_conversion_tick` (`█░` in pi, `#.` in e),
so each module hoists it to module constants `_BAR_FULL` and `_BAR_EMPTY`, and the
mirrored bodies become identical. A normaliser that blanked string constants would also
blank the f-string fragments the render functions exist to produce, which would make the
check vacuous. A negative case alters one parsed tree and asserts the comparison fails. Each mirrored function carries a one-line comment naming its twin. The
reason for the duplication goes in `pi/CLAUDE.md` and `e/CLAUDE.md`, not in the root
file, which has no room.

## Testing

All new tests go in `pi/test_pi.py` and `e/test_e.py`, in table-driven
`unittest.TestCase` classes. Each pure function gets boundary, error-path and state
cases as the repo's testing policy requires:

- **Boundaries.** Each `estimate_conversion_time` threshold at, below and above its
  value; the `max(...)` floors; `elapsed == estimated` (the `<=` branch edge);
  `elapsed == 0`; `completed_chunks == total_chunks`; a partial last chunk.
- **Error paths.** `render_write_progress` with `elapsed == 0` (the guard that avoids
  division by zero); `estimated == 0` is not reachable, because every
  `estimate_conversion_time` branch has a positive floor.
- **State.** The pure functions have no state. The multi-chunk test asserts the whole
  file, so it checks both that no chunk is written twice and that none is skipped.

At least one test for each function asserts a specific value, not just a shape, so an
empty string or `0.0` fails. The exception is `estimate_conversion_time`, whose tests
are property tests by design (R7). A constant positive return would pass them, and that
is accepted: its coefficients are tuning guesses (§5), and the properties exist to catch
ordering and sign breaks, not to pin values. Boundary mutants such as `<=` to `<` at a
threshold also survive the properties, and V1 will show them.

## Requirements

- **R1.** `pi/pi.py` and `e/e.py` each define module-level `estimate_conversion_time`, `render_conversion_tick`, `render_write_progress`, `render_bar`, `_io_workers` and `_format_mantissa`, with identical signatures across the two files.
- **R2.** `save_pi_to_file` and `save_e_to_file` no longer define an `estimate_conversion_time` closure, and their `show_one_tick` and `write_chunk` call `render_conversion_tick` and `render_write_progress`.
- **R3.** Every string printed by `save_*_to_file` and `_calculate_*_gmpy2` is byte-identical to master `eaed2c4` for the same inputs, pinned by golden-string tests.
- **R4.** A test writes a file with `_PWRITE_CHUNK` patched to 7 bytes and a digit string longer than three chunks and not a multiple of 7, and asserts the file bytes equal header + digits + footer, in both projects.
- **R5.** `_IO_WORKERS` equals `_io_workers(_CPU_COUNT)`, and `_io_workers` is tested at cpu counts 1, 2, 3, 8 and 9, returning 2, 2, 3, 8 and 8.
- **R6.** The four mantissa formatters delegate to `_format_mantissa`, which slices `mantissa[exp : exp + digits]`, raises `ValueError` for `exp < 1`, and is tested for negative input, `exp` of 1, 0 and -2, and `digits` of 0 and 1.
- **R7.** `estimate_conversion_time` is tested at each threshold (100,000, 1,000,000 and 10,000,000) and one above it, for both backends, asserting that the result is positive, non-decreasing in `digits`, and no larger for gmpy2 than for mpmath; no test restates a coefficient.
- **R8.** The `# noqa: C901` comments on `save_*_to_file` stay while `ruff check --select C901 --ignore-noqa` scores them above 10, and the root `CLAUDE.md` line's "0 → 21" figure is rewritten to the branch's measured score without growing the file.
- **R9.** A root test asserts that each mirrored function in `pi/pi.py` and `e/e.py` has an equal `ast.dump` with no normaliser, the bar glyphs live in module constants `_BAR_FULL` and `_BAR_EMPTY`, and a negative case shows the comparison fails when one copy changes alone.
- **R10.** `test_estimate_conversion_time_tiers` in `pi/test_pi.py` and `test_estimate_conversion_time_branches` in `e/test_e.py` each assert that captured stdout contains an `Estimated conversion time:` line.
- **V1.** After merge, dispatch `mutation-testing-python.yml` for `pi` and for `e`, and record in the PR or a follow-up comment the survivor count, the total mutant count and the kill rate for each, beside the 2026-11-01 figures (710 and 735 survivors).
- **N1.** No change to the π or e algorithms, the precision formulas or the series term counts.
- **N2.** No code moves out of `pi/pi.py` or `e/e.py` into another module.
- **N3.** No mutant exclusion mechanism (`pragma: no mutate`, a cosmic-ray filter or config exclusions).
- **N4.** No change to the other six Python projects or to the Rust crates.
- **N5.** No new dependencies.

## Multi-Lens Review

Reviewed at commit: `d4c828e` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: The premise "no test can call it" is false. `TestSavePiEstimateAndProgress.test_estimate_conversion_time_tiers` (`pi/test_pi.py:943`) already drives all four estimate tiers through `save_pi_to_file`, but sends stdout to a discarded `io.StringIO()` and asserts only that the file exists. The survivors exist because no test asserts the output, not because the code cannot be reached. Separately, the 160 estimate survivors are tuning constants (`5e-8`, `0.05`, ...). R7's "specific expected float" restates them, so it is a change detector that breaks on the first ETA re-tune and checks no correctness property; the same applies to golden render strings. A cheaper path to the same noise cut is to list display constants under §5. The real-gap half (R4 multi-chunk pwrite, 18 survivors on lines 686/687/692; R5 `_io_workers`, 4 survivors) is confirmed and could ship without the extraction. Minor: `_format_mantissa` cases for `exp == 0` and `exp == 2` pin behaviour outside the π/e domain.
Assumption: After extraction, mutants in the new module-level functions are killed by direct unit tests within the 60 s timeout, not only through `save_*_to_file`'s pool path, where tick-timing mutants could time out. Confirm on a prototype that extracts `estimate_conversion_time` and runs `MUTANT_SHARD=0/10 make mutants` in `pi/`.
Disposition: Addressed — operator chose the hybrid scope: R7 now tests ordering properties instead of restating coefficients, ETA constants and first-tier slope moved to §5, the premise sentence corrected, `_format_mantissa` raises for `exp < 1`, and R10 makes the existing tier test assert its stdout.

### Ergonomics

Finding: R1 creates six function pairs that must stay identical across `pi/pi.py` and `e/e.py`, and nothing enforces it; `tests/test_crate_uniformity.py` covers only rendered templates. §2's own pi/e slice drift is the proof this fails. Fix: a root test that parses both files with `ast` and asserts the six bodies equal after normalising glyph and label constants, plus a one-line "mirrored in e/e.py; mutation scope is one file" comment, with the rationale in the sub-project `CLAUDE.md` files (root is at 30,000/30,000 bytes). Secondary: V2 runs non-interactively (`python3 pi.py 1000 </dev/null`, exit 0), but at 1000 digits it reaches only the first estimate tier, one `write_chunk`, and no gmpy2 bar, and "timing figures masked" is undefined: a mask that swallows the `\r` progress line passes with `render_conversion_tick` returning `""`. Define the mask or drop V2. Minor: R3's golden capture from master needs `time.time` patched inside master's closures; say so in the plan.
Assumption: That the C901 score sits mainly in the closures, so R8 frees the root `CLAUDE.md` line. Settle with `ruff check --select C901 --isolated` on a scratch copy with the closures removed.
Disposition: Addressed — R9 adds the `ast` sync test with twin comments and sub-project `CLAUDE.md` rationale; V2 dropped in favour of R3's deterministic goldens; the golden capture method stated in §1.

### Risk

Finding: Design sound; no R/N conflict. Three defects. (1) Measured on a scratch prototype of the split: `ruff check --select C901 --ignore-noqa` gives `save_pi_to_file` 12 > 10 (down from 21), so the noqa stays, and R8's "keep the line unchanged" branch leaves root `CLAUDE.md`'s "0 → 21 regression" figure stale; the keep branch must rewrite the figure. (This also settles the Ergonomics assumption: R8 frees no bytes.) (2) The `bytes_done` clamp (`pi.py:692`) feeds only `rate` and the print; it is display, not a corruption risk. Only the slice end (686) and offset (687) are. (3) `_format_mantissa` returns `"0."` silently for negative `exp` via Python negative indexing; assert the domain or pin it. Confirmed fine: `patch.object(pi, "_PWRITE_CHUNK", 7)` reaches both `chunk_starts` and `write_chunk`; `_io_workers` is fork/spawn safe; the mutant denominator barely changes; no test passes on empty output. Minor: first-tier slope mutants never win the `max()` (gmpy2 `d*5e-8` ≤ 0.005 < 0.05; mpmath ≤ 0.6 < 1.0), so they are equivalent and belong in §5.
Assumption: The 2026-11-01 baseline is a complete run. Checked by the orchestrator: `gh run view 41279088956 --json jobs` shows all 20 pi and e shard jobs `success`.
Disposition: Addressed — §4 and R8 now keep the noqa (measured 12 > 10) and rewrite the root figure; line 692 reclassified as display; `_format_mantissa` domain enforced with `ValueError`; first-tier slope added to §5. Baseline completeness verified.

### Risk (round 2, scoped re-review at `790ecdf`)

Sections reviewed: Problem, §2-§6, R6-R10. Finding: (1) the Testing section still said a test pins the estimate floor and that every function gets a specific-value assertion, contradicting R7 and §5; (2) R9's normaliser was unspecified, and blanking string constants would also blank the render f-strings, so the check would be vacuous. Verified safe: `ValueError` for `exp < 1` (π, −π and e all give `exp` 1; no caller reaches the formatter with other values); all three estimate properties hold on master at every boundary; R10 is compatible; no R/N conflict. Noted: the properties pass a constant positive return and miss `<=`→`<` threshold mutants.
Assumption: That direct unit tests on the extracted functions kill a large share of the display survivors, rather than most surviving as threshold or constant mutants. V1 settles it after merge.
Disposition: Addressed (operator confirmed 2026-11-03) — R9 now hoists `_BAR_FULL`/`_BAR_EMPTY` and compares plain `ast.dump` with a negative case; the floor clause deleted; the specific-value rule carves out R7 and names the accepted gaps. Review stopped here: both round-2 findings were wording and test-apparatus level, and the fix removed surface (no normaliser).

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
