#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export ARTIFACT_DIR="${BATS_TEST_TMPDIR}/artifact"
    export OUT_DIR="${BATS_TEST_TMPDIR}/out"
    export GITHUB_STEP_SUMMARY="${BATS_TEST_TMPDIR}/summary.md"
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/calls"
    # Malformed spec so a leaked real gh fails in its own argument parser.
    export REPO="invalid-repo-spec-no-slash"
    export RUN_URL="https://github.com/brujack/math/actions/runs/456"
    export REF="refs/heads/master"
    export EVENT="schedule"
    export EXPECTED_STATUS_UNITS="fib-0 fib-1 perfect-numbers-0 perfect-numbers-1"
    mkdir -p "${ARTIFACT_DIR}/status" "${ARTIFACT_DIR}/survivors" "${OUT_DIR}"
    : > "${GITHUB_STEP_SUMMARY}"
    : > "${MOCK_CALLS_FILE}"
}

# write_cell <unit> <survivors> <timed-out> <jobs>: a green status file plus
# <survivors> survivor lines.
write_cell() {
    local _unit="${1}" _s="${2}" _t="${3}" _k="${4}" _i
    printf 'green: %s — %s surviving, %s timed out, %s jobs\n' "${_unit}" "${_s}" "${_t}" "${_k}" \
        > "${ARTIFACT_DIR}/status/${_unit}"
    : > "${ARTIFACT_DIR}/survivors/${_unit}.txt"
    for ((_i = 1; _i <= _s; _i++)); do
        printf '%s.py:%d operator\n' "${_unit%-*}" "$((_i * 10))" >> "${ARTIFACT_DIR}/survivors/${_unit}.txt"
    done
}

write_all_cells() {
    write_cell fib-0 3 1 10
    write_cell fib-1 2 0 12
    write_cell perfect-numbers-0 5 2 20
    write_cell perfect-numbers-1 0 0 15
}

assert_all_gh_calls_carry_repo() {
    local _total _with_repo
    _total=$(grep -c '^gh ' "${MOCK_CALLS_FILE}")
    _with_repo=$(grep '^gh ' "${MOCK_CALLS_FILE}" | grep -c -- "--repo")
    [ "${_total}" -gt 0 ]
    [ "${_total}" -eq "${_with_repo}" ]
}

@test "table sums green cells per sub-project" {
    write_all_cells
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -eq 0 ]
    grep -qF '| fib | 2/2 | 22 | 5 | 1 | 5 |' "${GITHUB_STEP_SUMMARY}"
    grep -qF '| perfect-numbers | 2/2 | 35 | 5 | 2 | 5 |' "${GITHUB_STEP_SUMMARY}"
}

@test "header fields reach summary and issue body" {
    write_all_cells
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -eq 0 ]
    for _f in "${GITHUB_STEP_SUMMARY}" "${MOCK_CALLS_FILE}"; do
        grep -qF "${REF}" "${_f}"
        grep -qF "${EVENT}" "${_f}"
        grep -qF "${RUN_URL}" "${_f}"
        grep -qF '4 of 4' "${_f}"
        grep -qF 'mutants-survivors-python' "${_f}"
    done
}

@test "open issue -> comment on it" {
    write_all_cells
    export MOCK_GH_ISSUE_LIST=17
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -eq 0 ]
    grep -q '^gh issue comment 17 ' "${MOCK_CALLS_FILE}"
    run ! grep -q '^gh issue create' "${MOCK_CALLS_FILE}"
    assert_all_gh_calls_carry_repo
}

@test "no open issue -> label create then issue create" {
    write_all_cells
    export MOCK_GH_ISSUE_LIST=
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -eq 0 ]
    _label=$(grep -n '^gh label create mutation-report-python' "${MOCK_CALLS_FILE}" | cut -d: -f1)
    _create=$(grep -n '^gh issue create' "${MOCK_CALLS_FILE}" | cut -d: -f1)
    [ -n "${_label}" ]
    [ "${_label}" -lt "${_create}" ]
    grep -q -- '--label mutation-report-python' "${MOCK_CALLS_FILE}"
    assert_all_gh_calls_carry_repo
}

@test "missing cell marks the sub-project incomplete" {
    write_all_cells
    rm "${ARTIFACT_DIR}/status/fib-1"
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -eq 0 ]
    grep -F '| fib |' "${GITHUB_STEP_SUMMARY}" | grep -qF 'incomplete'
    grep -F '| fib |' "${GITHUB_STEP_SUMMARY}" | grep -qF '1/2'
    _row=$(grep -F '| perfect-numbers |' "${GITHUB_STEP_SUMMARY}")
    [[ "${_row}" != *incomplete* ]]
}

@test "red cell counts as reporting and is noted, contributing no numbers" {
    write_all_cells
    printf 'red: fib-1 — no work items\n' > "${ARTIFACT_DIR}/status/fib-1"
    rm "${ARTIFACT_DIR}/survivors/fib-1.txt"
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -eq 0 ]
    grep -F '| fib |' "${GITHUB_STEP_SUMMARY}" | grep -qF '2/2'
    grep -F '| fib |' "${GITHUB_STEP_SUMMARY}" | grep -qF '1 red'
    grep -qF '| fib | 2/2 | 10 | 3 | 1 | 3 | 1 red |' "${GITHUB_STEP_SUMMARY}"
}

@test "survivor files are concatenated sorted per sub-project" {
    write_all_cells
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -eq 0 ]
    [ "$(wc -l < "${OUT_DIR}/survivors/fib.txt")" -eq 5 ]
    [ "$(wc -l < "${OUT_DIR}/survivors/perfect-numbers.txt")" -eq 5 ]
    expected=$'fib.py:10 operator\nfib.py:10 operator\nfib.py:20 operator\nfib.py:20 operator\nfib.py:30 operator'
    [ "$(cat "${OUT_DIR}/survivors/fib.txt")" = "${expected}" ]
}

@test "sub-project with no survivor file gets no output file" {
    write_all_cells
    rm "${ARTIFACT_DIR}/survivors/perfect-numbers-0.txt" "${ARTIFACT_DIR}/survivors/perfect-numbers-1.txt"
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -eq 0 ]
    [ ! -e "${OUT_DIR}/survivors/perfect-numbers.txt" ]
    [ -e "${OUT_DIR}/survivors/fib.txt" ]
}

@test "newline separated expected units work" {
    write_all_cells
    export EXPECTED_STATUS_UNITS=$'fib-0\nfib-1\nperfect-numbers-0\nperfect-numbers-1'
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -eq 0 ]
    grep -qF '| fib | 2/2 | 22 | 5 | 1 | 5 |' "${GITHUB_STEP_SUMMARY}"
}

@test "missing required env -> non-zero with message" {
    write_all_cells
    for _v in ARTIFACT_DIR EXPECTED_STATUS_UNITS REPO RUN_URL REF EVENT OUT_DIR GITHUB_STEP_SUMMARY; do
        : > "${MOCK_CALLS_FILE}"
        run env -u "${_v}" bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
        [ "${status}" -ne 0 ]
        [[ "${output}" == *"${_v}"* ]]
        [ ! -s "${MOCK_CALLS_FILE}" ]
    done
}

@test "issue create failure -> non-zero" {
    write_all_cells
    export MOCK_GH_ISSUE_LIST=
    export MOCK_GH_EXIT_ISSUE_CREATE=1
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -ne 0 ]
}

@test "issue comment failure -> non-zero" {
    write_all_cells
    export MOCK_GH_ISSUE_LIST=17
    export MOCK_GH_EXIT_ISSUE_COMMENT=1
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -ne 0 ]
}

@test "label create failure is tolerated" {
    write_all_cells
    export MOCK_GH_ISSUE_LIST=
    export MOCK_GH_EXIT_LABEL_CREATE=1
    run bash "${REPO_ROOT}/scripts/mutation-survivor-report.sh" </dev/null
    [ "${status}" -eq 0 ]
    grep -q '^gh issue create' "${MOCK_CALLS_FILE}"
}
