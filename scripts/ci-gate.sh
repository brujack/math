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

    local excluded_json
    excluded_json=$(printf '"%s",' "${ADVISORY_CHECKS[@]}" "${SELF_CHECKS[@]}")
    excluded_json="[${excluded_json%,}]"

    # GITHUB_REPOSITORY is set automatically in Actions; fall back to gh for local use
    local repo="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner --jq '.nameWithOwner')}"

    # Get HEAD SHA for this PR (REST API, no workflowRun access needed)
    local sha
    sha=$(gh api "repos/${repo}/pulls/${pr}" --jq '.head.sha') || return 1

    local check_runs non_terminal timed_out=1

    for (( poll=0; poll<max_polls; poll++ )); do
        # REST check-runs API: status=in_progress/queued/completed, conclusion=success/failure/skipped/...
        check_runs=$(gh api --paginate "repos/${repo}/commits/${sha}/check-runs" \
            --jq '.check_runs[] | {name: .name, status: .status, conclusion: (.conclusion // "")}') || return 1
        non_terminal=$(printf '%s' "${check_runs}" | jq -r --argjson excl "${excluded_json}" \
            'select([.name] | inside($excl) | not) | select(.status != "completed") | .name')
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

    local required
    required=$(printf '%s' "${check_runs}" | jq -r --argjson excl "${excluded_json}" \
        'select([.name] | inside($excl) | not) | .name')

    if [[ -z "${required}" ]]; then
        printf "No required checks triggered. Proceeding.\n"
        return 0
    fi

    local failures
    failures=$(printf '%s' "${check_runs}" | jq -r --argjson excl "${excluded_json}" \
        'select([.name] | inside($excl) | not) | select(.conclusion != "success" and .conclusion != "skipped") | .name')

    if [[ -n "${failures}" ]]; then
        printf "Required checks failed:\n%s\n" "${failures}" >&2
        return 1
    fi

    printf "All required checks passed.\n"
    return 0
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
ci_gate "$@"
