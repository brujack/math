#!/usr/bin/env bats

# A bare `! grep -q ...` only fails a bats test while it is the last command in
# the body (shellcheck SC2314); anywhere else the negation is silently ignored
# and the assertion cannot fail. Every negative assertion in this file goes
# through here instead, which also names what it found on failure.
assert_no_match() {
    if grep -q "$1" "${MOCK_CALLS_FILE}" 2>/dev/null; then
        printf 'expected no match for %s, but calls were:\n%s\n' \
            "$1" "$(cat "${MOCK_CALLS_FILE}")" >&2
        return 1
    fi
}

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
    assert_no_match "^make"
}

@test "no changed files in push range skips make" {
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    assert_no_match "^make"
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

@test "hook/script change runs the root test target" {
    # Regression guard: the sub-project loop only matches <dir>/*.py and
    # <dir>/**/*.rs, so a change to the hooks themselves matched nothing and
    # pushed with no local test at all.
    export MOCK_GIT_DIFF_NAMES="scripts/pre-push"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test "bats-only change runs the root test target and no sub-project suite" {
    export MOCK_GIT_DIFF_NAMES="tests/scripts/pre_push.bats"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qE "^make -C [^ ]+ test$" "${MOCK_CALLS_FILE}"
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 1 ]
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

@test "rust-only change does not drag in the python sibling suite" {
    # CI scopes pi.py with the single-level glob `pi/*.py`, which cannot match
    # a file under pi/pi-rs/. The hook must not be broader than the gate it
    # approximates.
    export MOCK_GIT_DIFF_NAMES="pi/pi-rs/src/lib.rs"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi/pi-rs test" "${MOCK_CALLS_FILE}"
    assert_no_match "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi test"
}

@test "python-only change does not drag in the rust sibling suite" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi test" "${MOCK_CALLS_FILE}"
    assert_no_match "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi/pi-rs test"
}

@test "scripts-only change reaches the root test target" {
    export MOCK_GIT_DIFF_NAMES="scripts/run-bash-coverage.sh"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qE "^make -C [^ ]+ test$" "${MOCK_CALLS_FILE}" || {
        printf 'expected the root test target, got:\n%s\n' \
            "$(cat "${MOCK_CALLS_FILE}")" >&2
        return 1
    }
}

@test "repo-level python test change triggers the root suite" {
    export MOCK_GIT_DIFF_NAMES="tests/test_triage_log.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qE "^make" "${MOCK_CALLS_FILE}" || {
        printf 'expected a make call for a tests/*.py change, got:\n%s\n' \
            "$(cat "${MOCK_CALLS_FILE}")" >&2
        return 1
    }
}

@test "release workflow change reaches the root test target" {
    # Regression guard: a change to .github/workflows/release-*.yml matches
    # neither the sub-project loop nor the root-test pattern, so
    # tests/test_release_workflows.py — the contract test pinning all eleven
    # release workflows — never runs on the change class it guards.
    export MOCK_GIT_DIFF_NAMES=".github/workflows/release-sq-rs.yml"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qE "^make -C [^ ]+ test$" "${MOCK_CALLS_FILE}" || {
        printf 'expected the root test target, got:\n%s\n' \
            "$(cat "${MOCK_CALLS_FILE}")" >&2
        return 1
    }
}

@test "pyrightconfig.json change reaches the root test target" {
    # Regression guard: pyrightconfig.json changes what the root suite can
    # type-check, but the trigger pattern did not name it.
    export MOCK_GIT_DIFF_NAMES="pyrightconfig.json"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test "requirements-dev.txt change reaches the root test target" {
    # Regression guard: requirements-dev.txt changes what the root suite can
    # import, but the trigger pattern did not name it.
    export MOCK_GIT_DIFF_NAMES="requirements-dev.txt"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test ".claude/scripts/ change reaches the root test target" {
    # Regression guard: .claude/scripts/triage_log.py enters the type-check
    # denominator, but the trigger pattern did not name the directory.
    export MOCK_GIT_DIFF_NAMES=".claude/scripts/triage_log.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test ".github/workflows/scripts.yml change reaches the root test target" {
    # Regression guard: tests/scripts/makefile.bats:133 greps this workflow
    # file, so editing it can turn the root suite red while the hook stays
    # silent unless it is named in the trigger pattern.
    export MOCK_GIT_DIFF_NAMES=".github/workflows/scripts.yml"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test "pi-only change does not reach the root test target" {
    # The point of this file: every existing negative case here either uses
    # an EMPTY diff (which an over-broad root-trigger regex also passes) or
    # names a specific sub-project target rather than the root one. Neither
    # would fail if line 52's regex were widened to match everything. This
    # one names an ordinary sub-project-only change and asserts the root
    # target is never reached.
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    assert_no_match "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$"
}
