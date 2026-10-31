#!/usr/bin/env bats

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export MOCK_CARGO_LOG="${BATS_TEST_TMPDIR}/cargo.log"
    export CARGO_DENY_CRATES="${BATS_TEST_TMPDIR}/crates.txt"
    unset MOCK_CARGO_FAIL
}

# Writes N fixture manifest paths (c1/c1-rs/Cargo.toml ...) to the crate list.
make_crates() {
    local n="$1" i
    : > "${CARGO_DENY_CRATES}"
    for ((i = 1; i <= n; i++)); do
        printf "c%d/c%d-rs/Cargo.toml\n" "${i}" "${i}" >> "${CARGO_DENY_CRATES}"
    done
}

@test "11 crates all pass → exit 0, 11 invocations with --config before check" {
    make_crates 11
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 0 ]
    [ "$(wc -l < "${MOCK_CARGO_LOG}")" -eq 11 ]
    while IFS= read -r line; do
        [[ "${line}" == *"--config "*" check" ]]
        prefix="${line%% check}"
        [[ "${prefix}" == *"--config"* ]]
        [[ "${prefix}" == *"--manifest-path"* ]]
    done < "${MOCK_CARGO_LOG}"
}

@test "--manifest-path is the absolute path of each crate manifest" {
    make_crates 11
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 0 ]
    local i
    for ((i = 1; i <= 11; i++)); do
        [ "$(command grep -cF -- "--manifest-path ${REPO_ROOT}/c${i}/c${i}-rs/Cargo.toml " "${MOCK_CARGO_LOG}")" -eq 1 ]
    done
}

@test "--config precedes check on every invocation" {
    make_crates 11
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 0 ]
    [ "$(wc -l < "${MOCK_CARGO_LOG}")" -eq 11 ]
    while IFS= read -r line; do
        before_check="${line%% check*}"
        [[ "${before_check}" == "deny --locked --config ${REPO_ROOT}/deny.toml --manifest-path "* ]]
    done < "${MOCK_CARGO_LOG}"
}

@test "one failing crate → exit 1, all 11 still invoked, failed crate named" {
    make_crates 11
    export MOCK_CARGO_FAIL="c3-rs"
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 1 ]
    [ "$(wc -l < "${MOCK_CARGO_LOG}")" -eq 11 ]
    [[ "$output" == *"c3/c3-rs"* ]]
    [[ "$output" == *"1 of 11 crates failed"* ]]
}

@test "empty crate list → exit 1, expected 11 crates, found 0" {
    make_crates 0
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"expected 11 crates, found 0"* ]]
    [ ! -e "${MOCK_CARGO_LOG}" ]
}

@test "10 crates → exit 1, found 10, cargo never invoked" {
    make_crates 10
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"expected 11 crates, found 10"* ]]
    [ ! -e "${MOCK_CARGO_LOG}" ]
}

@test "12 crates → exit 1, found 12" {
    make_crates 12
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"expected 11 crates, found 12"* ]]
}

@test "--locked precedes check on every invocation" {
    make_crates 11
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 0 ]
    [ "$(wc -l < "${MOCK_CARGO_LOG}")" -eq 11 ]
    while IFS= read -r line; do
        prefix="${line%% check*}"
        [[ "${prefix}" == *"--locked"* ]]
    done < "${MOCK_CARGO_LOG}"
}
