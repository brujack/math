# Worldclass slice 2: pi/e Python mutation survivors

- **Date:** 2026-11-03
- **Status:** Draft
- **Scope:** `pi/pi.py`, `e/e.py`, `pi/test_pi.py`, `e/test_e.py`, and the C901 line in root `CLAUDE.md`

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
reaches stdout. No test can call it, so no test can kill a mutation in it. The two
`# noqa: C901` comments on `save_*_to_file` already carry
`TODO: split into gmpy2/mpmath helpers`.

The display survivors hide three real gaps:

1. **Multi-chunk pwrite never runs under test.** `_PWRITE_CHUNK` is 4 MiB. Every test
   writes far less than that, so `write_chunk` always runs once with `start == 0`. The
   survivors on the slice end (`pi.py:686`), the `pwrite` offset (`pi.py:687`) and the
   `bytes_done` clamp (`pi.py:692`) are live: a wrong offset would corrupt any output
   file above 4 MiB (about 4.2 million digits), and nothing would notice.
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
for the tests are captured by running the current master code before the refactor.

`show_one_tick` computes its bar from a percentage, `int(30 * pct / 100)`.
`_calculate_*_gmpy2` uses integer division, `completed * 30 // n_workers`. The two
formulas can round differently, so `render_bar` serves only `_calculate_*_gmpy2`, and
`render_conversion_tick` keeps its own formula. Merging the two would change output.

### 2. Formatter consolidation

Each module gets one `_format_mantissa(mantissa, exp, digits)` that holds the sign
strip, the `exp > 0` branch and the slice `mantissa[exp : exp + digits]`. The four
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
- **`_format_mantissa`.** Test negative input, `exp == 0`, `exp == 1`, `exp == 2`,
  `digits == 1` and `digits == 0`.

### 4. Complexity comment

If `ruff check --select C901 pi/pi.py e/e.py`, run without the `noqa`, passes on
`save_*_to_file` after the split, delete both `# noqa: C901` comments. In that case
also delete the root `CLAUDE.md` line that calls them load-bearing. If either
function still exceeds the threshold, keep both comments and the line unchanged, and
record the measured complexity in the PR body.

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

## Testing

All new tests go in `pi/test_pi.py` and `e/test_e.py`, in table-driven
`unittest.TestCase` classes. Each pure function gets boundary, error-path and state
cases as the repo's testing policy requires:

- **Boundaries.** Each `estimate_conversion_time` threshold at, below and above its
  value; the `max(...)` floors; `elapsed == estimated` (the `<=` branch edge);
  `elapsed == 0`; `completed_chunks == total_chunks`; a partial last chunk.
- **Error paths.** `render_write_progress` with `elapsed == 0` (the guard that avoids
  division by zero); `estimated == 0` is not reachable, because every
  `estimate_conversion_time` branch has a positive floor, and a test pins that floor.
- **State.** The pure functions have no state. The multi-chunk test asserts the whole
  file, so it checks both that no chunk is written twice and that none is skipped.

At least one test for each function asserts a specific value, not just a shape. An
empty string or `0.0` must fail.

## Requirements

- **R1.** `pi/pi.py` and `e/e.py` each define module-level `estimate_conversion_time`, `render_conversion_tick`, `render_write_progress`, `render_bar`, `_io_workers` and `_format_mantissa`, with identical signatures across the two files.
- **R2.** `save_pi_to_file` and `save_e_to_file` no longer define an `estimate_conversion_time` closure, and their `show_one_tick` and `write_chunk` call `render_conversion_tick` and `render_write_progress`.
- **R3.** Every string printed by `save_*_to_file` and `_calculate_*_gmpy2` is byte-identical to master `eaed2c4` for the same inputs, pinned by golden-string tests.
- **R4.** A test writes a file with `_PWRITE_CHUNK` patched to 7 bytes and a digit string longer than three chunks and not a multiple of 7, and asserts the file bytes equal header + digits + footer, in both projects.
- **R5.** `_IO_WORKERS` equals `_io_workers(_CPU_COUNT)`, and `_io_workers` is tested at cpu counts 1, 2, 3, 8 and 9, returning 2, 2, 3, 8 and 8.
- **R6.** The four mantissa formatters delegate to `_format_mantissa`, which slices `mantissa[exp : exp + digits]` and is tested for negative input, `exp` of 0, 1 and 2, and `digits` of 0 and 1.
- **R7.** Each `estimate_conversion_time` branch is tested at its threshold (100,000, 1,000,000 and 10,000,000) and one above it, for both backends, with a specific expected float.
- **R8.** The `# noqa: C901` comments on `save_*_to_file`, and the root `CLAUDE.md` line describing them, are removed only if `ruff check --select C901` passes without them, and kept otherwise.
- **V1.** After merge, dispatch `mutation-testing-python.yml` for `pi` and for `e`, and record in the PR or a follow-up comment the survivor count, the total mutant count and the kill rate for each, beside the 2026-11-01 figures (710 and 735 survivors).
- **V2.** Run `python3 pi.py 1000` and `python3 e.py 1000` on the branch and on master, and diff stdout with timing figures masked; the diff is empty.
- **N1.** No change to the π or e algorithms, the precision formulas or the series term counts.
- **N2.** No code moves out of `pi/pi.py` or `e/e.py` into another module.
- **N3.** No mutant exclusion mechanism (`pragma: no mutate`, a cosmic-ray filter or config exclusions).
- **N4.** No change to the other six Python projects or to the Rust crates.
- **N5.** No new dependencies.
