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

@test "marker + status with one red file -> verdicts-present, names the crate" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == *"pi-rs"* ]]
}

@test "marker + status with two red files -> both crate names appear" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"
    printf 'red: e-rs - exit code 3\n' > "${ARTIFACT_DIR}/status/e-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == *"pi-rs"* ]]
    [[ "${body}" == *"e-rs"* ]]
}

@test "marker + status with no red line -> none flagged message" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'green: pi-rs - ok\n' > "${ARTIFACT_DIR}/status/pi-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == *"- (none flagged; see run log)"* ]]
}

@test "marker + mutants.out, no status -> loop-began-no-verdict" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/pi-rs/mutants.out"

    result="$(attribute)"
    [ "${result}" = "loop-began-no-verdict" ]
}

@test "marker only -> died-before-loop" {
    mkdir -p "${ARTIFACT_DIR}/marker"

    result="$(attribute)"
    [ "${result}" = "died-before-loop" ]
}

@test "download failure, empty artifact dir -> no-attestation" {
    mkdir -p "${ARTIFACT_DIR}"
    export DL_OUTCOME="failure"

    result="$(attribute)"
    [ "${result}" = "no-attestation" ]
}

@test "download success, populated artifact but no marker -> no-attestation (same token as failed download)" {
    mkdir -p "${ARTIFACT_DIR}/status" "${ARTIFACT_DIR}/pi-rs/mutants.out"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"
    export DL_OUTCOME="success"

    result="$(attribute)"
    [ "${result}" = "no-attestation" ]
}
