#!/usr/bin/env bash
# Usage: mutation-classify.sh <exit_code> <outcomes.json> <label> [max_missed [min_caught]]
#
# Without a 4th argument the verdict rules are the monthly sweep's: red only when nothing
# was evaluated (caught + missed == 0), the baseline failed or the runner died; survivors
# and timeouts are green.
# With a 4th argument (per-PR mode) timeouts count as evaluated, and the verdict is red
# when missed > max_missed, naming the missed.txt lines. A 5th argument additionally
# reds caught < min_caught, or a missing outcomes.json.

readonly GREEN_EXIT_CODES=(0 2 3)

_is_green_exit_code() {
    local code="$1"
    local candidate

    for candidate in "${GREEN_EXIT_CODES[@]}"; do
        if [[ "${candidate}" -eq "${code}" ]]; then
            return 0
        fi
    done
    return 1
}

_print_missed_lines() {
    local missed_file="$1"
    local line

    if [[ ! -f "${missed_file}" ]]; then
        printf "  missed.txt not found\n" >&2
        return 0
    fi
    while IFS= read -r line || [[ -n "${line}" ]]; do
        printf "  missed: %s\n" "${line}" >&2
    done <"${missed_file}"
}

classify_mutation_run() {
    local exit_code="$1"
    local outcomes="$2"
    local label="$3"
    local max_missed="${4-}"
    local min_caught="${5-}"
    # Function-local: a file-level readonly would fail when this file is sourced twice.
    local -r count_pattern='^(0|[1-9][0-9]{0,8})$'

    if [[ $# -ge 4 && ! "${max_missed}" =~ ${count_pattern} ]]; then
        printf "red: %s - max_missed '%s' is not a non-negative integer\n" "${label}" "${max_missed}" >&2
        return 1
    fi
    if [[ $# -ge 5 && ! "${min_caught}" =~ ${count_pattern} ]]; then
        printf "red: %s - min_caught '%s' is not a non-negative integer\n" "${label}" "${min_caught}" >&2
        return 1
    fi

    if [[ ! -f "${outcomes}" ]]; then
        if [[ $# -ge 5 ]]; then
            printf "red: %s - no outcomes.json (min_caught %s needs a measured run)\n" "${label}" "${min_caught}" >&2
            return 1
        fi
        if [[ "${exit_code}" -eq 0 ]]; then
            printf "green: %s - no mutants to test (no outcomes.json, exit 0)\n" "${label}"
            return 0
        fi
        printf "red: %s - no outcomes.json and exit code %s\n" "${label}" "${exit_code}" >&2
        return 1
    fi

    local parsed
    local jq_status
    # An absent key counts as 0; a present key keeps its value. A non-number renders as
    # non-empty text so the tab columns stay aligned and the integer check below names the
    # right field: null and false as their JSON text, a string as itself, except a digit
    # string, which is quoted so that "0" is not mistaken for the number 0.
    parsed=$(jq -e -r 'def count(k):
            if has(k) then
                .[k] | if type == "number" then tostring
                       elif type == "string" then (if test("^[0-9]+$") then tojson else . end)
                       else tojson end
            else "0" end;
        [count("caught"), count("missed"), count("timeout"), count("unviable")] | @tsv' "${outcomes}" 2>/dev/null)
    jq_status=$?
    if [[ "${jq_status}" -ne 0 ]]; then
        printf "red: %s - outcomes.json present but unparseable\n" "${label}" >&2
        return 1
    fi

    local caught missed timeout unviable
    IFS=$'\t' read -r caught missed timeout unviable <<<"${parsed}"

    local field value
    for field in caught missed timeout unviable; do
        value="${!field}"
        if [[ ! "${value}" =~ ${count_pattern} ]]; then
            printf "red: %s - outcomes.json %s '%s' is not a non-negative integer\n" "${label}" "${field}" "${value}" >&2
            return 1
        fi
    done

    local evaluated=$((caught + missed))
    if [[ $# -ge 4 ]]; then
        evaluated=$((evaluated + timeout))
    fi
    if [[ "${evaluated}" -eq 0 ]]; then
        printf "red: %s - nothing was evaluated (caught=%s missed=%s timeout=%s unviable=%s)\n" \
            "${label}" "${caught}" "${missed}" "${timeout}" "${unviable}" >&2
        return 1
    fi

    if ! _is_green_exit_code "${exit_code}"; then
        printf "red: %s - exit code %s (caught=%s missed=%s timeout=%s unviable=%s)\n" \
            "${label}" "${exit_code}" "${caught}" "${missed}" "${timeout}" "${unviable}" >&2
        return 1
    fi

    if [[ $# -ge 4 && "${missed}" -gt "${max_missed}" ]]; then
        printf "red: %s - missed=%s exceeds max_missed=%s (caught=%s timeout=%s unviable=%s)\n" \
            "${label}" "${missed}" "${max_missed}" "${caught}" "${timeout}" "${unviable}" >&2
        _print_missed_lines "$(dirname "${outcomes}")/missed.txt"
        return 1
    fi

    if [[ $# -ge 5 && "${caught}" -lt "${min_caught}" ]]; then
        printf "red: %s - caught=%s below min_caught=%s\n" "${label}" "${caught}" "${min_caught}" >&2
        return 1
    fi

    printf "green: %s - caught=%s missed=%s timeout=%s unviable=%s\n" \
        "${label}" "${caught}" "${missed}" "${timeout}" "${unviable}"
    return 0
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
classify_mutation_run "$@"
