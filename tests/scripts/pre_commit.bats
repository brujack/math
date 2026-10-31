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
    assert_no_match "^make"
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

@test "staged file in factorial/factorial-rs/ does NOT also lint sibling factorial/" {
    export MOCK_GIT_DIFF_NAMES="factorial/factorial-rs/src/main.rs"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    assert_no_match "make -C ${BATS_TEST_TMPDIR}/fake-root/factorial lint"
}

@test "staged file directly in factorial/ calls make for factorial only, not factorial-rs" {
    export MOCK_GIT_DIFF_NAMES="factorial/factorial.py"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-root/factorial lint" "${MOCK_CALLS_FILE}"
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 1 ]
}

@test "staged files in factorial/ and factorial/factorial-rs/ calls make for both dirs" {
    export MOCK_GIT_DIFF_NAMES=$'factorial/factorial.py\nfactorial/factorial-rs/src/main.rs'
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-root/factorial lint" "${MOCK_CALLS_FILE}"
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-root/factorial/factorial-rs lint" "${MOCK_CALLS_FILE}"
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 2 ]
}

@test "staged root-scope tests python runs root lint-python once" {
    export MOCK_GIT_DIFF_NAMES="tests/test_x.py"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    [ "$(grep -c "make -C ${BATS_TEST_TMPDIR}/fake-root lint-python" "${MOCK_CALLS_FILE}")" -eq 1 ]
}

@test "two staged root-scope python files still run lint-python once" {
    export MOCK_GIT_DIFF_NAMES=$'scripts/a.py\ntests/b.py'
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    [ "$(grep -c "make -C ${BATS_TEST_TMPDIR}/fake-root lint-python" "${MOCK_CALLS_FILE}")" -eq 1 ]
}

@test "staged typings stub runs root lint-python" {
    export MOCK_GIT_DIFF_NAMES="typings/gmpy2/__init__.pyi"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    [ "$(grep -c "make -C ${BATS_TEST_TMPDIR}/fake-root lint-python" "${MOCK_CALLS_FILE}")" -eq 1 ]
}

@test "staged .claude/scripts python runs root lint-python" {
    export MOCK_GIT_DIFF_NAMES=".claude/scripts/x.py"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    [ "$(grep -c "make -C ${BATS_TEST_TMPDIR}/fake-root lint-python" "${MOCK_CALLS_FILE}")" -eq 1 ]
}

@test "sub-project python alone does not run root lint-python" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    assert_no_match "lint-python"
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-root/pi lint" "${MOCK_CALLS_FILE}"
}

@test "staged root shell script does not run root lint-python" {
    export MOCK_GIT_DIFF_NAMES="scripts/x.sh"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    assert_no_match "lint-python"
}

@test "root lint-python failure exits non-zero" {
    export MOCK_GIT_DIFF_NAMES="tests/test_x.py"
    export MOCK_MAKE_FAIL_DIR="fake-root"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -ne 0 ]
}
