#!/usr/bin/env bash

readonly ADVISORY_CHECKS=("snyk-scan")
readonly SELF_CHECKS=("secret-scan" "auto-merge")

ci_gate() {
    local pr="${1}"
    if [[ -z "${pr}" ]]; then
        printf "Usage: ci-gate.sh <PR_NUMBER>\n" >&2
        return 1
    fi

    local max_polls="${CI_GATE_MAX_POLLS:-60}"
    local poll_interval="${CI_GATE_POLL_INTERVAL:-30}"
    local checks non_terminal timed_out=1

    for (( poll=0; poll<max_polls; poll++ )); do
        checks=$(gh pr checks "${pr}" --json name,state) || return 1
        non_terminal=$(printf '%s' "${checks}" | jq -r \
            '.[] | select(.state == "queued" or .state == "in_progress" or .state == "pending" or .state == "waiting" or .state == "requested") | .name')
        if [[ -z "${non_terminal}" ]]; then
            timed_out=0
            break
        fi
        sleep "${poll_interval}"
    done

    if [[ "${timed_out}" -eq 1 ]]; then
        printf "Timeout: checks did not complete within %d polls\n" "${max_polls}" >&2
        return 1
    fi

    local excluded_json
    excluded_json=$(printf '"%s",' "${ADVISORY_CHECKS[@]}" "${SELF_CHECKS[@]}")
    excluded_json="[${excluded_json%,}]"

    local required
    required=$(printf '%s' "${checks}" | jq -r --argjson excl "${excluded_json}" \
        '.[] | select([.name] | inside($excl) | not) | .name')

    if [[ -z "${required}" ]]; then
        printf "No required checks triggered. Proceeding.\n"
        return 0
    fi

    local failures
    failures=$(printf '%s' "${checks}" | jq -r --argjson excl "${excluded_json}" \
        '.[] | select([.name] | inside($excl) | not) | select(.state != "success" and .state != "skipped") | .name')

    if [[ -n "${failures}" ]]; then
        printf "Required checks failed:\n%s\n" "${failures}" >&2
        return 1
    fi

    printf "All required checks passed.\n"
    return 0
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
ci_gate "$@"
