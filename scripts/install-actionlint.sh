#!/usr/bin/env bash
# Install the pinned actionlint into ${XDG_BIN_HOME:-${HOME}/.local/bin}.
#
# Single source of the version and checksums: `make install-deps` and the CI
# workflows (scripts.yml, auto-merge.yml) all run this script. The checksums are
# the official values from actionlint_1.7.12_checksums.txt on the v1.7.12 release,
# hard-coded on purpose: a checksum fetched at install time proves nothing
# (core.md ci-002). Bumping the version means replacing all four values together.
#
# Usage: scripts/install-actionlint.sh   (exit 0 installed or already current)

readonly AL_VERSION="1.7.12"

# Print the pinned sha256 for a "<os>_<arch>" platform; fail for an unknown one.
al_expected_sha256() {
    case "${1:-}" in
        linux_amd64) printf '%s\n' "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8" ;;
        linux_arm64) printf '%s\n' "325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6" ;;
        darwin_amd64) printf '%s\n' "5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644" ;;
        darwin_arm64) printf '%s\n' "aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f" ;;
        *) return 1 ;;
    esac
}

# Map `uname` output to the release asset's "<os>_<arch>" suffix.
al_platform() {
    local os arch
    os="$(uname -s)" || return 1
    arch="$(uname -m)" || return 1
    case "${os}" in
        Linux) os="linux" ;;
        Darwin) os="darwin" ;;
        *) return 1 ;;
    esac
    case "${arch}" in
        x86_64 | amd64) arch="amd64" ;;
        aarch64 | arm64) arch="arm64" ;;
        *) return 1 ;;
    esac
    printf '%s_%s\n' "${os}" "${arch}"
}

# Verify "<sha256>  <file>" in <dir>; GNU sha256sum, else macOS shasum.
al_verify_sha256() {
    local dir="${1:-}" sum="${2:-}" file="${3:-}"
    [[ -n "${dir}" && -n "${sum}" && -n "${file}" ]] || return 1
    if command -v sha256sum > /dev/null 2>&1; then
        (cd "${dir}" && printf '%s  %s\n' "${sum}" "${file}" | sha256sum -c -) || return 1
    elif command -v shasum > /dev/null 2>&1; then
        (cd "${dir}" && printf '%s  %s\n' "${sum}" "${file}" | shasum -a 256 -c -) || return 1
    else
        printf 'install-actionlint: neither sha256sum nor shasum found\n' >&2
        return 1
    fi
}

install_actionlint() {
    local bin_dir="${XDG_BIN_HOME:-}"
    if [[ -z "${bin_dir}" ]]; then
        if [[ -z "${HOME:-}" ]]; then
            printf 'install-actionlint: set XDG_BIN_HOME or HOME\n' >&2
            return 1
        fi
        bin_dir="${HOME}/.local/bin"
    fi

    local current=""
    if [[ -x "${bin_dir}/actionlint" ]]; then
        current="$("${bin_dir}/actionlint" -version 2> /dev/null | head -1)"
    fi
    if [[ "${current}" == "${AL_VERSION}" ]]; then
        printf 'actionlint %s already installed in %s\n' "${AL_VERSION}" "${bin_dir}"
        return 0
    fi

    local platform sha
    platform="$(al_platform)" || {
        printf 'install-actionlint: unsupported platform %s/%s\n' "$(uname -s)" "$(uname -m)" >&2
        return 1
    }
    sha="$(al_expected_sha256 "${platform}")" || {
        printf 'install-actionlint: no pinned checksum for %s\n' "${platform}" >&2
        return 1
    }

    local asset="actionlint_${AL_VERSION}_${platform}.tar.gz"
    local url="https://github.com/rhysd/actionlint/releases/download/v${AL_VERSION}/${asset}"

    # Subshell so the EXIT trap fires on every path without touching the caller.
    (
        tmp="$(mktemp -d)" || exit 1
        [[ -n "${tmp}" ]] || exit 1
        trap 'rm -rf -- "${tmp}"' EXIT

        curl -fsSL -o "${tmp}/${asset}" "${url}" || {
            printf 'install-actionlint: download failed: %s\n' "${url}" >&2
            exit 1
        }
        al_verify_sha256 "${tmp}" "${sha}" "${asset}" > /dev/null || {
            printf 'install-actionlint: checksum mismatch for %s; refusing to extract\n' "${asset}" >&2
            exit 1
        }
        tar -xzf "${tmp}/${asset}" -C "${tmp}" actionlint || exit 1
        mkdir -p "${bin_dir}" || exit 1
        install -m 755 "${tmp}/actionlint" "${bin_dir}/actionlint" || exit 1
    ) || return 1

    current="$("${bin_dir}/actionlint" -version 2> /dev/null | head -1)"
    if [[ "${current}" != "${AL_VERSION}" ]]; then
        printf 'install-actionlint: installed binary reports "%s", expected %s\n' "${current}" "${AL_VERSION}" >&2
        return 1
    fi
    printf 'installed actionlint %s into %s\n' "${AL_VERSION}" "${bin_dir}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    install_actionlint || exit 1
fi
