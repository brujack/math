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
            --jq '.check_runs[] | {id: .id, suite: .check_suite.id, name: .name, status: .status, conclusion: (.conclusion // "")}') || return 1
        # The API returns every run on the SHA, including runs a newer workflow run
        # superseded (draft PR marked ready cancels the first auto-merge run). Keep
        # only the latest run per (workflow, check name) so a stale "cancelled" cannot
        # fail the gate. Job names repeat across workflows (every *-py.yml and *-rs.yml
        # has a "test" job), so the name alone is not a key; a suite with no workflow
        # run (a non-Actions app) keys on its own suite id, and a run with no suite on
        # its own run id, so neither is ever collapsed. A newer "skipped" never
        # supersedes an older non-skipped run, since skipped counts as a pass below.
        workflow_runs=$(gh api --paginate "repos/${repo}/actions/runs?head_sha=${sha}&per_page=100" \
            --jq '.workflow_runs[] | {suite: .check_suite_id, wf: .workflow_id}') || return 1
        check_runs=$(printf '%s' "${check_runs}" | jq -c -s \
            --argjson wf "$(printf '%s' "${workflow_runs}" | jq -s 'map({key: (.suite | tostring), value: .wf}) | from_entries')" \
            'group_by([($wf[.suite | tostring] // (if .suite == null then "id:\(.id)" else "suite:\(.suite)" end) | tostring), .name])
             | map(([.[] | select(.conclusion != "skipped")] | max_by(.id)) // max_by(.id)) | .[]') || return 1
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
