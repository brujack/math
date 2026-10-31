#!/usr/bin/env bats
# Offline controls for deny.toml: a GPL and an LGPL crate must be rejected, an
# MIT crate accepted. Fixtures are copied first because cargo-deny writes a
# Cargo.lock beside the manifest.

load '../helpers/common'

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    if ! command -v cargo-deny >/dev/null 2>&1; then
        if [[ -n "${CI:-}" ]]; then
            printf '%s\n' "cargo-deny is not installed but CI is set" >&2
            return 1
        fi
        skip "cargo-deny not installed (install it with cargo install cargo-deny --locked)"
    fi
}

run_deny_on_fixture() {
    local name="$1"
    cp -R "${REPO_ROOT}/tests/fixtures/cargo-deny/${name}" "${BATS_TEST_TMPDIR}/${name}"
    run cargo deny --config "${REPO_ROOT}/deny.toml" \
        --manifest-path "${BATS_TEST_TMPDIR}/${name}/Cargo.toml" check licenses
}

@test "gpl fixture is rejected by the licence policy" {
    run_deny_on_fixture gpl
    [ "$status" -eq 4 ]
    [[ "$output" == *"error[rejected]"* ]]
}

@test "lgpl fixture is rejected without a crate exception" {
    run_deny_on_fixture lgpl
    [ "$status" -eq 4 ]
    [[ "$output" == *"error[rejected]"* ]]
}

@test "mit fixture is accepted" {
    run_deny_on_fixture mit
    [ "$status" -eq 0 ]
}

@test "rug fixture is accepted only through its crate exception" {
    run_deny_on_fixture rug
    [ "$status" -eq 0 ]
}

# Copies the stale-lock fixture and activates its lockfile (shipped as
# Cargo.lock.stale so the repo never holds a Cargo.lock under the fixtures).
prepare_stale_lock() {
    cp -R "${REPO_ROOT}/tests/fixtures/cargo-deny/stale-lock" "${BATS_TEST_TMPDIR}/stale-lock"
    mv "${BATS_TEST_TMPDIR}/stale-lock/app/Cargo.lock.stale" "${BATS_TEST_TMPDIR}/stale-lock/app/Cargo.lock"
}

@test "stale lock is rejected under --locked" {
    prepare_stale_lock
    run env CARGO_NET_OFFLINE=true CARGO_HOME="${BATS_TEST_TMPDIR}/cargo-home" \
        cargo deny --locked --config "${REPO_ROOT}/deny.toml" \
        --manifest-path "${BATS_TEST_TMPDIR}/stale-lock/app/Cargo.toml" check licenses
    [ "$status" -ne 0 ]
    [[ "$output" == *"cannot update the lock file"* ]]
}

@test "stale lock passes without --locked and is rewritten" {
    prepare_stale_lock
    run env CARGO_NET_OFFLINE=true CARGO_HOME="${BATS_TEST_TMPDIR}/cargo-home" \
        cargo deny --config "${REPO_ROOT}/deny.toml" \
        --manifest-path "${BATS_TEST_TMPDIR}/stale-lock/app/Cargo.toml" check licenses
    [ "$status" -eq 0 ]
    command grep -q deny-fixture-stale-dep "${BATS_TEST_TMPDIR}/stale-lock/app/Cargo.lock"
}

@test "no Cargo.lock is left under the fixtures" {
    run find "${REPO_ROOT}/tests/fixtures/cargo-deny" -name Cargo.lock
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}
