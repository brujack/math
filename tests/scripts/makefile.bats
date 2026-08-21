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
        grep -q 'cargo-machete' "${REPO_ROOT}/${wf}" || missing="${missing}${wf} "
    done <<< "${workflows}"

    if [[ -n "${missing}" ]]; then
        printf 'cargo-machete not installed in: %s\n' "${missing}" >&2
        return 1
    fi
}
