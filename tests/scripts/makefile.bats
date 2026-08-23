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
    run make -C "${REPO_ROOT}" -n lint RUFF=/usr/bin/true --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff check"* ]]
}

@test "root make test reaches ruff" {
    run make -C "${REPO_ROOT}" -n test RUFF=/usr/bin/true --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff check"* ]]
}

@test "lint-python runs both ruff check and ruff format" {
    run make -C "${REPO_ROOT}" -n lint-python RUFF=/usr/bin/true --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff check"* ]]
    [[ "${output}" == *"ruff format --check"* ]]
}

# The guard is tested rather than incidental, and it is why the three above
# force RUFF. `ifndef RUFF` is evaluated at parse time, so on a machine without
# ruff -- the bash-coverage CI job, for one -- `make -n` prints the skip notice
# instead of the recipe. That notice contains the word "ruff", so an assertion
# matching the bare substring passes while reporting the gate was SKIPPED.
# Caught by CI on this branch, not by review.
@test "lint-python skips with a remedy when ruff is absent" {
    run make -C "${REPO_ROOT}" -n lint-python RUFF= --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff not found"* ]]
    [[ "${output}" == *"pip install ruff=="* ]]
    [[ "${output}" != *"ruff check"* ]]
}

@test "the workflow running root lint installs ruff" {
    run grep -E '^[[:space:]]*run: pip install .*ruff==' \
        "${REPO_ROOT}/.github/workflows/scripts.yml"
    [ "${status}" -eq 0 ]
}

# ADR-0006: pin GitHub Actions to immutable SHA digests. A *branch* ref is the
# worst case -- it moves with no upstream release at all, so a compromised or
# simply changed action reaches CI with nothing to notice. This asserts the
# whole class rather than one action, because the next branch ref will not be
# dtolnay's. Local `./.github/workflows/*.yml` reusable-workflow calls carry no
# `@` and cannot be digest-pinned, so they never match.
@test "no workflow pins a third-party action to a mutable branch ref" {
    local refs bad=""
    refs="$(cd "${REPO_ROOT}" && git grep -hoE 'uses: [^ ]+@[A-Za-z0-9._/-]+' -- '.github/workflows/*.yml' \
        | sed 's/uses: //' | sort -u)"
    [ -n "${refs}" ]

    while IFS= read -r r; do
        [[ -z "${r}" ]] && continue
        case "${r##*@}" in
        stable | main | master | nightly | dev) bad="${bad}${r} " ;;
        esac
    done <<< "${refs}"

    if [[ -n "${bad}" ]]; then
        printf 'action(s) pinned to a mutable branch ref: %s\n' "${bad}" >&2
        return 1
    fi
}

# renovate.json must not extend a preset hosted in another repo. Renovate
# resolves `extends` at initRepo, BEFORE any dependency extraction, so a preset
# it cannot fetch throws config-validation and abandons the entire repository --
# silently, from the repo's point of view: no PRs, no dashboard, no error
# anywhere a maintainer looks. math is public and the shared preset lives in a
# private repo, so this repo extracted 0 of its 291 dependencies from
# 2026-05-18 until the preset was inlined. Reproduced: result config-validation
# in 207ms, versus a full extraction in 6578ms once inlined.
@test "renovate.json extends no cross-repo preset" {
    local bad
    bad="$(python3 -c "
import json
for e in json.load(open('${REPO_ROOT}/renovate.json')).get('extends', []):
    if not e.startswith('config:'):
        print(e)
")"
    if [[ -n "${bad}" ]]; then
        printf 'renovate.json extends a non-official preset, which is fetched at initRepo and aborts the repo if unreachable: %s\n' "${bad}" >&2
        return 1
    fi
}
