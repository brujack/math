#!/usr/bin/env bash
# Reports the cause of a mutation-testing workflow run to its tracking issue.
#
# attribute() and build_body() key the red-path body on the downloaded
# artifact's own contents (ARTIFACT_DIR, RUN_URL, UNIT_NOUN). main() adds the
# green-path close (only on a full sweep, FULL_SWEEP=true) and the issue
# create/comment dispatch, consuming RESULT, ISSUE_TITLE, REPO, ISSUE_LABEL
# and FULL_SWEEP on top of those. main()'s dispatch logic is ported
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

# Red units from ${ARTIFACT_DIR}/status/*, one list item per unit: the first
# line starting with red is the reason, and any lines after it are detail in a
# fenced block capped at 20 lines (the rest is counted, not printed). Every
# line of the block, fences included, is indented two spaces: an unindented
# line ends the list item in GitHub's renderer and strips <u32>-style text.
# The fence is tildes, not backticks: a detail line of three or more backticks
# would close a backtick fence early and swallow the lines after the block.
# Prints nothing when no unit is red.
render_red_units() {
    local _file _line _found _ndetail _extra
    local -r _max=20
    local _fence='  ~~~~~'

    for _file in "${ARTIFACT_DIR}"/status/*; do
        [[ -f "${_file}" ]] || continue
        _found=0
        _ndetail=0
        _extra=0
        while IFS= read -r _line || [[ -n "${_line}" ]]; do
            if [[ "${_found}" == "0" ]]; then
                if [[ "${_line}" == red* ]]; then
                    _found=1
                    printf -- '- %s: %s\n' "${_file##*/}" "${_line}"
                fi
                continue
            fi
            _ndetail=$((_ndetail + 1))
            if [[ "${_ndetail}" -le "${_max}" ]]; then
                if [[ "${_ndetail}" -eq 1 ]]; then
                    printf '%s\n' "${_fence}"
                fi
                printf '  %s\n' "${_line}"
            else
                _extra=$((_extra + 1))
            fi
        done < "${_file}"
        if [[ "${_ndetail}" -gt 0 ]]; then
            if [[ "${_extra}" -gt 0 ]]; then
                printf '  ... %s more lines in the run\n' "${_extra}"
            fi
            printf '%s\n' "${_fence}"
        fi
    done
}

build_body() {
    local _token="${1}"
    local _detail

    case "${_token}" in
        verdicts-present)
            local _names
            _names=$(render_red_units)
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
# file, units rejected for containing a slash, and red units (render_red_units:
# first red line plus a capped, fenced detail block). The fourth parameter,
# omit_red, is 1 when the caller's build_body already lists the red units, so
# the Red section is left out and no unit is named twice.
build_units_body() {
    local _missing="${1}"
    local _invalid="${2}"
    local _empty="${3}"
    local _omit_red="${4:-0}"
    local _red _detail

    _red=$(render_red_units)

    if [[ "${_empty}" == "1" ]]; then
        _detail="The expected list was empty, so no ${UNIT_NOUN} could be verified."
    else
        _detail="Missing ${UNIT_NOUN}s:"$'\n'"${_missing:-- (none)}"
    fi
    if [[ -n "${_invalid}" ]]; then
        _detail+=$'\n\n'"Invalid ${UNIT_NOUN}s (a name may not contain a slash):"$'\n'"${_invalid}"
    fi
    printf 'Cause: missing-status\n\nThe run reported %s but not every expected %s wrote a verdict.\n\n%s\n\n' \
        "${RESULT}" "${UNIT_NOUN}" "${_detail}"
    if [[ "${_omit_red}" != "1" ]]; then
        printf 'Red %ss:\n%s\n\n' "${UNIT_NOUN}" "${_red:-- (none)}"
    fi
    printf 'Run: %s\n' "${RUN_URL}"
}

# Returns 0 when every expected unit has a status file. Otherwise posts a
# report and returns 1, or 2 when posting itself failed. Only called when
# EXPECTED_STATUS_UNITS is set. Units are split into an array, never left to
# word-splitting and globbing, and a name containing a slash is rejected
# before it can be joined onto ARTIFACT_DIR.
check_expected_units() {
    local _existing="${1}"
    local -a _units
    local _unit _missing="" _invalid="" _empty=0 _body _cause _omit_red

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

    # A non-success run prepends build_body, except when its cause is
    # verdicts-present and no unit is red: that body would only say "none
    # flagged", so the missing-status body stands alone. With red units the
    # prefix already lists them, so the units body omits its own Red section;
    # any other cause lists none, so the units body keeps it.
    _omit_red=0
    _cause=""
    if [[ "${RESULT}" != "success" ]]; then
        _cause=$(attribute) || return 2
        if [[ "${_cause}" == "verdicts-present" ]]; then
            if [[ -n "$(render_red_units)" ]]; then _omit_red=1; else _cause=""; fi
        fi
    fi
    _body=$(build_units_body "${_missing%$'\n'}" "${_invalid%$'\n'}" "${_empty}" "${_omit_red}") || return 2
    if [[ -n "${_cause}" ]]; then
        _body="$(build_body "${_cause}")"$'\n\n'"${_body}"
    fi
    post_issue "${_existing}" "${_body}" || return 2
    return 1
}

# File, comment, or close the tracking issue. Same decision tree as
# the notify job's former inline block, which it replaced on 2026-09-01;
# the workflows now supply only env: -- with two
# deliberate differences: no `set -u` (RESULT, REPO, ISSUE_TITLE,
# ISSUE_LABEL and FULL_SWEEP each get an explicit `:?` guard instead, since
# together they select the branch),
# and every gh issue/label call carries --repo "${REPO}" so a malformed
# fixture REPO fails in gh's own argument parser instead of reaching a live
# tracker (tdd.md E2).
main() {
    : "${RESULT:?}"
    : "${REPO:?}"
    : "${ISSUE_TITLE:?}"
    : "${ISSUE_LABEL:?}"
    : "${FULL_SWEEP:?FULL_SWEEP unset: the notify step must pass true or false}"
    case "${FULL_SWEEP}" in
        true | false) ;;
        *)
            printf 'FULL_SWEEP must be true or false, got: %s\n' "${FULL_SWEEP}" >&2
            return 1
            ;;
    esac

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
            if [[ "${FULL_SWEEP}" == "true" ]]; then
                gh issue comment "${_existing}" --repo "${REPO}" --body "Green as of ${RUN_URL}. Closing." || return 1
                gh issue close "${_existing}" --repo "${REPO}" || return 1
            else
                # One green unit says nothing about the others, so leave it open.
                gh issue comment "${_existing}" --repo "${REPO}" \
                    --body "Single-unit run green as of ${RUN_URL}; left open (only a full sweep closes this issue)." || return 1
            fi
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
