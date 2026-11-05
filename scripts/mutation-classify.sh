#!/usr/bin/env bash

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

    if [[ $# -ge 4 && ! "${max_missed}" =~ ^[0-9]+$ ]]; then
        printf "red: %s - max_missed '%s' is not a non-negative integer\n" "${label}" "${max_missed}" >&2
        return 1
    fi
    if [[ $# -ge 5 && ! "${min_caught}" =~ ^[0-9]+$ ]]; then
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
    parsed=$(jq -e -r '[(.caught // 0), (.missed // 0), (.timeout // 0), (.unviable // 0)] | @tsv' "${outcomes}" 2>/dev/null)
    jq_status=$?
    if [[ "${jq_status}" -ne 0 ]]; then
        printf "red: %s - outcomes.json present but unparseable\n" "${label}" >&2
        return 1
    fi

    local caught missed timeout unviable
    IFS=$'\t' read -r caught missed timeout unviable <<<"${parsed}"

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
