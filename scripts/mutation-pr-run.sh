#!/usr/bin/env bash
# Runs `make mutants-diff` on each Rust crate a PR touches and owns every red rule.
#
# Usage: mutation-pr-run.sh <base-ref> [--min-caught N] <crate-dir>...   (run from repo root)
#
# Per crate: build the crate-relative PR diff, run `make -C <dir> mutants-diff`
# on it, then classify the exit code in <dir>/mutants.out/exit-code with limit 0
# (any missed mutant is red) and N as the minimum caught count. A crate selected
# with an empty diff, or one that leaves no exit-code file, is red: both mean the
# run measured nothing. Every verdict goes to stdout; a red crate does not stop
# the loop. Exit 0 when all are green, 1 when any is red, 2 on bad usage.

readonly COUNT_PATTERN='^(0|[1-9][0-9]{0,8})$'

_usage() {
    printf 'Usage: %s <base-ref> [--min-caught N] <crate-dir>...\n' "${0##*/}" >&2
}

# Prints `red: <crate> - <reason>` to stdout and returns 1. Every caller follows it with
# `return 1` itself, so the verdict line is the only effect; the status is not consumed.
_red() {
    printf 'red: %s - %s\n' "$1" "$2"
    return 1
}

# run_crate <script-dir> <base-ref> <min-caught-or-empty> <tmp> <index> <crate-dir>
run_crate() {
    local script_dir="$1"
    local base_ref="$2"
    local min_caught="$3"
    local tmp="$4"
    local index="$5"
    local dir="${6%/}"
    local diff_file="${tmp}/${index}.diff"

    if ! "${script_dir}/mutation-pr-diff.sh" "${base_ref}" "${dir}" "${diff_file}"; then
        _red "${dir}" "diff failed"
        return 1
    fi
    if [[ ! -s "${diff_file}" ]]; then
        _red "${dir}" "selected but diff empty"
        return 1
    fi

    # Clear leftovers so a make that never reaches its recipe cannot pass on a stale run.
    if ! rm -rf -- "${dir}/mutants.out"; then
        _red "${dir}" "cannot clear mutants.out"
        return 1
    fi

    # A failing make is judged by mutants.out/exit-code below, not by its own status.
    make -C "${dir}" mutants-diff DIFF="${diff_file}" || true

    # The shared reader owns the missing-file and integer rules; its one red line comes
    # back on stderr, so fold it into stdout where every verdict of this script goes.
    local code
    if ! code="$(bash "${script_dir}/mutation-exit-code.sh" "${dir}" 2>&1)"; then
        printf '%s\n' "${code}"
        return 1
    fi

    local classify_args=("${code}" "${dir}/mutants.out/outcomes.json" "${dir}" 0)
    if [[ -n "${min_caught}" ]]; then
        classify_args+=("${min_caught}")
    fi
    "${script_dir}/mutation-classify.sh" "${classify_args[@]}" 2>&1
}

main() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 2

    local base_ref="${1-}"
    if [[ -z "${base_ref}" || "${base_ref}" == -* ]]; then
        _usage
        return 2
    fi
    shift

    local min_caught=""
    local dirs=()
    while [[ $# -gt 0 ]]; do
        if [[ "$1" == "--min-caught" ]]; then
            if [[ $# -lt 2 || ! "$2" =~ ${COUNT_PATTERN} ]]; then
                _usage
                return 2
            fi
            min_caught="$2"
            shift 2
        elif [[ "$1" == -* ]]; then
            _usage
            return 2
        else
            dirs+=("$1")
            shift
        fi
    done
    if [[ "${#dirs[@]}" -eq 0 ]]; then
        _usage
        return 2
    fi

    (
        local tmp
        tmp="$(mktemp -d)" || exit 1
        tmp="$(cd "${tmp}" && pwd)" || exit 1
        trap 'rm -rf -- "${tmp}"' EXIT

        local index=0
        local any_red=0
        local dir
        for dir in "${dirs[@]}"; do
            index=$((index + 1))
            run_crate "${script_dir}" "${base_ref}" "${min_caught}" "${tmp}" "${index}" "${dir}" || any_red=1
        done
        exit "${any_red}"
    )
    return "$?"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit "$?"
fi
