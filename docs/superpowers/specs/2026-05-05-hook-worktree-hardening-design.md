# Hook and Worktree Compatibility Hardening — Design Spec

**Date:** 2026-05-05
**Status:** Draft

## Context

`scripts/pre-commit` uses relative paths (`make -C "${dir}" lint`) with no explicit
`REPO_ROOT`, relying on git setting CWD to the working tree root before running hooks.
While this works in practice, direct invocation or unusual environments can silently
run `make` against the wrong directory. `scripts/pre-push` already resolves `REPO_ROOT`
correctly via `git rev-parse --show-toplevel`.

Neither hook has tests. `scripts/test_rust_check.py` tests `rust-check.sh` in Python,
but the project has no framework for shell script tests. The backlog item calls for
worktree-safe hooks **with tests**.

## Goal

- Add explicit `REPO_ROOT` resolution to `scripts/pre-commit` so absolute paths are
  always used for `make -C`, matching the pattern already in `scripts/pre-push`.
- Establish BATS as the standard for shell script tests, following the dotfiles repo
  convention (system-installed bats-core, `tests/` directory, PATH-injected mocks).
- Migrate `scripts/test_rust_check.py` to `tests/scripts/rust_check.bats`.
- Add `tests/scripts/pre_commit.bats` and `tests/scripts/pre_push.bats` covering the
  full range of hook behaviors including worktree path resolution.
- Gate hook tests in CI via a new `.github/workflows/scripts.yml`.

## Out of Scope

- Changing which sub-projects the hooks cover (that's a separate maintenance step).
- Adding BATS coverage for other shell scripts beyond the three files above.
- Testing `make install-hooks` behavior.

---

## Directory Structure

```
tests/
  helpers/
    common.bash          # REPO_ROOT export; load_mocks()
  mocks/
    make                 # logs "make <args>"; exits $MOCK_MAKE_EXIT (default 0)
    git                  # logs "git <args>"; exits $MOCK_GIT_EXIT; stdout via $MOCK_GIT_OUTPUT
    ggshield             # logs "ggshield <args>"; exits $MOCK_GGSHIELD_EXIT (default 0)
  scripts/
    rust_check.bats      # migrated from scripts/test_rust_check.py (4 tests)
    pre_commit.bats      # 7 tests (see below)
    pre_push.bats        # 7 tests (see below)
```

`scripts/test_rust_check.py` is deleted once `rust_check.bats` passes in CI.

---

## Mock Infrastructure

**`tests/helpers/common.bash`**

```bash
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

load_mocks() {
  export PATH="${REPO_ROOT}/tests/mocks:${PATH}"
}
```

Every `.bats` file's `setup()` calls `load_mocks` and sets
`MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/mock_calls"`. `teardown()` removes it.

**Mock contracts:**

| Mock       | Logs              | Exit control                      | Stdout control                      |
| ---------- | ----------------- | --------------------------------- | ----------------------------------- |
| `make`     | `make <args>`     | `$MOCK_MAKE_EXIT` (default 0)     | —                                   |
| `git`      | `git <args>`      | `$MOCK_GIT_EXIT` (default 0)      | per-subcommand env vars (see below) |
| `ggshield` | `ggshield <args>` | `$MOCK_GGSHIELD_EXIT` (default 0) | —                                   |

The `git` mock dispatches by subcommand keyword using if/elif and prints from
dedicated env vars:

- `$MOCK_GIT_SHOW_TOPLEVEL` → printed when args contain `--show-toplevel`
- `$MOCK_GIT_DIFF_NAMES` → printed when args contain `diff`
- `$MOCK_GIT_MERGE_BASE` → printed when args contain `merge-base` (default `abc123`)
- `$MOCK_GIT_REV_LIST` → printed when args contain `rev-list` (default `abc123`)

Unrecognised subcommands print nothing and exit 0. Each test sets only the vars it needs.

---

## pre-commit Hardening

Replace the opening of `scripts/pre-commit` with:

```bash
#!/usr/bin/env bash
set -e

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_ROOT}" ]]; then
    REPO_ROOT="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)" \
        || { printf "pre-commit: could not determine repo root\n" >&2; exit 1; }
fi

for dir in pi pi/pi-rs prime/prime-rs fib fib/fib-rs sq sq/sq-rs twin-primes/twin-primes-rs e e/e-rs factorial factorial/factorial-rs; do
    if git diff --cached --name-only | grep -q "^${dir}/"; then
        printf "lint: %s\n" "${dir}"
        make -C "${REPO_ROOT}/${dir}" lint
    fi
done

if command -v ggshield &>/dev/null; then
    ggshield secret scan pre-commit
fi
```

No other logic changes.

---

## Test Specifications

### `tests/scripts/rust_check.bats` — 4 tests (migrated from Python)

Each test writes a fake-cargo script to `$BATS_TEST_TMPDIR`, sets
`RUST_CHECK_CARGO_BIN` to point to it, and runs the wrapper via `run`.

1. **Sets repo-local CARGO_HOME by default** — fake cargo prints `$CARGO_HOME`; assert
   it contains `<REPO_ROOT>/.cache/cargo-home`.
2. **Passes --offline flag when RUST_CHECK_OFFLINE=1** — fake cargo prints its args;
   assert `--offline` appears.
3. **Propagates cargo fmt failure even when clippy succeeds** — fake cargo exits 1 for
   `fmt`, 0 for `clippy`; assert wrapper exits non-zero.
4. **Classifies environment failures** — fake cargo prints "Operation not permitted" and
   exits non-zero; assert stderr contains "Environment/setup failure".

### `tests/scripts/pre_commit.bats` — 7 tests

The hook is run directly (not via git): `run bash "${REPO_ROOT}/scripts/pre-commit"`.
The `git` mock controls what `git diff --cached --name-only` returns and what
`git rev-parse --show-toplevel` returns.

1. **No staged changes** → `make` never called, exit 0.
2. **Staged file in `pi/`** → `make -C <REPO_ROOT>/pi lint` called (absolute path).
3. **Staged file in `factorial/factorial-rs/`** → `make -C <REPO_ROOT>/factorial/factorial-rs lint` called.
4. **Staged files in two sub-projects** → `make` called twice (both recorded in `$MOCK_CALLS_FILE`).
5. **`make lint` fails** → hook exits non-zero.
6. **`ggshield` not on PATH** → hook exits 0 (degrades gracefully; `ggshield` not in mocks PATH for this test).
7. **`ggshield` exits non-zero** → hook exits non-zero.

### `tests/scripts/pre_push.bats` — 7 tests

The hook is run with a controlled stdin pipe simulating git's push info lines:
`printf "%s\n" "refs/heads/feat abc123 refs/heads/feat 0000...0" | run bash "${REPO_ROOT}/scripts/pre-push"`.

The `git` mock handles `rev-parse --show-toplevel` (returning a fake root), `diff --name-only` (returning controlled file lists), and `merge-base` (returning a fake SHA).

1. **Branch deletion** (local sha = zeros) → `make` never called, exit 0.
2. **No files changed in push range** → `make` never called, exit 0.
3. **Changed file in `pi/`** → `make -C <fake-root>/pi test` called; fake root from `git rev-parse --show-toplevel`.
4. **Changed file in `factorial/factorial-rs/`** → `make -C <fake-root>/factorial/factorial-rs test` called.
5. **Changed files in two sub-projects** → `make` called twice.
6. **`make test` fails** → hook exits non-zero.
7. **New branch push** (remote sha = zeros) → `git merge-base` used to find range; `make` still called for changed files.

Tests 3–4 are the **worktree-safety tests**: `--show-toplevel` returns `/tmp/fake-worktree` instead of the real repo path, and assertions confirm `make` is called with `/tmp/fake-worktree/...` — proving the hook uses the active worktree root.

---

## Makefile and CI

**Root `Makefile`** (add target):

```makefile
.PHONY: install-hooks test-hooks

test-hooks:
	bats --recursive tests/
```

**`.github/workflows/scripts.yml`**:

```yaml
name: scripts
on:
  pull_request:
    branches:
      - master
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: Install bats-core
        run: sudo apt-get install -y bats
      - name: Run hook and script tests
        run: bats --recursive tests/
```

Badge added to `README.md` using `?event=pull_request`.

---

## Acceptance Criteria

- `bats --recursive tests/` passes locally (all 18 tests: 4 + 7 + 7).
- `scripts/test_rust_check.py` is deleted.
- `scripts/pre-commit` uses `${REPO_ROOT}/${dir}` absolute paths.
- `pre_push.bats` tests 3–4 pass with a fake `--show-toplevel` value, proving worktree path safety.
- CI `scripts` workflow is green on the PR.
- `README.md` has the scripts badge.
- `CLAUDE.md` updated: BATS is the standard for shell script tests; `make test-hooks` documented.
