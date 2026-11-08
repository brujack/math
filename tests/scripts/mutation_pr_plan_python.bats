#!/usr/bin/env bats

load ../helpers/common

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    export HOME="${BATS_TEST_TMPDIR}/home"
    export XDG_CONFIG_HOME="${BATS_TEST_TMPDIR}/xdg"
    mkdir -p "${HOME}" "${XDG_CONFIG_HOME}"

    SCRIPT="${REPO_ROOT}/scripts/mutation-pr-plan-python.sh"
    export PLAN_OUT="${BATS_TEST_TMPDIR}/out"
    mkdir -p "${PLAN_OUT}"
    unset GITHUB_STEP_SUMMARY

    # Per-dir fixtures: ${FIX}/<dir>.out (make stdout), .err (stderr), .rc (exit status).
    export FIX="${BATS_TEST_TMPDIR}/fix"
    mkdir -p "${FIX}" "${BATS_TEST_TMPDIR}/bin"

    cat >"${BATS_TEST_TMPDIR}/bin/make" <<'MOCK'
#!/usr/bin/env bash
# Mock make: `make -C <dir> mutants-diff-plan DIFF=<file>`.
dir="$2"
[[ -f "${FIX}/${dir}.out" ]] && cat "${FIX}/${dir}.out"
[[ -f "${FIX}/${dir}.err" ]] && cat "${FIX}/${dir}.err" >&2
rc=0
[[ -f "${FIX}/${dir}.rc" ]] && rc="$(cat "${FIX}/${dir}.rc")"
exit "${rc}"
MOCK
    cat >"${BATS_TEST_TMPDIR}/bin/mock-diff" <<'MOCK'
#!/usr/bin/env bash
# Mock mutation-pr-diff.sh <base> <dir> <out>.
if [[ -f "${FIX}/$2.diffrc" ]]; then
    printf 'diff boom for %s\n' "$2" >&2
    exit 1
fi
printf 'diff for %s\n' "$2" >"$3"
MOCK
    chmod +x "${BATS_TEST_TMPDIR}/bin/make" "${BATS_TEST_TMPDIR}/bin/mock-diff"
    export PATH="${BATS_TEST_TMPDIR}/bin:${PATH}"
    export MUTATION_PR_DIFF="${BATS_TEST_TMPDIR}/bin/mock-diff"
}

prune_out() {
    # prune_out <dir> <excluded> <kept> <lines>
    local dir="$1" excl="$2" kept="$3" lines="$4"
    printf 'excluded %s of %s (re-confirm: diff, 0 on changed lines)\nkept %s of %s (lines %s)\n' \
        "${excl}" "$((excl + kept))" "${kept}" "$((excl + kept))" "${lines}" >"${FIX}/${dir}.out"
}

@test "n for K=0 gives no units and a green zero-mutants line" {
    prune_out pi 3 0 2
    run bash "${SCRIPT}" base pi </dev/null
    [ "${status}" -eq 0 ]
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t0 mutants on changed lines')" ]
    [ "$(cat "${PLAN_OUT}/units.json")" = "[]" ]
}

@test "n for K=1 is 1" {
    prune_out pi 0 1 1
    run bash "${SCRIPT}" base pi </dev/null
    [ "${status}" -eq 0 ]
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t1 mutants in 1 shards')" ]
    [ "$(cat "${PLAN_OUT}/units.json")" = '[{"dir":"pi","k":0,"n":1}]' ]
}

@test "n for K=150 is 1" {
    prune_out pi 0 150 9
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t150 mutants in 1 shards')" ]
    [ "$(cat "${PLAN_OUT}/units.json")" = '[{"dir":"pi","k":0,"n":1}]' ]
}

@test "n for K=151 is 2" {
    prune_out pi 0 151 9
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t151 mutants in 2 shards')" ]
    [ "$(cat "${PLAN_OUT}/units.json")" = '[{"dir":"pi","k":0,"n":2},{"dir":"pi","k":1,"n":2}]' ]
}

@test "n for K=1500 is 10" {
    prune_out pi 0 1500 9
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t1500 mutants in 10 shards')" ]
    run python3 -c 'import json,sys; u=json.load(open(sys.argv[1])); assert [x["k"] for x in u]==list(range(10)); assert {x["n"] for x in u}=={10}' "${PLAN_OUT}/units.json"
    [ "${status}" -eq 0 ]
}

@test "n for K=1501 is capped at 10" {
    prune_out pi 0 1501 9
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t1501 mutants in 10 shards')" ]
}

@test "plan n equals units n for every unit dir" {
    prune_out pi 0 151 9
    prune_out e 0 1 1
    run bash "${SCRIPT}" base pi e </dev/null
    [ "${status}" -eq 0 ]
    run python3 -I -c '
import json, sys, re
units = json.load(open(sys.argv[1]))
for line in open(sys.argv[2]):
    d, v, t = line.rstrip("\n").split("\t")
    m = re.fullmatch(r"([0-9]+) mutants in ([0-9]+) shards", t)
    assert m
    ns = {u["n"] for u in units if u["dir"] == d}
    assert ns == {int(m.group(2))}, (d, ns)
    assert len([u for u in units if u["dir"] == d]) == int(m.group(2))
' "${PLAN_OUT}/units.json" "${PLAN_OUT}/plan.txt"
    [ "${status}" -eq 0 ]
}

@test "lines 0 is a red plan line" {
    printf 'excluded 164 of 164 (re-confirm: diff, 0 on changed lines)\nkept 0 of 164 (lines 0)\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tred\tlines 0')" ]
    [ "$(cat "${PLAN_OUT}/units.json")" = "[]" ]
}

@test "kept 0 with lines 2 is green zero mutants" {
    printf 'excluded 4 of 4 (re-confirm: diff, 0 on changed lines)\nkept 0 of 4 (lines 2)\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t0 mutants on changed lines')" ]
}

@test "baseline failure is red and carries stderr" {
    printf 'baseline exploded\n' >"${FIX}/pi.err"
    printf '2' >"${FIX}/pi.rc"
    run bash "${SCRIPT}" base pi </dev/null
    [ "${status}" -eq 0 ]
    local line
    line="$(cat "${PLAN_OUT}/plan.txt")"
    [[ "${line}" == "pi"$'\t'"red"$'\t'*"baseline exploded" ]]
    [ "$(wc -l <"${PLAN_OUT}/plan.txt")" -eq 1 ]
}

@test "prune failure is red and carries stderr" {
    printf 'prune: cannot read equivalents\n' >"${FIX}/pi.err"
    printf '1' >"${FIX}/pi.rc"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'*"prune: cannot read equivalents" ]]
}

@test "re-confirm failure is red and carries prune's message" {
    printf 'prune: re-confirm failed: 3 equivalents now live\n' >"${FIX}/pi.err"
    printf '1' >"${FIX}/pi.rc"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'*"re-confirm failed: 3 equivalents now live" ]]
}

@test "multi-line stderr stays one plan line and full text reaches the summary" {
    printf 'line one\r\nline two\nline three\n' >"${FIX}/pi.err"
    printf '1' >"${FIX}/pi.rc"
    export GITHUB_STEP_SUMMARY="${BATS_TEST_TMPDIR}/summary.md"
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(wc -l <"${PLAN_OUT}/plan.txt")" -eq 1 ]
    run grep -c $'\r' "${PLAN_OUT}/plan.txt"
    [ "${output}" = "0" ]
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == *"line one | line two | line three" ]]
    grep -qx 'line two' "${GITHUB_STEP_SUMMARY}"
}

@test "diff step failure is red and names the step" {
    : >"${FIX}/pi.diffrc"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'"diff"*"diff boom for pi" ]]
    [ "$(cat "${PLAN_OUT}/units.json")" = "[]" ]
}

@test "unparseable make stdout is red (fail closed)" {
    printf 'something unexpected\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'* ]]
    [ "$(cat "${PLAN_OUT}/units.json")" = "[]" ]
}

@test "zero dirs gives empty plan and []" {
    run bash "${SCRIPT}" base </dev/null
    [ "${status}" -eq 0 ]
    [ -f "${PLAN_OUT}/plan.txt" ]
    [ ! -s "${PLAN_OUT}/plan.txt" ]
    [ "$(cat "${PLAN_OUT}/units.json")" = "[]" ]
}

@test "all dirs kept 0 gives []" {
    printf 'excluded 2 of 2 (re-confirm: diff, 0 on changed lines)\nkept 0 of 2 (lines 2)\n' >"${FIX}/pi.out"
    cp "${FIX}/pi.out" "${FIX}/e.out"
    run bash "${SCRIPT}" base pi e </dev/null
    [ "$(wc -l <"${PLAN_OUT}/plan.txt")" -eq 2 ]
    [ "$(cat "${PLAN_OUT}/units.json")" = "[]" ]
}

@test "mixed dirs keep one line per dir, units only for green unit dirs" {
    prune_out pi 0 5 5
    printf 'boom\n' >"${FIX}/e.err"
    printf '1' >"${FIX}/e.rc"
    run bash "${SCRIPT}" base pi e </dev/null
    [ "$(wc -l <"${PLAN_OUT}/plan.txt")" -eq 2 ]
    [ "$(sed -n 1p "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t5 mutants in 1 shards')" ]
    [ "$(cat "${PLAN_OUT}/units.json")" = '[{"dir":"pi","k":0,"n":1}]' ]
}

@test "step summary is written when GITHUB_STEP_SUMMARY is set" {
    prune_out pi 0 5 5
    export GITHUB_STEP_SUMMARY="${BATS_TEST_TMPDIR}/summary.md"
    run bash "${SCRIPT}" base pi </dev/null
    [ -s "${GITHUB_STEP_SUMMARY}" ]
    run grep -c 'pi' "${GITHUB_STEP_SUMMARY}"
    [ "${output}" -ge 1 ]
}

@test "no base sha exits 2" {
    run bash "${SCRIPT}" </dev/null
    [ "${status}" -eq 2 ]
}

@test "lines 0 with stderr carries flattened stderr and full stderr in summary" {
    printf 'excluded 164 of 164 (re-confirm: diff, 0 on changed lines)\nkept 0 of 164 (lines 0)\n' >"${FIX}/sq.out"
    printf 'diff changes nothing in sq.py;\nits +++ b/ paths: x.py\n' >"${FIX}/sq.err"
    export GITHUB_STEP_SUMMARY="${BATS_TEST_TMPDIR}/summary.md"
    run bash "${SCRIPT}" base sq </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'sq\tred\tlines 0: diff changes nothing in sq.py; | its +++ b/ paths: x.py')" ]
    grep -qx 'its +++ b/ paths: x.py' "${GITHUB_STEP_SUMMARY}"
}

@test "unparseable output carries flattened stderr" {
    printf 'garbage\n' >"${FIX}/pi.out"
    printf 'warn one\nwarn two\n' >"${FIX}/pi.err"
    export GITHUB_STEP_SUMMARY="${BATS_TEST_TMPDIR}/summary.md"
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tred\tunparseable prune output: garbage | stderr: warn one | warn two')" ]
    grep -qx 'warn two' "${GITHUB_STEP_SUMMARY}"
}

@test "kept without excluded is red" {
    printf 'kept 5 of 5 (lines 2)\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'"unparseable prune output:"* ]]
    [ "$(cat "${PLAN_OUT}/units.json")" = "[]" ]
}

@test "excluded without kept is red" {
    printf 'excluded 0 of 5 (re-confirm: diff, 0 on changed lines)\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'"unparseable prune output:"* ]]
}

@test "kept before excluded is red" {
    printf 'kept 5 of 5 (lines 2)\nexcluded 0 of 5 (re-confirm: diff, 0 on changed lines)\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'"unparseable prune output:"* ]]
}

@test "duplicate kept line is red" {
    printf 'excluded 0 of 5 (re-confirm: diff, 0 on changed lines)\nkept 5 of 5 (lines 2)\nkept 5 of 5 (lines 2)\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'"unparseable prune output:"* ]]
}

@test "duplicate excluded line is red" {
    printf 'excluded 0 of 5 (re-confirm: diff, 0 on changed lines)\nexcluded 0 of 5 (re-confirm: diff, 0 on changed lines)\nkept 5 of 5 (lines 2)\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'"unparseable prune output:"* ]]
}

@test "kept greater than total is red" {
    printf 'excluded 0 of 5 (re-confirm: diff, 0 on changed lines)\nkept 6 of 5 (lines 2)\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'"unparseable prune output:"* ]]
}

@test "anchored regex rejects a kept lookalike" {
    printf 'excluded 0 of 5 (re-confirm: diff, 0 on changed lines)\nxkept 5 of 5 (lines 2) y\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'* ]]
}

@test "anchored regex rejects an excluded lookalike" {
    printf 'xexcluded 0 of 5 (re-confirm: diff, 0 on changed lines) y\nkept 5 of 5 (lines 2)\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'* ]]
}

@test "leading-zero kept is read as decimal" {
    printf 'excluded 1 of 9 (re-confirm: diff, 0 on changed lines)\nkept 08 of 9 (lines 2)\n' >"${FIX}/pi.out"
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t8 mutants in 1 shards')" ]
}

@test "trailing slash dir is normalised" {
    prune_out pi 0 5 5
    run bash "${SCRIPT}" base pi/ </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t5 mutants in 1 shards')" ]
}

@test "tab in stderr keeps the plan line at three fields" {
    printf 'a\tb\n' >"${FIX}/pi.err"
    printf '1' >"${FIX}/pi.rc"
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(awk -F'\t' '{print NF}' "${PLAN_OUT}/plan.txt")" = "3" ]
}

@test "pipe in detail is escaped in the summary table but raw in the fence" {
    printf 'one\ntwo\n' >"${FIX}/pi.err"
    printf '1' >"${FIX}/pi.rc"
    export GITHUB_STEP_SUMMARY="${BATS_TEST_TMPDIR}/summary.md"
    run bash "${SCRIPT}" base pi </dev/null
    grep -qF 'one \| two' "${GITHUB_STEP_SUMMARY}"
}

@test "unwritable PLAN_OUT exits 1" {
    prune_out pi 0 5 5
    export PLAN_OUT="/dev/null/nope"
    run bash "${SCRIPT}" base pi </dev/null
    [ "${status}" -eq 1 ]
}
