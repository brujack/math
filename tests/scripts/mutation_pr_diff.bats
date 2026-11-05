#!/usr/bin/env bats

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    export HOME="${BATS_TEST_TMPDIR}"
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    SCRIPT="${REPO_ROOT}/scripts/mutation-pr-diff.sh"
    FIXTURE="${BATS_TEST_TMPDIR}/repo"
    OUT="${BATS_TEST_TMPDIR}/out.diff"

    mkdir -p "${FIXTURE}/a/a-rs/src" "${FIXTURE}/b/b-rs/src"
    printf '[package]\nname = "a"\n' >"${FIXTURE}/a/a-rs/Cargo.toml"
    printf '[package]\nname = "b"\n' >"${FIXTURE}/b/b-rs/Cargo.toml"
    printf 'pub fn f() -> u32 { 1 }\n' >"${FIXTURE}/a/a-rs/src/lib.rs"
    printf 'pub fn g() -> u32 { 1 }\n' >"${FIXTURE}/b/b-rs/src/lib.rs"
    _git init -q -b main
    _git add -A
    _git commit -q -m base
    _git checkout -q -b feature
}

_git() {
    git -C "${FIXTURE}" -c user.name=t -c user.email=t@t "$@"
}

_run_script() {
    cd "${FIXTURE}" || return 1
    run "${SCRIPT}" "$@"
}

@test "change in a-rs gives crate-relative +++ path" {
    printf 'pub fn f() -> u32 { 2 }\n' >"${FIXTURE}/a/a-rs/src/lib.rs"
    _git commit -q -am change
    _run_script main a/a-rs "${OUT}"
    [ "${status}" -eq 0 ]
    run grep -c '^+++ b/src/lib.rs$' "${OUT}"
    [ "${output}" = "1" ]
    run grep -c 'a/a-rs' "${OUT}"
    [ "${output}" = "0" ]
}

@test "trailing slash on crate dir is stripped" {
    printf 'pub fn f() -> u32 { 2 }\n' >"${FIXTURE}/a/a-rs/src/lib.rs"
    _git commit -q -am change
    _run_script main a/a-rs/ "${OUT}"
    [ "${status}" -eq 0 ]
    run grep -c '^+++ b/src/lib.rs$' "${OUT}"
    [ "${output}" = "1" ]
}

@test "only b-rs changed -> empty out-file for a-rs, exit 0" {
    printf 'pub fn g() -> u32 { 2 }\n' >"${FIXTURE}/b/b-rs/src/lib.rs"
    _git commit -q -am change
    _run_script main a/a-rs "${OUT}"
    [ "${status}" -eq 0 ]
    [ -f "${OUT}" ]
    [ ! -s "${OUT}" ]
}

@test "commit on base after the fork is absent (three-dot)" {
    printf 'pub fn f() -> u32 { 2 }\n' >"${FIXTURE}/a/a-rs/src/lib.rs"
    _git commit -q -am change
    _git checkout -q main
    printf 'pub fn f() -> u32 { 99 }\n' >"${FIXTURE}/a/a-rs/src/lib.rs"
    _git commit -q -am base-moves
    _git checkout -q feature
    _run_script main a/a-rs "${OUT}"
    [ "${status}" -eq 0 ]
    run grep -c '99' "${OUT}"
    [ "${output}" = "0" ]
    run grep -c '^+pub fn f() -> u32 { 2 }$' "${OUT}"
    [ "${output}" = "1" ]
}

@test "2 arguments exit 2 with usage" {
    _run_script main a/a-rs
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"Usage"* ]]
}

@test "4 arguments exit 2" {
    _run_script main a/a-rs "${OUT}" extra
    [ "${status}" -eq 2 ]
}

@test "dir without Cargo.toml exits 2" {
    mkdir -p "${FIXTURE}/c"
    _run_script main c "${OUT}"
    [ "${status}" -eq 2 ]
}

@test "unknown base ref exits 1" {
    _run_script no-such-ref a/a-rs "${OUT}"
    [ "${status}" -eq 1 ]
}

@test "user git config (color.ui=always, diff.noprefix) does not change the diff" {
    printf '[color]\n\tui = always\n[diff]\n\tnoprefix = true\n' >"${HOME}/.gitconfig"
    printf 'pub fn f() -> u32 { 2 }\n' >"${FIXTURE}/a/a-rs/src/lib.rs"
    _git commit -q -am change
    _run_script main a/a-rs "${OUT}"
    [ "${status}" -eq 0 ]
    run grep -c '^+++ b/src/lib.rs$' "${OUT}"
    [ "${output}" = "1" ]
    run grep -c $'\033' "${OUT}"
    [ "${output}" = "0" ]
}
