#!/usr/bin/env bash
# Runs `cargo deny check` against every Rust crate in the repo with the shared deny.toml.
#
# Usage: cargo-deny-all.sh
# Env:   CARGO_DENY_CRATES  file of manifest paths, one per line; replaces the git list (tests).
# Exit:  0 every crate passed, 1 any crate failed or the crate count is not EXPECTED_CRATES.
#
# The count guard fails closed: a glob that silently matches nothing (or a crate added
# without updating this script) must not turn the gate into a no-op.

readonly EXPECTED_CRATES=11

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 1
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)" || exit 1

# Prints the manifest paths (relative to the repo root), one per line.
list_manifests() {
    if [[ -n "${CARGO_DENY_CRATES:-}" ]]; then
        cat -- "${CARGO_DENY_CRATES}" || return 1
        return 0
    fi
    env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git -C "${REPO_ROOT}" ls-files '*/*-rs/Cargo.toml' || return 1
}

main() {
    local manifests=() manifest line crate_dir failed=()
    while IFS= read -r line; do
        [[ -n "${line}" ]] && manifests+=("${line}")
    done < <(list_manifests)

    if [[ "${#manifests[@]}" -ne "${EXPECTED_CRATES}" ]]; then
        printf "cargo-deny-all: expected %d crates, found %d\n" \
            "${EXPECTED_CRATES}" "${#manifests[@]}" >&2
        return 1
    fi

    for manifest in "${manifests[@]}"; do
        crate_dir="$(dirname "${manifest}")"
        printf "=== %s ===\n" "${crate_dir}"
        # --config is a global option: after `check` it exits 2 on cargo-deny 0.20.2.
        if ! cargo deny --config "${REPO_ROOT}/deny.toml" \
            --manifest-path "${REPO_ROOT}/${manifest}" check </dev/null; then
            failed+=("${crate_dir}")
        fi
    done

    if [[ "${#failed[@]}" -gt 0 ]]; then
        printf "cargo-deny-all: %d of %d crates failed:\n" "${#failed[@]}" "${EXPECTED_CRATES}" >&2
        printf "  %s\n" "${failed[@]}" >&2
        return 1
    fi
    printf "cargo-deny-all: all %d crates passed\n" "${EXPECTED_CRATES}"
    return 0
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
main "$@"
exit "$?"
