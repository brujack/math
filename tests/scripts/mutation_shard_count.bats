#!/usr/bin/env bats
# scripts/mutation-shard-count.sh: compares a shard's outcomes.json total_mutants
# with the count the planner expected.

bats_require_minimum_version 1.5.0

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    export HOME="${BATS_TEST_TMPDIR}"
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    SCRIPT="${REPO_ROOT}/scripts/mutation-shard-count.sh"
    OUTCOMES="${BATS_TEST_TMPDIR}/outcomes.json"
}

# _outcomes <raw printf format>
_outcomes() {
    printf -- "$1" >"${OUTCOMES}"
}

@test "equal count is green and silent" {
    _outcomes '{"total_mutants": 5}'
    run --separate-stderr bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/2" 5
    [ "${status}" -eq 0 ]
    [ -z "${output}" ]
    [ -z "${stderr}" ]
}

@test "unequal count is red with the exact line on stdout" {
    _outcomes '{"total_mutants": 4}'
    run --separate-stderr bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/2" 5
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 0/2 tested 4 mutants, plan expected 5" ]
    [ -z "${stderr}" ]
}

@test "more mutants than planned is red" {
    _outcomes '{"total_mutants": 6}'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/2" 5
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 0/2 tested 6 mutants, plan expected 5" ]
}

@test "missing file counts as zero mutants tested" {
    rm -f "${OUTCOMES}"
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 1/3" 3
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 1/3 tested 0 mutants, plan expected 3" ]
}

@test "non-JSON file is unreadable" {
    _outcomes 'not json\n'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 3
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 0/1 cannot read total_mutants from ${OUTCOMES}" ]
}

@test "empty file is unreadable" {
    : >"${OUTCOMES}"
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 3
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 0/1 cannot read total_mutants from ${OUTCOMES}" ]
}

@test "JSON without total_mutants is unreadable" {
    _outcomes '{"outcomes": []}'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 3
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 0/1 cannot read total_mutants from ${OUTCOMES}" ]
}

@test "non-integer total_mutants is unreadable, never compared" {
    local raw
    for raw in '4.5' '"4"' 'null' '-1' 'true' '[4]'; do
        _outcomes "{\"total_mutants\": ${raw}}"
        run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 4
        [ "${status}" -eq 1 ]
        [ "${output}" = "red: a-rs 0/1 cannot read total_mutants from ${OUTCOMES}" ]
    done
}

@test "integral float total_mutants is accepted" {
    _outcomes '{"total_mutants": 4.0}'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 4
    [ "${status}" -eq 0 ]
    [ -z "${output}" ]
}

@test "total_mutants zero against a positive plan is red" {
    _outcomes '{"total_mutants": 0}'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 3
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 0/1 tested 0 mutants, plan expected 3" ]
}

@test "bad count exits 2 with usage on stderr" {
    _outcomes '{"total_mutants": 5}'
    local bad
    for bad in 0 x -1 1.5 01 ''; do
        run --separate-stderr bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" "${bad}"
        [ "${status}" -eq 2 ]
        [ -z "${output}" ]
        [[ "${stderr}" == "Usage:"* ]]
    done
}

@test "wrong argument count exits 2 with usage on stderr" {
    run --separate-stderr bash "${SCRIPT}"
    [ "${status}" -eq 2 ]
    [[ "${stderr}" == "Usage:"* ]]
    run --separate-stderr bash "${SCRIPT}" "${OUTCOMES}" label
    [ "${status}" -eq 2 ]
    [[ "${stderr}" == "Usage:"* ]]
    run --separate-stderr bash "${SCRIPT}" "${OUTCOMES}" label 3 extra
    [ "${status}" -eq 2 ]
    [[ "${stderr}" == "Usage:"* ]]
}

@test "paths with spaces work and the input is left unchanged" {
    local spaced="${BATS_TEST_TMPDIR}/my dir/outcomes.json"
    mkdir -p "${BATS_TEST_TMPDIR}/my dir"
    printf '{"total_mutants": 7}\n' >"${spaced}"
    local before
    before="$(cksum <"${spaced}")"
    run bash "${SCRIPT}" "${spaced}" "a-rs 0/1" 7
    [ "${status}" -eq 0 ]
    run bash "${SCRIPT}" "${spaced}" "a-rs 0/1" 7
    [ "${status}" -eq 0 ]
    [ "$(cksum <"${spaced}")" = "${before}" ]
}

@test "sourcing defines the function and runs nothing" {
    run bash -c 'source "$1" && declare -F mutation_shard_count' _ "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [ "${output}" = "mutation_shard_count" ]
}

@test "exponent-form total is unreadable, never green" {
    _outcomes '{"total_mutants": 1e300}'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 5
    [ "${status}" -eq 1 ]
    [[ "${output}" == "red: a-rs 0/1 "* ]]
}

@test "two JSON documents are unreadable" {
    _outcomes '{"total_mutants":5}{"total_mutants":3}'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 5
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 0/1 cannot read total_mutants from ${OUTCOMES}" ]
}

@test "duplicate top-level total_mutants key is unreadable" {
    _outcomes '{"total_mutants":3,"total_mutants":5}'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 5
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 0/1 cannot read total_mutants from ${OUTCOMES}" ]
}

@test "a second document without total_mutants is unreadable" {
    _outcomes '{"total_mutants":5}{"other":1}'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 5
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 0/1 cannot read total_mutants from ${OUTCOMES}" ]
}

@test "a repeated top-level key with a container value is unreadable" {
    _outcomes '{"a":[1],"a":[],"total_mutants":5}'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 5
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 0/1 cannot read total_mutants from ${OUTCOMES}" ]
}

@test "nested key named like a top-level key is not a duplicate" {
    _outcomes '{"total_mutants":5,"x":{"total_mutants":3}}'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 5
    [ "${status}" -eq 0 ]
    [ -z "${output}" ]
}

@test "count beyond 64 bits does not wrap to a match" {
    _outcomes '{"total_mutants": 5}'
    run bash "${SCRIPT}" "${OUTCOMES}" "a-rs 0/1" 18446744073709551621
    [ "${status}" -eq 1 ]
    [ "${output}" = "red: a-rs 0/1 tested 5 mutants, plan expected 18446744073709551621" ]
}
