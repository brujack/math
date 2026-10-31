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

_run_in_fixture() {
    cd "${FIXTURE}" || return 1
    run "${SCRIPT}" "$@"
}

_expected_output() {
    printf 'enabled=true\nprefix=gmp-mpfr-sys-%s-Linux-ubuntu26-\nkey=gmp-mpfr-sys-%s-Linux-ubuntu26-2026-W44' "$1" "$1"
}

@test "two lockfiles -> three exact lines, versions sorted, unrelated package absent" {
    _run_in_fixture
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

@test "no lockfile names gmp-mpfr-sys, --strict -> exit 1 naming the cause" {
    printf '[[package]]\nname = "other"\nversion = "1.0.0"\n' >"${FIXTURE}/a/a-rs/Cargo.lock"
    printf '[[package]]\nname = "other"\nversion = "1.0.0"\n' >"${FIXTURE}/b/b-rs/Cargo.lock"
    _run_in_fixture --strict
    [ "${status}" -eq 1 ]
    [[ "${output}" == "gmp-cache-key: "*"gmp-mpfr-sys"* ]]
}

@test "no lockfile names gmp-mpfr-sys, lenient -> exit 0, enabled=false on stdout" {
    printf '[[package]]\nname = "other"\nversion = "1.0.0"\n' >"${FIXTURE}/a/a-rs/Cargo.lock"
    printf '[[package]]\nname = "other"\nversion = "1.0.0"\n' >"${FIXTURE}/b/b-rs/Cargo.lock"
    cd "${FIXTURE}"
    run --separate-stderr "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [ "${output}" = "enabled=false" ]
    [[ "${stderr}" == "::warning::gmp-cache-key: "*"gmp-mpfr-sys"* ]]
}

@test "empty RUNNER_OS, --strict -> exit 1 naming RUNNER_OS" {
    export RUNNER_OS=""
    _run_in_fixture --strict
    [ "${status}" -eq 1 ]
    [[ "${output}" == "gmp-cache-key: "*"RUNNER_OS"* ]]
}

@test "empty RUNNER_OS, lenient -> exit 0, enabled=false" {
    export RUNNER_OS=""
    cd "${FIXTURE}"
    run --separate-stderr "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [ "${output}" = "enabled=false" ]
    [[ "${stderr}" == *"RUNNER_OS"* ]]
}

@test "empty ImageOS, --strict -> exit 1 naming ImageOS" {
    export ImageOS=""
    _run_in_fixture --strict
    [ "${status}" -eq 1 ]
    [[ "${output}" == "gmp-cache-key: "*"ImageOS"* ]]
}

@test "empty ImageOS, lenient -> exit 0, enabled=false" {
    export ImageOS=""
    cd "${FIXTURE}"
    run --separate-stderr "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [ "${output}" = "enabled=false" ]
    [[ "${stderr}" == *"ImageOS"* ]]
}

@test "unknown argument -> exit 2 with usage" {
    _run_in_fixture --bogus
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"usage"* ]]
}

@test "extra argument after --strict -> exit 2" {
    _run_in_fixture --strict extra
    [ "${status}" -eq 2 ]
}

@test "real repo: key line carries the lockfile version, OS, image and ISO week" {
    cd "${REPO_ROOT}"
    unset GMP_CACHE_WEEK
    run "${SCRIPT}" --strict
    [ "${status}" -eq 0 ]
    [[ "${output}" =~ (^|$'\n')enabled=true($|$'\n') ]]
    [[ "${output}" =~ (^|$'\n')key=gmp-mpfr-sys-1\.7\.[0-9]+.*-Linux-ubuntu26-[0-9]{4}-W[0-9]{2}($|$'\n') ]]
}
