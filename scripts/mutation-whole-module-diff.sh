#!/usr/bin/env bash
# Writes a unified diff that adds a Python sub-project's whole module (and its
# mutants-equivalent.toml, when present) as new files.
#
# Usage: mutation-whole-module-diff.sh <dir> <out-diff>   (run from repo root)
#
# Paths are relative to <dir> (`+++ b/<module>.py`), the form `make mutants-diff-plan` expects, and
# the content is the working tree, so a dirty checkout is honoured. Adding the toml as well keeps
# cosmic_ray_prune.py's re-confirm rule satisfied: every entry sits on a changed line of an edited
# toml. The weakening planner (K) and the `mutants-weakening` head session both use this script, so
# their job sets match by construction. <dir> may be nested or absolute: the module
# is named from its last component. Exits 2 on bad usage, 1 on any failure (never a partial diff).

# Appends the diff adding <file> (relative to the cwd) to ${tmp}. `git diff --no-index` exits 1
# when the files differ, which is the normal case here; only other statuses are failures.
append_added_file() {
    local file="$1" rc
    env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git -c core.quotePath=false diff --no-index --no-color --no-ext-diff \
        --src-prefix=a/ --dst-prefix=b/ -- /dev/null "${file}" >>"${tmp}"
    rc=$?
    if ((rc != 0 && rc != 1)); then
        printf '%s: git diff failed for %s (status %s)\n' "${0##*/}" "${file}" "${rc}" >&2
        return 1
    fi
    return 0
}

main() {
    if [[ "$#" -ne 2 ]]; then
        printf 'Usage: %s <dir> <out-diff>\n' "${0##*/}" >&2
        return 2
    fi
    local dir="${1%/}" out="$2" base module
    base="${dir##*/}"
    module="${base//-/_}.py"

    if [[ ! -f "${dir}/${module}" ]]; then
        printf '%s: %s/%s is not a file\n' "${0##*/}" "${dir}" "${module}" >&2
        return 1
    fi

    case "${out}" in
        /*) ;;
        *) out="${PWD}/${out}" ;;
    esac

    local tmp
    tmp="$(mktemp)" || return 1
    # The subshell owns the cwd change and the temp file, so a failure leaves neither behind and
    # never writes a partial diff to ${out}.
    (
        trap 'rm -f -- "${tmp}"' EXIT
        cd "${dir}" || exit 1
        append_added_file "${module}" || exit 1
        if [[ -f mutants-equivalent.toml ]]; then
            append_added_file mutants-equivalent.toml || exit 1
        fi
        cat -- "${tmp}" >"${out}" || exit 1
    )
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit "$?"
fi
