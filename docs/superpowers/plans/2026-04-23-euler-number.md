# Euler's Number (e) Implementation Plan

> **Status: DONE** — Implemented 2026-04-23. PR #18 merged to master.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute Euler's number _e_ to N decimal places using the Taylor series with binary splitting, with parallel Python and Rust implementations mirroring the `pi/` project structure.

**Architecture:** Taylor series `e = sum(1/n! for n=0..N_terms)` computed via binary splitting with `(P, Q)` accumulators. Python parallelises across CPU cores via `ProcessPoolExecutor` with tree-reduction merge. Rust uses `rayon::join()` for shared-memory parallel recursion. Both use parallel pwrite for large file output.

**Tech Stack:** Python 3 + gmpy2/mpmath + ruff + coverage, Rust stable + rug (GMP) + rayon + clap 4

---

## File Map

| Action | Path                                 | Purpose                                 |
| ------ | ------------------------------------ | --------------------------------------- |
| Create | `e/e.py`                             | Python implementation + CLI             |
| Create | `e/test_e.py`                        | Python unit tests                       |
| Create | `e/Makefile`                         | run, lint, test, coverage targets       |
| Create | `e/install_deps.sh`                  | GMP + MPFR, mpmath, gmpy2, coverage     |
| Create | `e/CLAUDE.md`                        | Python project guidance                 |
| Create | `e/e-rs/src/main.rs`                 | Rust implementation + unit tests        |
| Create | `e/e-rs/Cargo.toml`                  | deps: rug, rayon, clap                  |
| Create | `e/e-rs/Makefile`                    | e, lint, test, clean targets            |
| Create | `e/e-rs/install_deps.sh`             | GMP + MPFR, Rust toolchain, tarpaulin   |
| Create | `e/e-rs/CLAUDE.md`                   | Rust project guidance                   |
| Create | `.github/workflows/e-py.yml`         | Python CI workflow                      |
| Create | `.github/workflows/e-rs.yml`         | Rust CI workflow (test → build)         |
| Create | `.github/workflows/release-e-rs.yml` | Rust release workflow (manual dispatch) |
| Modify | `.gitignore`                         | add `e_*_digits.txt`                    |
| Modify | `CLAUDE.md`                          | add e/ to all relevant tables           |
| Modify | `README.md`                          | add e/ row, CI badges, project section  |
| Modify | `scripts/pre-commit`                 | add `e` and `e/e-rs` to lint loop       |
| Modify | `scripts/pre-push`                   | add `e` and `e/e-rs` to test loop       |
| Modify | `docs/superpowers/README.md`         | move e from backlog to All Plans table  |

---

## Task 1: Create worktree and feature branch

- [ ] **Step 1: Create worktree on a feature branch**

```bash
git worktree add .worktrees/feat-euler-number -b feat/euler-number
cd .worktrees/feat-euler-number
```

- [ ] **Step 2: Confirm branch**

```bash
git branch --show-current
```

Expected: `feat/euler-number`

---

## Task 2: Scaffold Python project (non-code files)

**Files:** Create `e/Makefile`, `e/install_deps.sh`

- [ ] **Step 1: Create directory**

```bash
mkdir -p e
```

- [ ] **Step 2: Create `e/Makefile`**

```makefile
.PHONY: run lint test coverage clean

run:
	python3 e.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_e -v

coverage:
	python3 -m coverage run -m unittest test_e
	python3 -m coverage report

clean:
	rm -rf __pycache__ .coverage
```

- [ ] **Step 3: Create `e/install_deps.sh`**

```bash
#!/usr/bin/env bash
# install_deps.sh — install dependencies for e.py
#
# Installs:
#   C libraries  — GMP + MPFR (required by gmpy2)
#   Python       — mpmath, gmpy2, coverage, ruff  (runtime + test suite)
#
# For the Rust e-rs implementation, run e/e-rs/install_deps.sh instead.
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

echo "=== e.py dependency installer ==="
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
python3 -m pip install --upgrade mpmath gmpy2 coverage ruff

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
```

- [ ] **Step 4: Make it executable**

```bash
chmod +x e/install_deps.sh
```

- [ ] **Step 5: Commit scaffold**

```bash
git add e/Makefile e/install_deps.sh
git commit -m "chore: scaffold e/ Python project files"
```

---

## Task 3: Python binary splitting and core computation — TDD

**Files:** Create `e/test_e.py`, Create `e/e.py`

This task implements the core algorithm: `_taylor_bs(a, b)`, `_bs_chunk_worker(a, b)`, `_tree_combine(pq_list)`, `_calculate_e_gmpy2(digits)`, and `_e_to_str()`.

- [ ] **Step 1: Create `e/test_e.py` with failing tests for binary splitting**

```python
#!/usr/bin/env python3
"""Unit tests for e.py."""

import io
import os
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))

import e as e_module
from e import (
    _HAS_GMPY2,
    _tree_combine,
    _e_to_str,
    calculate_e,
    parse_args,
    get_target_digits,
)

# Known decimal expansion of e — first 50 decimal places.
E_REF = "2.71828182845904523536028747135266249775724709369995"


def _quiet_e(digits):
    """Compute e while suppressing the progress prints to stdout."""
    with redirect_stdout(io.StringIO()):
        return calculate_e(digits)


# ---------------------------------------------------------------------------
# _tree_combine
# ---------------------------------------------------------------------------

class TestTreeCombine(unittest.TestCase):
    """Tests for _tree_combine (pure Python, no gmpy2 dependency)."""

    @staticmethod
    def _merge(left, right):
        Pl, Ql = left
        Pr, Qr = right
        return Pl * Pr, Ql * Pr + Qr

    def test_single_element(self):
        pq = (2, 3)
        self.assertEqual(_tree_combine([pq]), pq)

    def test_two_elements(self):
        a = (2, 3)
        b = (5, 7)
        expected = self._merge(a, b)
        self.assertEqual(_tree_combine([a, b]), expected)

    def test_four_elements_tree_order(self):
        chunks = [(1, 1), (2, 3), (5, 7), (11, 13)]
        m01 = self._merge(chunks[0], chunks[1])
        m23 = self._merge(chunks[2], chunks[3])
        expected = self._merge(m01, m23)
        self.assertEqual(_tree_combine(list(chunks)), expected)

    def test_odd_length_passthrough(self):
        chunks = [(1, 1), (2, 3), (5, 7)]
        m01 = self._merge(chunks[0], chunks[1])
        expected = self._merge(m01, chunks[2])
        self.assertEqual(_tree_combine(list(chunks)), expected)

    def test_large_input_deterministic(self):
        chunks = [(i + 1, i + 2) for i in range(16)]
        result_a = _tree_combine(list(chunks))
        result_b = _tree_combine(list(chunks))
        self.assertEqual(result_a, result_b)

    def test_empty_list_raises(self):
        with self.assertRaises(IndexError):
            _tree_combine([])

    def test_identity_with_known_values(self):
        # P(a,b) = Pl * Pr = 2 * 5 = 10
        # Q(a,b) = Ql * Pr + Qr = 3 * 5 + 7 = 22
        result = _tree_combine([(2, 3), (5, 7)])
        self.assertEqual(result[0], 10)
        self.assertEqual(result[1], 22)


# ---------------------------------------------------------------------------
# Binary splitting — requires gmpy2
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestTaylorBS(unittest.TestCase):
    """Tests for _taylor_bs (requires gmpy2)."""

    def setUp(self):
        from e import _taylor_bs
        self.bs = _taylor_bs

    def test_leaf_a0(self):
        """Leaf at a=0: P=1, Q=1 (1/0! = 1)."""
        P, Q = self.bs(0, 1)
        self.assertEqual(int(P), 1)
        self.assertEqual(int(Q), 1)

    def test_leaf_a1(self):
        """Leaf at a=1: P=2, Q=2 (factorial factor a+1, Q=P for leaves)."""
        P, Q = self.bs(1, 2)
        self.assertEqual(int(P), 2)
        self.assertEqual(int(Q), 2)

    def test_leaf_a2(self):
        """Leaf at a=2: P=3, Q=3."""
        P, Q = self.bs(2, 3)
        self.assertEqual(int(P), 3)
        self.assertEqual(int(Q), 3)

    def test_split_consistency(self):
        """bs(0, 4) equals manually merging bs(0, 2) and bs(2, 4)."""
        P_full, Q_full = self.bs(0, 4)
        Pl, Ql = self.bs(0, 2)
        Pr, Qr = self.bs(2, 4)
        self.assertEqual(int(P_full), int(Pl * Pr))
        self.assertEqual(int(Q_full), int(Ql * Pr + Qr))

    def test_larger_range_consistency(self):
        """bs(0, 8) equals merging bs(0, 4) and bs(4, 8)."""
        P_full, Q_full = self.bs(0, 8)
        Pl, Ql = self.bs(0, 4)
        Pr, Qr = self.bs(4, 8)
        self.assertEqual(int(P_full), int(Pl * Pr))
        self.assertEqual(int(Q_full), int(Ql * Pr + Qr))

    def test_small_range_gives_correct_e(self):
        """50 terms should give accurate e to ~50 digits."""
        import gmpy2
        P, Q = self.bs(0, 50)
        prec = int(50 * 3.3219280948873626) + 100
        ctx = gmpy2.get_context()
        saved_prec = ctx.precision
        ctx.precision = prec
        try:
            e_val = gmpy2.mpfr(Q) / gmpy2.mpfr(P)
            mantissa, exp, _ = e_val.digits(10, 55)
            int_part = mantissa[:exp] if exp > 0 else '0'
            dec_part = mantissa[exp:51]
            result = f"{int_part}.{dec_part}"
        finally:
            ctx.precision = saved_prec
        self.assertEqual(result, E_REF)


# ---------------------------------------------------------------------------
# _bs_chunk_worker — requires gmpy2
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestBsChunkWorker(unittest.TestCase):
    """Tests for _bs_chunk_worker (requires gmpy2)."""

    def setUp(self):
        from e import _bs_chunk_worker, _taylor_bs
        self.worker = _bs_chunk_worker
        self.bs = _taylor_bs

    def test_returns_plain_python_ints(self):
        P, Q = self.worker(0, 10)
        self.assertIsInstance(P, int)
        self.assertIsInstance(Q, int)

    def test_values_match_taylor_bs(self):
        P_w, Q_w = self.worker(0, 20)
        P_bs, Q_bs = self.bs(0, 20)
        self.assertEqual(P_w, int(P_bs))
        self.assertEqual(Q_w, int(Q_bs))

    def test_non_zero_range(self):
        P, Q = self.worker(10, 20)
        P_bs, Q_bs = self.bs(10, 20)
        self.assertEqual(P, int(P_bs))
        self.assertEqual(Q, int(Q_bs))


# ---------------------------------------------------------------------------
# _e_to_str output format
# ---------------------------------------------------------------------------

class TestEToStr(unittest.TestCase):
    """Tests for _e_to_str: format, length, and known-digit checks."""

    @classmethod
    def setUpClass(cls):
        cls._e50 = _quiet_e(50)

    def test_starts_with_2_dot(self):
        result = _e_to_str(self._e50, 10)
        self.assertTrue(result.startswith("2."), f"Expected '2.' prefix, got: {result!r}")

    def test_no_exponent_notation(self):
        result = _e_to_str(self._e50, 10)
        self.assertNotIn("e", result.lower())

    def test_exactly_n_decimal_places(self):
        for digits in (10, 20, 50):
            with self.subTest(digits=digits):
                result = _e_to_str(self._e50, digits)
                _, dec = result.split(".")
                self.assertEqual(len(dec), digits)

    def test_known_10_digits(self):
        result = _e_to_str(self._e50, 10)
        self.assertEqual(result, E_REF[:12])

    def test_known_20_digits(self):
        result = _e_to_str(self._e50, 20)
        self.assertEqual(result, E_REF[:22])

    def test_known_50_digits(self):
        result = _e_to_str(self._e50, 50)
        self.assertEqual(result, E_REF)


# ---------------------------------------------------------------------------
# calculate_e — end-to-end accuracy
# ---------------------------------------------------------------------------

class TestEAccuracy(unittest.TestCase):
    """End-to-end accuracy tests against the known decimal expansion of e."""

    def _assert_correct(self, digits):
        e_val = _quiet_e(digits)
        e_str = _e_to_str(e_val, digits)
        expected = E_REF[:digits + 2]
        self.assertEqual(e_str, expected,
                         f"e to {digits} digits incorrect: {e_str!r}")

    def test_10_digits(self):
        self._assert_correct(10)

    def test_20_digits(self):
        self._assert_correct(20)

    def test_50_digits(self):
        self._assert_correct(50)

    def test_result_is_not_none(self):
        result = _quiet_e(10)
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# mpmath fallback path
# ---------------------------------------------------------------------------

class TestMpmathFallback(unittest.TestCase):
    """When gmpy2 is unavailable, calculate_e uses mpmath."""

    def test_fallback_returns_correct_digits(self):
        with unittest.mock.patch.object(e_module, "_HAS_GMPY2", False):
            e_val = _quiet_e(20)
        with unittest.mock.patch.object(e_module, "_HAS_GMPY2", False):
            result = _e_to_str(e_val, 20)
        self.assertEqual(result[:22], E_REF[:22])

    def test_fallback_result_is_mpmath_type(self):
        with unittest.mock.patch.object(e_module, "_HAS_GMPY2", False):
            e_val = _quiet_e(10)
        self.assertIn("mpmath", type(e_val).__module__)


# ---------------------------------------------------------------------------
# Parallel path — requires gmpy2
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestCalculateEParallel(unittest.TestCase):
    """Parallel path (n_workers > 1) matches sequential."""

    def test_parallel_result_matches_serial(self):
        with unittest.mock.patch.object(e_module, "_CPU_COUNT", 4):
            e_parallel = _quiet_e(2000)
        e_serial = _quiet_e(20)
        s_par = _e_to_str(e_parallel, 20)
        s_ser = _e_to_str(e_serial, 20)
        self.assertEqual(s_par[:22], E_REF[:22])
        self.assertEqual(s_ser[:22], s_par[:22])


# ---------------------------------------------------------------------------
# get_target_digits — non-interactive paths
# ---------------------------------------------------------------------------

class TestGetTargetDigits(unittest.TestCase):
    """get_target_digits with CLI args (non-interactive paths only)."""

    class _Args:
        def __init__(self, digits):
            self.digits = digits

    def test_returns_digits_from_args(self):
        self.assertEqual(get_target_digits(self._Args(50)), 50)

    def test_raises_on_zero(self):
        with self.assertRaises(ValueError):
            get_target_digits(self._Args(0))

    def test_raises_on_negative(self):
        with self.assertRaises(ValueError):
            get_target_digits(self._Args(-1))

    def test_large_digits_prints_warning_and_returns(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = get_target_digits(self._Args(2_000_000))
        self.assertEqual(result, 2_000_000)
        self.assertIn("Warning", buf.getvalue())

    def test_minimum_valid_value(self):
        self.assertEqual(get_target_digits(self._Args(1)), 1)


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------

class TestParseArgs(unittest.TestCase):
    """parse_args correctly handles CLI arguments."""

    def test_no_args_gives_none(self):
        with unittest.mock.patch("sys.argv", ["e.py"]):
            args = parse_args()
        self.assertIsNone(args.digits)

    def test_positional_digit_arg(self):
        with unittest.mock.patch("sys.argv", ["e.py", "100"]):
            args = parse_args()
        self.assertEqual(args.digits, 100)

    def test_invalid_arg_exits(self):
        with unittest.mock.patch("sys.argv", ["e.py", "abc"]):
            with self.assertRaises(SystemExit):
                parse_args()


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Create `e/e.py` with stubs so imports work**

```python
#!/usr/bin/env python3
"""
Calculate Euler's number e to a user-specified number of decimal places.

Uses the Taylor series e = sum(1/n!) with binary splitting and
gmpy2/GMP (if available) for a 5-50x speedup over the mpmath fallback.

Install fast backend (recommended):
    bash install_deps.sh
"""

import argparse
import concurrent.futures
import multiprocessing
import mpmath
import os
import sys
import threading
import time

try:
    import gmpy2 as _gmpy2
    _HAS_GMPY2 = True
except ImportError:
    _gmpy2 = None
    _HAS_GMPY2 = False

_CPU_COUNT = os.cpu_count() or 1
_IO_WORKERS = max(2, min(8, _CPU_COUNT))
_PWRITE_CHUNK = 4 * 1024 * 1024

_gmpy2_PQ_cache: tuple = ()


def _taylor_bs(a, b):
    pass


def _bs_chunk_worker(a, b):
    pass


def _tree_combine(pq_list):
    pass


def _calculate_e_gmpy2(digits):
    pass


def _e_to_str(e_value, digits):
    pass


def calculate_e(digits=1000):
    pass


def parse_args():
    pass


def get_target_digits(args):
    pass


def main():
    pass


if __name__ == "__main__":
    if multiprocessing.current_process().name == "MainProcess":
        try:
            import mpmath
        except ImportError:
            print("Error: mpmath is required.  Run: pip install mpmath")
            sys.exit(1)
        main()
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd e && python3 -m unittest test_e -v 2>&1 | tail -20
```

Expected: multiple FAIL/ERROR lines

- [ ] **Step 4: Implement `_taylor_bs(a, b)` in `e/e.py`**

```python
def _taylor_bs(a, b):
    """
    Binary splitting for the Taylor series of e, range [a, b).

    Returns (P, Q) as gmpy2.mpz such that the partial sum
    sum_{k=a}^{b-1} 1/k! can be recovered from Q(a,b) / P(a,b).

    Base case (single term): P(a, a+1) = a+1, Q(a, a+1) = a+1
    Special case a=0: P=1, Q=1 (the 1/0! = 1 term)

    The final result is e = Q(0,N) / P(0,N) — the leading 1/0! term
    is included in the recursion (leaf 0 has Q=1, P=1).

    Merge rule for [a, m) and [m, b):
        P(a,b) = P(a,m) * P(m,b)
        Q(a,b) = Q(a,m) * P(m,b) + Q(m,b)
    """
    if b - a == 1:
        if a == 0:
            return _gmpy2.mpz(1), _gmpy2.mpz(1)
        return _gmpy2.mpz(a + 1), _gmpy2.mpz(a + 1)
    m = (a + b) >> 1
    Pl, Ql = _taylor_bs(a, m)
    Pr, Qr = _taylor_bs(m, b)
    return Pl * Pr, Ql * Pr + Qr
```

- [ ] **Step 5: Implement `_bs_chunk_worker(a, b)` in `e/e.py`**

```python
def _bs_chunk_worker(a, b):
    """
    Subprocess worker: compute Taylor binary splitting for range [a, b).
    Returns (P, Q) as plain Python ints so they are always picklable.
    """
    P, Q = _taylor_bs(a, b)
    return int(P), int(Q)
```

- [ ] **Step 6: Implement `_tree_combine(pq_list)` in `e/e.py`**

```python
def _tree_combine(pq_list):
    """
    Reduce a list of (P, Q) tuples using pairwise tree combination.

    Combination rule for adjacent ranges [a,m) and [m,b):
        P(a,b) = P(a,m) * P(m,b)
        Q(a,b) = Q(a,m) * P(m,b) + Q(m,b)
    """
    while len(pq_list) > 1:
        next_level = []
        for i in range(0, len(pq_list), 2):
            if i + 1 < len(pq_list):
                Pl, Ql = pq_list[i]
                Pr, Qr = pq_list[i + 1]
                next_level.append((Pl * Pr, Ql * Pr + Qr))
            else:
                next_level.append(pq_list[i])
        pq_list = next_level
    return pq_list[0]
```

- [ ] **Step 7: Implement `_calculate_e_gmpy2(digits)` in `e/e.py`**

```python
def _calculate_e_gmpy2(digits):
    """
    Compute e using Taylor binary splitting + gmpy2/GMP.

    When _CPU_COUNT > 1 and N is large enough, splits [0, N) into chunks
    and computes in parallel using ProcessPoolExecutor.

    Returns (e_mpfr, P_int, Q_int).
    """
    import math
    N = int(digits / math.log10(digits + 1)) + 50 if digits > 1 else 20

    chunk_size = max(100, (N + _CPU_COUNT - 1) // _CPU_COUNT)
    ranges = []
    start = 0
    while start < N:
        ranges.append((start, min(start + chunk_size, N)))
        start += chunk_size
    n_workers = len(ranges)

    if n_workers > 1:
        mp_context = multiprocessing.get_context(
            'fork' if sys.platform == 'linux' else 'spawn'
        )
        print(
            f"  Parallel series: {n_workers} workers "
            f"× ~{chunk_size:,} terms each"
        )
        bar_width = 30
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=n_workers, mp_context=mp_context
        ) as pool:
            futures = [pool.submit(_bs_chunk_worker, a, b) for a, b in ranges]
            completed = 0
            for _ in concurrent.futures.as_completed(futures):
                completed += 1
                filled = completed * bar_width // n_workers
                bar = '█' * filled + '░' * (bar_width - filled)
                print(
                    f"\r  [{bar}] {completed}/{n_workers} chunks",
                    end="", flush=True,
                )
        print()

        int_results = [f.result() for f in futures]

        print("  Combining chunks...", end="", flush=True)
        pq_list = [
            (_gmpy2.mpz(P), _gmpy2.mpz(Q))
            for P, Q in int_results
        ]
        P, Q = _tree_combine(pq_list)
        print("\r  Combination complete.   ")
    else:
        P, Q = _taylor_bs(0, N)

    prec = int(digits * 3.3219280948873626) + 100

    ctx = _gmpy2.get_context()
    saved_prec = ctx.precision
    ctx.precision = prec
    try:
        e_mpfr = _gmpy2.mpfr(Q) / _gmpy2.mpfr(P)
    finally:
        ctx.precision = saved_prec

    return e_mpfr, int(P), int(Q)
```

- [ ] **Step 8: Implement `_e_to_str(e_value, digits)` in `e/e.py`**

```python
def _e_to_str(e_value, digits):
    """
    Convert an e value to a decimal string with *digits* decimal places.
    """
    if _HAS_GMPY2 and isinstance(e_value, _gmpy2.mpfr):
        mantissa, exp, _ = e_value.digits(10, digits + 5)
        sign = ''
        if mantissa.startswith('-'):
            sign, mantissa = '-', mantissa[1:]
        int_part = mantissa[:exp] if exp > 0 else '0'
        dec_part = mantissa[exp:digits + 1]
        return f"{sign}{int_part}.{dec_part}"
    return mpmath.nstr(e_value, digits + 1, strip_zeros=False)
```

- [ ] **Step 9: Implement `calculate_e(digits)` in `e/e.py`**

```python
def calculate_e(digits=1000):
    """
    Calculate e to the specified number of decimal places.

    Tries the fast Taylor/gmpy2 path first; falls back to mpmath.
    """
    print(f"Calculating e to {digits:,} decimal places...")
    print(f"Running on {_CPU_COUNT} CPU core{'s' if _CPU_COUNT != 1 else ''}...")

    if _HAS_GMPY2:
        print(
            f"Backend: Taylor binary splitting / gmpy2 {_gmpy2.version()} "
            f"(GMP {_gmpy2.mp_version()}, MPFR {_gmpy2.mpfr_version()})"
        )
        start = time.time()
        e_mpfr, P_int, Q_int = _calculate_e_gmpy2(digits)
        elapsed = time.time() - start
        print(f"\nCalculation completed in {elapsed:.2f} seconds")
        global _gmpy2_PQ_cache
        _gmpy2_PQ_cache = (P_int, Q_int)
        return e_mpfr

    print(
        f"Backend: mpmath {mpmath.__version__} "
        f"(install gmpy2 for 5-50x faster computation — see install_deps.sh)"
    )
    print("This may take a while for high precision calculations...")
    mpmath.mp.dps = digits + 50
    start = time.time()
    e_value = mpmath.e
    elapsed = time.time() - start
    print(f"\nCalculation completed in {elapsed:.2f} seconds")
    return e_value
```

- [ ] **Step 10: Run all tests to confirm they pass**

```bash
cd e && python3 -m unittest test_e -v
```

Expected: all tests pass

- [ ] **Step 11: Commit**

```bash
git add e/e.py e/test_e.py
git commit -m "feat: implement Python e calculator core (binary splitting + TDD)"
```

---

## Task 4: Python CLI, preview, and file save

**Files:** Modify `e/e.py`, Modify `e/test_e.py`

- [ ] **Step 1: Add file save and preview tests to `e/test_e.py`**

Append after the existing test classes:

```python
# ---------------------------------------------------------------------------
# show_e_preview
# ---------------------------------------------------------------------------

class TestShowEPreview(unittest.TestCase):
    """show_e_preview prints a correctly formatted e preview."""

    @classmethod
    def setUpClass(cls):
        cls._e = _quiet_e(50)

    def _capture(self, digits):
        buf = io.StringIO()
        with redirect_stdout(buf):
            from e import show_e_preview
            show_e_preview(self._e, digits)
        return buf.getvalue()

    def test_output_contains_e_equals(self):
        out = self._capture(10)
        self.assertIn("e =", out)

    def test_output_starts_with_2_dot(self):
        out = self._capture(10)
        self.assertIn("2.", out)

    def test_output_mentions_decimal_places(self):
        out = self._capture(10)
        self.assertIn("decimal places", out)

    def test_preview_capped_at_200(self):
        out = self._capture(500)
        self.assertIn("200", out)


# ---------------------------------------------------------------------------
# save_e_to_file
# ---------------------------------------------------------------------------

class TestSaveEToFile(unittest.TestCase):
    """save_e_to_file writes a correctly structured output file."""

    @classmethod
    def setUpClass(cls):
        cls._e = _quiet_e(50)

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        self._path = self._tmp.name
        self._tmp.close()

    def tearDown(self):
        os.unlink(self._path)

    def _save(self, digits=50):
        buf = io.StringIO()
        with redirect_stdout(buf):
            from e import save_e_to_file
            save_e_to_file(self._e, digits, self._path)

    def test_file_is_created(self):
        self._save()
        self.assertTrue(os.path.exists(self._path))

    def test_file_contains_header(self):
        self._save()
        with open(self._path) as f:
            content = f.read()
        self.assertIn("e calculated to", content)

    def test_file_contains_e_digits(self):
        self._save()
        with open(self._path) as f:
            content = f.read()
        self.assertIn("2.71828182845904", content)

    def test_file_contains_footer(self):
        self._save()
        with open(self._path) as f:
            content = f.read()
        self.assertIn("Total decimal places", content)

    def test_file_size_is_nonzero(self):
        self._save()
        self.assertGreater(os.path.getsize(self._path), 0)
```

- [ ] **Step 2: Implement `parse_args()` and `get_target_digits()` in `e/e.py`**

```python
def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Calculate Euler's number e to a specified number of decimal places.",
        epilog=(
            "Run without arguments to use the interactive prompts, or provide "
            "the number of digits directly."
        ),
    )
    parser.add_argument(
        "digits",
        nargs="?",
        type=int,
        help="number of decimal places to calculate",
    )
    return parser.parse_args()


def get_target_digits(args):
    """Get the requested digit count from CLI args or interactive input."""
    if args.digits is not None:
        if args.digits < 1:
            raise ValueError("Please enter a positive number of decimal places.")
        if args.digits > 1000000:
            print("Warning: Very large numbers may take a long time to calculate.")
        return args.digits

    while True:
        try:
            user_input = input("Enter the number of decimal places to calculate e (1-1000000): ")
            target_digits = int(user_input)
            if target_digits < 1:
                print("Please enter a positive number.")
                continue
            if target_digits > 1000000:
                print("Warning: Very large numbers may take a long time to calculate.")
                confirm = input(f"Continue with {target_digits} digits? (y/n): ").lower().strip()
                if confirm not in ['y', 'yes']:
                    continue
            return target_digits
        except ValueError:
            print("Please enter a valid integer.")
```

- [ ] **Step 3: Implement `show_e_preview()` in `e/e.py`**

```python
def show_e_preview(e_value, preview_digits=100):
    """Show a preview of e with specified number of digits."""
    actual_preview = min(preview_digits, 200)
    print(f"Generating preview of e ({actual_preview} digits)...")
    e_str = _e_to_str(e_value, actual_preview)
    if '.' in e_str:
        integer_part, decimal_part = e_str.split('.', 1)
    else:
        integer_part, decimal_part = e_str, ""
    print(f"\ne = {integer_part}.{decimal_part}...")
    print(f"(Showing first {len(decimal_part)} decimal places)")
```

- [ ] **Step 4: Implement `_gmpy2_str_from_PQ()`, `_convert_gmpy2_worker()`, `_convert_mpmath_worker()`, `_pwrite_all()` in `e/e.py`**

Add these module-level functions:

```python
def _gmpy2_str_from_PQ(P_int, Q_int, digits):
    """Recompute e from integer accumulators and return decimal string."""
    prec = int(digits * 3.3219280948873626) + 100
    ctx = _gmpy2.get_context()
    saved_prec = ctx.precision
    ctx.precision = prec
    try:
        P = _gmpy2.mpz(P_int)
        Q = _gmpy2.mpz(Q_int)
        e_mpfr = _gmpy2.mpfr(Q) / _gmpy2.mpfr(P)
        mantissa, exp, _ = e_mpfr.digits(10, digits + 5)
    finally:
        ctx.precision = saved_prec

    sign = ''
    if mantissa.startswith('-'):
        sign, mantissa = '-', mantissa[1:]
    int_part = mantissa[:exp] if exp > 0 else '0'
    dec_part = mantissa[exp:digits + 1]
    return f"{sign}{int_part}.{dec_part}"


def _convert_gmpy2_worker(P_int, Q_int, digits):
    """Subprocess worker: recompute e and convert to decimal string."""
    return _gmpy2_str_from_PQ(P_int, Q_int, digits)


def _convert_mpmath_worker(e_value, digits):
    """Subprocess worker: convert mpmath value to decimal string."""
    return mpmath.nstr(e_value, digits + 1, strip_zeros=False)


def _pwrite_all(fd, data, offset):
    """Write all bytes to fd at absolute offset using os.pwrite(2)."""
    view = memoryview(data)
    written = 0
    while written < len(view):
        n = os.pwrite(fd, view[written:], offset + written)
        if n == 0:
            raise OSError("os.pwrite returned 0 — file write stalled")
        written += n
    return written
```

- [ ] **Step 5: Implement `save_e_to_file()` in `e/e.py`**

Follow the same pattern as `save_pi_to_file()` from `pi/pi.py` — subprocess string conversion + parallel pwrite. Replace "π" with "e" in all labels and file headers. Use `_gmpy2_PQ_cache` instead of `_gmpy2_QT_cache`.

- [ ] **Step 6: Implement `main()` in `e/e.py`**

```python
def main():
    """Main function to execute e calculation."""
    try:
        args = parse_args()

        print("High-Precision e Calculator")
        print("=" * 40)

        target_digits = get_target_digits(args)
        e_result = calculate_e(target_digits)

        if target_digits <= 1_000_000:
            preview_digits = min(100, target_digits)
            show_e_preview(e_result, preview_digits)
        else:
            print(f"\nSkipping preview for {target_digits:,} digits (too large for quick preview)")

        if target_digits > 10000:
            filename = f"e_{target_digits}_digits.txt"
            print(f"\nFor {target_digits:,} digits, saving to file for better performance...")
            save_e_to_file(e_result, target_digits, filename)
            print(f"\nFull precision e saved to {filename}")
        else:
            print(f"\nWould you like to display all {target_digits:,} digits? (y/n): ", end="")
            response = input().lower().strip()
            if response in ['y', 'yes']:
                e_str = _e_to_str(e_result, target_digits)
                print(f"\ne = {e_str}")
                print(f"\nTotal digits: {target_digits:,}")
            else:
                filename = f"e_{target_digits}_digits.txt"
                save_e_to_file(e_result, target_digits, filename)
                print(f"\nFull precision e saved to {filename}")

    except KeyboardInterrupt:
        print("\n\nCalculation interrupted by user.")
        sys.exit(1)
    except ValueError as error:
        print(f"\nError: {error}")
        sys.exit(1)
    except Exception as ex:
        print(f"\nError occurred during calculation: {ex}")
        sys.exit(1)
```

- [ ] **Step 7: Run lint**

```bash
cd e && make lint
```

Expected: `All checks passed!`

- [ ] **Step 8: Run all Python tests**

```bash
cd e && make test
```

Expected: all tests pass

- [ ] **Step 9: Commit**

```bash
git add e/e.py e/test_e.py
git commit -m "feat: add Python CLI, preview, and file save for e calculator"
```

---

## Task 5: Scaffold Rust project

**Files:** Create `e/e-rs/Cargo.toml`, `e/e-rs/Makefile`, `e/e-rs/install_deps.sh`, `e/e-rs/src/main.rs` (stub)

- [ ] **Step 1: Create directories**

```bash
mkdir -p e/e-rs/src
```

- [ ] **Step 2: Create `e/e-rs/Cargo.toml`**

```toml
[package]
name = "e"
version = "0.1.0"
edition = "2021"
description = "High-precision e calculator — Taylor binary splitting + Rayon + GMP"

[[bin]]
name = "e"
path = "src/main.rs"

[dependencies]
rug = { version = "1", features = ["integer", "float"] }
rayon = "1"
clap = { version = "4", features = ["derive"] }

[profile.release]
opt-level   = 3
lto         = "thin"
codegen-units = 1
```

- [ ] **Step 3: Create `e/e-rs/Makefile`**

```makefile
.PHONY: e lint test clean

e:
	cargo build --release
	cp target/release/e ~/Downloads/e

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/e
```

- [ ] **Step 4: Create `e/e-rs/install_deps.sh`**

Same pattern as `pi/pi-rs/install_deps.sh` — platform detection for GMP+MPFR, Rust toolchain, cargo-tarpaulin. Replace "pi-rs" with "e-rs" in labels.

- [ ] **Step 5: Make it executable**

```bash
chmod +x e/e-rs/install_deps.sh
```

- [ ] **Step 6: Create minimal `e/e-rs/src/main.rs` stub**

```rust
fn main() {}
```

- [ ] **Step 7: Verify it compiles**

```bash
cd e/e-rs && cargo build 2>&1 | tail -5
```

Expected: `Finished` with no errors

- [ ] **Step 8: Commit**

```bash
git add e/e-rs/
git commit -m "chore: scaffold e-rs Rust project"
```

---

## Task 6: Rust binary splitting and core computation — TDD

**Files:** Modify `e/e-rs/src/main.rs`

- [ ] **Step 1: Replace `e/e-rs/src/main.rs` with full structure + tests (stubs for functions)**

```rust
/*!
Calculate Euler's number e to a user-specified number of decimal places.

Uses the Taylor series e = sum(1/n!) with binary splitting:
  - rayon::join()     — recursive parallel binary splitting across all cores
  - rug::Integer      — GMP big-integer arithmetic for the series accumulation
  - rug::Float        — MPFR arbitrary-precision float for the final value
  - pwrite(2)         — parallel file I/O (os::unix::fs::FileExt::write_at)

Build (requires GMP + MPFR; run install_deps.sh first):
    cargo build --release
    ./target/release/e [digits]
*/

use std::fs::File;
use std::io::{self, BufRead, Write};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

#[cfg(unix)]
use std::os::unix::fs::FileExt;

use clap::Parser;
use rayon::prelude::*;
use rug::{Float, Integer};

#[derive(Parser)]
#[command(
    name = "e",
    about = "Calculate Euler's number e to a specified number of decimal places",
    long_about = "Calculate Euler's number e to a specified number of decimal places using the \
                  Taylor series with Rayon parallelism and GMP arithmetic.\n\n\
                  Run without arguments to use interactive prompts."
)]
struct Cli {
    /// Number of decimal places to calculate
    digits: Option<usize>,
}

const BS_PAR_THRESHOLD: u64 = 512;

static BS_LEAF_COUNT: AtomicU64 = AtomicU64::new(0);

struct Pq {
    p: Integer,
    q: Integer,
}

fn bs(a: u64, b: u64) -> Pq {
    Pq { p: Integer::from(1u32), q: Integer::from(0u32) }
}

fn bs_leaf(a: u64) -> Pq {
    Pq { p: Integer::from(1u32), q: Integer::from(0u32) }
}

fn bs_merge(l: Pq, r: Pq) -> Pq {
    Pq { p: Integer::from(1u32), q: Integer::from(0u32) }
}

fn compute_e(digits: usize) -> String {
    String::new()
}

fn e_to_string(e: Float, digits: usize) -> String {
    String::new()
}

fn fmt_int(n: usize) -> String {
    String::new()
}

fn read_line() -> String {
    let stdin = io::stdin();
    let mut line = String::new();
    stdin.lock().read_line(&mut line).unwrap();
    line.trim().to_string()
}

fn prompt_digits() -> usize {
    1
}

fn main() {}

#[cfg(test)]
mod tests {
    use super::*;

    const E_REF: &str = "2.71828182845904523536028747135266249775724709369995";

    // --- fmt_int ---

    #[test]
    fn test_fmt_int_zero() {
        assert_eq!(fmt_int(0), "0");
    }

    #[test]
    fn test_fmt_int_below_thousand() {
        assert_eq!(fmt_int(999), "999");
    }

    #[test]
    fn test_fmt_int_thousands() {
        assert_eq!(fmt_int(1_000), "1,000");
        assert_eq!(fmt_int(10_000), "10,000");
    }

    #[test]
    fn test_fmt_int_millions() {
        assert_eq!(fmt_int(1_234_567), "1,234,567");
    }

    #[test]
    fn test_fmt_int_billions() {
        assert_eq!(fmt_int(1_000_000_000), "1,000,000,000");
    }

    // --- bs_leaf ---

    #[test]
    fn test_bs_leaf_zero() {
        let pq = bs_leaf(0);
        assert_eq!(pq.p, Integer::from(1u32));
        assert_eq!(pq.q, Integer::from(1u32));
    }

    #[test]
    fn test_bs_leaf_one() {
        // a=1: P = a+1 = 2, Q = a+1 = 2
        let pq = bs_leaf(1);
        assert_eq!(pq.p, Integer::from(2u32));
        assert_eq!(pq.q, Integer::from(2u32));
    }

    #[test]
    fn test_bs_leaf_two() {
        // a=2: P = 3, Q = 3
        let pq = bs_leaf(2);
        assert_eq!(pq.p, Integer::from(3u32));
        assert_eq!(pq.q, Integer::from(3u32));
    }

    #[test]
    fn test_bs_leaf_increments_counter() {
        let before = BS_LEAF_COUNT.load(Ordering::Relaxed);
        bs_leaf(0);
        bs_leaf(1);
        let after = BS_LEAF_COUNT.load(Ordering::Relaxed);
        assert!(after >= before + 2);
    }

    // --- bs_merge ---

    #[test]
    fn test_bs_merge_matches_two_leaves() {
        let merged = bs_merge(bs_leaf(0), bs_leaf(1));
        let full = bs(0, 2);
        assert_eq!(merged.p, full.p);
        assert_eq!(merged.q, full.q);
    }

    // --- bs (split consistency) ---

    #[test]
    fn test_bs_split_consistency_4() {
        let full = bs(0, 4);
        let merged = bs_merge(bs(0, 2), bs(2, 4));
        assert_eq!(full.p, merged.p);
        assert_eq!(full.q, merged.q);
    }

    #[test]
    fn test_bs_split_consistency_8() {
        let full = bs(0, 8);
        let merged = bs_merge(bs(0, 4), bs(4, 8));
        assert_eq!(full.p, merged.p);
        assert_eq!(full.q, merged.q);
    }

    // --- e_to_string ---

    #[test]
    fn test_e_to_string_starts_with_2_dot() {
        let e = Float::with_val(200, rug::float::Constant::Euler);
        // rug's Constant::Euler is the Euler-Mascheroni constant, not e.
        // Compute e from scratch for testing.
        let e = Float::with_val(200, 1u32).exp();
        let s = e_to_string(e, 10);
        assert!(s.starts_with("2."));
    }

    #[test]
    fn test_e_to_string_exact_decimal_count() {
        let e = Float::with_val(200, 1u32).exp();
        let s = e_to_string(e, 20);
        assert_eq!(s.len(), 22);
    }

    #[test]
    fn test_e_to_string_no_exponent_notation() {
        let e = Float::with_val(200, 1u32).exp();
        let s = e_to_string(e, 15);
        assert!(!s.contains('e') && !s.contains('E'));
    }

    #[test]
    fn test_e_to_string_known_digits() {
        let e = Float::with_val(200, 1u32).exp();
        let s = e_to_string(e, 15);
        assert_eq!(&s[..17], &E_REF[..17]);
    }

    #[test]
    fn test_e_to_string_single_decimal_place() {
        let e = Float::with_val(200, 1u32).exp();
        let s = e_to_string(e, 1);
        assert_eq!(s.len(), 3);
        assert_eq!(s, "2.7");
    }

    // --- compute_e (end-to-end accuracy) ---

    #[test]
    fn test_compute_e_10_digits() {
        let s = compute_e(10);
        assert_eq!(&s[..12], &E_REF[..12]);
    }

    #[test]
    fn test_compute_e_50_digits() {
        let s = compute_e(50);
        assert_eq!(s, E_REF);
    }
}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd e/e-rs && cargo test 2>&1 | tail -20
```

Expected: multiple failures (stubs return wrong values)

- [ ] **Step 3: Implement `fmt_int`**

```rust
fn fmt_int(n: usize) -> String {
    let s = n.to_string();
    let mut out = String::with_capacity(s.len() + s.len() / 3);
    for (i, ch) in s.chars().rev().enumerate() {
        if i > 0 && i % 3 == 0 {
            out.push(',');
        }
        out.push(ch);
    }
    out.chars().rev().collect()
}
```

- [ ] **Step 4: Implement `bs_leaf`**

```rust
fn bs_leaf(a: u64) -> Pq {
    let result = if a == 0 {
        Pq {
            p: Integer::from(1u32),
            q: Integer::from(1u32),
        }
    } else {
        Pq {
            p: Integer::from(a + 1),
            q: Integer::from(a + 1),
        }
    };

    BS_LEAF_COUNT.fetch_add(1, Ordering::Relaxed);
    result
}
```

- [ ] **Step 5: Implement `bs_merge`**

```rust
/// Combine two adjacent ranges [a,m) and [m,b):
///   P(a,b) = P(a,m) × P(m,b)
///   Q(a,b) = Q(a,m) × P(m,b) + Q(m,b)
fn bs_merge(l: Pq, r: Pq) -> Pq {
    Pq {
        p: Integer::from(&l.p * &r.p),
        q: Integer::from(&l.q * &r.p) + &r.q,
    }
}
```

- [ ] **Step 6: Implement `bs`**

```rust
fn bs(a: u64, b: u64) -> Pq {
    debug_assert!(b > a);

    if b - a == 1 {
        return bs_leaf(a);
    }

    let m = a + (b - a) / 2;

    if b - a <= BS_PAR_THRESHOLD {
        let l = bs(a, m);
        let r = bs(m, b);
        return bs_merge(l, r);
    }

    let (l, r) = rayon::join(|| bs(a, m), || bs(m, b));
    bs_merge(l, r)
}
```

- [ ] **Step 7: Implement `e_to_string`**

```rust
fn e_to_string(e: Float, digits: usize) -> String {
    let raw = e.to_string_radix(10, Some(digits + 5));
    let raw: &str = match raw.find(['e', 'E']) {
        Some(pos) => &raw[..pos],
        None => &raw,
    };

    if let Some(dot) = raw.find('.') {
        let want = dot + 1 + digits;
        if raw.len() >= want {
            raw[..want].to_string()
        } else {
            format!("{}{}", raw, "0".repeat(want - raw.len()))
        }
    } else {
        format!("{}.{}", raw, "0".repeat(digits))
    }
}
```

- [ ] **Step 8: Implement `compute_e`**

```rust
fn compute_e(digits: usize) -> String {
    let n = if digits > 1 {
        (digits as f64 / (digits as f64 + 1.0).log10()) as u64 + 50
    } else {
        20
    };
    let threads = rayon::current_num_threads();

    eprintln!(
        "  Series: {} terms, {} threads, threshold {}",
        fmt_int(n as usize),
        threads,
        BS_PAR_THRESHOLD
    );

    BS_LEAF_COUNT.store(0, Ordering::Relaxed);
    let series_done = Arc::new(AtomicBool::new(false));
    let series_done_c = Arc::clone(&series_done);
    let series_thread = thread::spawn(move || {
        loop {
            thread::sleep(Duration::from_millis(200));
            if series_done_c.load(Ordering::Relaxed) {
                break;
            }
            let completed = BS_LEAF_COUNT.load(Ordering::Relaxed);
            let pct = completed * 100 / n;
            eprint!(
                "\r  Computing series:  {:3}%  ({} / {} terms)   ",
                pct,
                fmt_int(completed as usize),
                fmt_int(n as usize),
            );
            let _ = io::stderr().flush();
        }
    });

    let t0 = Instant::now();
    let pq = bs(0, n);
    series_done.store(true, Ordering::Relaxed);
    series_thread.join().unwrap();
    eprintln!(
        "\r  Computing series:  100%  ({} terms)   ",
        fmt_int(n as usize)
    );
    eprintln!("  Series done in {:.2}s", t0.elapsed().as_secs_f64());

    // e = Q / P  (the 1/0! term is included in the recursion via leaf 0)
    let prec_bits = (digits as f64 * 3.321_928_094_887_362_6) as u32 + 100;
    eprintln!("  Computing final value ({} bits)…", prec_bits);

    let t1 = Instant::now();
    let e = Float::with_val(prec_bits, &pq.q) / Float::with_val(prec_bits, &pq.p);
    eprintln!("  Value done in {:.2}s", t1.elapsed().as_secs_f64());

    eprintln!("  Converting to decimal string…");
    let t2 = Instant::now();
    let s = e_to_string(e, digits);
    eprintln!("  Conversion done in {:.2}s", t2.elapsed().as_secs_f64());

    s
}
```

- [ ] **Step 9: Run all Rust tests**

```bash
cd e/e-rs && make test
```

Expected: all tests pass, clippy clean

- [ ] **Step 10: Commit**

```bash
git add e/e-rs/src/main.rs
git commit -m "feat: implement Rust e calculator core (binary splitting + TDD)"
```

---

## Task 7: Rust CLI and file I/O

**Files:** Modify `e/e-rs/src/main.rs`

- [ ] **Step 1: Implement `prompt_digits`**

```rust
fn prompt_digits() -> usize {
    loop {
        print!("Enter the number of decimal places to calculate e: ");
        io::stdout().flush().unwrap();
        match read_line().parse::<usize>() {
            Ok(n) if n >= 1 => {
                if n > 1_000_000 {
                    eprintln!("Warning: very large numbers may take a long time.");
                    print!("Continue with {} digits? (y/n): ", fmt_int(n));
                    io::stdout().flush().unwrap();
                    if !matches!(read_line().as_str(), "y" | "yes") {
                        continue;
                    }
                }
                return n;
            }
            _ => eprintln!("Please enter a positive integer."),
        }
    }
}
```

- [ ] **Step 2: Implement `write_e_file`**

Follow the same pattern as `write_pi_file()` from `pi/pi-rs/src/main.rs`:

- Replace "π" with "e" in file headers
- Replace "Chudnovsky/Rayon" with "Taylor/Rayon"
- Same parallel pwrite pattern with progress thread

```rust
#[cfg(unix)]
fn write_e_file(filename: &str, e_str: &str, digits: usize) -> io::Result<()> {
    let header = format!(
        "e calculated to {} decimal places using Taylor/Rayon\n{}\n\n",
        fmt_int(digits),
        "=".repeat(60),
    );
    let footer = format!("\n\nTotal decimal places: {}", fmt_int(digits));

    let hdr = header.as_bytes();
    let e_bytes = e_str.as_bytes();
    let ftr = footer.as_bytes();

    let total = (hdr.len() + e_bytes.len() + ftr.len()) as u64;
    let e_offset = hdr.len() as u64;
    let e_total = e_bytes.len() as u64;

    let file = File::create(filename)?;
    file.set_len(total)?;

    file.write_at(hdr, 0)?;
    file.write_at(ftr, e_offset + e_total)?;

    let n_threads = rayon::current_num_threads();
    let chunk_size = ((4 * 1024 * 1024) as usize).max(e_bytes.len() / n_threads);

    let bytes_written = Arc::new(AtomicU64::new(0));
    let bytes_written_c = Arc::clone(&bytes_written);
    let write_done = Arc::new(AtomicBool::new(false));
    let write_done_c = Arc::clone(&write_done);
    let t_write = Instant::now();

    let progress_thread = thread::spawn(move || {
        loop {
            thread::sleep(Duration::from_millis(200));
            if write_done_c.load(Ordering::Relaxed) {
                break;
            }
            let written = bytes_written_c.load(Ordering::Relaxed);
            let elapsed = t_write.elapsed().as_secs_f64();
            let speed = if elapsed > 0.001 {
                written as f64 / elapsed / 1_048_576.0
            } else {
                0.0
            };
            let pct = (written * 100).checked_div(e_total).unwrap_or(100);
            eprint!(
                "\r  Writing: {:3}%  ({:.1} / {:.1} MB)  {:.1} MB/s   ",
                pct,
                written as f64 / 1_048_576.0,
                e_total as f64 / 1_048_576.0,
                speed,
            );
            let _ = io::stderr().flush();
        }
    });

    e_bytes
        .par_chunks(chunk_size)
        .enumerate()
        .try_for_each(|(i, chunk)| -> io::Result<()> {
            let base = e_offset + (i * chunk_size) as u64;
            let mut written = 0;
            while written < chunk.len() {
                written += file.write_at(&chunk[written..], base + written as u64)?;
            }
            bytes_written.fetch_add(chunk.len() as u64, Ordering::Relaxed);
            Ok(())
        })?;

    write_done.store(true, Ordering::Relaxed);
    progress_thread.join().unwrap();

    let elapsed = t_write.elapsed().as_secs_f64();
    let speed = if elapsed > 0.001 {
        e_total as f64 / elapsed / 1_048_576.0
    } else {
        0.0
    };
    eprintln!(
        "\r  Writing: 100%  ({:.1} MB)  {:.1} MB/s              ",
        e_total as f64 / 1_048_576.0,
        speed,
    );

    Ok(())
}
```

- [ ] **Step 3: Implement `main`**

```rust
fn main() {
    let cli = Cli::parse();

    println!("High-Precision e Calculator (Rust/Rayon)");
    println!("{}", "=".repeat(40));

    let digits = match cli.digits {
        Some(d) => {
            if d < 1 {
                eprintln!("Error: digits must be ≥ 1");
                std::process::exit(1);
            }
            if d > 1_000_000 {
                eprintln!("Warning: very large numbers may take a long time.");
            }
            d
        }
        None => prompt_digits(),
    };

    println!(
        "Calculating e to {} decimal places…",
        fmt_int(digits)
    );
    println!(
        "Backend: Taylor / rug+GMP+MPFR / rayon ({} threads)",
        rayon::current_num_threads()
    );

    let t_total = Instant::now();
    let e_str = compute_e(digits);
    println!("\nDone in {:.2}s", t_total.elapsed().as_secs_f64());

    if digits <= 1_000_000 {
        let preview = 100.min(digits);
        if let Some(dot) = e_str.find('.') {
            let end = (dot + 1 + preview).min(e_str.len());
            println!("\ne = {}…", &e_str[..end]);
            println!("(Showing first {} decimal places)", preview);
        }
    }

    if digits > 10_000 {
        let filename = format!("e_{}_digits.txt", digits);
        println!("\nSaving to {}…", filename);
        #[cfg(unix)]
        write_e_file(&filename, &e_str, digits).expect("file write failed");
        println!("Full precision e saved to {}", filename);
    } else {
        print!("\nDisplay all {} digits? (y/n): ", fmt_int(digits));
        io::stdout().flush().unwrap();
        if matches!(read_line().as_str(), "y" | "yes") {
            println!("\ne = {}", e_str);
            println!("\nTotal digits: {}", fmt_int(digits));
        } else {
            let filename = format!("e_{}_digits.txt", digits);
            #[cfg(unix)]
            write_e_file(&filename, &e_str, digits).expect("file write failed");
            println!("\nFull precision e saved to {}", filename);
        }
    }
}
```

- [ ] **Step 4: Run all Rust tests and lint**

```bash
cd e/e-rs && make test
```

Expected: all tests pass, clippy clean

- [ ] **Step 5: Commit**

```bash
git add e/e-rs/src/main.rs
git commit -m "feat: add Rust CLI, prompt, and file I/O for e calculator"
```

---

## Task 8: `.gitignore` update

**Files:** Modify `.gitignore`

- [ ] **Step 1: Add `e_*_digits.txt` to `.gitignore`**

Add after `twin-primes_1e*.txt`:

```
e_*_digits.txt
```

- [ ] **Step 2: Verify**

```bash
echo "e_1000_digits.txt" | git check-ignore --stdin
```

Expected: `e_1000_digits.txt`

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: add e_*_digits.txt to .gitignore"
```

---

## Task 9: Sub-project CLAUDE.md files

**Files:** Create `e/CLAUDE.md`, Create `e/e-rs/CLAUDE.md`

- [ ] **Step 1: Create `e/CLAUDE.md`**

Follow the pattern of `pi/CLAUDE.md`. Document:

- Repository Overview (Python CLI for computing e)
- Code Layout (all functions: `_taylor_bs`, `_bs_chunk_worker`, `_tree_combine`, `_calculate_e_gmpy2`, `_e_to_str`, `_gmpy2_str_from_PQ`, `_convert_gmpy2_worker`, `_convert_mpmath_worker`, `_pwrite_all`, `calculate_e`, `show_e_preview`, `save_e_to_file`, `parse_args`, `get_target_digits`, `main`)
- Module-level constants/state: `_HAS_GMPY2`, `_gmpy2_PQ_cache`, `_CPU_COUNT`, `_IO_WORKERS`, `_PWRITE_CHUNK`
- Important Behavior (gmpy2 fast path, mpmath fallback, subprocess conversion, parallel pwrite, spawn vs fork)
- Makefile targets: run, lint, test, coverage, clean
- Testing section with coverage table
- Editing Guidance

- [ ] **Step 2: Create `e/e-rs/CLAUDE.md`**

Follow the pattern of `pi/pi-rs/CLAUDE.md` (documented in `pi/CLAUDE.md` under the Rust section). Document:

- Repository Overview (Rust CLI for computing e)
- rug arithmetic note (incomplete types, `Integer::from()` wrapping)
- Code Layout: `Pq` struct, `bs`/`bs_leaf`/`bs_merge`, `compute_e`, `e_to_string`, `write_e_file`, `fmt_int`, progress thread pattern
- Important behavior: `write_e_file` is `#[cfg(unix)]` only
- Makefile targets: e, lint, test, clean
- Testing section with coverage table

- [ ] **Step 3: Commit**

```bash
git add e/CLAUDE.md e/e-rs/CLAUDE.md
git commit -m "docs: add CLAUDE.md files for e/ and e/e-rs/"
```

---

## Task 10: CI workflows

**Files:** Create `.github/workflows/e-py.yml`, `.github/workflows/e-rs.yml`, `.github/workflows/release-e-rs.yml`

- [ ] **Step 1: Create `.github/workflows/e-py.yml`**

```yaml
name: e.py

on:
  pull_request:
    branches:
      - master

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  test:
    name: Test e.py
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: e
    steps:
      - uses: actions/checkout@v5

      - name: Install GMP and MPFR
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev libmpfr-dev

      - name: Install Python dependencies
        run: pip install mpmath gmpy2 coverage ruff

      - name: Run tests
        run: make test
```

- [ ] **Step 2: Create `.github/workflows/e-rs.yml`**

```yaml
name: e-rs

on:
  pull_request:
    branches:
      - master

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  test:
    name: Test e-rs
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: e/e-rs
    steps:
      - uses: actions/checkout@v5

      - name: Install GMP and MPFR
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev libmpfr-dev

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: e/e-rs

      - name: Run tests
        run: make test

  build:
    name: Build e-rs
    runs-on: ubuntu-latest
    needs: [test]
    defaults:
      run:
        working-directory: e/e-rs
    steps:
      - uses: actions/checkout@v5

      - name: Install GMP and MPFR
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev libmpfr-dev

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: e/e-rs

      - name: Build
        run: cargo build --release

      - name: Upload artifact
        uses: actions/upload-artifact@v7
        with:
          name: e
          path: e/e-rs/target/release/e
          retention-days: 7
```

- [ ] **Step 3: Create `.github/workflows/release-e-rs.yml`**

Follow the same pattern as `release-pi-rs.yml`:

- `workflow_dispatch` with `version` input
- Test → build → generate release notes → create tag → create GitHub release
- Replace `pi` with `e` in all names, paths, and tag prefixes (`e-v`)
- Use `env: VERSION:` pattern for inputs in shell, not direct interpolation
- Use randomized `GITHUB_OUTPUT` delimiter

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/e-py.yml .github/workflows/e-rs.yml .github/workflows/release-e-rs.yml
git commit -m "ci: add e.py, e-rs, and release-e-rs workflows"
```

---

## Task 11: Update `scripts/pre-commit` and `scripts/pre-push`

**Files:** Modify `scripts/pre-commit`, Modify `scripts/pre-push`

- [ ] **Step 1: Update `scripts/pre-commit`**

Add `e` and `e/e-rs` to the lint loop directory list:

```bash
for dir in pi pi/pi-rs prime/prime-rs fib fib/fib-rs sq sq/sq-rs twin-primes/twin-primes-rs e e/e-rs; do
```

- [ ] **Step 2: Update `scripts/pre-push`**

Add `e` and `e/e-rs` to the test loop directory list:

```bash
for dir in pi pi/pi-rs prime/prime-rs fib fib/fib-rs sq sq/sq-rs twin-primes/twin-primes-rs e e/e-rs; do
```

- [ ] **Step 3: Commit**

```bash
git add scripts/pre-commit scripts/pre-push
git commit -m "chore: add e and e/e-rs to pre-commit and pre-push hooks"
```

---

## Task 12: Update top-level `CLAUDE.md` and `README.md`

**Files:** Modify `CLAUDE.md`, Modify `README.md`

- [ ] **Step 1: Update `CLAUDE.md` — Repository Overview table**

Add row after `sq/`:

```markdown
| [`e/`](e/) | Python + Rust | Calculate e to N decimal places (Taylor series) | [`e/CLAUDE.md`](e/CLAUDE.md) |
```

- [ ] **Step 2: Update `CLAUDE.md` — Dependency Installation table**

Add rows:

```markdown
| `e/install_deps.sh` | GMP + MPFR, `mpmath`, `gmpy2`, `ruff`, `coverage` |
| `e/e-rs/install_deps.sh` | GMP + MPFR, Rust toolchain, `cargo-tarpaulin` |
```

- [ ] **Step 3: Update `CLAUDE.md` — Quick Reference section**

Add two new blocks after `twin-primes/twin-primes-rs/`:

````markdown
### Python (`e/`)

```bash
cd e
make run       # python3 e.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_e -v
make coverage  # coverage run + report
```

### Rust (`e/e-rs/`)

```bash
cd e/e-rs
make e         # cargo build --release
make lint      # cargo clippy -- -D warnings
make test      # lint, then cargo test
```
````

- [ ] **Step 4: Update `CLAUDE.md` — CI table**

Add three rows and update the workflow count:

```markdown
| e.py | `.github/workflows/e-py.yml` | test |
| e-rs | `.github/workflows/e-rs.yml` | test → build + artifact |
| release-e-rs | `.github/workflows/release-e-rs.yml` | release (manual dispatch) |
```

Update "Fourteen workflow files" to "Seventeen workflow files".

- [ ] **Step 5: Update `README.md` — badges**

Add two badges after `twin-primes-rs` badge:

```markdown
[![e.py](https://github.com/brujack/math/actions/workflows/e-py.yml/badge.svg?event=pull_request)](https://github.com/brujack/math/actions/workflows/e-py.yml)
[![e-rs](https://github.com/brujack/math/actions/workflows/e-rs.yml/badge.svg?event=pull_request)](https://github.com/brujack/math/actions/workflows/e-rs.yml)
```

- [ ] **Step 6: Update `README.md` — project table**

Add row after `twin-primes`:

```markdown
| [`e/`](e/README.md) | Calculate e to N decimal places (Taylor series) | Python + Rust | [![e.py](https://github.com/brujack/math/actions/workflows/e-py.yml/badge.svg?event=pull_request)](https://github.com/brujack/math/actions/workflows/e-py.yml) [![e-rs](https://github.com/brujack/math/actions/workflows/e-rs.yml/badge.svg?event=pull_request)](https://github.com/brujack/math/actions/workflows/e-rs.yml) |
```

- [ ] **Step 7: Update `README.md` — add e section**

Add after the twin-primes section:

```markdown
---

## e

Calculates Euler's number _e_ to an arbitrary number of decimal places using the **Taylor series** with binary splitting.

- Python implementation (`e/e.py`) — gmpy2/GMP fast path with mpmath fallback
- Rust implementation (`e/e-rs/`) — shared-memory rayon parallelism with zero IPC overhead

See [`e/README.md`](e/README.md) for full details.
```

- [ ] **Step 8: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: add e/ to top-level CLAUDE.md and README.md"
```

---

## Task 13: Update `docs/superpowers/README.md`

**Files:** Modify `docs/superpowers/README.md`

- [ ] **Step 1: Move e from backlog to All Plans table**

Add row to All Plans:

```markdown
| 2026-04-23 | [euler-number](plans/2026-04-23-euler-number.md) | [spec](specs/2026-04-23-euler-number-design.md) | In Progress |
```

Remove the `e (Euler's number)` row from the Backlog table.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/README.md
git commit -m "docs: move e from backlog to All Plans table"
```

---

## Task 14: Local testing and PR

- [ ] **Step 1: Run all Python tests**

```bash
cd e && make test
```

Expected: all tests pass

- [ ] **Step 2: Run all Rust tests**

```bash
cd e/e-rs && make test
```

Expected: all tests pass, clippy clean

- [ ] **Step 3: Run pr-review skill**

Invoke `pr-review` to validate the branch before pushing. Only push when verdict is PASS.

- [ ] **Step 4: Push branch**

```bash
git push -u origin feat/euler-number
```

- [ ] **Step 5: Open PR**

```bash
gh pr create \
  --title "feat: add Euler's number (e) calculator (Python + Rust)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `e/` project with Python and Rust implementations
- Taylor series with binary splitting, parallelized across CPU cores
- Python: gmpy2/GMP fast path with mpmath fallback, parallel pwrite file I/O
- Rust: rug/GMP + rayon shared-memory threads, parallel pwrite
- Full CI: test, build+artifact, release workflows
- Pre-commit and pre-push hooks updated

## Test plan
- [ ] `cd e && make test` passes (all Python tests)
- [ ] `cd e/e-rs && make test` passes (all Rust tests)
- [ ] CI workflows appear in GitHub Actions on PR
- [ ] Output matches known e digits for 10, 20, 50 decimal places

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Monitor CI until PR resolves**

```bash
gh pr checks <number> --watch
```

If any check fails, read the failure, fix, commit, push. Once all checks pass and the PR auto-merges, delete the branch:

```bash
git branch -d feat/euler-number
git push origin --delete feat/euler-number
```
