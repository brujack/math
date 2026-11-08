# Worldclass Slice 8: Per-PR Python Mutation Gate Implementation Plan

spec: docs/superpowers/specs/2026-11-07-worldclass-slice8-python-pr-mutation-gate-design.md

> **Status: DONE** — merged 2026-11-08 as math#219 (e27a608).

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `mutation-pr` fail any PR that leaves a surviving cosmic-ray mutant on a changed line of a Python module, under the operator's strict rule: edit a line, own its mutants.

**Architecture:** A vendored `cosmic_ray_prune.py` (ai-config canonical) deletes declared equivalents and out-of-diff specs from a fresh session. A plan job sizes each changed project into shards. A matrix job runs `make mutants-diff` per shard, and an aggregator keeps the required check name `mutation-pr`. The old single job becomes `mutation-rs`, with its steps unchanged.

**Tech Stack:** bash, bats, GNU make, cosmic-ray 8.7.0, Python 3.14 `unittest` + PyYAML, sqlite3, GitHub Actions.

## Dispatch preconditions (orchestrator, before Task 1)

1. ai-config has merged `.claude/scripts/cosmic_ray_prune.py` (spec approved at `96ffa257`). Record the sha of the last ai-config commit touching it: `git -C ~/git-repos/personal/ai-config fetch -q && git -C ~/git-repos/personal/ai-config log -1 --format=%h --abbrev=12 origin/master -- .claude/scripts/cosmic_ray_prune.py`.
2. **V7.** At that sha, `python3 <(git -C ~/git-repos/personal/ai-config show <sha>:.claude/scripts/cosmic_ray_prune.py) equivalents --help` and `... diff --help` must show `--full-run`, `--diff`, `--toml-path` and the `diff <session> <diff-file> <module>` form. Any mismatch with R2/R3 stops the plan.
3. Create the slice worktree: `git worktree add .worktrees/slice8 -b feat/slice8-python-pr-mutation-gate origin/master`.

## Global Constraints

- Strict rule: no survivor grandfathered, no committed survivor baseline, no base-commit survivor run (N5).
- Sweep verdict rules unchanged: `mutation-testing-python.yml` and `scripts/mutation-python-cell.sh` never pass `--max-survivors`, and the `--survivors` line format does not change (N1).
- Rust PR path unchanged: `scripts/mutation-pr-run.sh` and `scripts/mutation-classify.sh` are not modified, and `mutation-rs` steps equal the former `mutation-pr` job's (N2).
- `scripts/cosmic_ray_prune.py` is never edited beyond line 2 (N3).
- Nothing on the local push path runs `cosmic-ray exec` (N4). Branch protection is not changed (N6).
- Python templates are rendered: edit `scripts/crate_templates/python/*`, then run `python3 scripts/render_crate_files.py --write`. Never edit one project's copy.
- Every pip pin equals the other sites: `cosmic-ray==8.7.0`, `hypothesis==6.168.5` (`tests/test_tool_pins.py`).
- Root `CLAUDE.md` is 29,997 of 30,000 bytes. Every addition is paid for by a cut in the same task, and every cut fact is first found in ai-config knowledge.
- Shell follows `~/.claude/standards/shell.md`; Python follows `~/.claude/standards/python.md`. Read the matching file before each task.
- bats fixture repos: put `unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE` and `export HOME="${BATS_TEST_TMPDIR}"` in `setup()`. Commit with `git -c user.name=t -c user.email=t@t`. Never run `git config`.
- Wave members' gates are scoped. The orchestrator runs root `make test < /dev/null` once at each wave close.

## Verification

- **Session level:** root `make test < /dev/null` passes. `make -C pi test` and `make -C e test` pass. `CI=true python3 -m unittest tests.test_mutation_pr_python_e2e tests.test_mutants_equivalent -v` passes on `claude` with cosmic-ray installed, not skipped.
- **Local end-to-end before push**, from the slice worktree:
  1. Create the diff with `d=$(mktemp)`, then run `scripts/mutation-pr-diff.sh origin/master sq "$d"`. Because of the slice's own template render, it covers `sq/Makefile` only.
  2. Run `scripts/mutation-pr-plan-python.sh "$(git merge-base origin/master HEAD)"` with zero dirs. It writes units `[]`.
  3. A trailing-space commit on `sq/sq.py:18` planned and run through `mutants-diff` gives `kept 13 of 164 (lines 1)` and a green verdict.
- **V1 (CI):** before `gh pr ready`, open a throwaway draft PR stacked on the slice branch. It adds an untested `if max_digits == 123457: return 0` to `sq/sq.py`. `mutation-pr` must go red, naming the survivor with its full key and diff. Then close it and delete its branch.
- **V2 (CI):** the slice PR's `mutation-py-canary` is green with killed ≥ 1, shown in the step summary.
- **V3:** on the slice PR, each pi/e equivalent resolves to exactly one spec and was a survivor in run 42157890077 or 42157892557. Also record two facts and send them to `ai-config [625068]`:
  - whether `occurrence` shifts after an unrelated edit;
  - whether the `+1` `NumberReplacer` variant has the lower `occurrence` (from `work_results.diff`).
- **V4:** the ai-config session updates `math-testing-policy.md` § Mutation testing and `math-ci.md` § Workflow table, covering the gate and the `mutation-rs` rename.
- **V5:** `tests/test_vendored_prune.py` runs on `claude` and passes, not skipped.
- **V6:** replay c7c8f6f's pi and e diffs on `claude`. Each plans to `n = 5`, and one shard of each finishes inside 30 minutes, timed.
- **Edge cases covered by tests:**
  - zero dirs gives units `[]`;
  - all dirs at `kept 0` gives units `[]`;
  - `lines 0` is red;
  - an expected dir missing from the plan is red;
  - a missing status file is red;
  - `kept 0` with `--min-killed 1` is red;
  - a baseline failure is red;
  - a re-confirm failure is red;
  - a rename onto the module is selected;
  - a deletion-only or mode-only change is not selected.

---

### Task 1: Vendor cosmic_ray_prune.py and its drift test

```yaml-task
id: 1
description: Vendor ai-config's cosmic_ray_prune.py with the line-2 header and add a sha-pinned drift test
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: python3 -m unittest tests.test_vendored_prune -v
    exit_code: 0
  - cmd: make lint
    exit_code: 0
  - cmd: pyright scripts/cosmic_ray_prune.py tests/test_vendored_prune.py
    exit_code: 0
max_retries: 3
files_touched: [scripts/cosmic_ray_prune.py, tests/test_vendored_prune.py]
depends_on: []
parallel_group: wave-1
requirements: [R1]
```

- [ ] Write the test first:
  - Line 2 matches `^# Vendored from ai-config \.claude/scripts/cosmic_ray_prune\.py @ [0-9a-f]{12}\. Edit there, re-sync here\.$`.
  - Read the sha from line 2 and get the canonical file with `git -C ~/git-repos/personal/ai-config show <sha>:.claude/scripts/cosmic_ray_prune.py`, with `GIT_*` env stripped.
  - Assert every line except line 2 is equal. Skip with a reason when the checkout or the sha is absent.
  - When `origin/master`'s copy differs from the pinned sha, print `re-sync warning` and pass.
- [ ] Copy the canonical file at the precondition sha. Replace only line 2, and set the executable bit.
- [ ] Prove the drift test fails: change one body line and confirm the test goes red, then revert.

**Interfaces:** Produces `scripts/cosmic_ray_prune.py` with subcommands `equivalents <session> <toml> (--full-run | --diff <f> --toml-path <p>)` and `diff <session> <diff-file> <module>`.

### Task 2: cell_status --max-survivors

```yaml-task
id: 2
description: cosmic_ray_cell_status.py gains --max-survivors N with full-key survivor lines and diffs; no-flag output unchanged
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: python3 -m unittest tests.test_cosmic_ray_cell_status -v
    exit_code: 0
  - cmd: make lint
    exit_code: 0
  - cmd: pyright scripts/cosmic_ray_cell_status.py tests/test_cosmic_ray_cell_status.py
    exit_code: 0
max_retries: 3
files_touched: [scripts/cosmic_ray_cell_status.py, tests/test_cosmic_ray_cell_status.py]
depends_on: []
parallel_group: wave-1
requirements: [R5]
```

- [ ] Add tests on the existing fixtures:
  - With N=0: 0 survivors is green, and 1 survivor is red.
  - The red output lists each survivor as `<module>:<row> col <col> <operator> function "<definition_name>"`, followed by that row's `work_results.diff`.
  - N=1 with 1 survivor is green.
  - An N of `-1`, `x` or `01` exits 2.
  - Without the flag, stdout and the `--survivors` file are byte-identical to today's. Capture today's output first and pin it as a golden string.
- [ ] Implement it. `--survivors` keeps its `<module_path>:<start_pos_row> <operator_name>` format.

**Interfaces:** Produces the `--max-survivors N` flag and the full-key line format, which Task 8 parses.

### Task 3: detect py_src_dirs and py_canary

```yaml-task
id: 3
description: mutation-pr-detect.sh prints py_src_dirs (module with added lines, --no-renames) and py_canary
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_pr_detect.bats
    exit_code: 0
  - cmd: shellcheck --severity=warning scripts/mutation-pr-detect.sh tests/scripts/mutation_pr_detect.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-pr-detect.sh, tests/scripts/mutation_pr_detect.bats]
depends_on: []
parallel_group: wave-1
requirements: [R6]
```

- [ ] Add bats cases:
  - Selection:
    - A module with added lines selects its dir.
    - A deletion-only diff selects nothing; so does a mode-only change.
    - A rename onto `sq/sq.py` with an added line selects `sq`.
    - `perfect-numbers/perfect_numbers.py` selects `perfect-numbers`.
    - A test-file change leaves `py_src_dirs` empty and keeps `py_dirs`.
  - Canary: one `py_canary=true` case per canary path in the spec's Canary section, and one unrelated path giving `false`.
  - Existing output lines are unchanged.
- [ ] Implement it with `git diff --numstat --no-renames "$1...HEAD"`, selecting where added > 0 on `<dir>/<module>.py`. Print `py_src_dirs=` sorted and `py_canary=`.

### Task 4: diff script accepts Python dirs

```yaml-task
id: 4
description: mutation-pr-diff.sh accepts a dir with cosmic-ray.toml and pins diff.suppressBlankEmpty=false
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_pr_diff.bats tests/scripts/mutation_pr_run.bats
    exit_code: 0
  - cmd: shellcheck --severity=warning scripts/mutation-pr-diff.sh tests/scripts/mutation_pr_diff.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-pr-diff.sh, tests/scripts/mutation_pr_diff.bats]
depends_on: []
parallel_group: wave-1
requirements: [R7]
```

- [ ] Add bats cases:
  - A fixture dir holding `cosmic-ray.toml` gets `+++ b/<module>.py`.
  - A dir with neither manifest exits 2.
  - A blank context line inside a hunk is emitted as one space, even with `git -c diff.suppressBlankEmpty=true` set in `GIT_CONFIG_PARAMETERS`. This proves the pin wins.
- [ ] Implement it: accept `Cargo.toml` or `cosmic-ray.toml`, and put `-c diff.suppressBlankEmpty=false` before `diff`. The Rust bats suite stays green, which is why `mutation_pr_run.bats` is in the gate.

**Interfaces:** Produces the Python-dir form of `scripts/mutation-pr-diff.sh <base> <dir> <out>`.

### Task 5: Makefile template targets and toml files

```yaml-task
id: 5
description: Template gains prune calls, mutants-diff-plan and mutants-diff on a baseline; 9 empty tomls; outputs gitignored
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/makefile.bats
    exit_code: 0
  - cmd: python3 -m unittest tests.test_crate_uniformity -v
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/python/Makefile, amicable/Makefile, collatz/Makefile, e/Makefile, factorial/Makefile, fib/Makefile, perfect-numbers/Makefile, pi/Makefile, sq/Makefile, triangle/Makefile, amicable/mutants-equivalent.toml, collatz/mutants-equivalent.toml, e/mutants-equivalent.toml, factorial/mutants-equivalent.toml, fib/mutants-equivalent.toml, perfect-numbers/mutants-equivalent.toml, pi/mutants-equivalent.toml, sq/mutants-equivalent.toml, triangle/mutants-equivalent.toml, .gitignore, tests/scripts/makefile.bats]
depends_on: [1, 2]
requirements: [R2, R3]
```

- [ ] Add bats cases with the mock `cosmic-ray`, `cr-report` and a mock prune that logs calls:
  - `mutants-diff` and `mutants-diff-plan` exit 2 naming `DIFF` when it is unset or unreadable, and cosmic-ray is never called.
  - Both run `mutants-baseline` first and stop when it fails.
  - Call order: baseline, `init`, `equivalents ... --diff <abs DIFF> --toml-path mutants-equivalent.toml`, `diff ... <module>.py`, shard (only with `MUTANT_SHARD`), `exec`, `cell_status --max-survivors 0`.
  - A relative `DIFF` resolves against the invoking directory.
  - `mutants-diff` writes only `cosmic-ray-diff-session.sqlite` and `mutants-diff-report.txt`. A pre-existing `cosmic-ray-session.sqlite` is byte-identical afterwards.
  - `mutants` calls `equivalents ... --full-run` after `init` and before the shard, and fails when it fails.
  - `mutants-clean` removes both pairs.
- [ ] Edit the template, add the targets to `.PHONY`, and render. Create each of the 9 tomls as a comment-free empty file; Task 6 fills pi and e. Add the diff session, its journal and the report to `.gitignore`.

**Interfaces:** Produces `make -C <dir> mutants-diff-plan DIFF=<f>`, which prints the prune lines, and `make -C <dir> mutants-diff DIFF=<f> [MUTANT_SHARD=k/n] [STATUS_OUT=..] [SURVIVORS_OUT=..]`.

### Task 6: pi/e equivalents, equivalents test, pre-push and scripts.yml

```yaml-task
id: 6
description: Author pi/e entries via prune's listing; test_mutants_equivalent.py; pre-push and scripts.yml wiring
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: CI=true python3 -m unittest tests.test_mutants_equivalent -v
    exit_code: 0
  - cmd: bats tests/scripts/pre_push.bats
    exit_code: 0
  - cmd: python3 -m unittest tests.test_tool_pins -v
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [pi/mutants-equivalent.toml, e/mutants-equivalent.toml, tests/test_mutants_equivalent.py, scripts/pre-push, tests/scripts/pre_push.bats, .github/workflows/scripts.yml]
depends_on: [5]
requirements: [R4, R14, R15]
```

- [ ] Write `tests/test_mutants_equivalent.py`:
  - All 9 tomls exist and keep the strict layout.
  - Each project runs `cosmic-ray init` in a temp copy, then `prune equivalents --full-run`.
  - A failure prints prune's stderr.
  - Skip with a reason when cosmic-ray is absent and `CI` is not `true`; fail when `CI=true`.
- [ ] Author the 3 pi and 3 e entries from the spec's equivalents table, using skeleton entries and prune's candidate listing. Each entry gets `operator`, `function`, `line`, `col`, `above` and `reason`, with no `row`, `variant` or `of`. Run `prune equivalents --full-run` to confirm it prints `excluded 3 of 1828` (pi) and `excluded 3 of 1621` (e).
- [ ] Pre-push: when a pushed commit changes `*/mutants-equivalent.toml` or a Python module file, run `python3 -m unittest tests.test_mutants_equivalent < /dev/null`, mirroring the `RUN_MUTANTS_CHECK` block. Add a bats case for each trigger and one for a no-trigger push.
- [ ] `scripts.yml`: add the path `*/mutants-equivalent.toml`, and add `cosmic-ray==8.7.0 hypothesis==6.168.5` to the install line.

### Task 7: plan script

```yaml-task
id: 7
description: mutation-pr-plan-python.sh writes plan lines and units JSON, accepting zero dirs
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_pr_plan_python.bats
    exit_code: 0
  - cmd: shellcheck --severity=warning scripts/mutation-pr-plan-python.sh tests/scripts/mutation_pr_plan_python.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-pr-plan-python.sh, tests/scripts/mutation_pr_plan_python.bats]
depends_on: [4, 5]
parallel_group: wave-3
requirements: [R8]
```

Usage: `mutation-pr-plan-python.sh <base-sha> [<dir>...]`. It writes `plan.txt` (`<dir>\t<green|red>\t<text>`) and `units.json` to `${PLAN_OUT:-.}`, and appends to `${GITHUB_STEP_SUMMARY}` when set.

- [ ] Add bats cases with a mock `make` that prints prune lines:
  - Shard count `n` for K = 0, 1, 150, 151, 1500 and 1501, which gives 0 units, then 1, 1, 2, 10, 10.
  - `lines 0` gives a red plan line, and `kept 0 (lines 2)` gives a green `0 mutants on changed lines`.
  - A baseline failure and a prune failure each give a red plan line that carries the mock's stderr line.
  - A re-confirm failure gives a red plan line that carries prune's message.
  - Zero dirs gives an empty plan and `[]`; all dirs at `kept 0` gives `[]`.
  - The output also matches `stdout_match`-style exact lines.
- [ ] Implement it with `n = min(10, max(1, ceil(K/150)))`.

**Interfaces:** Produces `plan.txt` and `units.json` (`[{"dir":"pi","k":0,"n":5},...]`).

### Task 8: verdict script

```yaml-task
id: 8
description: mutation-pr-verdict-python.sh applies the ordered verdict table against expected dirs
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_pr_verdict_python.bats
    exit_code: 0
  - cmd: shellcheck --severity=warning scripts/mutation-pr-verdict-python.sh tests/scripts/mutation_pr_verdict_python.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-pr-verdict-python.sh, tests/scripts/mutation_pr_verdict_python.bats]
depends_on: [2]
parallel_group: wave-3
requirements: [R9]
```

Usage: `--expected-dirs "<dirs>" [--min-killed N] <plan.txt> <status-dir>`. It reads `status/<dir>-<k>` files, each holding a cell_status line plus survivor blocks.

- [ ] Add one bats case per verdict row, plus:
  - An unexpected plan dir is red.
  - A missing status file is red.
  - `kept 0` with `--min-killed 1` is red.
  - The repro line in a red unit carries `MUTANT_SHARD=<k>/<n>` and `d=$(mktemp)`.
  - Exit codes: 1 when any dir is red, 2 on bad usage, 0 otherwise.

### Task 9: mutation-pr.yml restructure

```yaml-task
id: 9
description: Five jobs with mutation-pr as aggregator; mutation-rs keeps old steps; workflow tests rewritten
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_workflows -v
    exit_code: 0
  - cmd: make lint-workflows
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/mutation-pr.yml, tests/test_mutation_workflows.py]
depends_on: [3, 6, 7, 8]
requirements: [R10, R11]
```

- [ ] Tests first:
  - Five job ids, with each job's `needs`, `if:` and `timeout-minutes` (30 on `mutation-py`).
  - `mutation-py-plan` is unconditional and always sets `units`.
  - `mutation-py` runs on `units != '[]'`.
  - Status uploads go to `mutants-pr-status-<dir>-<k>` with `overwrite: true`.
  - The canary uses `HEAD~1`, `MUTANT_SHARD=0/1` and `--min-killed 1`.
  - The aggregator is id `mutation-pr` with `if: always()`. It applies the Aggregator rule's result checks and passes `--expected-dirs`.
  - Install conditions apply per job.
  - The `mutation-rs` steps equal the former `mutation-pr` steps; compare against the YAML loaded from `git show origin/master:.github/workflows/mutation-pr.yml`.
  - Rewrite `test_pip_line_matches_template` to check each job's install line. Re-point `test_no_cosmic_ray_exec` and every `jobs["mutation-pr"]` test that means the old job at `mutation-rs`.
- [ ] Rewrite the workflow and confirm `actionlint` is clean.

### Task 10: Python end-to-end test

```yaml-task
id: 10
description: Real cosmic-ray e2e on a temp sq repo; green kept 13 and red untested branch; CI-only
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: CI=true python3 -m unittest tests.test_mutation_pr_python_e2e -v
    exit_code: 0
    stderr_match: '^OK$'
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [tests/test_mutation_pr_python_e2e.py]
depends_on: [7, 8]
requirements: [R12, R13]
```

- [ ] Build a temp git repo from `git archive HEAD sq scripts`. The green case commits a trailing space on `sq.py:18`, plans, runs `mutants-diff MUTANT_SHARD=0/1` and runs the verdict. It asserts the line `kept 13 of 164 (lines 1)` and a green verdict.
- [ ] The red case commits `if max_digits == 123457: return 0`, and asserts red with a full-key survivor line.
- [ ] Skip unless `CI=true`. With `CI` unset, confirm the output says skipped.

### Task 11: ADR-0044, CLAUDE.md and plan index

```yaml-task
id: 11
description: Docs-only - ADR-0044 and index, CLAUDE.md rules within 30000 bytes, README rows (no behaviour change, so TDD does not apply)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: python3 scripts/claude_md_budget.py
    exit_code: 0
  - cmd: 'grep -qE "mutation-rs" CLAUDE.md'
    exit_code: 0
  - cmd: 'test -f "$(ls docs/adr/0044-*.md)"'
    exit_code: 0
max_retries: 3
files_touched: [docs/adr/0044-python-pr-mutation-gate.md, docs/adr/README.md, CLAUDE.md, docs/superpowers/README.md]
depends_on: [9, 10]
requirements: [R16, R17, R18]
```

- [ ] ADR-0044 covers the strict rule, deletion-based pruning, the equivalents file with `above` and re-confirm, sharding with the aggregator, and vendoring. Add its row to the ADR index.
- [ ] `CLAUDE.md`:
  - Replace the line "`mutation-pr.yml` runs `mutants-baseline` for Python" with the gate, its repro, the equivalents rule, the re-sync rule and `mutation-rs`.
  - Pay for the bytes by moving detail to ai-config knowledge, and grep each cut fact there first.
  - Stay at or under 30,000 bytes.
- [ ] `docs/superpowers/README.md` gets this R18:
  - Mark the plan row.
  - Add the four Backlog rows the spec names.
  - Delete the pi/e equivalents row.
  - Narrow the "Mutation score threshold" row to Python.
- [ ] The orchestrator then runs `make test < /dev/null` once.

## Non-goal check

Reviewer run 2026-11-07 against N1-N6: 0 CONFLICT, 0 UNCLEAR. No plan revision or amendment needed.

- N1 CLEAR: Task 5's `mutants` calls `prune equivalents --full-run`, but never passes `--max-survivors`. Task 2 pins the no-flag output and the `--survivors` file with a golden test.
- N2 CLEAR: Task 4 adds `-c diff.suppressBlankEmpty=false` to `mutation-pr-diff.sh`, which is not an N2 file. Its output is unchanged under git's default. `mutation-pr-run.sh` and `mutation-classify.sh` are untouched. Task 9 compares `mutation-rs` steps against origin/master.
- N3 CLEAR: Task 1 changes only line 2 of the vendored file.
- N4 CLEAR: the pre-push hook runs `test_mutants_equivalent`, which calls `init` and prune but never `exec`. The e2e test skips unless `CI=true`.
- N5 CLEAR: no baseline file and no base-commit run.
- N6 CLEAR: no protection change.
