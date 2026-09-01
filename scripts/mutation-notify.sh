#!/usr/bin/env bash
# Reports the cause of a mutation-testing workflow run to its tracking issue.
#
# This task implements the red-path attribution only: attribute() and
# build_body(). Consumed here: ARTIFACT_DIR, RUN_URL, UNIT_NOUN.

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

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
