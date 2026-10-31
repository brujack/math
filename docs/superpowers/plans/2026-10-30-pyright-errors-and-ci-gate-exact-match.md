# Pyright Errors and ci-gate Exact Match Implementation Plan

> **Status: DONE** — merged in math#185 (863e514), 2026-10-31.

spec: docs/superpowers/specs/2026-10-30-pyright-errors-and-ci-gate-exact-match-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make root pyright errors fail the local push path with a pinned pyright, and make `ci-gate.sh` exclude checks by exact name only.

**Architecture:** `tests/test_root_pyright_scope.py` runs the repo-root `pyright --outputjson` once in `setUpClass` and reads that report for file count, error count and engine version. `requirements-dev.txt` pins the engine, and `test_tool_pins.py` folds it into the one-version rule. `ci-gate.sh`'s three jq filters switch from `inside` (substring) to exact equality.

**Tech Stack:** Python 3.14 unittest, pyright 1.1.411, bash, jq, bats.

## Global Constraints

- Worktree `/home/bruce/git-repos/personal/math/.worktrees/gate-holes`, branch `fix/pyright-and-ci-gate-holes`. Every prompt starts: **IMPORTANT: All work must happen in `/home/bruce/git-repos/personal/math/.worktrees/gate-holes/`. Do not cd anywhere else.**
- Read `~/.claude/standards/python.md` before `.py` changes; core.md shell rules for `.sh`.
- No change to `pyrightconfig.json` (N1); no pyright in `make lint` (N2); no change to the excluded check names (N3).
- Exact stderr skip line: `pyright not found; root type errors are unchecked locally (run: make install-deps)`.
- Root `make test` takes about 50 s and is every task's aggregate gate (`make test </dev/null`, Bash timeout 600000).
- Probes stay under `ulimit -v 4194304`; scratch only under a new `/tmp/claude-1000/` dir.

## Verification

- `make test </dev/null` exit 0 after every task.
- Seeded control: copy the repo with `git archive HEAD`, add `x: int = "s"` to a file under `tests/`, run `python3 -m unittest tests.test_root_pyright_scope` there: it fails listing that line.
- V1 on the PR: `scripts` CI job and the `ci-gate` job green.
- V2: on the Mac Studio (`ssh studio`), a fresh venv with `pip install -r requirements-dev.txt` gives a pyright report whose `version` is 1.1.411.

---

### Task 1: Root pyright error count, pinned engine, pin scope

```yaml-task
id: 1
description: Gate root pyright errors and engine version in test_root_pyright_scope.py, pin pyright in requirements-dev.txt and fold it into the pin scan
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R8, R10, R11]
acceptance:
  - cmd: python3 -m unittest tests.test_root_pyright_scope tests.test_tool_pins -v </dev/null
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [tests/test_root_pyright_scope.py, requirements-dev.txt, tests/test_tool_pins.py, .github/workflows/scripts.yml]
depends_on: []
```

- `setUpClass` of the coverage class runs `pyright --outputjson` once at the repo root and stores the parsed report. No-JSON output stores a failure (return code plus first 500 chars of stderr) that each test raises via `self.fail` — never a skip. Missing pyright outside CI: write the exact stderr skip line, then skip; inside CI: raise as today.
- New pure helpers (module level, tested directly): `error_lines(report, root) -> list[str]` giving `<repo-relative file>:<line+1> <rule> <message>` for each `severity == "error"` diagnostic; `version_problem(report, pin) -> str | None` returning `None` when `report["version"] == pin`, a message naming `make install-deps` on mismatch, and a distinct missing-version message when the field is absent or empty; `pinned_pyright(requirements_text) -> str` reading `pyright==X.Y.Z` from `requirements-dev.txt`.
- Tests: `errorCount == 0` against the shared report with the failure message built by `error_lines`; version check against the shared report; `error_lines` on a hand-built one-error report pins the exact line; `version_problem` with a captured real report (build it by running pyright once on a tiny temp project, or embed a trimmed real JSON with its `version` and `summary` keys) for match, mismatch, missing; R3 seeded run: temp dir with a copy of the root `pyrightconfig.json` and `scripts/seeded.py` containing `x: int = "s"` on line 2 and no imports, assert exactly one error, rule `reportAssignmentType`, line 2.
- `requirements-dev.txt`: add `pyright==1.1.411` (keep sorted).
- `tests/test_tool_pins.py`: include `requirements-dev.txt` in `pyright_installs()` (it has no `pip install` text, so read its `pyright==` line directly) (and in the one-version check across sites); update the site-count assertion and its comment to the new total (`.github/workflows/scripts.yml` loses its pyright pin in this task, so count both changes).
- `.github/workflows/scripts.yml`: drop `pyright==1.1.411` from the `pip install -r requirements-dev.txt ...` line.
- Commits: RED `test: gate root pyright errors and engine version`; GREEN `feat: pin pyright and fail root type errors locally`.

### Task 2: Exact-name exclusion in ci-gate

```yaml-task
id: 2
description: Replace jq inside substring exclusion with exact match at all three ci-gate.sh sites, with bats cases for a colliding name
role: executor
model: sonnet
tdd: required
requirements: [R4, R5]
acceptance:
  - cmd: bats --jobs 8 tests/scripts/ci_gate.bats </dev/null
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/ci-gate.sh, tests/scripts/ci_gate.bats]
depends_on: [1]
```

- All three filters `select([.name] | inside($excl) | not)` become `select(.name as $n | $excl | any(. == $n) | not)`.
- Read `tests/scripts/ci_gate.bats` and `tests/mocks/gh` (`MOCK_GH_CHECK_RUNS`, `MOCK_GH_CHECK_RUNS_<n>`, `MOCK_GH_WORKFLOW_RUNS`) first and follow the existing case shape.
- Case 1: completed check runs `scan` (failure) and `snyk-scan` (failure): gate exits non-zero, stderr names `scan` under `Required checks failed`, and does not name `snyk-scan`. RED against the old code: it exits 0 with `Proceeding`.
- Case 2: `scan` in progress on every poll, with `CI_GATE_MAX_POLLS=2 CI_GATE_POLL_INTERVAL=0`: gate exits non-zero with `Timeout: checks did not complete`.
- Commits: RED `test: cover substring check names in ci-gate`; GREEN `fix: match ci-gate exclusions by exact name`.

### Task 3: Docs

```yaml-task
id: 3
description: Update root CLAUDE.md pyright and requirements-dev lines and close the two backlog rows (docs-only, no behavior change)
role: executor
model: sonnet
tdd: not-applicable
requirements: [R6, R7, R9]
acceptance:
  - cmd: python3 scripts/claude_md_budget.py HEAD
    exit_code: 0
  - cmd: '! grep -q "Root pyright type errors are caught only in CI" docs/superpowers/README.md'
    exit_code: 0
  - cmd: '! grep -q "ci-gate excludes any check whose name is a substring" docs/superpowers/README.md'
    exit_code: 0
max_retries: 2
files_touched: [CLAUDE.md, docs/superpowers/README.md]
depends_on: [2]
```

- CLAUDE.md: the `requirements-dev.txt` line lists `pyright==1.1.411`; the pyright install-site line names `requirements-dev.txt` and drops `scripts.yml` (count as Task 1 measured); the `test_root_pyright_scope.py` line says it fails on any root pyright error or engine-version mismatch and prints the skip line when pyright is absent. Stay under 30,000 bytes; commit first, then run the budget gate on `HEAD`.
- `docs/superpowers/README.md`: delete the two P2 rows; add a plan-index row (In Progress) for this plan and spec.
- `make test` is not this task's gate: neither file is read by the suite except the budget checker, gated above.

## Non-goal check

Fresh reviewer, 2026-10-30, against the three effective non-goals: N1 CLEAR (the seeded test copies the config into a temp dir, never edits it), N2 CLEAR (no Makefile in any task), N3 CLEAR (matching changes, the exclusion list does not). No revisions needed.
