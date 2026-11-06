#!/usr/bin/env bats
# scripts/mutation-exit-code.sh: the one reader of <crate>/mutants.out/exit-code.

bats_require_minimum_version 1.5.0

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    export HOME="${BATS_TEST_TMPDIR}"
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    SCRIPT="${REPO_ROOT}/scripts/mutation-exit-code.sh"
    CRATE="${BATS_TEST_TMPDIR}/a/a-rs"
    mkdir -p "${CRATE}/mutants.out"
}

# _write <raw printf format> [dir]
_write() {
    printf -- "$1" >"${2:-${CRATE}}/mutants.out/exit-code"
}

@test "missing file is red with the exact line on stderr" {
    rm -f "${CRATE}/mutants.out/exit-code"
    run --separate-stderr bash "${SCRIPT}" "${CRATE}"
    [ "${status}" -eq 1 ]
    [ -z "${output}" ]
    [ "${stderr}" = "red: ${CRATE} - no mutants.out/exit-code" ]
}

@test "empty file is red" {
    : >"${CRATE}/mutants.out/exit-code"
    run --separate-stderr bash "${SCRIPT}" "${CRATE}"
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "red: ${CRATE} - mutants.out/exit-code '' is not an integer" ]
}

@test "non-integer is red and quoted" {
    _write 'oops\n'
    run --separate-stderr bash "${SCRIPT}" "${CRATE}"
    [ "${status}" -eq 1 ]
    [ -z "${output}" ]
    [ "${stderr}" = "red: ${CRATE} - mutants.out/exit-code 'oops' is not an integer" ]
}

@test "negative is red" {
    _write '-1\n'
    run --separate-stderr bash "${SCRIPT}" "${CRATE}"
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *"'-1' is not an integer" ]]
}

@test "four digits is red" {
    _write '1000\n'
    run --separate-stderr bash "${SCRIPT}" "${CRATE}"
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *"'1000' is not an integer" ]]
}

@test "leading zero is red" {
    _write '01\n'
    run --separate-stderr bash "${SCRIPT}" "${CRATE}"
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *"'01' is not an integer" ]]
}

@test "valid values print the integer and exit 0" {
    local value
    for value in 0 3 999; do
        printf '%s\n' "${value}" >"${CRATE}/mutants.out/exit-code"
        run --separate-stderr bash "${SCRIPT}" "${CRATE}"
        [ "${status}" -eq 0 ]
        [ "${output}" = "${value}" ]
        [ -z "${stderr}" ]
    done
}

@test "file without a trailing newline is accepted" {
    _write '4'
    run bash "${SCRIPT}" "${CRATE}"
    [ "${status}" -eq 0 ]
    [ "${output}" = "4" ]
}

@test "crate dir with spaces" {
    local spaced="${BATS_TEST_TMPDIR}/my crate/x-rs"
    mkdir -p "${spaced}/mutants.out"
    _write '2\n' "${spaced}"
    run bash "${SCRIPT}" "${spaced}"
    [ "${status}" -eq 0 ]
    [ "${output}" = "2" ]
    rm -f "${spaced}/mutants.out/exit-code"
    run --separate-stderr bash "${SCRIPT}" "${spaced}"
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "red: ${spaced} - no mutants.out/exit-code" ]
}

@test "no argument exits 2 with usage" {
    run --separate-stderr bash "${SCRIPT}"
    [ "${status}" -eq 2 ]
    [[ "${stderr}" == "Usage:"* ]]
}

@test "sourcing defines the function and runs nothing" {
    run bash -c 'source "$1" && declare -F mutation_exit_code' _ "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [ "${output}" = "mutation_exit_code" ]
}
