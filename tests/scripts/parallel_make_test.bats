#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/mock_calls"
    SCRIPT="${REPO_ROOT}/scripts/parallel-make-test.sh"
}

@test "no arguments is a usage error" {
    run bash "${SCRIPT}"
    [ "$status" -eq 2 ]
    [[ "${output}" == *"usage:"* ]]
}

@test "jobs and root without a dir is a usage error" {
    run bash "${SCRIPT}" 4 "${BATS_TEST_TMPDIR}"
    [ "$status" -eq 2 ]
}

@test "a non-numeric jobs value is a usage error" {
    run bash "${SCRIPT}" many "${BATS_TEST_TMPDIR}" pi
    [ "$status" -eq 2 ]
    [[ "${output}" == *"jobs must be a positive integer"* ]]
}

@test "zero jobs is a usage error" {
    run bash "${SCRIPT}" 0 "${BATS_TEST_TMPDIR}" pi
    [ "$status" -eq 2 ]
}

@test "a negative jobs value is a usage error" {
    run bash "${SCRIPT}" -3 "${BATS_TEST_TMPDIR}" pi
    [ "$status" -eq 2 ]
}

@test "usage errors run no make" {
    run bash "${SCRIPT}" x "${BATS_TEST_TMPDIR}" pi
    [ ! -e "${MOCK_CALLS_FILE}" ]
}

@test "all passing prints ok lines in input order and exits 0" {
    run bash "${SCRIPT}" 4 "${BATS_TEST_TMPDIR}" pi fib/fib-rs e
    [ "$status" -eq 0 ]
    [ "${lines[0]}" = "ok pi" ]
    [ "${lines[1]}" = "ok fib/fib-rs" ]
    [ "${lines[2]}" = "ok e" ]
    [ "${#lines[@]}" -eq 3 ]
}

@test "single job still runs every dir" {
    run bash "${SCRIPT}" 1 "${BATS_TEST_TMPDIR}" pi fib
    [ "$status" -eq 0 ]
    [ "$(grep -c '^make' "${MOCK_CALLS_FILE}")" -eq 2 ]
}

@test "make is invoked with -C root/dir test" {
    run bash "${SCRIPT}" 2 "${BATS_TEST_TMPDIR}" pi/pi-rs
    grep -qxF "make -C ${BATS_TEST_TMPDIR}/pi/pi-rs test" "${MOCK_CALLS_FILE}"
}

@test "a failure keeps input order, prints its log and exits 1" {
    export MOCK_MAKE_FAIL_DIR="fib"
    run bash "${SCRIPT}" 4 "${BATS_TEST_TMPDIR}" pi fib e
    [ "$status" -eq 1 ]
    [ "${lines[0]}" = "ok pi" ]
    [ "${lines[1]}" = "FAIL fib" ]
    [ "${lines[2]}" = "ok e" ]
    [[ "${output}" == *"==== log: fib ===="* ]]
    [[ "${output}" == *"simulated failure in ${BATS_TEST_TMPDIR}/fib"* ]]
}

@test "a passing dir's log is not printed" {
    export MOCK_MAKE_FAIL_DIR="fib"
    run bash "${SCRIPT}" 4 "${BATS_TEST_TMPDIR}" pi fib
    [[ "${output}" != *"==== log: pi ===="* ]]
}

@test "a missing status file counts as FAIL" {
    export MOCK_MAKE_KILL_DIR="e"
    run bash "${SCRIPT}" 4 "${BATS_TEST_TMPDIR}" pi e
    [ "$status" -eq 1 ]
    # xargs reports the killed child on stderr, so match lines rather than index.
    [[ "${output}" == *$'ok pi\n'* ]]
    [[ "${output}" == *$'FAIL e\n'* ]]
}

@test "a nested dir failure is reported under its full path" {
    export MOCK_MAKE_FAIL_DIR="fib/fib-rs"
    run bash "${SCRIPT}" 2 "${BATS_TEST_TMPDIR}" fib fib/fib-rs
    [ "$status" -eq 1 ]
    [ "${lines[0]}" = "ok fib" ]
    [ "${lines[1]}" = "FAIL fib/fib-rs" ]
}

@test "the temp directory is removed afterwards" {
    export TMPDIR="${BATS_TEST_TMPDIR}/tmp"
    mkdir -p "${TMPDIR}"
    run bash "${SCRIPT}" 2 "${BATS_TEST_TMPDIR}" pi
    [ -z "$(ls -A "${TMPDIR}")" ]
}

@test "the temp directory is removed after a failure too" {
    export TMPDIR="${BATS_TEST_TMPDIR}/tmp"
    mkdir -p "${TMPDIR}"
    export MOCK_MAKE_FAIL_DIR="pi"
    run bash "${SCRIPT}" 2 "${BATS_TEST_TMPDIR}" pi
    [ "$status" -eq 1 ]
    [ -z "$(ls -A "${TMPDIR}")" ]
}

@test "an unwritable TMPDIR fails without running make" {
    export TMPDIR="${BATS_TEST_TMPDIR}/does-not-exist"
    run bash "${SCRIPT}" 2 "${BATS_TEST_TMPDIR}" pi
    [ "$status" -ne 0 ]
    [ ! -e "${MOCK_CALLS_FILE}" ]
}

@test "sourcing the script runs nothing" {
    run bash -c 'source "$1" && declare -F main run_suites' _ "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ ! -e "${MOCK_CALLS_FILE}" ]
}
