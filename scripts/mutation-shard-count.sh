#!/usr/bin/env bash
# Compares a shard's cargo-mutants outcomes.json total_mutants with the count
# the planner expected for that shard.
#
# Usage: mutation-shard-count.sh <outcomes.json> <label> <count>
#
# Called by mutation-pr-run.sh --expect and by the monthly sweep `mutants` job.
# A missing file counts as 0 mutants tested (the recipe died before cargo-mutants
# wrote it). An unreadable file, or a total_mutants that is not a non-negative
# integer, prints `red: <label> cannot read total_mutants from <path>` to stdout
# and exits 1. A mismatch prints `red: <label> tested <M> mutants, plan expected
# <count>` to stdout and exits 1; a match prints nothing and exits 0. Bad usage
# (wrong argc, or a count that is not a positive integer) prints usage to stderr
# and exits 2.

readonly COUNT_PATTERN='^[1-9][0-9]*$'
# Strings, booleans, arrays and null make `floor` error, so jq -e fails them.
readonly TOTAL_FILTER='.total_mutants | select(. >= 0 and . == floor) | floor | @text'

# Succeeds only for exactly one JSON object with unique top-level keys. Adapted from
# _reject_ambiguous_outcomes in mutation-classify.sh: a second document or a repeated
# key would let a single jq pass read a different total than the file's author meant.
# Invalid JSON also fails here.
_is_single_object() {
    local file="${1}"
    local shape dup_key
    shape="$(jq -s 'length == 1 and (.[0] | type) == "object"' "${file}" 2>/dev/null)" || return 1
    [[ "${shape}" == "true" ]] || return 1
    # In --stream form a top-level key ends on a scalar or empty-container leaf event
    # (path length 1) or on the closing event of its container value (path length 2).
    dup_key="$(jq -n -r --stream '
        [inputs
         | select((length == 2 and (.[0] | length) == 1)
                  or (length == 1 and (.[0] | length) == 2))
         | .[0][0]]
        | group_by(.) | map(select(length > 1)) | (.[0][0] // empty) | tojson' "${file}" 2>/dev/null)" || return 1
    [[ -z "${dup_key}" ]]
}

# mutation_shard_count <outcomes.json> <label> <count>
mutation_shard_count() {
    if [[ "$#" -ne 3 || ! "${3}" =~ ${COUNT_PATTERN} ]]; then
        printf 'Usage: %s <outcomes.json> <label> <count>\n' "${0##*/}" >&2
        return 2
    fi
    local file="${1}" label="${2}" count="${3}"

    local tested=0
    if [[ -f "${file}" ]]; then
        if ! _is_single_object "${file}" || ! tested="$(jq -er "${TOTAL_FILTER}" "${file}" 2>/dev/null)"; then
            printf 'red: %s cannot read total_mutants from %s\n' "${label}" "${file}"
            return 1
        fi
    fi

    # String compare: both sides are canonical integers (COUNT_PATTERN forbids leading
    # zeros, jq prints integers plainly), and `-ne` would fail open on overflow.
    if [[ "${tested}" != "${count}" ]]; then
        printf 'red: %s tested %s mutants, plan expected %s\n' "${label}" "${tested}" "${count}"
        return 1
    fi
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
mutation_shard_count "$@"
