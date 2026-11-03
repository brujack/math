# Worldclass Slice 1: CI Monitors Implementation Plan

> **Status: DONE** — merged in math#200 (5bb2bf4), 2026-11-03.

spec: docs/superpowers/specs/2026-11-03-worldclass-slice1-ci-monitors-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Rust mutation sweep's crate discovery (#195) and the single-unit close (#100), and add a CI-enforced actionlint gate with its 41 findings fixed.

**Architecture:** Discovery moves to its own workflow step tested by executing it. `mutation-notify.sh` gains a required `FULL_SWEEP` input. A root `lint-workflows` target runs actionlint, fails closed under `CI=true`, and is proven live by a SC2086 fixture; every bats-suite CI job installs the pinned binary.

**Tech Stack:** GitHub Actions YAML, bash, bats-core, Python unittest + PyYAML, actionlint 1.7.12, shellcheck 0.11.0.

## Global Constraints

- actionlint 1.7.12, tarball `actionlint_1.7.12_linux_amd64.tar.gz`, sha256 `8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8` (verified 2026-11-03 against the release checksums file).
- A local verified binary for gates: `AL=/tmp/claude-1000/-home-bruce-git-repos-personal-math/bdd39d1a-9669-445b-9954-63f2da67dffa/scratchpad/actionlint` (directory holding `actionlint`). Gates that need actionlint prepend it: `PATH="$AL:$PATH"`.
- Rendered workflows change only via `python3 scripts/render_crate_files.py --write` from `scripts/crate_templates/` (N4).
- No change to `scripts/pre-push` (N5), any crate `Makefile` `mutants` recipe (N1), or branch protection (N2).
- A coverage-data failure (worktree or push) never fails a CI job (N3).
- Top-level `$(shell git ...)` in the Makefile uses `env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git ...` (core.md ci-016).
- Shell style per core.md shell-006; tests per CLAUDE.md Testing Policy (boundary, error path, state transition).
- Suite timing: `make test-python` measured 32 s; `make test` (bats + python) is run once by the orchestrator after the last code task, not by wave members.

## Verification (session level)

- `PATH="$AL:$PATH" make lint` exits 0 (actionlint 0 findings over the repo; shellcheck, ruff clean).
- `PATH="$AL:$PATH" CI=true bats tests/scripts/makefile.bats --filter actionlint` passes with no skips.
- `make test` exits 0 with actionlint on PATH and again without it.
- Edge cases: `CI=true` with actionlint absent fails `lint-workflows`; a single-unit green run comments without closing; an empty crate list exits 1; a failed `coverage-data` worktree exits 0.
- After merge: V1-V3 of the spec.

---

### Task 1: Crate discovery step

```yaml-task
id: 1
description: Move Rust mutation crate discovery into a List crates step using git ls-files, tested by executing the step
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R4]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_workflows -v
    exit_code: 0
  - cmd: pyright tests/test_mutation_workflows.py
    exit_code: 0
  - cmd: '! command grep -nE "find .*Cargo.toml" .github/workflows/mutation-testing.yml'
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/mutation-testing.yml, tests/test_mutation_workflows.py]
depends_on: []
parallel_group: wave-1
```

**Change:** in `mutants` job add step `List crates` (`id: crates`, `env: CRATE: ${{ github.event.inputs.crate }}`) before `Run mutants`. Run block: if `CRATE` non-empty use it; else `git ls-files '*/*-rs/Cargo.toml'` → dirnames. Empty → existing "no crates found to test — refusing to report green" message, exit 1. Write exactly one line `printf 'crate_dirs=%s\n' "<space-joined>" >> "${GITHUB_OUTPUT}"`. `Run mutants` drops its discovery block, takes `CRATE_DIRS: ${{ steps.crates.outputs.crate_dirs }}` via `env:`, keeps the count line (quote it: fixes SC2086) and loop unchanged.

**Test** (new class in `tests/test_mutation_workflows.py`; load `mutation-testing.yml`, pick the step whose `id` is `crates`): helper runs `["bash", "-e", "-c", run]` with `cwd=REPO_ROOT`, env `PATH`, `GITHUB_OUTPUT`, `CRATE`, and `GIT_*` removed. Parse output: every non-empty line must match `^[A-Za-z_]+=.*$`, else fail. Cases: empty `CRATE` → 11 dirs equal to `git ls-files` dirnames, none `tests/`; positive control `git ls-files 'tests/fixtures/**/Cargo.toml'` non-empty; `CRATE=sq/sq-rs` → exactly `sq/sq-rs`; no `${{` in run; empty list (run with `PATH` holding a stub `git` printing nothing) → exit 1 and message in stderr; `Run mutants` env reads `steps.crates.outputs.crate_dirs`. Watch each fail first.

**Produces:** step id `crates`, output `crate_dirs` (space-joined).

### Task 2: FULL_SWEEP gate in mutation-notify

```yaml-task
id: 2
description: Require FULL_SWEEP in mutation-notify.sh, close only after a full sweep, comment on single-unit green, wire both workflows
role: executor
model: sonnet
tdd: required
requirements: [R5, R6, R7]
acceptance:
  - cmd: bats tests/scripts/mutation_notify.bats
    exit_code: 0
  - cmd: shellcheck scripts/mutation-notify.sh && shellcheck --severity=warning tests/scripts/mutation_notify.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-notify.sh, tests/scripts/mutation_notify.bats, .github/workflows/mutation-testing.yml, .github/workflows/mutation-testing-python.yml]
depends_on: [1]
```

**Change in `main()`:** add `: "${FULL_SWEEP:?FULL_SWEEP unset: the notify step must pass true or false}"` and a `case` rejecting anything but `true`/`false` with `printf 'FULL_SWEEP must be true or false, got: %s\n' ... >&2; return 1`. Success branch: `true` → unchanged; `false` → if `_existing` non-empty, `gh issue comment "${_existing}" --repo "${REPO}" --body "Single-unit run green as of ${RUN_URL}; left open (only a full sweep closes this issue)." || return 1`; never close; return 0. `check_expected_units` stays before it.

**Workflows:** each notify step that runs the script gets `FULL_SWEEP: ${{ format('{0}', inputs.crate) == '' && 'true' || 'false' }}` (Rust) and the same with `inputs.subproject` (Python). `format` makes a schedule run's null input read as empty.

**Tests:** add `export FULL_SWEEP=true` to `setup()` so the existing 40+ cases keep current behaviour. New cases: single-unit + open issue → exactly one `gh issue comment` with the single-unit text, zero `issue close`; single-unit + no issue → no calls after `issue list`; unset and `maybe` → exit 1 with message; failure + single unit still comments; single-unit comment failing (`MOCK_GH_EXIT_ISSUE_COMMENT=1`) → non-zero. Workflow case modelled on the `ISSUE_LABEL` test (line ~522): both notify steps declare `FULL_SWEEP`, each expression names its own input.

### Task 3: lint-workflows target and positive control

```yaml-task
id: 3
description: Add root lint-workflows (actionlint over WORKFLOWS, fail closed under CI=true) to lint, with a SC2086 fixture proving actionlint and shellcheck ran
role: executor
model: sonnet
tdd: required
requirements: [R8, R10]
acceptance:
  - cmd: 'PATH="/tmp/claude-1000/-home-bruce-git-repos-personal-math/bdd39d1a-9669-445b-9954-63f2da67dffa/scratchpad/actionlint:$PATH" CI=true bats tests/scripts/makefile.bats --filter actionlint'
    exit_code: 0
  - cmd: bats tests/scripts/makefile.bats --filter actionlint
    exit_code: 0
  - cmd: '[ "$(bats --count --filter actionlint tests/scripts/makefile.bats)" -ge 4 ]'
    exit_code: 0
  - cmd: make lint-hooks
    exit_code: 0
max_retries: 3
files_touched: [Makefile, tests/fixtures/actionlint/sc2086.yml, tests/scripts/makefile.bats]
depends_on: []
parallel_group: wave-1
```

**Makefile:** `ACTIONLINT := $(shell command -v actionlint 2>/dev/null)`; `WORKFLOWS ?= $(shell env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git ls-files '.github/workflows/*.yml')`; target `lint-workflows`: absent + `CI=true` → `printf 'lint-workflows: actionlint not found and CI=true; install actionlint 1.7.12\n' >&2; exit 1`; absent otherwise → `printf "actionlint not found, skipping (install: https://github.com/rhysd/actionlint/releases/tag/v1.7.12)\n"`; present → `actionlint $(WORKFLOWS)`. Empty `WORKFLOWS` with actionlint present → exit 1 naming it. Add to `.PHONY`; `lint: lint-hooks lint-python lint-workflows`.

**Fixture:** minimal valid workflow (`on: push`, one job, one step) whose `run:` is `echo $UNQUOTED` style (SC2086).

**bats** (names contain `actionlint`, so `--filter actionlint` selects them): (a) fixture → non-zero, output contains `SC2086`; skip with message when actionlint or shellcheck absent unless `CI=true`, in which case `fail`; (b) PATH without actionlint + `CI=true` → non-zero, stderr names it; (c) PATH without actionlint, `CI` unset → 0, remedy text; (d) `make -n lint` lists `lint-workflows`. Build the actionlint-free PATH by filtering directories that contain `actionlint`, keeping `make`/`shellcheck`. Do not run `lint-workflows` over the real workflows here (Task 4 owns that).

### Task 4: Fix the badge step findings

```yaml-task
id: 4
description: Rewrite the coverage badge worktree logic as advisory if/else with _ retry var in both templates, re-render, prove actionlint is clean
role: executor
model: sonnet
tdd: required
requirements: [R11, R12, R13]
acceptance:
  - cmd: python3 -m unittest tests.test_coverage_badge_step tests.test_crate_uniformity -v
    exit_code: 0
  - cmd: 'PATH="/tmp/claude-1000/-home-bruce-git-repos-personal-math/bdd39d1a-9669-445b-9954-63f2da67dffa/scratchpad/actionlint:$PATH" make lint-workflows'
    exit_code: 0
  - cmd: pyright tests/test_coverage_badge_step.py
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/ci.yml, scripts/crate_templates/python/py.yml, tests/test_coverage_badge_step.py, .github/workflows/amicable-rs.yml, .github/workflows/collatz-rs.yml, .github/workflows/e-rs.yml, .github/workflows/factorial-rs.yml, .github/workflows/fib-rs.yml, .github/workflows/goldbach-rs.yml, .github/workflows/perfect-numbers-rs.yml, .github/workflows/pi-rs.yml, .github/workflows/prime-rs.yml, .github/workflows/sq-rs.yml, .github/workflows/twin-primes-rs.yml, .github/workflows/amicable-py.yml, .github/workflows/collatz-py.yml, .github/workflows/e-py.yml, .github/workflows/factorial-py.yml, .github/workflows/fib-py.yml, .github/workflows/perfect-numbers-py.yml, .github/workflows/pi-py.yml, .github/workflows/sq-py.yml, .github/workflows/triangle-py.yml]
depends_on: [1, 3]
```

**Template change** (`ci.yml:143-145`, `py.yml:90-92`), replacing the `&& ||` chain:

```bash
          if git fetch origin coverage-data 2>/dev/null; then
            git worktree add /tmp/cov-data coverage-data \
              || { echo "coverage-data worktree unavailable; badge not published"; exit 0; }
          else
            git worktree add -b coverage-data --orphan /tmp/cov-data \
              || { echo "coverage-data worktree unavailable; badge not published"; exit 0; }
          fi
```

and `for i in 1 2 3` → `for _ in 1 2 3`. Then `python3 scripts/render_crate_files.py --write`.

**Test** `tests/test_coverage_badge_step.py`: for `amicable-rs.yml` and `amicable-py.yml`, extract the `Publish coverage badge` run and execute it with `bash -e -c` in a temp dir, `HOME` set to it, and `PATH` starting with a stub-bin dir. Stubs only, so nothing touches a real remote or writes outside the temp dir: `python3` exits 0 for `-m coverage ...` and prints `95` for `-c ...`; `git` appends argv to a log and exits `STUB_FETCH_RC` for `fetch`, `STUB_WORKTREE_RC` for `worktree`, `STUB_PUSH_RC` for `push`, `STUB_DIFF_RC` for `diff`, else 0; `sleep` exits 0. Cases: fetch 0 + worktree 1 → exit 0, stdout has `badge not published`, no `push` and no `pull` in the log; fetch 1 + worktree 1 → same, log shows the `--orphan` add; fetch 0 + worktree 0 + `STUB_PUSH_RC=1` (stub `git diff --staged --quiet` exits 1 so the loop runs; stub `sleep` exits 0 at once) → exit 0 with exactly 3 `push` lines logged (N3, push half: the loop's last command is `sleep`, and a failed `git push ... && break` does not trip `-e`); each case fails against the pre-change template first (old chain aborts under `-e` or proceeds to `push`).

### Task 5: Install actionlint in every bats-suite job

```yaml-task
id: 5
description: Pinned checksummed actionlint install in scripts.yml and auto-merge.yml bash-coverage, scripts.yml paths widened, pinned by a test
role: executor
model: sonnet
tdd: required
requirements: [R9, R14]
acceptance:
  - cmd: python3 -m unittest tests.test_actionlint_install tests.test_workflow_downloads_verified tests.test_crate_uniformity tests.test_python_workflow_paths tests.test_gmp_cache_workflow -v
    exit_code: 0
  - cmd: pyright tests/test_actionlint_install.py
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/scripts.yml, .github/workflows/auto-merge.yml, tests/test_actionlint_install.py]
depends_on: []
parallel_group: wave-1
```

**Step** (after `Install shellcheck (pinned)` in both jobs), same shape as the shellcheck step so `test_workflow_downloads_verified.py` accepts it:

```yaml
- name: Install actionlint (pinned)
  env:
    AL_VER: "1.7.12"
    AL_SHA256: "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
  run: |
    curl -fsSL -o /tmp/actionlint.tar.gz \
      "https://github.com/rhysd/actionlint/releases/download/v${AL_VER}/actionlint_${AL_VER}_linux_amd64.tar.gz"
    echo "${AL_SHA256}  /tmp/actionlint.tar.gz" | sha256sum -c -
    tar -xzf /tmp/actionlint.tar.gz -C /tmp actionlint
    sudo install -m755 /tmp/actionlint /usr/local/bin/actionlint
    actionlint --version | head -1 | grep -qx "${AL_VER}"
```

`scripts.yml` `paths:`: add `".github/workflows/**"`. Keep the existing per-file workflow entries: `tests/test_gmp_cache_workflow.py:312` pins `.github/workflows/gmp-cache.yml` by exact membership, and removing entries is not needed for R9.

**Test** `tests/test_actionlint_install.py`, modelled on `TestBatsJobsInstallCargoDeny` in `tests/test_deny_policy.py` (reuse its `_BATS_SUITE` regex by import or copy): every job whose steps run the bats suite has a step whose `run` installs actionlint and whose `env.AL_VER` is `1.7.12`; checked ≥2 jobs; the install step comes after the shellcheck step in each; `scripts.yml` `on.pull_request.paths` (PyYAML loads `on` as `True`) contains `.github/workflows/**`. Watch each fail first.

### Task 6: Docs

```yaml-task
id: 6
description: Update CLAUDE.md and the superpowers index/Backlog for lint-workflows, FULL_SWEEP and crate discovery (docs-only, no behaviour change)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: command grep -q 'lint-workflows' CLAUDE.md
    exit_code: 0
  - cmd: command grep -q 'FULL_SWEEP' CLAUDE.md
    exit_code: 0
  - cmd: '[ "$(wc -c < CLAUDE.md)" -le 30000 ]'
    exit_code: 0
  - cmd: '! command grep -q "^| actionlint is not run anywhere" docs/superpowers/README.md'
    exit_code: 0
max_retries: 2
files_touched: [CLAUDE.md, docs/superpowers/README.md]
depends_on: [1, 2, 3, 4, 5]
```

**CLAUDE.md** (one line per rule; check the 30,000-byte cap): root `make lint` runs `lint-workflows` (actionlint 1.7.12, skips locally when absent, fails under `CI=true`; every bats-suite CI job installs it, pinned by `tests/test_actionlint_install.py`); `mutation-notify.sh` needs `FULL_SWEEP` and only a full sweep closes the tracking issue; `mutation-testing.yml` derives crates with `git ls-files '*/*-rs/Cargo.toml'` in its `List crates` step. Edit the existing mutation-notification and pre-commit/lint lines in place rather than adding beside them. **README:** delete the `actionlint is not run anywhere` Backlog row; set the plan-index row for this slice to link the plan, status `In progress`.

## Orchestrator steps

- [ ] After Task 5 (wave close) and again after Task 6: `PATH="$AL:$PATH" make test </dev/null` and `make test </dev/null`, both exit 0.
- [ ] `rm -rf .cache`; Phase 3 via `finishing-a-development-branch`; open the PR as a draft with `Closes #100`; `gh pr ready` only after Phase 3 passes.

## Non-goal check

Reviewer verdicts (fresh subagent, `nongoal-check.md`): N1 CLEAR, N2 CLEAR, N4 CLEAR, N5 CLEAR.

- **N3 UNCLEAR** — quote: "Task 4: `for i in 1 2 3` → `for _ in 1 2 3` ... Cases: fetch 0 + worktree 1 → exit 0 ... fetch 1 + worktree 1 → same"; nothing tested a push that fails all three retries. Resolution (plan revision): Task 4 test gains the case "fetch 0 + worktree 0 + `STUB_PUSH_RC=1` → exit 0 with exactly 3 `push` lines", and the git stub gains `STUB_PUSH_RC`/`STUB_DIFF_RC` and a `sleep` stub. Before: cases covered only the worktree half. After: both halves of N3 are tested.
