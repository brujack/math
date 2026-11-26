#!/usr/bin/env bash
# Plans the Python PR mutation gate: one plan line per project dir, plus the shard units.
#
# Usage: [PY_TEST_DIRS="<dir> ..."] mutation-pr-plan-python.sh <base-sha> [<dir>...]   (run from repo root)
#
# <dir>... are the changed-line (diff) dirs. PY_TEST_DIRS (space-separated, as printed by
# mutation-pr-detect.sh `py_test_dirs=`) are planned as whole-module "weakening" shards instead,
# n = min(40, max(10, ceil(K * s / 600))); a dir in both lists is planned once, as weakening.
# K is the whole-module mutant count after the head prune, s the head suite's wall seconds.
# Seams (executables, `<cmd> <dir>` prints one number; unset runs the real measurement):
#   MUTATION_PR_WEAKENING_K, MUTATION_PR_SUITE_SECONDS
# A missing or non-numeric K or s, or a failing seam, aborts the plan non-zero (never a default n).
#
# Writes plan.txt and units.json to ${PLAN_OUT:-.}; appends a table to ${GITHUB_STEP_SUMMARY} when set.
# plan.txt holds exactly one line per dir, `<dir>\t<green|red>\t<text>`; the verdict script
# (mutation-pr-verdict-python.sh) parses it, so the green/red texts below are a pinned contract:
#   `<K> mutants in <n> shards`, `0 mutants on changed lines`, `lines 0`, or a flattened error.
# units.json rows: diff mode {"dir":..,"k":..,"n":..,"mode":"diff"} for green dirs with K > 0 only,
# weakening mode {"dir":..,"k":..,"n":..,"mode":"weakening"}; [] when none.
# Zero dirs is valid (an empty plan and []), so the caller never special-cases "nothing changed".

readonly SHARD_SIZE=150
readonly MAX_SHARDS=10
readonly WEAK_MIN_SHARDS=10
readonly WEAK_MAX_SHARDS=40
readonly WEAK_BUDGET_SECONDS=600
readonly TAB=$'\t'
readonly FENCE=$'\x60\x60\x60'

# Overridable so tests can substitute the diff writer.
readonly DIFF_SCRIPT="${MUTATION_PR_DIFF:-$(dirname "${BASH_SOURCE[0]}")/mutation-pr-diff.sh}"

# Shard count: min(MAX_SHARDS, max(1, ceil(K / SHARD_SIZE))).
shard_count() {
    local kept="$1" n
    n=$(((kept + SHARD_SIZE - 1) / SHARD_SIZE))
    ((n < 1)) && n=1
    ((n > MAX_SHARDS)) && n="${MAX_SHARDS}"
    printf '%s\n' "${n}"
}

# Joins lines with " | " and drops CR so multi-line stderr is one plan line.
flatten() {
    local text="$1"
    text="${text//$'\r'/}"
    text="${text//$'\t'/ }"
    text="${text//$'\n'/ | }"
    printf '%s\n' "${text}"
}

# JSON string escape for the dir name (fixed ASCII in practice; quoted anyway).
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    printf '%s' "${s}"
}

# Plans one dir. Sets PLAN_LINE (without dir) and appends to UNITS.
# Full stderr goes to the summary through SUMMARY_BODY.
plan_dir() {
    local base="$1" dir="$2"
    local diff_file="${WORK}/${dir//\//_}.diff" err out rc

    err="$("${DIFF_SCRIPT}" "${base}" "${dir}" "${diff_file}" 2>&1 >/dev/null)"
    rc=$?
    if ((rc != 0)); then
        SUMMARY_BODY+="${dir}: diff step failed:"$'\n'"${err}"$'\n'
        PLAN_LINE="red${TAB}diff step failed: $(flatten "${err}")"
        return 0
    fi

    local errfile="${WORK}/${dir//\//_}.err"
    out="$(make -C "${dir}" mutants-diff-plan DIFF="${diff_file}" 2>"${errfile}")"
    rc=$?
    err="$(cat "${errfile}")"
    if ((rc != 0)); then
        SUMMARY_BODY+="${dir}: mutants-diff-plan failed:"$'\n'"${err}"$'\n'
        PLAN_LINE="red${TAB}mutants-diff-plan failed: $(flatten "${err}")"
        return 0
    fi

    local kept="" total="" lines="" line bad=0 excl_n=0 kept_n=0
    local re_kept='^kept ([0-9]+) of ([0-9]+) \(lines ([0-9]+)\)$'
    local re_excl='^excluded [0-9]+ of [0-9]+ \(re-confirm: .*\)$'
    while IFS= read -r line; do
        line="${line//$'\r'/}"
        if [[ "${line}" =~ ${re_kept} ]]; then
            # Exactly one kept line, and only after the excluded line.
            ((kept_n > 0 || excl_n == 0)) && bad=1
            ((kept_n++))
            kept="${BASH_REMATCH[1]}"
            total="${BASH_REMATCH[2]}"
            lines="${BASH_REMATCH[3]}"
        elif [[ "${line}" =~ ${re_excl} ]]; then
            ((excl_n > 0 || kept_n > 0)) && bad=1
            ((excl_n++))
        fi
    done <<<"${out}"

    if ((bad == 0 && (excl_n != 1 || kept_n != 1))); then
        bad=1
    fi
    if ((bad == 0 && 10#${kept} > 10#${total})); then
        bad=1
    fi
    if ((bad != 0)); then
        SUMMARY_BODY+="${dir}: unparseable prune output:"$'\n'"${out}"$'\n'
        PLAN_LINE="red${TAB}unparseable prune output: $(flatten "${out}")"
        if [[ -n "${err}" ]]; then
            SUMMARY_BODY+="stderr:"$'\n'"${err}"$'\n'
            PLAN_LINE+=" | stderr: $(flatten "${err}")"
        fi
        return 0
    fi

    # Force base 10: a leading zero must not read as octal.
    kept=$((10#${kept}))
    lines=$((10#${lines}))
    if ((lines == 0)); then
        PLAN_LINE="red${TAB}lines 0"
        if [[ -n "${err}" ]]; then
            SUMMARY_BODY+="${dir}: lines 0, prune stderr:"$'\n'"${err}"$'\n'
            PLAN_LINE+=": $(flatten "${err}")"
        fi
    elif ((kept == 0)); then
        PLAN_LINE="green${TAB}0 mutants on changed lines"
    else
        local n k
        n="$(shard_count "${kept}")" || return 1
        PLAN_LINE="green${TAB}${kept} mutants in ${n} shards"
        for ((k = 0; k < n; k++)); do
            UNITS+=("{\"dir\":\"$(json_escape "${dir}")\",\"k\":${k},\"n\":${n},\"mode\":\"diff\"}")
        done
    fi
    return 0
}

# Real K measurement: the head prune over a diff that adds the whole module, so every
# non-equivalent mutant is "on a changed line". Prints K.
whole_module_mutant_count() {
    local dir="$1" module diff_file out empty_tree
    module="${dir//-/_}.py"
    diff_file="${WORK}/${dir//\//_}.whole.diff"
    empty_tree="$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git hash-object -t tree /dev/null)" || return 1
    env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git -c core.quotePath=false diff --no-color --no-ext-diff --src-prefix=a/ --dst-prefix=b/ \
        --relative="${dir}/" "${empty_tree}" HEAD -- "${dir}/${module}" >"${diff_file}" || return 1
    out="$(make -C "${dir}" mutants-diff-plan DIFF="${diff_file}")" || return 1
    local re_kept='^kept ([0-9]+) of [0-9]+ \(lines [0-9]+\)$' line count=""
    while IFS= read -r line; do
        [[ "${line//$'\r'/}" =~ ${re_kept} ]] && count="${BASH_REMATCH[1]}"
    done <<<"${out}"
    [[ -n "${count}" ]] || return 1
    printf '%s\n' "${count}"
}

# Real s measurement: wall seconds of the head suite on the unmutated module. Prints seconds.
head_suite_seconds() {
    local dir="$1" start end
    start="${EPOCHREALTIME}"
    (cd "${dir}" && python3 -m unittest "test_${dir//-/_}" >/dev/null 2>&1 </dev/null) || return 1
    end="${EPOCHREALTIME}"
    printf '%s\n' "$(((${end/./} - ${start/./}) / 1000000)).$((((${end/./} - ${start/./}) % 1000000 + 999999) / 1000000))"
}

# Runs a seam (the env override, else the real measurement) and validates its output as a
# non-negative decimal. Prints it; returns 1 with a message naming the dir and the quantity.
measure() {
    local what="$1" dir="$2" seam="$3" fallback="$4" value
    if [[ -n "${seam}" ]]; then
        value="$("${seam}" "${dir}")" || {
            printf '%s: %s command failed\n' "${dir}" "${what}" >&2
            return 1
        }
    else
        value="$("${fallback}" "${dir}")" || {
            printf '%s: %s measurement failed\n' "${dir}" "${what}" >&2
            return 1
        }
    fi
    if [[ ! "${value}" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        printf '%s: %s is not a non-negative number: %q\n' "${dir}" "${what}" "${value}" >&2
        return 1
    fi
    printf '%s\n' "${value}"
}

# Whole seconds, rounded up: "0.4" -> 1, "3.0" -> 3, "08" -> 8.
ceil_seconds() {
    local value="$1" whole frac=""
    whole="${value%%.*}"
    [[ "${value}" == *.* ]] && frac="${value#*.}"
    whole=$((10#${whole}))
    [[ "${frac}" =~ [1-9] ]] && ((whole++))
    printf '%s\n' "${whole}"
}

# Shard count: min(40, max(10, ceil(K * s / 600))), integer arithmetic only.
weakening_shard_count() {
    local kept="$1" secs="$2" n
    n=$(((kept * secs + WEAK_BUDGET_SECONDS - 1) / WEAK_BUDGET_SECONDS))
    ((n < WEAK_MIN_SHARDS)) && n="${WEAK_MIN_SHARDS}"
    ((n > WEAK_MAX_SHARDS)) && n="${WEAK_MAX_SHARDS}"
    printf '%s\n' "${n}"
}

# Plans one py_test_dirs dir as whole-module weakening shards. Sets PLAN_LINE and appends to UNITS.
# Returns 1 (fail closed) when K or s cannot be measured.
plan_weakening_dir() {
    local dir="$1" kept secs n k
    kept="$(measure 'mutant count' "${dir}" "${MUTATION_PR_WEAKENING_K:-}" whole_module_mutant_count)" || return 1
    secs="$(measure 'suite time' "${dir}" "${MUTATION_PR_SUITE_SECONDS:-}" head_suite_seconds)" || return 1
    kept=$((10#${kept}))
    secs="$(ceil_seconds "${secs}")"
    n="$(weakening_shard_count "${kept}" "${secs}")" || return 1
    PLAN_LINE="green${TAB}${kept} mutants in ${n} shards"
    for ((k = 0; k < n; k++)); do
        UNITS+=("{\"dir\":\"$(json_escape "${dir}")\",\"k\":${k},\"n\":${n},\"mode\":\"weakening\"}")
    done
    return 0
}

main() {
    if [[ "$#" -lt 1 ]]; then
        printf 'Usage: %s <base-sha> [<dir>...]\n' "${0##*/}" >&2
        return 2
    fi

    local base="$1"
    shift
    local out_dir="${PLAN_OUT:-.}"
    mkdir -p "${out_dir}" || return 1

    WORK="$(mktemp -d)" || return 1
    # shellcheck disable=SC2064
    trap "rm -rf '${WORK}'" EXIT

    UNITS=()
    SUMMARY_BODY=""
    local plan="" dir test_dirs=() planned=" "
    read -ra test_dirs <<<"${PY_TEST_DIRS:-}"
    for dir in "${test_dirs[@]}"; do
        dir="${dir%/}"
        [[ "${planned}" == *" ${dir} "* ]] && continue
        planned+="${dir} "
        PLAN_LINE=""
        plan_weakening_dir "${dir}" || return 1
        plan+="${dir}${TAB}${PLAN_LINE}"$'\n'
    done
    for dir in "$@"; do
        dir="${dir%/}"
        [[ "${planned}" == *" ${dir} "* ]] && continue
        planned+="${dir} "
        PLAN_LINE=""
        plan_dir "${base}" "${dir}" || return 1
        plan+="${dir}${TAB}${PLAN_LINE}"$'\n'
    done

    printf '%s' "${plan}" >"${out_dir}/plan.txt" || return 1

    local json="[" sep="" unit
    for unit in "${UNITS[@]}"; do
        json+="${sep}${unit}"
        sep=","
    done
    printf '%s]\n' "${json}" >"${out_dir}/units.json" || return 1

    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        {
            printf '### Python mutation plan\n\n'
            if [[ -z "${plan}" ]]; then
                printf 'No Python projects to mutate.\n'
            else
                printf '| dir | verdict | detail |\n| --- | --- | --- |\n'
                local d v t
                while IFS="${TAB}" read -r d v t; do
                    printf '| %s | %s | %s |\n' "${d}" "${v}" "${t//|/\\|}"
                done <<<"${plan%$'\n'}"
            fi
            if [[ -n "${SUMMARY_BODY}" ]]; then
                printf '\n%s\n%s%s\n' "${FENCE}" "${SUMMARY_BODY}" "${FENCE}"
            fi
        } >>"${GITHUB_STEP_SUMMARY}" || return 1
    fi
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit "$?"
fi
