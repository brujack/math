#!/usr/bin/env bash
# Applies the ordered per-dir verdict table of the Python PR mutation gate
# (spec 2026-11-07-worldclass-slice8, "Verdicts per dir") to a plan file and the
# per-unit status files.
#
# Usage: mutation-pr-verdict-python.sh --expected-dirs "<dirs>" [--min-killed N]
#                                      <plan-file> <status-dir>
#
# plan-file lines: <dir>\t<green|red>\t<text>; a dir with units carries
# "<K> mutants in <n> shards", a dir with nothing to test "0 mutants on changed lines".
# status-dir holds <dir>-<k> for k in 0..n-1, the stdout of
# cosmic_ray_cell_status.py <session> <label> --max-survivors 0.
#
# Prints one verdict line per dir (details indented) to stdout and appends the same
# to ${GITHUB_STEP_SUMMARY} when set. Exit 1 when any dir is red, 2 on bad usage.

readonly EX_RED=1
readonly EX_USAGE=2
readonly KEPT_ZERO_TEXT='0 mutants on changed lines'
readonly UNITS_RE='^([0-9]+) mutants in ([0-9]+) shards$'
readonly SPACE_RE='^[[:space:]]*$'
# green status line: "green: <label> — S surviving, T timed out, J jobs"
readonly GREEN_RE='^green: .* ([0-9]+) surviving, [0-9]+ timed out, ([0-9]+) jobs$'

_out=""

emit() {
    _out+="$1"$'\n'
}

usage() {
    printf 'usage: %s --expected-dirs "<dirs>" [--min-killed N] <plan-file> <status-dir>\n' "$0" >&2
    return 0
}

# repro_line <dir> <k> <n>: the local reproduction for one unit.
repro_line() {
    # shellcheck disable=SC2016  # $(mktemp) and "$d" are printed literally for the reader
    printf '    repro: d=$(mktemp) && scripts/mutation-pr-diff.sh origin/master %s "$d" && make -C %s mutants-diff DIFF="$d" MUTANT_SHARD=%s/%s\n' "$1" "$1" "$2" "$3"
    return 0
}

# red_dir <dir> <reason> [detail-block]: record a red dir verdict.
red_dir() {
    emit "${1}: red: ${2}"
    if [[ -n "${3:-}" ]]; then
        emit "${3}"
    fi
    return 0
}

# unit_status <dir> <k> <n> <file>: judge one unit's status file. Returns 0 when green
# (UNIT_KILLED = jobs - surviving), 1 when red (UNIT_DETAIL = the lines to show).
unit_status() {
    local dir="$1" k="$2" n="$3" file="$4"
    local first body
    UNIT_KILLED=0
    UNIT_DETAIL=""
    if [[ ! -f "${file}" ]]; then
        UNIT_DETAIL="  unit ${k}/${n}: no status file ${file##*/} (its step failed or never ran)"$'\n'"$(repro_line "${dir}" "${k}" "${n}")"
        return 1
    fi
    first=""
    IFS= read -r first <"${file}"
    if [[ "${first}" =~ ${GREEN_RE} ]]; then
        UNIT_KILLED=$((BASH_REMATCH[2] - BASH_REMATCH[1]))
        if ((BASH_REMATCH[1] > 0)); then
            UNIT_DETAIL="  unit ${k}/${n}: ${first}"$'\n'"$(repro_line "${dir}" "${k}" "${n}")"
            return 1
        fi
        return 0
    fi
    if [[ "${first}" == red:* ]]; then
        UNIT_DETAIL="  unit ${k}/${n}: ${first}"
        # Survivor blocks (full key + diff) follow the verdict line.
        body="$(tail -n +2 "${file}" | sed 's/^/    /')"
        if [[ -n "${body}" ]]; then
            UNIT_DETAIL+=$'\n'"${body}"
        fi
        UNIT_DETAIL+=$'\n'"$(repro_line "${dir}" "${k}" "${n}")"
        return 1
    fi
    UNIT_DETAIL="  unit ${k}/${n}: unrecognised status file ${file##*/}"$'\n'"$(repro_line "${dir}" "${k}" "${n}")"
    return 1
}

# judge_units <dir> <n> <min_killed> <status_dir>: rows 2, 4-6, 8 for a dir with units.
judge_units() {
    local dir="$1" n="$2" min_killed="$3" status_dir="$4"
    local k details="" killed_total=0 red=0
    for ((k = 0; k < n; k++)); do
        if unit_status "${dir}" "${k}" "${n}" "${status_dir}/${dir}-${k}"; then
            killed_total=$((killed_total + UNIT_KILLED))
        else
            red=1
            details+="${UNIT_DETAIL}"$'\n'
        fi
    done
    if ((red)); then
        red_dir "${dir}" "survivors or failed units across ${n} shards" "${details%$'\n'}"
        return 1
    fi
    if ((killed_total < min_killed)); then
        red_dir "${dir}" "killed ${killed_total} < --min-killed ${min_killed}"
        return 1
    fi
    emit "${dir}: green: ${n} shards, 0 surviving, ${killed_total} killed"
    return 0
}

# judge_dir <dir> <verdict> <text> <min_killed> <status_dir>: rows 2-8 for one planned dir.
judge_dir() {
    local dir="$1" verdict="$2" text="$3" min_killed="$4" status_dir="$5"
    if [[ "${verdict}" == red ]]; then
        if [[ "${text}" == "lines 0" ]]; then
            red_dir "${dir}" "no changed module lines (lines 0)"
        else
            red_dir "${dir}" "plan step failed: ${text}"
        fi
        return 1
    fi
    if [[ "${verdict}" != green ]]; then
        red_dir "${dir}" "unknown plan verdict '${verdict}'"
        return 1
    fi
    if [[ "${text}" == "${KEPT_ZERO_TEXT}" ]]; then
        if ((min_killed > 0)); then
            red_dir "${dir}" "killed 0 < --min-killed ${min_killed} (${KEPT_ZERO_TEXT})"
            return 1
        fi
        emit "${dir}: green: ${KEPT_ZERO_TEXT}"
        return 0
    fi
    if [[ "${text}" =~ ${UNITS_RE} ]]; then
        if ((BASH_REMATCH[2] < 1)); then
            red_dir "${dir}" "unknown plan line: '${text}' (zero shards)"
            return 1
        fi
        judge_units "${dir}" "$((10#${BASH_REMATCH[2]}))" "${min_killed}" "${status_dir}"
        return $?
    fi
    red_dir "${dir}" "unknown plan line: '${text}'"
    return 1
}

main() {
    local expected="" have_expected=0 min_killed=0 plan="" status_dir="" positional=0
    while (($# > 0)); do
        case "$1" in
            --expected-dirs)
                if (($# < 2)); then usage; return "${EX_USAGE}"; fi
                expected="$2"
                have_expected=1
                shift 2
                ;;
            --min-killed)
                if (($# < 2)); then usage; return "${EX_USAGE}"; fi
                if [[ ! "$2" =~ ^[0-9]+$ ]]; then
                    printf 'error: --min-killed needs a non-negative integer, got "%s"\n' "$2" >&2
                    return "${EX_USAGE}"
                fi
                min_killed=$((10#$2))
                shift 2
                ;;
            -*)
                printf 'error: unknown option %s\n' "$1" >&2
                usage
                return "${EX_USAGE}"
                ;;
            *)
                if ((positional == 0)); then plan="$1"; elif ((positional == 1)); then status_dir="$1"; else usage; return "${EX_USAGE}"; fi
                positional=$((positional + 1))
                shift
                ;;
        esac
    done
    if ((have_expected == 0)) || [[ -z "${plan}" || -z "${status_dir}" ]]; then
        usage
        return "${EX_USAGE}"
    fi
    if [[ ! -f "${plan}" ]]; then
        printf 'error: plan file not found: %s\n' "${plan}" >&2
        return "${EX_USAGE}"
    fi

    local any_red=0 dir verdict text seen=" " d
    # Row 1 (plan side): every plan line is judged, unexpected dirs are red.
    while IFS=$'\t' read -r dir verdict text || [[ -n "${dir}" ]]; do
        if [[ "${dir}" =~ ${SPACE_RE} ]]; then continue; fi
        if [[ "${seen}" == *" ${dir} "* ]]; then
            red_dir "${dir}" "duplicate plan line"
            any_red=1
            continue
        fi
        seen+="${dir} "
        if [[ " ${expected} " != *" ${dir} "* ]]; then
            red_dir "${dir}" "plan line for a dir that is not expected"
            any_red=1
            continue
        fi
        judge_dir "${dir}" "${verdict}" "${text}" "${min_killed}" "${status_dir}" || any_red=1
    done <"${plan}"
    # Row 1 (expected side): every expected dir needs a plan line.
    for d in ${expected}; do
        if [[ "${seen}" != *" ${d} "* ]]; then
            red_dir "${d}" "expected dir has no plan line"
            any_red=1
        fi
    done

    printf '%s' "${_out}"
    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        printf '%s' "${_out}" >>"${GITHUB_STEP_SUMMARY}" || return 1
    fi
    if ((any_red)); then
        return "${EX_RED}"
    fi
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit $?
fi
