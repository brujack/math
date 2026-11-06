#!/usr/bin/env bats
# The real mutation-pr-diff.sh and mutation-classify.sh run here; only `make` is stubbed.

bats_require_minimum_version 1.5.0

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    export HOME="${BATS_TEST_TMPDIR}"
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    SCRIPT="${REPO_ROOT}/scripts/mutation-pr-run.sh"
    FIXTURE="${BATS_TEST_TMPDIR}/repo"
    STUBS="${BATS_TEST_TMPDIR}/stubs"
    export STUB_CFG="${BATS_TEST_TMPDIR}/cfg"
    export STUB_LOG="${BATS_TEST_TMPDIR}/make.log"

    mkdir -p "${FIXTURE}/a/a-rs/src" "${FIXTURE}/b/b-rs/src" "${STUBS}" "${STUB_CFG}"
    printf '[package]\nname = "a"\n' >"${FIXTURE}/a/a-rs/Cargo.toml"
    printf '[package]\nname = "b"\n' >"${FIXTURE}/b/b-rs/Cargo.toml"
    printf 'pub fn f() -> u32 { 1 }\n' >"${FIXTURE}/a/a-rs/src/lib.rs"
    printf 'pub fn g() -> u32 { 1 }\n' >"${FIXTURE}/b/b-rs/src/lib.rs"
    _git init -q -b main
    _git add -A
    _git commit -q -m base
    _git checkout -q -b feature
    : >"${STUB_LOG}"
    _write_stub_make
}

_git() {
    git -C "${FIXTURE}" -c user.name=t -c user.email=t@t "$@"
}

# Stub make: logs -C dir, DIFF path and the diff's +++ line, then writes the
# mutants.out files named by the per-crate config (cfg/<dir with / as _>).
# A config line `exit=N` writes exit-code; `outcomes=JSON` writes outcomes.json.
_write_stub_make() {
    cat >"${STUBS}/make" <<'STUB'
#!/usr/bin/env bash
dir=""
diff=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -C) dir="$2"; shift 2 ;;
        DIFF=*) diff="${1#DIFF=}"; shift ;;
        *) shift ;;
    esac
done
plus=$(grep -m1 '^+++ ' "${diff}")
printf 'make -C %s DIFF=%s PLUS=%s\n' "${dir}" "${diff}" "${plus}" >>"${STUB_LOG}"
cfg="${STUB_CFG}/${dir//\//_}"
mkdir -p "${dir}/mutants.out"
status=0
[[ -f "${cfg}" ]] || exit 0
while IFS= read -r line; do
    case "${line}" in
        exit=*) printf '%s\n' "${line#exit=}" >"${dir}/mutants.out/exit-code" ;;
        outcomes=*) printf '%s\n' "${line#outcomes=}" >"${dir}/mutants.out/outcomes.json" ;;
        status=*) status="${line#status=}" ;;
    esac
done <"${cfg}"
exit "${status}"
STUB
    chmod +x "${STUBS}/make"
}

# _cfg <dir> <exit-or-empty> <outcomes-json>
_cfg() {
    local file="${STUB_CFG}/${1//\//_}"
    : >"${file}"
    [[ -n "$2" ]] && printf 'exit=%s\n' "$2" >>"${file}"
    [[ -n "$3" ]] && printf 'outcomes=%s\n' "$3" >>"${file}"
    return 0
}

_change() {
    printf 'pub fn f() -> u32 { 2 }\n' >"${FIXTURE}/$1/src/lib.rs"
}

_commit() {
    _git commit -q -am change
}

_run_script() {
    cd "${FIXTURE}" || return 1
    PATH="${STUBS}:${PATH}" run "${SCRIPT}" "$@"
}

_run_script_sep() {
    cd "${FIXTURE}" || return 1
    PATH="${STUBS}:${PATH}" run --separate-stderr "${SCRIPT}" "$@"
}

GREEN='{"caught":3,"missed":0,"timeout":0,"unviable":1}'

@test "no arguments exit 2 with usage" {
    _run_script
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"Usage"* ]]
}

@test "base ref only exits 2 with usage" {
    _run_script main
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"Usage"* ]]
}

@test "--min-caught with non-integer exits 2" {
    _run_script main --min-caught x a/a-rs
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"Usage"* ]]
}

@test "--min-caught with leading zero exits 2" {
    _run_script main --min-caught 01 a/a-rs
    [ "${status}" -eq 2 ]
}

@test "--min-caught with 20 digits exits 2" {
    _run_script main --min-caught 12345678901234567890 a/a-rs
    [ "${status}" -eq 2 ]
}

@test "--min-caught without a value exits 2" {
    _run_script main a/a-rs --min-caught
    [ "${status}" -eq 2 ]
}

@test "two green crates exit 0 and stub runs once per crate" {
    _change a/a-rs
    _change b/b-rs
    _commit
    _cfg a/a-rs 0 "${GREEN}"
    _cfg b/b-rs 0 "${GREEN}"
    _run_script main a/a-rs b/b-rs
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"green: a/a-rs"* ]]
    [[ "${output}" == *"green: b/b-rs"* ]]
    [ "$(wc -l <"${STUB_LOG}")" -eq 2 ]
    [ "$(grep -c -- '-C a/a-rs ' "${STUB_LOG}")" -eq 1 ]
    [ "$(grep -c -- '-C b/b-rs ' "${STUB_LOG}")" -eq 1 ]
}

@test "DIFF is absolute and its +++ line is crate-relative" {
    _change a/a-rs
    _commit
    _cfg a/a-rs 0 "${GREEN}"
    _run_script main a/a-rs
    [ "${status}" -eq 0 ]
    [[ "${output}" != *"red:"* ]]
    run grep -c 'DIFF=/' "${STUB_LOG}"
    [ "${output}" = "1" ]
    run grep -c 'PLUS=+++ b/src/' "${STUB_LOG}"
    [ "${output}" = "1" ]
}

@test "empty diff is red and make never runs for it" {
    _change b/b-rs
    _commit
    _cfg a/a-rs 0 "${GREEN}"
    _run_script main a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"red: a/a-rs - selected but diff empty"* ]]
    [ ! -s "${STUB_LOG}" ]
}

@test "diff failure is red" {
    _change a/a-rs
    _commit
    _run_script no-such-ref a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"red: a/a-rs - diff failed"* ]]
    [ ! -s "${STUB_LOG}" ]
}

@test "missing exit-code file is red" {
    _change a/a-rs
    _commit
    _cfg a/a-rs "" "${GREEN}"
    _run_script main a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"red: a/a-rs - no mutants.out/exit-code"* ]]
}

@test "non-integer exit-code is red" {
    _change a/a-rs
    _commit
    _cfg a/a-rs "oops" "${GREEN}"
    _run_script main a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"red: a/a-rs - mutants.out/exit-code 'oops' is not an integer"* ]]
}

@test "red first crate still runs the second and exits 1" {
    _change a/a-rs
    _change b/b-rs
    _commit
    _cfg a/a-rs "" ""
    _cfg b/b-rs 0 "${GREEN}"
    _run_script main a/a-rs b/b-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"red: a/a-rs"* ]]
    [[ "${output}" == *"green: b/b-rs"* ]]
    [ "$(wc -l <"${STUB_LOG}")" -eq 2 ]
}

@test "any missed mutant is red (limit 0)" {
    _change a/a-rs
    _commit
    _cfg a/a-rs 2 '{"caught":3,"missed":1,"timeout":0,"unviable":0}'
    _run_script main a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"red: a/a-rs - missed=1 exceeds max_missed=0"* ]]
}

@test "--min-caught 1 with caught 0 is red" {
    _change a/a-rs
    _commit
    _cfg a/a-rs 0 '{"caught":0,"missed":0,"timeout":0,"unviable":2}'
    _run_script main --min-caught 1 a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"red: a/a-rs"* ]]
}

@test "--min-caught 1 with caught 3 is green, flag after base or after dirs" {
    _change a/a-rs
    _commit
    _cfg a/a-rs 0 "${GREEN}"
    _run_script main --min-caught 1 a/a-rs
    [ "${status}" -eq 0 ]
    _run_script main a/a-rs --min-caught 1
    [ "${status}" -eq 0 ]
}

@test "temp dir is removed on exit" {
    _change a/a-rs
    _commit
    _cfg a/a-rs 0 "${GREEN}"
    export TMPDIR="${BATS_TEST_TMPDIR}/tmp"
    mkdir -p "${TMPDIR}"
    _run_script main a/a-rs
    [ "${status}" -eq 0 ]
    [ -z "$(ls -A "${TMPDIR}")" ]
}

@test "stale green mutants.out is cleared: make writing nothing is red" {
    _change a/a-rs
    _commit
    mkdir -p "${FIXTURE}/a/a-rs/mutants.out"
    printf '0\n' >"${FIXTURE}/a/a-rs/mutants.out/exit-code"
    printf '%s\n' "${GREEN}" >"${FIXTURE}/a/a-rs/mutants.out/outcomes.json"
    printf 'status=2\n' >"${STUB_CFG}/a_a-rs"
    _run_script main a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"red: a/a-rs - no mutants.out/exit-code"* ]]
}

@test "--min-caught reaches the classifier: caught 2 below 3 is red" {
    _change a/a-rs
    _commit
    _cfg a/a-rs 0 '{"caught":2,"missed":0,"timeout":0,"unviable":0}'
    _run_script main a/a-rs
    [ "${status}" -eq 0 ]
    _run_script main --min-caught 3 a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"caught=2 below min_caught=3"* ]]
}

@test "red classifier verdict goes to stdout, not stderr" {
    _change a/a-rs
    _commit
    _cfg a/a-rs 2 '{"caught":3,"missed":1,"timeout":0,"unviable":0}'
    _run_script_sep main a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"red: a/a-rs - missed=1"* ]]
    [[ "${stderr}" != *"red:"* ]]
}

@test "relative TMPDIR still yields an absolute DIFF" {
    _change a/a-rs
    _commit
    _cfg a/a-rs 0 "${GREEN}"
    mkdir -p "${FIXTURE}/reltmp"
    export TMPDIR="reltmp"
    _run_script main a/a-rs
    [ "${status}" -eq 0 ]
    run grep -c 'DIFF=/' "${STUB_LOG}"
    [ "${output}" = "1" ]
}

@test "exit-code beyond 255 is red" {
    _change a/a-rs
    _commit
    _cfg a/a-rs 18446744073709551616 "${GREEN}"
    _run_script main a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"red: a/a-rs"* ]]
}

@test "exit-code 00 is red, not read as 0" {
    _change a/a-rs
    _commit
    _cfg a/a-rs 00 "${GREEN}"
    _run_script main a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"red: a/a-rs"* ]]
}

@test "dash-prefixed base ref exits 2 with usage" {
    _run_script --min-caught 1 HEAD~1 a/a-rs
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"Usage"* ]]
    [ ! -s "${STUB_LOG}" ]
}

@test "unknown dash-prefixed argument exits 2 with usage" {
    _run_script main --bogus a/a-rs
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"Usage"* ]]
    [ ! -s "${STUB_LOG}" ]
}
