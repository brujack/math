#!/usr/bin/env bash
# install_deps.sh — install dependencies for fib.py
#
# Installs:
#   Python — ruff (linter), coverage (test coverage reporting)
#
# fib.py uses only Python built-in integers — no C libraries required.
# For the Rust fib-rs implementation, run fib/fib-rs/install_deps.sh instead.
#
# Supported platforms: macOS, Debian/Ubuntu, RHEL/Fedora/CentOS

set -euo pipefail

echo "=== fib.py dependency installer ==="
echo ""
echo "==> Installing Python packages..."
python3 -m pip install --upgrade ruff coverage cosmic-ray hypothesis

echo ""
echo "==> Verifying installation..."

python3 - <<'PYEOF'
import sys

try:
    import coverage
    print(f"  coverage  {coverage.__version__}  OK")
except ImportError as e:
    print(f"  coverage  FAILED: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

ruff --version && echo "  ruff      OK"

echo ""
echo "All dependencies installed successfully."
echo ""
echo "  make run       — run the generator"
echo "  make test      — run unit tests"
echo "  make coverage  — run tests with coverage report"
