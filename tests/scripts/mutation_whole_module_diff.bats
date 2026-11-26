#!/usr/bin/env bats

load ../helpers/common

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    export HOME="${BATS_TEST_TMPDIR}/home"
    export XDG_CONFIG_HOME="${BATS_TEST_TMPDIR}/xdg"
    mkdir -p "${HOME}" "${XDG_CONFIG_HOME}"
    SCRIPT="${REPO_ROOT}/scripts/mutation-whole-module-diff.sh"
    WORK="${BATS_TEST_TMPDIR}/work"
    mkdir -p "${WORK}/pi" "${WORK}/perfect-numbers"
    printf 'a = 1\nb = 2\nc = 3\n' >"${WORK}/pi/pi.py"
    printf '[[equivalent]]\nline = 2\n' >"${WORK}/pi/mutants-equivalent.toml"
    printf 'x = 1\n' >"${WORK}/perfect-numbers/perfect_numbers.py"
    OUT="${BATS_TEST_TMPDIR}/out.diff"
}

@test "adds the module and the equivalents toml as new files relative to the dir" {
    cd "${WORK}"
    run bash "${SCRIPT}" pi "${OUT}" </dev/null
    [ "${status}" -eq 0 ]
    grep -qxF -- '--- /dev/null' "${OUT}"
    grep -qxF -- '+++ b/pi.py' "${OUT}"
    grep -qxF -- '+++ b/mutants-equivalent.toml' "${OUT}"
    grep -qxF -- '@@ -0,0 +1,3 @@' "${OUT}"
    grep -qxF -- '@@ -0,0 +1,2 @@' "${OUT}"
    grep -qxF -- '+b = 2' "${OUT}"
    grep -qxF -- '+line = 2' "${OUT}"
}

@test "the module comes first, then the toml" {
    cd "${WORK}"
    bash "${SCRIPT}" pi "${OUT}" </dev/null
    [ "$(grep -n '^+++ ' "${OUT}" | cut -d: -f1 | head -1)" -lt "$(grep -n '^+++ b/mutants-equivalent.toml' "${OUT}" | cut -d: -f1)" ]
}

@test "works without the toml" {
    cd "${WORK}"
    run bash "${SCRIPT}" perfect-numbers "${OUT}" </dev/null
    [ "${status}" -eq 0 ]
    grep -qxF -- '+++ b/perfect_numbers.py' "${OUT}"
    run grep -c 'mutants-equivalent' "${OUT}"
    [ "${output}" = "0" ]
}

@test "reads the working tree, so a dirty file is honoured" {
    cd "${WORK}"
    printf 'dirty = 9\n' >>"${WORK}/pi/pi.py"
    bash "${SCRIPT}" pi "${OUT}" </dev/null
    grep -qxF -- '+dirty = 9' "${OUT}"
    grep -qxF -- '@@ -0,0 +1,4 @@' "${OUT}"
}

@test "trailing slash on the dir is accepted" {
    cd "${WORK}"
    run bash "${SCRIPT}" pi/ "${OUT}" </dev/null
    [ "${status}" -eq 0 ]
    grep -qxF -- '+++ b/pi.py' "${OUT}"
}

@test "missing module fails closed with a message and writes no diff" {
    cd "${WORK}"
    rm "${WORK}/pi/pi.py"
    run bash "${SCRIPT}" pi "${OUT}" </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"pi/pi.py"* ]]
    [ ! -s "${OUT}" ]
}

@test "missing dir fails closed" {
    cd "${WORK}"
    run bash "${SCRIPT}" nope "${OUT}" </dev/null
    [ "${status}" -ne 0 ]
}

@test "wrong argument count exits 2" {
    run bash "${SCRIPT}" pi </dev/null
    [ "${status}" -eq 2 ]
}

@test "unwritable output fails closed" {
    cd "${WORK}"
    run bash "${SCRIPT}" pi /dev/null/nope </dev/null
    [ "${status}" -ne 0 ]
}

@test "git diff failure other than 'differences' fails closed" {
    cd "${WORK}"
    mkdir -p "${BATS_TEST_TMPDIR}/bin"
    printf '#!/usr/bin/env bash\nexit 129\n' >"${BATS_TEST_TMPDIR}/bin/git"
    chmod +x "${BATS_TEST_TMPDIR}/bin/git"
    PATH="${BATS_TEST_TMPDIR}/bin:${PATH}" run bash "${SCRIPT}" pi "${OUT}" </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"git diff failed"* ]]
}

@test "exit status 1 from git diff --no-index counts as success" {
    cd "${WORK}"
    mkdir -p "${BATS_TEST_TMPDIR}/bin"
    printf '#!/usr/bin/env bash\nprintf "+++ b/x\\n"\nexit 1\n' >"${BATS_TEST_TMPDIR}/bin/git"
    chmod +x "${BATS_TEST_TMPDIR}/bin/git"
    PATH="${BATS_TEST_TMPDIR}/bin:${PATH}" run bash "${SCRIPT}" pi "${OUT}" </dev/null
    [ "${status}" -eq 0 ]
}
