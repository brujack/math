#!/usr/bin/env bash
# Summarises a sharded cosmic-ray mutation run per sub-project.
#
# Reads the merged status artifacts (ARTIFACT_DIR/status/<dir>-<k> holding the
# verdict line written by scripts/cosmic_ray_cell_status.py, and
# ARTIFACT_DIR/survivors/<dir>-<k>.txt holding `<module>:<line> <operator>`
# lines), writes OUT_DIR/survivors/<dir>.txt per sub-project, appends a
# markdown table to GITHUB_STEP_SUMMARY and posts it to the open
# mutation-report-python issue (creating the issue when none is open).
#
# Survivors are a finding to read, not a failure: the exit status is 0 on any
# counts. It is non-zero only when a required input is missing or a gh call
# (other than the best-effort label create) fails.

readonly REPORT_LABEL="mutation-report-python"
readonly REPORT_TITLE="mutation-testing-python: survivor report"

# Unit directory is everything before the last '-' (perfect-numbers-0 ->
# perfect-numbers), because sub-project names themselves contain '-'.
unit_dir() {
    printf '%s' "${1%-*}"
}

check_inputs() {
    local _var
    for _var in ARTIFACT_DIR EXPECTED_STATUS_UNITS REPO RUN_URL REF EVENT OUT_DIR GITHUB_STEP_SUMMARY; do
        if [[ -z "${!_var:-}" ]]; then
            printf 'mutation-survivor-report: required env %s is unset or empty\n' "${_var}" >&2
            return 1
        fi
    done
}

# Concatenate each sub-project's survivor files, sorted, into
# OUT_DIR/survivors/<dir>.txt. Only dirs with at least one file get an output.
write_survivor_files() {
    local _dir _file
    local -a _files
    mkdir -p "${OUT_DIR}/survivors" || return 1
    for _dir in "$@"; do
        _files=()
        for _file in "${ARTIFACT_DIR}/survivors/${_dir}-"*.txt; do
            [[ -f "${_file}" ]] || continue
            # The glob also matches longer names sharing the prefix
            # (fib-0 vs fib-x-0); require the remainder to be a bare cell index.
            [[ "${_file##*/}" =~ ^${_dir}-[0-9]+\.txt$ ]] || continue
            _files+=("${_file}")
        done
        [[ ${#_files[@]} -gt 0 ]] || continue
        LC_ALL=C sort "${_files[@]}" > "${OUT_DIR}/survivors/${_dir}.txt" || return 1
    done
}

# Sets TABLE_ROWS and UNITS_REPORTING / UNITS_EXPECTED.
build_table() {
    local _unit _dir _status _line
    local -a _dirs=()
    local -A _expected=() _reporting=() _red=() _jobs=() _surv=() _timed=()
    local _re='^green: .* — ([0-9]+) surviving, ([0-9]+) timed out, ([0-9]+) jobs'

    read -rd '' -a _units <<< "${EXPECTED_STATUS_UNITS}" || true
    UNITS_REPORTING=0
    UNITS_EXPECTED=0
    for _unit in "${_units[@]}"; do
        [[ "${_unit}" == */* || "${_unit}" != *-* ]] && continue
        _dir=$(unit_dir "${_unit}")
        if [[ -z "${_expected[${_dir}]:-}" ]]; then
            _dirs+=("${_dir}")
            _expected[${_dir}]=0 _reporting[${_dir}]=0 _red[${_dir}]=0
            _jobs[${_dir}]=0 _surv[${_dir}]=0 _timed[${_dir}]=0
        fi
        _expected[${_dir}]=$((_expected[${_dir}] + 1))
        UNITS_EXPECTED=$((UNITS_EXPECTED + 1))
        _status="${ARTIFACT_DIR}/status/${_unit}"
        [[ -f "${_status}" ]] || continue
        _reporting[${_dir}]=$((_reporting[${_dir}] + 1))
        UNITS_REPORTING=$((UNITS_REPORTING + 1))
        IFS= read -r _line < "${_status}" || [[ -n "${_line}" ]]
        if [[ "${_line}" =~ ${_re} ]]; then
            _surv[${_dir}]=$((_surv[${_dir}] + BASH_REMATCH[1]))
            _timed[${_dir}]=$((_timed[${_dir}] + BASH_REMATCH[2]))
            _jobs[${_dir}]=$((_jobs[${_dir}] + BASH_REMATCH[3]))
        else
            # Red, or anything that is not a green line: counts as reporting
            # but contributes no numbers.
            _red[${_dir}]=$((_red[${_dir}] + 1))
        fi
    done

    write_survivor_files "${_dirs[@]}" || return 1

    TABLE_ROWS=""
    local _lines _notes
    for _dir in "${_dirs[@]}"; do
        _lines=0
        [[ -f "${OUT_DIR}/survivors/${_dir}.txt" ]] && _lines=$(wc -l < "${OUT_DIR}/survivors/${_dir}.txt")
        _lines=$((_lines + 0))
        _notes=""
        [[ ${_reporting[${_dir}]} -lt ${_expected[${_dir}]} ]] && _notes="incomplete"
        if [[ ${_red[${_dir}]} -gt 0 ]]; then
            _notes+="${_notes:+, }${_red[${_dir}]} red"
        fi
        TABLE_ROWS+="| ${_dir} | ${_reporting[${_dir}]}/${_expected[${_dir}]} | ${_jobs[${_dir}]} | ${_surv[${_dir}]} | ${_timed[${_dir}]} | ${_lines} | ${_notes} |"$'\n'
    done
}

build_report() {
    printf '## Python mutation survivor report\n\n'
    printf 'Ref: %s\nEvent: %s\nUnits reporting: %s of %s\nRun: %s\n\n' \
        "${REF}" "${EVENT}" "${UNITS_REPORTING}" "${UNITS_EXPECTED}" "${RUN_URL}"
    printf 'Survivor locations are in artifact mutants-survivors-python.\n\n'
    printf '| sub-project | cells reporting/expected | jobs | survivors | timed out | survivor lines | notes |\n'
    printf '| --- | --- | --- | --- | --- | --- | --- |\n'
    printf '%s' "${TABLE_ROWS}"
}

post_report() {
    local _body="${1}"
    local _existing

    _existing=$(gh issue list --repo "${REPO}" --state open --label "${REPORT_LABEL}" \
        --json number --jq '.[0].number // empty') || return 1
    if [[ -n "${_existing}" ]]; then
        gh issue comment "${_existing}" --repo "${REPO}" --body "${_body}" || return 1
    else
        gh label create "${REPORT_LABEL}" --repo "${REPO}" --color 0E8A16 \
            --description "Monthly Python mutation survivor report" 2>/dev/null || true
        gh issue create --repo "${REPO}" --title "${REPORT_TITLE}" \
            --label "${REPORT_LABEL}" --body "${_body}" || return 1
    fi
}

main() {
    check_inputs || return 1
    build_table || return 1
    local _report
    _report=$(build_report) || return 1
    printf '%s\n' "${_report}" >> "${GITHUB_STEP_SUMMARY}" || return 1
    post_report "${_report}" || return 1
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0

main "$@"
