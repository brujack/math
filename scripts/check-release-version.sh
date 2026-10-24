#!/usr/bin/env bash
# Validate a release workflow's `version` input before any step uses it. It must be
# plain MAJOR.MINOR.PATCH and equal the crate's Cargo.toml [package] version, so a
# release cannot tag a binary under a version it does not report, and the input
# cannot carry quotes or other metacharacters into git-cliff's args, the tag or the
# release name. Prints the checked version on success.

readonly SEMVER_RE='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'

check_release_version() {
    local crate_dir="${1:-}"
    local version="${2:-}"

    if [[ -z "${crate_dir}" || -z "${version}" ]]; then
        printf "usage: check-release-version.sh <crate-dir> <version>\n" >&2
        return 2
    fi
    if [[ ! "${version}" =~ ${SEMVER_RE} ]]; then
        printf "version '%s' is not MAJOR.MINOR.PATCH (no v prefix)\n" "${version}" >&2
        return 1
    fi

    local manifest="${crate_dir}/Cargo.toml"
    local cargo_version
    # tomllib reads [package] version exactly; a line grep would also match
    # dependency versions. Runs before any Rust toolchain step, so no cargo here.
    if ! cargo_version=$(python3 -c '
import sys, tomllib
with open(sys.argv[1], "rb") as f:
    print(tomllib.load(f)["package"]["version"])
' "${manifest}" 2>/dev/null); then
        printf "cannot read [package] version from %s\n" "${manifest}" >&2
        return 1
    fi
    if [[ "${version}" != "${cargo_version}" ]]; then
        printf "version input %s does not match %s version %s\n" \
            "${version}" "${manifest}" "${cargo_version}" >&2
        return 1
    fi
    printf "%s\n" "${version}"
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
check_release_version "$@"
