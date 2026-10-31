#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    SCRIPT="${REPO_ROOT}/scripts/gmp-cache-key.sh"
    FIXTURE="${BATS_TEST_TMPDIR}/fixture"
    mkdir -p "${FIXTURE}"
    git -C "${FIXTURE}" init -q
    _write_lock a 1.7.1
    _write_lock b 1.7.0
    git -C "${FIXTURE}" add a/a-rs/Cargo.lock b/b-rs/Cargo.lock
    export RUNNER_OS=Linux ImageOS=ubuntu26 GMP_CACHE_WEEK=2026-W44
}

# _write_lock <crate> <gmp-mpfr-sys version>; an unrelated package follows it
_write_lock() {
    mkdir -p "${FIXTURE}/$1/$1-rs"
    printf '%s\n' \
        '[[package]]' \
        'name = "gmp-mpfr-sys"' \
        "version = \"$2\"" \
        '' \
        '[[package]]' \
        'name = "unrelated"' \
        'version = "9.9.9"' >"${FIXTURE}/$1/$1-rs/Cargo.lock"
}

# _write_lockless <crate>: a tracked-style lockfile with no gmp-mpfr-sys
_write_lockless() {
    printf '[[package]]\nname = "other"\nversion = "1.0.0"\n' >"${FIXTURE}/$1/$1-rs/Cargo.lock"
}

_run_in_fixture() {
    cd "${FIXTURE}" || return 1
    run --separate-stderr "${SCRIPT}" "$@"
}

_expected_output() {
    printf 'enabled=true\nprefix=gmp-mpfr-sys-%s-Linux-ubuntu26-\nkey=gmp-mpfr-sys-%s-Linux-ubuntu26-2026-W44' "$1" "$1"
}

# _assert_fails_closed <cause>: the current fixture must fail under --strict
# (exit 1, empty stdout, exact stderr) and degrade without it (exit 0,
# stdout exactly enabled=false, exact warning).
_assert_fails_closed() {
    local cause="$1"
    _run_in_fixture --strict
    [ "${status}" -eq 1 ]
    [ -z "${output}" ]
    [ "${stderr}" = "gmp-cache-key: ${cause}" ]
    _run_in_fixture
    [ "${status}" -eq 0 ]
    [ "${output}" = "enabled=false" ]
    [ "${stderr}" = "::warning::gmp-cache-key: ${cause}" ]
}

@test "two lockfiles -> three exact lines, versions sorted, unrelated package absent" {
    _run_in_fixture
    [ "${status}" -eq 0 ]
    [ "${output}" = "$(_expected_output 1.7.0_1.7.1)" ]
    [ -z "${stderr}" ]
}

@test "--strict with good input prints the same three lines" {
    _run_in_fixture --strict
    [ "${status}" -eq 0 ]
    [ "${output}" = "$(_expected_output 1.7.0_1.7.1)" ]
}

@test "a third lockfile repeating 1.7.1 collapses to the same output" {
    _write_lock c 1.7.1
    git -C "${FIXTURE}" add c/c-rs/Cargo.lock
    _run_in_fixture
    [ "${status}" -eq 0 ]
    [ "${output}" = "$(_expected_output 1.7.0_1.7.1)" ]
}

@test "an untracked lockfile naming 1.9.9 is ignored" {
    _write_lock d 1.9.9
    _run_in_fixture
    [ "${status}" -eq 0 ]
    [ "${output}" = "$(_expected_output 1.7.0_1.7.1)" ]
}

@test "versions sort numerically: 1.7.9 before 1.7.10" {
    _write_lock a 1.7.10
    _write_lock b 1.7.9
    _run_in_fixture
    [ "${status}" -eq 0 ]
    [ "${output}" = "$(_expected_output 1.7.9_1.7.10)" ]
}

@test "a package named gmp-mpfr-sys-foo is not read as gmp-mpfr-sys" {
    printf '%s\n' \
        '[[package]]' \
        'name = "gmp-mpfr-sys-foo"' \
        'version = "2.0.0"' \
        '' \
        '[[package]]' \
        'name = "gmp-mpfr-sys"' \
        'version = "1.7.1"' >"${FIXTURE}/a/a-rs/Cargo.lock"
    _run_in_fixture
    [ "${status}" -eq 0 ]
    [ "${output}" = "$(_expected_output 1.7.0_1.7.1)" ]
}

@test "a CRLF lockfile is parsed" {
    printf '[[package]]\r\nname = "gmp-mpfr-sys"\r\nversion = "1.7.1"\r\n' >"${FIXTURE}/a/a-rs/Cargo.lock"
    _run_in_fixture
    [ "${status}" -eq 0 ]
    [ "${output}" = "$(_expected_output 1.7.0_1.7.1)" ]
}

@test "no lockfile names gmp-mpfr-sys -> fails closed" {
    _write_lockless a
    _write_lockless b
    _assert_fails_closed "no tracked Cargo.lock names gmp-mpfr-sys"
}

@test "a tracked lockfile missing from disk -> fails closed naming it" {
    rm "${FIXTURE}/a/a-rs/Cargo.lock"
    _assert_fails_closed "cannot read tracked lockfile a/a-rs/Cargo.lock"
}

@test "empty RUNNER_OS -> fails closed" {
    export RUNNER_OS=""
    _assert_fails_closed "RUNNER_OS is empty"
}

@test "empty ImageOS -> fails closed" {
    export ImageOS=""
    _assert_fails_closed "ImageOS is empty"
}

@test "run outside a git repository -> fails closed" {
    mkdir -p "${BATS_TEST_TMPDIR}/norepo"
    export GIT_CEILING_DIRECTORIES="${BATS_TEST_TMPDIR}"
    cd "${BATS_TEST_TMPDIR}/norepo"
    run --separate-stderr "${SCRIPT}" --strict
    [ "${status}" -eq 1 ]
    [ -z "${output}" ]
    [ "${stderr}" = "gmp-cache-key: not inside a git repository" ]
    run --separate-stderr "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [ "${output}" = "enabled=false" ]
    [ "${stderr}" = "::warning::gmp-cache-key: not inside a git repository" ]
}

@test "unknown argument -> exit 2 with exact usage" {
    _run_in_fixture --bogus
    [ "${status}" -eq 2 ]
    [ -z "${output}" ]
    [ "${stderr}" = "usage: gmp-cache-key.sh [--strict]" ]
}

@test "extra argument after --strict -> exit 2 with exact usage" {
    _run_in_fixture --strict extra
    [ "${status}" -eq 2 ]
    [ -z "${output}" ]
    [ "${stderr}" = "usage: gmp-cache-key.sh [--strict]" ]
}

@test "real repo: key line carries the lockfile version, OS, image and ISO week" {
    cd "${REPO_ROOT}"
    unset GMP_CACHE_WEEK
    run "${SCRIPT}" --strict
    [ "${status}" -eq 0 ]
    [[ "${output}" =~ (^|$'\n')enabled=true($|$'\n') ]]
    [[ "${output}" =~ (^|$'\n')key=gmp-mpfr-sys-[0-9]+\.[0-9]+\.[0-9]+.*-Linux-ubuntu26-[0-9]{4}-W[0-9]{2}($|$'\n') ]]
}
