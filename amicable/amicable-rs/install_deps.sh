#!/usr/bin/env bash
# install_deps.sh — install everything amicable-rs needs to build, test and lint.
#
# Rendered from scripts/crate_templates/install_deps.sh for all 11 crates; edit the
# template and run `python3 scripts/render_crate_files.py --write`, never this copy.
#
# Installs:
#   C libraries — GMP + MPFR (all 11 crates install the same set)
#   Rust        — rustup stable toolchain
#   Cargo tools — cargo-nextest and cargo-machete (`make test` / `make lint`) and
#                 cargo-tarpaulin (coverage), at the versions CI pins
#
# Supported platforms: macOS (Homebrew), Debian/Ubuntu (apt), RHEL/Fedora (dnf/yum).
# Re-running is safe: installed tools are left as they are.

# Overridable so tests can exercise the Debian branch without a real /etc file.
DEBIAN_VERSION_FILE="${MATH_DEBIAN_VERSION_FILE:-/etc/debian_version}"

install_system_libs() {
    local os
    os="$(uname -s)" || return 1
    case "${os}" in
        Darwin)
            if ! command -v brew >/dev/null 2>&1; then
                printf "Error: Homebrew is required on macOS: https://brew.sh\n" >&2
                return 1
            fi
            printf "==> Installing GMP and MPFR via Homebrew\n"
            brew install gmp mpfr || return 1
            ;;
        Linux)
            if [[ -f "${DEBIAN_VERSION_FILE}" ]]; then
                printf "==> Installing GMP and MPFR via apt\n"
                sudo apt-get update -qq || return 1
                sudo apt-get install -y libgmp-dev libmpfr-dev || return 1
            elif command -v dnf >/dev/null 2>&1; then
                printf "==> Installing GMP and MPFR via dnf\n"
                sudo dnf install -y gmp-devel mpfr-devel || return 1
            elif command -v yum >/dev/null 2>&1; then
                printf "==> Installing GMP and MPFR via yum\n"
                sudo yum install -y gmp-devel mpfr-devel || return 1
            else
                printf "Error: unrecognised Linux distribution; install GMP and MPFR development packages manually\n" >&2
                return 1
            fi
            ;;
        *)
            printf "Error: unsupported OS '%s' (supported: macOS, Debian/Ubuntu, RHEL/Fedora)\n" "${os}" >&2
            return 1
            ;;
    esac
}

install_rust() {
    if command -v cargo >/dev/null 2>&1; then
        printf "==> Rust present; updating the stable toolchain\n"
        rustup update stable || return 1
        return 0
    fi
    printf "==> Installing Rust via rustup\n"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path \
        || return 1
    # shellcheck source=/dev/null
    source "${HOME}/.cargo/env" || return 1
}

install_cargo_tools() {
    if ! cargo nextest --version >/dev/null 2>&1; then
        printf "==> Installing cargo-nextest\n"
        cargo install cargo-nextest --locked --version 0.9.148 || return 1
    fi
    if ! cargo machete --version >/dev/null 2>&1; then
        printf "==> Installing cargo-machete\n"
        cargo install cargo-machete --locked --version 0.9.2 || return 1
    fi
    if ! cargo tarpaulin --version >/dev/null 2>&1; then
        printf "==> Installing cargo-tarpaulin (compiles from source; takes a few minutes)\n"
        cargo install cargo-tarpaulin --locked --version 0.37.5 || return 1
    fi
}

main() {
    printf "=== amicable-rs dependency installer ===\n"
    install_system_libs || return 1
    install_rust || return 1
    install_cargo_tools || return 1
    printf "All dependencies installed. Next: make test, make amicable, make install\n"
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
main "$@" || exit 1
