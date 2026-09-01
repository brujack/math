#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    source "${REPO_ROOT}/scripts/mutation-notify.sh"
    export UNIT_NOUN="crate"
    export RUN_URL="https://github.com/brujack/math/actions/runs/123"
    export ARTIFACT_DIR="${BATS_TEST_TMPDIR}/artifact"
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
