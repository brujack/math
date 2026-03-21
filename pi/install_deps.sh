#!/usr/bin/env bash
# install_deps.sh — install all dependencies for the pi and prime projects
#
# Installs:
#   C libraries  — GMP + MPFR (required by pi.py via gmpy2, and by pi-rs via rug)
#   Python       — mpmath, gmpy2, coverage  (pi.py + test suite)
#   Rust         — rustup toolchain + cargo-tarpaulin  (pi-rs, prime-rs + coverage)
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
# Rust toolchain
# ---------------------------------------------------------------------------

install_rust() {
    if command -v cargo >/dev/null 2>&1; then
        echo "==> Rust already installed: $(rustc --version)"
        echo "==> Updating toolchain..."
        rustup update stable
    else
        echo "==> Installing Rust via rustup..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
        # Source the env so cargo is available for the rest of this script.
        # shellcheck source=/dev/null
        source "${HOME}/.cargo/env"
        echo "==> Rust installed: $(rustc --version)"
    fi
}

install_cargo_tarpaulin() {
    if cargo tarpaulin --version >/dev/null 2>&1; then
        echo "==> cargo-tarpaulin already installed: $(cargo tarpaulin --version)"
    else
        echo "==> Installing cargo-tarpaulin (Rust coverage tool)..."
        echo "    This compiles from source and may take a few minutes."
        cargo install cargo-tarpaulin
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

echo "=== π / prime dependency installer ==="
echo ""

# ---- C libraries (GMP + MPFR, needed by pi.py and pi-rs) ----
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

# ---- Python packages (pi.py runtime + test coverage) ----
echo ""
echo "==> Installing Python packages..."
python3 -m pip install --upgrade mpmath gmpy2 coverage

# ---- Rust toolchain (pi-rs, prime-rs) ----
echo ""
install_rust

# ---- cargo-tarpaulin (Rust coverage) ----
echo ""
install_cargo_tarpaulin

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

echo "  rustc     $(rustc --version)  OK"
echo "  cargo     $(cargo --version)  OK"
echo "  tarpaulin $(cargo tarpaulin --version)  OK"

echo ""
echo "All dependencies installed successfully."
echo ""
echo "Python (pi.py):"
echo "  make run       — run the calculator"
echo "  make test      — run unit tests"
echo "  make coverage  — run tests with coverage report"
echo ""
echo "Rust (pi-rs):    cd pi/pi-rs  && make pi | make test"
echo "Rust (prime-rs): cd prime/prime-rs && make prime | make test"
