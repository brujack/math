# Hook hardening — design

Date: 2026-10-31. Repo: math. Source: four Backlog rows in `docs/superpowers/README.md`:

- `scripts/pre-commit` never lints a staged root-scope `.py`.
- `tests/scripts/pre_push.bats` `setup()` does not isolate `HOME` or `GIT_*`.
- `scripts/pre-push` "cannot determine a base" and mktemp-failure refusals are untested.
- `scripts/pre-push` checker temp-file `rm -f` is unpinned.

The operator chose to ship the four as one spec, one plan and one PR.

## Problem

1. **pre-commit skips root Python.** `scripts/pre-commit` maps each staged path to the
   longest matching sub-project directory and runs `make lint` there. A staged root-scope
   Python file (`scripts/`, `tests/`, `.claude/scripts/`, `typings/`) matches none, so it
   is committed unlinted. In math#191 two implementers committed unformatted `tests/*.py`
   this way. The push-time root `make test` would have caught both; review caught them
   first.
2. **`pre_push.bats` inherits the caller's git and home environment.** Its `setup()`
   neither unsets `GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE` nor redirects
   `HOME` (core.md tdd-007/009, git-workflow-042). `pre_push_budget.bats` does both. Two
   tests call the real `git ls-files` on `REPO_ROOT`:
   - "every root-scope trigger alternative matches at least one tracked path"
   - "every harness entry names a tracked `<dir>/<module>.py` and there are 8"
3. **Two fail-closed refusals in `check_claude_md_budget` have no test.** No case covers
   "cannot determine a base" (both `git merge-base` and `git rev-list --max-parents=0`
   fail) or "cannot create a temp file" (`mktemp` fails). A refactor that made either fall
   through would push unchecked with every test green. `pre_push_budget.bats` has 13
   tests, none of them for these branches.
4. **The checker's temp file is never shown to be removed.** `check_claude_md_budget` ends
   with `rm -f "${tmp}"`, and no test asserts that the file is gone, so dropping the line
   leaks one file per pushed ref with every test green.

## Measurements

All on Linux `claude`, 2026-10-31, master `ff23b67`.

| What                                | Command                                                                                                                   | Result                                                                                                               | Population                                                                                                                                                                             |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pre-commit routing                  | read of `scripts/pre-commit`                                                                                              | `dirs=(...)` lists the 19 sub-project dirs only; no root-scope route                                                 | the hook as tracked                                                                                                                                                                    |
| `pre_push.bats` under a hostile env | `HOME=<read-only dir> GIT_DIR=<bogus> GIT_WORK_TREE=<tmp> GIT_INDEX_FILE=<tmp> bats --jobs 8 tests/scripts/pre_push.bats` | rc 1; tests 33 and 41 (the two real-`git ls-files` tests) `not ok`; 45 ok; nothing written under `HOME`              | that one file, with an invalid `GIT_DIR`. A real worktree push exports a valid `GIT_DIR` for the same repo, and every push this session passed, so no observed failure; fragility only |
| Refusal tests                       | `grep -n '^@test' tests/scripts/pre_push_budget.bats`                                                                     | 13 tests; none for no-base or mktemp failure                                                                         | that file                                                                                                                                                                              |
| `lint-python` scope                 | `Makefile` `lint-python`                                                                                                  | `ruff check .` plus `git ls-files -z '*.py' \| xargs -0 ruff format --check`; a staged new file is in `git ls-files` | the target as tracked                                                                                                                                                                  |

## Design

### 1. pre-commit lints staged root-scope Python

- After the sub-project loop, `scripts/pre-commit` checks the staged paths against
  `^(scripts|tests|\.claude/scripts|typings)/.*\.pyi?$`. If any path matches, it runs
  `make -C "${REPO_ROOT}" lint-python` once. A non-zero exit fails the commit; the hook
  already runs under `set -e`.
- `lint-python` already degrades to a message when ruff is absent (CLAUDE.md), so a
  machine without ruff can still commit.
- Root shell, Makefile and workflow changes stay out. The pre-push hook already runs
  `lint-hooks` for `.sh` changes.
- `tests/scripts/pre_commit.bats` gains these cases, using the existing `make`/`git`
  mocks and `MOCK_GIT_DIFF_NAMES`:
  - a staged `tests/test_x.py` calls `make -C <root> lint-python` exactly once;
  - `scripts/a.py` and `tests/b.py` staged together still call it once;
  - a staged `pi/pi.py` does not call it;
  - a staged `typings/gmpy2/__init__.pyi` calls it;
  - a failing `lint-python` (mock make failure injection on the root target) makes the
    hook exit non-zero.

### 2. `pre_push.bats` isolation

- `setup()` unsets the four `GIT_*` variables and exports
  `HOME="${BATS_TEST_TMPDIR}/home"` (created first), `GIT_CONFIG_GLOBAL=/dev/null` and
  `GIT_CONFIG_SYSTEM=/dev/null`, matching `pre_push_budget.bats`.
- Proof: the file passes in full under the hostile environment that failed tests 33 and
  41 above.

### 3. Refusal tests in `pre_push_budget.bats`

- **No base.** Push a line whose local sha is a well-formed 40-hex value that does not
  exist in the fixture. `git merge-base` and `git rev-list --max-parents=0` both fail.
  Assert:
  - rc 1;
  - stderr contains `refusing <sha>: cannot determine a base`;
  - the stub `make` was not called.
- **mktemp fails.** Make a compliant CLAUDE.md change, so the diff is non-empty and the
  checker exists. Put a `mktemp` stub that exits 1 in `${STUBS}`. Assert:
  - rc 1;
  - stderr contains `cannot create a temp file for the CLAUDE.md checker`;
  - output has no `CLAUDE.md byte ceiling OK` line, so the checker never ran.

### 4. Temp-file cleanup

- Make a compliant CLAUDE.md change, run the hook with `TMPDIR` set to an empty
  `${BATS_TEST_TMPDIR}/t`, and assert:
  - rc 0;
  - `CLAUDE.md byte ceiling OK` is printed;
  - `${BATS_TEST_TMPDIR}/t` is empty afterwards.
- Mutation control: with `rm -f "${tmp}"` deleted, the case fails.

### Docs

- `CLAUDE.md`: the Pre-commit line changes "on staged sub-projects" to "on staged
  sub-projects and root `.py`" (+17 bytes). The file is 29,980 bytes against the 30,000
  ceiling, so nothing longer fits. `ai-config/docs/knowledge/math-ci.md` carries the detail
  (owned by the ai-config session; message it).
- Backlog: remove the four rows.

## Requirements

- **R1.** `scripts/pre-commit` runs `make -C <repo root> lint-python` exactly once when any staged path matches `^(scripts|tests|\.claude/scripts|typings)/.*\.pyi?$`, and not when none does.
- **R2.** A failing root `lint-python` makes `scripts/pre-commit` exit non-zero, asserted by a bats case.
- **R3.** `tests/scripts/pre_push.bats` `setup()` unsets `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR` and `GIT_INDEX_FILE` and points `HOME` at a directory under `BATS_TEST_TMPDIR`.
- **R4.** A `pre_push_budget.bats` case pushes a nonexistent sha and asserts rc 1, `cannot determine a base` on stderr, and no `make` call.
- **R5.** A `pre_push_budget.bats` case with a failing `mktemp` stub asserts rc 1, `cannot create a temp file for the CLAUDE.md checker`, and no `CLAUDE.md byte ceiling OK` line.
- **R6.** A `pre_push_budget.bats` case asserts the hook leaves its `TMPDIR` empty after a compliant CLAUDE.md check.
- **V1.** `tests/scripts/pre_push.bats` passes in full with `HOME` read-only and `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` set to bogus paths.
- **V2.** Deleting `rm -f "${tmp}"` from `scripts/pre-push` makes the R6 case fail, and making `check_claude_md_budget`'s no-base branch `return` without refusing makes the R4 case fail.
- **V3.** This PR's CI is green.
- **N1.** No change to `scripts/pre-push` behaviour: its diff is empty.
- **N2.** pre-commit adds no lint for root shell, Makefile or workflow files.
- **N3.** No change to the root `Makefile`.
