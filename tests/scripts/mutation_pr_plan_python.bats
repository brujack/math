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
for arg in "$@"; do
    [[ "${arg}" == DIFF=* ]] && cp "${arg#DIFF=}" "${FIX}/${dir}.seen" 2>/dev/null
done
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

    # Weakening seams: `<cmd> <dir>` prints K (whole-module mutants after the prune) or s (suite seconds).
    # Fixtures: ${FIX}/<dir>.k, .s (stdout) and .krc, .src (exit status).
    cat >"${BATS_TEST_TMPDIR}/bin/mock-k" <<'MOCK'
#!/usr/bin/env bash
[[ -f "${FIX}/$1.k" ]] && cat "${FIX}/$1.k"
rc=0
[[ -f "${FIX}/$1.krc" ]] && rc="$(cat "${FIX}/$1.krc")"
exit "${rc}"
MOCK
    cat >"${BATS_TEST_TMPDIR}/bin/mock-s" <<'MOCK'
#!/usr/bin/env bash
[[ -f "${FIX}/$1.s" ]] && cat "${FIX}/$1.s"
rc=0
[[ -f "${FIX}/$1.src" ]] && rc="$(cat "${FIX}/$1.src")"
exit "${rc}"
MOCK
    chmod +x "${BATS_TEST_TMPDIR}/bin/mock-k" "${BATS_TEST_TMPDIR}/bin/mock-s"
    export MUTATION_PR_WEAKENING_K="${BATS_TEST_TMPDIR}/bin/mock-k"
    export MUTATION_PR_SUITE_SECONDS="${BATS_TEST_TMPDIR}/bin/mock-s"
    unset PY_TEST_DIRS
}

weak_fix() {
    # weak_fix <dir> <K> <s>
    printf '%s' "$2" >"${FIX}/$1.k"
    printf '%s' "$3" >"${FIX}/$1.s"
}

weak_n() {
    # weak_n <dir> <K> <s>: runs the planner on a test-only dir and prints the planned n.
    weak_fix "$1" "$2" "$3"
    PY_TEST_DIRS="$1" run bash "${SCRIPT}" base </dev/null
    [ "${status}" -eq 0 ]
    python3 -I -c '
import json, sys
u = json.load(open(sys.argv[1]))
assert [x["k"] for x in u] == list(range(len(u)))
assert {x["mode"] for x in u} == {"weakening"} and {x["dir"] for x in u} == {sys.argv[2]}
ns = {x["n"] for x in u}
assert ns == {len(u)}, (ns, len(u))
print(len(u))
' "${PLAN_OUT}/units.json" "$1"
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
    [ "$(cat "${PLAN_OUT}/units.json")" = '[{"dir":"pi","k":0,"n":1,"mode":"diff"}]' ]
}

@test "n for K=150 is 1" {
    prune_out pi 0 150 9
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t150 mutants in 1 shards')" ]
    [ "$(cat "${PLAN_OUT}/units.json")" = '[{"dir":"pi","k":0,"n":1,"mode":"diff"}]' ]
}

@test "n for K=151 is 2" {
    prune_out pi 0 151 9
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t151 mutants in 2 shards')" ]
    [ "$(cat "${PLAN_OUT}/units.json")" = '[{"dir":"pi","k":0,"n":2,"mode":"diff"},{"dir":"pi","k":1,"n":2,"mode":"diff"}]' ]
}

@test "n for K=1500 is 10" {
    prune_out pi 0 1500 9
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t1500 mutants in 10 shards')" ]
    run python3 -c 'import json,sys; u=json.load(open(sys.argv[1])); assert [x["k"] for x in u]==list(range(10)); assert {x["n"] for x in u}=={10}; assert {x["mode"] for x in u}=={"diff"}' "${PLAN_OUT}/units.json"
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
    [ "$(cat "${PLAN_OUT}/units.json")" = '[{"dir":"pi","k":0,"n":1,"mode":"diff"}]' ]
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

@test "weakening n for K=100 s=1 is 10" {
    [ "$(weak_n pi 100 1)" = "10" ]
}

@test "weakening n for K=3000 s=5 is 25" {
    [ "$(weak_n pi 3000 5)" = "25" ]
}

@test "weakening n for K=10000 s=10 is 40" {
    [ "$(weak_n pi 10000 10)" = "40" ]
}

@test "weakening n for K=0 is 10" {
    [ "$(weak_n pi 0 7)" = "10" ]
}

@test "weakening n rounds up at the 600 boundary: 601 gives 11 shards of work" {
    # K*s = 6001 -> ceil(6001/600) = 11
    [ "$(weak_n pi 6001 1)" = "11" ]
}

@test "weakening n at exactly K*s=6000 is 10 and 6000 vs 6600 differ" {
    [ "$(weak_n pi 6000 1)" = "10" ]
    [ "$(weak_n pi 6600 1)" = "11" ]
}

@test "sub-second suite time is kept in milliseconds, not rounded up first" {
    # K=6600, s=0.5 -> ceil(3300000/600000)=6 -> clamped to 10 (rounding s to 1 would give 11)
    [ "$(weak_n pi 6600 0.5)" = "10" ]
    # K=12100, s=0.5 -> ceil(6050000/600000)=11
    [ "$(weak_n pi 12100 0.5)" = "11" ]
    # one millisecond over the boundary: K=6000, s=1.001 -> 6006000/600000 -> 11
    [ "$(weak_n pi 6000 1.001)" = "11" ]
    [ "$(weak_n pi 6000 1.000)" = "10" ]
}

@test "weakening rows carry the exact shape and the plan line keeps the pinned text" {
    weak_fix pi 100 1
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [[ "$(cat "${PLAN_OUT}/units.json")" == '[{"dir":"pi","k":0,"n":10,"mode":"weakening","planned":10},{"dir":"pi","k":1,'* ]]
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t100 mutants in 10 shards')" ]
}

@test "dir in both src and test sets is planned once, in weakening mode" {
    prune_out pi 0 5 5
    weak_fix pi 100 1
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base pi </dev/null
    [ "${status}" -eq 0 ]
    [ "$(wc -l <"${PLAN_OUT}/plan.txt")" -eq 1 ]
    run python3 -I -c '
import json, sys
u = json.load(open(sys.argv[1]))
assert len(u) == 10 and {x["mode"] for x in u} == {"weakening"}
' "${PLAN_OUT}/units.json"
    [ "${status}" -eq 0 ]
}

@test "dir in both sets with an unconfirmed equivalent on a changed line is red and emits no weakening row" {
    weak_fix pi 100 1
    printf '%s\n' 'cosmic_ray_prune: entry 3 excludes a mutant on a changed line (pi.py:682); re-confirm it in this PR' >"${FIX}/pi.err"
    printf '2' >"${FIX}/pi.rc"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base pi </dev/null
    [ "${status}" -eq 0 ]
    [ "$(wc -l <"${PLAN_OUT}/plan.txt")" -eq 1 ]
    [[ "$(cat "${PLAN_OUT}/plan.txt")" == "pi"$'\t'"red"$'\t'"mutants-diff-plan failed: "*"entry 3 excludes a mutant on a changed line"*"re-confirm it in this PR" ]]
    [ "$(cat "${PLAN_OUT}/units.json")" = "[]" ]
    # the check reads the real PR diff, not the whole-module diff
    [ "$(cat "${FIX}/pi.seen")" = "diff for pi" ]
}

@test "dir in both sets whose diff plan is lines 0 is red and emits no weakening row" {
    weak_fix pi 100 1
    printf 'excluded 164 of 164 (re-confirm: diff, 0 on changed lines)\nkept 0 of 164 (lines 0)\n' >"${FIX}/pi.out"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base pi </dev/null
    [ "${status}" -eq 0 ]
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tred\tlines 0')" ]
    [ "$(cat "${PLAN_OUT}/units.json")" = "[]" ]
}

@test "dir in both sets with no covered line changed stays green weakening" {
    prune_out pi 2 0 2
    weak_fix pi 100 1
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base pi </dev/null
    [ "${status}" -eq 0 ]
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t100 mutants in 10 shards')" ]
    run python3 -I -c '
import json, sys
u = json.load(open(sys.argv[1]))
assert len(u) == 10 and {x["mode"] for x in u} == {"weakening"}
' "${PLAN_OUT}/units.json"
    [ "${status}" -eq 0 ]
}

@test "src-only dirs keep diff rows beside weakening rows" {
    prune_out e 0 5 5
    weak_fix pi 100 1
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base e </dev/null
    [ "${status}" -eq 0 ]
    [ "$(wc -l <"${PLAN_OUT}/plan.txt")" -eq 2 ]
    run python3 -I -c '
import json, sys
u = json.load(open(sys.argv[1]))
d = [x for x in u if x["dir"] == "e"]
w = [x for x in u if x["dir"] == "pi"]
assert d == [{"dir": "e", "k": 0, "n": 1, "mode": "diff"}], d
assert len(w) == 10 and {x["mode"] for x in w} == {"weakening"}
' "${PLAN_OUT}/units.json"
    [ "${status}" -eq 0 ]
}

@test "weakening ignores the changed-line prune: no make call for a test-only dir" {
    weak_fix pi 100 1
    printf 'garbage\n' >"${FIX}/pi.out"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -eq 0 ]
}

@test "non-numeric K fails closed" {
    weak_fix pi abc 1
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"pi"*"mutant count"* ]]
}

@test "empty K fails closed" {
    printf '' >"${FIX}/pi.k"
    printf '1' >"${FIX}/pi.s"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
}

@test "failed count command fails closed even when it printed a number" {
    weak_fix pi 100 1
    printf '3' >"${FIX}/pi.krc"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"pi"*"mutant count"* ]]
}

@test "non-numeric suite time fails closed" {
    weak_fix pi 100 fast
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"pi"*"suite time"* ]]
}

@test "failed timing command fails closed even when it printed a number" {
    weak_fix pi 100 1
    printf '1' >"${FIX}/pi.src"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"pi"*"suite time"* ]]
}

@test "negative or signed numbers fail closed" {
    weak_fix pi -5 1
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
}

@test "weakening failure leaves no units.json claiming success" {
    weak_fix pi abc 1
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
    [ ! -s "${PLAN_OUT}/units.json" ]
}

@test "empty PY_TEST_DIRS plans nothing in weakening mode" {
    prune_out pi 0 5 5
    PY_TEST_DIRS="" run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/units.json")" = '[{"dir":"pi","k":0,"n":1,"mode":"diff"}]' ]
}

@test "leading-zero K and s are read as decimal" {
    [ "$(weak_n pi 08 09)" = "10" ]
}

@test "K with a fractional part fails closed with the named message" {
    weak_fix pi 1.5 1
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"pi: mutant count is not a non-negative number"* ]]
}

@test "PY_TEST_DIRS with a dir and its trailing-slash twin plans 10 rows once" {
    weak_fix pi 100 1
    PY_TEST_DIRS="pi pi/" run bash "${SCRIPT}" base </dev/null
    [ "${status}" -eq 0 ]
    [ "$(wc -l <"${PLAN_OUT}/plan.txt")" -eq 1 ]
    run python3 -I -c 'import json,sys; assert len(json.load(open(sys.argv[1])))==10' "${PLAN_OUT}/units.json"
    [ "${status}" -eq 0 ]
}

# Real K path: the seam is unset, so the planner builds the whole-module diff and runs the (mock) make.
real_k_setup() {
    unset MUTATION_PR_WEAKENING_K
    WORKDIR="${BATS_TEST_TMPDIR}/work"
    mkdir -p "${WORKDIR}/pi"
    printf 'a = 1\nb = 2\n' >"${WORKDIR}/pi/pi.py"
    printf '[[equivalent]]\nline = 1\n' >"${WORKDIR}/pi/mutants-equivalent.toml"
    printf '5' >"${FIX}/pi.s"
    cd "${WORKDIR}" || return 1
}

@test "real K path hands mutants-diff-plan a whole-module diff with the toml" {
    real_k_setup
    printf 'excluded 2 of 102 (re-confirm: diff, 2 on changed lines)\nkept 100 of 102 (lines 3)\n' >"${FIX}/pi.out"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -eq 0 ]
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t100 mutants in 10 shards')" ]
    grep -qxF -- '+++ b/pi.py' "${FIX}/pi.seen"
    grep -qxF -- '+++ b/mutants-equivalent.toml' "${FIX}/pi.seen"
    grep -qxF -- '@@ -0,0 +1,2 @@' "${FIX}/pi.seen"
}

@test "real K path rejects a duplicated excluded line" {
    real_k_setup
    printf 'excluded 0 of 5 (re-confirm: diff, 0 on changed lines)\nexcluded 0 of 5 (re-confirm: diff, 0 on changed lines)\nkept 5 of 5 (lines 2)\n' >"${FIX}/pi.out"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"pi: mutant count"* ]]
}

@test "real K path rejects kept greater than total" {
    real_k_setup
    printf 'excluded 0 of 5 (re-confirm: diff, 0 on changed lines)\nkept 6 of 5 (lines 2)\n' >"${FIX}/pi.out"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
}

@test "real K path rejects kept before excluded" {
    real_k_setup
    printf 'kept 5 of 5 (lines 2)\nexcluded 0 of 5 (re-confirm: diff, 0 on changed lines)\n' >"${FIX}/pi.out"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
}

@test "real K path fails closed when make fails" {
    real_k_setup
    printf 'excluded 0 of 5 (re-confirm: diff, 0 on changed lines)\nkept 5 of 5 (lines 2)\n' >"${FIX}/pi.out"
    printf '1' >"${FIX}/pi.rc"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
}

@test "real K path fails closed when the module is missing" {
    real_k_setup
    rm pi/pi.py
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"pi: mutant count"* ]]
}

# Real suite-time path: stub python3 (and timeout) on PATH.
real_s_setup() {
    unset MUTATION_PR_SUITE_SECONDS
    WORKDIR="${BATS_TEST_TMPDIR}/work"
    mkdir -p "${WORKDIR}/pi"
    printf '100' >"${FIX}/pi.k"
    cd "${WORKDIR}" || return 1
    cat >"${BATS_TEST_TMPDIR}/bin/python3" <<'MOCK'
#!/usr/bin/env bash
printf '%s %s %s %s\n' "${PYTHONHASHSEED-unset}" "${PYTHONDONTWRITEBYTECODE-unset}" "$(basename "${PWD}")" "$*" >"${FIX}/python3.seen"
exit "${STUB_PY_RC:-0}"
MOCK
    chmod +x "${BATS_TEST_TMPDIR}/bin/python3"
}

@test "real suite-time path runs the suite under the shard's environment" {
    real_s_setup
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -eq 0 ]
    [ "$(cat "${FIX}/python3.seen")" = "0 1 pi -m unittest test_pi" ]
    run python3 -I -c 'import json,sys; assert len(json.load(open(sys.argv[1])))==10' "${PLAN_OUT}/units.json"
}

@test "real suite-time path fails closed when the suite fails" {
    real_s_setup
    STUB_PY_RC=1 PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"pi: suite time"* ]]
}

@test "real suite-time path fails closed on a timeout (rc 124) naming the dir" {
    real_s_setup
    printf '#!/usr/bin/env bash\nexit 124\n' >"${BATS_TEST_TMPDIR}/bin/timeout"
    chmod +x "${BATS_TEST_TMPDIR}/bin/timeout"
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"pi: suite timed out"* ]]
}

# Clock seam: prints a scripted microsecond reading per call (start, then end).
clock_stub() {
    # clock_stub <start_us> <end_us>
    printf '%s\n%s\n' "$1" "$2" >"${FIX}/clock.seq"
    cat >"${BATS_TEST_TMPDIR}/bin/mock-clock" <<'MOCK'
#!/usr/bin/env bash
head -n1 "${FIX}/clock.seq"
tail -n +2 "${FIX}/clock.seq" >"${FIX}/clock.seq.new"
mv "${FIX}/clock.seq.new" "${FIX}/clock.seq"
MOCK
    chmod +x "${BATS_TEST_TMPDIR}/bin/mock-clock"
    export MUTATION_PR_CLOCK_US="${BATS_TEST_TMPDIR}/bin/mock-clock"
}

@test "real suite time is end minus start, rounded up to a millisecond" {
    real_s_setup
    # 1000500 us -> 1001 ms (ceil). K=6000: 6000*1001/600000 -> 11; floor (1000 ms) would give 10.
    printf '6000' >"${FIX}/pi.k"
    clock_stub 5000000000 5001000500
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -eq 0 ]
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t6000 mutants in 11 shards')" ]
}

@test "real suite time on an exact millisecond is not rounded up" {
    real_s_setup
    printf '6000' >"${FIX}/pi.k"
    clock_stub 5000000000 5001000000
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t6000 mutants in 10 shards')" ]
}

@test "real suite time uses the start reading, not zero" {
    real_s_setup
    printf '6000' >"${FIX}/pi.k"
    clock_stub 5000000000 5002000000
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    # 2.000 s -> 12000000/600000 = 20 shards
    [ "$(cat "${PLAN_OUT}/plan.txt")" = "$(printf 'pi\tgreen\t6000 mutants in 20 shards')" ]
}

@test "the suite runs with stdin from /dev/null" {
    real_s_setup
    cat >"${BATS_TEST_TMPDIR}/bin/python3" <<'MOCK'
#!/usr/bin/env bash
cat >"${FIX}/python3.stdin"
exit 0
MOCK
    chmod +x "${BATS_TEST_TMPDIR}/bin/python3"
    run bash -c 'printf "SENTINEL\n" | PY_TEST_DIRS=pi bash "$0" base' "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [ ! -s "${FIX}/python3.stdin" ]
}

@test "trailing garbage in s fails closed with the named message" {
    weak_fix pi 100 1.5x
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"pi: suite time is not a non-negative number"* ]]
}

@test "seconds_to_ms itself rejects a non-decimal value" {
    run bash -c 'source "$1"; seconds_to_ms 1.5x' _ "${SCRIPT}"
    [ "${status}" -ne 0 ]
    run bash -c 'source "$1"; seconds_to_ms ""' _ "${SCRIPT}"
    [ "${status}" -ne 0 ]
    run bash -c 'source "$1"; seconds_to_ms 1.0005' _ "${SCRIPT}"
    [ "${output}" = "1001" ]
}

# planned = jobs in slice k of the round-robin cosmic_ray_shard.py split (i % n == k over sorted keys).
planned_list() {
    # planned_list <K> prints the per-shard planned counts, space separated
    weak_fix pi "$1" 1
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    [ "${status}" -eq 0 ]
    python3 -I -c '
import json, sys
u = json.load(open(sys.argv[1]))
assert [x["k"] for x in u] == list(range(len(u)))
print(" ".join(str(x["planned"]) for x in u))
' "${PLAN_OUT}/units.json"
}

@test "planned counts for K=17 over 10 shards are 2x7 then 1x3" {
    [ "$(planned_list 17)" = "2 2 2 2 2 2 2 1 1 1" ]
}

@test "planned counts sum to K" {
    for k in 1 9 10 11 99 1000 6001; do
        counts="$(planned_list "${k}")"
        [ "$(printf '%s\n' "${counts}" | awk '{ s = 0; for (i = 1; i <= NF; i++) s += $i; print s }')" = "${k}" ]
    done
}

@test "planned counts for K=0 are all 0" {
    [ "$(planned_list 0)" = "0 0 0 0 0 0 0 0 0 0" ]
}

@test "planned counts when K divides n evenly are equal" {
    [ "$(planned_list 20)" = "2 2 2 2 2 2 2 2 2 2" ]
}

@test "planned counts for K smaller than n give 1 then 0" {
    [ "$(planned_list 3)" = "1 1 1 0 0 0 0 0 0 0" ]
}

@test "planned counts follow n when K*s pushes n above 10" {
    weak_fix pi 6600 1
    PY_TEST_DIRS=pi run bash "${SCRIPT}" base </dev/null
    run python3 -I -c '
import json, sys
u = json.load(open(sys.argv[1]))
assert len(u) == 11 and {x["n"] for x in u} == {11}
assert [x["planned"] for x in u] == [600] * 11
' "${PLAN_OUT}/units.json"
    [ "${status}" -eq 0 ]
}

@test "diff rows carry no planned key" {
    prune_out pi 0 5 5
    run bash "${SCRIPT}" base pi </dev/null
    [ "$(cat "${PLAN_OUT}/units.json")" = '[{"dir":"pi","k":0,"n":1,"mode":"diff"}]' ]
}

# Six weakening dirs at 40 shards (240) plus one dir sized to ${1} shards: K*s/600 = ${1}.
matrix_dirs() {
    # matrix_dirs <last-dir-K>
    local d
    for d in d1 d2 d3 d4 d5 d6; do
        weak_fix "${d}" 10000 10
    done
    weak_fix d7 "$1" 1
    export PY_TEST_DIRS="d1 d2 d3 d4 d5 d6 d7"
}

@test "a matrix of exactly 256 units is green" {
    matrix_dirs 9600
    run bash "${SCRIPT}" base </dev/null
    [ "${status}" -eq 0 ]
    run python3 -I -c 'import json,sys; assert len(json.load(open(sys.argv[1])))==256' "${PLAN_OUT}/units.json"
    [ "${status}" -eq 0 ]
}

@test "a matrix of 257 units is red, names the limit and writes no units.json" {
    matrix_dirs 9601
    run bash "${SCRIPT}" base </dev/null
    [ "${status}" -eq 1 ]
    [[ "${output}" == *'error: plan needs 257 shards, over the 256-job matrix limit (ADR-0046)'* ]]
    [ ! -e "${PLAN_OUT}/units.json" ]
}

@test "the 256 cap counts diff rows beside weakening rows" {
    matrix_dirs 9600
    export PY_TEST_DIRS="d1 d2 d3 d4 d5 d6"
    prune_out e 0 151 9
    run bash "${SCRIPT}" base e </dev/null
    [ "${status}" -eq 0 ]
    weak_fix d7 9600 1
    prune_out e 0 1 1
    export PY_TEST_DIRS="d1 d2 d3 d4 d5 d6 d7"
    run bash "${SCRIPT}" base e </dev/null
    [ "${status}" -eq 1 ]
    [[ "${output}" == *'plan needs 257 shards'* ]]
}
