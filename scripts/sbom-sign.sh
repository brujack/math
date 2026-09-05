#!/usr/bin/env bash

sbom_sign() {
    if [[ $# -ne 2 ]]; then
        printf "Usage: sbom-sign.sh <binary_path> <binary_name>\n" >&2
        return 1
    fi

    local binary_path="$1"
    local binary_name="$2"
    local target="${binary_path}/${binary_name}"

    if [[ ! -f "${target}" ]]; then
        printf "sbom-sign: not a regular file: %s\n" "${target}" >&2
        return 1
    fi

    syft "${target}" -o spdx-json --file "${target}.sbom.spdx.json" || return 1

    # An SBOM that catalogues only the binary itself is the failure this whole
    # pipeline exists to prevent: it publishes, grype scans it, and finds nothing
    # forever. Measured 2026-09-04 on both Mach-O arm64 and ELF x86-64 -- without
    # cargo-auditable's .dep-v0 section syft reports exactly 1 package (the binary),
    # with it 13. Verifying presence and not content is what let that ship before.
    local pkgs
    pkgs=$(jq '.packages | length' "${target}.sbom.spdx.json" 2>/dev/null)
    if [[ ! "${pkgs}" =~ ^[0-9]+$ ]]; then
        printf "sbom-sign: could not read package count from %s\n" \
            "${target}.sbom.spdx.json" >&2
        return 1
    fi
    if [[ "${pkgs}" -le 1 ]]; then
        printf "sbom-sign: SBOM catalogues %s package(s) for %s -- expected more than the binary itself. Was it built with 'cargo auditable build'?\n" \
            "${pkgs}" "${binary_name}" >&2
        return 1
    fi
    cosign sign-blob --yes "${target}" --bundle "${target}.bundle" || return 1
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
sbom_sign "$@"
