#!/usr/bin/env bash
# Reports the cause of a mutation-testing workflow run to its tracking issue.
#
# Environment inputs: RESULT, DL_OUTCOME, ARTIFACT_DIR, RUN_URL, ISSUE_TITLE,
# UNIT_NOUN, REPO.
#
# attribute() keys the red-path cause on the downloaded artifact's own
# contents and nothing else -- specifically NOT on DL_OUTCOME. A failed
# download leaves ARTIFACT_DIR without a marker/ directory, so it reaches
# "no-attestation" by the same test as an empty or marker-less artifact.
# actions/download-artifact may fail on a missing artifact or succeed having
# downloaded nothing, and the attribution must not depend on which.

attribute() {
    local _dir="${ARTIFACT_DIR}"
    if [[ ! -d "${_dir}/marker" ]]; then
        printf 'no-attestation'
    elif [[ -d "${_dir}/status" ]]; then
        printf 'verdicts-present'
    elif find "${_dir}" -type d -name mutants.out -print -quit 2>/dev/null | grep -q .; then
        printf 'loop-began-no-verdict'
    else
        printf 'died-before-loop'
    fi
}

build_body() {
    local _token="${1}"
    local _detail

    case "${_token}" in
        verdicts-present)
            local _names
            _names=$(grep -l '^red' "${ARTIFACT_DIR}"/status/* 2>/dev/null | xargs -r -n1 basename | sed 's/^/- /')
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

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
