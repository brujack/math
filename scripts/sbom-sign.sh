#!/usr/bin/env bash

sbom_sign() {
    local binary_path="$1"
    local binary_name="$2"
    local target="${binary_path}/${binary_name}"

    if [[ ! -f "${target}" ]]; then
        printf "sbom-sign: not a regular file: %s\n" "${target}" >&2
        return 1
    fi

    syft "${target}" -o spdx-json --file "${target}.sbom.spdx.json" || return 1
    cosign sign-blob --yes "${target}" --bundle "${target}.bundle" || return 1
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
sbom_sign "$@"
