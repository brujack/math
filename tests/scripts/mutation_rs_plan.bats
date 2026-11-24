#!/usr/bin/env bats
# The real mutation-pr-diff.sh runs against a fixture git repo; only `cargo` is stubbed.

bats_require_minimum_version 1.5.0

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    export HOME="${BATS_TEST_TMPDIR}"
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    SCRIPT="${REPO_ROOT}/scripts/mutation-rs-plan.sh"
    FIXTURE="${BATS_TEST_TMPDIR}/repo"
    STUBS="${BATS_TEST_TMPDIR}/stubs"
    export STUB_CFG="${BATS_TEST_TMPDIR}/cfg"
    export STUB_LOG="${BATS_TEST_TMPDIR}/cargo.log"

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
    _write_stub_cargo
}

_git() {
    git -C "${FIXTURE}" -c user.name=t -c user.email=t@t "$@"
}

# Stub cargo: logs argv and whether the --in-diff file exists, then prints per
# the config named for the crate dir's basename (cwd). Config lines:
# `count=K` prints a JSON array of K objects, `raw=TEXT` prints TEXT, `exit=N` sets the status.
_write_stub_cargo() {
    cat >"${STUBS}/cargo" <<'STUB'
#!/usr/bin/env bash
base="${PWD##*/}"
diff_ok=no
prev=""
for arg in "$@"; do
    if [[ "${prev}" == "--in-diff" && -s "${arg}" && "${arg}" == /* ]]; then diff_ok=yes; fi
    prev="${arg}"
done
printf '%s %s diff_ok=%s\n' "${base}" "$*" "${diff_ok}" >>"${STUB_LOG}"
cfg="${STUB_CFG}/${base}"
status=0
[[ -f "${cfg}" ]] || exit 0
while IFS= read -r line; do
    case "${line}" in
        count=*) jq -nc --argjson k "${line#count=}" '[range($k) | {}]' ;;
        raw=*) printf '%s' "${line#raw=}" ;;
        exit=*) status="${line#exit=}" ;;
    esac
done <"${cfg}"
exit "${status}"
STUB
    chmod +x "${STUBS}/cargo"
}

# _cfg <crate-basename> <line>...
_cfg() {
    local name="$1"
    shift
    printf '%s\n' "$@" >"${STUB_CFG}/${name}"
}

_change() {
    printf 'pub fn f() -> u32 { 2 }\n' >"${FIXTURE}/$1/src/lib.rs"
}

_commit() {
    _git commit -q -am change
}

_plan() {
    cd "${FIXTURE}" || return 1
    PATH="${STUBS}:${PATH}" run --separate-stderr "${SCRIPT}" "$@"
}

@test "no arguments exits 2" {
    _plan
    [ "${status}" -eq 2 ]
}

@test "base ref alone without crates exits 2" {
    _plan main
    [ "${status}" -eq 2 ]
}

@test "--whole without crates exits 2" {
    _plan --whole
    [ "${status}" -eq 2 ]
}

@test "diff mode: one crate K=1 gives one unit and the plan line" {
    _change a/a-rs
    _commit
    _cfg a-rs count=1
    _plan main a/a-rs
    [ "${status}" -eq 0 ]
    [ "${output}" = '[{"crate":"a/a-rs","slug":"a-rs-0","k":0,"n":1,"count":1}]' ]
    [[ "${stderr}" == *'plan: a/a-rs K=1 n=1 per-shard=1'* ]]
}

@test "diff mode: trailing slash on the crate is normalised" {
    _change a/a-rs
    _commit
    _cfg a-rs count=1
    _plan main a/a-rs/
    [ "${status}" -eq 0 ]
    [ "$(jq -r '.[0].crate' <<<"${output}")" = "a/a-rs" ]
}

@test "diff mode: several crates give units in crate order" {
    _change a/a-rs
    _change b/b-rs
    _commit
    _cfg a-rs count=1
    _cfg b-rs count=76
    _plan main a/a-rs b/b-rs
    [ "${status}" -eq 0 ]
    [ "$(jq -c '[.[] | .slug]' <<<"${output}")" = '["a-rs-0","b-rs-0","b-rs-1"]' ]
}

@test "diff mode passes an absolute non-empty --in-diff file to cargo" {
    _change a/a-rs
    _commit
    _cfg a-rs count=1
    _plan main a/a-rs
    [ "${status}" -eq 0 ]
    command grep -q 'mutants --list --json --in-diff /' "${STUB_LOG}"
    command grep -q 'diff_ok=yes' "${STUB_LOG}"
}

@test "whole mode does not pass --in-diff" {
    _cfg a-rs count=1
    _plan --whole a/a-rs
    [ "${status}" -eq 0 ]
    command grep -q 'mutants --list --json' "${STUB_LOG}"
    ! command grep -q -- '--in-diff' "${STUB_LOG}"
}

@test "shard counts: K=1,75,76,1201 give n=1,1,2,17" {
    local k want n
    for pair in "1 1" "75 1" "76 2" "1201 17"; do
        k="${pair% *}"
        want="${pair#* }"
        _cfg a-rs "count=${k}"
        _plan --whole a/a-rs
        [ "${status}" -eq 0 ]
        n="$(jq -r '.[0].n' <<<"${output}")"
        [ "${n}" = "${want}" ]
        [ "$(jq 'length' <<<"${output}")" -eq "${want}" ]
        [ "$(jq '[.[].count] | add' <<<"${output}")" -eq "${k}" ]
    done
}

@test "K=339 gives counts 68,68,68,68,67" {
    _cfg a-rs count=339
    _plan --whole a/a-rs
    [ "${status}" -eq 0 ]
    [ "$(jq -c '[.[].count]' <<<"${output}")" = '[68,68,68,68,67]' ]
    [[ "${stderr}" == *'plan: a/a-rs K=339 n=5 per-shard=68'* ]]
}

@test "whole K=432 gives k 0..5 and six counts of 72" {
    _cfg a-rs count=432
    _plan --whole a/a-rs
    [ "${status}" -eq 0 ]
    [ "$(jq -c '[.[].k]' <<<"${output}")" = '[0,1,2,3,4,5]' ]
    [ "$(jq -c '[.[].count]' <<<"${output}")" = '[72,72,72,72,72,72]' ]
}

@test "unit key order is crate, slug, k, n, count" {
    _cfg a-rs count=5
    _plan --whole a/a-rs
    [ "$(jq -c '.[0] | keys_unsorted' <<<"${output}")" = '["crate","slug","k","n","count"]' ]
}

@test "shard total 257 is red" {
    _cfg a-rs count=19200
    _cfg b-rs count=1
    _plan --whole a/a-rs b/b-rs
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *'error: plan needs 257 shards, over the 256-job matrix limit (ADR-0046)'* ]]
}

@test "shard total 256 is green" {
    _cfg a-rs count=19200
    _plan --whole a/a-rs
    [ "${status}" -eq 0 ]
    [ "$(jq 'length' <<<"${output}")" -eq 256 ]
}

@test "diff mode K=0 (empty stdout) gives [] and the stderr line" {
    _change a/a-rs
    _commit
    _cfg a-rs raw=
    _plan main a/a-rs
    [ "${status}" -eq 0 ]
    [ "${output}" = '[]' ]
    [[ "${stderr}" == *'plan: a/a-rs K=0 (no mutants on changed lines)'* ]]
}

@test "diff mode K=0 (empty array) gives []" {
    _change a/a-rs
    _commit
    _cfg a-rs count=0
    _plan main a/a-rs
    [ "${status}" -eq 0 ]
    [ "${output}" = '[]' ]
}

@test "diff mode: empty diff is red" {
    _cfg a-rs count=3
    _plan main a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *'red: a/a-rs - diff empty'* ]]
}

@test "diff mode: diff failure is red" {
    _change a/a-rs
    _commit
    _plan no-such-ref a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *'red: a/a-rs - diff failed'* ]]
}

@test "diff mode: list exit 1 is red" {
    _change a/a-rs
    _commit
    _cfg a-rs count=3 exit=1
    _plan main a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *'red: a/a-rs - mutant listing failed'* ]]
}

@test "diff mode: non-array stdout is red" {
    _change a/a-rs
    _commit
    _cfg a-rs 'raw={}'
    _plan main a/a-rs
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *'red: a/a-rs - mutant listing failed'* ]]
}

@test "diff mode: one red crate does not hide the other crate's verdict" {
    _change b/b-rs
    _commit
    _cfg b-rs count=2
    _plan main a/a-rs b/b-rs
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *'red: a/a-rs - diff empty'* ]]
    [[ "${stderr}" == *'plan: b/b-rs K=2'* ]]
    [ -z "${output}" ]
}

@test "whole: a failing crate becomes a fault unit beside the other crate's units" {
    _cfg a-rs count=3 exit=1
    _cfg b-rs count=80
    _plan --whole a/a-rs b/b-rs
    [ "${status}" -eq 0 ]
    [ "$(jq -c '.[0]' <<<"${output}")" = '{"crate":"a/a-rs","slug":"a-rs-plan","k":0,"n":0,"count":0,"fault":"mutant listing failed"}' ]
    [ "$(jq -c '[.[1:][] | .slug]' <<<"${output}")" = '["b-rs-0","b-rs-1"]' ]
}

@test "whole: non-array stdout becomes a fault unit" {
    _cfg a-rs 'raw={}'
    _plan --whole a/a-rs
    [ "${status}" -eq 0 ]
    [ "$(jq -r '.[0].fault' <<<"${output}")" = "mutant listing is not a JSON array" ]
}

@test "whole: K=0 becomes a fault unit" {
    _cfg a-rs count=0
    _plan --whole a/a-rs
    [ "${status}" -eq 0 ]
    [ "$(jq -r '.[0].fault' <<<"${output}")" = "no mutants listed" ]
    [ "$(jq -r '.[0].slug' <<<"${output}")" = "a-rs-plan" ]
}

@test "whole: empty stdout becomes a no-mutants fault unit" {
    _cfg a-rs raw=
    _plan --whole a/a-rs
    [ "${status}" -eq 0 ]
    [ "$(jq -r '.[0].fault' <<<"${output}")" = "no mutants listed" ]
}

@test "fault units add nothing to the 256 shard total" {
    _cfg a-rs count=19200
    _cfg b-rs count=1 exit=1
    _plan --whole a/a-rs b/b-rs
    [ "${status}" -eq 0 ]
    [ "$(jq 'length' <<<"${output}")" -eq 257 ]
}

@test "large listing (750 objects) is counted" {
    _cfg a-rs count=750
    _plan --whole a/a-rs
    [ "${status}" -eq 0 ]
    [ "$(jq '[.[].count] | add' <<<"${output}")" -eq 750 ]
}
