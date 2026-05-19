#!/usr/bin/env bash
# install_deps.sh — install dependencies for factorial.py
#
# Installs:
#   C libraries  — GMP + MPFR (required by gmpy2)
#   Python       — mpmath, gmpy2, coverage, ruff  (runtime + test suite)
#
# For the Rust factorial-rs implementation, run factorial/factorial-rs/install_deps.sh instead.

set -euo pipefail

OS="$(uname -s)"

install_macos() {
    echo "==> Detected macOS ($(uname -m))"
    if ! command -v brew >/dev/null 2>&1; then
        echo "Error: Homebrew is required on macOS." >&2
        echo "Install it from https://brew.sh, then re-run this script." >&2
        exit 1
    fi
    echo "==> Installing GMP and MPFR via Homebrew..."
    brew install gmp mpfr
}

install_debian() {
    echo "==> Detected Debian / Ubuntu"
    sudo apt-get update -qq
    sudo apt-get install -y libgmp-dev libmpfr-dev libmpc-dev python3-dev
}

install_rhel() {
    echo "==> Detected RHEL / Fedora / CentOS"
    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y gmp-devel mpfr-devel libmpc-devel python3-devel
    elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y gmp-devel mpfr-devel libmpc-devel python3-devel
    else
        echo "Error: neither dnf nor yum found." >&2
        exit 1
    fi
}

echo "=== factorial.py dependency installer ==="
echo ""

case "$OS" in
    Darwin)
        install_macos
        ;;
    Linux)
        if [ -f /etc/debian_version ]; then
            install_debian
        elif [ -f /etc/redhat-release ] || [ -f /etc/fedora-release ] || [ -f /etc/centos-release ]; then
            install_rhel
        else
            echo "Warning: unrecognised Linux distribution." >&2
            exit 1
        fi
        ;;
    *)
        echo "Error: unsupported OS '$OS'." >&2
        exit 1
        ;;
esac

echo ""
echo "==> Installing Python packages..."
python3 -m pip install --upgrade mpmath gmpy2 coverage ruff mutmut hypothesis

echo ""
echo "==> Verifying installation..."
python3 - <<'PYEOF'
import sys
for name in ("mpmath", "gmpy2", "coverage"):
    try:
        mod = __import__(name)
        print(f"  {name:<10} OK")
    except ImportError as e:
        print(f"  {name:<10} FAILED: {e}", file=sys.stderr)
        sys.exit(1)
PYEOF

echo ""
echo "All dependencies installed successfully."
echo "  make run       — run the calculator"
echo "  make test      — run unit tests"
echo "  make coverage  — run tests with coverage report"
