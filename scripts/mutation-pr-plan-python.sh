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
# weakening mode {"dir":..,"k":..,"n":..,"mode":"weakening","planned":..}; [] when none.
# `planned` is the job count of slice k under cosmic_ray_shard.py's round-robin split (sorted index
# i belongs to shard i % n), so K // n plus one when k < K % n; the planned counts sum to K.
# Zero dirs is valid (an empty plan and []), so the caller never special-cases "nothing changed".

readonly SHARD_SIZE=150
readonly MAX_SHARDS=10
readonly WEAK_MIN_SHARDS=10
readonly WEAK_MAX_SHARDS=40
readonly WEAK_BUDGET_MS=600000
readonly TAB=$'\t'
readonly FENCE=$'\x60\x60\x60'

# Overridable so tests can substitute the diff writer.
readonly WHOLE_MODULE_DIFF="${MUTATION_WHOLE_MODULE_DIFF:-$(dirname "${BASH_SOURCE[0]}")/mutation-whole-module-diff.sh}"
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

# Strict parse of the prune summary (stdout of `make mutants-diff-plan`): exactly one `excluded`
# line, then exactly one `kept K of T (lines L)` line, K <= T. Sets P_KEPT, P_TOTAL, P_LINES
# (decimal, leading zeros stripped); returns 1 on anything else.
parse_prune_summary() {
    local out="$1" line bad=0 excl_n=0 kept_n=0
    local re_kept='^kept ([0-9]+) of ([0-9]+) \(lines ([0-9]+)\)$'
    local re_excl='^excluded [0-9]+ of [0-9]+ \(re-confirm: .*\)$'
    P_KEPT="" P_TOTAL="" P_LINES=""
    while IFS= read -r line; do
        line="${line//$'\r'/}"
        if [[ "${line}" =~ ${re_kept} ]]; then
            # Exactly one excluded line, then exactly one kept line: the order checks reject
            # duplicates and kept-before-excluded, the final count check a missing kept line.
            ((kept_n > 0 || excl_n == 0)) && bad=1
            ((kept_n++))
            P_KEPT="${BASH_REMATCH[1]}"
            P_TOTAL="${BASH_REMATCH[2]}"
            P_LINES="${BASH_REMATCH[3]}"
        elif [[ "${line}" =~ ${re_excl} ]]; then
            ((excl_n > 0 || kept_n > 0)) && bad=1
            ((excl_n++))
        fi
    done <<<"${out}"
    ((kept_n != 1)) && bad=1
    ((bad == 0 && 10#${P_KEPT} > 10#${P_TOTAL})) && bad=1
    ((bad != 0)) && return 1
    # Force base 10: a leading zero must not read as octal.
    P_KEPT=$((10#${P_KEPT}))
    P_TOTAL=$((10#${P_TOTAL}))
    P_LINES=$((10#${P_LINES}))
    return 0
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

    local kept lines bad=0
    parse_prune_summary "${out}" || bad=1
    kept="${P_KEPT}"
    lines="${P_LINES}"
    if ((bad != 0)); then
        SUMMARY_BODY+="${dir}: unparseable prune output:"$'\n'"${out}"$'\n'
        PLAN_LINE="red${TAB}unparseable prune output: $(flatten "${out}")"
        if [[ -n "${err}" ]]; then
            SUMMARY_BODY+="stderr:"$'\n'"${err}"$'\n'
            PLAN_LINE+=" | stderr: $(flatten "${err}")"
        fi
        return 0
    fi

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

# Real K measurement: the head prune over the whole-module diff (mutation-whole-module-diff.sh,
# shared with the weakening head session), so every non-equivalent mutant counts. Prints K.
whole_module_mutant_count() {
    local dir="$1" diff_file out
    diff_file="${WORK}/${dir//\//_}.whole.diff"
    "${WHOLE_MODULE_DIFF}" "${dir}" "${diff_file}" || return 1
    out="$(make -C "${dir}" mutants-diff-plan DIFF="${diff_file}")" || return 1
    parse_prune_summary "${out}" || {
        printf '%s: unparseable prune output: %s\n' "${dir}" "$(flatten "${out}")" >&2
        return 1
    }
    printf '%s\n' "${P_KEPT}"
}

# Microsecond clock reading. MUTATION_PR_CLOCK_US (an executable printing one integer) replaces it in tests.
now_us() {
    local reading
    if [[ -n "${MUTATION_PR_CLOCK_US:-}" ]]; then
        reading="$("${MUTATION_PR_CLOCK_US}")" || return 1
    else
        reading="${EPOCHREALTIME/[.,]/}"
    fi
    [[ "${reading}" =~ ^[0-9]+$ ]] || return 1
    printf '%s\n' "${reading}"
}

# Real s measurement: wall time of the head suite on the unmutated module, under the shard's
# environment (fixed hash seed, no bytecode writes), capped at 600 s. Prints seconds as S.mmm.
head_suite_seconds() {
    local dir="$1" start end rc ms
    start="$(now_us)" || return 1
    (cd "${dir}" && env PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 timeout 600 python3 -m unittest "test_${dir//-/_}" >/dev/null 2>&1 </dev/null)
    rc=$?
    if ((rc == 124)); then
        printf '%s: suite timed out after 600 s\n' "${dir}" >&2
        return 1
    fi
    ((rc == 0)) || return 1
    end="$(now_us)" || return 1
    ms=$(((end - start + 999) / 1000))
    printf '%s.%03d\n' "$((ms / 1000))" "$((ms % 1000))"
}

# Runs a seam (the env override, else the real measurement) and validates its output as a
# non-negative decimal. Prints it; returns 1 with a message naming the dir and the quantity.
measure() {
    local what="$1" dir="$2" seam="$3" fallback="$4" re="$5" value
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
    if [[ ! "${value}" =~ ${re} ]]; then
        printf '%s: %s is not a non-negative number: %q\n' "${dir}" "${what}" "${value}" >&2
        return 1
    fi
    printf '%s\n' "${value}"
}

# Decimal seconds to whole milliseconds, rounded up: "0.5" -> 500, "1.0005" -> 1001, "08" -> 8000.
seconds_to_ms() {
    local value="$1" whole frac=""
    [[ "${value}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || return 1
    whole="${value%%.*}"
    [[ "${value}" == *.* ]] && frac="${value#*.}"
    local head="${frac:0:3}" rest="${frac:3}"
    head="${head}000"
    head="${head:0:3}"
    local ms=$((10#${whole} * 1000 + 10#${head}))
    [[ "${rest}" =~ [1-9] ]] && ((ms++))
    printf '%s\n' "${ms}"
}

# Shard count per R6: min(40, max(10, ceil(K * s / 600))) with s in integer milliseconds.
weakening_shard_count() {
    local kept="$1" ms="$2" n
    n=$(((kept * ms + WEAK_BUDGET_MS - 1) / WEAK_BUDGET_MS))
    ((n < WEAK_MIN_SHARDS)) && n="${WEAK_MIN_SHARDS}"
    ((n > WEAK_MAX_SHARDS)) && n="${WEAK_MAX_SHARDS}"
    printf '%s\n' "${n}"
}

# Plans one py_test_dirs dir as whole-module weakening shards. Sets PLAN_LINE and appends to UNITS.
# Returns 1 (fail closed) when K or s cannot be measured.
plan_weakening_dir() {
    local dir="$1" kept secs ms n k
    kept="$(measure 'mutant count' "${dir}" "${MUTATION_PR_WEAKENING_K:-}" whole_module_mutant_count '^[0-9]+$')" || return 1
    secs="$(measure 'suite time' "${dir}" "${MUTATION_PR_SUITE_SECONDS:-}" head_suite_seconds '^[0-9]+(\.[0-9]+)?$')" || return 1
    kept=$((10#${kept}))
    ms="$(seconds_to_ms "${secs}")" || {
        printf '%s: suite time is not a non-negative number: %q\n' "${dir}" "${secs}" >&2
        return 1
    }
    n="$(weakening_shard_count "${kept}" "${ms}")" || return 1
    PLAN_LINE="green${TAB}${kept} mutants in ${n} shards"
    local planned
    for ((k = 0; k < n; k++)); do
        planned=$((kept / n))
        ((k < kept % n)) && ((planned++))
        UNITS+=("{\"dir\":\"$(json_escape "${dir}")\",\"k\":${k},\"n\":${n},\"mode\":\"weakening\",\"planned\":${planned}}")
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
