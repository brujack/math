#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    source "${REPO_ROOT}/scripts/mutation-notify.sh"
    export UNIT_NOUN="crate"
    export RUN_URL="https://github.com/brujack/math/actions/runs/123"
    export ARTIFACT_DIR="${BATS_TEST_TMPDIR}/artifact"
    export REPO="example-org/fixture-repo-do-not-use"
    export ISSUE_TITLE="mutation-testing: monthly run failed"
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/calls"
}

# Every body-asserting case below checks the full contract, not just a
# substring: the body must start with "Cause: <token>" and end with
# "Run: ${RUN_URL}" -- both are stated twice in the plan as the stable
# surface tests pin, and neither was asserted before this fix round.

@test "marker + status with one red file -> verdicts-present, names the crate" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"- pi-rs"* ]]
}

@test "marker + status with two red files -> both crate names appear" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"
    printf 'red: e-rs - exit code 3\n' > "${ARTIFACT_DIR}/status/e-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"- pi-rs"* ]]
    [[ "${body}" == *"- e-rs"* ]]
}

@test "marker + status with no red line -> none flagged message" {
    # The fixture must contain the substring "red" NOT at the start of the
    # line, so a mutant that drops the ^ anchor from grep -l '^red' is
    # distinguishable: anchored, this file never matches; unanchored, it
    # would.
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'green: pi-rs - 0 red mutants\n' > "${ARTIFACT_DIR}/status/pi-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"- (none flagged; see run log)"* ]]
}

@test "verdicts-present with a mixed red and green status directory lists only the red crate" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"
    printf 'green: e-rs - ok\n' > "${ARTIFACT_DIR}/status/e-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == *"- pi-rs"* ]]
    [[ "${body}" != *"e-rs"* ]]
}

@test "verdicts-present survives a status filename containing a space" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: twin primes-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/twin primes-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == *"- twin primes-rs"* ]]
}

@test "marker + mutants.out, no status -> loop-began-no-verdict" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/pi-rs/mutants.out"

    result="$(attribute)"
    [ "${result}" = "loop-began-no-verdict" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"loop began and no verdict was written"* ]]
}

@test "marker only -> died-before-loop" {
    mkdir -p "${ARTIFACT_DIR}/marker"

    result="$(attribute)"
    [ "${result}" = "died-before-loop" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"failed before the loop"* ]]
}

@test "download failure, empty artifact dir -> no-attestation" {
    mkdir -p "${ARTIFACT_DIR}"
    export DL_OUTCOME="failure"

    result="$(attribute)"
    [ "${result}" = "no-attestation" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"own reporting never ran"* ]]
}

@test "download success, populated artifact but no marker -> no-attestation (same token as failed download)" {
    mkdir -p "${ARTIFACT_DIR}/status" "${ARTIFACT_DIR}/pi-rs/mutants.out"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"
    export DL_OUTCOME="success"

    result="$(attribute)"
    [ "${result}" = "no-attestation" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"own reporting never ran"* ]]
}

@test "marker + status + mutants.out together -> verdicts-present (status takes precedence)" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status" "${ARTIFACT_DIR}/pi-rs/mutants.out"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]
}

@test "marker + empty status directory, no mutants.out -> falls through to died-before-loop" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"

    result="$(attribute)"
    [ "${result}" = "died-before-loop" ]
}

@test "attribute fails visibly when ARTIFACT_DIR is unset" {
    unset ARTIFACT_DIR
    run attribute
    [ "${status}" -ne 0 ]
}

@test "build_body reports an unknown token rather than silently producing nothing" {
    body="$(build_body "some-bogus-token")"
    [[ "${body}" == "Cause: some-bogus-token"$'\n'* ]]
    [[ "${body}" == *"Unknown cause token: some-bogus-token"* ]]
}

@test "RESULT=success with an open issue comments then closes it, every call carrying --repo" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST="98"

    run main
    [ "${status}" -eq 0 ]

    local _comment_line _close_line
    _comment_line=$(grep -n "gh issue comment 98 --repo" "${MOCK_CALLS_FILE}" | cut -d: -f1)
    _close_line=$(grep -n "gh issue close 98 --repo" "${MOCK_CALLS_FILE}" | cut -d: -f1)
    [ -n "${_comment_line}" ]
    [ -n "${_close_line}" ]
    [ "${_comment_line}" -lt "${_close_line}" ]

    local _total _with_repo
    _total=$(grep -c . "${MOCK_CALLS_FILE}")
    _with_repo=$(grep -c -- "--repo" "${MOCK_CALLS_FILE}")
    [ "${_total}" -gt 0 ]
    [ "${_total}" -eq "${_with_repo}" ]

    # NOT asserting that closing is correct behaviour: math#100 is open and
    # describes exactly this path as a defect -- a single-crate green run
    # closed the full-sweep issue #98 while pi-rs and e-rs were still red,
    # which the 2026-09-01 cron confirms is still true. This case pins
    # --repo scoping and the absence of a second issue only; asserting the
    # close itself as correct would make #100 harder to fix, since a
    # passing test reads as intent.
}

@test "RESULT=success with no open issue exits 0 and writes nothing to the tracker" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST=""

    run main
    [ "${status}" -eq 0 ]

    run ! grep -q "gh issue comment" "${MOCK_CALLS_FILE}"
    run ! grep -q "gh issue close" "${MOCK_CALLS_FILE}"
    run ! grep -q "gh issue create" "${MOCK_CALLS_FILE}"
}

@test "RESULT=failure with an open issue comments only, never files a second issue" {
    export RESULT="failure"
    export MOCK_GH_ISSUE_LIST="98"
    mkdir -p "${ARTIFACT_DIR}/marker"

    run main
    [ "${status}" -eq 0 ]

    grep -q "gh issue comment 98 --repo" "${MOCK_CALLS_FILE}"
    run ! grep -q "gh issue create" "${MOCK_CALLS_FILE}"
}

@test "RESULT=failure with no open issue creates one carrying the attributed cause" {
    export RESULT="failure"
    export MOCK_GH_ISSUE_LIST=""
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"

    run main
    [ "${status}" -eq 0 ]

    grep -q "gh issue create --repo" "${MOCK_CALLS_FILE}"
    grep -q "Cause: verdicts-present" "${MOCK_CALLS_FILE}"
}

@test "RESULT=cancelled files an issue -- pinned, though never observed in this repo" {
    # cancelled has never occurred here: all four measured failures carry a
    # job conclusion of "failure", and "cancelled" is attested only at the
    # step level. This pins current behaviour (anything other than
    # RESULT=success takes the file/comment path) without claiming the shape
    # has ever actually been observed.
    export RESULT="cancelled"
    export MOCK_GH_ISSUE_LIST=""
    mkdir -p "${ARTIFACT_DIR}/marker"

    run main
    [ "${status}" -eq 0 ]

    grep -q "gh issue create --repo" "${MOCK_CALLS_FILE}"
}

@test "main fails visibly when REPO is unset" {
    unset REPO
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST=""

    run main
    [ "${status}" -ne 0 ]
}

@test "direct execution (not sourced) exits 0 on a green run with no open issue" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST=""

    run bash "${REPO_ROOT}/scripts/mutation-notify.sh"
    [ "${status}" -eq 0 ]
}
