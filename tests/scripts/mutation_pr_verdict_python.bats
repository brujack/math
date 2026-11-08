#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    SCRIPT="${REPO_ROOT}/scripts/mutation-pr-verdict-python.sh"
    export HOME="${BATS_TEST_TMPDIR}"
    export XDG_CONFIG_HOME="${BATS_TEST_TMPDIR}/xdg"
    unset GITHUB_STEP_SUMMARY
    PLAN="${BATS_TEST_TMPDIR}/plan.txt"
    STATUS="${BATS_TEST_TMPDIR}/status"
    mkdir -p "${STATUS}"
    : >"${PLAN}"
}

# plan_line <dir> <verdict> <text>
plan_line() {
    printf '%s\t%s\t%s\n' "$1" "$2" "$3" >>"${PLAN}"
}

# green_unit <dir> <k> <jobs>: the status file cell_status prints for a clean unit.
green_unit() {
    printf 'green: %s-%s — 0 surviving, 1 timed out, %s jobs\n' "$1" "$2" "$3" >"${STATUS}/$1-$2"
}

# red_unit <dir> <k>: real cell_status output for a session with survivors.
red_unit() {
    python3 "${REPO_ROOT}/scripts/cosmic_ray_cell_status.py" \
        "${REPO_ROOT}/tests/fixtures/cosmic_ray/crfix-exec.sqlite" "$1-$2" --max-survivors 0 \
        >"${STATUS}/$1-$2" || true
}

verdict() {
    "${SCRIPT}" "$@" "${PLAN}" "${STATUS}"
}

# Row 1
@test "row 1: expected dir missing from plan is red" {
    plan_line pi green "0 mutants on changed lines"
    run -1 verdict --expected-dirs "pi e"
    [[ "${output}" == *"e: red: expected dir has no plan line"* ]]
}

@test "row 1: unexpected plan dir is red" {
    plan_line pi green "0 mutants on changed lines"
    plan_line sq green "0 mutants on changed lines"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"sq: red: plan line for a dir that is not expected"* ]]
    [[ "${output}" == *"pi: green: 0 mutants on changed lines"* ]]
}

@test "row 1: zero expected dirs and an empty plan is green" {
    run -0 verdict --expected-dirs ""
    [ -z "${output}" ]
}

@test "row 1: duplicate plan line is red" {
    plan_line pi green "0 mutants on changed lines"
    plan_line pi green "0 mutants on changed lines"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"pi: red: duplicate plan line"* ]]
    # The duplicate must not also be judged: exactly one verdict line besides the red one.
    [ "$(printf '%s\n' "${output}" | grep -c '^pi: green')" -eq 1 ]
}

# Row 2
@test "row 2: red plan line carries its failure text" {
    plan_line pi red "baseline failed: ModuleNotFoundError"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"pi: red: plan step failed: baseline failed: ModuleNotFoundError"* ]]
}

@test "row 2: planned unit with no status file is red with its repro" {
    plan_line pi green "300 mutants in 2 shards"
    green_unit pi 0 150
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"unit 1/2: no status file pi-1"* ]]
    [[ "${output}" == *"MUTANT_SHARD=1/2"* ]]
}

@test "row 2: unknown plan verdict is red" {
    plan_line pi maybe "x"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"unknown plan verdict 'maybe'"* ]]
}

@test "row 2: unknown green plan text fails closed" {
    plan_line pi green "all fine"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"unknown plan line: 'all fine'"* ]]
}

@test "row 2: zero shards in plan text fails closed" {
    plan_line pi green "5 mutants in 0 shards"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"zero shards"* ]]
}

@test "row 2: unrecognised status file content is red" {
    plan_line pi green "5 mutants in 1 shards"
    printf 'garbage\n' >"${STATUS}/pi-0"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"unrecognised status file pi-0"* ]]
}

# Row 3
@test "row 3: lines 0 is red" {
    plan_line pi red "lines 0"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"pi: red: no changed module lines (lines 0)"* ]]
}

@test "row 3: lines 0 with prune detail is row 3 and shows the detail" {
    plan_line sq red "lines 0: diff changes nothing in sq.py; its +++ b/ paths: x.py"
    run -1 verdict --expected-dirs "sq"
    [[ "${output}" == *"sq: red: no changed module lines (lines 0)"* ]]
    [[ "${output}" == *"diff changes nothing in sq.py; its +++ b/ paths: x.py"* ]]
}

@test "row 3: lines 05 is not row 3" {
    plan_line sq red "lines 05"
    run -1 verdict --expected-dirs "sq"
    [[ "${output}" == *"sq: red: plan step failed: lines 05"* ]]
}

@test "row 3: lines 0x is not row 3" {
    plan_line sq red "lines 0x"
    run -1 verdict --expected-dirs "sq"
    [[ "${output}" == *"sq: red: plan step failed: lines 0x"* ]]
}

@test "row 3: xlines 0 is not row 3" {
    plan_line sq red "xlines 0"
    run -1 verdict --expected-dirs "sq"
    [[ "${output}" == *"sq: red: plan step failed: xlines 0"* ]]
}

# Row 4
@test "row 4: kept 0 with --min-killed 1 is red" {
    plan_line sq green "0 mutants on changed lines"
    run -1 verdict --expected-dirs "sq" --min-killed 1
    [[ "${output}" == *"killed 0 < --min-killed 1"* ]]
}

@test "row 4: killed below --min-killed is red" {
    plan_line sq green "13 mutants in 1 shards"
    green_unit sq 0 3
    run -1 verdict --expected-dirs "sq" --min-killed 4
    [[ "${output}" == *"killed 3 < --min-killed 4"* ]]
}

@test "row 4: killed equal to --min-killed is green, summed over shards" {
    plan_line sq green "300 mutants in 2 shards"
    green_unit sq 0 2
    green_unit sq 1 2
    run -0 verdict --expected-dirs "sq" --min-killed 4
    [[ "${output}" == *"sq: green: 2 shards, 0 surviving, 4 killed"* ]]
}

# Row 5
@test "row 5: structural red status is red" {
    plan_line pi green "5 mutants in 1 shards"
    printf 'red: pi-0 — 232 work items without a result\n' >"${STATUS}/pi-0"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"unit 0/1: red: pi-0 — 232 work items without a result"* ]]
}

# Row 6
@test "row 6: survivors show full key, diff and repro" {
    plan_line pi green "300 mutants in 3 shards"
    green_unit pi 0 100
    red_unit pi 1
    green_unit pi 2 100
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *'crfix.py:5 col 13 core/ReplaceBinaryOperator_Add_BitAnd function "bump"'* ]]
    [[ "${output}" == *"+    return x & 2"* ]]
    [[ "${output}" == *'repro: d=$(mktemp) && scripts/mutation-pr-diff.sh origin/master pi "$d" && make -C pi mutants-diff DIFF="$d" MUTANT_SHARD=1/3'* ]]
    [[ "${output}" != *"MUTANT_SHARD=0/3"* ]]
}

# Rows 7 and 8
@test "row 7: kept 0 with lines > 0 is green" {
    plan_line pi green "0 mutants on changed lines"
    run -0 verdict --expected-dirs "pi"
    [ "${output}" = "pi: green: 0 mutants on changed lines" ]
}

@test "row 8: all units clean is green" {
    plan_line pi green "613 mutants in 2 shards"
    green_unit pi 0 300
    green_unit pi 1 313
    plan_line e green "0 mutants on changed lines"
    run -0 verdict --expected-dirs "pi e"
    [[ "${output}" == *"pi: green: 2 shards, 0 surviving, 613 killed"* ]]
    [[ "${output}" == *"e: green: 0 mutants on changed lines"* ]]
}

@test "order: one red dir among green ones exits 1 and still reports the others" {
    plan_line pi green "5 mutants in 1 shards"
    red_unit pi 0
    plan_line e green "0 mutants on changed lines"
    run -1 verdict --expected-dirs "pi e"
    [[ "${output}" == *"e: green"* ]]
}

@test "summary: output is appended to GITHUB_STEP_SUMMARY when set" {
    plan_line pi green "0 mutants on changed lines"
    export GITHUB_STEP_SUMMARY="${BATS_TEST_TMPDIR}/summary.md"
    run -0 verdict --expected-dirs "pi"
    [ "$(cat "${GITHUB_STEP_SUMMARY}")" = "pi: green: 0 mutants on changed lines" ]
}

@test "summary: unset leaves no file behind" {
    plan_line pi green "0 mutants on changed lines"
    run -0 verdict --expected-dirs "pi"
    [ ! -e "${BATS_TEST_TMPDIR}/summary.md" ]
}

# Usage errors
@test "usage: no arguments exits 2" {
    run -2 "${SCRIPT}"
}

@test "usage: missing --expected-dirs exits 2" {
    run -2 verdict
}

@test "usage: missing status dir exits 2" {
    run -2 "${SCRIPT}" --expected-dirs "pi" "${PLAN}"
}

@test "usage: unknown flag exits 2" {
    run -2 verdict --expected-dirs "pi" --bogus
    [[ "${output}" == *"unknown option --bogus"* ]]
}

@test "usage: non-numeric --min-killed exits 2" {
    run -2 verdict --expected-dirs "pi" --min-killed abc
    [[ "${output}" == *"--min-killed needs a non-negative integer"* ]]
}

@test "usage: negative --min-killed exits 2" {
    run -2 verdict --expected-dirs "pi" --min-killed -1
}

@test "usage: flag without value exits 2" {
    run -2 "${SCRIPT}" "${PLAN}" "${STATUS}" --expected-dirs
}

@test "usage: missing plan file exits 2" {
    run -2 "${SCRIPT}" --expected-dirs "pi" "${BATS_TEST_TMPDIR}/nope.txt" "${STATUS}"
}

@test "usage: extra positional exits 2" {
    run -2 "${SCRIPT}" --expected-dirs "pi" "${PLAN}" "${STATUS}" extra
}

@test "script is executable" {
    [ -x "${SCRIPT}" ]
}

@test "row 6: green-form line with one surviving is red (boundary 1)" {
    plan_line pi green "5 mutants in 1 shards"
    printf 'green: pi-0 — 1 surviving, 0 timed out, 5 jobs\n' >"${STATUS}/pi-0"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"unit 0/1: green: pi-0 — 1 surviving"* ]]
    [[ "${output}" == *"MUTANT_SHARD=0/1"* ]]
}

@test "row 6: green-form line with two surviving is red" {
    plan_line pi green "5 mutants in 1 shards"
    printf 'green: pi-0 — 2 surviving, 0 timed out, 5 jobs\n' >"${STATUS}/pi-0"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"MUTANT_SHARD=0/1"* ]]
    [[ "${output}" != *"pi: green"* ]]
}

@test "plan: text after the shard count is unknown" {
    plan_line pi green "5 mutants in 1 shards x"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"unknown plan line"* ]]
}

@test "plan: text before the mutant count is unknown" {
    plan_line pi green "x 5 mutants in 1 shards"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"unknown plan line"* ]]
}

@test "status: valid green line with trailing text is unrecognised" {
    plan_line pi green "5 mutants in 1 shards"
    printf 'green: pi-0 — 0 surviving, 0 timed out, 5 jobs extra\n' >"${STATUS}/pi-0"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"unrecognised status file pi-0"* ]]
}

@test "status: valid green line with leading text is unrecognised" {
    plan_line pi green "5 mutants in 1 shards"
    printf 'x green: pi-0 — 0 surviving, 0 timed out, 5 jobs\n' >"${STATUS}/pi-0"
    run -1 verdict --expected-dirs "pi"
    [[ "${output}" == *"unrecognised status file pi-0"* ]]
}

@test "plan: LF and CRLF blank lines are skipped" {
    plan_line pi green "0 mutants on changed lines"
    printf '\n\r\n' >>"${PLAN}"
    run -0 verdict --expected-dirs "pi"
    [ "${output}" = "pi: green: 0 mutants on changed lines" ]
}

@test "plan: last line without a trailing newline is judged" {
    printf 'pi\tgreen\t0 mutants on changed lines' >"${PLAN}"
    run -0 verdict --expected-dirs "pi"
    [ "${output}" = "pi: green: 0 mutants on changed lines" ]
}
