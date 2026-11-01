# Python Makefile Template Hardening Implementation Plan

spec: docs/superpowers/specs/2026-10-31-python-makefile-template-hardening-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Python `make lint` skip when ruff is not runnable, and make `make mutants` mutate a three-file scratch copy so an interrupted run never leaves a mutant in the source.

**Architecture:** Work on branch `fix/python-makefile-hardening` in `.worktrees/python-makefile`: three sequential tasks and one draft PR. The work is all in `scripts/crate_templates/python/Makefile`, rendered with `python3 scripts/render_crate_files.py --write` to the 8 project Makefiles, and in `tests/scripts/makefile.bats` (harness `_py_stub_setup`, helpers `_py_make`, `_calls_line`, `_assert_no_call`).

**Tech Stack:** GNU make, bash, bats, cosmic-ray 8.7.0, ruff 0.16.4.

## Global Constraints

- No change to `mutants-baseline`, `cosmic-ray.toml`, `scripts/mutation-python-cell.sh` or any workflow (N1).
- No change to the Rust template or any Rust crate (N2).
- No change to `CLAUDE.md` (N3). It is 29,995 bytes against a 30,000 cap.
- Edit only the template. Then run `render_crate_files.py --write` and never hand-edit a rendered Makefile. `tests/test_crate_uniformity.py` must pass.
- Run every gate synchronously, with `< /dev/null` and Bash `timeout: 600000`. Run `make lint` after `git add`.
- Never put `rm -rf` inside `bash -c` in a gate command: the harness safety check refuses it. Scratch copies are cleaned up with `rm -r`.
- **Session verification** (orchestrator, after Task 3):
  - `make lint && make test` pass in the worktree.
  - V1: in a `git archive` scratch copy committed to a fresh git repo, `cd fib && timeout -s TERM 25 make mutants` and `timeout -s KILL 25 make mutants` each leave `git diff --stat -- fib/fib.py` empty.
  - V2: PR CI is green on all 8 `*-py.yml`.
  - V3 waits for the next scheduled mutation run.

## Orchestrator steps

1. `git worktree add .worktrees/python-makefile -b fix/python-makefile-hardening origin/master`.
2. Dispatch Tasks 1-3 in order. Each prompt starts: **IMPORTANT: All work must happen in `/home/bruce/git-repos/personal/math/.worktrees/python-makefile/`. Do not cd anywhere else.**
3. Run the session verification above.
4. Run Phase 3.
5. Push and open the PR with `gh pr create --draft`.
6. Run `gh pr checks <n> --watch`. Once CI is green, run `gh pr ready <n>`.
7. After merge, message the ai-config session: `math-testing-policy.md` § Mutation testing should say that the local run works in a scratch copy.

---

### Task 1: sub-project `lint` guards ruff

```yaml-task
id: 1
description: Set RUFF in the Python template only when ruff --version succeeds and make lint skip with the root remedy message otherwise, with makefile.bats cases in both directions
role: executor
model: sonnet
tdd: required
requirements: [R4]
acceptance:
  - cmd: bats tests/scripts/makefile.bats < /dev/null
    exit_code: 0
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: python3 -m unittest tests.test_crate_uniformity
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/python/Makefile, tests/scripts/makefile.bats, amicable/Makefile, collatz/Makefile, e/Makefile, factorial/Makefile, fib/Makefile, perfect-numbers/Makefile, pi/Makefile, sq/Makefile]
depends_on: []
```

- [ ] **RED.** Add two cases to `tests/scripts/makefile.bats`. Both run against `fib/Makefile` (rendered) via `env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS PATH="${stub}:${PATH}" make -C "${REPO_ROOT}/fib" ...`, with no `RUFF=`. Model them on the root cases `"lint-python skips when ruff is on PATH but not runnable"` and `"lint-python runs ruff when ruff answers --version"`.
  - Case 1: the stub `ruff` is `exit 127`. Run the real `make lint`. Expect rc 0, `ruff not found, skipping` in the output, and no `Error 127`.
  - Case 2: the stub `ruff` is `exit 0`. Run `make -n lint`. Expect `ruff check` in the output and no `ruff not found`.
  - The first case fails today. The second is a regression pin and passes today.
- [ ] **GREEN.** In the template, add `RUFF := $(shell ruff --version >/dev/null 2>&1 && command -v ruff)` near the top. Make `lint:` an `ifdef RUFF` block that runs the two existing ruff lines. In the `else` branch, run `@printf "ruff not found, skipping (install: pip install ruff==0.16.4)\n"`. Then run `python3 scripts/render_crate_files.py --write`.
- [ ] Run the gates. Commit `fix(make): skip python lint when ruff is not runnable`.

### Task 2: `make mutants` runs in a three-file scratch copy

```yaml-task
id: 2
description: Rewrite the Python mutants recipe to run init/shard/exec/cr-report in a mktemp scratch copy of only the module, test and config, copy results back in-band before status and via an EXIT cleanup that keeps scratch on copy failure, and extend the makefile.bats harness and cases
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R5]
acceptance:
  - cmd: bats tests/scripts/makefile.bats < /dev/null
    exit_code: 0
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: python3 -m unittest tests.test_crate_uniformity
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/python/Makefile, tests/scripts/makefile.bats, amicable/Makefile, collatz/Makefile, e/Makefile, factorial/Makefile, fib/Makefile, perfect-numbers/Makefile, pi/Makefile, sq/Makefile]
depends_on: [1]
```

- [ ] **Harness, all python mutants tests.** Change `_py_stub_setup` as the spec's "Harness changes" bullet says:
  - Write the `fib.py`, `test_fib.py` and `cosmic-ray.toml` stubs into `${STUBDIR}`.
  - Make the stub `cosmic-ray` append `pwd=$PWD`, and give it `STUB_INIT_RC`.
  - Give the stub `exec` opt-in behaviours, selected by env:
    - `STUB_EXEC_MUTATE=1` appends `MUTATED` to `fib.py` in its cwd;
    - `STUB_EXEC_SESSION=1` writes `cosmic-ray-session.sqlite` containing `S`;
    - `STUB_EXEC_LS=1` records `ls -A`;
    - `STUB_EXEC_DANGLE=1` runs `ln -s /nonexistent/x "${STUBDIR}/mutants-report.txt"`.
  - Make the stub `cr-report` write `mutants-report.txt` when its stdout is redirected.
  - Make the stub `python3` record, in its `cosmic_ray_cell_status` branch, `pwd`, `test -f cosmic-ray-session.sqlite` and the session's content.
  - Add a `^cosmic-ray init` assertion to "exits non-zero and skips status when exec fails" and to "stops when the shard script fails".
- [ ] **RED.** Add the spec's Tests cases. Each sets `TMPDIR="${BATS_TEST_TMPDIR}/t"` (created empty first).
  - **Source untouched on failure.** Run with `STUB_EXEC_MUTATE=1` and `STUB_EXEC_RC=1`. Assert:
    - rc ≠ 0;
    - the recorded exec `pwd` is under `${BATS_TEST_TMPDIR}/t/`;
    - `cmp` of `fib.py` against its pre-run copy succeeds.
  - **Outputs copied back before status.** Run with `STUB_EXEC_SESSION=1` and a successful run. Assert:
    - the status `pwd` is `${STUBDIR}`, and it saw the session with content `S`;
    - both files are in `${STUBDIR}`;
    - `t` is empty.
  - **Partial session kept on failure.** Run with `STUB_EXEC_SESSION=1` and `STUB_EXEC_RC=1`. Assert:
    - the exec `pwd` is under `t`;
    - the session is in `${STUBDIR}`;
    - `t` is empty.
  - **Scratch kept when copy-back fails.** Run with `STUB_EXEC_SESSION=1`, `STUB_EXEC_DANGLE=1` and `STUB_EXEC_RC=1`. Assert:
    - rc ≠ 0;
    - the output contains `mutants: kept`;
    - `t` is not empty.
  - **Stale outputs removed.** Pre-create `${STUBDIR}/mutants-report.txt` containing `OLD`, then run with `STUB_INIT_RC=1`. Assert `${STUBDIR}/mutants-report.txt` is absent.
  - **Only three files.** Create `${STUBDIR}/fib-rs/target/big` and run with `STUB_EXEC_LS=1`. The recorded listing is exactly `cosmic-ray.toml fib.py test_fib.py`.

  Run the file; these cases fail today.

- [ ] **GREEN.** Rewrite the template's `mutants:` recipe. Keep the `MUTANTS_CAP`, the shard validation and the `|| exit 1` on every step. The order is:
  - `proj="$$(pwd)"`
  - `rm -f cosmic-ray-session.sqlite mutants-report.txt || exit 1`
  - `work="$$(mktemp -d "$${TMPDIR:-/tmp}/mutants-@CRATE@.XXXXXX")" || exit 1`
  - a `cleanup()` function that, using absolute `"$$work/@CRATE@/..."` paths:
    - copies `cosmic-ray-session.sqlite*` back when the db exists;
    - copies `mutants-report.txt` back when it exists;
    - runs `rm -rf -- "$$work"` only if every copy succeeded, and otherwise prints `mutants: kept %s (copy-back failed)\n` to stderr;
  - `trap cleanup EXIT`
  - `mkdir "$$work/@CRATE@"`
  - `cp -- @MODULE@.py test_@MODULE@.py cosmic-ray.toml "$$work/@CRATE@/"`
  - `ln -s "$$(cd .. && pwd)/scripts" "$$work/scripts"`
  - `cd "$$work/@CRATE@"`
  - the existing `init`, shard, `exec` and both `cr-report` calls
  - `cp -- cosmic-ray-session.sqlite mutants-report.txt "$$proj/"`
  - `cd "$$proj"`
  - the existing `set --` argument build, then `python3 ../scripts/cosmic_ray_cell_status.py "$$@"`, **without `exec`**

  Run `render_crate_files.py --write`.

- [ ] **Mutation control.** In a scratch copy (`mktemp -d` plus `git archive HEAD | tar -x`), edit the copy's template so `init`/`exec` run in the project directory, not scratch. Re-render, and confirm "source untouched" fails. Repeat with `rm -rf -- "$$work"` made unconditional, and confirm "scratch kept" fails. Report both. Remove the copy with `rm -r`.
- [ ] Run the gates. Commit `fix(make): run python mutants in a scratch copy`.

### Task 3: Backlog

```yaml-task
id: 3
description: Remove the two shipped Backlog rows (docs-only, no behaviour change, so TDD does not apply)
role: executor
model: sonnet
tdd: not-applicable
requirements: []
acceptance:
  - cmd: bash -c '! grep -q "Interrupted local .make mutants. leaves mutated source" docs/superpowers/README.md'
    exit_code: 0
  - cmd: bash -c '! grep -q "template runs ruff unguarded" docs/superpowers/README.md'
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [docs/superpowers/README.md]
depends_on: [2]
```

- [ ] In the Backlog of `docs/superpowers/README.md`, delete the rows whose first cells begin "Interrupted local `make mutants` leaves mutated source" and "Sub-project Python `Makefile` template runs ruff unguarded". Grep before and after. Commit `docs: close python makefile backlog rows`.

## Non-goal check

Reviewer verdicts (3 CLEAR, 0 CONFLICT, 0 UNCLEAR):

- N1 CLEAR — only the `mutants:` recipe changes. `mutants-baseline`, `cosmic-ray.toml` (copied, not edited), `mutation-python-cell.sh` and the workflows are untouched. The mutation control edits a throwaway copy.
- N2 CLEAR — every touched file is the Python template, the 8 rendered Python Makefiles, `makefile.bats` or `docs/superpowers/README.md`.
- N3 CLEAR — no task touches `CLAUDE.md`.

Resolution: none needed.
