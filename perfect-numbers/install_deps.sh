#!/usr/bin/env bash
# install_deps.sh — install dependencies for perfect_numbers.py
#
# Installs:
#   Python — ruff (linter), coverage (test coverage reporting)
#
# perfect_numbers.py uses only Python built-in integers — no C libraries required.
# For the Rust implementation, run perfect-numbers/perfect-numbers-rs/install_deps.sh.
#
# Supported platforms: macOS, Debian/Ubuntu, RHEL/Fedora/CentOS

set -euo pipefail

echo "=== perfect-numbers.py dependency installer ==="
echo ""
echo "==> Installing Python packages..."
python3 -m pip install --upgrade ruff coverage mutmut

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
echo "  make run       — run the finder"
echo "  make test      — run unit tests"
echo "  make coverage  — run tests with coverage report"
