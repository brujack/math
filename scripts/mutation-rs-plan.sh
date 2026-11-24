#!/usr/bin/env bash
# Plans cargo-mutants shards per Rust crate and prints them as one JSON array.
#
# Usage: mutation-rs-plan.sh <base-ref> <crate-dir>...   (PR gate: changed-line mutants)
#        mutation-rs-plan.sh --whole <crate-dir>...      (monthly sweep: every mutant)
#        Run from the repo root.
#
# Per crate, K is the number of mutants `cargo mutants --list --json` reports (with
# `--in-diff` of the PR diff in diff mode). K > 0 becomes n = ceil(K/75) round-robin
# shards; shard k holds ceil((K-k)/n) mutants. Units go to stdout as one compact line,
# [{"crate","slug","k","n","count"}], `[]` when none. A plan of more than 256 shards in
# total is red (the GitHub matrix limit, ADR-0046).
#
# Diff mode: an empty diff, a failed diff or a failed or non-array listing prints
# `red: <crate> - <reason>` to stderr; the other crates are still planned, no units are
# printed, and the exit is 1. --whole: the same faults become one unit per crate,
# {"slug":"<name>-plan","k":0,"n":0,"count":0,"fault":"<cause>"}, so the sweep can
# report them red without failing the plan; the exit stays 0. Exit 2 on bad usage.

readonly SHARD_SIZE=75
readonly MATRIX_LIMIT=256

_usage() {
    printf 'Usage: %s (<base-ref> | --whole) <crate-dir>...\n' "${0##*/}" >&2
}

# Prints `red: <crate> - <reason>` to stderr and returns 1.
_red() {
    printf 'red: %s - %s\n' "$1" "$2" >&2
    return 1
}

# _emit_fault <units-file> <dir> <message>: one fault unit line.
_emit_fault() {
    jq -nc --arg crate "$2" --arg slug "${2##*/}-plan" --arg fault "$3" \
        '{crate: $crate, slug: $slug, k: 0, n: 0, count: 0, fault: $fault}' >>"$1"
}

# _list_count <dir> <listing-file> <diff-file-or-empty>
# Runs the listing with the crate as cwd. Prints K on stdout. Returns 1 when the listing
# command failed, 2 when it printed no mutants-array (non-array stdout), 0 otherwise.
_list_count() {
    local dir="$1" listing="$2" diff_file="$3"
    local args=(mutants --list --json)
    [[ -n "${diff_file}" ]] && args+=(--in-diff "${diff_file}")

    (cd "${dir}" && cargo "${args[@]}") >"${listing}" || return 1
    if [[ ! -s "${listing}" ]]; then
        printf '0\n'
        return 0
    fi
    jq -e 'if type == "array" then length else error end' "${listing}" 2>/dev/null || return 2
}

# plan_crate <script-dir> <base-ref-or-empty> <tmp> <index> <units-file> <crate-dir>
# An empty base-ref means --whole. Returns 1 for a diff-mode red.
plan_crate() {
    local script_dir="$1" base_ref="$2" tmp="$3" index="$4" units="$5"
    local dir="${6%/}"
    local name="${dir##*/}"
    local diff_file=""
    local listing="${tmp}/${index}.json"

    if [[ -n "${base_ref}" ]]; then
        # cargo runs with the crate as cwd, so hand it an absolute path.
        diff_file="${tmp}/${index}.diff"
        if ! "${script_dir}/mutation-pr-diff.sh" "${base_ref}" "${dir}" "${diff_file}"; then
            _red "${dir}" "diff failed"
            return 1
        fi
        if [[ ! -s "${diff_file}" ]]; then
            _red "${dir}" "diff empty"
            return 1
        fi
    fi

    local k rc
    k="$(_list_count "${dir}" "${listing}" "${diff_file}")"
    rc="$?"
    if [[ "${rc}" -ne 0 ]]; then
        if [[ -n "${base_ref}" ]]; then
            _red "${dir}" "mutant listing failed"
            return 1
        fi
        if [[ "${rc}" -eq 1 ]]; then
            _emit_fault "${units}" "${dir}" "mutant listing failed"
        else
            _emit_fault "${units}" "${dir}" "mutant listing is not a JSON array"
        fi
        return 0
    fi

    if [[ "${k}" -eq 0 ]]; then
        if [[ -n "${base_ref}" ]]; then
            printf 'plan: %s K=0 (no mutants on changed lines)\n' "${dir}" >&2
        else
            _emit_fault "${units}" "${dir}" "no mutants listed"
        fi
        return 0
    fi

    local n=$(((k + SHARD_SIZE - 1) / SHARD_SIZE))
    printf 'plan: %s K=%s n=%s per-shard=%s\n' "${dir}" "${k}" "${n}" "$(((k + n - 1) / n))" >&2
    local shard
    for ((shard = 0; shard < n; shard++)); do
        jq -nc --arg crate "${dir}" --arg slug "${name}-${shard}" \
            --argjson k "${shard}" --argjson n "${n}" --argjson count "$(((k - shard + n - 1) / n))" \
            '{crate: $crate, slug: $slug, k: $k, n: $n, count: $count}' >>"${units}"
    done
}

main() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 2

    local base_ref="${1-}"
    if [[ -z "${base_ref}" || ( "${base_ref}" == -* && "${base_ref}" != "--whole" ) ]]; then
        _usage
        return 2
    fi
    shift
    if [[ "${base_ref}" == "--whole" ]]; then
        base_ref=""
    fi
    if [[ "$#" -eq 0 ]]; then
        _usage
        return 2
    fi

    (
        local tmp
        tmp="$(mktemp -d)" || exit 1
        tmp="$(cd "${tmp}" && pwd)" || exit 1
        trap 'rm -rf -- "${tmp}"' EXIT
        local units="${tmp}/units.jsonl"
        : >"${units}"

        local index=0 any_red=0 dir
        for dir in "$@"; do
            index=$((index + 1))
            plan_crate "${script_dir}" "${base_ref}" "${tmp}" "${index}" "${units}" "${dir}" || any_red=1
        done
        if [[ "${any_red}" -ne 0 ]]; then
            exit 1
        fi

        local total
        # Each crate's shards all carry its n, so count n once per crate, at shard 0.
        total="$(jq -s '[.[] | select(.k == 0) | .n] | add // 0' "${units}")" || exit 1
        if [[ "${total}" -gt "${MATRIX_LIMIT}" ]]; then
            printf 'error: plan needs %s shards, over the %s-job matrix limit (ADR-0046)\n' \
                "${total}" "${MATRIX_LIMIT}" >&2
            exit 1
        fi
        jq -sc '.' "${units}" || exit 1
    )
    return "$?"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit "$?"
fi
