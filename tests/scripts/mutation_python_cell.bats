#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/calls"
    export GITHUB_WORKSPACE="${BATS_TEST_TMPDIR}/ws"
    export GITHUB_STEP_SUMMARY="${BATS_TEST_TMPDIR}/summary"
    mkdir -p "${GITHUB_WORKSPACE}"
    SCRIPT="${REPO_ROOT}/scripts/mutation-python-cell.sh"
}

@test "failing make leaves the red line and exits with make's code" {
    export MOCK_MAKE_EXIT=2
    run -2 bash "${SCRIPT}" fib 0 10
    [ "$(cat "${GITHUB_WORKSPACE}/status/fib-0")" = "red: fib-0 — make mutants failed (exit 2)" ]
}

@test "green status written by make is left untouched" {
    export MOCK_MAKE_STATUS_LINE="green: fib-0 — 5 caught"
    run -0 bash "${SCRIPT}" fib 0 10
    [ "$(cat "${GITHUB_WORKSPACE}/status/fib-0")" = "green: fib-0 — 5 caught" ]
}

@test "make exit 0 without a status file is red with exit 1" {
    run -1 bash "${SCRIPT}" fib 0 10
    [ "$(cat "${GITHUB_WORKSPACE}/status/fib-0")" = "red: fib-0 — make mutants failed (exit 1)" ]
}

@test "stale status file is removed before make runs" {
    mkdir -p "${GITHUB_WORKSPACE}/status" "${GITHUB_WORKSPACE}/survivors"
    printf 'green: stale\n' > "${GITHUB_WORKSPACE}/status/fib-0"
    printf 'stale:1 op\n' > "${GITHUB_WORKSPACE}/survivors/fib-0.txt"
    export MOCK_MAKE_EXIT=2
    run -2 bash "${SCRIPT}" fib 0 10
    [ "$(cat "${GITHUB_WORKSPACE}/status/fib-0")" = "red: fib-0 — make mutants failed (exit 2)" ]
    [ ! -e "${GITHUB_WORKSPACE}/survivors/fib-0.txt" ]
}

@test "make receives the exact arguments" {
    export MOCK_MAKE_STATUS_LINE="green: x"
    run -0 bash "${SCRIPT}" perfect-numbers 3 10
    local ws="${GITHUB_WORKSPACE}"
    [ "$(cat "${MOCK_CALLS_FILE}")" = "make -C perfect-numbers mutants MUTANT_SHARD=3/10 CELL_LABEL=perfect-numbers-3 STATUS_OUT=${ws}/status/perfect-numbers-3 SURVIVORS_OUT=${ws}/survivors/perfect-numbers-3.txt" ]
}

@test "status is appended to the step summary" {
    export MOCK_MAKE_EXIT=2
    run -2 bash "${SCRIPT}" fib 0 10
    [ "$(cat "${GITHUB_STEP_SUMMARY}")" = "red: fib-0 — make mutants failed (exit 2)" ]
}

@test "unknown directory exits 2 without calling make" {
    run -2 bash "${SCRIPT}" bogus 0 10
    [ ! -e "${MOCK_CALLS_FILE}" ]
}

@test "a Rust crate directory is rejected" {
    run -2 bash "${SCRIPT}" prime 0 10
    [ ! -e "${MOCK_CALLS_FILE}" ]
}

@test "non-decimal k exits 2 without calling make" {
    run -2 bash "${SCRIPT}" fib "1/2" 10
    [ ! -e "${MOCK_CALLS_FILE}" ]
}

@test "non-decimal n exits 2 without calling make" {
    run -2 bash "${SCRIPT}" fib 0 x
    [ ! -e "${MOCK_CALLS_FILE}" ]
}

@test "missing arguments exit 2" {
    run -2 bash "${SCRIPT}" fib
    [ ! -e "${MOCK_CALLS_FILE}" ]
}
