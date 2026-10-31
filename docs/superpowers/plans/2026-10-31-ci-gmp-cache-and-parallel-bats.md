# GMP Cache and Parallel Bats Implementation Plan

> **Status: DONE** (math#186, merged 15c0c7c)

spec: docs/superpowers/specs/2026-10-31-ci-gmp-cache-and-parallel-bats-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the five `rug` crates rebuilding GMP/MPFR from C in every CI coverage and build job, and run the CI bats suite in parallel.

**Architecture:** One key script (`scripts/gmp-cache-key.sh`) is the only source of the cache key. A new master-scoped `gmp-cache.yml` builds `gmp-mpfr-sys` and saves its cache weekly; every rendered crate job restores it read-only and fails open. `scripts.yml` runs `bats --jobs 8`.

**Tech Stack:** bash, bats-core, GitHub Actions (`actions/cache` v6.1.0), Python `unittest` + `yaml.safe_load`.

## Global Constraints

- Pin `actions/cache/restore` and `actions/cache/save` as `@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0` (released 2026-06-26).
- `GMP_MPFR_SYS_CACHE` is `${{ runner.temp }}/gmp-mpfr-sys` in every job that sets it.
- Key: `prefix=gmp-mpfr-sys-<sorted unique versions joined by _>-${RUNNER_OS}-${ImageOS}-`, `key=<prefix><date -u +%G-W%V, or GMP_CACHE_WEEK>`.
- Crate jobs: script without `--strict`, restore only `if: steps.gmpkey.outputs.enabled == 'true'`, never save (R4).
- Edit `scripts/crate_templates/ci.yml` and run `python3 scripts/render_crate_files.py --write`; never hand-edit a rendered `*-rs.yml` (N3).
- No change to `release-*-rs.yml` (N4), the rust-cache steps (N2), or crate workflow triggers (N1).
- Shell follows `~/.claude/standards/shell.md` via `core.md` shell-006: `#!/usr/bin/env bash`, no `set -e`, `[[ ]]`, `${VAR}`, `printf`, `readonly`, top-level `|| exit 1`; git calls use `env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git` (shell-007).
- Root `make test` takes 46 s on `claude` (measured at plan time, rc 0), below the 600 s Bash cap.

## Verification

- Tasks 2 and 3 form wave-2 (disjoint files, both after Task 1) and carry scoped gates; the orchestrator runs `make test </dev/null` once at wave close and again after Task 4.

- Session gate: `make test </dev/null` from the worktree root exits 0; `make validate-plan` exits 0.
- On the PR: the `scripts` job log shows `bats --jobs 8 --recursive tests/` and passes (V3); every crate job's key step shows `enabled=true` and a restore miss (no master entry yet) without failing.
- After merge: dispatch `gmp-cache.yml` on master; it saves key `gmp-mpfr-sys-1.7.0_1.7.1-Linux-ubuntu26-<week>` (V1). Next rug-crate PR: GMP restore hit, under 20 s from `Compiling rug` to the next `Compiling` line (V2).
- Edge cases: empty `ImageOS` (crate job stays green, warm job fails), duplicate versions, no lockfile naming `gmp-mpfr-sys`.

---

### Task 1: Key script

```yaml-task
id: 1
description: Add scripts/gmp-cache-key.sh printing prefix, key and enabled lines from the tracked Cargo.lock files, with --strict fail-closed mode
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/gmp_cache_key.bats
    exit_code: 0
  - cmd: make lint </dev/null
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/gmp-cache-key.sh, tests/scripts/gmp_cache_key.bats]
depends_on: []
requirements: [R1, R6]
```

**Behaviour** (`scripts/gmp-cache-key.sh [--strict]`, executable, run from anywhere inside a repo):

1. Repo root: `env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git rev-parse --show-toplevel`.
2. Versions: for each file in `git ls-files -z '*/*-rs/Cargo.lock'`, take the `version = "X"` line that follows `name = "gmp-mpfr-sys"` in the same `[[package]]` block (awk). Sort `-u -V`, join with `_`.
3. Week: `${GMP_CACHE_WEEK:-$(date -u +%G-W%V)}`.
4. If versions, `RUNNER_OS`, `ImageOS` or week is empty: with `--strict` print `gmp-cache-key: <cause>` to stderr and exit 1; without it print the cause as `::warning::gmp-cache-key: <cause>` to stderr, print `enabled=false` to stdout, exit 0.
5. Otherwise print exactly three stdout lines: `enabled=true`, `prefix=gmp-mpfr-sys-<versions>-${RUNNER_OS}-${ImageOS}-`, `key=<prefix><week>`.
6. Any other argument: usage on stderr, exit 2.

**Tests** (`tests/scripts/gmp_cache_key.bats`, style of `check_release_version.bats`): `setup()` does `unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE`, builds a fixture git repo in `BATS_TEST_TMPDIR` with `a/a-rs/Cargo.lock` (gmp-mpfr-sys `1.7.1`, plus an unrelated `[[package]]` whose `version` follows) and `b/b-rs/Cargo.lock` (`1.7.0`), `git add`s them, and exports `RUNNER_OS=Linux ImageOS=ubuntu26 GMP_CACHE_WEEK=2026-W44`. Cases, each asserting the exact `output`:

- exact three lines with `1.7.0_1.7.1` (sorted, and the unrelated package's version absent);
- a third lockfile repeating `1.7.1` collapses to the same output;
- an untracked lockfile naming `1.9.9` is ignored;
- each of: no lockfile names `gmp-mpfr-sys`, `RUNNER_OS=""`, `ImageOS=""` — under `--strict` exits 1 with stderr naming the cause; without `--strict` exits 0 with stdout exactly `enabled=false`;
- unknown argument exits 2;
- real repo (`cd "${REPO_ROOT}"`, `GMP_CACHE_WEEK` unset): exit 0, a line matching `^key=gmp-mpfr-sys-1\.7\.[0-9]+.*-Linux-ubuntu26-[0-9]{4}-W[0-9]{2}$`.

Run `bats tests/scripts/gmp_cache_key.bats` before the script exists: it must fail with `not ok` lines (exit 1), not a usage error.

**Interfaces:** Produces `scripts/gmp-cache-key.sh [--strict]` and its stdout lines `enabled=`, `prefix=`, `key=`, which Tasks 2 and 3 append to `$GITHUB_OUTPUT`.

### Task 2: Read-only restore in the crate template

```yaml-task
id: 2
description: Set GMP_MPFR_SYS_CACHE and add a fail-open key step plus guarded actions/cache/restore to the test, coverage and build jobs of the crate CI template, rendered to all 11
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: python3 -m unittest tests.test_rust_ci_jobs -v
    exit_code: 0
  - cmd: python3 -m unittest tests.test_crate_uniformity
    exit_code: 0
  - cmd: bats tests/scripts/makefile.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/ci.yml, tests/test_rust_ci_jobs.py, .github/workflows/amicable-rs.yml, .github/workflows/collatz-rs.yml, .github/workflows/e-rs.yml, .github/workflows/factorial-rs.yml, .github/workflows/fib-rs.yml, .github/workflows/goldbach-rs.yml, .github/workflows/perfect-numbers-rs.yml, .github/workflows/pi-rs.yml, .github/workflows/prime-rs.yml, .github/workflows/sq-rs.yml, .github/workflows/twin-primes-rs.yml]
depends_on: [1]
parallel_group: wave-2
requirements: [R3, R4, R6]
```

**Template change**, in each of `test`, `coverage`, `build` of `scripts/crate_templates/ci.yml`:

- job-level `env: GMP_MPFR_SYS_CACHE: ${{ runner.temp }}/gmp-mpfr-sys`;
- right after `actions/checkout`, before any cargo/make step:

```yaml
- name: GMP cache key
  id: gmpkey
  working-directory: ${{ github.workspace }}
  run: scripts/gmp-cache-key.sh >> "$GITHUB_OUTPUT"

- name: Restore GMP/MPFR build cache
  if: steps.gmpkey.outputs.enabled == 'true'
  uses: actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0
  with:
    path: ${{ runner.temp }}/gmp-mpfr-sys
    key: ${{ steps.gmpkey.outputs.key }}
    restore-keys: ${{ steps.gmpkey.outputs.prefix }}
```

Then `python3 scripts/render_crate_files.py --write`.

**Tests** (new class `TestGmpCacheRestore` in `tests/test_rust_ci_jobs.py`, over `CI_WORKFLOWS`, all three jobs): job env `GMP_MPFR_SYS_CACHE` equals `${{ runner.temp }}/gmp-mpfr-sys`; a step with `id: gmpkey` whose `run` contains `scripts/gmp-cache-key.sh` and `>> "$GITHUB_OUTPUT"` and not `--strict`; a step using `actions/cache/restore@` with `if` exactly `steps.gmpkey.outputs.enabled == 'true'`, `with.key` `${{ steps.gmpkey.outputs.key }}`, `with.restore-keys` `${{ steps.gmpkey.outputs.prefix }}`, `with.path` equal to the env value; both steps precede the first step whose `run` contains `cargo` or `make`; no step `uses` `actions/cache@` or `actions/cache/save@`. Assert `len(CI_WORKFLOWS) == 11` stays. Run the class on the base tree first: it must fail (exit 1).


### Task 3: Warm workflow and parallel bats

```yaml-task
id: 3
description: Add master-scoped gmp-cache.yml (dispatch + weekly schedule, --strict key, per-version library check, save) and make scripts.yml install parallel and run bats --jobs 8
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: python3 -m unittest tests.test_gmp_cache_workflow -v
    exit_code: 0
  - cmd: bats tests/scripts/makefile.bats
    exit_code: 0
  - cmd: make lint </dev/null
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/gmp-cache.yml, .github/workflows/scripts.yml, tests/test_gmp_cache_workflow.py]
depends_on: [1]
parallel_group: wave-2
requirements: [R2, R5, R6]
```

**`.github/workflows/gmp-cache.yml`:** `on: workflow_dispatch` and `schedule: - cron: "0 3 * * 1"` only; `permissions: contents: read`; `env: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true`; one job `warm` on `ubuntu-latest`, `timeout-minutes: 30`, job env `GMP_MPFR_SYS_CACHE: ${{ runner.temp }}/gmp-mpfr-sys`. Steps: checkout (same SHA as `scripts.yml`); `id: gmpkey` running `scripts/gmp-cache-key.sh --strict >> "$GITHUB_OUTPUT"`; `id: restore` `actions/cache/restore` with only `path` and `key` (no `restore-keys`); then, each `if: steps.restore.outputs.cache-hit != 'true'`: the apt step and toolchain action copied from the crate template; a build step looping over `git ls-files '*/*-rs/Cargo.lock'`, running `cargo build --locked -p gmp-mpfr-sys` in each crate whose lockfile names it (`grep -q '^name = "gmp-mpfr-sys"$'`); a check step that, for each such lockfile's version `v`, requires `libgmp.a`, `libmpfr.a` and `libmpc.a` under a `"${GMP_MPFR_SYS_CACHE}"/*/*/"${v}"` directory and exits 1 naming the missing file; `actions/cache/save` with `path` and `key: ${{ steps.gmpkey.outputs.key }}`.

**`scripts.yml`:** install step becomes `sudo apt-get install -y bats parallel`; test step `bats --jobs 8 --recursive tests/`; add `".github/workflows/gmp-cache.yml"` to its `paths`.

**Tests** (`tests/test_gmp_cache_workflow.py`, `yaml.safe_load`; note PyYAML loads the `on` key as `True`): triggers are exactly `{workflow_dispatch, schedule}`; `permissions == {"contents": "read"}`; key step runs the script with `--strict`; restore has no `restore-keys`; a `actions/cache/save@` step whose `key` is `${{ steps.gmpkey.outputs.key }}` and `path` equals the job env; build, check and save steps all gated on `cache-hit != 'true'`; check step names all three libraries; every `uses` is pinned `@<40 hex>`; `scripts.yml` installs `parallel`, runs `bats --jobs 8 --recursive tests/`, and lists `.github/workflows/gmp-cache.yml` in `paths`. Run on the base tree first: it must fail (exit 1, not a missing-module error, so create the file with the tests before the workflow).

### Task 4: Docs, ADR and Backlog

```yaml-task
id: 4
description: Document gmp-cache.yml, the read-only restore and bats --jobs 8 in CLAUDE.md, write ADR-0034, and update the Backlog (docs-only, no behaviour change, so TDD does not apply)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: python3 -m unittest tests.test_claude_md_budget
    exit_code: 0
  - cmd: 'grep -q "gmp-cache.yml" CLAUDE.md'
    exit_code: 0
  - cmd: '! command grep -q "GMP/MPFR rebuilt from source" docs/superpowers/README.md'
    exit_code: 0
  - cmd: 'grep -qE "Status:.*Accepted" docs/adr/0034-master-scoped-gmp-cache.md'
    exit_code: 0
max_retries: 3
files_touched: [CLAUDE.md, docs/adr/0034-master-scoped-gmp-cache.md, docs/adr/README.md, docs/superpowers/README.md]
depends_on: [2, 3]
requirements: [R7, R8]
```

- `CLAUDE.md` CI section: add `gmp-cache.yml` to the workflow list; one line stating crate jobs restore the GMP build read-only and fail open via `scripts/gmp-cache-key.sh`, the warm job saves weekly, and to dispatch `gmp-cache.yml` after a `gmp-mpfr-sys` bump on master; change both `scripts.yml runs \`bats --recursive tests/\``mentions to`bats --jobs 8 --recursive tests/`. Stay under 30000 bytes.
- ADR-0034 (Context, Decision, Consequences, Related; format of ADR-0033) plus its `docs/adr/README.md` row: master-scoped warm cache, why not rust-cache paths, push trigger or `use-system-libs`.
- `docs/superpowers/README.md`: delete the "GMP/MPFR rebuilt from source on every CI rust-cache miss" Backlog row; add a row for the unused `libgmp-dev libmpfr-dev` apt step in the Rust CI jobs; add an In Progress row for this spec and plan.
- These files are not read by the suite except `CLAUDE.md` (budget test); the orchestrator runs `make test` after this task.

## Non-goal check

Reviewer (fresh, opus): 4 CLEAR, 0 CONFLICT, 0 UNCLEAR.

- N1 CLEAR: "the only `schedule` trigger is on the new `gmp-cache.yml`, which is not a crate workflow". No resolution needed.
- N2 CLEAR: the key and restore steps sit beside the rust-cache steps, whose configuration is unchanged. No resolution needed.
- N3 CLEAR: Task 2 edits the template and re-renders with `--write`. No resolution needed.
- N4 CLEAR: no task touches `release-*-rs.yml`. No resolution needed.
