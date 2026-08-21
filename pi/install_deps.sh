#!/usr/bin/env bash
# install_deps.sh — install dependencies for pi.py
#
# Installs:
#   C libraries  — GMP + MPFR (required by gmpy2)
#   Python       — mpmath, gmpy2, coverage  (runtime + test suite)
#
# For the Rust pi-rs implementation, run pi/pi-rs/install_deps.sh instead.
#
# Supported platforms:
#   macOS (Apple Silicon & x86_64) — uses Homebrew
#   Debian / Ubuntu                — uses apt
#   RHEL / Fedora / CentOS         — uses dnf (falls back to yum)

set -euo pipefail

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

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
    echo "==> Installing GMP and MPFR via apt..."
    sudo apt-get update -qq
    sudo apt-get install -y libgmp-dev libmpfr-dev libmpc-dev python3-dev
}

install_rhel() {
    echo "==> Detected RHEL / Fedora / CentOS"
    echo "==> Installing GMP and MPFR via dnf (or yum)..."
    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y gmp-devel mpfr-devel libmpc-devel python3-devel
    elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y gmp-devel mpfr-devel libmpc-devel python3-devel
    else
        echo "Error: neither dnf nor yum found." >&2
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

echo "=== pi.py dependency installer ==="
echo ""

# ---- C libraries (GMP + MPFR) ----
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
            echo "Please install libgmp-dev and libmpfr-dev (or equivalent) manually, then re-run." >&2
            exit 1
        fi
        ;;
    *)
        echo "Error: unsupported OS '$OS'." >&2
        echo "Supported: macOS, Debian/Ubuntu, RHEL/Fedora/CentOS" >&2
        exit 1
        ;;
esac

# ---- Python packages ----
echo ""
echo "==> Installing Python packages..."
python3 -m pip install ruff==0.16.1
python3 -m pip install --upgrade mpmath gmpy2 coverage cosmic-ray hypothesis pytest pytest-cov

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

echo ""
echo "==> Verifying installation..."

python3 - <<'PYEOF'
import sys

try:
    import mpmath
    print(f"  mpmath    {mpmath.__version__}  OK")
except ImportError as e:
    print(f"  mpmath    FAILED: {e}", file=sys.stderr)
    sys.exit(1)

try:
    import gmpy2
    print(f"  gmpy2     {gmpy2.version()}  (GMP {gmpy2.mp_version()}, MPFR {gmpy2.mpfr_version()})  OK")
except ImportError as e:
    print(f"  gmpy2     FAILED: {e}", file=sys.stderr)
    sys.exit(1)

try:
    import coverage
    print(f"  coverage  {coverage.__version__}  OK")
except ImportError as e:
    print(f"  coverage  FAILED: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo ""
echo "All dependencies installed successfully."
echo ""
echo "  make run       — run the calculator"
echo "  make test      — run unit tests"
echo "  make coverage  — run tests with coverage report"
