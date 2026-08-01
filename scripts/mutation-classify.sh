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

classify_mutation_run() {
    local exit_code="$1"
    local outcomes="$2"
    local label="$3"

    if [[ ! -f "${outcomes}" ]]; then
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

    if [[ $((caught + missed)) -eq 0 ]]; then
        printf "red: %s - nothing was evaluated (caught=%s missed=%s timeout=%s unviable=%s)\n" \
            "${label}" "${caught}" "${missed}" "${timeout}" "${unviable}" >&2
        return 1
    fi

    if _is_green_exit_code "${exit_code}"; then
        printf "green: %s - caught=%s missed=%s timeout=%s unviable=%s\n" \
            "${label}" "${caught}" "${missed}" "${timeout}" "${unviable}"
        return 0
    fi

    printf "red: %s - exit code %s (caught=%s missed=%s timeout=%s unviable=%s)\n" \
        "${label}" "${exit_code}" "${caught}" "${missed}" "${timeout}" "${unviable}" >&2
    return 1
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
classify_mutation_run "$@"
