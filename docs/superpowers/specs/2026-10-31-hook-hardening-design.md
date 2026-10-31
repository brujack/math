# Hook hardening — design

Date: 2026-10-31. Repo: math. Source: four Backlog rows in `docs/superpowers/README.md`:

- `scripts/pre-commit` never lints a staged root-scope `.py`.
- `tests/scripts/pre_push.bats` `setup()` does not isolate `HOME` or `GIT_*`.
- `scripts/pre-push` "cannot determine a base" and mktemp-failure refusals are untested.
- `scripts/pre-push` checker temp-file `rm -f` is unpinned.

The operator chose to ship the four as one spec, one plan and one PR.

- **Approved:** 2026-10-31

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
- `lint-python` must degrade to its skip message when ruff is not runnable, or this
  route locks a machine out of committing (core.md shell-004). Today it does not under
  pyenv: the root `Makefile` sets `RUFF := $(shell command -v ruff 2>/dev/null)`, and
  `command -v` finds `~/.pyenv/shims/ruff` even when the active Python has no ruff.
  Measured on `claude` with `PYENV_VERSION` unset: `make -s lint-python` fails with
  pyenv's `ruff: command not found` and `Error 127`. The workstation and Studio have no
  ruff at all and print the skip message. So the detection line becomes
  `RUFF := $(shell ruff --version >/dev/null 2>&1 && command -v ruff)`, which treats an
  unrunnable shim as absent. Two `tests/scripts/makefile.bats` cases cover it. Both run
  under `env -u MAKEFLAGS -u MAKELEVEL` with no `RUFF=` override. Every existing ruff case
  forces `RUFF`, so none of them ever reaches the detection line.
  - Negative: a `ruff` stub that exits 127 sits first on `PATH`. Real `make lint-python`
    prints `ruff not found, skipping` and exits 0. With the old line it exits 2 on
    `Error 127` (measured).
  - Positive: a `ruff` stub whose `--version` exits 0 sits first on `PATH`.
    `make -n lint-python` shows `ruff check` and does not show `ruff not found`. This
    kills a detection line that never finds ruff. Without it, CI's `make lint` would print
    the skip message and go green while root Python went unlinted.
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

- **No base.** Push an existing branch whose local sha is a well-formed 40-hex value that
  does not exist in the fixture, with the fixture's real HEAD as the remote sha. Both
  `git merge-base` and `git rev-list --max-parents=0` fail. Assert rc 1 and stderr
  containing `refusing <sha>: cannot determine a base`.
  - The remote sha matters. With the file's usual all-zeros remote sha, the hook prints
    the refusal and then exits 128: its main loop runs its own base lookup under
    `set -e`. Measured in a scratch fixture by two lenses.
  - That 128 is existing behaviour and fails closed. N1 keeps `scripts/pre-push`
    unchanged, so it is recorded here and not fixed.
  - Outside a corrupt repo the branch is defensive: git only sends local shas, and
    `rev-list --max-parents=0` finds a root for any of them. The test guards against a
    refactor that makes the branch fall through.
- **mktemp fails.** Make a compliant CLAUDE.md change, so the diff is non-empty and the
  checker exists. Put a `mktemp` stub that exits 1 in `${STUBS}`. Assert rc 1 and stderr
  containing `cannot create a temp file for the CLAUDE.md checker`.
- Not asserted, because they cannot fail: "no `make` call" on the no-base case (the
  missing sha matches no paths) and "no ceiling-OK line" on the mktemp case (every
  broken variant also prints none). Each case's rc and specific message do the work, and
  V2's mutations prove it.

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
- Backlog: remove the four rows. Add one: the sub-project Python `Makefile` template runs
  `ruff check .` unguarded, so on a pyenv-shim machine with no ruff behind the shim,
  committing a staged `pi/*.py` already fails `make lint` with 127 (found by the round-2
  risk lens; outside N3).

## Requirements

- **R1.** `scripts/pre-commit` runs `make -C <repo root> lint-python` exactly once when any staged path matches `^(scripts|tests|\.claude/scripts|typings)/.*\.pyi?$`, and not when none does.
- **R2.** A failing root `lint-python` makes `scripts/pre-commit` exit non-zero, asserted by a bats case.
- **R3.** `tests/scripts/pre_push.bats` `setup()` unsets `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR` and `GIT_INDEX_FILE` and points `HOME` at a directory under `BATS_TEST_TMPDIR`.
- **R4.** A `pre_push_budget.bats` case pushes a nonexistent local sha with an existing remote sha and asserts rc 1 and `cannot determine a base` on stderr.
- **R5.** A `pre_push_budget.bats` case with a failing `mktemp` stub asserts rc 1 and `cannot create a temp file for the CLAUDE.md checker` on stderr.
- **R6.** A `pre_push_budget.bats` case asserts the hook leaves its `TMPDIR` empty after a compliant CLAUDE.md check.
- **R7.** The root `Makefile` sets `RUFF` only when `ruff --version` succeeds. `tests/scripts/makefile.bats` asserts both directions with no `RUFF=` override: a `ruff` stub exiting 127 first on `PATH` gives `ruff not found, skipping` and rc 0; a stub whose `--version` exits 0 gives `ruff check` in `make -n lint-python` and no `ruff not found`.
- **V1.** `tests/scripts/pre_push.bats` passes in full with `HOME` read-only and `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` set to bogus paths.
- **V2.** Deleting `rm -f "${tmp}"` from `scripts/pre-push` makes the R6 case fail, and making `check_claude_md_budget`'s no-base branch `return` without refusing makes the R4 case fail.
- **V3.** This PR's CI is green, and the `scripts.yml` log for `make lint` shows `ruff check` and not `ruff not found`.
- **N1.** No change to `scripts/pre-push` behaviour: its diff is empty.
- **N2.** pre-commit adds no lint for root shell, Makefile or workflow files.
- **N3.** No change to the root `Makefile` beyond the `RUFF :=` detection line.

## Multi-Lens Review

Reviewed at commit: `4a2c56c` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: R4 cannot pass with the file's usual all-zeros remote sha: the hook refuses, then exits 128 at the main loop's base lookup under `set -e` (measured in a scratch fixture). Two assertions cannot fail, R4's "no `make` call" and R5's "no ceiling-OK line". Otherwise all four items are worth doing and there is no simpler path. R6's mutation control was measured: removing `rm -f` leaves the 3,253-byte checker copy behind.
Assumption: no genuinely uncertain one. The closest is that the no-base branch is reachable by a real push; the lens expects it is not (git sends only local shas, and `rev-list --max-parents=0` finds a root even in a shallow clone), so the R4 test guards against a refactor.
Disposition: Addressed — operator chose "fix wording": R4 uses an existing remote sha, and R4/R5 drop their unfailable assertions. The 128 is recorded as existing behaviour under N1.

### Ergonomics

Finding: under pyenv, the root `Makefile`'s `command -v ruff` finds a shim with no ruff behind it. On `claude` with `PYENV_VERSION` unset, `make -s lint-python` exits 127, which the spec would move onto every root-Python commit. The workstation and Studio have no ruff and print the skip message. Latency is 0.21–0.27 s per run; `.worktrees/` is not linted.
Assumption: "ruff absent" and "ruff not runnable" behave the same. Refuted on `claude`; the author measured the other two machines over ssh (skip message).
Disposition: Addressed — operator chose to fix the Makefile detection (R7, N3 narrowed to allow that one line).

### Risk

Finding: same R4 rc-128 defect. Mock injection on the root target works (`MOCK_MAKE_FAIL_DIR=fake-root`). The `mktemp` stub shadows the real one, and only `pre-push:85` calls it. `TMPDIR` stays empty, and the mutation control kills the mutant. No test relies on `~/.gitconfig`.
Assumption: settled by measurement (rc 128 with zeros, rc 1 with an existing remote sha).
Disposition: Addressed — as Goal-Fit.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

### Round 2 (scoped Risk)

Reviewed at commit: `72e6ac5`, covering section 1's ruff paragraph, section 3, R4, R5, R7 and N3.

Risk: Finding: R7 checked only the "absent" direction. The mutant `RUFF :=` (always empty) passes R7 and every existing case, because all of them force `RUFF=`. CI's `make lint` would then print `ruff not found, skipping` and go green. Fix: add a positive case. Also verified:
- The old line fails R7's negative case (rc 2, `Error 127`).
- R4 with an existing remote sha reaches rc 1 with the refusal and `push refused`, and the V2 mutant is killed.
- No existing makefile.bats case breaks.
- CI is unchanged.
- The probe costs about 0.05 s per root make parse.
Assumption: none uncertain; V3 now confirms the CI side.
Disposition: Addressed (fix in text, apparatus-level). R7 and the design now require the positive case, V3 checks the CI log, and a Backlog row records the unguarded sub-project template. Review stops here: the finding sits in the test apparatus, and this round changed nothing in the design.

## Amendments

- finding R4 (2026-10-31, reviewer A): DIFFERS — The case at tests/scripts/pre_push_budget.bats:227 pushes a fake local sha against an existing remote sha (head_sha) and asserts rc 1, but checks `cannot determine a base` in bats `${output}` (merged stdout+stderr unless run_hook separates them, which this diff does not show), so it does not assert the message is on stderr as the requirement says.
- R4 -> A `pre_push_budget.bats` case pushes a nonexistent local sha with an existing remote sha and asserts rc 1 and `cannot determine a base` in the hook's output. — bats `run` merges stdout and stderr, as every case in this file does; the refusal prints to stderr, and the V2 mutation shows the case fails when it is removed.
- finding R5 (2026-10-31, reviewer A): DIFFERS — The case at tests/scripts/pre_push_budget.bats:236 stubs mktemp to exit 1 and asserts rc 1 and the message text, but against `${output}` rather than stderr, so the stream the requirement names is not asserted.
- R5 -> A `pre_push_budget.bats` case with a failing `mktemp` stub asserts rc 1 and `cannot create a temp file for the CLAUDE.md checker` in the hook's output. — bats `run` merges stdout and stderr, as every case in this file does; the refusal prints to stderr, and the Task 4 mutation shows the case fails when the guard is removed.

## Spec alignment (2026-10-31)

- spec: docs/superpowers/specs/2026-10-31-hook-hardening-design.md
- anchor: 05ed27f2a4c8384a7895f5508ce1fa0136ef7696
- in scope: R1, R2, R3, R4, R5, R6, R7
- out of scope: none

### Findings

| ID | Reviewer | Verdict | Reason | Amendment |
| --- | --- | --- | --- | --- |
| R4 | A | DIFFERS | The case at tests/scripts/pre_push_budget.bats:227 pushes a fake local sha against an existing remote sha (head_sha) and asserts rc 1, but checks `cannot determine a base` in bats `${output}` (merged stdout+stderr unless run_hook separates them, which this diff does not show), so it does not assert the message is on stderr as the requirement says. | - R4 -> A `pre_push_budget.bats` case pushes a nonexistent local sha with an existing remote sha and asserts rc 1 and `cannot determine a base` in the hook's output. — bats `run` merges stdout and stderr, as every case in this file does; the refusal prints to stderr, and the V2 mutation shows the case fails when it is removed. |
| R5 | A | DIFFERS | The case at tests/scripts/pre_push_budget.bats:236 stubs mktemp to exit 1 and asserts rc 1 and the message text, but against `${output}` rather than stderr, so the stream the requirement names is not asserted. | - R5 -> A `pre_push_budget.bats` case with a failing `mktemp` stub asserts rc 1 and `cannot create a temp file for the CLAUDE.md checker` in the hook's output. — bats `run` merges stdout and stderr, as every case in this file does; the refusal prints to stderr, and the Task 4 mutation shows the case fails when the guard is removed. |

### Reviewed

- none

### Verifications

- V1: orchestrator ran pre_push.bats with read-only HOME and bogus GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE in a scratchpad dir: rc 0, 47 ok (2026-10-31)
- V2: scratch-copy mutations: rm -f removal fails test 16 only (orchestrator); no-base return-0 fails 14, mktemp guard removal fails 15 (Task 4 implementer)
- V3: pending: PR CI
