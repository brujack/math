#!/usr/bin/env bash
# Reports the cause of a mutation-testing workflow run to its tracking issue.
#
# attribute() and build_body() key the red-path body on the downloaded
# artifact's own contents (ARTIFACT_DIR, RUN_URL, UNIT_NOUN). main() adds the
# green-path close and the issue create/comment dispatch, consuming RESULT,
# ISSUE_TITLE, REPO and ISSUE_LABEL on top of those. main()'s dispatch logic is ported
# from .github/workflows/mutation-testing.yml's notify job -- but not
# byte-for-byte: it drops that block's `set -u` in favour of explicit `:?`
# guards per input, and adds --repo "${REPO}" to every gh issue/label call
# so a malformed fixture REPO fails in gh's own argument parser rather than
# reaching the network (tdd.md E2).

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
    # as verdicts-present. Fall through to the loop-began / died-before-loop
    # checks below, the same as if status/ were absent entirely.
    if [[ -d "${_dir}/status" ]] && find "${_dir}/status" -mindepth 1 -print -quit | grep -q .; then
        printf 'verdicts-present'
        return 0
    fi

    # "The loop began" is: the artifact contains any ROOT-LEVEL entry other
    # than marker/ and status/ (-maxdepth 1 -- marker/job-began itself sits
    # one level deeper and must not match). This must stay tool-agnostic --
    # cargo-mutants uploads mutants.out/, cosmic-ray uploads
    # mutants-report.txt and cosmic-ray-session.sqlite, and this script is
    # shared by both workflows. Naming either tool's filenames here would
    # misattribute the other's run the moment it began the loop and wrote
    # no verdict.
    if find "${_dir}" -mindepth 1 -maxdepth 1 ! -name marker ! -name status -print -quit | grep -q .; then
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

# Comment on the open tracking issue, or file one (creating the label first).
# Both branches end in an explicit `|| return 1`; the last-statement position
# alone would return gh's own exit code, so the expected-units path in main()
# returns 2 after calling this when posting failed (1 when it posted), and the tests pin both codes.
post_issue() {
    local _existing="${1}"
    local _body="${2}"

    if [[ -n "${_existing}" ]]; then
        gh issue comment "${_existing}" --repo "${REPO}" --body "${_body}" || return 1
    else
        gh label create "${ISSUE_LABEL}" --repo "${REPO}" --color B60205 \
            --description "Monthly mutation run failed" 2>/dev/null || true
        gh issue create --repo "${REPO}" --title "${ISSUE_TITLE}" --label "${ISSUE_LABEL}" --body "${_body}" || return 1
    fi
}

# Units section of the EXPECTED_STATUS_UNITS report: units that wrote no status
# file, units rejected for containing a slash, and red units with the first
# line of their status file as the reason.
build_units_body() {
    local _missing="${1}"
    local _invalid="${2}"
    local _empty="${3}"
    local _red="" _file _line _detail

    for _file in "${ARTIFACT_DIR}"/status/*; do
        [[ -f "${_file}" ]] || continue
        # First line starting with red is the reason, wherever it sits.
        while IFS= read -r _line || [[ -n "${_line}" ]]; do
            if [[ "${_line}" == red* ]]; then
                _red+="- ${_file##*/}: ${_line}"$'\n'
                break
            fi
        done < "${_file}"
    done

    if [[ "${_empty}" == "1" ]]; then
        _detail="The expected list was empty, so no ${UNIT_NOUN} could be verified."
    else
        _detail="Missing ${UNIT_NOUN}s:"$'\n'"${_missing:-- (none)}"
    fi
    if [[ -n "${_invalid}" ]]; then
        _detail+=$'\n\n'"Invalid ${UNIT_NOUN}s (a name may not contain a slash):"$'\n'"${_invalid}"
    fi
    printf 'Cause: missing-status\n\nThe run reported %s but not every expected %s wrote a verdict.\n\n%s\n\nRed %ss:\n%s\n\nRun: %s\n' \
        "${RESULT}" "${UNIT_NOUN}" "${_detail}" "${UNIT_NOUN}" "${_red:-- (none)}" "${RUN_URL}"
}

# Returns 0 when every expected unit has a status file. Otherwise posts a
# report and returns 1, or 2 when posting itself failed. Only called when
# EXPECTED_STATUS_UNITS is set. Units are split into an array, never left to
# word-splitting and globbing, and a name containing a slash is rejected
# before it can be joined onto ARTIFACT_DIR.
check_expected_units() {
    local _existing="${1}"
    local -a _units
    local _unit _missing="" _invalid="" _empty=0 _body _cause

    # read -d '' always returns 1 at EOF, so the || true is not hiding a failure.
    read -rd '' -a _units <<< "${EXPECTED_STATUS_UNITS}" || true
    [[ ${#_units[@]} -eq 0 ]] && _empty=1

    for _unit in "${_units[@]}"; do
        if [[ "${_unit}" == */* ]]; then
            _invalid+="- ${_unit}"$'\n'
        elif [[ ! -f "${ARTIFACT_DIR}/status/${_unit}" ]]; then
            _missing+="- ${_unit}"$'\n'
        fi
    done
    [[ "${_empty}" == "0" && -z "${_missing}" && -z "${_invalid}" ]] && return 0

    _body=$(build_units_body "${_missing%$'\n'}" "${_invalid%$'\n'}" "${_empty}") || return 2
    if [[ "${RESULT}" != "success" ]]; then
        _cause=$(attribute) || return 2
        _body="$(build_body "${_cause}")"$'\n\n'"${_body}"
    fi
    post_issue "${_existing}" "${_body}" || return 2
    return 1
}

# File, comment, or close the tracking issue. Same decision tree as
# the notify job's former inline block, which it replaced on 2026-09-01;
# the workflows now supply only env: -- with two
# deliberate differences: no `set -u` (RESULT, REPO, ISSUE_TITLE and
# ISSUE_LABEL each get an explicit `:?` guard instead, since RESULT alone
# selects the branch),
# and every gh issue/label call carries --repo "${REPO}" so a malformed
# fixture REPO fails in gh's own argument parser instead of reaching a live
# tracker (tdd.md E2).
main() {
    : "${RESULT:?}"
    : "${REPO:?}"
    : "${ISSUE_TITLE:?}"
    : "${ISSUE_LABEL:?}"

    local _existing
    # --jq '.[0].number // empty' is real gh/jq behaviour; the test mock
    # echoes MOCK_GH_ISSUE_LIST verbatim and never runs jq, so this suite
    # cannot exercise the `// empty` fallback itself -- only that whatever
    # gh returns is treated as truthy/falsy by bash's -n test below.
    _existing=$(gh issue list --repo "${REPO}" --state open --label "${ISSUE_LABEL}" \
        --search "in:title \"${ISSUE_TITLE}\"" --json number --jq '.[0].number // empty') || return 1

    if [[ -n "${EXPECTED_STATUS_UNITS+x}" ]]; then
        check_expected_units "${_existing}" || return "$?"
    fi

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

    post_issue "${_existing}" "${_body}"
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0

main "$@"
