# Auto-Merge Gate Integrity Implementation Plan

> **Status: DONE** — Merged in PR #45 (2026-05-06)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure PRs only auto-merge when all test workflows relevant to the PR's changed files
have passed.

**Architecture:** Add `paths:` filters to all 13 project workflows (irrelevant workflows don't
fire), add `scripts/ci-gate.sh` (polls `gh pr checks` until triggered checks reach terminal
state then verifies none failed), and call the gate from `auto-merge.yml` before merging.
Advisory checks (`snyk-scan`) and self-checks (`secret-scan`, `auto-merge`) are excluded.

**Tech Stack:** Bash, GitHub Actions YAML, `gh` CLI, `jq`, BATS

---

## File Map

| File                                   | Action | Responsibility                                                 |
| -------------------------------------- | ------ | -------------------------------------------------------------- |
| `tests/mocks/gh`                       | Create | Mock `gh` CLI with sequential JSON responses for polling tests |
| `tests/scripts/ci_gate.bats`           | Create | BATS tests for `scripts/ci-gate.sh`                            |
| `tests/scripts/makefile.bats`          | Create | BATS tests for root Makefile targets                           |
| `scripts/ci-gate.sh`                   | Create | Polling gate: wait for required checks, exit 0/1               |
| `.github/workflows/pi-py.yml`          | Modify | Add `paths:` block                                             |
| `.github/workflows/pi-rs.yml`          | Modify | Add `paths:` block                                             |
| `.github/workflows/fib-py.yml`         | Modify | Add `paths:` block                                             |
| `.github/workflows/fib-rs.yml`         | Modify | Add `paths:` block                                             |
| `.github/workflows/sq-py.yml`          | Modify | Add `paths:` block                                             |
| `.github/workflows/sq-rs.yml`          | Modify | Add `paths:` block                                             |
| `.github/workflows/prime-rs.yml`       | Modify | Add `paths:` block                                             |
| `.github/workflows/twin-primes-rs.yml` | Modify | Add `paths:` block                                             |
| `.github/workflows/e-py.yml`           | Modify | Add `paths:` block                                             |
| `.github/workflows/e-rs.yml`           | Modify | Add `paths:` block                                             |
| `.github/workflows/factorial-py.yml`   | Modify | Add `paths:` block                                             |
| `.github/workflows/factorial-rs.yml`   | Modify | Add `paths:` block                                             |
| `.github/workflows/scripts.yml`        | Modify | Add `paths:` block (includes root `Makefile`)                  |
| `.github/workflows/auto-merge.yml`     | Modify | Call gate script before merge                                  |
| `CLAUDE.md`                            | Modify | Update CI section                                              |

---

### Task 1: Create the `gh` mock

**Files:**

- Create: `tests/mocks/gh`

The mock supports sequential JSON responses for the polling loop, an exit-code override, and
call logging — matching the existing `git`/`make` mock pattern. On sequential `gh pr checks`
calls it reads `MOCK_GH_PR_CHECKS_1`, `MOCK_GH_PR_CHECKS_2`, … using a counter file.

- [ ] **Step 1: Create the mock executable**

```bash
cat > tests/mocks/gh << 'EOF'
#!/usr/bin/env bash
printf "gh %s\n" "$*" >> "${MOCK_CALLS_FILE:-/tmp/mock_calls}"

if [[ "${MOCK_GH_EXIT:-0}" -ne 0 ]]; then
    exit "${MOCK_GH_EXIT}"
fi

if [[ "$*" == *"pr checks"* && "$*" == *"--json"* ]]; then
    _counter_file="${MOCK_GH_COUNTER_FILE:-/tmp/gh_counter}"
    _count=$(cat "${_counter_file}" 2>/dev/null || printf "0")
    _count=$((_count + 1))
    printf "%d\n" "${_count}" > "${_counter_file}"
    _var="MOCK_GH_PR_CHECKS_${_count}"
    _fallback="MOCK_GH_PR_CHECKS"
    printf '%s\n' "${!_var:-${!_fallback:-[]}}"
else
    printf '%s\n' "${MOCK_GH_OUTPUT:-}"
fi
EOF
chmod +x tests/mocks/gh
```

- [ ] **Step 2: Smoke-test the mock manually**

```bash
export MOCK_CALLS_FILE=/tmp/test_gh_calls
export MOCK_GH_PR_CHECKS_1='[{"name":"test","state":"success"}]'
export MOCK_GH_COUNTER_FILE=/tmp/test_gh_counter
rm -f /tmp/test_gh_counter
tests/mocks/gh pr checks 42 --json name,state
cat /tmp/test_gh_calls
```

Expected: stdout is `[{"name":"test","state":"success"}]`, calls file contains
`gh pr checks 42 --json name,state`.

- [ ] **Step 3: Commit**

```bash
git add tests/mocks/gh
git commit -m "test: add gh mock for ci-gate BATS tests"
```

---

### Task 2: Write failing BATS tests for ci-gate.sh

**Files:**

- Create: `tests/scripts/ci_gate.bats`

All seven tests must be written before the script exists. They should all fail because
`scripts/ci-gate.sh` does not exist yet. Do not commit — wait for Task 3.

Follow the pattern from `tests/scripts/pre_commit.bats`: use `run` to execute the script as a
subprocess (`run "${REPO_ROOT}/scripts/ci-gate.sh" 42`), not source+function calls. For tests
that check stderr content, redirect stderr into stdout with `run bash -c "... 2>&1"`.

`CI_GATE_POLL_INTERVAL=0` and `CI_GATE_MAX_POLLS=5` are exported in `setup()` and inherited
by the subprocess, so the polling loop completes instantly without real sleeps.

- [ ] **Step 1: Create the test file**

```bash
cat > tests/scripts/ci_gate.bats << 'BATS'
#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/calls"
    export MOCK_GH_COUNTER_FILE="${BATS_TEST_TMPDIR}/gh_counter"
    export CI_GATE_POLL_INTERVAL=0
    export CI_GATE_MAX_POLLS=5
}

@test "all required checks pass → exit 0" {
    export MOCK_GH_PR_CHECKS_1='[{"name":"Test pi-rs","state":"success"},{"name":"snyk-scan","state":"failure"}]'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
}

@test "required check failure → exit 1 naming failed check" {
    export MOCK_GH_PR_CHECKS_1='[{"name":"Test pi-rs","state":"failure"}]'
    run bash -c "${REPO_ROOT}/scripts/ci-gate.sh 42 2>&1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Test pi-rs"* ]]
}

@test "advisory snyk-scan failure with required passing → exit 0" {
    export MOCK_GH_PR_CHECKS_1='[{"name":"Test pi-rs","state":"success"},{"name":"snyk-scan","state":"failure"}]'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
}

@test "polls until terminal: in-progress first then success → exit 0" {
    export MOCK_GH_PR_CHECKS_1='[{"name":"Test pi-rs","state":"in_progress"}]'
    export MOCK_GH_PR_CHECKS_2='[{"name":"Test pi-rs","state":"success"}]'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
}

@test "timeout when checks remain in-progress → exit 1 with timeout message" {
    export MOCK_GH_PR_CHECKS_1='[{"name":"Test pi-rs","state":"in_progress"}]'
    export CI_GATE_MAX_POLLS=1
    run bash -c "${REPO_ROOT}/scripts/ci-gate.sh 42 2>&1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"imeout"* ]]
}

@test "no required checks triggered (docs-only PR) → exit 0" {
    export MOCK_GH_PR_CHECKS_1='[{"name":"snyk-scan","state":"failure"},{"name":"secret-scan","state":"success"},{"name":"auto-merge","state":"success"}]'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
}

@test "missing PR number argument → exit 1 with usage message" {
    run bash -c "${REPO_ROOT}/scripts/ci-gate.sh 2>&1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"sage"* ]]
}
BATS
```

- [ ] **Step 2: Run the tests and confirm all fail**

```bash
bats tests/scripts/ci_gate.bats
```

Expected: all 7 tests fail — `ci-gate.sh: No such file or directory` (or similar).

---

### Task 3: Implement ci-gate.sh

**Files:**

- Create: `scripts/ci-gate.sh`

Write the minimum implementation to make all 7 tests pass.

`ADVISORY_CHECKS` and `SELF_CHECKS` are `readonly` at file scope. `max_polls` and
`poll_interval` are local variables inside `ci_gate()` that read `CI_GATE_MAX_POLLS` and
`CI_GATE_POLL_INTERVAL` from the environment at call time, so the values exported in
`setup()` are picked up correctly by the subprocess.

**Note on check names:** `gh pr checks --json name` returns the job `name:` value from the
workflow YAML (or the job key if no `name:` is set). The jobs in `auto-merge.yml` — `snyk-scan`,
`secret-scan`, `auto-merge` — have no `name:` field, so their check run names are exactly those
strings. Verify against `gh pr checks <PR> --json name,state` on a live PR before merging.

- [ ] **Step 1: Create the script**

```bash
cat > scripts/ci-gate.sh << 'EOF'
#!/usr/bin/env bash

readonly ADVISORY_CHECKS=("snyk-scan")
readonly SELF_CHECKS=("secret-scan" "auto-merge")

ci_gate() {
    local pr="${1}"
    if [[ -z "${pr}" ]]; then
        printf "Usage: ci-gate.sh <PR_NUMBER>\n" >&2
        return 1
    fi

    local max_polls="${CI_GATE_MAX_POLLS:-60}"
    local poll_interval="${CI_GATE_POLL_INTERVAL:-30}"
    local checks non_terminal timed_out=1

    for (( poll=0; poll<max_polls; poll++ )); do
        checks=$(gh pr checks "${pr}" --json name,state)
        non_terminal=$(printf '%s' "${checks}" | jq -r \
            '.[] | select(.state == "queued" or .state == "in_progress" or .state == "pending" or .state == "waiting" or .state == "requested") | .name')
        if [[ -z "${non_terminal}" ]]; then
            timed_out=0
            break
        fi
        sleep "${poll_interval}"
    done

    if [[ "${timed_out}" -eq 1 ]]; then
        printf "Timeout: checks did not complete within %d polls\n" "${max_polls}" >&2
        return 1
    fi

    local excluded_json
    excluded_json=$(printf '"%s",' "${ADVISORY_CHECKS[@]}" "${SELF_CHECKS[@]}")
    excluded_json="[${excluded_json%,}]"

    local required
    required=$(printf '%s' "${checks}" | jq -r --argjson excl "${excluded_json}" \
        '.[] | select([.name] | inside($excl) | not) | .name')

    if [[ -z "${required}" ]]; then
        printf "No required checks triggered. Proceeding.\n"
        return 0
    fi

    local failures
    failures=$(printf '%s' "${checks}" | jq -r --argjson excl "${excluded_json}" \
        '.[] | select([.name] | inside($excl) | not) | select(.state != "success" and .state != "skipped") | .name')

    if [[ -n "${failures}" ]]; then
        printf "Required checks failed:\n%s\n" "${failures}" >&2
        return 1
    fi

    printf "All required checks passed.\n"
    return 0
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
ci_gate "$@"
EOF
chmod +x scripts/ci-gate.sh
```

- [ ] **Step 2: Run tests and verify all 7 pass**

```bash
bats tests/scripts/ci_gate.bats
```

Expected: `7 tests, 0 failures`.

- [ ] **Step 3: Commit**

```bash
git add scripts/ci-gate.sh tests/scripts/ci_gate.bats
git commit -m "feat: add ci-gate.sh polling gate with BATS tests"
```

---

### Task 4: Write and verify Makefile BATS tests

**Files:**

- Create: `tests/scripts/makefile.bats`

The root Makefile already has both targets, so these tests should pass immediately. They use
real `make --dry-run` (`-n`) which prints recipes without executing them — no mocks needed,
no system state modified.

- [ ] **Step 1: Create the test file**

```bash
cat > tests/scripts/makefile.bats << 'BATS'
#!/usr/bin/env bats

load '../helpers/common'

@test "make test-hooks recipe calls bats --recursive tests/" {
    run make -C "${REPO_ROOT}" -n test-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"bats --recursive tests/"* ]]
}

@test "make install-hooks recipe links pre-commit hook" {
    run make -C "${REPO_ROOT}" -n install-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"scripts/pre-commit"* ]]
}

@test "make install-hooks recipe links pre-push hook" {
    run make -C "${REPO_ROOT}" -n install-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"scripts/pre-push"* ]]
}

@test "install-hooks and test-hooks are declared .PHONY" {
    run grep -E "^\.PHONY" "${REPO_ROOT}/Makefile"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"install-hooks"* ]]
    [[ "${output}" == *"test-hooks"* ]]
}
BATS
```

- [ ] **Step 2: Run the tests and verify all pass**

```bash
bats tests/scripts/makefile.bats
```

Expected: `4 tests, 0 failures`.

- [ ] **Step 3: Run the full BATS suite to verify no regressions**

```bash
make test-hooks
```

Expected: all tests pass including the new files.

- [ ] **Step 4: Commit**

```bash
git add tests/scripts/makefile.bats
git commit -m "test: add BATS tests for root Makefile targets"
```

---

### Task 5: Add paths filters to Python project workflows

**Files:**

- Modify: `.github/workflows/pi-py.yml`
- Modify: `.github/workflows/fib-py.yml`
- Modify: `.github/workflows/sq-py.yml`
- Modify: `.github/workflows/e-py.yml`
- Modify: `.github/workflows/factorial-py.yml`

Add a `paths:` block to the `pull_request:` trigger in each workflow. Only files within the
project directory (and the workflow file itself) trigger the workflow.

- [ ] **Step 1: Update `pi-py.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "pi/*.py"
      - "pi/install_deps.sh"
      - "pi/Makefile"
      - ".github/workflows/pi-py.yml"
```

- [ ] **Step 2: Update `fib-py.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "fib/*.py"
      - "fib/install_deps.sh"
      - "fib/Makefile"
      - ".github/workflows/fib-py.yml"
```

- [ ] **Step 3: Update `sq-py.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "sq/*.py"
      - "sq/install_deps.sh"
      - "sq/Makefile"
      - ".github/workflows/sq-py.yml"
```

- [ ] **Step 4: Update `e-py.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "e/*.py"
      - "e/install_deps.sh"
      - "e/Makefile"
      - ".github/workflows/e-py.yml"
```

- [ ] **Step 5: Update `factorial-py.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "factorial/*.py"
      - "factorial/install_deps.sh"
      - "factorial/Makefile"
      - ".github/workflows/factorial-py.yml"
```

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/pi-py.yml .github/workflows/fib-py.yml \
        .github/workflows/sq-py.yml .github/workflows/e-py.yml \
        .github/workflows/factorial-py.yml
git commit -m "ci: add paths filters to Python project workflows"
```

---

### Task 6: Add paths filters to Rust workflows and scripts.yml

**Files:**

- Modify: `.github/workflows/pi-rs.yml`
- Modify: `.github/workflows/fib-rs.yml`
- Modify: `.github/workflows/sq-rs.yml`
- Modify: `.github/workflows/prime-rs.yml`
- Modify: `.github/workflows/twin-primes-rs.yml`
- Modify: `.github/workflows/e-rs.yml`
- Modify: `.github/workflows/factorial-rs.yml`
- Modify: `.github/workflows/scripts.yml`

- [ ] **Step 1: Update `pi-rs.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "pi/pi-rs/**"
      - ".github/workflows/pi-rs.yml"
```

- [ ] **Step 2: Update `fib-rs.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "fib/fib-rs/**"
      - ".github/workflows/fib-rs.yml"
```

- [ ] **Step 3: Update `sq-rs.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "sq/sq-rs/**"
      - ".github/workflows/sq-rs.yml"
```

- [ ] **Step 4: Update `prime-rs.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "prime/prime-rs/**"
      - ".github/workflows/prime-rs.yml"
```

- [ ] **Step 5: Update `twin-primes-rs.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "twin-primes/twin-primes-rs/**"
      - ".github/workflows/twin-primes-rs.yml"
```

- [ ] **Step 6: Update `e-rs.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "e/e-rs/**"
      - ".github/workflows/e-rs.yml"
```

- [ ] **Step 7: Update `factorial-rs.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "factorial/factorial-rs/**"
      - ".github/workflows/factorial-rs.yml"
```

- [ ] **Step 8: Update `scripts.yml`**

Replace the `on:` block:

```yaml
on:
  pull_request:
    branches:
      - master
    paths:
      - "scripts/**"
      - "tests/**"
      - "Makefile"
      - ".github/workflows/scripts.yml"
```

- [ ] **Step 9: Commit**

```bash
git add .github/workflows/pi-rs.yml .github/workflows/fib-rs.yml \
        .github/workflows/sq-rs.yml .github/workflows/prime-rs.yml \
        .github/workflows/twin-primes-rs.yml .github/workflows/e-rs.yml \
        .github/workflows/factorial-rs.yml .github/workflows/scripts.yml
git commit -m "ci: add paths filters to Rust project workflows and scripts"
```

---

### Task 7: Wire gate script into auto-merge.yml

**Files:**

- Modify: `.github/workflows/auto-merge.yml`

Replace the existing `Auto-merge passing PRs` step in the `auto-merge` job with a combined
gate-and-merge step. The gate runs first; if it exits 1 the merge is skipped and the job fails.

- [ ] **Step 1: Replace the `auto-merge` job's merge step**

The current `auto-merge` job ends with:

```yaml
- name: Auto-merge passing PRs
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    PR=$(gh pr list --head "${{ github.head_ref || github.ref_name }}" --json number --jq '.[0].number' 2>/dev/null || echo "")
    if [[ -n "${PR}" ]]; then
      gh pr merge "${PR}" --squash
    fi
```

Replace it with:

```yaml
- name: Gate and merge
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    PR=$(gh pr list --head "${{ github.head_ref || github.ref_name }}" \
      --json number --jq '.[0].number' 2>/dev/null || echo "")
    if [[ -n "${PR}" ]]; then
      ./scripts/ci-gate.sh "${PR}" && gh pr merge "${PR}" --squash
    fi
```

The `&&` ensures `gh pr merge` only runs if the gate exits 0. If the gate exits 1, the `if`
block exits 1, the step fails, and the PR stays open with a visible red check.

- [ ] **Step 2: Verify the complete `auto-merge` job looks correct**

After your edit, the full `auto-merge` job should be:

```yaml
auto-merge:
  needs: [secret-scan]
  runs-on: ubuntu-latest
  permissions:
    contents: write
    pull-requests: write
  steps:
    - uses: actions/checkout@v5

    - name: Gate and merge
      env:
        GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      run: |
        PR=$(gh pr list --head "${{ github.head_ref || github.ref_name }}" \
          --json number --jq '.[0].number' 2>/dev/null || echo "")
        if [[ -n "${PR}" ]]; then
          ./scripts/ci-gate.sh "${PR}" && gh pr merge "${PR}" --squash
        fi
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/auto-merge.yml
git commit -m "ci: call ci-gate.sh before auto-merge to enforce required checks"
```

---

### Task 8: Update CLAUDE.md

**Files:**

- Modify: `CLAUDE.md`

Update the CI section to document the gate script, the paths-filter behaviour, and the
advisory vs required check distinction.

- [ ] **Step 1: Add gate script entry to the CI table**

In the CI table (under `## CI`), the `auto-merge` row currently reads:

```
| auto-merge | `.github/workflows/auto-merge.yml` | secret-scan → snyk-scan (advisory) → auto-merge (secret-scan is a hard gate) |
```

Replace with:

```
| auto-merge | `.github/workflows/auto-merge.yml` | secret-scan → ci-gate (polls for required checks, merges on pass) → snyk-scan (advisory, not gated) |
```

- [ ] **Step 2: Add gate script documentation**

After the CI table, add a paragraph (or update the existing CI notes) to document:

```markdown
**CI gate script** — `scripts/ci-gate.sh <PR>` is called by the `auto-merge` job before
merging. It polls `gh pr checks` until all checks are terminal, then verifies that no
check outside the advisory list (`snyk-scan`) and self-checks (`secret-scan`, `auto-merge`)
has failed. Docs-only PRs trigger no project workflows and merge immediately. The gate is
tested via `tests/scripts/ci_gate.bats` and runs offline using the `tests/mocks/gh` mock.

**Paths-filtered workflows** — each project workflow fires only when files in its directory
change. The root `Makefile` is covered by `scripts.yml`. Release workflows and `auto-merge.yml`
trigger unconditionally.
```

- [ ] **Step 3: Run make test-hooks to verify all BATS tests still pass**

```bash
make test-hooks
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CI section for gate script and paths-filtered workflows"
```
