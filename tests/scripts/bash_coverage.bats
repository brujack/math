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
