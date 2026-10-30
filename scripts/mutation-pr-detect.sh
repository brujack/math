#!/usr/bin/env bash
# Decides which Python sub-projects a PR's mutation run covers.
#
# Prints `py_dirs=<sorted dirs>` and `has_py=true|false` for GITHUB_OUTPUT.
# A change to shared Python tooling (templates, *-py.yml, a Python
# install_deps.sh, mutation-pr.yml) selects all eight; otherwise each
# `<dir>/*.py` directly under a Python dir selects that dir. The nested
# <dir>/<dir>-rs/ tree is Rust and never matches.

readonly PYTHON_DIRS="amicable collatz e factorial fib perfect-numbers pi sq"

detect() {
    local _path _d _all=0
    local -a _sel=()
    while IFS= read -r _path; do
        [[ -n "${_path}" ]] || continue
        case "${_path}" in
            scripts/crate_templates/python/* | .github/workflows/mutation-pr.yml)
                _all=1 ;;
            .github/workflows/*-py.yml)
                _all=1 ;;
        esac
        for _d in ${PYTHON_DIRS}; do
            if [[ "${_path}" == "${_d}/install_deps.sh" ]]; then
                _all=1
            elif [[ "${_path}" == "${_d}/"*.py && "${_path#"${_d}/"}" != */* ]]; then
                _sel+=("${_d}")
            fi
        done
    done
    if [[ "${_all}" -eq 1 ]]; then
        printf 'py_dirs=%s\nhas_py=true\n' "${PYTHON_DIRS}"
        return 0
    fi
    local _list=""
    if [[ "${#_sel[@]}" -gt 0 ]]; then
        _list=$(printf '%s\n' "${_sel[@]}" | sort -u | paste -sd' ' -) || return 1
    fi
    printf 'py_dirs=%s\n' "${_list}"
    if [[ -n "${_list}" ]]; then printf 'has_py=true\n'; else printf 'has_py=false\n'; fi
}

main() {
    if [[ "$#" -ne 1 || -z "$1" ]]; then
        printf 'usage: mutation-pr-detect.sh <base-ref>\n' >&2
        return 2
    fi
    local _names
    _names=$(git diff --name-only "$1...HEAD") || return 1
    detect <<< "${_names}"
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0

main "$@" || exit $?
