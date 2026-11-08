#!/usr/bin/env bash
# Decides which Python sub-projects a PR's mutation run covers.
#
# Prints `py_dirs=<sorted dirs>` and `has_py=true|false` for GITHUB_OUTPUT.
# A change to shared Python tooling (templates, *-py.yml, a Python
# install_deps.sh, mutation-pr.yml) selects every Python dir; otherwise each
# `<dir>/*.py` directly under a Python dir selects that dir. The nested
# <dir>/<dir>-rs/ tree is Rust and never matches.
#
# Then prints `rs_dirs=<sorted crate dirs>`, `has_rs=true|false` and
# `rs_canary=true|false`. A crate dir (passed as arguments to detect) is
# selected when a changed path is `<crate>/src/**/*.rs`. rs_canary is true when
# a file that shapes the Rust mutation run itself changed.
#
# Finally prints `py_src_dirs=<sorted dirs>` and `py_canary=true|false`. A Python
# dir is in py_src_dirs only when `git diff --numstat --no-renames` shows more
# than 0 added lines in `<dir>/<module>.py` (module = dir with `-` as `_`): a
# deletion-only or mode-only change leaves no new line to mutate. py_canary is
# true when a file that shapes the Python mutation run itself changed.

readonly PYTHON_DIRS="amicable collatz e factorial fib perfect-numbers pi sq triangle"

readonly RS_CANARY_PATHS=".github/workflows/mutation-pr.yml scripts/mutation-pr-detect.sh scripts/mutation-pr-diff.sh scripts/mutation-pr-run.sh scripts/mutation-classify.sh scripts/crate_templates/Makefile amicable/amicable-rs/src/lib.rs"

readonly PY_CANARY_PATHS=".github/workflows/mutation-pr.yml scripts/mutation-pr-detect.sh scripts/mutation-pr-diff.sh scripts/mutation-pr-plan-python.sh scripts/mutation-pr-verdict-python.sh scripts/cosmic_ray_prune.py scripts/cosmic_ray_cell_status.py scripts/crate_templates/python/Makefile sq/sq.py sq/mutants-equivalent.toml"

# Stdin is `git diff --numstat --no-renames` output (added<TAB>deleted<TAB>path).
# Prints the sorted, space-joined Python dirs whose module gained lines. A binary
# file shows `-` for added and is not selected.
py_src_dirs() {
    local _added _deleted _path _d _m
    local -a _sel=()
    while IFS=$'\t' read -r _added _deleted _path; do
        [[ "${_added}" =~ ^[0-9]+$ && "${_added}" -gt 0 ]] || continue
        for _d in ${PYTHON_DIRS}; do
            _m="${_d//-/_}"
            [[ "${_path}" == "${_d}/${_m}.py" ]] && _sel+=("${_d}")
        done
    done
    if [[ "${#_sel[@]}" -gt 0 ]]; then
        printf '%s\n' "${_sel[@]}" | sort -u | paste -sd' ' - || return 1
    else
        printf '\n'
    fi
}

# Args are the Rust crate dirs; stdin is the changed paths.
detect() {
    local _path _d _c _all=0 _canary=false _py_canary=false
    local -a _sel=() _rs=()
    while IFS= read -r _path; do
        [[ -n "${_path}" ]] || continue
        case "${_path}" in
            scripts/crate_templates/python/* | .github/workflows/mutation-pr.yml)
                _all=1 ;;
            .github/workflows/*-py.yml)
                _all=1 ;;
        esac
        for _c in ${RS_CANARY_PATHS}; do
            [[ "${_path}" == "${_c}" ]] && _canary=true
        done
        for _c in ${PY_CANARY_PATHS}; do
            [[ "${_path}" == "${_c}" ]] && _py_canary=true
        done
        for _c in "$@"; do
            [[ "${_path}" == "${_c}/src/"*.rs ]] && _rs+=("${_c}")
        done
        for _d in ${PYTHON_DIRS}; do
            if [[ "${_path}" == "${_d}/install_deps.sh" ]]; then
                _all=1
            elif [[ "${_path}" == "${_d}/"*.py && "${_path#"${_d}/"}" != */* ]]; then
                _sel+=("${_d}")
            fi
        done
    done
    local _rs_list=""
    if [[ "${#_rs[@]}" -gt 0 ]]; then
        _rs_list=$(printf '%s\n' "${_rs[@]}" | sort -u | paste -sd' ' -) || return 1
    fi
    if [[ "${_all}" -eq 1 ]]; then
        printf 'py_dirs=%s\nhas_py=true\n' "${PYTHON_DIRS}"
    else
        local _list=""
        if [[ "${#_sel[@]}" -gt 0 ]]; then
            _list=$(printf '%s\n' "${_sel[@]}" | sort -u | paste -sd' ' -) || return 1
        fi
        printf 'py_dirs=%s\n' "${_list}"
        if [[ -n "${_list}" ]]; then printf 'has_py=true\n'; else printf 'has_py=false\n'; fi
    fi
    printf 'rs_dirs=%s\n' "${_rs_list}"
    if [[ -n "${_rs_list}" ]]; then printf 'has_rs=true\n'; else printf 'has_rs=false\n'; fi
    printf 'rs_canary=%s\n' "${_canary}"
    printf 'py_src_dirs=%s\n' "${PY_SRC_DIRS:-}"
    printf 'py_canary=%s\n' "${_py_canary}"
}

main() {
    if [[ "$#" -ne 1 || -z "$1" ]]; then
        printf 'usage: mutation-pr-detect.sh <base-ref>\n' >&2
        return 2
    fi
    local _names
    _names=$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git diff --name-only "$1...HEAD") || return 1
    local _numstat _src _manifests _path
    _numstat=$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git diff --numstat --no-renames "$1...HEAD") || return 1
    _src=$(py_src_dirs <<< "${_numstat}") || return 1
    local -a _crates=()
    _manifests=$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git ls-files '*/*-rs/Cargo.toml') || return 1
    while IFS= read -r _path; do
        [[ -n "${_path}" ]] && _crates+=("${_path%/Cargo.toml}")
    done <<< "${_manifests}"
    PY_SRC_DIRS="${_src}" detect "${_crates[@]}" <<< "${_names}"
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0

main "$@" || exit $?
