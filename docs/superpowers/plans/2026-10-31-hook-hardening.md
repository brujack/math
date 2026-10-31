# Hook Hardening Implementation Plan

spec: docs/superpowers/specs/2026-10-31-hook-hardening-design.md

> **Status: DONE** (math#192, 4cb0987)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lint staged root Python at commit, make ruff detection survive pyenv shims, isolate `pre_push.bats`, and pin the pre-push checker's untested refusal and cleanup branches.

**Architecture:** Branch `test/hook-hardening` in `.worktrees/hook-hardening`. Five sequential tasks and one draft PR. The work is bats under `tests/scripts/`, with mocks in `tests/mocks/` (`make` honours `MOCK_MAKE_FAIL_DIR` and `MOCK_MAKE_EXIT`) and real-git fixtures in `pre_push_budget.bats`.

**Tech Stack:** bash, bats, GNU make, ruff 0.16.4.

## Global Constraints

- `scripts/pre-push` must not change (N1).
- Change only the `RUFF :=` line in the root `Makefile` (N3).
- pre-commit adds no lint for root shell, Makefile or workflow files (N2).
- `CLAUDE.md` is 29,980 bytes. Its only edit is +17 bytes, for a total of 29,997, and it must stay ≤ 30,000.
- Run every gate synchronously with `< /dev/null` and Bash `timeout: 600000`. Root `make test` takes about 52 s.
- Run `make lint` after `git add`: root lint scopes `ruff format --check` by `git ls-files`.
- Every new bats `setup()` that touches real git unsets `GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE`.
- **Session verification, run by the orchestrator after Task 5:**
  - `make lint < /dev/null && make test < /dev/null` exits 0 in the worktree.
  - V1: `pre_push.bats` passes with `HOME` read-only and `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` set to bogus paths.
  - V2: in a scratch copy, delete `rm -f "${tmp}"` and the R6 case fails; make the no-base branch `return 0` without refusing and the R4 case fails.
  - V3: PR CI is green, and the `scripts.yml` `make lint` log shows `ruff check` and does not show `ruff not found`.

## Orchestrator steps

1. Run `git worktree add .worktrees/hook-hardening -b test/hook-hardening origin/master`.
2. Dispatch Tasks 1-5 in order. Every prompt starts with **IMPORTANT: All work must happen in `/home/bruce/git-repos/personal/math/.worktrees/hook-hardening/`. Do not cd anywhere else.**
3. Run the session verification above.
4. Run Phase 3, push, then `gh pr create --draft`.
5. Run `gh pr checks <n> --watch`. Once CI is green, run `gh pr ready <n>`.
6. After the merge, message the ai-config session: `math-ci.md` § Pre-commit hook needs the root `.py` route.

---

### Task 1: ruff detection survives an unrunnable shim

```yaml-task
id: 1
description: Set RUFF only when ruff --version succeeds, with makefile.bats cases for both directions and no RUFF override
role: executor
model: sonnet
tdd: required
requirements: [R7]
acceptance:
  - cmd: bats tests/scripts/makefile.bats < /dev/null
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [Makefile, tests/scripts/makefile.bats]
depends_on: []
```

- [ ] **RED.** Add two cases to `tests/scripts/makefile.bats`, next to `"lint-python skips with a remedy when ruff is absent"`. In each, make `STUB="${BATS_TEST_TMPDIR}/bin"` and run `run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS PATH="${STUB}:${PATH}" make -C "${REPO_ROOT}" ... --no-print-directory`, with **no** `RUFF=` argument.
  - `"lint-python skips when ruff is on PATH but not runnable"`: the stub `ruff` is `#!/usr/bin/env bash` + `exit 127`. Run the real `make lint-python`, not `-n`. Assert `status -eq 0`, output contains `ruff not found, skipping`, and output does not contain `Error 127`.
  - `"lint-python runs ruff when ruff answers --version"`: the stub `ruff` exits 0 for every argument. Run `make -n lint-python`. Assert output contains `ruff check` and does not contain `ruff not found`.
  - Run the file. The first case fails today with rc 2 and `Error 127`. The second passes today; it guards against a detection line that never finds ruff.
- [ ] **GREEN.** In the root `Makefile`, replace `RUFF := $(shell command -v ruff 2>/dev/null)` with `RUFF := $(shell ruff --version >/dev/null 2>&1 && command -v ruff)`. Change nothing else in the `Makefile`, not even a comment (N3); put the reason in the commit body: a pyenv shim answers `command -v` with no ruff behind it.
- [ ] Mutation check, in a scratch copy only: set `RUFF :=` (always empty). The positive case must fail. Report the result.
- [ ] Run the gates. Commit `fix(make): detect ruff by running it, not by PATH lookup`.

### Task 2: pre-commit lints staged root-scope Python

```yaml-task
id: 2
description: Run root make lint-python once from scripts/pre-commit when a staged path is root-scope .py or .pyi, with bats cases for both directions and failure
role: executor
model: sonnet
tdd: required
requirements: [R1, R2]
acceptance:
  - cmd: bats tests/scripts/pre_commit.bats < /dev/null
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/pre-commit, tests/scripts/pre_commit.bats]
depends_on: [1]
```

- [ ] **RED.** Add cases to `tests/scripts/pre_commit.bats`, using its existing mocks (`MOCK_GIT_DIFF_NAMES`, `MOCK_CALLS_FILE`, root `${BATS_TEST_TMPDIR}/fake-root`) and `assert_no_match`:
  - `tests/test_x.py` staged: `[ "$(grep -c "make -C ${BATS_TEST_TMPDIR}/fake-root lint-python" "${MOCK_CALLS_FILE}")" -eq 1 ]`.
  - `scripts/a.py` and `tests/b.py` staged: the same count is still 1.
  - `typings/gmpy2/__init__.pyi` staged: the count is 1.
  - `.claude/scripts/x.py` staged: the count is 1.
  - `pi/pi.py` only: `assert_no_match "lint-python"`, and the existing `make -C .../pi lint` call still happens.
  - `scripts/x.sh` only: `assert_no_match "lint-python"` (N2).
  - `MOCK_MAKE_FAIL_DIR=fake-root` with `tests/test_x.py` staged: `[ "$status" -ne 0 ]`.
- [ ] **GREEN.** In `scripts/pre-commit`, after the sub-project loop and before ggshield: if any staged path matches `^(scripts|tests|\.claude/scripts|typings)/.*\.pyi?$` (`grep -qE` on `${staged_files}`), print `lint: root python` and run `make -C "${REPO_ROOT}" lint-python`. Do not wrap the call in `if` or `||`; `set -e` fails the commit.
- [ ] Run the gates. Commit `fix(pre-commit): lint staged root-scope Python`.

### Task 3: isolate `pre_push.bats`

```yaml-task
id: 3
description: Unset GIT_* and redirect HOME and git config in pre_push.bats setup, proven under a hostile environment
role: executor
model: sonnet
tdd: required
requirements: [R3]
acceptance:
  - cmd: bats --jobs 8 tests/scripts/pre_push.bats < /dev/null
    exit_code: 0
  - cmd: 'bash -c ''D=$(mktemp -d) && mkdir "$D/h" && chmod 500 "$D/h" && HOME="$D/h" GIT_DIR="$D/bogus" GIT_WORK_TREE="$D" GIT_INDEX_FILE="$D/idx" bats --jobs 8 tests/scripts/pre_push.bats < /dev/null; rc=$?; chmod 700 "$D/h"; rm -rf -- "$D"; exit $rc'''
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [tests/scripts/pre_push.bats]
depends_on: [2]
```

- [ ] **RED.** Run the second acceptance command on the unchanged file. It exits 1, with `not ok` on "every root-scope trigger alternative matches at least one tracked path" and "every harness entry names a tracked ...". Record that output.
- [ ] **GREEN.** At the top of `setup()` in `tests/scripts/pre_push.bats`, add `unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE`, `mkdir -p "${BATS_TEST_TMPDIR}/home"`, `export HOME="${BATS_TEST_TMPDIR}/home"` and `export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null`, with a one-line comment citing tdd-007/009.
- [ ] Run the gates. Commit `test(pre-push): isolate HOME and GIT_* in pre_push.bats`.

### Task 4: pin the checker's refusal and cleanup branches

```yaml-task
id: 4
description: Add pre_push_budget.bats cases for the no-base refusal (existing remote sha), the mktemp-failure refusal, and temp-file cleanup, each proven by a mutation
role: executor
model: sonnet
tdd: required
requirements: [R4, R5, R6]
acceptance:
  - cmd: bats tests/scripts/pre_push_budget.bats < /dev/null
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [tests/scripts/pre_push_budget.bats]
depends_on: [3]
```

These tests cover existing behaviour, so a mutation of `scripts/pre-push` stands in for RED. Run every mutation in a scratch copy (`mktemp -d` plus `git archive HEAD | tar -x`), never in the worktree. Delete the copy afterwards.

Use the file's helpers: `run_hook`, `head_sha`, `big_claude_md`, `commit_all`, `${STUBS}` and `${ZEROS}`.

- [ ] **No base.** `local fake=1234567890123456789012345678901234567890`. Run `run_hook "refs/heads/feat ${fake} refs/heads/feat $(head_sha)"`, which uses an existing remote sha; with `${ZEROS}` the hook exits 128. Assert `[ "$status" -eq 1 ]` and `[[ "$output" == *"refusing ${fake}: cannot determine a base"* ]]`.
  - Mutation: make the no-base branch `return 0` without the refusal. The case must fail.
- [ ] **mktemp fails.**
  - Setup: `big_claude_md 29000`, `commit_all "grow"`, then `printf '#!/usr/bin/env bash\nexit 1\n' > "${STUBS}/mktemp"` and `chmod +x` it.
  - Run `run_hook "refs/heads/feat $(head_sha) refs/heads/feat ${ZEROS}"`.
  - Assert `[ "$status" -eq 1 ]` and output contains `cannot create a temp file for the CLAUDE.md checker`.
  - Mutation: delete the `|| { ... }` block after `tmp="$(mktemp)"`. The case must fail.
- [ ] **Cleanup.**
  - Setup: `big_claude_md 29000`, `commit_all "grow"`, and `mkdir "${BATS_TEST_TMPDIR}/t"`.
  - Run `TMPDIR="${BATS_TEST_TMPDIR}/t" run_hook "refs/heads/feat $(head_sha) refs/heads/feat ${ZEROS}"`.
  - Assert `[ "$status" -eq 0 ]`, output contains `CLAUDE.md byte ceiling OK`, and `[ -z "$(find "${BATS_TEST_TMPDIR}/t" -mindepth 1)" ]`.
  - Mutation: delete `rm -f "${tmp}"`. The case must fail.
- [ ] Report each mutation's result. Run the gates. Commit `test(pre-push): pin no-base, mktemp and cleanup branches`.

### Task 5: docs and Backlog

```yaml-task
id: 5
description: CLAUDE.md pre-commit line (+17 bytes) and Backlog rows (docs-only, no behaviour change, so TDD does not apply)
role: executor
model: sonnet
tdd: not-applicable
requirements: []
acceptance:
  - cmd: 'test "$(wc -c < CLAUDE.md)" -le 30000'
    exit_code: 0
  - cmd: grep -qF 'on staged sub-projects and root `.py`' CLAUDE.md
    exit_code: 0
  - cmd: grep -qi 'sub-project Python .Makefile. template runs' docs/superpowers/README.md
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [CLAUDE.md, docs/superpowers/README.md]
depends_on: [4]
```

- [ ] `CLAUDE.md`, Pre-commit line: replace `runs \`make lint\` on staged sub-projects`with`runs \`make lint\` on staged sub-projects and root \`.py\``. Check `wc -c CLAUDE.md` is ≤ 30000; the expected value is 29,997.
- [ ] Backlog in `docs/superpowers/README.md`. Delete the four rows whose first cells begin:
  - "`scripts/pre-commit` never lints a staged root-scope"
  - "`tests/scripts/pre_push.bats` setup() does not isolate"
  - "`scripts/pre-push` \"cannot determine a base\""
  - "`scripts/pre-push` checker temp-file `rm -f`"

  Grep each row before and after. Then add this row: "| Sub-project Python `Makefile` template runs ruff unguarded | `scripts/crate_templates/python/Makefile`'s `lint` runs `ruff check .` with no runnable-ruff check, so on a pyenv-shim machine with no ruff behind the shim a staged `pi/*.py` commit fails `make lint` with 127; the root Makefile got the `ruff --version` probe in the hook-hardening PR. Detail: [spec](specs/2026-10-31-hook-hardening-design.md) |".

- [ ] Run the gates. Commit `docs: hook hardening notes`.

## Non-goal check

Reviewer verdicts (3 CLEAR, 0 CONFLICT, 0 UNCLEAR):

- N1 CLEAR — no task lists `scripts/pre-push` in `files_touched`; Task 4's mutations run in a deleted scratch copy.
- N2 CLEAR — Task 2 triggers only on staged `.py`/`.pyi` and adds a case that a staged `scripts/x.sh` does not trigger `lint-python`.
- N3 CLEAR — Task 1 replaces only the `RUFF :=` line and forbids any other `Makefile` edit; its mutation runs in a scratch copy.

Resolution: none needed.
