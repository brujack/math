#!/usr/bin/env bash
# Runs one cosmic-ray shard cell (<dir> <k> <n>) for a Python sub-project.
#
# Stale outputs are removed first so a status file from an earlier run can
# never stand in for this one. When the recipe dies before writing a status
# (init, exec or report failure), a red line is written in its place so the
# merge job always has a verdict for every cell.

readonly PYTHON_DIRS="amicable collatz e factorial fib perfect-numbers pi sq"

usage_error() {
    printf 'mutation-python-cell: %s\n' "$1" >&2
    return 2
}

validate_args() {
    local _dir="$1" _k="$2" _n="$3" _d
    [[ "$#" -eq 3 ]] || { usage_error "usage: <dir> <k> <n>"; return 2; }
    for _d in ${PYTHON_DIRS}; do
        [[ "${_d}" == "${_dir}" ]] && break
        _d=""
    done
    [[ -n "${_d}" ]] || { usage_error "unknown Python sub-project '${_dir}'"; return 2; }
    [[ "${_k}" =~ ^[0-9]+$ ]] || { usage_error "k must be a plain decimal, got '${_k}'"; return 2; }
    [[ "${_n}" =~ ^[0-9]+$ ]] || { usage_error "n must be a plain decimal, got '${_n}'"; return 2; }
    return 0
}

main() {
    validate_args "$@" || return 2
    local _dir="$1" _k="$2" _n="$3"
    [[ -n "${GITHUB_WORKSPACE:-}" ]] || { printf 'mutation-python-cell: GITHUB_WORKSPACE unset\n' >&2; return 2; }
    local _unit="${_dir}-${_k}"
    local _out="${GITHUB_WORKSPACE}/status/${_unit}"
    local _surv="${GITHUB_WORKSPACE}/survivors/${_unit}.txt"
    mkdir -p "${GITHUB_WORKSPACE}/status" "${GITHUB_WORKSPACE}/survivors" || return 1
    if [[ -e "${_out}" && ! -f "${_out}" ]]; then
        printf 'mutation-python-cell: %s is not a regular file\n' "${_out}" >&2
        return 2
    fi
    rm -f "${_out}" "${_surv}" || return 1

    local _rc=0
    make -C "${_dir}" mutants MUTANT_SHARD="${_k}/${_n}" CELL_LABEL="${_unit}" \
        STATUS_OUT="${_out}" SURVIVORS_OUT="${_surv}" || _rc=$?

    if [[ ! -f "${_out}" ]]; then
        [[ "${_rc}" -eq 0 ]] && _rc=1
        printf 'red: %s — make mutants failed (exit %s)\n' "${_unit}" "${_rc}" > "${_out}" || return 1
    fi
    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        cat "${_out}" >> "${GITHUB_STEP_SUMMARY}" || return 1
    fi
    return "${_rc}"
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0

main "$@" || exit $?
