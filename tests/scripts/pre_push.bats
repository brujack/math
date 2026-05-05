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
