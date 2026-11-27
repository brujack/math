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

@test "failing only the module diff call (no toml) is red and leaves no output file" {
    cd "${WORK}"
    rm "${WORK}/pi/mutants-equivalent.toml"
    mkdir -p "${BATS_TEST_TMPDIR}/bin"
    cat >"${BATS_TEST_TMPDIR}/bin/git" <<'MOCK'
#!/usr/bin/env bash
[[ "${*: -1}" == "pi.py" ]] && exit 129
exit 0
MOCK
    chmod +x "${BATS_TEST_TMPDIR}/bin/git"
    PATH="${BATS_TEST_TMPDIR}/bin:${PATH}" run bash "${SCRIPT}" pi "${OUT}" </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"git diff failed for pi.py"* ]]
    [ ! -e "${OUT}" ]
}

@test "failing only the toml diff call is red and leaves no output file" {
    cd "${WORK}"
    mkdir -p "${BATS_TEST_TMPDIR}/bin"
    cat >"${BATS_TEST_TMPDIR}/bin/git" <<'MOCK'
#!/usr/bin/env bash
[[ "${*: -1}" == "mutants-equivalent.toml" ]] && exit 129
printf '+++ b/pi.py\n'
exit 1
MOCK
    chmod +x "${BATS_TEST_TMPDIR}/bin/git"
    PATH="${BATS_TEST_TMPDIR}/bin:${PATH}" run bash "${SCRIPT}" pi "${OUT}" </dev/null
    [ "${status}" -ne 0 ]
    [ ! -e "${OUT}" ]
}

@test "an absolute dir derives the module from its last component" {
    cd "${BATS_TEST_TMPDIR}"
    run bash "${SCRIPT}" "${WORK}/pi" "${OUT}" </dev/null
    [ "${status}" -eq 0 ]
    grep -qxF -- '+++ b/pi.py' "${OUT}"
}

@test "a nested dir with a hyphen derives the module from its last component" {
    cd "${WORK}"
    mkdir -p sub/perfect-numbers
    printf 'y = 2\n' >sub/perfect-numbers/perfect_numbers.py
    run bash "${SCRIPT}" sub/perfect-numbers "${OUT}" </dev/null
    [ "${status}" -eq 0 ]
    grep -qxF -- '+++ b/perfect_numbers.py' "${OUT}"
}

@test "user git config (noprefix, forced colour) does not change the diff format" {
    cd "${WORK}"
    printf '[diff]\n\tnoprefix = true\n[color]\n\tui = always\n' >"${BATS_TEST_TMPDIR}/gitconfig"
    GIT_CONFIG_GLOBAL="${BATS_TEST_TMPDIR}/gitconfig" run bash "${SCRIPT}" pi "${OUT}" </dev/null
    [ "${status}" -eq 0 ]
    grep -qxF -- '+++ b/pi.py' "${OUT}"
    grep -qxF -- '+++ b/mutants-equivalent.toml' "${OUT}"
    ! command grep -q $'\x1b' "${OUT}"
}

@test "extra arguments exit 2" {
    cd "${WORK}"
    run bash "${SCRIPT}" pi "${OUT}" extra </dev/null
    [ "${status}" -eq 2 ]
    [ ! -e "${OUT}" ]
}

@test "a relative out-diff is written relative to the caller's cwd, not the dir" {
    cd "${WORK}"
    run bash "${SCRIPT}" pi rel.diff </dev/null
    [ "${status}" -eq 0 ]
    [ -s "${WORK}/rel.diff" ]
    [ ! -e "${WORK}/pi/rel.diff" ]
}
