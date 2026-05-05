#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/mock_calls"
}

teardown() {
    rm -f "${MOCK_CALLS_FILE:-}"
}

_write_fake_cargo() {
    local body="$1"
    local path="${BATS_TEST_TMPDIR}/fake-cargo"
    printf '#!/usr/bin/env bash\n%s\n' "${body}" > "${path}"
    chmod +x "${path}"
    printf '%s' "${path}"
}

@test "sets repo-local CARGO_HOME when CARGO_HOME is unset" {
    local fake_cargo
    fake_cargo="$(_write_fake_cargo 'printf "%s\n" "${CARGO_HOME}"')"
    run env -u CARGO_HOME \
        RUST_CHECK_CARGO_BIN="${fake_cargo}" \
        bash "${REPO_ROOT}/scripts/rust-check.sh" lint
    [ "$status" -eq 0 ]
    [[ "$output" == *"${REPO_ROOT}/.cache/cargo-home"* ]]
}

@test "passes --offline flag when RUST_CHECK_OFFLINE=1" {
    local fake_cargo
    fake_cargo="$(_write_fake_cargo 'printf "%s\n" "$@"')"
    run env RUST_CHECK_CARGO_BIN="${fake_cargo}" \
        RUST_CHECK_OFFLINE=1 \
        bash "${REPO_ROOT}/scripts/rust-check.sh" test
    [ "$status" -eq 0 ]
    [[ "$output" == *"--offline"* ]]
}

@test "propagates fmt failure even when clippy succeeds" {
    local fake_cargo
    fake_cargo="$(_write_fake_cargo 'if [ "$1" = "fmt" ]; then exit 1; fi; exit 0')"
    run env RUST_CHECK_CARGO_BIN="${fake_cargo}" \
        bash "${REPO_ROOT}/scripts/rust-check.sh" lint
    [ "$status" -ne 0 ]
}

@test "classifies environment failures in stderr" {
    local fake_cargo stderr_file rc
    fake_cargo="$(_write_fake_cargo 'printf "Operation not permitted\n"; exit 101')"
    stderr_file="${BATS_TEST_TMPDIR}/stderr.txt"
    rc=0
    RUST_CHECK_CARGO_BIN="${fake_cargo}" \
        bash "${REPO_ROOT}/scripts/rust-check.sh" lint \
        2>"${stderr_file}" || rc=$?
    [ "${rc}" -eq 101 ]
    grep -q "Environment/setup failure" "${stderr_file}"
}
