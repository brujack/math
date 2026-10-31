#!/usr/bin/env bash
# Writes exactly one THIRD-PARTY-NOTICES.txt for a crate.
# Usage: third-party-notices.sh <crate-dir> <out-dir>
# LICENSES_DIR overrides the directory holding LGPL-3.0.txt and GPL-3.0.txt.
#
# Why: crates linking gmp-mpfr-sys statically ship GMP/MPFR/MPC under
# LGPL-3.0-or-later, which requires the licence texts to accompany the binary.

readonly NOTICES_NAME="THIRD-PARTY-NOTICES.txt"
readonly GMP_CRATE="gmp-mpfr-sys"
readonly RUG_CRATE="rug"

log_error() {
    printf 'third-party-notices: %s\n' "$*" >&2
}

# lock_versions <lock-content> <crate>: print every locked version of the crate,
# sorted and comma-separated; empty output means the crate is not locked.
# CR is stripped (CRLF lockfiles) and name/version are buffered per block so
# field order does not matter.
lock_versions() {
    local content="${1}" crate="${2}" found
    found="$(printf '%s\n' "${content}" | awk -v want="${crate}" '
        function flush() { if (name == want && version != "") print version }
        /^\[\[package\]\]/ { flush(); name = ""; version = ""; next }
        /^name = / { name = $3; gsub(/"/, "", name); next }
        /^version = / { version = $3; gsub(/"/, "", version); next }
        END { flush() }
    ')" || {
        log_error "cannot parse versions of ${crate} from Cargo.lock"
        return 1
    }
    [[ -z "${found}" ]] && return 0
    printf '%s\n' "${found}" | LC_ALL=C sort -V | paste -sd, - | sed 's/,/, /g' || return 1
}

# declares_rug <toml-content>: succeed if a Cargo.toml declares rug in any
# form: `rug = ...`, `rug.key = ...`, a [*dependencies.rug] table, or a
# renamed dependency carrying package = "rug".
declares_rug() {
    printf '%s\n' "${1}" | grep -Eq \
        -e '^[[:space:]]*rug[[:space:]]*(=|\.)' \
        -e '^[[:space:]]*\[[^]]*dependencies\.rug\][[:space:]]*$' \
        -e 'package[[:space:]]*=[[:space:]]*"rug"'
}

# require_text <path>: fail closed on an absent or empty licence text.
require_text() {
    local path="${1}"
    if [[ ! -f "${path}" ]]; then
        log_error "licence text not found: ${path}"
        return 1
    fi
    if [[ ! -s "${path}" ]]; then
        log_error "licence text is empty: ${path}"
        return 1
    fi
}

emit_gmp_notice() {
    local gmp_ver="${1}" rug_ver="${2}" lgpl="${3}" gpl="${4}"
    printf 'THIRD-PARTY NOTICES\n===================\n\n'
    printf 'This binary statically links the following components:\n\n'
    printf '  - GMP, MPFR and MPC, via %s %s\n' "${GMP_CRATE}" "${gmp_ver}"
    printf '  - %s %s (Rust bindings)\n\n' "${RUG_CRATE}" "${rug_ver}"
    printf 'Licence: LGPL-3.0-or-later. These libraries are statically linked.\n\n'
    printf 'Corresponding source\n--------------------\n'
    printf 'The application source (MIT) is this repository at the release tag, which is\n'
    printf 'sufficient to relink the binary against a modified version of the libraries.\n'
    printf 'The GMP, MPFR and MPC C sources are bundled in the %s crate on\n' "${GMP_CRATE}"
    printf 'crates.io. Both must remain available.\n\n'
    printf '================================================================================\n'
    printf 'GNU LESSER GENERAL PUBLIC LICENSE, version 3\n'
    printf '================================================================================\n\n'
    cat "${lgpl}" || return 1
    printf '\n================================================================================\n'
    printf 'GNU GENERAL PUBLIC LICENSE, version 3 (incorporated by the LGPL)\n'
    printf '================================================================================\n\n'
    cat "${gpl}" || return 1
}

emit_plain_notice() {
    printf 'THIRD-PARTY NOTICES\n===================\n\n'
    printf 'This binary links no LGPL components.\n'
}

main() {
    local crate_dir="${1:-}" out_dir="${2:-}"
    if [[ -z "${crate_dir}" || -z "${out_dir}" ]]; then
        log_error "usage: third-party-notices.sh <crate-dir> <out-dir>"
        return 1
    fi
    local lockfile="${crate_dir}/Cargo.lock"
    if [[ ! -f "${lockfile}" ]]; then
        log_error "missing Cargo.lock: ${lockfile}"
        return 1
    fi
    if [[ ! -d "${out_dir}" || ! -w "${out_dir}" ]]; then
        log_error "output directory not writable: ${out_dir}"
        return 1
    fi

    local script_dir repo_root licenses_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 1
    repo_root="$(dirname "${script_dir}")"
    licenses_dir="${LICENSES_DIR:-${repo_root}/licenses}"

    local lock_content toml_content="" gmp_ver rug_ver
    lock_content="$(tr -d '\r' <"${lockfile}")" || {
        log_error "cannot read ${lockfile}"
        return 1
    }
    if [[ -e "${crate_dir}/Cargo.toml" ]]; then
        toml_content="$(tr -d '\r' <"${crate_dir}/Cargo.toml")" || {
            log_error "cannot read ${crate_dir}/Cargo.toml"
            return 1
        }
    fi
    gmp_ver="$(lock_versions "${lock_content}" "${GMP_CRATE}")" || return 1
    rug_ver="$(lock_versions "${lock_content}" "${RUG_CRATE}")" || return 1
    if [[ -z "${gmp_ver}" ]] && declares_rug "${toml_content}"; then
        log_error "${crate_dir}/Cargo.toml declares rug but Cargo.lock has no ${GMP_CRATE}"
        return 1
    fi
    if [[ -z "${gmp_ver}" && -n "${rug_ver}" ]]; then
        log_error "rug is locked but ${GMP_CRATE} is not locked in ${lockfile}"
        return 1
    fi
    if [[ -n "${gmp_ver}" && -z "${rug_ver}" ]]; then
        log_error "${GMP_CRATE} is locked but rug is not locked in ${lockfile}"
        return 1
    fi

    local tmp
    tmp="$(mktemp "${out_dir}/.notices.XXXXXX")" || {
        log_error "cannot create temp file in ${out_dir}"
        return 1
    }
    if [[ -n "${gmp_ver}" ]]; then
        if ! require_text "${licenses_dir}/LGPL-3.0.txt" ||
            ! require_text "${licenses_dir}/GPL-3.0.txt" ||
            ! emit_gmp_notice "${gmp_ver}" "${rug_ver}" \
                "${licenses_dir}/LGPL-3.0.txt" "${licenses_dir}/GPL-3.0.txt" >"${tmp}"; then
            rm -f "${tmp}"
            return 1
        fi
    elif ! emit_plain_notice >"${tmp}"; then
        rm -f "${tmp}"
        return 1
    fi
    if ! chmod 0644 "${tmp}"; then
        log_error "cannot set mode on ${tmp}"
        rm -f "${tmp}"
        return 1
    fi
    if ! mv "${tmp}" "${out_dir}/${NOTICES_NAME}"; then
        log_error "cannot move notices into ${out_dir}"
        rm -f "${tmp}"
        return 1
    fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@" || exit 1
fi
