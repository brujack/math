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
# selected when a changed path starts with `<crate>/src/`, `<crate>/tests/` or
# `<crate>/.cargo/` (any extension), is `<crate>/build.rs`, or is
# `<crate>/Cargo.toml` with a changed line that is neither inside its
# `[dependencies]`, `[dev-dependencies]` or `[build-dependencies]` table nor the
# `[package]` `version` line. rs_canary is true when a file that
# shapes the Rust mutation run itself changed.
#
# Then prints `py_src_dirs=<sorted dirs>` and `py_canary=true|false`. A Python
# dir is in py_src_dirs only when `git diff --numstat --no-renames` shows more
# than 0 added lines in `<dir>/<module>.py` (module = dir with `-` as `_`): a
# deletion-only or mode-only change leaves no new line to mutate. py_canary is
# true when a file that shapes the Python mutation run itself changed.
#
# Finally prints `py_test_dirs=<sorted dirs>`: a Python dir with any added or
# deleted line (a file deletion included) in `<dir>/test_<module>.py`,
# `<dir>/cosmic-ray.toml` or `<dir>/mutants-equivalent.toml`.

readonly PYTHON_DIRS="amicable collatz descartes e factorial fib perfect-numbers pi sq triangle"

readonly RS_CANARY_PATHS=".github/workflows/mutation-pr.yml scripts/mutation-pr-detect.sh scripts/mutation-pr-diff.sh scripts/mutation-pr-run.sh scripts/mutation-classify.sh scripts/crate_templates/Makefile amicable/amicable-rs/src/lib.rs scripts/mutation-rs-plan.sh scripts/mutation-exit-code.sh scripts/mutation-shard-count.sh"

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

# Stdin is `git diff --numstat --no-renames` output. Prints the sorted, space-joined
# Python dirs whose test file or mutation config gained or lost any line. A
# binary file shows `-` and counts as changed; a mode-only change shows 0 and 0.
py_test_dirs() {
    local _added _deleted _path _d _m
    local -a _sel=()
    while IFS=$'\t' read -r _added _deleted _path; do
        [[ "${_added}" != 0 || "${_deleted}" != 0 ]] || continue
        for _d in ${PYTHON_DIRS}; do
            _m="${_d//-/_}"
            case "${_path}" in
                "${_d}/test_${_m}.py" | "${_d}/cosmic-ray.toml" | "${_d}/mutants-equivalent.toml")
                    _sel+=("${_d}") ;;
            esac
        done
    done
    if [[ "${#_sel[@]}" -gt 0 ]]; then
        printf '%s\n' "${_sel[@]}" | sort -u | paste -sd' ' - || return 1
    else
        printf '\n'
    fi
}

# Returns 0 when a changed Cargo.toml line counts: it is neither inside one of
# the three dependency tables (`[dependencies.<name>]` belongs to the first) nor
# the `[package]` `version` line. Args: table header (no closing `]`), line text.
cargo_line_counts() {
    local _dep='^\[(dev-|build-)?dependencies(\..+)?$'
    [[ "$1" =~ ${_dep} ]] && return 1
    [[ "$1" == "[package" && "$2" =~ ^version[[:space:]]*= ]] && return 1
    return 0
}

# Stdin is a full-context unified diff of one Cargo.toml (`git diff -U1000000`).
# Returns 0 when a changed line counts (see cargo_line_counts). Two tables are
# tracked: a context or `-` line moves the base-side one, a context or `+` line
# the head-side one, so each changed line is judged against the table it sat in
# on its own side of the diff, not one the same hunk removed or added.
# Known limit: a table header inside a multi-line string is read as a header.
cargo_toml_changed() {
    local _line _c _t _base="" _head="" _body=0 _sec
    local _hdr='^\[\[?[^]]+\]\]?[[:space:]]*(#.*)?$'
    while IFS= read -r _line; do
        if [[ "${_body}" -eq 0 ]]; then
            [[ "${_line}" == @@* ]] && _body=1
            continue
        fi
        _c="${_line:0:1}"
        _t="${_line:1}"
        _t="${_t#"${_t%%[![:space:]]*}"}"
        _sec=""
        [[ "${_t}" =~ ${_hdr} ]] && _sec="${_t%%]*}"
        case "${_c}" in
            ' ')
                [[ -n "${_sec}" ]] && { _base="${_sec}"; _head="${_sec}"; } ;;
            '-')
                [[ -n "${_sec}" ]] && _base="${_sec}"
                ! cargo_line_counts "${_base}" "${_t}" || return 0 ;;
            '+')
                [[ -n "${_sec}" ]] && _head="${_sec}"
                ! cargo_line_counts "${_head}" "${_t}" || return 0 ;;
        esac
    done
    return 1
}

# Args: base ref, the changed paths, then the crate dirs. Prints the sorted,
# space-joined crates whose Cargo.toml changed outside the dependency tables.
cargo_crates_changed() {
    local _base="$1" _names="$2" _c _diff
    shift 2
    local -a _sel=()
    for _c in "$@"; do
        [[ $'\n'"${_names}"$'\n' == *$'\n'"${_c}/Cargo.toml"$'\n'* ]] || continue
        _diff=$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
            git diff -U1000000 --no-renames "${_base}...HEAD" -- "${_c}/Cargo.toml") || return 1
        if cargo_toml_changed <<< "${_diff}"; then _sel+=("${_c}"); fi
    done
    if [[ "${#_sel[@]}" -gt 0 ]]; then
        printf '%s\n' "${_sel[@]}" | sort -u | paste -sd' ' - || return 1
    else
        printf '\n'
    fi
}

# Args are the Rust crate dirs; stdin is the changed paths. CARGO_CRATES and
# PY_SRC_DIRS / PY_TEST_DIRS carry the diff-derived selections.
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
            case "${_path}" in
                "${_c}/src/"* | "${_c}/tests/"* | "${_c}/.cargo/"* | "${_c}/build.rs") _rs+=("${_c}") ;;
            esac
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
    for _c in ${CARGO_CRATES:-}; do _rs+=("${_c}"); done
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
    printf 'py_test_dirs=%s\n' "${PY_TEST_DIRS:-}"
}

main() {
    if [[ "$#" -ne 1 || -z "$1" ]]; then
        printf 'usage: mutation-pr-detect.sh <base-ref>\n' >&2
        return 2
    fi
    local _names
    _names=$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git diff --name-only --no-renames "$1...HEAD") || return 1
    local _numstat _src _test _cargo _manifests _path
    _numstat=$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git diff --numstat --no-renames "$1...HEAD") || return 1
    _src=$(py_src_dirs <<< "${_numstat}") || return 1
    _test=$(py_test_dirs <<< "${_numstat}") || return 1
    local -a _crates=()
    _manifests=$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git ls-files '*/*-rs/Cargo.toml') || return 1
    while IFS= read -r _path; do
        [[ -n "${_path}" ]] && _crates+=("${_path%/Cargo.toml}")
    done <<< "${_manifests}"
    _cargo=$(cargo_crates_changed "$1" "${_names}" "${_crates[@]}") || return 1
    CARGO_CRATES="${_cargo}" PY_SRC_DIRS="${_src}" PY_TEST_DIRS="${_test}" detect "${_crates[@]}" <<< "${_names}"
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0

main "$@" || exit $?
