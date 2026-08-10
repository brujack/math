#!/usr/bin/env bats
# Regression coverage for scripts/run-bash-coverage.sh's INCLUDE_FILES
# predicate (ported from dotfiles/scripts/run-bash-coverage.sh @ c27cc4e —
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
