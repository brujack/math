#!/usr/bin/env bats

load '../helpers/common'

@test "make test-hooks recipe calls bats --recursive tests/" {
    run make -C "${REPO_ROOT}" -n test-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"bats --recursive tests/"* ]]
}

@test "make install-hooks recipe links pre-commit hook" {
    run make -C "${REPO_ROOT}" -n install-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"scripts/pre-commit"* ]]
}

@test "make install-hooks recipe links pre-push hook" {
    run make -C "${REPO_ROOT}" -n install-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"scripts/pre-push"* ]]
}

@test "install-hooks and test-hooks are declared .PHONY" {
    run grep -E "^\.PHONY" "${REPO_ROOT}/Makefile"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"install-hooks"* ]]
    [[ "${output}" == *"test-hooks"* ]]
}

# Both lists are derived from `git ls-files`, never hardcoded: an omitted crate
# would be absent from the loop rather than failing it, so a hand-list turns a
# real gap into a silent pass (tdd.md "Coverage Denominators"). The non-empty
# assertion before each loop guards the same class from the other direction --
# an empty derived list makes every `for` body vacuously true.

@test "every Rust crate Makefile's test target depends on lint" {
    local makefiles missing=""
    makefiles="$(cd "${REPO_ROOT}" && git ls-files '*-rs/Makefile')"
    [ -n "${makefiles}" ]

    while IFS= read -r mf; do
        [[ -z "${mf}" ]] && continue
        local prereqs
        prereqs="$(grep -m1 -E '^test:' "${REPO_ROOT}/${mf}" | sed 's/^test:[[:space:]]*//')"
        case " ${prereqs} " in
        *" lint "*) ;;
        *) missing="${missing}${mf} " ;;
        esac
    done <<< "${makefiles}"

    if [[ -n "${missing}" ]]; then
        printf 'test: target does not depend on lint in: %s\n' "${missing}" >&2
        return 1
    fi
}

# scripts/rust-check.sh lint mode runs `cargo machete` unguarded, so a workflow
# reaching lint -- directly or through `test: lint` -- fails without it
# installed. This invariant is coupled to the one above: satisfying that test
# without this one turns the crate's CI red instead of green.
@test "every Rust crate CI workflow installs cargo-machete" {
    local workflows missing=""
    workflows="$(cd "${REPO_ROOT}" && git ls-files '.github/workflows/*-rs.yml' | grep -v '/release-')"
    [ -n "${workflows}" ]

    while IFS= read -r wf; do
        [[ -z "${wf}" ]] && continue
        grep -qE '^[[:space:]]*run:[[:space:]]*cargo install cargo-machete' \
            "${REPO_ROOT}/${wf}" || missing="${missing}${wf} "
    done <<< "${workflows}"

    if [[ -n "${missing}" ]]; then
        printf 'cargo-machete not installed in: %s\n' "${missing}" >&2
        return 1
    fi
}

# The push path is what this pins, not the Makefile's aesthetics: pre-push
# invokes a root target when scripts/, tests/ or the Makefile change, and until
# this prerequisite existed that target ran bats without ever linting the shell.
# `make lint-hooks` had exactly one call site in the repo and it was CI. See
# code-standards.md: the requirement is that every changed component's lint
# runs on the push path.
#
# (A comment line must not START with the word shellcheck -- that is parsed as
# a directive, SC1072/SC1073. Caught by this very prerequisite on its first run.)
@test "root make test reaches shell lint" {
    run make -C "${REPO_ROOT}" -n test --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"shellcheck"* ]]
}

# Companion to the shell-lint assertion above. ruff.toml at the repo root
# already reaches every .py in the repo by ancestor discovery -- the config was
# never the gap, the invocation was. scripts/ and tests/ sat outside every
# gated scope and were linted by nothing, which math's own CLAUDE.md recorded
# as a known gap. `ruff check .` from the root needs no derived file list and
# so has no denominator to drift.
@test "root make lint reaches ruff" {
    run make -C "${REPO_ROOT}" -n lint --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff"* ]]
}

@test "root make test reaches ruff" {
    run make -C "${REPO_ROOT}" -n test --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff"* ]]
}

@test "root-scope Python is clean under the repo's own ruff config" {
    run make -C "${REPO_ROOT}" -n lint-python --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff check"* ]]
    [[ "${output}" == *"ruff format"* ]]
}

# Coupled to the target above, exactly as the cargo-machete assertion is coupled
# to `test: lint`. `lint-python` guards a missing ruff and returns 0 with a
# "skipping" notice -- correct locally, since `test` depends on it and the
# pre-push hook runs `test`, so a hard failure would lock a machine out of
# committing the change that installs ruff (ci.md). In CI that same guard makes
# the gate decorative: green having examined nothing. Verified by running
# `make lint-python` with ruff off PATH -- it prints "skipping" and exits 0.
@test "the workflow running root lint installs ruff" {
    run grep -E '^[[:space:]]*run: pip install .*ruff==' \
        "${REPO_ROOT}/.github/workflows/scripts.yml"
    [ "${status}" -eq 0 ]
}
