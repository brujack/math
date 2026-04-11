#!/usr/bin/env bash
# install_deps.sh — install dependencies for twin-primes-rs
#
# Installs:
#   Rust — rustup toolchain + cargo-tarpaulin (build, test, coverage)
#
# No external C libraries required.
#
# Supported platforms:
#   macOS (Apple Silicon & x86_64) — uses Homebrew / rustup
#   Debian / Ubuntu                — uses rustup
#   RHEL / Fedora / CentOS         — uses rustup

set -euo pipefail

install_rust() {
    if command -v cargo >/dev/null 2>&1; then
        echo "==> Rust already installed: $(rustc --version)"
        echo "==> Updating toolchain..."
        rustup update stable
    else
        echo "==> Installing Rust via rustup..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
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

echo "=== twin-primes-rs dependency installer ==="
echo ""

install_rust

echo ""
install_cargo_tarpaulin

echo ""
echo "==> Verifying installation..."
echo "  rustc     $(rustc --version)  OK"
echo "  cargo     $(cargo --version)  OK"
echo "  tarpaulin $(cargo tarpaulin --version)  OK"

echo ""
echo "All dependencies installed successfully."
echo ""
echo "  make twin-primes — build release binary"
echo "  make test        — run unit tests"
