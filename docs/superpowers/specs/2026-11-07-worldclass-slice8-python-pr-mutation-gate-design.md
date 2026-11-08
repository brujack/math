# Worldclass slice 8: per-PR Python mutation gate on changed lines

- **Status:** Draft (round 1 dispositions recorded; round 2 pending)
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
| Mutants kept on a real pi/e refactor (c7c8f6f, math#201, 108 changed rows each) | `pi.py`, `e.py` at c7c8f6f (Step 8 goal-fit lens) | 613 of 1830 and 613 of 1623; about 105 min serial |
| Survivor-bearing lines | pi run 42157890077 (master 70ea2a9), e run 42157892557 (Step 8 ergonomics lens) | pi 87 of 609 code lines, e 91 of 601 |
| Recent pi.py PRs whose changed lines held a survivor | last 6 pi.py commits since 2026-09-01, approximate (line drift) | 3 of 6 |

The three equivalents per file, located on the same inits (pi has 1828 specs, e 1621):

| File:line                                                    | Function                 | Operator                                  | Col | Why equivalent                                            |
| ------------------------------------------------------------ | ------------------------ | ----------------------------------------- | --- | --------------------------------------------------------- |
| `pi.py:96`, `e.py:97` `filled = int(bar_length * pct / 100)` | `render_conversion_tick` | `core/ReplaceBinaryOperator_Div_FloorDiv` | 38  | `int()` of a non-negative quotient: `/` and `//` agree    |
| `pi.py:117`, `e.py:118` `rate = ... if elapsed > 0 else 0`   | `render_write_progress`  | `core/ReplaceComparisonOperator_Gt_NotEq` | 57  | `elapsed` is a monotonic-clock difference, never negative |
| `pi.py:119`, `e.py:120` `eta = ... if done > 0 else 0`       | `render_write_progress`  | `core/ReplaceComparisonOperator_Gt_NotEq` | 47  | `done` is a non-negative byte count                       |

These rows are located by operator and column; that each is a survivor comes from the Backlog
row's runs 42157890077 and 42157892557, re-confirmed at build (V3).


## Design

### The rule (operator, 2026-11-07)

Edit a line and you own its mutants. Every survivor on a changed new-side line is red until a test
kills it or `mutants-equivalent.toml` declares it equivalent with a reason. This is the Rust rule
already in root `CLAUDE.md` ("every missed mutant on a changed line gets a killing test, glue
included"). No survivor is grandfathered: the gate keys on changed new-side lines, so every
survivor it reports sits on a line whose text the PR changed, and a text-keyed baseline would
exempt nothing. Measured cost: 3 of the last 6 pi.py PRs touched a survivor-bearing line, so old
survivors get paid down as a side effect and slices 9..N shrink.

### Pipeline

```
mutation-py-plan (one job)
  detect -> py_src_dirs, py_canary; base = git merge-base origin/<base> HEAD (job output)
  for dir: mutation-pr-diff.sh base dir d.diff; make -C dir mutants-diff-plan DIFF=d.diff
           -> `kept K of T (lines L)` -> unit list {dir, k, n}, n = min(10, max(1, ceil(K/150)))
mutation-py (matrix over units)
  mutation-pr-diff.sh base dir d.diff; make -C dir mutants-diff DIFF=d.diff MUTANT_SHARD=k/n
     init -> prune equivalents -> prune diff -> shard -> exec -> cell_status --max-survivors 0
mutation-py-canary (when py_canary)
mutation-rs (the existing job renamed: Python baselines, Rust loop, Rust canary; steps unchanged)
mutation-pr (aggregator; keeps the required check's name)
  needs all four, if: always(); green only when every job is success or legitimately skipped
  and every planned unit has a green status file
```

The required status check on `master` is the context `mutation-pr` (classic branch protection,
`gh api repos/brujack/math/branches/master/protection`). The aggregator keeps that job name, so the
protection needs no change; the old single job becomes `mutation-rs`.

### Components

1. **`scripts/cosmic_ray_prune.py`**, vendored from ai-config (spec @ `3c810293`). `equivalents
   <session> <toml>` prints `excluded E of T`; `diff <session> <diff-file> <module>` prints
   `kept K of T (lines L)`. Both delete rows from a fresh session, never write `SKIPPED`, check
   the 8.7.0 schema exactly, and on invalid input exit 1 with the session byte-identical. `diff`
   exits 1 when `<module>` matches no spec's `module_path`.
2. **`<project>/mutants-equivalent.toml`** in all 9 Python projects. Each `[[equivalent]]` carries
   `operator`, `function` (`""` for module level), `row`, `col`, `line` (stripped text), `variant`
   when more than one spec matches (a `NumberReplacer` pair: 0 = +1, 1 = -1), and a non-empty
   `reason` (ai-config spec @ `f4f7fa49`). `row` is mandatory (operator, 2026-11-07): it stops a
   declared variant sliding onto a new, unreviewed mutant in a group of identical lines. The cost
   is accepted: inserting or deleting lines above an entry makes it exit 1 on that PR's own gate
   until its `row` is updated from the candidate listing. Entries
   are authored by the route the ai-config spec defines: write a skeleton entry, run `prune
   equivalents` on a fresh local init, and copy the fields from the candidate listing its error
   prints. pi and e hold the three rows of the equivalents table; the other seven hold none. The
   file is a per-project data parameter, not template output.
3. **Python `Makefile` template** (rendered into 9 projects).
   - `mutants` copies `mutants-equivalent.toml` into the work dir and runs `prune equivalents`
     after `init` and before the shard step. Until the final "sweep holds 0" slice this changes no
     sweep verdict; it removes declared equivalents from the #184 counts and makes a stale entry
     fail loudly.
   - `mutants-diff-plan` (needs `DIFF`) runs `init`, `prune equivalents` and `prune diff` and
     prints the prune lines, with no `exec`.
   - `mutants-diff` (needs `DIFF`, optional `MUTANT_SHARD`) runs the same, then the shard, `exec`
     and `cell_status --max-survivors 0`. It writes `cosmic-ray-diff-session.sqlite` and
     `mutants-diff-report.txt`, never the full run's `cosmic-ray-session.sqlite` or
     `mutants-report.txt`; `mutants-clean` removes both pairs.
4. **`scripts/cosmic_ray_cell_status.py --max-survivors N`.** Red when survivors exceed N. With the
   flag, each survivor prints as `<module>:<row> col <c> <operator> function "<f>"`, the fields an
   equivalents entry needs, followed by its mutant diff from `work_results.diff` (ai-config spec
   V4). Without the flag, output is byte-identical to today's, and
   `--survivors` keeps its current line format, so the sweep's survivor report is unchanged.
5. **`scripts/mutation-pr-plan-python.sh <base-sha> <dir>...`** builds each dir's diff, runs
   `mutants-diff-plan`, and writes the unit matrix plus a per-dir plan line: red for a failed step
   or `lines 0`, green `0 mutants on changed lines` for `kept 0` with `lines` > 0 (no units), else
   one unit per shard.
6. **`scripts/mutation-pr-verdict-python.sh <plan-file> <status-dir>`** prints one line per dir:
   the plan's red or green line, or, for a dir with units, red when any unit's status is missing
   or red, naming each survivor and the local repro
   (`scripts/mutation-pr-diff.sh origin/master <dir> /tmp/d.diff && make -C <dir> mutants-diff DIFF=/tmp/d.diff`),
   else green. Exits 1 when any dir is red.
7. **`scripts/mutation-pr-detect.sh`** adds `py_src_dirs` (a dir only when `<dir>/<module>.py`
   changed, `<module>` the dir name with `-` mapped to `_`) and `py_canary`. Existing outputs are
   unchanged.
8. **`scripts/mutation-pr-diff.sh`** accepts a dir holding `cosmic-ray.toml` as well as
   `Cargo.toml`, and runs git with `-c diff.suppressBlankEmpty=false`.

### Verdicts per dir

Rows are evaluated in order; the first that applies decides.

| # | Condition | Verdict |
| --- | --- | --- |
| 1 | Diff, prune, `init`, shard or `exec` fails, or a planned unit has no status file | red, naming the step or unit |
| 2 | `lines 0` for a selected dir (no changed line in the module section) | red, `no changed module lines` |
| 3 | `--min-killed N` (canary only) and killed < N, where `kept 0` counts as killed 0 | red |
| 4 | Any result not `NORMAL` with `KILLED`/`SURVIVED` | red (existing rule) |
| 5 | Survivors > 0 | red, one full-key line per survivor plus the repro |
| 6 | `kept 0` with `lines` > 0 (comment or blank-line change) | green, `0 mutants on changed lines` |
| 7 | Otherwise | green; timeouts count as KILLED, parity with ADR-0042 |

Row 2 follows the ai-config contract: a selected module whose diff section is missing is a broken
diff, not a no-op. A pure-deletion edit to a module is therefore red; deleting code that carries
mutants is rare enough to accept.

### Canary

`mutation-py-canary` runs when the PR changes a canary path: `.github/workflows/mutation-pr.yml`,
`scripts/mutation-pr-detect.sh`, `scripts/mutation-pr-diff.sh`,
`scripts/mutation-pr-plan-python.sh`, `scripts/mutation-pr-verdict-python.sh`,
`scripts/cosmic_ray_prune.py`, `scripts/cosmic_ray_cell_status.py`,
`scripts/crate_templates/python/Makefile`, `sq/sq.py` or `sq/mutants-equivalent.toml`. It installs
the Python toolchain itself, appends a trailing space to the single line `    limit = 10**max_digits`
of `sq/sq.py` (red unless exactly one line matches), commits that path alone in the runner
checkout, and runs plan, one unsharded `mutants-diff` and the verdict with `--min-killed 1`. That
line carries 13 killed mutants, and row 3 makes a filter that keeps nothing red.

### Install conditions

Every job that runs cosmic-ray installs the pinned Python toolchain on its own condition:
`mutation-py-plan` and `mutation-py` when `py_src_dirs` is non-empty, `mutation-py-canary` when
`py_canary` is true, `mutation-rs` on `has_py` as today. A canary-only PR (for example a vendored
re-sync touching only `scripts/cosmic_ray_prune.py`) therefore has cosmic-ray where it runs.

### Equivalents file changes

A PR changing only a `mutants-equivalent.toml` selects no dir. `scripts.yml` gains the path
`*/mutants-equivalent.toml` and installs cosmic-ray (R16), so `tests/test_mutants_equivalent.py`
runs in CI and a stale or ambiguous entry fails the PR instead of turning 10 sweep cells red the
next month. A module edit that breaks an entry fails that PR's own gate, because `mutants-diff`
runs `prune equivalents` first. Whether a declared mutant is truly equivalent is a review
judgement on its `reason`; no tool decides it.

### Vendoring

`scripts/cosmic_ray_prune.py` equals ai-config `.claude/scripts/cosmic_ray_prune.py` in every line
but line 2, which reads `# Vendored from ai-config .claude/scripts/cosmic_ray_prune.py @ <sha12>.
Edit there, re-sync here.` Re-sync: copy, rewrite line 2 with the sha of the last ai-config commit
touching the file, run `make test`; one math PR per canonical change. Such a PR touches a canary
path, so the canary proves the new copy on real cosmic-ray.

math's ruff `extend-select` is ai-config's `select` plus `C901`, which ai-config's maintainability
gate bounds at 10; pyright runs `standard` in both and ai-config adds mypy.

The drift check is local and lazy: CI cannot read private ai-config. Accepted: canonical line 2
names math, so whoever edits it knows.

### Known gap, not closed here

A PR that weakens or deletes tests in `test_<module>.py` creates survivors on unchanged lines and is
never gated; the Rust gate has the same hole. The monthly sweep sees it. A Backlog row records it
for both languages.

### Testing

Test-first; every case pins an exact derived value.

- `tests/test_cosmic_ray_cell_status.py`: `--max-survivors` green/red, the full-key survivor line,
  bad N exits 2, output and `--survivors` file without the flag byte-identical to today.
- `tests/scripts/makefile.bats`: `mutants-diff` and `mutants-diff-plan` exit 2 on unset or
  unreadable `DIFF` without calling cosmic-ray; call order `init`, `equivalents`, `diff`, shard,
  `exec` (mock log); `mutants-diff` writes only the diff session and report names; `mutants`
  calls `equivalents` after `init` and before the shard and fails when it fails; `mutants-clean`
  removes both pairs.
- `tests/scripts/mutation_pr_detect.bats`: `py_src_dirs` and `py_canary` cases, one per canary path.
- `tests/scripts/mutation_pr_diff.bats`: a `cosmic-ray.toml` dir is accepted; neither manifest
  exits 2; the git call carries `diff.suppressBlankEmpty=false`.
- `tests/scripts/mutation_pr_plan_python.bats` (new): `n` for K = 0, 1, 150, 151, 1500, 1501;
  plan lines for `lines 0`, `kept 0`, a prune failure.
- `tests/scripts/mutation_pr_verdict_python.bats` (new): every verdict row, including `kept 0`
  with `--min-killed 1` red and a planned unit with no status file red.
- `tests/test_mutants_equivalent.py` (new): all 9 tomls exist; with cosmic-ray installed each
  entry resolves on a fresh init (skip when absent outside CI, fail under `CI=true`).
- `tests/test_vendored_prune.py` (new): line 2 form; drift against `~/.claude/scripts/` excluding
  line 2, skipped when absent.
- `tests/test_mutation_workflows.py`: the five jobs, their `needs` and `if:` conditions, the
  aggregator named `mutation-pr` with `if: always()`, each job's install condition, matrix
  `timeout-minutes: 30`, the canary's `--min-killed 1`.
- `tests/test_crate_uniformity.py`: the template change renders identically into all 9.
- `tests/test_mutation_pr_python_e2e.py` (new, real cosmic-ray on sq, only under `CI=true`): the
  `sq.py:18` trailing-space change gives `kept 13 of 164 (lines 1)` and green; an untested
  `if max_digits == 123457: return 0` gives red with full-key survivor lines.

### Docs

Root `CLAUDE.md` is 29,997 bytes of its 30,000 ceiling, so the new rules (Python PR gate and its
repro, the equivalents file, the vendored-copy rule, the `mutation-rs` rename) replace existing
text; detail moves to ai-config knowledge, and every cut fact is first grepped for there. ADR-0044
records the gate, the strict rule, deletion-based pruning, the equivalents file, sharding and the
vendoring.

## Requirements

- **R1.** `scripts/cosmic_ray_prune.py` equals ai-config `.claude/scripts/cosmic_ray_prune.py` at a named commit in every line except line 2, which matches `# Vendored from ai-config .claude/scripts/cosmic_ray_prune.py @ <12 hex>. Edit there, re-sync here.`
- **R2.** The Python `mutants` recipe copies `mutants-equivalent.toml` into the work dir and runs `cosmic_ray_prune.py equivalents` after `cosmic-ray init` and before `cosmic_ray_shard.py`; a non-zero exit fails the recipe.
- **R3.** The Python template has `mutants-diff-plan` and `mutants-diff` targets, listed in `.PHONY` and rendered into all 9 projects; each exits 2 with a message naming `DIFF` when `DIFF` is unset or not a readable file without invoking cosmic-ray, and resolves a relative `DIFF` against the invoking directory; `mutants-diff-plan` runs `init`, `prune equivalents` and `prune diff <session> <DIFF> <module>.py` and no `exec`; `mutants-diff` additionally applies `MUTANT_SHARD` when set, runs `exec` and `cosmic_ray_cell_status.py --max-survivors 0`, and writes only `cosmic-ray-diff-session.sqlite` and `mutants-diff-report.txt` in the project dir.
- **R4.** Each of the 9 Python projects has `mutants-equivalent.toml`; pi and e each hold exactly the 3 entries of the equivalents table, each with `operator`, `function`, `row`, `col`, `line` and a non-empty `reason`, and no `of`; the other 7 hold no `[[equivalent]]` entry.
- **R5.** `cosmic_ray_cell_status.py --max-survivors N` reports red when survivors exceed N, printing each as `<module>:<row> col <col> <operator> function "<definition_name>"` followed by its `work_results.diff`, exits 2 when N is not a plain non-negative decimal, and without the flag produces stdout and `--survivors` output byte-identical to today's.
- **R6.** `scripts/mutation-pr-detect.sh` prints `py_src_dirs=<sorted dirs>`, selecting a Python dir only when `<dir>/<module>.py` changed (`<module>` is the dir name with `-` replaced by `_`), and `py_canary=true|false`, true exactly when a canary path listed in the Canary section changed; its existing outputs are unchanged.
- **R7.** `scripts/mutation-pr-diff.sh` accepts a dir containing `Cargo.toml` or `cosmic-ray.toml`, exits 2 when it contains neither, and passes `-c diff.suppressBlankEmpty=false` to git.
- **R8.** `scripts/mutation-pr-plan-python.sh` writes one plan line per dir and the unit matrix with `n = min(10, max(1, ceil(K / 150)))` shards per dir with `K` > 0, and no unit for a dir with `K` = 0 or a red plan line.
- **R9.** `scripts/mutation-pr-verdict-python.sh` applies the verdict table's rows in order, prints one verdict line per dir with full-key survivor lines and the local repro on red, accepts `--min-killed N`, exits 1 when any dir is red, 2 on bad usage, else 0.
- **R10.** `mutation-pr.yml` has jobs `mutation-py-plan`, `mutation-py` (matrix over the plan's units, `timeout-minutes: 30`), `mutation-py-canary`, `mutation-rs` (the former `mutation-pr` job's steps, unchanged except its name) and an aggregator named `mutation-pr` with `needs` on all four and `if: always()` that fails unless each needed job succeeded or was skipped for its own condition and the verdict script exits 0; the base commit is the plan job's merge-base output, used by every Python job.
- **R11.** Each job that runs cosmic-ray installs the pinned Python toolchain on its own condition as the Install conditions section states, so a PR touching only a canary path has cosmic-ray in `mutation-py-canary`.
- **R12.** Each test file named in the Testing section exists or is extended with the cases listed there.
- **R13.** `tests/test_mutation_pr_python_e2e.py` asserts `kept 13 of 164 (lines 1)` and green for the `sq.py:18` trailing-space change and red with full-key survivor lines for the untested-branch change; it runs only when `CI=true`.
- **R14.** `scripts/pre-push` runs `tests/test_mutants_equivalent.py` when a pushed commit changes a `mutants-equivalent.toml` or a Python project's module file, as it runs `tests.test_mutants_exclusions` for Rust.
- **R15.** `.github/workflows/scripts.yml` adds `*/mutants-equivalent.toml` to its `paths` and adds `cosmic-ray==8.7.0` and `hypothesis==6.168.5` to its install step, at the versions every other install site pins.
- **R16.** `docs/adr/0044-*.md` records the strict changed-line rule, deletion-based pruning, the equivalents file, sharding with the `mutation-pr` aggregator, and the vendoring, and `docs/adr/README.md` lists it.
- **R17.** Root `CLAUDE.md` states the Python PR gate with its local repro, the equivalents-file rule, the vendored-copy re-sync rule and the `mutation-rs` job name, and stays at or under 30,000 bytes.
- **R18.** `docs/superpowers/README.md` gains this slice's plan row and Backlog rows "Python survivor kills, slices 9..N", "Python sweep holds 0 survivors" and "PR mutation gates miss test-only weakening (Rust and Python)", "Python sweep survivor report lacks col and diff" (for slice 9's entry authoring), no longer contains the row "pi/e render helpers: three equivalent cosmic-ray survivors", and its "Mutation score threshold" row names Python only.
- **V1.** Positive control before the slice PR is marked ready: a throwaway draft PR on the slice branch adds an untested branch to `sq/sq.py`; `mutation-pr` is red naming the survivor with its full key; the PR is closed and its branch deleted.
- **V2.** This slice's PR changes canary paths, so `mutation-py-canary` runs green with at least 1 killed, shown in the step summary.
- **V3.** On this slice's PR: each pi and e equivalent resolves to exactly one spec on a fresh init and was a survivor in the last full run; whether `occurrence` shifts after an unrelated edit is confirmed or refuted; whether the `+1` `NumberReplacer` variant has the lower `occurrence` is confirmed or refuted from `work_results.diff`; results go to the ai-config session.
- **V4.** In a change coordinated with the ai-config session, `math-testing-policy.md` § Mutation testing and `math-ci.md` § Workflow table describe the Python PR gate and the `mutation-rs` rename.
- **V5.** At vendoring time, `tests/test_vendored_prune.py` runs on `claude` against `~/.claude/scripts/cosmic_ray_prune.py` and passes, not skipped.
- **V6.** Replay c7c8f6f (math#201) on `claude`: its pi and e diffs plan to `n` = 5 shards each (613 kept), and one shard of each finishes inside 30 minutes, timed.
- **N1.** The Python sweep's verdict rules do not change: `mutation-testing-python.yml` and `scripts/mutation-python-cell.sh` never pass `--max-survivors`, and the sweep's `--survivors` line format does not change.
- **N2.** The Rust PR path does not change: `scripts/mutation-pr-run.sh` and `scripts/mutation-classify.sh` are not modified, and the `mutation-rs` job's steps match the former `mutation-pr` job's.
- **N3.** `scripts/cosmic_ray_prune.py` is not edited in math beyond line 2.
- **N4.** Nothing on the local push path runs `cosmic-ray exec`.
- **N5.** No survivor is grandfathered: no committed survivor baseline file and no base-commit survivor run.
- **N6.** Branch protection on `master` is not changed.

## Multi-Lens Review

Reviewed at commit: `041ff3d` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: Worth building; premise verified (`mutation-pr.yml:111-120` runs only `mutants-baseline`, an unmutated run). Load-bearing flaw: all dirs ran serially in one 60-minute job; c7c8f6f (math#201) keeps 613 mutants in each of pi and e, about 105 minutes, and every pi.py commit since 2026-08-01 also touched e.py; a cap kill prints no verdict. Also: test-only weakening is never gated; `prune equivalents` in the sweep changes no verdict until the final slice.
Assumption: kept mutants × per-mutant cost fit the job budget for real PRs; settled by timing a c7c8f6f replay.
Disposition: Addressed (operator, 2026-11-07) — matrix over shards with `n = min(10, max(1, ceil(K/150)))` and a `mutation-pr` aggregator (R8, R10); V6 times the c7c8f6f replay; test-only gap named and Backlogged (R18); sweep equivalents' role stated in Components 3.

### Ergonomics

Finding: A red line lacked the fields an equivalents entry needs; 3 of the last 6 pi.py PRs would have gone red on survivors already on the edited lines (pi survivors on 87 of 609 lines, e on 91 of 601). Runtime has no ceiling plan. The text-keyed equivalents entry breaks on reformatting.
Assumption: PRs rarely land on survivor-bearing lines; measured roughly half do for pi.py.
Disposition: Addressed (operator, 2026-11-07) — operator chose the strict rule (A, 2026-11-07): edit a line, own its mutants; red lines now print the full key and the repro (R5, R9); runtime per Goal-Fit. Reformat fragility accepted: entries fail loudly on that PR's own gate.

### Risk

Finding: (1) No order between `kept 0` green and `--min-killed`, so the canary could pass a filter that keeps nothing. (2) The ai-config `L = 0` red was replaced by a weaker "dir diff empty" check. (3) Canary-only PRs never install cosmic-ray. (4) An equivalents-only PR gets no CI check, and a stale entry turns 10 sweep cells red. (5) A local `mutants-diff` overwrites the full run's session and report. Sweep ordering (equivalents before shard) verified sound; pi's three equivalents each match exactly one spec.
Assumption: changed-line mutants fit one 60-minute job; same as Goal-Fit.
Disposition: Addressed (operator, 2026-11-07) — ordered verdict table with `kept 0` counting as killed 0 (row 3); `lines 0` red per the ai-config contract (row 2); per-job install conditions (R11); `scripts.yml` path and install (R15); distinct diff output names (R3).

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
