#!/usr/bin/env bats

# A bare `! grep -q ...` only fails a bats test while it is the last command in
# the body (shellcheck SC2314); anywhere else the negation is silently ignored
# and the assertion cannot fail. Every negative assertion in this file goes
# through here instead, which also names what it found on failure.
assert_no_match() {
    [[ -f "${MOCK_CALLS_FILE}" ]] || {
        printf 'calls file missing: %s\n' "${MOCK_CALLS_FILE}" >&2
        return 1
    }
    if grep -q "$1" "${MOCK_CALLS_FILE}" 2>/dev/null; then
        printf 'expected no match for %s, but calls were:\n%s\n' \
            "$1" "$(cat "${MOCK_CALLS_FILE}")" >&2
        return 1
    fi
}

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    SCRIPT="${REPO_ROOT}/scripts/sbom-sign.sh"
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/mock_calls"
    : > "${MOCK_CALLS_FILE}"

    BIN_DIR="${BATS_TEST_TMPDIR}/bin"
    mkdir -p "${BIN_DIR}"
    printf 'fake binary\n' > "${BIN_DIR}/mybin"
}

teardown() {
    rm -f "${MOCK_CALLS_FILE:-}"
}

@test "writes both sbom and bundle artifacts on success" {
    run "${SCRIPT}" "${BIN_DIR}" "mybin"
    [ "${status}" -eq 0 ]
    [ -f "${BIN_DIR}/mybin.sbom.spdx.json" ]
    [ -f "${BIN_DIR}/mybin.bundle" ]
    grep -q '^syft .* -o spdx-json .*--file ' "${MOCK_CALLS_FILE}"
    grep -q '^cosign sign-blob --yes ' "${MOCK_CALLS_FILE}"
}

@test "syft failure propagates and cosign is never invoked" {
    export MOCK_SYFT_EXIT=1
    run "${SCRIPT}" "${BIN_DIR}" "mybin"
    [ "${status}" -ne 0 ]
    assert_no_match "^cosign "
}

@test "cosign failure propagates" {
    export MOCK_COSIGN_EXIT=1
    run "${SCRIPT}" "${BIN_DIR}" "mybin"
    [ "${status}" -ne 0 ]
}

# The guard that rejects a content-free SBOM. Without cargo-auditable, real syft
# reports exactly 1 package (the binary itself) and the release would otherwise
# publish an SBOM grype can never find anything in -- the failure this pipeline
# exists to prevent. These drive the mock's package count to both sides of it.
@test "SBOM cataloguing only the binary fails, and cosign is never invoked" {
    MOCK_SYFT_PACKAGES=1 run "${SCRIPT}" "${BIN_DIR}" mybin
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"catalogues 1 package"* ]]
    [[ "${output}" == *"cargo auditable build"* ]]
    assert_no_match "^cosign "
}

@test "SBOM with no packages key fails rather than reading as zero" {
    MOCK_SYFT_PACKAGES=0 run "${SCRIPT}" "${BIN_DIR}" mybin
    [ "${status}" -ne 0 ]
    assert_no_match "^cosign "
}

# Wrong arity is a distinct failure from a missing binary -- both return 1, so
# these assert on the Usage message rather than bare non-zero. `Usage:` and
# `not a regular file` each appear in exactly one branch of sbom-sign.sh, so the
# assertions discriminate; if a future edit converges the wording, these go red.
@test "no arguments fails with usage, invoking neither tool" {
    run "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"Usage: sbom-sign.sh"* ]]
    [[ "${output}" != *"not a regular file"* ]]
    assert_no_match "^syft "
    assert_no_match "^cosign "
}

@test "one argument fails with usage, invoking neither tool" {
    run "${SCRIPT}" "${BIN_DIR}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"Usage: sbom-sign.sh"* ]]
    [[ "${output}" != *"not a regular file"* ]]
    assert_no_match "^syft "
    assert_no_match "^cosign "
}

@test "missing binary fails without invoking syft, naming the path" {
    run "${SCRIPT}" "${BIN_DIR}" "does-not-exist"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"${BIN_DIR}/does-not-exist"* ]]
    assert_no_match "^syft "
}
