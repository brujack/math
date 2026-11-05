#!/usr/bin/env bash
# Writes the PR diff for one crate with paths relative to the crate dir.
#
# Usage: mutation-pr-diff.sh <base-ref> <crate-dir> <out-file>   (run from repo root)
#
# cargo-mutants runs inside the crate dir and matches --in-diff paths against
# paths relative to it, so a repo-root-relative diff (a/x/x-rs/src/..) selects
# nothing. `--relative` makes every path start `src/`. Three-dot keeps commits
# that landed on the base after the fork out of the diff.

main() {
    if [[ "$#" -ne 3 ]]; then
        printf 'Usage: %s <base-ref> <crate-dir> <out-file>\n' "${0##*/}" >&2
        return 2
    fi

    local base_ref="$1"
    local crate_dir="${2%/}"
    local out_file="$3"

    if [[ ! -f "${crate_dir}/Cargo.toml" ]]; then
        printf '%s: %s/Cargo.toml is not a file\n' "${0##*/}" "${crate_dir}" >&2
        return 2
    fi

    if ! env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git diff --no-color --no-ext-diff --src-prefix=a/ --dst-prefix=b/ --relative="${crate_dir}/" "${base_ref}...HEAD" -- "${crate_dir}" >"${out_file}"; then
        printf '%s: git diff failed or cannot write %s\n' "${0##*/}" "${out_file}" >&2
        return 1
    fi
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit "$?"
fi
