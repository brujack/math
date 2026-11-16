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

@test "12 crates all pass → exit 0, 12 invocations with --config before check" {
    make_crates 12
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 0 ]
    [ "$(wc -l < "${MOCK_CARGO_LOG}")" -eq 12 ]
    while IFS= read -r line; do
        [[ "${line}" == *"--config "*" check" ]]
        prefix="${line%% check}"
        [[ "${prefix}" == *"--config"* ]]
        [[ "${prefix}" == *"--manifest-path"* ]]
    done < "${MOCK_CARGO_LOG}"
}

@test "--manifest-path is the absolute path of each crate manifest" {
    make_crates 12
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 0 ]
    local i
    for ((i = 1; i <= 12; i++)); do
        [ "$(command grep -cF -- "--manifest-path ${REPO_ROOT}/c${i}/c${i}-rs/Cargo.toml " "${MOCK_CARGO_LOG}")" -eq 1 ]
    done
}

@test "--config precedes check on every invocation" {
    make_crates 12
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 0 ]
    [ "$(wc -l < "${MOCK_CARGO_LOG}")" -eq 12 ]
    while IFS= read -r line; do
        before_check="${line%% check*}"
        [[ "${before_check}" == "deny --locked --config ${REPO_ROOT}/deny.toml --manifest-path "* ]]
    done < "${MOCK_CARGO_LOG}"
}

@test "one failing crate → exit 1, all 12 still invoked, failed crate named" {
    make_crates 12
    export MOCK_CARGO_FAIL="c3-rs"
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 1 ]
    [ "$(wc -l < "${MOCK_CARGO_LOG}")" -eq 12 ]
    [[ "$output" == *"c3/c3-rs"* ]]
    [[ "$output" == *"1 of 12 crates failed"* ]]
}

@test "empty crate list → exit 1, expected 12 crates, found 0" {
    make_crates 0
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"expected 12 crates, found 0"* ]]
    [ ! -e "${MOCK_CARGO_LOG}" ]
}

@test "11 crates → exit 1, found 11, cargo never invoked" {
    make_crates 11
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"expected 12 crates, found 11"* ]]
    [ ! -e "${MOCK_CARGO_LOG}" ]
}

@test "13 crates → exit 1, found 13" {
    make_crates 13
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"expected 12 crates, found 13"* ]]
}

@test "--locked precedes check on every invocation" {
    make_crates 12
    run "${REPO_ROOT}/scripts/cargo-deny-all.sh"
    [ "$status" -eq 0 ]
    [ "$(wc -l < "${MOCK_CARGO_LOG}")" -eq 12 ]
    while IFS= read -r line; do
        prefix="${line%% check*}"
        [[ "${prefix}" == *"--locked"* ]]
    done < "${MOCK_CARGO_LOG}"
}

@test "EXPECTED_CRATES equals the number of tracked crate manifests" {
    # The other tests feed a mocked crate list, so only this one ties the
    # constant to the repository: descartes-rs (crate 12) shipped with it at 11.
    # load_mocks put tests/mocks first on PATH, and its git answers ls-files
    # with nothing; drop it so the real git counts the real manifests.
    clean_path="$(printf '%s' "${PATH}" | tr ':' '\n' | command grep -v '/tests/mocks' | paste -sd: -)"
    want="$(PATH="${clean_path}" command git -C "${REPO_ROOT}" ls-files '*/*-rs/Cargo.toml' | wc -l)"
    [ "${want}" -gt 0 ]
    got="$(command grep -oE '^readonly EXPECTED_CRATES=[0-9]+' "${REPO_ROOT}/scripts/cargo-deny-all.sh" | cut -d= -f2)"
    [ -n "${got}" ]
    [ "${got}" -eq "${want}" ]
}
