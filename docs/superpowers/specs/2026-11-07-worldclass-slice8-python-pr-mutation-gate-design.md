# Worldclass slice 8: per-PR Python mutation gate on changed lines

- **Status:** Draft
- **Date:** 2026-11-07
- **Depends on:** ai-config `docs/superpowers/specs/2026-11-07-cosmic-ray-prune-design.md` (canonical `cosmic_ray_prune.py`, owned by the ai-config session)

## Context

The 2026-11-03 worldclass audit's Rust half is closed: slices 3-7 built the Rust mutation matrix,
killed its survivors, added a per-PR changed-line gate with 0 missed allowed (slice 5) and made
the monthly sweep hold 0 missed (slice 6, ADR-0042). Python got only slice 2 (pi/e render-helper
survivors). It has no ratchet in either direction.

Premises verified on master `6a67b8c` before design:

1. **The per-PR Python leg evaluates no mutant.** `.github/workflows/mutation-pr.yml:111-120`
   runs `make -C "${dir}" mutants-baseline` for each changed Python dir and nothing else.
2. **Survivors are high.** Issue #184 (latest per-project figures): pi 368 and e 396 on master
   (runs 42157890077, 42157892557, after slice 2); collatz 121, factorial 130, perfect-numbers
   111, amicable 48, fib 46, sq 31 from branch run 41136722047. Roughly 1,250 in all. triangle
   (cosmic-ray config since 2026-11-02) is in the sweep matrix but has never appeared in a
   reported full sweep: the last reported one was 80 cells, 8 projects.
3. **A sweep hold is not shippable yet.** Rust reached "sweep holds 0 missed" only after slice 4
   killed its survivors. Python's ~1,250 must be killed or declared equivalent first, which is
   several slices of test work. The operator approved the decomposition (2026-11-07): this
   slice is the per-PR gate; slices 9..N kill survivors per project, smallest first (sq, fib,
   amicable, perfect-numbers, collatz, factorial, e, pi), triangle measured in the first; a
   final slice makes the Python sweep hold 0.
4. **Equivalent mutants would deadlock a 0-survivor gate.** A PR touching a line that carries an
   equivalent mutant could never go green. The Backlog row "pi/e render helpers: three
   equivalent cosmic-ray survivors" records three per file. Rust escapes through
   `.cargo/mutants.toml` `exclude_re`; Python has nothing.
5. **cosmic-ray 8.7.0 has no usable exclusion or diff filter.** `cr-filter-git` runs a two-dot
   `git diff <branch> .` and needs a git working directory (math runs mutants in a non-git
   `.mutants-tmp` copy); `cr-filter-lines` and `cr-filter-git` mark filtered work `SKIPPED`,
   which `scripts/cosmic_ray_cell_status.py` deliberately treats as red; `cr-filter-pragma` is
   line-granular, and `pi.py:117` holds an equivalent `> 0` mutant beside killable `/` mutants;
   `cosmic-ray.toml` has only `excluded-modules`. Read in the installed 8.7.0 package.

### Measurements

All on cosmic-ray 8.7.0, Python 3.14, Linux `claude`, `git archive` copies of `6a67b8c`.

| Fact                                                         | Population        | Value                                                          |
| ------------------------------------------------------------ | ----------------- | -------------------------------------------------------------- |
| Session rows are 1-based, cols 0-based                       | `sq.py`, `pi.py`  | `sq.py` row 18 = file line 18; `pi.py:117` first `/` at col 22 |
| Mutants on `sq.py:18` (`limit = 10**max_digits`), all KILLED | `sq.py`, one init | 13 of 164                                                      |
| One test-suite run, the per-mutant cost                      | sq, pi, e         | 1.2 s, 4.7 s, 5.6 s                                            |
| `(operator, function, line)` is not unique                   | `pi.py:117`       | `Div_FloorDiv` at cols 22, 32, 39                              |
| `NumberReplacer` emits 2 specs per literal at one position   | `pi.py`           | differ only in `occurrence`                                    |

The three equivalents per file, located on the same inits (pi has 1828 specs, e 1621):

| File:line                                                    | Function                 | Operator                                  | Col | Why equivalent                                            |
| ------------------------------------------------------------ | ------------------------ | ----------------------------------------- | --- | --------------------------------------------------------- |
| `pi.py:96`, `e.py:97` `filled = int(bar_length * pct / 100)` | `render_conversion_tick` | `core/ReplaceBinaryOperator_Div_FloorDiv` | 38  | `int()` of a non-negative quotient: `/` and `//` agree    |
| `pi.py:117`, `e.py:118` `rate = ... if elapsed > 0 else 0`   | `render_write_progress`  | `core/ReplaceComparisonOperator_Gt_NotEq` | 57  | `elapsed` is a monotonic-clock difference, never negative |
| `pi.py:119`, `e.py:120` `eta = ... if done > 0 else 0`       | `render_write_progress`  | `core/ReplaceComparisonOperator_Gt_NotEq` | 47  | `done` is a non-negative byte count                       |

These rows are located by operator and column; that each is a survivor comes from the Backlog
row's runs 42157890077 and 42157892557, re-confirmed at build (V3).

## Design

### Pipeline

```
mutation-pr-detect.sh  -> py_src_dirs (module file changed), py_canary
for dir in py_src_dirs:
  mutation-pr-diff.sh <base> <dir> <tmp>/<dir>.diff
  make -C <dir> mutants-diff DIFF=<abs diff>
     init -> prune equivalents -> prune diff -> (kept 0: green, stop) -> exec
          -> cosmic_ray_cell_status.py --max-survivors 0
```

### Components

1. **`scripts/cosmic_ray_prune.py`**, vendored from ai-config. Subcommands
   `equivalents <session> <toml>` (prints `excluded E of T`) and `diff <session> <diff-file>
<module>` (prints `kept K of T`). It deletes `mutation_specs` and `work_items` rows on a fresh
   session, never writes `SKIPPED`, checks the 8.7.0 schema exactly, and exits 1 leaving the
   session byte-identical on any invalid input. Its contract is the ai-config spec; this slice
   only vendors and calls it.
2. **`<project>/mutants-equivalent.toml`** in all 9 Python projects. Each `[[equivalent]]`
   carries `operator`, `function` (`definition_name`), `line` (stripped source text), `col`
   (`start_pos_col`), `variant` when several specs tie, and a non-empty `reason`; each entry must
   match exactly one spec. pi and e hold the three rows above; the other seven hold none. The
   file is a per-project data parameter, not template output.
3. **Python `Makefile` template** (`scripts/crate_templates/python/Makefile`, rendered into 9
   projects). `mutants` copies `mutants-equivalent.toml` into the work dir and runs `prune
equivalents` after `init`, before the shard step, so the monthly sweep's survivor counts stop
   carrying declared equivalents. A new `mutants-diff` target takes `DIFF`, runs the same recipe
   with `prune diff` after `prune equivalents`, and classifies with `--max-survivors 0`.
4. **`scripts/cosmic_ray_cell_status.py --max-survivors N`.** Red when survivors exceed N, the red
   line naming each `<module_path>:<row> <operator>`. Without the flag, behaviour is unchanged,
   so the sweep's verdict rules do not move. Math-local: it has one consumer (ai-config
   agreed, 2026-11-07).
5. **`scripts/mutation-pr-run-python.sh <base> [--min-killed N] <dir>...`**, a sibling of the
   Rust runner (which is built around cargo-mutants' `exit-code` and `outcomes.json`). Prints one
   verdict line per dir, continues past a red dir, exits 1 when any is red and 2 on bad usage.
6. **`scripts/mutation-pr-detect.sh`** adds `py_src_dirs` (a dir only when `<dir>/<module>.py`
   changed, `<module>` being the dir name with `-` mapped to `_`) and `py_canary`. Existing
   outputs are unchanged: tooling and test-file changes still select every affected `py_dirs`
   entry for the existing baseline step.
7. **`scripts/mutation-pr-diff.sh`** accepts a dir holding `cosmic-ray.toml` as well as one
   holding `Cargo.toml`.

### Verdicts per dir

| Condition                                                          | Verdict                                                  |
| ------------------------------------------------------------------ | -------------------------------------------------------- |
| Selected, but the diff of the dir is empty                         | red, `selected but diff empty`                           |
| Diff, prune, `init` or `exec` fails, or no status line is produced | red, naming the step                                     |
| `kept 0` (comment or blank-line change)                            | green, `0 mutants on changed lines`                      |
| Survivors > 0                                                      | red, one `<module>:<row> <operator>` line each           |
| `--min-killed N` and killed < N                                    | red                                                      |
| Any result not `NORMAL` with `KILLED`/`SURVIVED`                   | red (existing rule, unchanged)                           |
| Timeout                                                            | green: cosmic-ray scores it KILLED, parity with ADR-0042 |

### Canary

A filter bug that keeps 0 forever reads green on every PR. When the PR changes any canary path
(`.github/workflows/mutation-pr.yml`, `scripts/mutation-pr-detect.sh`,
`scripts/mutation-pr-diff.sh`, `scripts/mutation-pr-run-python.sh`,
`scripts/cosmic_ray_prune.py`, `scripts/cosmic_ray_cell_status.py`,
`scripts/crate_templates/python/Makefile`, `sq/sq.py`), the job appends a trailing space to the
single line `    limit = 10**max_digits` of `sq/sq.py` (red unless exactly one line matches),
commits that path alone in the runner checkout and runs
`scripts/mutation-pr-run-python.sh HEAD~1 --min-killed 1 sq`. That line carries 13 killed
mutants, so a broken parser, an off-by-one row or a wrong module match turns red.

### Vendoring

`scripts/cosmic_ray_prune.py` equals ai-config `.claude/scripts/cosmic_ray_prune.py` in every
line but line 2, which reads `# Vendored from ai-config .claude/scripts/cosmic_ray_prune.py @
<sha12>. Edit there, re-sync here.` (the canonical line 2 reads `# Canonical copy. Vendored by:
math/scripts/cosmic_ray_prune.py.`). Re-sync: copy, rewrite line 2 with the sha of the last
ai-config commit touching the file, run `make test`, one math PR per canonical change.

math's ruff `extend-select` is ai-config's `select` plus `C901`, which ai-config's
maintainability gate already bounds at 10; pyright runs `standard` in both and ai-config adds
mypy. A canonical file that passes ai-config's gates passes math's lint.

The drift check is local and lazy: CI cannot read private ai-config, so a canonical change
surfaces on math's next push touching `scripts/` or `tests/` from a machine with
`~/.claude/scripts/`. Accepted: canonical line 2 names math, so whoever edits it knows.

### Testing

Test-first throughout; every case pins an exact derived value.

- `tests/test_cosmic_ray_cell_status.py`: `--max-survivors` green/red/naming, bad N exits 2,
  output without the flag byte-identical to today on existing fixtures.
- `tests/scripts/makefile.bats`: `mutants-diff` exits 2 on unset or unreadable `DIFF` without
  calling cosmic-ray; call order `init`, `equivalents`, `diff`, `exec` (mock log); `kept 0`
  writes the green line and never calls `exec`; `mutants` calls `equivalents` after `init` and
  before the shard, and fails when it fails.
- `tests/scripts/mutation_pr_detect.bats`: `py_src_dirs` and `py_canary` cases.
- `tests/scripts/mutation_pr_diff.bats`: a `cosmic-ray.toml` dir is accepted; a dir with neither
  manifest exits 2.
- `tests/scripts/mutation_pr_run_python.bats` (new): every verdict row above, plus usage.
- `tests/test_mutants_equivalent.py` (new): all 9 tomls exist; with cosmic-ray installed each
  entry resolves to exactly one spec on a fresh init (skip when absent outside CI, fail under
  `CI=true`).
- `tests/test_vendored_prune.py` (new): line 2 form; drift against `~/.claude/scripts/`
  excluding line 2, skipped when absent.
- `tests/test_mutation_workflows.py`: the new steps, their `if:` conditions, `--min-killed 1`,
  `timeout-minutes: 60`.
- `tests/test_crate_uniformity.py`: the template change renders identically into all 9.
- `tests/test_mutation_pr_python_e2e.py` (new, real cosmic-ray on sq, runs only under
  `CI=true` so the push path runs no `cosmic-ray exec`): a trailing-space change to
  `sq.py:18` gives `kept 13 of 164` and green; an untested `if max_digits == 123457: return 0`
  gives red naming the survivor rows.

### Docs

Root `CLAUDE.md` is 29,997 bytes of its 30,000 ceiling, so the new rules (Python PR gate and its
repro, the equivalents file, the vendored-copy rule) replace existing text and detail moves to
ai-config knowledge; every cut fact is first grepped for in ai-config knowledge
([[math-claude-md-trim-can-drop-the-only-copy]]). ADR-0044 records the gate, deletion-based
pruning, the equivalents file and the vendoring.

## Requirements

- **R1.** `scripts/cosmic_ray_prune.py` equals ai-config `.claude/scripts/cosmic_ray_prune.py` at a named commit in every line except line 2, which matches `# Vendored from ai-config .claude/scripts/cosmic_ray_prune.py @ <12 hex>. Edit there, re-sync here.`
- **R2.** The Python `mutants` recipe copies `mutants-equivalent.toml` into the work dir and runs `cosmic_ray_prune.py equivalents` after `cosmic-ray init` and before `cosmic_ray_shard.py`; a non-zero exit fails the recipe.
- **R3.** The Python template has a `mutants-diff` target, listed in `.PHONY` and rendered into all 9 projects, that exits 2 with a message naming `DIFF` when `DIFF` is unset or not a readable file without invoking cosmic-ray, resolves a relative `DIFF` against the invoking directory, runs `init`, `prune equivalents`, `prune diff <session> <DIFF> <module>.py`, and on `kept 0` prints `green: <dir> — 0 mutants on changed lines` (also to `STATUS_OUT` when set) and exits 0 without `cosmic-ray exec`; otherwise it runs `exec` and `cosmic_ray_cell_status.py --max-survivors 0`.
- **R4.** Each of the 9 Python projects has `mutants-equivalent.toml`; pi and e each hold exactly the 3 entries of the equivalents table (operator, function, stripped line, col, a non-empty reason); the other 7 hold no `[[equivalent]]` entry.
- **R5.** `cosmic_ray_cell_status.py --max-survivors N` reports red when survivors exceed N, naming each survivor as `<module_path>:<start_pos_row> <operator_name>`, exits 2 when N is not a plain non-negative decimal, and without the flag produces output byte-identical to today's.
- **R6.** `scripts/mutation-pr-detect.sh` prints `py_src_dirs=<sorted dirs>`, selecting a Python dir only when `<dir>/<module>.py` changed (`<module>` is the dir name with `-` replaced by `_`), and `py_canary=true|false`, true exactly when a canary path listed in the Canary section changed; its existing outputs are unchanged.
- **R7.** `scripts/mutation-pr-diff.sh` accepts a dir containing `Cargo.toml` or `cosmic-ray.toml` and exits 2 when it contains neither.
- **R8.** `scripts/mutation-pr-run-python.sh <base-ref> [--min-killed N] <dir>...` implements every row of the verdicts table, prints one verdict line per dir to stdout, continues past a red dir, exits 1 when any dir is red, 2 on bad usage or no dirs, else 0.
- **R9.** `mutation-pr.yml` runs `scripts/mutation-pr-run-python.sh "origin/${GITHUB_BASE_REF}"` over `py_src_dirs` in a step conditioned on `py_src_dirs` being non-empty, runs the canary as specified when `py_canary` is true, keeps the existing baseline step unchanged, and keeps `timeout-minutes: 60`.
- **R10.** Each test file named in the Testing section exists or is extended with the cases listed there.
- **R11.** `tests/test_mutation_pr_python_e2e.py` asserts `kept 13 of 164` and green for the `sq.py:18` trailing-space change and red naming survivors for the untested-branch change; it runs only when `CI=true`.
- **R12.** `scripts/pre-push` runs `tests/test_mutants_equivalent.py` when a pushed commit changes a `mutants-equivalent.toml` or a Python project's module file, as it runs `tests.test_mutants_exclusions` for Rust.
- **R13.** `docs/adr/0044-*.md` records the per-PR changed-line gate, deletion-based pruning, the equivalents file and the vendoring, and `docs/adr/README.md` lists it.
- **R14.** Root `CLAUDE.md` states the Python PR gate with its local repro, the equivalents-file rule and the vendored-copy re-sync rule, and stays at or under 30,000 bytes.
- **R15.** `docs/superpowers/README.md` gains this slice's plan row and Backlog rows "Python survivor kills, slices 9..N" and "Python sweep holds 0 survivors", no longer contains the row "pi/e render helpers: three equivalent cosmic-ray survivors", and its "Mutation score threshold" row names Python only.
- **R16.** `.github/workflows/scripts.yml`'s install step adds `cosmic-ray==8.7.0` and `hypothesis==6.168.5` (the versions every other install site pins, so `tests/test_tool_pins.py` stays green), because `tests/test_mutants_equivalent.py` and `tests/test_mutation_pr_python_e2e.py` fail under `CI=true` without cosmic-ray and the e2e run executes `sq`'s tests, which import hypothesis.
- **V1.** Positive control before the slice PR is marked ready: a throwaway draft PR on the slice branch adds an untested branch to `sq/sq.py`; `mutation-pr` is red naming the survivor; the PR is closed and its branch deleted.
- **V2.** This slice's PR changes canary paths, so the canary runs green with at least 1 killed, shown in the step summary.
- **V3.** On this slice's PR, each pi and e equivalent matches exactly one spec on a fresh init and was a survivor in the last full run; and whether `occurrence` shifts after an unrelated edit is confirmed or refuted, and the result reported to the ai-config session.
- **V4.** In a change coordinated with the ai-config session, `math-testing-policy.md` § Mutation testing and `math-ci.md` § Workflow table describe the Python PR gate.
- **V5.** At vendoring time, `tests/test_vendored_prune.py` runs on `claude` against `~/.claude/scripts/cosmic_ray_prune.py` and passes, not skipped.
- **N1.** The Python sweep's verdict rules do not change: `mutation-testing-python.yml` and `scripts/mutation-python-cell.sh` never pass `--max-survivors`.
- **N2.** The Rust PR path does not change: `scripts/mutation-pr-run.sh` and `scripts/mutation-classify.sh` are not modified.
- **N3.** `scripts/cosmic_ray_prune.py` is not edited in math beyond line 2.
- **N4.** Nothing on the local push path runs `cosmic-ray exec`.
- **N5.** No survivor is killed in this slice other than by a test the gate itself requires on a changed line.
