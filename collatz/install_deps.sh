#!/usr/bin/env bash
# install_deps.sh -- install dependencies for collatz.py
#
# Rendered from scripts/crate_templates/python/install_deps.sh; edit the template
# and run scripts/render_crate_files.py --write, never one project's copy.
#
# Installs:
#   C libraries -- GMP + MPFR (required by gmpy2)
#   Python      -- every package pinned below, runtime and tooling
#
# For the Rust collatz-rs implementation, run collatz/collatz-rs/install_deps.sh instead.
#
# Supported platforms:
#   macOS (Apple Silicon and x86_64) -- Homebrew
#   Debian / Ubuntu                  -- apt
#   RHEL / Fedora / CentOS           -- dnf (falls back to yum)

# Distro marker files; the overrides let a test steer detection on any host.
DEBIAN_VERSION_FILE="${MATH_DEBIAN_VERSION_FILE:-/etc/debian_version}"

is_rhel_family() {
    local f
    if [[ -n "${MATH_RHEL_RELEASE_FILE:-}" ]]; then
        [[ -f "${MATH_RHEL_RELEASE_FILE}" ]]
        return
    fi
    for f in /etc/redhat-release /etc/fedora-release /etc/centos-release; do
        [[ -f "${f}" ]] && return 0
    done
    return 1
}

install_macos() {
    printf '%s\n' "==> Detected macOS ($(uname -m))"
    if ! command -v brew >/dev/null 2>&1; then
        printf '%s\n' "Error: Homebrew is required on macOS." >&2
        printf '%s\n' "Install it from https://brew.sh, then re-run this script." >&2
        return 1
    fi
    printf '%s\n' "==> Installing GMP and MPFR via Homebrew..."
    brew install gmp mpfr || return 1
}

install_debian() {
    printf '%s\n' "==> Detected Debian / Ubuntu"
    printf '%s\n' "==> Installing GMP and MPFR via apt..."
    sudo apt-get update -qq || return 1
    sudo apt-get install -y libgmp-dev libmpfr-dev libmpc-dev python3-dev || return 1
}

install_rhel() {
    printf '%s\n' "==> Detected RHEL / Fedora / CentOS"
    printf '%s\n' "==> Installing GMP and MPFR via dnf (or yum)..."
    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y gmp-devel mpfr-devel libmpc-devel python3-devel || return 1
    elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y gmp-devel mpfr-devel libmpc-devel python3-devel || return 1
    else
        printf '%s\n' "Error: neither dnf nor yum found." >&2
        return 1
    fi
}

install_c_libraries() {
    local os
    os="$(uname -s)"
    case "${os}" in
        Darwin)
            install_macos || return 1
            ;;
        Linux)
            if [[ -f "${DEBIAN_VERSION_FILE}" ]]; then
                install_debian || return 1
            elif is_rhel_family; then
                install_rhel || return 1
            else
                printf '%s\n' "Warning: unrecognised Linux distribution." >&2
                printf '%s\n' "Please install libgmp-dev and libmpfr-dev (or equivalent) manually, then re-run." >&2
                return 1
            fi
            ;;
        *)
            printf '%s\n' "Error: unsupported OS '${os}'." >&2
            printf '%s\n' "Supported: macOS, Debian/Ubuntu, RHEL/Fedora/CentOS" >&2
            return 1
            ;;
    esac
}

install_python_packages() {
    printf '\n%s\n' "==> Installing Python packages..."
    python3 -m pip install mpmath==1.4.1 gmpy2==2.3.2 coverage==7.16.2 cosmic-ray==8.7.0 hypothesis==6.168.5 pytest==9.1.1 pytest-cov==7.1.0 ruff==0.16.4 pyright==1.1.411 pip-audit==2.10.1 || return 1
}

verify_install() {
    printf '\n%s\n' "==> Verifying installation..."
    python3 - <<'PYEOF' || return 1
import importlib
import sys

failed = False
for name in (
    "mpmath",
    "gmpy2",
    "coverage",
    "cosmic_ray",
    "hypothesis",
    "pytest",
    "pytest_cov",
    "ruff",
    "pyright",
    "pip_audit",
):
    try:
        importlib.import_module(name)
        print(f"  {name}  OK")
    except ImportError as e:
        print(f"  {name}  FAILED: {e}", file=sys.stderr)
        failed = True
sys.exit(1 if failed else 0)
PYEOF
}

main() {
    printf '%s\n\n' "=== collatz.py dependency installer ==="
    install_c_libraries || return 1
    install_python_packages || return 1
    verify_install || return 1
    printf '\n%s\n\n' "All dependencies installed successfully."
    printf '%s\n' "  make run       -- run the program"
    printf '%s\n' "  make test      -- run unit tests"
    printf '%s\n' "  make coverage  -- run tests with coverage report"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@" || exit 1
fi
