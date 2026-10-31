#!/usr/bin/env bash
# Print the GMP/MPFR build cache identity for CI as `enabled=`, `prefix=` and
# `key=` lines, derived from the gmp-mpfr-sys version in every tracked crate
# Cargo.lock. The prefix is the restore-keys prefix; the key adds the ISO week
# so the cache is rebuilt weekly.
#
# Usage: gmp-cache-key.sh [--strict]
#   (default)  an unusable input prints a ::warning:: and `enabled=false`, exit 0,
#              so a crate job degrades to a cold build instead of failing.
#   --strict   an unusable input exits 1, so the warm job fails loudly.
# Exit 2 on a bad argument.

readonly USAGE="usage: gmp-cache-key.sh [--strict]"

# Set VERSIONS to the sorted, unique gmp-mpfr-sys versions of every tracked
# crate lockfile, joined by `_`. Runs in the caller's shell (no command
# substitution around it) so that bail can exit the script; every read
# failure is a cause rather than a silently shorter list.
# The version line is read only inside the gmp-mpfr-sys [[package]] block.
collect_versions() {
    local strict="$1" root="$2"
    local listing lock found="" out
    local -a locks
    listing="$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git -C "${root}" ls-files '*/*-rs/Cargo.lock')" \
        || bail "${strict}" "could not list the tracked Cargo.lock files"
    mapfile -t locks <<<"${listing}"
    for lock in "${locks[@]}"; do
        [[ -n "${lock}" ]] || continue
        [[ -r "${root}/${lock}" ]] || bail "${strict}" "cannot read tracked lockfile ${lock}"
        out="$(awk '
            { sub(/\r$/, "") }
            /^\[\[package\]\]/ { in_gmp = 0; next }
            /^name = "gmp-mpfr-sys"$/ { in_gmp = 1; next }
            in_gmp && /^version = "/ {
                gsub(/^version = "|"$/, "")
                print
                in_gmp = 0
            }
        ' "${root}/${lock}")" || bail "${strict}" "cannot parse tracked lockfile ${lock}"
        [[ -z "${out}" ]] || found+="${out}"$'\n'
    done
    VERSIONS="$(printf '%s' "${found}" | sort -u -V | paste -sd_ -)"
}

# Report an unusable input per mode and exit.
bail() {
    local strict="$1" cause="$2"
    if [[ "${strict}" == "1" ]]; then
        printf 'gmp-cache-key: %s\n' "${cause}" >&2
        exit 1
    fi
    printf '::warning::gmp-cache-key: %s\n' "${cause}" >&2
    printf 'enabled=false\n'
    exit 0
}

main() {
    local strict=0
    case "$#:${1:-}" in
        0:) ;;
        1:--strict) strict=1 ;;
        *)
            printf '%s\n' "${USAGE}" >&2
            exit 2
            ;;
    esac

    local root
    root="$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
        git rev-parse --show-toplevel 2>/dev/null)" \
        || bail "${strict}" "not inside a git repository"

    collect_versions "${strict}" "${root}"
    local versions="${VERSIONS}"

    local week="${GMP_CACHE_WEEK:-$(date -u +%G-W%V)}"

    [[ -n "${versions}" ]] || bail "${strict}" "no tracked Cargo.lock names gmp-mpfr-sys"
    [[ -n "${RUNNER_OS:-}" ]] || bail "${strict}" "RUNNER_OS is empty"
    [[ -n "${ImageOS:-}" ]] || bail "${strict}" "ImageOS is empty"
    [[ -n "${week}" ]] || bail "${strict}" "ISO week is empty"

    local prefix="gmp-mpfr-sys-${versions}-${RUNNER_OS}-${ImageOS}-"
    printf 'enabled=true\nprefix=%s\nkey=%s%s\n' "${prefix}" "${prefix}" "${week}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
