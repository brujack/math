# Python Mutation Baseline and Sharding Implementation Plan

> **Status: DONE** — merged in math#183 (f7669a2), 2026-10-30. V1 full-matrix run 41136722047 green.

spec: docs/superpowers/specs/2026-10-30-python-mutation-baseline-and-sharding-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Python mutation workflows fail closed on a broken environment, install the real test dependencies, and run the monthly measurement as an 8 × 10 sharded matrix whose survivor counts and locations reach a durable record.

**Architecture:** Two small Python scripts own the session logic (`cosmic_ray_shard.py` partitions a session, `cosmic_ray_cell_status.py` turns a finished session into one verdict line plus a survivor list). Three bash scripts own the CI glue so bats can drive them (`mutation-python-cell.sh`, `mutation-survivor-report.sh`, `mutation-pr-detect.sh`), and `mutation-notify.sh` gains an expected-units check. The rendered Python `Makefile` template wires baseline, memory cap, shard and cell status together for local and CI runs alike.

**Tech Stack:** Python 3.14 (stdlib `sqlite3`, `argparse`), bash, bats, GitHub Actions YAML, cosmic-ray 8.7.0 (fixture generation only).

## Global Constraints

- Worktree: `/home/bruce/git-repos/personal/math/.worktrees/python-mutation-baseline`, branch `fix/python-mutation-baseline`. Every task starts its prompt with: **IMPORTANT: All work must happen in `/home/bruce/git-repos/personal/math/.worktrees/python-mutation-baseline/`. Do not cd anywhere else.**
- Read `~/.claude/standards/python.md` before any `.py` change and follow core.md shell rules for `.sh` (`#!/usr/bin/env bash`, no `set -e`, sourcing guard before main, `[[ ]]`, `${VAR}`, `printf`, functions `|| return 1`).
- cosmic-ray stores enum **names**: `worker_outcome` is `NORMAL`, `EXCEPTION`, `ABNORMAL`, `NO_TEST`; `test_outcome` is `KILLED`, `SURVIVED`, `INCOMPETENT`. A timeout is `test_outcome='KILLED'` with `output='timeout'`.
- Shard count 10 and `timeout-minutes: 90` for every sub-project (N2). No change to any `<dir>/cosmic-ray.toml` (N1). No survivor or timeout count may fail anything (N3). Rust `mutation-testing.yml` behaviour unchanged (N4). No `http` distributor (N5). No diff-scoped Python mutation (N6).
- Edit `scripts/crate_templates/python/*` and run `python3 scripts/render_crate_files.py --write`; never hand-edit a rendered copy.
- Pinned pip line (copy verbatim from `scripts/crate_templates/python/py.yml:39`): `pip install mpmath==1.4.1 gmpy2==2.3.2 coverage==7.16.2 cosmic-ray==8.7.0 hypothesis==6.168.5 pytest==9.1.1 pytest-cov==7.1.0 ruff==0.16.4 pyright==1.1.411 pip-audit==2.10.1`.
- A cosmic-ray venv for fixture generation: `python3 -m venv "${TMPDIR:-/tmp}/crvenv" && "${TMPDIR:-/tmp}/crvenv/bin/pip" install cosmic-ray==8.7.0 hypothesis==6.168.5`. Never run `cosmic-ray exec` inside the worktree's sub-project dirs: it mutates source in place.
- Root `make test` runs in about 44 s (measured on the base tree, rc 0, 316 Python tests). It is every task's aggregate gate.
- Commit messages via `caveman:caveman-commit`, ending with the session's Co-Authored-By and Claude-Session trailers.

## Verification

- `make test </dev/null` in the worktree exits 0 after every task; at the end also `python3 scripts/render_crate_files.py --check` exits 0.
- V2: in a venv with only `cosmic-ray==8.7.0`, `make -C fib mutants-baseline` exits non-zero and prints `ImportError`; with the pinned set it exits 0. Run in a `git archive` copy of the branch, not the worktree.
- V3: in a fresh venv from the pinned pip line, the `mutation-pr.yml` Python step command for fib exits 0 (same copy).
- V1 (orchestrator, before `gh pr ready`): `gh workflow run mutation-testing-python.yml --ref fix/python-mutation-baseline`; all 80 cells green inside 90 min, pi survivors > 0, the cell holding pi's `Mul→Pow` mutant at `pi.py:574` has a verdict line, the `mutation-report-python` issue gets the table; record longest cell duration and timeout count per sub-project in the PR body.
- Edge cases exercised by tests: lowercase-outcome regression, a row that ran no test, missing status units, `RESULT=success` with missing units, a failing `make` in a cell, a pip-line-only diff in `mutation-pr`.

---

### Task 1: Session shard script

```yaml-task
id: 1
description: Add scripts/cosmic_ray_shard.py partitioning a cosmic-ray session by spec key, with committed real init fixtures
role: executor
model: sonnet
tdd: required
requirements: [R3, R4, R5]
acceptance:
  - cmd: python3 -m unittest tests.test_cosmic_ray_shard -v
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/cosmic_ray_shard.py, tests/test_cosmic_ray_shard.py, tests/fixtures/cosmic_ray/regen.sh, tests/fixtures/cosmic_ray/fib-init-a.sqlite, tests/fixtures/cosmic_ray/fib-init-b.sqlite]
depends_on: []
```

**Files:** create the five paths above.

- `regen.sh` (bash): takes the cosmic-ray venv bin dir as `$1`; copies `fib/fib.py`, `fib/test_fib.py`, `fib/cosmic-ray.toml` into a `mktemp -d` dir and runs `cosmic-ray init` twice into `fib-init-a.sqlite` and `fib-init-b.sqlite` beside itself. Run it once and commit both sessions.
- `cosmic_ray_shard.py <sqlite> <k> <n>`: sort `mutation_specs` rows by `(module_path, operator_name, operator_args, occurrence, start_pos_row, start_pos_col, end_pos_row, end_pos_col)`; keep row `i` where `i % n == k`; delete the others' `job_id` from `mutation_specs` and `work_items` in one transaction; print `kept K of T`. Exit 1 with a message on: missing file, zero work items, `n < 1`, `k` outside `[0, n)`, non-integer `k` or `n`.
- Tests copy fixtures to a temp dir before mutating. Cases: n=10 shards pairwise disjoint by spec key and union equal to the full key set (fails on "keep all" and on "keep none"); session a and session b give the same key partition for every k; each error input exits non-zero with the file unchanged; n=1 keeps everything; k=n-1 boundary.

**Interfaces:** Produces CLI `python3 scripts/cosmic_ray_shard.py <sqlite> <k> <n>`, stdout `kept K of T`. Task 3 calls it from the template.

### Task 2: Cell status script

```yaml-task
id: 2
description: Add scripts/cosmic_ray_cell_status.py emitting one verdict line and a survivor list from a finished session, with real exec fixtures
role: executor
model: sonnet
tdd: required
requirements: [R6, R7, R22]
acceptance:
  - cmd: python3 -m unittest tests.test_cosmic_ray_cell_status -v
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/cosmic_ray_cell_status.py, tests/test_cosmic_ray_cell_status.py, tests/fixtures/cosmic_ray/regen.sh, tests/fixtures/cosmic_ray/crfix.py, tests/fixtures/cosmic_ray/test_crfix.py, tests/fixtures/cosmic_ray/cosmic-ray.toml, tests/fixtures/cosmic_ray/crfix-exec.sqlite]
depends_on: [1]
```

**Files:** a fixture module `crfix.py` with two small functions: one whose test leaves an arithmetic mutant alive, one loop that a comparison mutant makes non-terminating. `cosmic-ray.toml` for it uses `timeout = 2.0` (fixture only; N1 covers the sub-project tomls). Extend `regen.sh` to `init` + `exec` it into `crfix-exec.sqlite`; commit the result.

- `cosmic_ray_cell_status.py <sqlite> <label> [--out FILE] [--survivors FILE]`: K = `count(work_items)`; S = rows with `test_outcome='SURVIVED'`; T = `test_outcome='KILLED' and output='timeout'`. Green line exactly `green: <label> — S surviving, T timed out, K jobs`, exit 0. Red (`red: <label> — <reason>`, exit 1) when K == 0, result rows != K, or any row not (`worker_outcome='NORMAL'` and `test_outcome in ('KILLED','SURVIVED')`). Timeouts never red. `--out` writes the line to FILE as well as stdout; `--survivors` writes one `<module_path>:<start_pos_row> <operator_name>` line per survivor (join on `job_id`), sorted.
- Tests (temp copies of `crfix-exec.sqlite`): pin the exact green line and the exact survivor-file content with their non-zero S and T as read from the committed fixture; red for a deleted result row, deleted work items, one row set to `INCOMPETENT`, one `worker_outcome` set to `EXCEPTION`; `--out` content equals stdout.

**Interfaces:** Produces the CLI above. Tasks 3 and 6 call it.

### Task 3: Template mutants recipe

```yaml-task
id: 3
description: Rework the Python template mutants recipe with baseline, 8 GiB cap, optional shard and cell status, rendered to all 8
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R21]
acceptance:
  - cmd: bats tests/scripts/makefile.bats
    exit_code: 0
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/python/Makefile, tests/scripts/makefile.bats, amicable/Makefile, collatz/Makefile, e/Makefile, factorial/Makefile, fib/Makefile, perfect-numbers/Makefile, pi/Makefile, sq/Makefile]
depends_on: [1, 2]
```

**Template changes** (`.PHONY` gains `mutants-baseline`):

```make
CELL_LABEL ?= @CRATE@

mutants-baseline:
	cosmic-ray baseline cosmic-ray.toml || { python3 -m unittest test_@MODULE@; exit 1; }

mutants: mutants-baseline
```

The `mutants` body runs in one `bash -c` under the Rust template's exact cap block (`ulimit -v 8388608`, `MUTANTS_UNCAPPED` escape, fail-closed message; copy from `scripts/crate_templates/Makefile:23-31`): `rm -f` the session, `cosmic-ray init`, then `python3 ../scripts/cosmic_ray_shard.py cosmic-ray-session.sqlite <k> <n>` only when `MUTANT_SHARD` (`k/n`) is set, `cosmic-ray exec`, `mutants-report`, then `python3 ../scripts/cosmic_ray_cell_status.py cosmic-ray-session.sqlite "$(CELL_LABEL)"` plus `--out "$(STATUS_OUT)"` and `--survivors "$(SURVIVORS_OUT)"` when those are set. Its exit code is the recipe's.

**Tests** (`makefile.bats`, read every rendered `*/Makefile` from `git ls-files '*/Makefile'` that has a sibling `cosmic-ray.toml`; assert count is 8): `mutants-baseline` precedes `init`, which precedes `exec`; the failed-baseline branch runs `python3 -m unittest test_<module>`; `ulimit -v 8388608` and `MUTANTS_UNCAPPED` present in `mutants`; shard script is guarded by `MUTANT_SHARD` and sits between `init` and `exec`; cell-status script is the last command. Then `render_crate_files.py --write`.

### Task 4: Expected-units check in mutation-notify.sh

```yaml-task
id: 4
description: Add EXPECTED_STATUS_UNITS to mutation-notify.sh, checked before the success return, naming missing and red units and exiting 1
role: executor
model: sonnet
tdd: required
requirements: [R12]
acceptance:
  - cmd: bats tests/scripts/mutation_notify.bats
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-notify.sh, tests/scripts/mutation_notify.bats]
depends_on: []
```

In `main()`, before the `if [[ "${RESULT}" == "success" ]]` block: when `EXPECTED_STATUS_UNITS` is set (`${EXPECTED_STATUS_UNITS+x}`), compute missing units (no `${ARTIFACT_DIR}/status/<unit>`) and red units (`grep -l '^red'`). If the value is empty or any unit is missing, build a body listing `Missing units:` and `Red units:`, file or comment exactly as the red path does (including `gh label create`), then `return 1`. Unset: unchanged. The file's comment above the create/comment `if` says its `|| return 1` guards become load-bearing once anything follows them; this task adds a path that ends in `return 1`, so give that path's create and comment failures their own tests and update the comment.

Tests: `RESULT=success`, one of three units missing: issue created, body names the unit, status 1; set-but-empty: status 1; all present with `RESULT=success`: the existing close-issue calls happen (assert the `gh issue close` line in `MOCK_CALLS_FILE`); one red plus one missing: body lists both; unset: existing suite unchanged; `MOCK_GH_EXIT_ISSUE_CREATE=1` on the missing path returns 1.

### Task 5: Survivor report script

```yaml-task
id: 5
description: Add scripts/mutation-survivor-report.sh writing the per-sub-project table, survivor list files, and the issue comment
role: executor
model: sonnet
tdd: required
requirements: [R13, R22]
acceptance:
  - cmd: bats tests/scripts/mutation_survivor_report.bats
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-survivor-report.sh, tests/scripts/mutation_survivor_report.bats]
depends_on: [2]
```

Inputs by env: `ARTIFACT_DIR` (merged status artifacts: `status/<dir>-<k>`, `survivors/<dir>-<k>.txt`), `EXPECTED_STATUS_UNITS`, `REPO`, `RUN_URL`, `REF`, `EVENT`, `OUT_DIR`, `GITHUB_STEP_SUMMARY`. Parses green lines `green: <dir>-<k> — S surviving, T timed out, K jobs`. Writes `${OUT_DIR}/survivors/<dir>.txt` (concatenation, sorted). Table columns: sub-project, cells reporting/expected, jobs, survivors, timed out, survivor lines; a sub-project short of cells is marked `incomplete`. Header: ref, event, units reporting of expected, run URL, and a note that locations are in artifact `mutants-survivors-python`. Writes table to `GITHUB_STEP_SUMMARY`; `gh label create mutation-report-python ... || true`; comments on the open issue with that label or creates it. Exits 0 on any counts; non-zero only when a `gh` call fails or inputs are missing.

Tests (`tests/mocks/gh`, `REPO=invalid-repo-spec-no-slash` as in `mutation_notify.bats`): two sub-projects × two cells with S/T values 3/1, 2/0, 5/2, 0/0 give sums 5/1 and 5/2 in the table; header fields present; open issue → `gh issue comment`; none → `gh label create` then `gh issue create`; a missing cell → `incomplete`; survivor files concatenated with the summed line count.

### Task 6: Cell and PR-detect scripts

```yaml-task
id: 6
description: Add scripts/mutation-python-cell.sh and scripts/mutation-pr-detect.sh with bats tests driving their failure paths
role: executor
model: sonnet
tdd: required
requirements: [R23]
acceptance:
  - cmd: bats tests/scripts/mutation_python_cell.bats tests/scripts/mutation_pr_detect.bats
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-python-cell.sh, scripts/mutation-pr-detect.sh, tests/scripts/mutation_python_cell.bats, tests/scripts/mutation_pr_detect.bats, tests/mocks/make]
depends_on: [3]
```

- `mutation-python-cell.sh <dir> <k> <n>`: `unit="<dir>-<k>"`; `out="${GITHUB_WORKSPACE}/status/${unit}"`; runs `rc=0; make -C "<dir>" mutants MUTANT_SHARD=<k>/<n> CELL_LABEL="${unit}" STATUS_OUT="${out}" SURVIVORS_OUT="${GITHUB_WORKSPACE}/survivors/${unit}.txt" || rc=$?`; if `${out}` is absent writes `red: ${unit} — make mutants failed (exit ${rc})`; appends `${out}` to `GITHUB_STEP_SUMMARY`; exits `${rc}`.
- `mutation-pr-detect.sh <base-ref>`: reads `git diff --name-only "<base>...HEAD"`; prints `py_dirs=<space list>` and `has_py=true|false` lines for `GITHUB_OUTPUT`. Any path under `scripts/crate_templates/python/`, any `.github/workflows/*-py.yml`, any `<pydir>/install_deps.sh` for the 8 Python dirs, or `.github/workflows/mutation-pr.yml` selects all 8; else each `<dir>/*.py` selects its dir.
- Tests with the repo's PATH mocks: `tests/mocks/make` already honours `MOCK_MAKE_EXIT`; add `MOCK_MAKE_STATUS_LINE`, which when set writes its value to the path given by a `STATUS_OUT=<path>` argument before exiting (no other behaviour change; existing bats suites must stay green). `tests/mocks/git` prints `MOCK_GIT_DIFF_NAMES` for any `diff` call. Cases: failing make (exit 2) leaves exactly `red: fib-0 — make mutants failed (exit 2)` and exits 2; make that wrote a green status leaves it and exits 0; pip-line-only diff → all 8; `fib/fib.py` only → `fib`; docs-only → `has_py=false`.

### Task 7: Monthly workflow matrix

```yaml-task
id: 7
description: Rewrite mutation-testing-python.yml as a setup plus 8x10 matrix plus notify workflow, with structure tests
role: executor
model: sonnet
tdd: required
requirements: [R8, R9, R10, R11, R16, R22]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_workflows -v
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/mutation-testing-python.yml, tests/test_mutation_workflows.py]
depends_on: [4, 5, 6]
```

Jobs: `setup` (validates `inputs.subproject` against the 8 dirs, fails on unknown; outputs `matrix` JSON `{"dir":[...],"shard":[0..9]}` and `units`, both from one list) → `mutants` (`needs: setup`, `strategy.fail-fast: false`, `matrix: ${{ fromJSON(needs.setup.outputs.matrix) }}`, `timeout-minutes: 90`; steps: checkout, marker, GMP/MPFR apt, `setup-python` 3.14, the pinned pip line, `scripts/mutation-python-cell.sh`, an `if: cancelled()` step writing `red: <unit> — did not finish (cancelled or timed out)` when absent, upload `mutants-status-python-<dir>-<shard>` (`status/`, `survivors/`, `marker/`) and `mutants-report-python-<dir>-<shard>` (session, `mutants-report.txt`), both `if: always()`) → `notify` (download `pattern: mutants-status-python-*`, `merge-multiple: true`; `mutation-survivor-report.sh` then upload `mutants-survivors-python` with `retention-days: 90`; then `mutation-notify.sh` with `EXPECTED_STATUS_UNITS: ${{ needs.setup.outputs.units }}`, `needs: [setup, mutants]`). Keep existing action SHA pins, the cron, `permissions`, and the notify env names.

Tests (`yaml.safe_load`): matrix/timeout/fail-fast values; units and matrix built in the same step; status and report artifacts distinct; notify pattern and merge; `EXPECTED_STATUS_UNITS` wired; survivors artifact retention 90; the Python `pip install` line is non-empty, contains `hypothesis`, and equals the template line (R16, this workflow).

### Task 8: mutation-pr baseline-only step

```yaml-task
id: 8
description: Switch mutation-pr.yml Python step to make mutants-baseline via mutation-pr-detect.sh, gated installs, Python 3.14
role: executor
model: sonnet
tdd: required
requirements: [R14, R15, R16]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_workflows -v
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/mutation-pr.yml, tests/test_mutation_workflows.py]
depends_on: [7]
```

Detect step calls `scripts/mutation-pr-detect.sh "origin/${GITHUB_BASE_REF}" >> "${GITHUB_OUTPUT}"` plus the existing Rust detection. `setup-python` 3.14. Split "Install tools": `cargo-mutants` stays unconditional for the Rust path; GMP/MPFR apt and the pinned pip line run `if: steps.detect.outputs.has_py == 'true'`. Python step: `for dir in ${PY_DIRS}; do make -C "${dir}" mutants-baseline || exit 1; done`, no `continue-on-error`, no `cosmic-ray exec`. Tests: no `cosmic-ray exec` in any step; baseline loop present; install steps gated on `has_py`; setup-python 3.14; pip line equal to template (R16, this workflow).

### Task 9: Pin scope

```yaml-task
id: 9
description: Widen test_tool_pins.py to every workflow pip install and pin pip-audit in scripts.yml
role: executor
model: sonnet
tdd: required
requirements: [R17, R18]
acceptance:
  - cmd: python3 -m unittest tests.test_tool_pins -v
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [tests/test_tool_pins.py, .github/workflows/scripts.yml]
depends_on: [8]
```

New test class scanning every `pip install` in every `.github/workflows/*.yml` (reuse `_PIP_INSTALL`), skipping `-r <file>` pairs and flags; every package `name==X.Y.Z`; one version per package across workflows and installers. Write it first and confirm it fails naming `pip-audit` in `scripts.yml` (the cosmic-ray sites are fixed by Tasks 7-8), then pin `pip-audit==2.10.1`. Add a fixture case showing a bare package is rejected.

### Task 10: Docs

```yaml-task
id: 10
description: Update root CLAUDE.md, the Backlog and the plan index for the new mutation design (docs-only, no behavior change)
role: executor
model: sonnet
tdd: not-applicable
requirements: [R19, R20]
acceptance:
  - cmd: python3 scripts/claude_md_budget.py
    exit_code: 0
  - cmd: 'grep -q "MUTANT_SHARD=0/10" CLAUDE.md'
    exit_code: 0
  - cmd: '! grep -q "Python mutation workflows probably mutate nothing" docs/superpowers/README.md'
    exit_code: 0
max_retries: 2
files_touched: [CLAUDE.md, docs/superpowers/README.md]
depends_on: [9]
```

`CLAUDE.md`: under Mutation testing add Python lines (baseline first, 8 GiB cap with `MUTANTS_UNCAPPED`, monthly 8 × 10 matrix reporting to `mutation-report-python` plus 90-day `mutants-survivors-python`, `MUTANT_SHARD=0/10` local sampling, enum names uppercase); change the pip-pin line to say every workflow `pip install` is in scope. Stay under 30,000 bytes. `docs/superpowers/README.md`: delete the P1 row and the "pip installs outside the 16 rendered sites are unpinned" row; add a Backlog row for SIGKILL leaving mutated source in place, noting a real local pi run now takes hours; add a plan-index row for this plan and spec (status In progress). `make test` is not this task's gate: neither file is read by the suite except the budget checker, which is gated above.

## Non-goal check

Fresh reviewer, 2026-10-30, against the six effective non-goals (`spec_contract.py | grep '^N'`).

| N | Verdict | Reviewer note | Resolution |
| --- | --- | --- | --- |
| N1 | CLEAR | — | none needed |
| N2 | CLEAR | — | none needed |
| N3 | CLEAR | — | none needed |
| N4 | CLEAR | "Task 4 edits `mutation-notify.sh` (shared with Rust) but gates the new check on `EXPECTED_STATUS_UNITS` being set, which the plan never sets in `mutation-testing.yml`." | none needed |
| N5 | CLEAR | — | none needed |
| N6 | CLEAR | "Task 8 selects Python dirs from the diff but runs only `mutants-baseline` and tests that no step runs `cosmic-ray exec`." | none needed |
