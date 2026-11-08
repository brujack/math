# Worldclass slice 8: per-PR Python mutation gate on changed lines

- **Status:** Approved
- **Approved:** 2026-11-07
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

| File:line | Function | Operator | Col | `above` | Why equivalent |
| --- | --- | --- | --- | --- | --- |
| `pi.py:96`, `e.py:97` `filled = int(bar_length * pct / 100)` | `render_conversion_tick` | `core/ReplaceBinaryOperator_Div_FloorDiv` | 38 | `bar_length = 30` | `int()` of a non-negative quotient: `/` and `//` agree |
| `pi.py:117`, `e.py:118` `rate = ... if elapsed > 0 else 0` | `render_write_progress` | `core/ReplaceComparisonOperator_Gt_NotEq` | 57 | `bytes_done = min(done * chunk, total_bytes)` | `elapsed` is a `time.monotonic()` difference, never negative |
| `pi.py:119`, `e.py:120` `eta = ... if done > 0 else 0` | `render_write_progress` | `core/ReplaceComparisonOperator_Gt_NotEq` | 47 | `remaining = total_chunks - done` | `done` is a non-negative byte count |

These rows are located by operator and column, `above` measured on `origin/master` `a7bb16e`; that each is a survivor comes from the Backlog
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
           (baseline first) -> `kept K of T (lines L)`
           -> units [{dir, k, n}], n = min(10, max(1, ceil(K/150))); plan lines; units JSON output
mutation-py (matrix over units; if: units != '[]')
  mutation-pr-diff.sh base dir d.diff; make -C dir mutants-diff DIFF=d.diff MUTANT_SHARD=k/n
     baseline -> init -> prune equivalents -> prune diff -> shard -> exec
     -> cell_status --max-survivors 0 -> status/<dir>-<k> in artifact
        mutants-pr-status-<dir>-<k> (overwrite: true)
mutation-py-canary (if: py_canary == 'true'; diff base HEAD~1)
mutation-rs (the existing job renamed: Python baselines, Rust loop, Rust canary; steps unchanged)
mutation-pr (aggregator; keeps the required check's name)
  needs all four, if: always()
  verdict --expected-dirs "<py_src_dirs>" plan status-dir
```

The required status check on `master` is the context `mutation-pr` (classic branch protection;
`gh api repos/brujack/math/branches/master/protection` returned contexts `["secret-scan",
"mutation-pr"]`, app_id 15368). The aggregator keeps that job id, so the protection needs no
change; the old single job becomes `mutation-rs`.

**Aggregator rule.** Green only when all of these hold: `mutation-rs` and `mutation-py-plan` are
`success`; `mutation-py` is `success`, or `skipped` while the plan's `units` output is exactly
`[]`; `mutation-py-canary` is `success`, or `skipped` while `py_canary` is not `true`; and the
verdict script exits 0. A skip is accepted only when its own `if:` expression, re-evaluated in the
aggregator, explains it. `cancelled` and `failure` are always red. Earlier attempts' artifacts stay
visible on a re-run (memory `ai-config-rerun-failed-keeps-prior-attempt-artifacts`), so a stale
green status file can never stand alone: the job result must also be `success`.

### Components

1. **`scripts/cosmic_ray_prune.py`**, vendored from ai-config (spec approved at `96ffa257`).
   `equivalents <session> <toml> --full-run` prints `excluded E of T`; `equivalents <session> <toml>
   --diff <diff-file> --toml-path <path>` prints `excluded E of T (re-confirm: diff, R on changed
   lines)`; any other mode combination exits 2. `diff <session> <diff-file> <module>` prints
   `kept K of T (lines L)`.
   Both delete rows from a fresh session, never write `SKIPPED`, check the 8.7.0 schema exactly,
   and on invalid input exit 1 with the session byte-identical. `diff` exits 1 when `<module>`
   matches no spec's `module_path`.
2. **`<project>/mutants-equivalent.toml`** in all 9 Python projects. Each `[[equivalent]]` carries
   `operator`, `function` (`""` for module level), `line` (stripped text), `col`, `above` (stripped
   text of the nearest non-blank line above the mutant's row), `row` only when that group spans more
   than one row (rejected otherwise), `variant` only when more than one spec matches (a
   `NumberReplacer` pair: 0 = +1, 1 = -1, within one row and col), and a non-empty `reason`
   (operator ruling, 2026-11-07, superseding mandatory `row`). The layout is strict: only
   `[[equivalent]]` headers at column 0, no other tables or top-level keys. **Re-confirm rule**
   (operator, 2026-11-07): in `--diff` mode an entry whose mutant sits on a changed line (row-range
   intersection) exits 1 unless the same diff changes one of that entry's own lines (its header or
   key/value lines; blank and comment lines never count). Editing a line therefore means owning its
   declared equivalents too: the author re-confirms the entry in the same PR. Inserting lines elsewhere in the
   file does not break an entry; editing or deleting the line or the line above it does, and the
   entry then exits 1 on that PR's own gate. A line moved to a new place gets a new `above` and so
   matches 0 instead of silently matching the moved mutant. Entries are authored by the route the
   ai-config spec defines: write a skeleton entry, run `prune equivalents` on a fresh local init,
   and copy the fields from the candidate listing its error prints. pi and e hold the three rows
   of the equivalents table, all one-row groups, so none carries `row`; the other seven hold none.
   The file is a per-project data parameter, not template output.
3. **Python `Makefile` template** (rendered into 9 projects).
   - `mutants` copies `mutants-equivalent.toml` into the work dir and runs `prune equivalents
     --full-run` after `init` and before the shard step. Until the final "sweep holds 0" slice this changes no
     sweep verdict; it removes declared equivalents from the #184 counts and makes a stale entry
     fail loudly.
   - `mutants-diff-plan` (needs `DIFF`; depends on `mutants-baseline`) runs `init`, `prune
     equivalents --diff "$DIFF" --toml-path mutants-equivalent.toml` (the same diff file `prune
     diff` reads; the path is the `--relative=<dir>/` form the diff carries, matched as a string,
     never opened) and `prune diff`, and prints the prune lines, with no `exec`.
   - `mutants-diff` (needs `DIFF`, optional `MUTANT_SHARD`; depends on `mutants-baseline`) runs the
     same, then the shard, `exec` and `cell_status --max-survivors 0`. It writes
     `cosmic-ray-diff-session.sqlite` and `mutants-diff-report.txt`, never the full run's
     `cosmic-ray-session.sqlite` or `mutants-report.txt`; `mutants-clean` removes both pairs.
   - The baseline dependency is what makes a broken test environment red: without it, a missing
     package makes every mutant's test command fail, cosmic-ray scores each `KILLED`, and the dir
     reads green with 0 survivors. Each CI leg installs its own toolchain, so each leg baselines
     itself.
4. **`scripts/cosmic_ray_cell_status.py --max-survivors N`.** Red when survivors exceed N. With the
   flag, each survivor prints as `<module>:<row> col <c> <operator> function "<f>"`, the fields an
   equivalents entry needs, followed by its mutant diff from `work_results.diff` (ai-config spec
   V4). Without the flag, stdout is byte-identical to today's and `--survivors` keeps its current
   line format, so the sweep's survivor report is unchanged.
5. **`scripts/mutation-pr-plan-python.sh <base-sha> [<dir>...]`** accepts zero dirs, writing an
   empty plan and units `[]`, so the plan job always emits `units`. It builds each dir's diff, runs
   `mutants-diff-plan`, and writes the units JSON plus one plan line per dir: red for a failed
   step (baseline, diff, prune) or `lines 0`; green `0 mutants on changed lines` for `kept 0` with
   `lines` > 0 (no units); else one unit per shard. Every failing step's stderr, including
   prune's candidate listing, is appended to the plan line's detail and to `$GITHUB_STEP_SUMMARY`.
6. **`scripts/mutation-pr-verdict-python.sh --expected-dirs "<dirs>" [--min-killed N] <plan-file>
   <status-dir>`** prints one line per dir. It is red for any dir in `--expected-dirs` without a
   plan line, or a plan line for a dir not expected; otherwise the plan's red or green line, or,
   for a dir with units, red when any unit's status is missing or red, naming each survivor and
   the local repro for that unit, else green. The repro is
   `d=$(mktemp) && scripts/mutation-pr-diff.sh origin/master <dir> "$d" && make -C <dir> mutants-diff DIFF="$d" MUTANT_SHARD=<k>/<n>`.
   Exits 1 when any dir is red, 2 on bad usage.
7. **`scripts/mutation-pr-detect.sh`** adds `py_src_dirs` and `py_canary`. A dir is selected only
   when `git diff --numstat --no-renames` shows more than 0 added lines in `<dir>/<module>.py` (`<module>` the
   dir name with `-` mapped to `_`). A pure deletion or a mode-only change creates no new-side
   line, so no mutant to gate, and is not selected; measured on `origin/master`, 5 of 67 commits
   touching a module since 2026-05-01 were deletion-only or mode-only (8aae590 math#189 in four
   modules; 17e426c). `--no-renames` keeps a rename onto `<module>.py` from printing in the brace
   form `sq/{sq.py => sq2.py}`, which would match no path. Existing outputs are unchanged.
8. **`scripts/mutation-pr-diff.sh`** accepts a dir holding `cosmic-ray.toml` as well as
   `Cargo.toml`, and runs git with `-c diff.suppressBlankEmpty=false`.

### Verdicts per dir

Rows are evaluated in order; the first that applies decides.

| # | Condition | Verdict |
| --- | --- | --- |
| 1 | Expected dir has no plan line, or a plan line names an unexpected dir | red, naming the dir |
| 2 | Baseline, diff, prune, `init`, shard or `exec` fails, or a planned unit has no status file | red, naming the step or unit, with its stderr |
| 3 | `lines 0` for a selected dir | red, `no changed module lines` (detect selects only dirs with added lines, so this is a broken diff) |
| 4 | `--min-killed N` (canary only) and killed < N, where `kept 0` counts as killed 0 | red |
| 5 | Any result not `NORMAL` with `KILLED`/`SURVIVED` | red (existing rule) |
| 6 | Survivors > 0 | red, one full-key line and mutant diff per survivor plus the unit's repro |
| 7 | `kept 0` with `lines` > 0 (comment or blank-line change) | green, `0 mutants on changed lines` |
| 8 | Otherwise | green; timeouts count as KILLED, parity with ADR-0042 |

### Canary

`mutation-py-canary` runs when the PR changes a canary path: `.github/workflows/mutation-pr.yml`,
`scripts/mutation-pr-detect.sh`, `scripts/mutation-pr-diff.sh`,
`scripts/mutation-pr-plan-python.sh`, `scripts/mutation-pr-verdict-python.sh`,
`scripts/cosmic_ray_prune.py`, `scripts/cosmic_ray_cell_status.py`,
`scripts/crate_templates/python/Makefile`, `sq/sq.py` or `sq/mutants-equivalent.toml`. It installs
the Python toolchain itself, appends a trailing space to the single line `    limit = 10**max_digits`
of `sq/sq.py` (red unless exactly one line matches), commits that path alone in the runner
checkout, and runs plan, `mutants-diff` with `MUTANT_SHARD=0/1` (the single unit the plan emits
for K = 13) and the verdict with `--expected-dirs sq --min-killed 1`, all against base `HEAD~1`, so the PR's own `sq.py` edits never enter the
canary's diff. That line carries 13 killed mutants, and row 4 makes a filter that keeps nothing
red; the baseline dependency makes a broken environment red rather than all-`KILLED`.

### Install conditions

Every job that runs cosmic-ray installs the pinned Python toolchain on its own condition:
`mutation-py-plan` when `py_src_dirs` is non-empty (the job and its plan step always run, so
`units` is always set), `mutation-py` whenever it runs,
`mutation-py-canary` when `py_canary` is true, `mutation-rs` on `has_py` as today. A canary-only
PR (for example a vendored re-sync touching only `scripts/cosmic_ray_prune.py`) therefore has
cosmic-ray where it runs.

### Equivalents file changes

A PR changing only a `mutants-equivalent.toml` selects no dir. `scripts.yml` gains the path
`*/mutants-equivalent.toml` and installs cosmic-ray (R15), so `tests/test_mutants_equivalent.py`
runs in CI and a stale or ambiguous entry fails the PR instead of turning 10 sweep cells red the
next month; on failure the test prints prune's candidate listing. A module edit that lands on a
declared equivalent's line fails that PR's gate with `re-confirm` until the PR also edits that
entry, and a module edit that breaks an entry's key fails it with the candidate listing, because `mutants-diff` runs `prune equivalents` first, and the
plan line carries the listing. Whether a declared mutant is truly equivalent is a review judgement
on its `reason`; no tool decides it.

### Vendoring

`scripts/cosmic_ray_prune.py` equals ai-config `.claude/scripts/cosmic_ray_prune.py` in every line
but line 2, which reads `# Vendored from ai-config .claude/scripts/cosmic_ray_prune.py @ <sha12>.
Edit there, re-sync here.` Re-sync: copy, rewrite line 2 with the sha of the last ai-config commit
touching the file, run `make test`; one math PR per canonical change. Such a PR touches a canary
path, so the canary proves the new copy on real cosmic-ray.

math's ruff `extend-select` is ai-config's `select` plus `C901`, which ai-config's maintainability
gate bounds at 10; pyright runs `standard` in both and ai-config adds mypy.

The drift check compares against the commit line 2 names, not the live canonical file:
`git -C ~/git-repos/personal/ai-config show <sha>:.claude/scripts/cosmic_ray_prune.py`, every line
but line 2, failing on any difference and skipped when that checkout or sha is absent. A canonical
change on ai-config master therefore never blocks an unrelated math push; when the file on
ai-config's `origin/master` differs from the pinned sha, the test prints a re-sync warning and
passes. CI cannot read private ai-config, so the check is local only.

### Known gap, not closed here

A PR that weakens or deletes tests in `test_<module>.py` creates survivors on unchanged lines and is
never gated; the Rust gate has the same hole. The monthly sweep sees it. A Backlog row records it
for both languages.

### Testing

Test-first; every case pins an exact derived value.

- `tests/test_cosmic_ray_cell_status.py`: `--max-survivors` green/red, the full-key survivor line
  followed by its diff, bad N exits 2, stdout and `--survivors` file without the flag
  byte-identical to today.
- `tests/scripts/makefile.bats`: `mutants-diff` and `mutants-diff-plan` exit 2 on unset or
  unreadable `DIFF` without calling cosmic-ray; both run `mutants-baseline` first and stop when it
  fails; call order baseline, `init`, `equivalents`, `diff`, shard, `exec` (mock log);
  `mutants-diff` writes only the diff session and report names; `mutants` calls `equivalents` after
  `init` and before the shard and fails when it fails; `mutants-clean` removes both pairs.
- `tests/scripts/mutation_pr_detect.bats`: a module with added lines selects its dir; a
  deletion-only module diff and a mode-only change select nothing; a rename onto `<module>.py` with
  an added line selects the dir; a test-file change selects
  nothing in `py_src_dirs` while `py_dirs` keeps it; one `py_canary` case per canary path.
- `tests/scripts/mutation_pr_diff.bats`: a `cosmic-ray.toml` dir is accepted; neither manifest
  exits 2; the git call carries `diff.suppressBlankEmpty=false`.
- `tests/scripts/mutation_pr_plan_python.bats` (new): `n` for K = 0, 1, 150, 151, 1500, 1501;
  plan lines for `lines 0`, `kept 0`, a baseline failure, a prune failure whose mock stderr line
  appears in the plan line's detail; units JSON `[]` when every dir is `kept 0` and when given zero
  dirs; a re-confirm failure from prune is a red plan line carrying prune's message.
- `tests/scripts/mutation_pr_verdict_python.bats` (new): every verdict row, including an expected
  dir missing from the plan, an unexpected plan dir, `kept 0` with `--min-killed 1` red, a planned
  unit with no status file red, and a red unit's repro carrying its `MUTANT_SHARD=k/n` and a
  `mktemp` diff path.
- `tests/test_mutants_equivalent.py` (new): all 9 tomls exist and keep the strict layout; with
  cosmic-ray installed each entry resolves under `--full-run` on a fresh init and a failure prints prune's candidate listing (skip when absent
  outside CI, fail under `CI=true`).
- `tests/test_vendored_prune.py` (new): line 2 form; equality with the pinned sha's file except line
  2, skipped when the ai-config checkout or sha is absent; a moved `origin/master` warns and passes.
- `tests/test_mutation_workflows.py`: the five jobs, their `needs` and `if:` conditions
  (`mutation-py` on `units != '[]'`), the aggregator named `mutation-pr` with `if: always()` and the
  aggregator rule's result checks, `--expected-dirs` from `py_src_dirs`, status uploads with
  `overwrite: true`, each job's install site and condition, matrix `timeout-minutes: 30`, the
  canary's `HEAD~1` base and `--min-killed 1`. `test_pip_line_matches_template` is rewritten to
  check each job's install line rather than one line per file, and `test_no_cosmic_ray_exec` and
  every test keyed on `jobs["mutation-pr"]` are re-pointed at `mutation-rs` where they mean the old
  job, so none passes vacuously against the aggregator.
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
- **R2.** The Python `mutants` recipe copies `mutants-equivalent.toml` into the work dir and runs `cosmic_ray_prune.py equivalents <session> mutants-equivalent.toml --full-run` after `cosmic-ray init` and before `cosmic_ray_shard.py`; a non-zero exit fails the recipe.
- **R3.** The Python template has `mutants-diff-plan` and `mutants-diff` targets, listed in `.PHONY` and rendered into all 9 projects, each depending on `mutants-baseline`; each exits 2 with a message naming `DIFF` when `DIFF` is unset or not a readable file without invoking cosmic-ray, and resolves a relative `DIFF` against the invoking directory; `mutants-diff-plan` runs `init`, `prune equivalents <session> mutants-equivalent.toml --diff "$DIFF" --toml-path mutants-equivalent.toml` and `prune diff <session> <DIFF> <module>.py` and no `exec`; `mutants-diff` additionally applies `MUTANT_SHARD` when set, runs `exec` and `cosmic_ray_cell_status.py --max-survivors 0`, and writes only `cosmic-ray-diff-session.sqlite` and `mutants-diff-report.txt` in the project dir.
- **R4.** Each of the 9 Python projects has `mutants-equivalent.toml`; pi and e each hold exactly the 3 entries of the equivalents table, each with `operator`, `function`, `line`, `col`, `above` and a non-empty `reason`, and none with `row`, `variant` or `of`; the other 7 hold no `[[equivalent]]` entry.
- **R5.** `cosmic_ray_cell_status.py --max-survivors N` reports red when survivors exceed N, printing each as `<module>:<row> col <col> <operator> function "<definition_name>"` followed by its `work_results.diff`, exits 2 when N is not a plain non-negative decimal, and without the flag produces stdout and `--survivors` output byte-identical to today's.
- **R6.** `scripts/mutation-pr-detect.sh` prints `py_src_dirs=<sorted dirs>`, selecting a Python dir only when `git diff --numstat --no-renames` shows more than 0 added lines in `<dir>/<module>.py` (`<module>` is the dir name with `-` replaced by `_`), and `py_canary=true|false`, true exactly when a canary path listed in the Canary section changed; its existing outputs are unchanged.
- **R7.** `scripts/mutation-pr-diff.sh` accepts a dir containing `Cargo.toml` or `cosmic-ray.toml`, exits 2 when it contains neither, and passes `-c diff.suppressBlankEmpty=false` to git.
- **R8.** `scripts/mutation-pr-plan-python.sh` accepts zero dirs (empty plan, units `[]`) and writes one plan line per dir and a units JSON with `n = min(10, max(1, ceil(K / 150)))` shards per dir with `K` > 0, and no unit for a dir with `K` = 0 or a red plan line (so `[]` when no dir has units); a failing step's stderr is carried in the plan line's detail and appended to `$GITHUB_STEP_SUMMARY`.
- **R9.** `scripts/mutation-pr-verdict-python.sh --expected-dirs "<dirs>" [--min-killed N] <plan-file> <status-dir>` applies the verdict table's rows in order, is red for an expected dir without a plan line and for a plan line naming an unexpected dir, prints one verdict line per dir with full-key survivor lines, mutant diffs and a repro carrying the unit's `MUTANT_SHARD=k/n` and a `mktemp` diff path on red, exits 1 when any dir is red, 2 on bad usage, else 0.
- **R10.** `mutation-pr.yml` has jobs `mutation-py-plan` (unconditional, always setting its `units` output), `mutation-py` (matrix over the plan's units, `if:` the units output is not `[]`, `timeout-minutes: 30`, status file `status/<dir>-<k>` uploaded as `mutants-pr-status-<dir>-<k>` with `overwrite: true`), `mutation-py-canary` (diff base `HEAD~1`, `MUTANT_SHARD=0/1`), `mutation-rs` (the former `mutation-pr` job's steps, unchanged except its id) and an aggregator with id `mutation-pr`, `needs` on all four and `if: always()`, which is green only under the Aggregator rule and passes `--expected-dirs` from `py_src_dirs`; every Python job except the canary uses the plan job's merge-base output.
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
- **V7.** The plan's first task runs the vendored `cosmic_ray_prune.py equivalents --help` and `diff --help` at the sha line 2 names and checks them against the call lines of R2 and R3; any mismatch stops the plan before dispatch.
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

### Round 2

Reviewed at commit: `a7bb16e` (round 1 revisions, all three lenses re-run; the equivalents key
was superseded during the round by the operator's `above` ruling, so findings on mandatory `row`
are moot).

**Goal-Fit.** Finding: worth building; the five jobs are proportionate (a fixed `py_src_dirs × 10`
matrix would put 20 units against the concurrency cap on a pi+e PR); required context
`mutation-pr` confirmed (`gh api .../branches/master/protection`); shard fit confirmed by sweep run
42157890077 (182-183 mutants per shard in 15m17s-20m10s). Flaw: verdict row "lines 0 red" turns a
pure-deletion PR red with no remedy; math#189 (8aae590) did this in four modules. Assumption: row
drift on mandatory `row` grows with the entry count; moot under the `above` ruling.
Disposition: Addressed (operator, 2026-11-07) — detect selects only dirs with added lines (R6).

**Ergonomics.** Finding: (1) 5 of 7 recent pi PRs shifted lines above row 96 and prune's candidate
listing never reached the author; (2) pure deletion red, 5 of 67 module commits; (3) the repro
dropped `MUTANT_SHARD` and shared `/tmp/d.diff`; (4) the drift test against live `~/.claude` would
block unrelated math pushes whenever ai-config master moved; (5) an empty or short plan reads
green. Assumption: prune's stderr reaches the author; settled by requiring it.
Disposition: Addressed (operator, 2026-11-07) — listing in the plan line and step summary (R8)
and the test; detect by added lines (R6); repro with `MUTANT_SHARD` and `mktemp` (R9); drift test
pinned to the line-2 sha, warning on a moved master (Vendoring); `--expected-dirs` (R9).

**Risk.** Finding: (1) `mutants-diff` dropped the baseline, so a broken leg environment scores
every mutant `KILLED` and reads green, and the canary cannot see it; (2) the verdict's dir set came
only from the plan; (3) an all-`kept 0` plan makes the matrix error and turns a green red; (4) the
canary's merge-base diff carries the PR's own `sq.py` edits; `test_pip_line_matches_template` and
`test_no_cosmic_ray_exec` break or go vacuous under the rename. Assumption: earlier attempts'
artifacts could satisfy a re-run aggregator; memory `ai-config-rerun-failed-keeps-prior-attempt-artifacts`
confirms they stay visible, so the aggregator also requires a `success` job result.
Disposition: Addressed (operator, 2026-11-07) — baseline dependency (R3, Components 3); verdict
`--expected-dirs` (R9); `mutation-py` on `units != '[]'` and the Aggregator rule (R10); canary on
`HEAD~1` (R10); test rewrites (Testing); `overwrite: true` uploads (R10).

### Round 3 (scoped, Risk only)

Reviewed at commit: `0a61533`. Scope: the sections round 2 changed.

Finding: (1) ai-config's `equivalents` gained mode flags (`--diff`/`--toml-path` or `--full-run`,
exit 2 otherwise) and the re-confirm rule, which the math call lines and prose did not carry;
(2) `units` was unset when `py_src_dirs` is empty, so `'' != '[]'` would run the matrix on
`fromJSON('')` and turn every non-Python PR red; (3) the canary ran unsharded against a planned
unit `0/1` with no named status file; (4) `--numstat` prints a rename in brace form, so a rename
onto the module was not selected. Verified: the canary's trailing space is `1 1 sq/sq.py` in
numstat; `HEAD~1` is the merge commit on top of the merge ref. Assumption: the vendored CLI is
frozen; ai-config approved its spec at `96ffa257` during the round.
Disposition: Addressed (operator, 2026-11-07) — mode flags in R2/R3 and Components 1-3; plan
always emits `units` (R8, R10); canary `MUTANT_SHARD=0/1` and named status files (R10); detect
`--no-renames` (R6); V7 checks the vendored CLI before dispatch. Review closed: round 3's findings
were interface and harness defects, not design, so the next instrument is Phase 2's first red test.

## Spec alignment (2026-11-08)

- spec: docs/superpowers/specs/2026-11-07-worldclass-slice8-python-pr-mutation-gate-design.md
- anchor: 2e1013c6e0726006a8aabddfb205bd6d02ae3f8d
- in scope: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15, R16, R17, R18
- out of scope: none

### Findings

| ID | Reviewer | Verdict | Reason | Amendment |
| --- | --- | --- | --- | --- |

### Reviewed

- none

### Verifications

- V1: Throwaway draft math#220 (slice + untested `if max_digits == 123457: return 0` in sq.py): mutation-pr red; the sq leg named 6 survivors with full keys (e.g. sq.py:19 col 18 core/ReplaceComparisonOperator_Eq_Gt function "generate_squares"). It exposed the aggregator skipping the verdict after a red result check, fixed in ce6a3af; re-run pending after push.
- V2: math#219 run at 601155d: mutation-py-canary passed (13 killed on sq.py `limit` line, per plan).
- V3: no evidence recorded
- V4: no evidence recorded
- V5: tests/test_vendored_prune.py ran on claude at f3427c6 (pin 0694f163fbd4): 2 tests OK, not skipped; a one-line body edit turned it red.
- V6: no evidence recorded
- V7: Before Task 1: equivalents --help and diff --help at 9b588ce3f4fb showed --full-run, --diff, --toml-path and the diff <session> <diff-file> <module> form; a bad mode combination exited 2. Re-vendored at 0694f163fbd4 (ISC004 fix, AST identical).
