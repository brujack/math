#!/usr/bin/env bash
# Plans the Python PR mutation gate: one plan line per project dir, plus the shard units.
#
# Usage: mutation-pr-plan-python.sh <base-sha> [<dir>...]   (run from repo root)
#
# Writes plan.txt and units.json to ${PLAN_OUT:-.}; appends a table to ${GITHUB_STEP_SUMMARY} when set.
# plan.txt holds exactly one line per dir, `<dir>\t<green|red>\t<text>`; the verdict script
# (mutation-pr-verdict-python.sh) parses it, so the green/red texts below are a pinned contract:
#   `<K> mutants in <n> shards`, `0 mutants on changed lines`, `lines 0`, or a flattened error.
# units.json is [{"dir":..,"k":..,"n":..}] for green dirs with K > 0 only; [] when none.
# Zero dirs is valid (an empty plan and []), so the caller never special-cases "nothing changed".

readonly SHARD_SIZE=150
readonly MAX_SHARDS=10
readonly TAB=$'\t'

# Overridable so tests can substitute the diff writer.
readonly DIFF_SCRIPT="${MUTATION_PR_DIFF:-$(dirname "${BASH_SOURCE[0]}")/mutation-pr-diff.sh}"

# Shard count: min(MAX_SHARDS, max(1, ceil(K / SHARD_SIZE))).
shard_count() {
    local kept="$1" n
    n=$(((kept + SHARD_SIZE - 1) / SHARD_SIZE))
    ((n < 1)) && n=1
    ((n > MAX_SHARDS)) && n="${MAX_SHARDS}"
    printf '%s\n' "${n}"
}

# Joins lines with " | " and drops CR so multi-line stderr is one plan line.
flatten() {
    local text="$1"
    text="${text//$'\r'/}"
    text="${text//$'\n'/ | }"
    printf '%s\n' "${text}"
}

# JSON string escape for the dir name (fixed ASCII in practice; quoted anyway).
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    printf '%s' "${s}"
}

# Plans one dir. Sets PLAN_LINE (without dir) and appends to UNITS.
# Full stderr goes to the summary through SUMMARY_BODY.
plan_dir() {
    local base="$1" dir="$2"
    local diff_file="${WORK}/${dir//\//_}.diff" err out rc

    err="$("${DIFF_SCRIPT}" "${base}" "${dir}" "${diff_file}" 2>&1 >/dev/null)"
    rc=$?
    if ((rc != 0)); then
        SUMMARY_BODY+="${dir}: diff step failed:"$'\n'"${err}"$'\n'
        PLAN_LINE="red${TAB}diff step failed: $(flatten "${err}")"
        return 0
    fi

    local errfile="${WORK}/${dir//\//_}.err"
    out="$(make -C "${dir}" mutants-diff-plan DIFF="${diff_file}" 2>"${errfile}")"
    rc=$?
    err="$(cat "${errfile}")"
    if ((rc != 0)); then
        SUMMARY_BODY+="${dir}: mutants-diff-plan failed:"$'\n'"${err}"$'\n'
        PLAN_LINE="red${TAB}mutants-diff-plan failed: $(flatten "${err}")"
        return 0
    fi

    local kept="" lines="" line
    local re_kept='^kept ([0-9]+) of ([0-9]+) \(lines ([0-9]+)\)$'
    local re_excl='^excluded [0-9]+ of [0-9]+ \(re-confirm: .*\)$'
    local seen_excl=0
    while IFS= read -r line; do
        line="${line//$'\r'/}"
        if [[ "${line}" =~ ${re_kept} ]]; then
            kept="${BASH_REMATCH[1]}"
            lines="${BASH_REMATCH[3]}"
        elif [[ "${line}" =~ ${re_excl} ]]; then
            seen_excl=1
        fi
    done <<<"${out}"

    if [[ -z "${kept}" || "${seen_excl}" -ne 1 ]]; then
        SUMMARY_BODY+="${dir}: unparseable prune output:"$'\n'"${out}"$'\n'
        PLAN_LINE="red${TAB}unparseable prune output: $(flatten "${out}")"
        return 0
    fi

    # Force base 10: a leading zero must not read as octal.
    kept=$((10#${kept}))
    lines=$((10#${lines}))
    if ((lines == 0)); then
        PLAN_LINE="red${TAB}lines 0"
    elif ((kept == 0)); then
        PLAN_LINE="green${TAB}0 mutants on changed lines"
    else
        local n k
        n="$(shard_count "${kept}")" || return 1
        PLAN_LINE="green${TAB}${kept} mutants in ${n} shards"
        for ((k = 0; k < n; k++)); do
            UNITS+=("{\"dir\":\"$(json_escape "${dir}")\",\"k\":${k},\"n\":${n}}")
        done
    fi
    return 0
}

main() {
    if [[ "$#" -lt 1 ]]; then
        printf 'Usage: %s <base-sha> [<dir>...]\n' "${0##*/}" >&2
        return 2
    fi

    local base="$1"
    shift
    local out_dir="${PLAN_OUT:-.}"
    mkdir -p "${out_dir}" || return 1

    WORK="$(mktemp -d)" || return 1
    # shellcheck disable=SC2064
    trap "rm -rf '${WORK}'" EXIT

    UNITS=()
    SUMMARY_BODY=""
    local plan="" dir
    for dir in "$@"; do
        dir="${dir%/}"
        PLAN_LINE=""
        plan_dir "${base}" "${dir}" || return 1
        plan+="${dir}${TAB}${PLAN_LINE}"$'\n'
    done

    printf '%s' "${plan}" >"${out_dir}/plan.txt" || return 1

    local json="[" sep="" unit
    for unit in "${UNITS[@]}"; do
        json+="${sep}${unit}"
        sep=","
    done
    printf '%s]\n' "${json}" >"${out_dir}/units.json" || return 1

    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        {
            printf '### Python mutation plan\n\n'
            if [[ -z "${plan}" ]]; then
                printf 'No Python projects to mutate.\n'
            else
                printf '| dir | verdict | detail |\n| --- | --- | --- |\n'
                local d v t
                while IFS="${TAB}" read -r d v t; do
                    printf '| %s | %s | %s |\n' "${d}" "${v}" "${t}"
                done <<<"${plan%$'\n'}"
            fi
            if [[ -n "${SUMMARY_BODY}" ]]; then
                printf '\n```\n%s```\n' "${SUMMARY_BODY}"
            fi
        } >>"${GITHUB_STEP_SUMMARY}" || return 1
    fi
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit "$?"
fi
