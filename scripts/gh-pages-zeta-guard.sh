#!/usr/bin/env bash
# Deploy guard for zeta-results-pages.yml: the workflow may change only zeta/ on the
# gh-pages branch, which also holds dev/bench/ (written by benchmarks.yml). Exits 1,
# naming the first offending path, when `git status` in the given checkout lists any
# path outside zeta/. Exits 2 on a usage error or a directory that is not a repository.

zeta_guard() {
    local dir="${1:-}"
    if [[ -z "${dir}" ]]; then
        printf "usage: gh-pages-zeta-guard.sh <gh-pages dir>\n" >&2
        return 2
    fi

    local status_file
    status_file="$(mktemp)" || return 2
    # NUL-separated output keeps odd file names intact; a rename or copy entry is
    # "XY new" followed by a separate "old" token, and both must lie inside zeta/.
    if ! env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git -C "${dir}" status --porcelain -z --untracked-files=all >"${status_file}"; then
        rm -f "${status_file}"
        printf "cannot read git status in %s\n" "${dir}" >&2
        return 2
    fi

    local entry path code=0 expect_origin=0
    while IFS= read -r -d '' entry; do
        if [[ "${expect_origin}" -eq 1 ]]; then
            path="${entry}"
            expect_origin=0
        else
            path="${entry:3}"
            case "${entry:0:2}" in
                *R* | *C*) expect_origin=1 ;;
            esac
        fi
        if [[ "${path}" != zeta/* ]]; then
            printf "path outside zeta/ changed: %s\n" "${path}" >&2
            code=1
            break
        fi
    done <"${status_file}"
    rm -f "${status_file}"
    return "${code}"
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
zeta_guard "$@"
