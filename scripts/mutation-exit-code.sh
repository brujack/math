#!/usr/bin/env bash
# Reads cargo-mutants' own exit code from <crate_dir>/mutants.out/exit-code.
#
# Usage: mutation-exit-code.sh <crate_dir>
#
# Prints the integer to stdout and exits 0. Otherwise prints one line
# `red: <crate_dir> - <reason>` to stderr and exits 1; with no argument it prints
# usage and exits 2. The file is the single
# source of truth for the PR run (mutation-pr-run.sh) and the monthly sweep
# (mutation-testing.yml): a missing file means the recipe died before
# cargo-mutants ran, and anything but a plain 0-999 integer is rejected because
# the classifier's `-eq` reads '' or text as 0 (green).

readonly EXIT_CODE_PATTERN='^(0|[1-9][0-9]{0,2})$'

# mutation_exit_code <crate_dir>
mutation_exit_code() {
    local dir="${1-}"
    if [[ -z "${dir}" ]]; then
        printf 'Usage: %s <crate_dir>\n' "${0##*/}" >&2
        return 2
    fi

    local code_file="${dir}/mutants.out/exit-code"
    if [[ ! -f "${code_file}" ]]; then
        printf 'red: %s - no mutants.out/exit-code\n' "${dir}" >&2
        return 1
    fi

    local code
    code="$(<"${code_file}")"
    if [[ ! "${code}" =~ ${EXIT_CODE_PATTERN} ]]; then
        printf "red: %s - mutants.out/exit-code '%s' is not an integer\n" "${dir}" "${code}" >&2
        return 1
    fi

    printf '%s\n' "${code}"
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
mutation_exit_code "$@"
