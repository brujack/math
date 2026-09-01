#!/usr/bin/env bash
# Reports the cause of a mutation-testing workflow run to its tracking issue.
#
# attribute() and build_body() key the red-path body on the downloaded
# artifact's own contents (ARTIFACT_DIR, RUN_URL, UNIT_NOUN). main() adds the
# green-path close and the issue create/comment dispatch, consuming RESULT,
# ISSUE_TITLE and REPO on top of those. Ported from
# .github/workflows/mutation-testing.yml, unchanged in behaviour.

# attribute() keys the red-path cause on the downloaded artifact's own
# contents and nothing else -- specifically NOT on DL_OUTCOME. A failed
# download leaves ARTIFACT_DIR without a marker/ directory, so it reaches
# "no-attestation" by the same test as an empty or marker-less artifact.
# actions/download-artifact may fail on a missing artifact or succeed having
# downloaded nothing, and the attribution must not depend on which.
attribute() {
    : "${ARTIFACT_DIR:?}"
    local _dir="${ARTIFACT_DIR}"

    if [[ ! -d "${_dir}/marker" ]]; then
        printf 'no-attestation'
        return 0
    fi

    # A status/ directory that exists but is empty is a third state -- the
    # loop created the directory and wrote nothing yet -- and must not read
    # as verdicts-present. Fall through to the mutants.out / died-before-loop
    # checks below, the same as if status/ were absent entirely.
    if [[ -d "${_dir}/status" ]] && find "${_dir}/status" -mindepth 1 -print -quit | grep -q .; then
        printf 'verdicts-present'
        return 0
    fi

    if find "${_dir}" -type d -name mutants.out -print -quit | grep -q .; then
        printf 'loop-began-no-verdict'
        return 0
    fi

    printf 'died-before-loop'
}

build_body() {
    local _token="${1}"
    local _detail

    case "${_token}" in
        verdicts-present)
            local _names
            _names=$(grep -l '^red' "${ARTIFACT_DIR}"/status/* 2>/dev/null | sed 's|.*/|- |')
            _detail="Failing ${UNIT_NOUN}s:"$'\n'"${_names:-- (none flagged; see run log)}"
            ;;
        loop-began-no-verdict)
            _detail="The loop began and no verdict was written. At least one ${UNIT_NOUN} ran \`make mutants\`, and the job stopped before the first status file was written."
            ;;
        died-before-loop)
            _detail="The job ran and failed before the loop. Checkout succeeded and it did not reach the first \`make mutants\`. The failing step is in the run log."
            ;;
        no-attestation)
            _detail="The job's own reporting never ran. One of: terminated before the upload step; a checkout failure before the marker was written; the upload itself failed; the artifact was corrupt on download. None of these is asserted."
            ;;
        *)
            _detail="Unknown cause token: ${_token}"
            ;;
    esac

    printf 'Cause: %s\n\n%s\n\nRun: %s\n' "${_token}" "${_detail}" "${RUN_URL}"
}

# File, comment, or close the tracking issue -- ported unchanged in
# behaviour from .github/workflows/mutation-testing.yml:113-142. Every gh
# issue/label call carries --repo "${REPO}" so a fixture REPO fails at gh's
# own resolution rather than reaching a live tracker (tdd.md E2).
main() {
    : "${REPO:?}"
    : "${ISSUE_TITLE:?}"

    local _existing
    _existing=$(gh issue list --repo "${REPO}" --state open --label mutation-failure \
        --search "in:title \"${ISSUE_TITLE}\"" --json number --jq '.[0].number // empty') || return 1

    if [[ "${RESULT}" == "success" ]]; then
        if [[ -n "${_existing}" ]]; then
            gh issue comment "${_existing}" --repo "${REPO}" --body "Green as of ${RUN_URL}. Closing." || return 1
            gh issue close "${_existing}" --repo "${REPO}" || return 1
        fi
        return 0
    fi

    local _token _body
    _token=$(attribute) || return 1
    _body=$(build_body "${_token}") || return 1

    if [[ -n "${_existing}" ]]; then
        gh issue comment "${_existing}" --repo "${REPO}" --body "${_body}" || return 1
    else
        gh label create mutation-failure --repo "${REPO}" --color B60205 \
            --description "Monthly mutation run failed" 2>/dev/null || true
        gh issue create --repo "${REPO}" --title "${ISSUE_TITLE}" --label mutation-failure --body "${_body}" || return 1
    fi
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0

main "$@"
