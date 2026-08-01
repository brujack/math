#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    SCRIPT="${REPO_ROOT}/scripts/mutation-classify.sh"
}

_write_outcomes() {
    local path="$1"
    local body="$2"
    printf '%s' "${body}" >"${path}"
}

@test "missing outcomes.json + exit 0 -> green, no mutants to test" {
    local missing="${BATS_TEST_TMPDIR}/nope.json"
    run "${SCRIPT}" 0 "${missing}" "collatz/collatz-rs"
    [ "${status}" -eq 0 ]
    [ "${output}" = "green: collatz/collatz-rs - no mutants to test (no outcomes.json, exit 0)" ]
}

@test "missing outcomes.json + exit 2 -> red" {
    local missing="${BATS_TEST_TMPDIR}/nope.json"
    run "${SCRIPT}" 2 "${missing}" "collatz/collatz-rs"
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: collatz/collatz-rs - no outcomes.json and exit code 2" ]
}

@test "unparseable outcomes.json -> red" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" "not valid json{{{"
    run "${SCRIPT}" 0 "${outcomes}" "collatz/collatz-rs"
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: collatz/collatz-rs - outcomes.json present but unparseable" ]
}

@test "caught=0 missed=0 unviable=5 + exit 0 -> red (all-unviable)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":5,"caught":0,"missed":0,"timeout":0,"unviable":5}'
    run "${SCRIPT}" 0 "${outcomes}" "amicable/amicable-rs"
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: amicable/amicable-rs - nothing was evaluated (caught=0 missed=0 timeout=0 unviable=5)" ]
}

@test "caught=0 missed=0 timeout=7 + exit 3 -> red (all-timeout)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":7,"caught":0,"missed":0,"timeout":7,"unviable":0}'
    run "${SCRIPT}" 3 "${outcomes}" "amicable/amicable-rs"
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: amicable/amicable-rs - nothing was evaluated (caught=0 missed=0 timeout=7 unviable=0)" ]
}

@test "total_mutants=0 -> red (zero-mutant)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":0,"success":true}'
    run "${SCRIPT}" 0 "${outcomes}" "goldbach/goldbach-rs"
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: goldbach/goldbach-rs - nothing was evaluated (caught=0 missed=0 timeout=0 unviable=0)" ]
}

@test "caught=36 missed=4 unviable=1 + exit 2 -> green with all four counts (real collatz numbers)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":41,"caught":36,"missed":4,"timeout":0,"unviable":1}'
    run "${SCRIPT}" 2 "${outcomes}" "collatz/collatz-rs"
    [ "${status}" -eq 0 ]
    [ "${output}" = "green: collatz/collatz-rs - caught=36 missed=4 timeout=0 unviable=1" ]
}

@test "exit 0 with survivors -> green" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":10,"caught":10,"missed":0,"timeout":0,"unviable":0}'
    run "${SCRIPT}" 0 "${outcomes}" "sq/sq-rs"
    [ "${status}" -eq 0 ]
    [ "${output}" = "green: sq/sq-rs - caught=10 missed=0 timeout=0 unviable=0" ]
}

@test "exit 3 with survivors -> green" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":10,"caught":7,"missed":1,"timeout":2,"unviable":0}'
    run "${SCRIPT}" 3 "${outcomes}" "sq/sq-rs"
    [ "${status}" -eq 0 ]
    [ "${output}" = "green: sq/sq-rs - caught=7 missed=1 timeout=2 unviable=0" ]
}

@test "exit 4 -> red (baseline tests failed)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":10,"caught":7,"missed":1,"timeout":2,"unviable":0}'
    run "${SCRIPT}" 4 "${outcomes}" "sq/sq-rs"
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: sq/sq-rs - exit code 4 (caught=7 missed=1 timeout=2 unviable=0)" ]
}

@test "exit 143 -> red (runner killed)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":10,"caught":7,"missed":1,"timeout":2,"unviable":0}'
    run "${SCRIPT}" 143 "${outcomes}" "sq/sq-rs"
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: sq/sq-rs - exit code 143 (caught=7 missed=1 timeout=2 unviable=0)" ]
}

@test "exit 99 -> red (unknown exit code)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":10,"caught":7,"missed":1,"timeout":2,"unviable":0}'
    run "${SCRIPT}" 99 "${outcomes}" "sq/sq-rs"
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: sq/sq-rs - exit code 99 (caught=7 missed=1 timeout=2 unviable=0)" ]
}
