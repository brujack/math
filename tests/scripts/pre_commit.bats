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
    # The hook's real fallback list names absolute install paths that exist on
    # dev machines, so a test that leaves it alone can run the real ggshield.
    # Empty fallbacks and no override make tests/mocks/ggshield on PATH the only
    # binary any test can reach unless it says otherwise.
    export GGSHIELD_FALLBACK_PATHS=""
    unset GGSHIELD_BIN
}

# A recording ggshield stub at an absolute path, for the override and fallback
# branches. It logs under a distinct name so a test can tell it from the PATH
# mock, and exits with MOCK_GGSHIELD_EXIT like the mock does.
make_stub() {
    local stub="$1"
    mkdir -p "$(dirname "${stub}")"
    printf '#!/usr/bin/env bash\nprintf "stub %%s %%s\\n" "%s" "$*" >> "${MOCK_CALLS_FILE}"\nexit "${MOCK_GGSHIELD_EXIT:-0}"\n' \
        "${stub}" > "${stub}"
    chmod +x "${stub}"
}

# PATH with every entry that holds an executable ggshield removed (the mocks
# dir and any real install, so a dev machine's ggshield is never run) and a
# dir holding only the git and make mocks prepended, so `command -v ggshield`
# finds nothing.
path_without_ggshield() {
    local no_ggs="${BATS_TEST_TMPDIR}/no_ggs"
    mkdir -p "${no_ggs}"
    ln -sf "${REPO_ROOT}/tests/mocks/git"  "${no_ggs}/git"
    ln -sf "${REPO_ROOT}/tests/mocks/make" "${no_ggs}/make"
    local entry kept=""
    local -a entries
    IFS=':' read -r -a entries <<< "${PATH}"
    for entry in "${entries[@]}"; do
        [[ -n "${entry}" && -x "${entry}/ggshield" ]] && continue
        kept="${kept:+${kept}:}${entry}"
    done
    printf '%s:%s' "${no_ggs}" "${kept}"
}

@test "path_without_ggshield leaves no ggshield resolvable" {
    run env "PATH=$(path_without_ggshield)" bash -c 'command -v ggshield'
    [ "$status" -ne 0 ]
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

@test "ggshield unresolvable anywhere: exits 0 but says the scan did not run" {
    run env "PATH=$(path_without_ggshield)" bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    [[ "$output" == *"SECRET SCAN DID NOT RUN"* ]]
    assert_no_match "ggshield"
}

@test "ggshield on PATH runs the pre-commit scan with --fail-on-server-error" {
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    grep -qx "ggshield secret scan pre-commit --fail-on-server-error" "${MOCK_CALLS_FILE}"
}

@test "ggshield off PATH but at a fallback path is found and run" {
    local stub="${BATS_TEST_TMPDIR}/fallback/ggshield"
    make_stub "${stub}"
    export GGSHIELD_FALLBACK_PATHS="${BATS_TEST_TMPDIR}/absent/ggshield ${stub}"
    run env "PATH=$(path_without_ggshield)" bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    grep -qx "stub ${stub} secret scan pre-commit --fail-on-server-error" "${MOCK_CALLS_FILE}"
    [[ "$output" != *"SECRET SCAN DID NOT RUN"* ]]
}

@test "override set to an executable is used ahead of PATH" {
    local stub="${BATS_TEST_TMPDIR}/override/ggshield"
    make_stub "${stub}"
    export GGSHIELD_BIN="${stub}"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    grep -qx "stub ${stub} secret scan pre-commit --fail-on-server-error" "${MOCK_CALLS_FILE}"
    assert_no_match "^ggshield "
}

@test "override set but empty falls through to PATH" {
    export GGSHIELD_BIN=""
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    grep -qx "ggshield secret scan pre-commit --fail-on-server-error" "${MOCK_CALLS_FILE}"
}

@test "override set to a non-executable path blocks the commit" {
    local stub="${BATS_TEST_TMPDIR}/override/ggshield"
    make_stub "${stub}"
    chmod -x "${stub}"
    export GGSHIELD_BIN="${stub}"
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -ne 0 ]
    [[ "$output" == *"is set but not executable"* ]]
    assert_no_match "ggshield"
}

@test "ggshield exit 1 (secret found) blocks the commit" {
    export MOCK_GGSHIELD_EXIT=1
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -ne 0 ]
}

@test "ggshield exit 2 (usage error) blocks the commit" {
    export MOCK_GGSHIELD_EXIT=2
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -ne 0 ]
    [[ "$output" == *"(exit 2)"* ]]
}

@test "ggshield exit 3 (cannot authenticate) warns and lets the commit through" {
    export MOCK_GGSHIELD_EXIT=3
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    [[ "$output" == *"(exit 3)"* ]]
    [[ "$output" == *"SECRET SCAN DID NOT RUN"* ]]
}

@test "ggshield exit 4 (server unavailable) blocks the commit" {
    export MOCK_GGSHIELD_EXIT=4
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -ne 0 ]
    [[ "$output" == *"(exit 4)"* ]]
}

@test "ggshield exit 128 blocks the commit" {
    export MOCK_GGSHIELD_EXIT=128
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -ne 0 ]
    [[ "$output" == *"(exit 128)"* ]]
}

@test "ggshield unknown exit code fails closed" {
    export MOCK_GGSHIELD_EXIT=7
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -ne 0 ]
    [[ "$output" == *"(exit 7)"* ]]
}

@test "ggshield exit 0 lets the commit through with no warning" {
    export MOCK_GGSHIELD_EXIT=0
    run bash "${REPO_ROOT}/scripts/pre-commit"
    [ "$status" -eq 0 ]
    [[ "$output" != *"SECRET SCAN DID NOT RUN"* ]]
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
