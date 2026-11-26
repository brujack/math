#!/usr/bin/env bash
# Runs a Rust crate's mutants through `make` and owns every red rule, in two modes.
#
# Usage: mutation-pr-run.sh <base-ref> [--min-caught N] [--shard k/n [--expect N]] <crate-dir>...
#        mutation-pr-run.sh --whole [--shard k/n [--expect N]] <crate-dir>...
#        (run from repo root)
#
# Diff mode (first form), per crate: build the crate-relative PR diff, run `make -C <dir> mutants-diff`
# on it, then classify the exit code in <dir>/mutants.out/exit-code with limit 0
# (any missed mutant is red) and N as the minimum caught count. A crate selected
# with an empty diff, or one that leaves no exit-code file, is red: both mean the
# run measured nothing. Every verdict goes to stdout; a red crate does not stop
# the loop. Exit 0 when all are green, 1 when any is red, 2 on bad usage.
#
# --shard k/n passes MUTANT_SHARD=k/n to make (an unsharded run passes it empty, overriding any
# MUTANT_SHARD exported in the environment) (same grammar as the Makefile:
# k < n, both without leading zeros). --expect N, which needs --shard, compares the
# shard's outcomes.json total_mutants with the planner's count before classifying; a
# mismatch is red and the classifier does not run. --shard and --expect may each be
# given once, and a sharded run takes exactly one crate (the repro line and the count label
# name one shard of one crate); more than one crate is bad usage.
# Every crate first prints a `repro:` line with the equivalent command.
#
# Whole mode: mutation-pr-run.sh --whole [--shard k/n [--expect N]] <crate-dir>...
# takes no base ref and no diff: it runs `make -C <dir> mutants` (the crate's whole mutant
# set, optionally one shard) and applies the same red rules, classifying with limits `0 1`
# (no missed mutant, at least one caught; ADR-0042). --min-caught is refused: the limit is fixed.

readonly COUNT_PATTERN='^(0|[1-9][0-9]{0,8})$'
readonly SHARD_PATTERN='^(0|[1-9][0-9]{0,3})/([1-9][0-9]{0,3})$'
readonly EXPECT_PATTERN='^[1-9][0-9]{0,8}$'

_usage() {
    printf 'Usage: %s <base-ref> [--min-caught N] [--shard k/n [--expect N]] <crate-dir>...\n' "${0##*/}" >&2
    printf '       %s --whole [--shard k/n [--expect N]] <crate-dir>...\n' "${0##*/}" >&2
}

# Prints `red: <crate> - <reason>` to stdout and returns 1. Every caller follows it with
# `return 1` itself, so the verdict line is the only effect; the status is not consumed.
_red() {
    printf 'red: %s - %s\n' "$1" "$2"
    return 1
}

# run_crate <script-dir> <base-ref> <min-caught-or-empty> <shard-or-empty> <expect-or-empty> <tmp> <index> <crate-dir>
run_crate() {
    local script_dir="$1"
    local base_ref="$2"
    local min_caught="$3"
    local shard="$4"
    local expect="$5"
    local tmp="$6"
    local index="$7"
    local dir="${8%/}"
    local diff_file="${tmp}/${index}.diff"

    local repro="repro: scripts/mutation-pr-run.sh ${base_ref}"
    if [[ -n "${shard}" ]]; then
        repro+=" --shard ${shard}"
    fi
    if [[ -n "${expect}" ]]; then
        repro+=" --expect ${expect}"
    fi
    printf '%s %s\n' "${repro}" "${dir}"

    if ! "${script_dir}/mutation-pr-diff.sh" "${base_ref}" "${dir}" "${diff_file}"; then
        _red "${dir}" "diff failed"
        return 1
    fi
    if [[ ! -s "${diff_file}" ]]; then
        _red "${dir}" "selected but diff empty"
        return 1
    fi

    judge_crate "${script_dir}" "${min_caught}" "${shard}" "${expect}" "${dir}" mutants-diff DIFF="${diff_file}"
}

# judge_crate <script-dir> <min-caught-or-empty> <shard-or-empty> <expect-or-empty> <crate-dir> <make-target> [make-var...]
# Runs the crate's make target, then applies the shared red rules to what it left in mutants.out.
judge_crate() {
    local script_dir="$1"
    local min_caught="$2"
    local shard="$3"
    local expect="$4"
    local dir="$5"
    local target="$6"
    shift 6

    # Clear leftovers so a make that never reaches its recipe cannot pass on a stale run.
    if ! rm -rf -- "${dir}/mutants.out"; then
        _red "${dir}" "cannot clear mutants.out"
        return 1
    fi

    # A failing make is judged by mutants.out/exit-code below, not by its own status.
    # MUTANT_SHARD is always passed, empty when unsharded: a command-line variable beats the
    # environment, so an exported MUTANT_SHARD cannot silently shrink an unsharded run to one shard.
    local make_args=(-C "${dir}" "${target}" "$@" MUTANT_SHARD="${shard}")
    make "${make_args[@]}" || true

    # The shared reader owns the missing-file and integer rules; its one red line comes
    # back on stderr, so fold it into stdout where every verdict of this script goes.
    local code
    if ! code="$(bash "${script_dir}/mutation-exit-code.sh" "${dir}" 2>&1)"; then
        printf '%s\n' "${code}"
        return 1
    fi

    # The count check sits after the exit-code read (a missing file keeps its own red)
    # and before the classifier, which must not bless a shard that tested the wrong set.
    if [[ -n "${expect}" ]]; then
        local count_out
        if ! count_out="$("${script_dir}/mutation-shard-count.sh" "${dir}/mutants.out/outcomes.json" "${dir} shard ${shard}" "${expect}" 2>&1)"; then
            printf '%s\n' "${count_out}"
            return 1
        fi
    fi

    local classify_args=("${code}" "${dir}/mutants.out/outcomes.json" "${dir}" 0)
    if [[ -n "${min_caught}" ]]; then
        classify_args+=("${min_caught}")
    fi
    "${script_dir}/mutation-classify.sh" "${classify_args[@]}" 2>&1
}

# run_crate_whole <script-dir> <shard-or-empty> <expect-or-empty> <crate-dir>
run_crate_whole() {
    local script_dir="$1"
    local shard="$2"
    local expect="$3"
    local dir="${4%/}"

    local repro="repro: scripts/mutation-pr-run.sh --whole"
    if [[ -n "${shard}" ]]; then
        repro+=" --shard ${shard}"
    fi
    if [[ -n "${expect}" ]]; then
        repro+=" --expect ${expect}"
    fi
    printf '%s %s\n' "${repro}" "${dir}"

    judge_crate "${script_dir}" 1 "${shard}" "${expect}" "${dir}" mutants
}

main() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 2

    local whole=0
    local base_ref="${1-}"
    if [[ "${base_ref}" == "--whole" ]]; then
        whole=1
        base_ref=""
        shift
    elif [[ -z "${base_ref}" || "${base_ref}" == -* ]]; then
        _usage
        return 2
    else
        shift
    fi

    local min_caught=""
    local shard=""
    local expect=""
    local dirs=()
    while [[ $# -gt 0 ]]; do
        if [[ "$1" == "--min-caught" ]]; then
            if [[ "${whole}" -eq 1 || $# -lt 2 || ! "$2" =~ ${COUNT_PATTERN} ]]; then
                _usage
                return 2
            fi
            min_caught="$2"
            shift 2
        elif [[ "$1" == "--shard" ]]; then
            if [[ -n "${shard}" || $# -lt 2 || ! "$2" =~ ${SHARD_PATTERN} ]] \
                || ((10#${BASH_REMATCH[1]} >= 10#${BASH_REMATCH[2]})); then
                _usage
                return 2
            fi
            shard="$2"
            shift 2
        elif [[ "$1" == "--expect" ]]; then
            if [[ -n "${expect}" || $# -lt 2 || ! "$2" =~ ${EXPECT_PATTERN} ]]; then
                _usage
                return 2
            fi
            expect="$2"
            shift 2
        elif [[ "$1" == -* ]]; then
            _usage
            return 2
        else
            dirs+=("$1")
            shift
        fi
    done
    if [[ "${#dirs[@]}" -eq 0 || ( -n "${expect}" && -z "${shard}" ) \
        || ( -n "${shard}" && "${#dirs[@]}" -gt 1 ) ]]; then
        _usage
        return 2
    fi

    (
        local tmp
        tmp="$(mktemp -d)" || exit 1
        tmp="$(cd "${tmp}" && pwd)" || exit 1
        trap 'rm -rf -- "${tmp}"' EXIT

        local index=0
        local any_red=0
        local dir
        for dir in "${dirs[@]}"; do
            index=$((index + 1))
            if [[ "${whole}" -eq 1 ]]; then
                run_crate_whole "${script_dir}" "${shard}" "${expect}" "${dir}" || any_red=1
            else
                run_crate "${script_dir}" "${base_ref}" "${min_caught}" "${shard}" "${expect}" "${tmp}" "${index}" "${dir}" || any_red=1
            fi
        done
        exit "${any_red}"
    )
    return "$?"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit "$?"
fi
