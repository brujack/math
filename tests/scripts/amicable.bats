#!/usr/bin/env bats

setup() {
    load "../helpers/common.bash"
    PYTHON_CLI="${REPO_ROOT}/amicable/amicable.py"
    RUST_BIN="${REPO_ROOT}/amicable/amicable-rs/target/release/amicable"
}

# ── Python CLI ────────────────────────────────────────────────────────────────

@test "python: N=0 exits non-zero with message" {
    run python3 "${PYTHON_CLI}" 0
    [ "${status}" -ne 0 ]
    [[ "${output}" =~ "must be between" ]]
}

@test "python: N=8 exits non-zero (exceeds max)" {
    run python3 "${PYTHON_CLI}" 8
    [ "${status}" -ne 0 ]
}

@test "python: non-integer argument exits non-zero" {
    run python3 "${PYTHON_CLI}" abc
    [ "${status}" -ne 0 ]
}

@test "python: N=3 produces exactly one pair" {
    tmp=$(mktemp -d)
    run bash -c "cd '${tmp}' && python3 '${PYTHON_CLI}' 3"
    [ "${status}" -eq 0 ]
    [ "${output}" = "220 284" ]
    rm -rf "${tmp}"
}

# ── Rust CLI ──────────────────────────────────────────────────────────────────
# Rust tests require the release binary. Skip gracefully when not built
# (scripts.yml runs BATS without building Rust crates).

@test "rust: missing argument exits non-zero" {
    [[ -x "${RUST_BIN}" ]] || skip "Rust binary not built"
    run "${RUST_BIN}"
    [ "${status}" -ne 0 ]
}

@test "rust: N=0 exits non-zero" {
    [[ -x "${RUST_BIN}" ]] || skip "Rust binary not built"
    run "${RUST_BIN}" 0
    [ "${status}" -ne 0 ]
}

@test "rust: N=9 exits non-zero (exceeds max)" {
    [[ -x "${RUST_BIN}" ]] || skip "Rust binary not built"
    run "${RUST_BIN}" 9
    [ "${status}" -ne 0 ]
}

@test "rust: non-integer argument exits non-zero" {
    [[ -x "${RUST_BIN}" ]] || skip "Rust binary not built"
    run "${RUST_BIN}" abc
    [ "${status}" -ne 0 ]
}

@test "rust: N=3 produces exactly one pair" {
    [[ -x "${RUST_BIN}" ]] || skip "Rust binary not built"
    tmp=$(mktemp -d)
    run bash -c "cd '${tmp}' && '${RUST_BIN}' 3"
    [ "${status}" -eq 0 ]
    [ "${output}" = "220 284" ]
    rm -rf "${tmp}"
}
