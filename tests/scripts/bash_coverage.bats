#!/usr/bin/env bats
# Regression coverage for scripts/run-bash-coverage.sh's INCLUDE_FILES
# predicate (ported from dotfiles/scripts/run-bash-coverage.sh @ 67417bc —
# see the header comment there for the origin commit and this repo's
# divergences). Mirrors dotfiles/tests/scripts/unit.bats's predicate tests
# and ai-config/tests/coverage_tracer.bats's structure.
#
# No PATH-based git mock is loaded here (checked: tests/mocks/git exists but
# load_mocks() is opt-in per-test, not global) — --list-sources is exercised
# directly against the real repo's tracked files, not through a PATH strip.

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    SCRIPT="${REPO_ROOT}/scripts/run-bash-coverage.sh"
}

# Independently re-derives the expected instrumented set via the same
# predicate the script uses, so this test does not simply assert "whatever
# the script currently prints" — a regression that narrows the glob would
# narrow both sides identically only if this list is hand-written here too.
_expected_sources() {
    env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git -C "${REPO_ROOT}" ls-files \
        'scripts/*.sh' '*/install_deps.sh' '*/*/install_deps.sh' \
        'scripts/pre-push' 'scripts/pre-commit' 'scripts/commit-msg' \
        | grep -v '^scripts/bash-tracer\.sh$' \
        | sort
}

@test "--list-sources output is non-empty before any loop" {
    run bash "${SCRIPT}" --list-sources
    [ "${status}" -eq 0 ]
    [ -n "${output}" ]
}

@test "--list-sources includes every predicate-matched tracked file" {
    local expected actual missing=0
    expected="$(_expected_sources)"
    [ -n "${expected}" ]

    run bash "${SCRIPT}" --list-sources
    [ "${status}" -eq 0 ]
    actual="${output}"

    while IFS= read -r _rel; do
        [[ -z "${_rel}" ]] && continue
        if [[ "${actual}" != *"${_rel}"* ]]; then
            printf "missing from --list-sources: %s\n" "${_rel}" >&2
            missing=1
        fi
    done <<< "${expected}"

    [ "${missing}" -eq 0 ]
}

@test "--list-sources includes all three extensionless hooks" {
    run bash "${SCRIPT}" --list-sources
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"scripts/pre-push"* ]]
    [[ "${output}" == *"scripts/pre-commit"* ]]
    [[ "${output}" == *"scripts/commit-msg"* ]]
}

@test "--list-sources includes install_deps.sh at the top-level sub-project depth" {
    run bash "${SCRIPT}" --list-sources
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"amicable/install_deps.sh"* ]]
}

@test "--list-sources includes install_deps.sh at the nested <name>-rs/ depth" {
    run bash "${SCRIPT}" --list-sources
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"amicable/amicable-rs/install_deps.sh"* ]]
}

@test "--list-sources includes install_deps.sh entries at every tracked nesting depth, derived not hardcoded" {
    local expected_count actual_count
    expected_count=$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git -C "${REPO_ROOT}" ls-files '*/install_deps.sh' '*/*/install_deps.sh' | wc -l | tr -d '[:space:]')
    # This repo's own Makefile SHELL_SOURCES comment records 19 install_deps.sh
    # scripts across both nesting depths as of the port — asserted here as a
    # floor rather than an exact literal, so the test does not need editing
    # every time a new sub-project (and its install_deps.sh) is added.
    [ "${expected_count}" -ge 19 ]

    run bash "${SCRIPT}" --list-sources
    [ "${status}" -eq 0 ]
    actual_count=$(printf '%s\n' "${output}" | grep -c 'install_deps\.sh$')
    [ "${actual_count}" -eq "${expected_count}" ]
}

@test "--list-sources excludes tests/helpers/common.bash" {
    run bash "${SCRIPT}" --list-sources
    [ "${status}" -eq 0 ]
    [[ "${output}" != *"tests/helpers/common.bash"* ]]
}

@test "--list-sources excludes scripts/bash-tracer.sh" {
    run bash "${SCRIPT}" --list-sources
    [ "${status}" -eq 0 ]
    [[ "${output}" != *"scripts/bash-tracer.sh"* ]]
}

@test "--list-sources count matches the derived predicate count exactly" {
    local expected_count actual_count
    expected_count=$(_expected_sources | grep -c .)

    run bash "${SCRIPT}" --list-sources
    [ "${status}" -eq 0 ]
    actual_count=$(printf '%s\n' "${output}" | grep -c .)

    [ "${actual_count}" -eq "${expected_count}" ]
}

@test "--count-coverable requires a file argument" {
    run bash "${SCRIPT}" --count-coverable
    [ "${status}" -eq 2 ]
}

@test "--count-coverable on scripts/ci-gate.sh returns a non-zero count" {
    run bash "${SCRIPT}" --count-coverable "${REPO_ROOT}/scripts/ci-gate.sh"
    [ "${status}" -eq 0 ]
    [ "${output}" -gt 0 ]
}

@test "--count-coverable on a missing file exits 2" {
    run bash "${SCRIPT}" --count-coverable "${REPO_ROOT}/scripts/does-not-exist.sh"
    [ "${status}" -eq 2 ]
}

@test "--file-coverage exits 2 with no arguments" {
    run bash "${SCRIPT}" --file-coverage
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"--file-coverage"* ]]
}

@test "--file-coverage exits 2 with only a source file argument" {
    run bash "${SCRIPT}" --file-coverage "${REPO_ROOT}/scripts/ci-gate.sh"
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"--file-coverage"* ]]
}

# The union is what makes the denominator honest — proves the union actually
# unions, the single most load-bearing behaviour in _file_coverage_report.
# Ported fixture/assertions from ai-config/tests/coverage_tracer.bats (itself
# ported from dotfiles), unchanged: this behaviour is repo-agnostic.
@test "--file-coverage unions a traced line the heuristic excluded, and reports it as a disagreement" {
    cat > "${BATS_TEST_TMPDIR}/arrbug.sh" <<'FIXTURE'
#!/usr/bin/env bash
arr=(
  a
)
echo "${arr[@]}"
FIXTURE
    {
        printf '%s:2\n' "${BATS_TEST_TMPDIR}/arrbug.sh"
        printf '%s:3\n' "${BATS_TEST_TMPDIR}/arrbug.sh"
        printf '%s:5\n' "${BATS_TEST_TMPDIR}/arrbug.sh"
    } > "${BATS_TEST_TMPDIR}/arrbug_trace.txt"

    run bash "${SCRIPT}" --file-coverage \
        "${BATS_TEST_TMPDIR}/arrbug.sh" "${BATS_TEST_TMPDIR}/arrbug_trace.txt"
    [ "${status}" -eq 0 ]
    [ "${#lines[@]}" -eq 3 ]
    # covered: 3 distinct traced lines (2, 3, 5).
    [ "${lines[0]}" = "3" ]
    # coverable: union of heuristic [2, 5] and traced [2, 3, 5] is [2, 3, 5] = 3.
    [ "${lines[1]}" = "3" ]
    # disagreement: the only line the heuristic excluded but the trace emitted.
    [ "${lines[2]}" = "3" ]
}

@test "--file-coverage reports no disagreement when the trace matches the heuristic" {
    cat > "${BATS_TEST_TMPDIR}/clean.sh" <<'FIXTURE'
#!/usr/bin/env bash
a=1
b=2
FIXTURE
    {
        printf '%s:2\n' "${BATS_TEST_TMPDIR}/clean.sh"
        printf '%s:3\n' "${BATS_TEST_TMPDIR}/clean.sh"
    } > "${BATS_TEST_TMPDIR}/clean_trace.txt"

    run bash "${SCRIPT}" --file-coverage \
        "${BATS_TEST_TMPDIR}/clean.sh" "${BATS_TEST_TMPDIR}/clean_trace.txt"
    [ "${status}" -eq 0 ]
    [ "${#lines[@]}" -eq 2 ]
    [ "${lines[0]}" = "2" ]
    [ "${lines[1]}" = "2" ]
}

# Regression (ported from dotfiles/tests/scripts/unit.bats @ 67417bc): every
# inspection flag exits, so an unrecognised one used to fall straight through
# to the full `bats --recursive` tracer run — minutes of work that reads as a
# hang, triggered by a single mistyped character. It happened during
# dotfiles' own development of this guard. The guard must reject the typo and
# must NOT reject --json, which legitimately continues to the main run.
@test "run-bash-coverage.sh rejects an unknown flag instead of running the suite" {
    run bash "${SCRIPT}" --definitely-not-a-flag
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"unknown option"* ]]
    [[ "${output}" == *"--definitely-not-a-flag"* ]]
    # It must not have started a run: the tracer announces itself first.
    [[ "${output}" != *"Running"*"tests with coverage tracer"* ]]
}

@test "run-bash-coverage.sh rejects a near-miss typo of a real flag" {
    run bash "${SCRIPT}" --list-source
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"unknown option"* ]]
}

# ── --check-missing: the tracked-but-absent warning ─────────────────────────
# The original `[[ ! -f "${src_file}" ]] && continue` in the per-file loop
# dropped a tracked-but-absent file from the run with no output at all — the
# file vanishes from both numerator and denominator, so the percentage is
# unchanged rather than lowered. That is the exact invisible-shrinkage class
# this whole script exists to eliminate, surviving inside its own fix.
# Testable via --check-missing rather than a full tracer pass, which the loop
# this guards takes minutes to reach.
@test "run-bash-coverage.sh --check-missing warns on stderr and exits 1 for an absent file" {
    run bash "${SCRIPT}" --check-missing "${BATS_TEST_TMPDIR}/nonexistent-tracked.sh"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"nonexistent-tracked.sh"* ]]
    [[ "${output}" == *"tracked but absent"* ]]
}

@test "run-bash-coverage.sh --check-missing is silent and exits 0 for a present file" {
    printf 'a=1\n' > "${BATS_TEST_TMPDIR}/present.sh"
    run bash "${SCRIPT}" --check-missing "${BATS_TEST_TMPDIR}/present.sh"
    [ "${status}" -eq 0 ]
    [ -z "${output}" ]
}

@test "run-bash-coverage.sh --check-missing exits 2 with no file argument" {
    run bash "${SCRIPT}" --check-missing
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"--check-missing"* ]]
}

# The warning must be non-fatal — the per-file loop calls the same function
# with `|| continue`, never `|| exit`, so one absent file shrinks the
# denominator but does not end the run. --check-missing's own exit code IS
# the function's return code (the flag block is just `_warn_if_source_missing
# "${2}"; exit $?`), so a plain 1 here — not a crash, not a hard process
# exit — proves the function returns rather than terminates the script.
# Confirmed structurally too: the real loop line is grepped directly, so a
# future edit that turns the skip into a hard `exit` fails this test.
@test "run-bash-coverage.sh's per-file loop treats a missing source as a non-fatal skip" {
    run bash "${SCRIPT}" --check-missing "${BATS_TEST_TMPDIR}/missing-for-loop-check.sh"
    [ "${status}" -eq 1 ]
    grep -qF '_warn_if_source_missing "${src_file}" || continue' "${SCRIPT}"
}

# ── unterminated-region errors name the opening line and delimiter ──────────
# The error used to identify neither the opening line nor the delimiter, so a
# reader had to re-scan the whole file by hand to find the unterminated
# region — and it aborts the whole run (and therefore CI) when it fires.
@test "run-bash-coverage.sh names the opening line and delimiter for an unterminated heredoc" {
    printf '#!/usr/bin/env bash\na=1\ncat <<'"'"'PAYLOAD'"'"'\nfoo\n' > "${BATS_TEST_TMPDIR}/untermhd2.sh"
    run bash "${SCRIPT}" --count-coverable "${BATS_TEST_TMPDIR}/untermhd2.sh"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"unterminated heredoc"* ]]
    [[ "${output}" == *"opened at line 3"* ]]
    [[ "${output}" == *"delimiter 'PAYLOAD'"* ]]
}

@test "run-bash-coverage.sh names the opening line for an unterminated python3 -c block" {
    printf '#!/usr/bin/env bash\na=1\n_x=$(python3 -c "\nimport json\n' > "${BATS_TEST_TMPDIR}/untermpyc2.sh"
    run bash "${SCRIPT}" --count-coverable "${BATS_TEST_TMPDIR}/untermpyc2.sh"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"unterminated python3 -c block"* ]]
    [[ "${output}" == *"opened at line 3"* ]]
}

# ── --check-red-suite: the red-suite guard ──────────────────────────────────
# The tracer refuses to report a coverage figure computed over a suite that
# did not pass — --check-red-suite exercises that refusal directly, without
# running the full suite under the tracer to reach it.
@test "run-bash-coverage.sh --check-red-suite proceeds silently for a green status" {
    printf '1..2\nok 1 a\nok 2 b\n' > "${BATS_TEST_TMPDIR}/green.log"
    run bash "${SCRIPT}" --check-red-suite 0 "${BATS_TEST_TMPDIR}/green.log"
    [ "${status}" -eq 0 ]
    [ -z "${output}" ]
}

@test "run-bash-coverage.sh --check-red-suite refuses a red status, naming the count and the failing tests" {
    printf '1..3\nok 1 a\nnot ok 2 b\nnot ok 3 c\n' > "${BATS_TEST_TMPDIR}/red.log"
    run bash "${SCRIPT}" --check-red-suite 1 "${BATS_TEST_TMPDIR}/red.log"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"2 test(s) not ok"* ]]
    [[ "${output}" == *"not ok 2 b"* ]]
    [[ "${output}" == *"not ok 3 c"* ]]
}

@test "run-bash-coverage.sh --check-red-suite exits 2 with fewer than two arguments" {
    run bash "${SCRIPT}" --check-red-suite 1
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"--check-red-suite"* ]]
}

@test "run-bash-coverage.sh --check-red-suite exits 2 on a nonexistent log file" {
    run bash "${SCRIPT}" --check-red-suite 1 "${BATS_TEST_TMPDIR}/no-such-log.txt"
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"no such readable log file"* ]]
}

# --- covalias: a hook copy run outside REPO_ROOT counts against the tracked file ---
# tests/helpers/push_gates.bash runs scripts/pre-push from <tmp>/covalias/scripts/pre-push.
# A trace there is attributed to the tracked file of the same relative path and counts only
# on lines the real file's static heuristic counts; a covalias path that is not a tracked
# file is ignored. Each fixture is its own git repo holding a copy of the runner, because
# the runner derives its REPO_ROOT from its own location and runs that repo's whole suite.

# _alias_fixture <dir> -- a git repo with the runner, the tracer and scripts/sample.sh (line 1
# a shebang, line 2 a comment, lines 3-5 commands); no test is written yet.
_alias_fixture() {
    local dir="$1"
    mkdir -p "${dir}/scripts" "${dir}/tests"
    cp "${REPO_ROOT}/scripts/run-bash-coverage.sh" "${REPO_ROOT}/scripts/bash-tracer.sh" "${dir}/scripts/"
    printf '#!/usr/bin/env bash\n# a comment the heuristic does not count\nx=1\ny=2\n: "${x}${y}"\n' > "${dir}/scripts/sample.sh"
    cp "${dir}/scripts/sample.sh" "${dir}/scripts/other.sh"
    env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git -C "${dir}" init -q -b master
}

# _alias_commit <dir> <bats body> -- writes tests/sample.bats around the body and commits it all.
_alias_commit() {
    local dir="$1"
    printf '#!/usr/bin/env bats\n@test "fixture" {\n%s\n}\n' "$2" > "${dir}/tests/sample.bats"
    env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null git -C "${dir}" add scripts tests
    env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null git -C "${dir}" \
        -c user.name=Test -c user.email=test@example.com commit -q -m fixture
}

# The bats body that copies <name> to <tmp>/covalias/scripts/<name> and runs the copy, optionally
# replacing line 2 of the copy with a command first.
_alias_body() { # <dir> <name> [replacement for line 2]
    local body
    body="$(printf '  mkdir -p "$BATS_TEST_TMPDIR/covalias/scripts"\n  cp "%s/scripts/%s" "$BATS_TEST_TMPDIR/covalias/scripts/%s"' "$1" "$2" "$2")"
    if [[ -n "${3:-}" ]]; then
        body+="$(printf '\n  sed -i.bak "2s|.*|%s|" "$BATS_TEST_TMPDIR/covalias/scripts/%s"' "$3" "$2")"
    fi
    body+="$(printf '\n  run bash "$BATS_TEST_TMPDIR/covalias/scripts/%s"\n  [ "$status" -eq 0 ]' "$2")"
    printf '%s' "${body}"
}

# _run_fixture <dir> -- runs the fixture's own copy of the runner; output in ${output}.
_run_fixture() {
    run env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null \
        bash "$1/scripts/run-bash-coverage.sh" < /dev/null
}

# _row_field <file name> <field> -- one column of that file's report row (2 covered, 3 coverable).
_row_field() {
    printf '%s\n' "${output}" | grep -E "^$1 " | awk -v f="$2" '{print $f}'
}

@test "covalias: a trace of a copy at covalias/<tracked path> counts exactly as a direct run of the file" {
    local alias_dir="${BATS_TEST_TMPDIR}/fixture-alias" direct_dir="${BATS_TEST_TMPDIR}/fixture-direct"
    local alias_covered alias_coverable direct_covered direct_coverable
    _alias_fixture "${alias_dir}"
    _alias_commit "${alias_dir}" "$(_alias_body "${alias_dir}" sample.sh)"
    _alias_fixture "${direct_dir}"
    _alias_commit "${direct_dir}" "$(printf '  run bash "%s/scripts/sample.sh"\n  [ "$status" -eq 0 ]' "${direct_dir}")"
    _run_fixture "${alias_dir}"
    [ "$status" -eq 0 ]
    alias_covered="$(_row_field sample.sh 2)"
    alias_coverable="$(_row_field sample.sh 3)"
    _run_fixture "${direct_dir}"
    [ "$status" -eq 0 ]
    direct_covered="$(_row_field sample.sh 2)"
    direct_coverable="$(_row_field sample.sh 3)"
    [ "${direct_covered}" -gt 0 ]
    [ "${alias_covered}" -eq "${direct_covered}" ]
    [ "${alias_coverable}" -eq "${direct_coverable}" ]
}

@test "covalias: a directly run file and an aliased file both report covered lines" {
    local dir="${BATS_TEST_TMPDIR}/fixture-both"
    _alias_fixture "${dir}"
    _alias_commit "${dir}" "$(printf '  run bash "%s/scripts/sample.sh"\n  [ "$status" -eq 0 ]\n%s' "${dir}" "$(_alias_body "${dir}" other.sh)")"
    _run_fixture "${dir}"
    [ "$status" -eq 0 ]
    [ "$(_row_field sample.sh 2)" -gt 0 ]
    [ "$(_row_field other.sh 2)" -gt 0 ]
}

@test "covalias: a covalias path that is not a tracked file is ignored" {
    local dir="${BATS_TEST_TMPDIR}/fixture-ghost"
    _alias_fixture "${dir}"
    # Untracked, but present on disk, so only the instrumented-set membership check can drop it.
    cp "${dir}/scripts/sample.sh" "${dir}/scripts/ghost.sh"
    _alias_commit "${dir}" "$(_alias_body "${dir}" ghost.sh)"
    env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git -C "${dir}" rm -q --cached scripts/ghost.sh
    [ -f "${dir}/scripts/ghost.sh" ]
    _run_fixture "${dir}"
    # Nothing tracked was traced, so the run refuses for lack of trace data.
    [ "$status" -eq 1 ]
    [[ "${output}" == *"no trace data produced"* ]]
}

@test "covalias: an alias trace on a non-coverable line adds to neither covered nor coverable" {
    local plain="${BATS_TEST_TMPDIR}/fixture-plain" extra="${BATS_TEST_TMPDIR}/fixture-extra"
    local covered_plain coverable_plain
    _alias_fixture "${plain}"
    _alias_commit "${plain}" "$(_alias_body "${plain}" sample.sh)"
    _alias_fixture "${extra}"
    _alias_commit "${extra}" "$(_alias_body "${extra}" sample.sh ': extra')"
    _run_fixture "${plain}"
    [ "$status" -eq 0 ]
    covered_plain="$(_row_field sample.sh 2)"
    coverable_plain="$(_row_field sample.sh 3)"
    [ "${covered_plain}" -gt 0 ]
    _run_fixture "${extra}"
    [ "$status" -eq 0 ]
    [ "$(_row_field sample.sh 2)" -eq "${covered_plain}" ]
    [ "$(_row_field sample.sh 3)" -eq "${coverable_plain}" ]
}
