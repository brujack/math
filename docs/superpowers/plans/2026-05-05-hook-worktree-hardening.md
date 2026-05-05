# Hook and Worktree Compatibility Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish BATS as the standard for shell script tests, migrate `test_rust_check.py` to BATS, add tests for both hook scripts, and harden `scripts/pre-commit` to use absolute paths.

**Architecture:** Five sequential tasks. Task 1 creates the shared test infrastructure (helpers + mocks). Tasks 2–4 add BATS test files using TDD, with Task 3 also hardening `pre-commit`. Task 5 wires up the Makefile, CI, and docs. All tests run via `bats --recursive tests/`.

**Tech Stack:** Bash, BATS (system-installed via Homebrew/apt), PATH-injected mock executables, GitHub Actions ubuntu-latest.

---

## File Map

| File                            | Action                                     |
| ------------------------------- | ------------------------------------------ |
| `tests/helpers/common.bash`     | Create — REPO_ROOT export + load_mocks()   |
| `tests/mocks/make`              | Create — mock executable                   |
| `tests/mocks/git`               | Create — mock executable                   |
| `tests/mocks/ggshield`          | Create — mock executable                   |
| `tests/scripts/rust_check.bats` | Create — 4 tests migrated from Python      |
| `tests/scripts/pre_commit.bats` | Create — 7 tests                           |
| `tests/scripts/pre_push.bats`   | Create — 7 tests                           |
| `scripts/pre-commit`            | Modify — add REPO_ROOT, use absolute paths |
| `scripts/test_rust_check.py`    | Delete — replaced by rust_check.bats       |
| `Makefile`                      | Modify — add test-hooks target             |
| `.github/workflows/scripts.yml` | Create — CI job                            |
| `README.md`                     | Modify — add scripts badge                 |
| `CLAUDE.md`                     | Modify — BATS standard, make test-hooks    |

---

## Task 1: Test infrastructure

**Files:**

- Create: `tests/helpers/common.bash`
- Create: `tests/mocks/make`
- Create: `tests/mocks/git`
- Create: `tests/mocks/ggshield`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p tests/helpers tests/mocks tests/scripts
```

- [ ] **Step 2: Create `tests/helpers/common.bash`**

```bash
#!/usr/bin/env bash
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

load_mocks() {
    export PATH="${REPO_ROOT}/tests/mocks:${PATH}"
}
```

- [ ] **Step 3: Create `tests/mocks/make`**

```bash
#!/usr/bin/env bash
printf "make %s\n" "$*" >> "${MOCK_CALLS_FILE:-/tmp/mock_calls}"
exit "${MOCK_MAKE_EXIT:-0}"
```

Mark executable: `chmod +x tests/mocks/make`

- [ ] **Step 4: Create `tests/mocks/git`**

```bash
#!/usr/bin/env bash
printf "git %s\n" "$*" >> "${MOCK_CALLS_FILE:-/tmp/mock_calls}"
if [[ "${MOCK_GIT_EXIT:-0}" -ne 0 ]]; then
    exit "${MOCK_GIT_EXIT}"
fi
if [[ "$*" == *"--show-toplevel"* ]]; then
    printf '%s\n' "${MOCK_GIT_SHOW_TOPLEVEL:-}"
elif [[ "$*" == *"merge-base"* ]]; then
    printf '%s\n' "${MOCK_GIT_MERGE_BASE:-abc123}"
elif [[ "$*" == *"rev-list"* ]]; then
    printf '%s\n' "${MOCK_GIT_REV_LIST:-abc123}"
elif [[ "$*" == *"diff"* ]]; then
    printf '%s\n' "${MOCK_GIT_DIFF_NAMES:-}"
fi
```

Mark executable: `chmod +x tests/mocks/git`

- [ ] **Step 5: Create `tests/mocks/ggshield`**

```bash
#!/usr/bin/env bash
printf "ggshield %s\n" "$*" >> "${MOCK_CALLS_FILE:-/tmp/mock_calls}"
exit "${MOCK_GGSHIELD_EXIT:-0}"
```

Mark executable: `chmod +x tests/mocks/ggshield`

- [ ] **Step 6: Verify bats is installed**

```bash
bats --version
```

Expected: `Bats 1.x.x`. If missing: `brew install bats-core` (macOS) or `sudo apt-get install -y bats` (Linux).

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "feat: add BATS test infrastructure (helpers + mocks)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Migrate rust_check tests to BATS

**Files:**

- Create: `tests/scripts/rust_check.bats`
- Delete: `scripts/test_rust_check.py`

- [ ] **Step 1: Create `tests/scripts/rust_check.bats`**

```bash
#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/mock_calls"
}

teardown() {
    rm -f "${MOCK_CALLS_FILE:-}"
}

_write_fake_cargo() {
    local body="$1"
    local path="${BATS_TEST_TMPDIR}/fake-cargo"
    printf '#!/usr/bin/env bash\n%s\n' "${body}" > "${path}"
    chmod +x "${path}"
    printf '%s' "${path}"
}

@test "sets repo-local CARGO_HOME when CARGO_HOME is unset" {
    local fake_cargo
    fake_cargo="$(_write_fake_cargo 'printf "%s\n" "${CARGO_HOME}"')"
    run env -u CARGO_HOME \
        RUST_CHECK_CARGO_BIN="${fake_cargo}" \
        bash "${REPO_ROOT}/scripts/rust-check.sh" lint
    [ "$status" -eq 0 ]
    [[ "$output" == *"${REPO_ROOT}/.cache/cargo-home"* ]]
}

@test "passes --offline flag when RUST_CHECK_OFFLINE=1" {
    local fake_cargo
    fake_cargo="$(_write_fake_cargo 'printf "%s\n" "$@"')"
    run env RUST_CHECK_CARGO_BIN="${fake_cargo}" \
        RUST_CHECK_OFFLINE=1 \
        bash "${REPO_ROOT}/scripts/rust-check.sh" test
    [ "$status" -eq 0 ]
    [[ "$output" == *"--offline"* ]]
}

@test "propagates fmt failure even when clippy succeeds" {
    local fake_cargo
    fake_cargo="$(_write_fake_cargo 'if [ "$1" = "fmt" ]; then exit 1; fi; exit 0')"
    run env RUST_CHECK_CARGO_BIN="${fake_cargo}" \
        bash "${REPO_ROOT}/scripts/rust-check.sh" lint
    [ "$status" -ne 0 ]
}

@test "classifies environment failures in stderr" {
    local fake_cargo stderr_file rc
    fake_cargo="$(_write_fake_cargo 'printf "Operation not permitted\n"; exit 101')"
    stderr_file="${BATS_TEST_TMPDIR}/stderr.txt"
    rc=0
    RUST_CHECK_CARGO_BIN="${fake_cargo}" \
        bash "${REPO_ROOT}/scripts/rust-check.sh" lint \
        2>"${stderr_file}" || rc=$?
    [ "${rc}" -eq 101 ]
    grep -q "Environment/setup failure" "${stderr_file}"
}
```

- [ ] **Step 2: Run to confirm all 4 tests pass**

```bash
bats tests/scripts/rust_check.bats
```

Expected:

```
 ✓ sets repo-local CARGO_HOME when CARGO_HOME is unset
 ✓ passes --offline flag when RUST_CHECK_OFFLINE=1
 ✓ propagates fmt failure even when clippy succeeds
 ✓ classifies environment failures in stderr

4 tests, 0 failures
```

- [ ] **Step 3: Delete the Python test file**

```bash
git rm scripts/test_rust_check.py
```

- [ ] **Step 4: Commit**

```bash
git add tests/scripts/rust_check.bats
git commit -m "test: migrate rust_check tests from Python to BATS

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: pre_commit.bats + harden pre-commit

TDD: write tests first — tests 2 and 3 will be RED (current `pre-commit` uses relative paths). Harden `pre-commit` to make them GREEN.

**Files:**

- Create: `tests/scripts/pre_commit.bats`
- Modify: `scripts/pre-commit`

- [ ] **Step 1: Create `tests/scripts/pre_commit.bats`**

```bash
#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/mock_calls"
    # Default: show-toplevel returns our fake root; no staged files
    export MOCK_GIT_SHOW_TOPLEVEL="${BATS_TEST_TMPDIR}/fake-root"
    export MOCK_GIT_DIFF_NAMES=""
}

teardown() {
    rm -f "${MOCK_CALLS_FILE:-}"
}

@test "no staged changes exits 0 without calling make" {
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    ! grep -q "^make" "${MOCK_CALLS_FILE}" 2>/dev/null
}

@test "staged file in pi/ calls make with absolute path" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-root/pi lint" "${MOCK_CALLS_FILE}"
}

@test "staged file in factorial/factorial-rs/ calls make with absolute path" {
    export MOCK_GIT_DIFF_NAMES="factorial/factorial-rs/src/main.rs"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-root/factorial/factorial-rs lint" "${MOCK_CALLS_FILE}"
}

@test "staged files in two sub-projects calls make twice" {
    export MOCK_GIT_DIFF_NAMES=$'pi/pi.py\ne/e.py'
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 2 ]
}

@test "make lint failure exits non-zero" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    export MOCK_MAKE_EXIT=1
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -ne 0 ]
}

@test "ggshield not on PATH exits 0" {
    # Build a mock dir with git+make but no ggshield
    local no_ggs="${BATS_TEST_TMPDIR}/no_ggs"
    mkdir -p "${no_ggs}"
    ln -sf "${REPO_ROOT}/tests/mocks/git"  "${no_ggs}/git"
    ln -sf "${REPO_ROOT}/tests/mocks/make" "${no_ggs}/make"
    # Strip tests/mocks from PATH and prepend our ggshield-free dir
    local base_path
    base_path="$(printf '%s' "${PATH}" | tr ':' '\n' \
        | grep -v "${REPO_ROOT}/tests/mocks" | paste -sd: -)"
    run env "PATH=${no_ggs}:${base_path}" bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
}

@test "ggshield failure exits non-zero" {
    export MOCK_GGSHIELD_EXIT=1
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -ne 0 ]
}
```

- [ ] **Step 2: Run to confirm tests 2 and 3 are RED**

```bash
bats tests/scripts/pre_commit.bats
```

Expected: tests 2 and 3 FAIL with something like:

```
 ✓ no staged changes exits 0 without calling make
 ✗ staged file in pi/ calls make with absolute path
   (in test file tests/scripts/pre_commit.bats, line ...)
   `grep -q "make -C ${BATS_TEST_TMPDIR}/fake-root/pi lint"` failed
 ✗ staged file in factorial/factorial-rs/ calls make with absolute path
   ...
 ✓ staged files in two sub-projects calls make twice
 ✓ make lint failure exits non-zero
 ✓ ggshield not on PATH exits 0
 ✓ ggshield failure exits non-zero
```

(Tests 2 and 3 fail because the current `pre-commit` calls `make -C pi lint` without the `${REPO_ROOT}/` prefix.)

- [ ] **Step 3: Replace `scripts/pre-commit` with the hardened version**

Full file content — replace entirely:

```bash
#!/usr/bin/env bash
set -e

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_ROOT}" ]]; then
    REPO_ROOT="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)" \
        || { printf "pre-commit: could not determine repo root\n" >&2; exit 1; }
fi

# Run lint for each sub-project that has staged changes
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

- [ ] **Step 4: Run to confirm all 7 tests are GREEN**

```bash
bats tests/scripts/pre_commit.bats
```

Expected:

```
 ✓ no staged changes exits 0 without calling make
 ✓ staged file in pi/ calls make with absolute path
 ✓ staged file in factorial/factorial-rs/ calls make with absolute path
 ✓ staged files in two sub-projects calls make twice
 ✓ make lint failure exits non-zero
 ✓ ggshield not on PATH exits 0
 ✓ ggshield failure exits non-zero

7 tests, 0 failures
```

- [ ] **Step 5: Commit**

```bash
git add tests/scripts/pre_commit.bats scripts/pre-commit
git commit -m "fix: harden pre-commit with absolute REPO_ROOT paths; add BATS tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: pre_push.bats

The pre-push script already has correct REPO_ROOT resolution, so all 7 tests should pass after writing them. Tests 3–4 are the key worktree-safety tests: they prove the hook uses `--show-toplevel` output (the active worktree root), not a hardcoded path.

**Files:**

- Create: `tests/scripts/pre_push.bats`

- [ ] **Step 1: Create `tests/scripts/pre_push.bats`**

```bash
#!/usr/bin/env bats

ZEROS="0000000000000000000000000000000000000000"

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/mock_calls"
    export MOCK_GIT_SHOW_TOPLEVEL="${BATS_TEST_TMPDIR}/fake-worktree"
    export MOCK_GIT_DIFF_NAMES=""
    export MOCK_GIT_MERGE_BASE="base123"
}

teardown() {
    rm -f "${MOCK_CALLS_FILE:-}"
}

@test "branch deletion push skips make" {
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat ${ZEROS} refs/heads/feat abc123"
    [ "$status" -eq 0 ]
    ! grep -q "^make" "${MOCK_CALLS_FILE}" 2>/dev/null
}

@test "no changed files in push range skips make" {
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    ! grep -q "^make" "${MOCK_CALLS_FILE}" 2>/dev/null
}

@test "changed file in pi/ uses worktree root in make path" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi test" "${MOCK_CALLS_FILE}"
}

@test "changed file in factorial/factorial-rs/ uses worktree root in make path" {
    export MOCK_GIT_DIFF_NAMES="factorial/factorial-rs/src/main.rs"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree/factorial/factorial-rs test" "${MOCK_CALLS_FILE}"
}

@test "changed files in two sub-projects calls make twice" {
    export MOCK_GIT_DIFF_NAMES=$'pi/pi.py\ne/e.py'
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 2 ]
}

@test "make test failure exits non-zero" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    export MOCK_MAKE_EXIT=1
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -ne 0 ]
}

@test "new branch push uses merge-base and calls make for changed files" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat ${ZEROS}"
    [ "$status" -eq 0 ]
    grep -q "merge-base" "${MOCK_CALLS_FILE}"
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi test" "${MOCK_CALLS_FILE}"
}
```

- [ ] **Step 2: Run to confirm all 7 tests pass**

```bash
bats tests/scripts/pre_push.bats
```

Expected:

```
 ✓ branch deletion push skips make
 ✓ no changed files in push range skips make
 ✓ changed file in pi/ uses worktree root in make path
 ✓ changed file in factorial/factorial-rs/ uses worktree root in make path
 ✓ changed files in two sub-projects calls make twice
 ✓ make test failure exits non-zero
 ✓ new branch push uses merge-base and calls make for changed files

7 tests, 0 failures
```

- [ ] **Step 3: Run full test suite**

```bash
bats --recursive tests/
```

Expected: 18 tests, 0 failures.

- [ ] **Step 4: Commit**

```bash
git add tests/scripts/pre_push.bats
git commit -m "test: add BATS tests for pre-push worktree path resolution

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Makefile, CI, and docs

**Files:**

- Modify: `Makefile`
- Create: `.github/workflows/scripts.yml`
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add `test-hooks` target to `Makefile`**

Current `Makefile`:

```makefile
.PHONY: install-hooks

install-hooks:
	ln -sf "../../scripts/pre-commit" "$$(git rev-parse --git-path hooks)/pre-commit"
	ln -sf "../../scripts/pre-push" "$$(git rev-parse --git-path hooks)/pre-push"
	@printf "Pre-commit and pre-push hooks installed\n"
```

Replace with:

```makefile
.PHONY: install-hooks test-hooks

install-hooks:
	ln -sf "../../scripts/pre-commit" "$$(git rev-parse --git-path hooks)/pre-commit"
	ln -sf "../../scripts/pre-push" "$$(git rev-parse --git-path hooks)/pre-push"
	@printf "Pre-commit and pre-push hooks installed\n"

test-hooks:
	bats --recursive tests/
```

- [ ] **Step 2: Verify `make test-hooks` works**

```bash
make test-hooks 2>&1 | tail -5
```

Expected: `18 tests, 0 failures`

- [ ] **Step 3: Create `.github/workflows/scripts.yml`**

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

- [ ] **Step 4: Add scripts badge to `README.md`**

Find the existing badge block at the top of `README.md`. Add the scripts badge alongside the existing ones:

```markdown
[![scripts](https://github.com/brujack/math/actions/workflows/scripts.yml/badge.svg?event=pull_request)](https://github.com/brujack/math/actions/workflows/scripts.yml)
```

- [ ] **Step 5: Update `CLAUDE.md`**

Find this line in `CLAUDE.md` (search for `"Worktree compatibility requirement"`):

```
**Worktree compatibility requirement:** `scripts/pre-push` must resolve the repository root ...
```

Add the following block immediately after that paragraph:

```
**Shell script testing** — BATS (`bats --recursive tests/`) is the standard for all shell script tests in this repo. Run with `make test-hooks`. Requires system-installed bats-core: `brew install bats-core` (macOS) or `sudo apt-get install -y bats` (Linux).
- `tests/helpers/common.bash` — shared REPO_ROOT export and `load_mocks()` (prepends `tests/mocks/` to PATH)
- `tests/mocks/` — PATH-injected mock executables: `make` (logs calls, exits `$MOCK_MAKE_EXIT`), `git` (dispatches by subcommand, outputs from per-subcommand env vars), `ggshield` (logs calls, exits `$MOCK_GGSHIELD_EXIT`)
- `tests/scripts/` — BATS test files; one per script tested (`rust_check.bats`, `pre_commit.bats`, `pre_push.bats`)
```

Also find the CI table (search for `| auto-merge |`) and add a new row:

```
| scripts | `.github/workflows/scripts.yml` | test (bats --recursive tests/) |
```

- [ ] **Step 6: Commit everything**

```bash
git add Makefile .github/workflows/scripts.yml README.md CLAUDE.md
git commit -m "feat: add test-hooks Makefile target, scripts CI workflow, and docs

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Acceptance Verification

After all tasks, run this sweep:

```bash
# All 18 BATS tests pass
bats --recursive tests/

# No relative make -C in pre-commit
grep "make -C " scripts/pre-commit
# Expected: only lines containing ${REPO_ROOT}

# Python test file is gone
ls scripts/test_rust_check.py 2>/dev/null || echo "correctly deleted"

# CI workflow exists
ls .github/workflows/scripts.yml
```
