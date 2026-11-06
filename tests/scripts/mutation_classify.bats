#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

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

@test "limit 0 with missed=0 -> green" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":5,"caught":5,"missed":0,"timeout":0,"unviable":0}'
    run "${SCRIPT}" 0 "${outcomes}" "e/e-rs" 0
    [ "${status}" -eq 0 ]
    [ "${output}" = "green: e/e-rs - caught=5 missed=0 timeout=0 unviable=0" ]
}

@test "limit 0 with missed=1 -> red, names the survivor from missed.txt" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":5,"caught":4,"missed":1,"timeout":0,"unviable":0}'
    printf 'src/main.rs:10:5: replace foo -> bool with true\n' >"${BATS_TEST_TMPDIR}/missed.txt"
    run --separate-stderr "${SCRIPT}" 2 "${outcomes}" "e/e-rs" 0
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *"red: e/e-rs - missed=1 exceeds max_missed=0 (caught=4 timeout=0 unviable=0)"* ]]
    [[ "${stderr}" == *"  missed: src/main.rs:10:5: replace foo -> bool with true"* ]]
}

@test "limit exceeded without missed.txt -> red, says missed.txt not found" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":5,"caught":4,"missed":1,"timeout":0,"unviable":0}'
    run --separate-stderr "${SCRIPT}" 2 "${outcomes}" "e/e-rs" 0
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *"  missed.txt not found"* ]]
}

@test "limit 2 with missed=2 -> green (boundary equal)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":5,"caught":3,"missed":2,"timeout":0,"unviable":0}'
    run "${SCRIPT}" 2 "${outcomes}" "e/e-rs" 2
    [ "${status}" -eq 0 ]
}

@test "limit mode: caught=0 missed=0 timeout=1 exit 3 -> green" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":1,"caught":0,"missed":0,"timeout":1,"unviable":0}'
    run "${SCRIPT}" 3 "${outcomes}" "e/e-rs" 0
    [ "${status}" -eq 0 ]
    [ "${output}" = "green: e/e-rs - caught=0 missed=0 timeout=1 unviable=0" ]
}

@test "limit mode: all zero with outcomes -> red" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":3,"caught":0,"missed":0,"timeout":0,"unviable":3}'
    run "${SCRIPT}" 0 "${outcomes}" "e/e-rs" 0
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: e/e-rs - nothing was evaluated (caught=0 missed=0 timeout=0 unviable=3)" ]
}

@test "limit mode: missing outcomes + exit 0 -> green" {
    run "${SCRIPT}" 0 "${BATS_TEST_TMPDIR}/nope.json" "e/e-rs" 0
    [ "${status}" -eq 0 ]
    [ "${output}" = "green: e/e-rs - no mutants to test (no outcomes.json, exit 0)" ]
}

@test "limit mode: red exit code still red even within the limit" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":5,"caught":5,"missed":0,"timeout":0,"unviable":0}'
    run "${SCRIPT}" 4 "${outcomes}" "e/e-rs" 0
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: e/e-rs - exit code 4 (caught=5 missed=0 timeout=0 unviable=0)" ]
}

@test "non-numeric max_missed -> red" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":5,"caught":5,"missed":0,"timeout":0,"unviable":0}'
    run --separate-stderr "${SCRIPT}" 0 "${outcomes}" "e/e-rs" abc
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "red: e/e-rs - max_missed 'abc' is not a non-negative integer" ]
}

@test "non-numeric min_caught -> red" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":5,"caught":5,"missed":0,"timeout":0,"unviable":0}'
    run --separate-stderr "${SCRIPT}" 0 "${outcomes}" "e/e-rs" 0 -1
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "red: e/e-rs - min_caught '-1' is not a non-negative integer" ]
}

@test "no 4th arg: missed=3 exit 2 -> green; caught=0 timeout=1 -> red (unchanged)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":8,"caught":5,"missed":3,"timeout":0,"unviable":0}'
    run "${SCRIPT}" 2 "${outcomes}" "e/e-rs"
    [ "${status}" -eq 0 ]
    _write_outcomes "${outcomes}" '{"total_mutants":1,"caught":0,"missed":0,"timeout":1,"unviable":0}'
    run "${SCRIPT}" 3 "${outcomes}" "e/e-rs"
    [ "${status}" -eq 1 ]
}

@test "min_caught 1: missing outcomes + exit 0 -> red" {
    run --separate-stderr "${SCRIPT}" 0 "${BATS_TEST_TMPDIR}/nope.json" "amicable/amicable-rs" 0 1
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "red: amicable/amicable-rs - no outcomes.json (min_caught 1 needs a measured run)" ]
}

@test "min_caught 1: caught=0 timeout=1 -> red below min_caught" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":1,"caught":0,"missed":0,"timeout":1,"unviable":0}'
    run --separate-stderr "${SCRIPT}" 3 "${outcomes}" "amicable/amicable-rs" 0 1
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "red: amicable/amicable-rs - caught=0 below min_caught=1" ]
}

@test "min_caught 1: caught=1 missed=0 -> green" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":1,"caught":1,"missed":0,"timeout":0,"unviable":0}'
    run "${SCRIPT}" 0 "${outcomes}" "amicable/amicable-rs" 0 1
    [ "${status}" -eq 0 ]
    [ "${output}" = "green: amicable/amicable-rs - caught=1 missed=0 timeout=0 unviable=0" ]
}

@test "max_missed with leading zero 08 -> red (invalid octal must not fail open)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":13,"caught":4,"missed":9,"timeout":0,"unviable":0}'
    run --separate-stderr "${SCRIPT}" 2 "${outcomes}" "e/e-rs" 08
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "red: e/e-rs - max_missed '08' is not a non-negative integer" ]
}

@test "min_caught with leading zero 09 -> red" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":1,"caught":0,"missed":0,"timeout":1,"unviable":0}'
    run --separate-stderr "${SCRIPT}" 3 "${outcomes}" "e/e-rs" 0 09
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "red: e/e-rs - min_caught '09' is not a non-negative integer" ]
}

@test "max_missed 010 -> red (would silently read as octal 8)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":10,"caught":2,"missed":8,"timeout":0,"unviable":0}'
    run --separate-stderr "${SCRIPT}" 2 "${outcomes}" "e/e-rs" 010
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "red: e/e-rs - max_missed '010' is not a non-negative integer" ]
}

@test "20-digit min_caught -> red (absurd length rejected)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":5,"caught":5,"missed":0,"timeout":0,"unviable":0}'
    run --separate-stderr "${SCRIPT}" 0 "${outcomes}" "e/e-rs" 0 12345678901234567890
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "red: e/e-rs - min_caught '12345678901234567890' is not a non-negative integer" ]
}

@test "20-digit max_missed -> red (absurd length rejected)" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"total_mutants":5,"caught":5,"missed":0,"timeout":0,"unviable":0}'
    run --separate-stderr "${SCRIPT}" 0 "${outcomes}" "e/e-rs" 12345678901234567890
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "red: e/e-rs - max_missed '12345678901234567890' is not a non-negative integer" ]
}

@test "sweep 0 1: caught=5 missed=1 exit 2 -> red naming the survivor" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"caught":5,"missed":1,"timeout":0,"unviable":0}'
    _write_outcomes "${BATS_TEST_TMPDIR}/missed.txt" 'src/lib.rs:5:5: replace sieve -> Vec<u32> with vec![]'
    run --separate-stderr "${SCRIPT}" 2 "${outcomes}" "prime/prime-rs" 0 1
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *"missed=1 exceeds max_missed=0"* ]]
    [[ "${stderr}" == *"  missed: src/lib.rs:5:5: replace sieve -> Vec<u32> with vec![]"* ]]
}

@test "sweep 0 1: caught=5 missed=0 timeout=2 exit 3 -> green" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"caught":5,"missed":0,"timeout":2,"unviable":0}'
    run --separate-stderr "${SCRIPT}" 3 "${outcomes}" "prime/prime-rs" 0 1
    [ "${status}" -eq 0 ]
    [[ "${output}" == green:\ prime/prime-rs* ]]
}

@test "sweep 0 1: caught=0 missed=0 timeout=3 exit 3 -> red below min_caught" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"caught":0,"missed":0,"timeout":3,"unviable":0}'
    run --separate-stderr "${SCRIPT}" 3 "${outcomes}" "prime/prime-rs" 0 1
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *"caught=0 below min_caught=1"* ]]
}

@test "non-integer outcomes.json counts -> red naming the field" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    local field value
    for field in caught missed timeout unviable; do
        for value in '"1.5"' '-1' '"abc"' '1.5'; do
            _write_outcomes "${outcomes}" "$(jq -c --argjson v "${value}" ".${field} = \$v" <<<'{"caught":3,"missed":0,"timeout":0,"unviable":0}')"
            run "${SCRIPT}" 0 "${outcomes}" "amicable/amicable-rs"
            [ "${status}" -eq 1 ]
            [[ "${output}" == "red: amicable/amicable-rs - outcomes.json ${field} '"*"' is not a non-negative integer" ]]
        done
    done
}

# Without the 9-digit cap, 2^64 wraps to 0 in bash arithmetic and a huge missed count
# would read as green under max_missed 0; a leading zero would be read as octal.
@test "out-of-range or leading-zero outcomes.json counts -> red, 9-digit max -> green" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    local field value
    for field in caught missed; do
        for value in '1000000000' '"18446744073709551616"' '"010"'; do
            _write_outcomes "${outcomes}" "$(jq -c --argjson v "${value}" ".${field} = \$v" <<<'{"caught":3,"missed":0,"timeout":0,"unviable":0}')"
            run "${SCRIPT}" 0 "${outcomes}" "amicable/amicable-rs" 0
            [ "${status}" -eq 1 ]
            [[ "${output}" == "red: amicable/amicable-rs - outcomes.json ${field} '"*"' is not a non-negative integer" ]]
        done
    done
    _write_outcomes "${outcomes}" '{"caught":999999999,"missed":999999999,"timeout":0,"unviable":0}'
    run "${SCRIPT}" 0 "${outcomes}" "amicable/amicable-rs" 999999999
    [ "${status}" -eq 0 ]
    [[ "${output}" == "green: amicable/amicable-rs - caught=999999999 missed=999999999"* ]]
}

# An empty value rendered as an empty tab column would collapse under the tab-IFS read and
# shift later fields left, so the message named unviable whichever field was empty.
@test "empty-string outcomes.json count -> red naming that field" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    local field body
    for field in caught missed timeout unviable; do
        body="$(jq -c --arg f "${field}" '.[$f] = ""' <<<'{"caught":3,"missed":0,"timeout":0,"unviable":0}')"
        _write_outcomes "${outcomes}" "${body}"
        run "${SCRIPT}" 0 "${outcomes}" "amicable/amicable-rs"
        [ "${status}" -eq 1 ]
        [ "${output}" = "red: amicable/amicable-rs - outcomes.json ${field} '\"\"' is not a non-negative integer" ]
    done
}

@test "arithmetic injection in outcomes.json count -> red and not executed" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    local marker="${BATS_TEST_TMPDIR}/pwned"
    printf '{"caught":"a[$(touch %s)]","missed":0,"timeout":0,"unviable":0}' "${marker}" >"${outcomes}"
    run "${SCRIPT}" 0 "${outcomes}" "amicable/amicable-rs"
    [ "${status}" -eq 1 ]
    [[ "${output}" == "red: amicable/amicable-rs - outcomes.json caught '"* ]]
    [ ! -e "${marker}" ]
}

@test "present null or false count -> red naming that field" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    local field value
    for field in caught missed timeout unviable; do
        for value in null false; do
            local body='{"caught":3,"missed":0,"timeout":0,"unviable":0}'
            body="$(printf '%s' "${body}" | jq -c --arg f "${field}" --argjson v "${value}" '.[$f] = $v')"
            _write_outcomes "${outcomes}" "${body}"
            run "${SCRIPT}" 0 "${outcomes}" "m/m-rs" 0
            [ "${status}" -eq 1 ]
            [ "${output}" = "red: m/m-rs - outcomes.json ${field} '${value}' is not a non-negative integer" ]
        done
    done
}

@test "present string count -> red naming that field" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"caught":3,"missed":"0","timeout":0,"unviable":0}'
    run "${SCRIPT}" 0 "${outcomes}" "m/m-rs" 0
    [ "${status}" -eq 1 ]
    [[ "${output}" == "red: m/m-rs - outcomes.json missed '"*"' is not a non-negative integer" ]]
}

@test "absent count keys still read as 0 -> green" {
    local outcomes="${BATS_TEST_TMPDIR}/outcomes.json"
    _write_outcomes "${outcomes}" '{"caught":3}'
    run "${SCRIPT}" 0 "${outcomes}" "m/m-rs" 0
    [ "${status}" -eq 0 ]
    [ "${output}" = "green: m/m-rs - caught=3 missed=0 timeout=0 unviable=0" ]
}
