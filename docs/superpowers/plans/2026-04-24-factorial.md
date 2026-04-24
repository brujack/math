# Factorial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `factorial/` project that computes N! to arbitrary precision using the prime swing algorithm (Python + Rust).

**Architecture:** Prime swing with recursive squaring: `n! = swing(n) × (⌊n/2⌋!)²`. Swing computed by iterating primes ≤ n and applying Legendre's formula bit-counting loop. Python uses gmpy2 + ProcessPoolExecutor; Rust uses rug + Rayon. Both always save output to `factorial_<N>.txt`.

**Tech Stack:** Python 3 + gmpy2/GMP + mpmath fallback; Rust + rug (GMP) + rayon + clap

---

## File Structure

| File                                         | Action | Purpose                                              |
| -------------------------------------------- | ------ | ---------------------------------------------------- |
| `docs/adr/0007-prime-swing-factorial.md`     | Create | ADR for algorithm choice                             |
| `docs/adr/README.md`                         | Modify | Add ADR-0007 row                                     |
| `factorial/factorial.py`                     | Create | Python CLI — prime swing via gmpy2                   |
| `factorial/test_factorial.py`                | Create | Python unit tests                                    |
| `factorial/install_deps.sh`                  | Create | Install GMP, gmpy2, mpmath, ruff, coverage           |
| `factorial/Makefile`                         | Create | run, lint, test, coverage, clean                     |
| `factorial/CLAUDE.md`                        | Create | Project guidance                                     |
| `factorial/factorial-rs/src/main.rs`         | Create | Rust CLI — prime swing via rug + Rayon               |
| `factorial/factorial-rs/Cargo.toml`          | Create | Rust package manifest                                |
| `factorial/factorial-rs/install_deps.sh`     | Create | Install GMP, Rust toolchain, cargo-tarpaulin         |
| `factorial/factorial-rs/Makefile`            | Create | factorial, lint, test, clean                         |
| `factorial/factorial-rs/CLAUDE.md`           | Create | Rust project guidance                                |
| `.github/workflows/factorial-py.yml`         | Create | CI: Python test job                                  |
| `.github/workflows/factorial-rs.yml`         | Create | CI: Rust test + build + artifact                     |
| `.github/workflows/release-factorial-rs.yml` | Create | CI: manual release dispatch                          |
| `scripts/pre-commit`                         | Modify | Add factorial and factorial/factorial-rs to dir loop |
| `scripts/pre-push`                           | Modify | Add factorial and factorial/factorial-rs to dir loop |
| `.gitignore`                                 | Modify | Add `factorial_*.txt`                                |
| `README.md`                                  | Modify | Add badges, project table row, section               |
| `CLAUDE.md`                                  | Modify | Repository Overview, CI table, Quick Reference       |
| `docs/superpowers/README.md`                 | Modify | Add factorial row, remove from backlog               |

---

## Task 1: ADR for prime swing algorithm

**Files:**

- Create: `docs/adr/0007-prime-swing-factorial.md`
- Modify: `docs/adr/README.md`

- [ ] **Step 1: Create ADR-0007**

Create `docs/adr/0007-prime-swing-factorial.md`:

```markdown
# ADR-0007: Prime Swing Algorithm for Factorial

**Date:** 2026-04-24
**Status:** Accepted

## Context

N! grows extremely fast — 10^6! has ~5.5 million digits. A naive sequential
multiplication requires O(N) big-integer multiplies, each more expensive than
the last as the result grows. Faster algorithms exploit the prime factorisation
of N! directly.

Candidates considered:

- **Naive multiplication**: O(N · M(D)) where M(D) is the cost of multiplying
  two D-digit numbers. Too slow for large N.
- **Divide-and-conquer binary splitting**: O(M(D) · log²N). Parallelisable,
  but requires careful management of the partial product tree.
- **Prime swing (Luschny)**: Decomposes N! into `n! = swing(n) × (⌊n/2⌋!)²`
  where `swing(n)` is computed directly from the prime sieve. Theoretically
  optimal for large N; all swing values at each recursion level are independent.

## Decision

Use the **prime swing algorithm** for both Python and Rust implementations.

The key identity: `swing(m) = ∏ p^e_p` where `e_p = Σ_{j≥1} (⌊m/pʲ⌋ mod 2)`.
This allows swing(m) to be computed in a single pass over the prime sieve with
no floating-point arithmetic. The recursion `n! = swing(n) × (⌊n/2⌋!)²`
naturally parallelises — all swing computations at each level are independent.

## Consequences

- Faster than divide-and-conquer for large N due to fewer large-integer
  multiplications.
- Requires a prime sieve up to N — O(N) space, precomputed once.
- More complex to implement than naive multiplication; the bit-counting loop
  for `e_p` is non-obvious.
- Both Python and Rust implementations share the same algorithm, so correctness
  can be cross-validated.

## Related

- [ADR-0002: Python + Rust dual implementation](0002-python-rust-dual-implementation.md)
- [ADR-0003: Parallel segmented sieve](0003-parallel-segmented-sieve-for-primes.md)
- [ADR-0005: rayon for shared-memory parallelism](0005-rayon-for-shared-memory-parallelism.md)
```

- [ ] **Step 2: Add row to `docs/adr/README.md`**

Add after the last row (0006):

```markdown
| [0007](0007-prime-swing-factorial.md) | Prime swing algorithm for factorial | 2026-04-24 | Accepted |
```

- [ ] **Step 3: Commit**

```bash
git add docs/adr/0007-prime-swing-factorial.md docs/adr/README.md
git commit -m "docs: add ADR-0007 for prime swing factorial algorithm

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Python scaffold

**Files:**

- Create: `factorial/install_deps.sh`
- Create: `factorial/Makefile`

- [ ] **Step 1: Create `factorial/install_deps.sh`**

```bash
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
    Darwin)  install_macos ;;
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
python3 -m pip install --upgrade mpmath gmpy2 coverage ruff

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
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x factorial/install_deps.sh
```

- [ ] **Step 3: Create `factorial/Makefile`**

```makefile
.PHONY: run lint test coverage clean

run:
	python3 factorial.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_factorial -v

coverage:
	python3 -m coverage run -m unittest test_factorial
	python3 -m coverage report

clean:
	rm -rf __pycache__ .coverage
```

- [ ] **Step 4: Commit**

```bash
git add factorial/install_deps.sh factorial/Makefile
git commit -m "chore: add factorial Python project scaffold

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Python — `_sieve` (TDD)

**Files:**

- Create: `factorial/factorial.py` (skeleton + `_sieve`)
- Create: `factorial/test_factorial.py` (TestSieve)

- [ ] **Step 1: Create `factorial/test_factorial.py` with TestSieve**

```python
#!/usr/bin/env python3
"""Unit tests for factorial.py."""

import io
import os
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))

import factorial as fac_module
from factorial import (
    _HAS_GMPY2,
    _sieve,
    _compute_swing_chunk,
    _tree_combine_int,
    calculate_factorial,
    get_target_n,
    parse_args,
)

# Known exact factorial values for testing.
FACTORIAL_REF = {
    0: 1, 1: 1, 2: 2, 3: 6, 4: 24,
    5: 120, 10: 3628800, 20: 2432902008176640000,
}


def _quiet_factorial(n):
    """Compute factorial while suppressing stdout."""
    with redirect_stdout(io.StringIO()):
        return calculate_factorial(n)


class TestSieve(unittest.TestCase):

    def test_empty_below_2(self):
        self.assertEqual(_sieve(0), [])
        self.assertEqual(_sieve(1), [])

    def test_n_equals_2(self):
        self.assertEqual(_sieve(2), [2])

    def test_small_known_primes(self):
        self.assertEqual(_sieve(10), [2, 3, 5, 7])

    def test_no_composites(self):
        result = _sieve(20)
        for p in result:
            for d in range(2, p):
                self.assertNotEqual(p % d, 0, f"{p} is not prime")

    def test_prime_count_to_100(self):
        # π(100) = 25
        self.assertEqual(len(_sieve(100)), 25)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd factorial && python3 -m unittest test_factorial.TestSieve -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` or `ImportError` (factorial.py does not exist yet).

- [ ] **Step 3: Create `factorial/factorial.py` with `_sieve`**

```python
#!/usr/bin/env python3
"""
Compute N! (N factorial) to arbitrary precision using the prime swing algorithm.

Algorithm: n! = swing(n) × (floor(n/2)!)²  (Luschny prime swing)
  swing(m) = ∏ p^e_p  where e_p = Σ_{j≥1} (floor(m/p^j) mod 2)

Uses gmpy2/GMP for fast arbitrary-precision arithmetic.
Falls back to mpmath.factorial if gmpy2 is not installed.

Install fast backend (recommended):
    bash install_deps.sh
"""

import argparse
import bisect
import concurrent.futures
import multiprocessing
import os
import sys
import time

try:
    import gmpy2 as _gmpy2
    _HAS_GMPY2 = True
except ImportError:
    _gmpy2 = None
    _HAS_GMPY2 = False

_CPU_COUNT = os.cpu_count() or 1


# ---------------------------------------------------------------------------
# Sieve of Eratosthenes
# ---------------------------------------------------------------------------

def _sieve(n):
    """Return sorted list of all primes <= n."""
    if n < 2:
        return []
    composite = bytearray(n + 1)  # 0 = prime, 1 = composite
    composite[0] = 1
    composite[1] = 1
    i = 2
    while i * i <= n:
        if not composite[i]:
            j = i * i
            while j <= n:
                composite[j] = 1
                j += i
        i += 1
    return [p for p in range(2, n + 1) if not composite[p]]
```

- [ ] **Step 4: Run TestSieve to confirm it passes**

```bash
cd factorial && python3 -m unittest test_factorial.TestSieve -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add factorial/factorial.py factorial/test_factorial.py
git commit -m "feat: add _sieve to factorial.py with TestSieve

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Python — `_compute_swing_chunk` and `_tree_combine_int` (TDD)

**Files:**

- Modify: `factorial/factorial.py`
- Modify: `factorial/test_factorial.py`

- [ ] **Step 1: Add TestComputeSwingChunk and TestTreeCombineInt to test file**

Add after `TestSieve`:

```python
class TestComputeSwingChunk(unittest.TestCase):

    def test_empty_prime_chunk(self):
        self.assertEqual(_compute_swing_chunk(10, []), 1)

    def test_prime_greater_than_m_returns_1(self):
        # p=7 > m=5, so no contribution
        self.assertEqual(_compute_swing_chunk(5, [7, 11]), 1)

    def test_swing_of_2_via_chunk(self):
        # p=2, m=2: q=2//2=1, 1%2=1, exp=1 → 2^1=2
        self.assertEqual(_compute_swing_chunk(2, [2]), 2)

    def test_swing_of_4_p2_contribution(self):
        # p=2, m=4: q=4//2=2, 2%2=0; q=2//2=1, 1%2=1 → exp=1 → 2^1=2
        self.assertEqual(_compute_swing_chunk(4, [2]), 2)

    def test_swing_of_6_p2_contribution(self):
        # p=2, m=6: q=6//2=3, 3%2=1, exp++; q=3//2=1, 1%2=1, exp++ → exp=2 → 2^2=4
        self.assertEqual(_compute_swing_chunk(6, [2]), 4)

    def test_swing_of_6_p3_contribution(self):
        # p=3, m=6: q=6//3=2, 2%2=0; q=2//3=0, done → exp=0 → no contribution
        self.assertEqual(_compute_swing_chunk(6, [3]), 1)

    def test_swing_of_6_p5_contribution(self):
        # p=5, m=6: q=6//5=1, 1%2=1 → exp=1 → 5^1=5
        self.assertEqual(_compute_swing_chunk(6, [5]), 5)


class TestTreeCombineInt(unittest.TestCase):

    def test_empty_returns_1(self):
        self.assertEqual(_tree_combine_int([]), 1)

    def test_single_element(self):
        self.assertEqual(_tree_combine_int([42]), 42)

    def test_two_elements(self):
        self.assertEqual(_tree_combine_int([3, 7]), 21)

    def test_four_elements_tree_order(self):
        # (2*3) * (5*7) = 6 * 35 = 210
        self.assertEqual(_tree_combine_int([2, 3, 5, 7]), 210)

    def test_odd_length(self):
        # (2*3) * 5 = 30
        self.assertEqual(_tree_combine_int([2, 3, 5]), 30)
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
cd factorial && python3 -m unittest test_factorial.TestComputeSwingChunk test_factorial.TestTreeCombineInt -v 2>&1 | head -20
```

Expected: `ImportError` for `_compute_swing_chunk` and `_tree_combine_int` (not defined yet).

- [ ] **Step 3: Add `_compute_swing_chunk` and `_tree_combine_int` to `factorial.py`**

Add after `_sieve`:

```python
# ---------------------------------------------------------------------------
# Swing chunk worker — must be at module level for multiprocessing pickling
# ---------------------------------------------------------------------------

def _compute_swing_chunk(m, prime_chunk):
    """
    Compute product of p^e_p for each prime in prime_chunk, for swing(m).

    e_p = number of odd values in {floor(m/p), floor(m/p^2), ...}
    Returns a plain Python int (always picklable).
    """
    result = 1
    for p in prime_chunk:
        if p > m:
            break
        exp = 0
        q = m
        while q >= p:
            q //= p
            if q & 1:
                exp += 1
        if exp:
            result *= p ** exp
    return result


# ---------------------------------------------------------------------------
# Tree reduction
# ---------------------------------------------------------------------------

def _tree_combine_int(values):
    """
    Pairwise tree reduction of a list of integers (plain int or gmpy2.mpz).
    Returns 1 for an empty list.
    Balanced tree keeps GMP multiply sizes similar at each level.
    """
    if not values:
        return 1
    while len(values) > 1:
        next_level = []
        for i in range(0, len(values), 2):
            if i + 1 < len(values):
                next_level.append(values[i] * values[i + 1])
            else:
                next_level.append(values[i])
        values = next_level
    return values[0]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd factorial && python3 -m unittest test_factorial.TestComputeSwingChunk test_factorial.TestTreeCombineInt -v
```

Expected: 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add factorial/factorial.py factorial/test_factorial.py
git commit -m "feat: add _compute_swing_chunk and _tree_combine_int

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Python — `_compute_swing` (TDD)

**Files:**

- Modify: `factorial/factorial.py`
- Modify: `factorial/test_factorial.py`

- [ ] **Step 1: Add TestComputeSwing to test file**

Add after `TestTreeCombineInt`:

```python
class TestComputeSwing(unittest.TestCase):
    """Tests for _compute_swing. Requires gmpy2 for the fast path."""

    def _swing(self, m):
        """Compute swing(m) and return as plain int."""
        from factorial import _compute_swing
        primes = _sieve(m) if m >= 2 else []
        result = _compute_swing(m, primes)
        return int(result)

    def test_swing_zero(self):
        self.assertEqual(self._swing(0), 1)

    def test_swing_one(self):
        self.assertEqual(self._swing(1), 1)

    def test_swing_two(self):
        # Only prime <=2 is 2. e_2 = floor(2/2) mod 2 = 1. swing=2.
        self.assertEqual(self._swing(2), 2)

    def test_swing_four(self):
        # p=2: exp=1 (floor(4/2)=2 even; floor(4/4)=1 odd) → 2^1=2
        # p=3: exp=1 (floor(4/3)=1 odd) → 3^1=3
        # swing(4) = 2*3 = 6
        self.assertEqual(self._swing(4), 6)

    def test_swing_six(self):
        # p=2: exp=2 → 4; p=3: exp=0 → 1; p=5: exp=1 → 5
        # swing(6) = 4*5 = 20
        self.assertEqual(self._swing(6), 20)

    def test_swing_satisfies_factorial_recursion(self):
        # n! = swing(n) * (n//2)!^2  for n=6
        import math
        self.assertEqual(self._swing(6) * (math.factorial(3) ** 2), math.factorial(6))
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
cd factorial && python3 -m unittest test_factorial.TestComputeSwing -v 2>&1 | head -10
```

Expected: `ImportError` — `_compute_swing` not defined.

- [ ] **Step 3: Add `_compute_swing` to `factorial.py`**

Add after `_tree_combine_int`:

```python
# ---------------------------------------------------------------------------
# Parallel swing computation
# ---------------------------------------------------------------------------

def _compute_swing(m, primes):
    """
    Compute swing(m) = product(p^e_p for all primes p <= m).

    Parallelises over prime chunks using ProcessPoolExecutor.
    Returns gmpy2.mpz (fast path) or plain int (mpmath fallback).
    """
    if m < 2 or not primes:
        return _gmpy2.mpz(1) if _HAS_GMPY2 else 1

    # Only primes <= m contribute.
    bound = bisect.bisect_right(primes, m)
    relevant = primes[:bound]
    if not relevant:
        return _gmpy2.mpz(1) if _HAS_GMPY2 else 1

    chunk_size = max(1, (len(relevant) + _CPU_COUNT - 1) // _CPU_COUNT)
    chunks = [relevant[i:i + chunk_size] for i in range(0, len(relevant), chunk_size)]

    mp_context = multiprocessing.get_context(
        'fork' if sys.platform == 'linux' else 'spawn'
    )
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=len(chunks), mp_context=mp_context
    ) as pool:
        parts = list(pool.map(_compute_swing_chunk, [m] * len(chunks), chunks))

    if _HAS_GMPY2:
        return _tree_combine_int([_gmpy2.mpz(p) for p in parts])
    return _tree_combine_int(parts)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd factorial && python3 -m unittest test_factorial.TestComputeSwing -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add factorial/factorial.py factorial/test_factorial.py
git commit -m "feat: add _compute_swing with ProcessPoolExecutor parallelism

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Python — `calculate_factorial` (TDD)

**Files:**

- Modify: `factorial/factorial.py`
- Modify: `factorial/test_factorial.py`

- [ ] **Step 1: Add TestCalculateFactorial to test file**

Add after `TestComputeSwing`:

```python
class TestCalculateFactorial(unittest.TestCase):

    def test_zero(self):
        self.assertEqual(int(_quiet_factorial(0)), FACTORIAL_REF[0])

    def test_one(self):
        self.assertEqual(int(_quiet_factorial(1)), FACTORIAL_REF[1])

    def test_two(self):
        self.assertEqual(int(_quiet_factorial(2)), FACTORIAL_REF[2])

    def test_five(self):
        self.assertEqual(int(_quiet_factorial(5)), FACTORIAL_REF[5])

    def test_ten(self):
        self.assertEqual(int(_quiet_factorial(10)), FACTORIAL_REF[10])

    def test_twenty(self):
        self.assertEqual(int(_quiet_factorial(20)), FACTORIAL_REF[20])

    @unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
    def test_returns_mpz_with_gmpy2(self):
        import gmpy2
        result = _quiet_factorial(5)
        self.assertIsInstance(result, gmpy2.mpz)

    def test_digit_count_100(self):
        # 100! has 158 digits
        result = str(int(_quiet_factorial(100)))
        self.assertEqual(len(result), 158)
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
cd factorial && python3 -m unittest test_factorial.TestCalculateFactorial -v 2>&1 | head -10
```

Expected: `ImportError` — `calculate_factorial` not defined.

- [ ] **Step 3: Add `_factorial_rec` and `calculate_factorial` to `factorial.py`**

Add after `_compute_swing`:

```python
# ---------------------------------------------------------------------------
# Prime swing factorial (recursive squaring)
# ---------------------------------------------------------------------------

def _factorial_rec(n, primes):
    """
    Recursive prime swing: n! = swing(n) * (floor(n/2)!)^2

    Recursion depth is floor(log2(n)) ~ 20 for n=10^6, well within Python's limit.
    """
    if n <= 1:
        return _gmpy2.mpz(1) if _HAS_GMPY2 else 1
    half = _factorial_rec(n >> 1, primes)
    swing = _compute_swing(n, primes)
    return half * half * swing


def calculate_factorial(n):
    """
    Compute n! using the prime swing algorithm.

    Fast path: gmpy2/GMP with ProcessPoolExecutor parallelism.
    Fallback: mpmath.factorial (correct but slow for large n).

    Returns gmpy2.mpz (fast path) or int (fallback).
    """
    if n < 0:
        raise ValueError("n must be a non-negative integer")
    print(f"Calculating {n:,}! using prime swing...")
    print(f"Running on {_CPU_COUNT} CPU core{'s' if _CPU_COUNT != 1 else ''}...")

    if _HAS_GMPY2:
        print(
            f"Backend: prime swing / gmpy2 {_gmpy2.version()} "
            f"(GMP {_gmpy2.mp_version()})"
        )
        t0 = time.time()
        primes = _sieve(n)
        print(f"  Sieve: {len(primes):,} primes up to {n:,}")
        result = _factorial_rec(n, primes)
        print(f"Calculation completed in {time.time() - t0:.2f}s")
        return result

    # mpmath fallback
    try:
        import mpmath
    except ImportError as exc:
        raise RuntimeError("Neither gmpy2 nor mpmath is installed.") from exc
    print(
        f"Backend: mpmath {mpmath.__version__} "
        f"(install gmpy2 for faster computation — see install_deps.sh)"
    )
    t0 = time.time()
    result = int(mpmath.factorial(n))
    print(f"Calculation completed in {time.time() - t0:.2f}s")
    return result
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd factorial && python3 -m unittest test_factorial.TestCalculateFactorial -v
```

Expected: 8 tests pass.

- [ ] **Step 5: Run the full suite so far**

```bash
cd factorial && python3 -m unittest test_factorial -v
```

Expected: all tests pass (no regressions).

- [ ] **Step 6: Commit**

```bash
git add factorial/factorial.py factorial/test_factorial.py
git commit -m "feat: add _factorial_rec and calculate_factorial (prime swing)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Python — CLI, file output, and `main` (TDD)

**Files:**

- Modify: `factorial/factorial.py`
- Modify: `factorial/test_factorial.py`

- [ ] **Step 1: Add CLI and file output tests**

Add after `TestCalculateFactorial`:

```python
class TestMpmathFallback(unittest.TestCase):
    """Test the mpmath fallback path via monkeypatching."""

    def test_fallback_produces_correct_result(self):
        with unittest.mock.patch.object(fac_module, '_HAS_GMPY2', False):
            result = _quiet_factorial(5)
            self.assertEqual(int(result), 120)

    def test_fallback_returns_int(self):
        with unittest.mock.patch.object(fac_module, '_HAS_GMPY2', False):
            result = _quiet_factorial(3)
            self.assertIsInstance(result, int)


class TestParseArgs(unittest.TestCase):

    def test_no_args_gives_none(self):
        args = parse_args([])
        self.assertIsNone(args.n)

    def test_positional_arg_parsed(self):
        args = parse_args(['42'])
        self.assertEqual(args.n, 42)

    def test_help_exits(self):
        with self.assertRaises(SystemExit):
            parse_args(['--help'])


class TestGetTargetN(unittest.TestCase):

    def test_cli_arg_returned_directly(self):
        args = parse_args(['100'])
        self.assertEqual(get_target_n(args), 100)

    def test_zero_raises(self):
        args = parse_args(['0'])
        with self.assertRaises(ValueError):
            get_target_n(args)

    def test_negative_raises(self):
        args = parse_args(['-5'])
        with self.assertRaises(SystemExit):  # argparse rejects negative int
            parse_args(['-5'])

    def test_interactive_valid_input(self):
        args = parse_args([])
        with unittest.mock.patch('builtins.input', return_value='7'):
            self.assertEqual(get_target_n(args), 7)

    def test_interactive_non_integer_retries(self):
        args = parse_args([])
        with unittest.mock.patch('builtins.input', side_effect=['abc', '5']):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(get_target_n(args), 5)


class TestOutputFile(unittest.TestCase):

    def test_file_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fname = os.path.join(tmpdir, 'factorial_5.txt')
            result = _quiet_factorial(5)
            _write_factorial_file(result, 5, fname)
            self.assertTrue(os.path.exists(fname))

    def test_filename_convention(self):
        # filename should encode N
        with tempfile.TemporaryDirectory() as tmpdir:
            fname = os.path.join(tmpdir, 'factorial_10.txt')
            result = _quiet_factorial(10)
            _write_factorial_file(result, 10, fname)
            self.assertIn('factorial_10', fname)

    def test_content_is_correct_digits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fname = os.path.join(tmpdir, 'out.txt')
            result = _quiet_factorial(5)
            _write_factorial_file(result, 5, fname)
            content = open(fname).read()
            self.assertIn('120', content)

    def test_idempotent_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fname = os.path.join(tmpdir, 'out.txt')
            result = _quiet_factorial(5)
            _write_factorial_file(result, 5, fname)
            _write_factorial_file(result, 5, fname)
            content = open(fname).read()
            self.assertEqual(content.count('120'), 1)
```

Also add `_write_factorial_file` to the imports at the top of the test file:

```python
from factorial import (
    _HAS_GMPY2,
    _sieve,
    _compute_swing_chunk,
    _tree_combine_int,
    _write_factorial_file,
    calculate_factorial,
    get_target_n,
    parse_args,
)
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
cd factorial && python3 -m unittest test_factorial.TestParseArgs test_factorial.TestGetTargetN test_factorial.TestOutputFile -v 2>&1 | head -15
```

Expected: `ImportError` — `_write_factorial_file`, `get_target_n`, `parse_args` not defined.

- [ ] **Step 3: Add CLI and file output functions to `factorial.py`**

Add at the end of the file (before `if __name__ == "__main__"`):

```python
# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------

def _write_factorial_file(result, n, filename):
    """
    Write n! to filename.

    File format:
        n! computed using prime swing
        ============================================================

        <digits>

        Total digits: <count>
    """
    digits_str = str(int(result))
    digit_count = len(digits_str)
    header = (
        f"{n:,}! computed using prime swing\n"
        + "=" * 60 + "\n\n"
    )
    footer = f"\n\nTotal digits: {digit_count:,}"
    with open(filename, 'w') as fh:
        fh.write(header)
        fh.write(digits_str)
        fh.write(footer)
    print(f"Saved to {filename} ({digit_count:,} digits)")


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Compute N! (N factorial) to arbitrary precision.",
        epilog=(
            "Run without arguments to use the interactive prompt, or provide "
            "N directly."
        ),
    )
    parser.add_argument(
        "n",
        nargs="?",
        type=int,
        help="N — compute N!",
    )
    return parser.parse_args(argv)


def get_target_n(args):
    """Return N from CLI args or interactive input. Raises ValueError for N < 1."""
    if args.n is not None:
        if args.n < 1:
            raise ValueError("N must be a positive integer.")
        return args.n

    while True:
        try:
            raw = input("Enter N to compute N!: ")
            n = int(raw)
            if n < 1:
                print("Please enter a positive integer.")
                continue
            return n
        except ValueError:
            print("Please enter a valid integer.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Main entry point."""
    try:
        args = parse_args()

        print("High-Precision Factorial Calculator")
        print("=" * 40)

        n = get_target_n(args)
        t_start = time.time()
        result = calculate_factorial(n)
        elapsed = time.time() - t_start

        digit_count = len(str(int(result)))
        print(f"\n{n:,}! has {digit_count:,} digits")
        print(f"Total time: {elapsed:.2f}s")

        filename = f"factorial_{n}.txt"
        _write_factorial_file(result, n, filename)

    except KeyboardInterrupt:
        print("\n\nInterrupted.")
        sys.exit(1)
    except ValueError as exc:
        print(f"\nError: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\nError: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    if multiprocessing.current_process().name == "MainProcess":
        main()
```

- [ ] **Step 4: Run the full test suite**

```bash
cd factorial && python3 -m unittest test_factorial -v
```

Expected: all tests pass.

- [ ] **Step 5: Run `make lint`**

```bash
cd factorial && make lint
```

Expected: no ruff errors.

- [ ] **Step 6: Run `make test`**

```bash
cd factorial && make test
```

Expected: lint passes, all tests pass.

- [ ] **Step 7: Commit**

```bash
git add factorial/factorial.py factorial/test_factorial.py
git commit -m "feat: add CLI, file output, and main for factorial.py

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Python CLAUDE.md

**Files:**

- Create: `factorial/CLAUDE.md`

- [ ] **Step 1: Create `factorial/CLAUDE.md`**

````markdown
# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

Python CLI that computes N! to arbitrary precision using the prime swing algorithm.
Always saves output to `factorial_<N>.txt`.

Current structure:

- `factorial.py`: interactive calculator (Python, gmpy2/GMP + mpmath fallback)
- `factorial-rs/`: Rust implementation — prime swing + Rayon + rug/GMP
- `install_deps.sh`: installs GMP, gmpy2, mpmath, ruff, coverage
- `test_factorial.py`: unit tests

## Algorithm

Prime swing (Luschny): `n! = swing(n) × (⌊n/2⌋!)²`

`swing(m) = ∏ p^e_p` where `e_p = Σ_{j≥1} (⌊m/pʲ⌋ mod 2)` (count odd terms in
the Legendre sequence for prime p and value m).

The recursion depth is `⌊log₂(n)⌋` — about 20 for n=10^6. Python targets n up
to ~10^7; use `factorial-rs` for larger n.

## Code Layout

Module-level constants:

- `_HAS_GMPY2`: True if gmpy2 imported successfully
- `_CPU_COUNT`: `os.cpu_count()`

Sieve:

- `_sieve(n)`: Sieve of Eratosthenes returning `list[int]` of primes up to n

Swing computation (module-level for pickling):

- `_compute_swing_chunk(m, prime_chunk)`: subprocess worker; returns plain `int`
- `_tree_combine_int(values)`: pairwise tree reduction of int/mpz list
- `_compute_swing(m, primes)`: splits prime range into chunks, dispatches to
  ProcessPoolExecutor, tree-combines results

Factorial:

- `_factorial_rec(n, primes)`: recursive prime swing; returns gmpy2.mpz or int
- `calculate_factorial(n)`: sieves primes, calls `_factorial_rec`, prints progress

File output:

- `_write_factorial_file(result, n, filename)`: writes header + digits + footer

CLI:

- `parse_args(argv)`: argparse, optional positional `n`
- `get_target_n(args)`: returns n from CLI arg or interactive prompt
- `main()`: orchestrates parse → compute → save

## Running

```bash
make run       # python3 factorial.py (interactive)
make lint      # ruff check .
make test      # lint + python3 -m unittest test_factorial -v
make coverage  # coverage run + report
make clean     # remove __pycache__, .coverage
```
````

## Testing

TDD required. Tests in `test_factorial.py`.

```bash
make test
make coverage
```

Known reference values: `FACTORIAL_REF = {0:1, 1:1, 2:2, 5:120, 10:3628800, 20:2432902008176640000}`

gmpy2-dependent tests use `@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")`.
Use `_quiet_factorial(n)` to suppress stdout in tests.

## Keeping This File Up To Date

Update when: new or renamed function/constant, Makefile target change, dependency
added, test coverage changes, behavior or algorithm change. Also update top-level
`CLAUDE.md` for repo-level changes.

````

- [ ] **Step 2: Commit**

```bash
git add factorial/CLAUDE.md
git commit -m "docs: add factorial/CLAUDE.md

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
````

---

## Task 9: Rust scaffold

**Files:**

- Create: `factorial/factorial-rs/Cargo.toml`
- Create: `factorial/factorial-rs/Makefile`
- Create: `factorial/factorial-rs/install_deps.sh`
- Create: `factorial/factorial-rs/src/main.rs` (skeleton)

- [ ] **Step 1: Create `factorial/factorial-rs/Cargo.toml`**

```toml
[package]
name = "factorial"
version = "0.1.0"
edition = "2021"
description = "High-precision factorial — prime swing + Rayon + GMP"

[[bin]]
name = "factorial"
path = "src/main.rs"

[dependencies]
rug = { version = "1", features = ["integer"] }
rayon = "1"
clap = { version = "4", features = ["derive"] }

[profile.release]
opt-level   = 3
lto         = "thin"
codegen-units = 1
```

- [ ] **Step 2: Create `factorial/factorial-rs/Makefile`**

```makefile
.PHONY: factorial lint test clean

factorial:
	cargo build --release

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
```

- [ ] **Step 3: Create `factorial/factorial-rs/install_deps.sh`**

```bash
#!/usr/bin/env bash
# install_deps.sh — install dependencies for factorial-rs
#
# Installs: GMP + MPFR (required by rug), Rust toolchain, cargo-tarpaulin

set -euo pipefail

OS="$(uname -s)"

install_macos() {
    echo "==> Detected macOS"
    if ! command -v brew >/dev/null 2>&1; then
        echo "Error: Homebrew required." >&2; exit 1
    fi
    brew install gmp mpfr
}

install_debian() {
    echo "==> Detected Debian/Ubuntu"
    sudo apt-get update -qq
    sudo apt-get install -y libgmp-dev libmpfr-dev libmpc-dev
}

install_rhel() {
    echo "==> Detected RHEL/Fedora"
    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y gmp-devel mpfr-devel libmpc-devel
    else
        sudo yum install -y gmp-devel mpfr-devel libmpc-devel
    fi
}

case "$OS" in
    Darwin) install_macos ;;
    Linux)
        if [ -f /etc/debian_version ]; then install_debian
        elif [ -f /etc/redhat-release ] || [ -f /etc/fedora-release ]; then install_rhel
        else echo "Warning: unknown Linux distro" >&2; exit 1
        fi ;;
    *) echo "Error: unsupported OS '$OS'" >&2; exit 1 ;;
esac

if ! command -v rustup >/dev/null 2>&1; then
    echo "==> Installing Rust toolchain..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi

echo "==> Installing cargo-tarpaulin..."
cargo install cargo-tarpaulin

echo ""
echo "All dependencies installed."
echo "  make factorial  — build release binary"
echo "  make test       — run tests"
```

- [ ] **Step 4: Make it executable**

```bash
chmod +x factorial/factorial-rs/install_deps.sh
```

- [ ] **Step 5: Create skeleton `factorial/factorial-rs/src/main.rs`**

```rust
/*!
Compute N! (N factorial) to arbitrary precision using the prime swing algorithm.

Algorithm: n! = swing(n) × (floor(n/2)!)²  (Luschny prime swing)
  swing(m) = ∏ p^e_p  where e_p = Σ_{j≥1} (floor(m/p^j) mod 2)

Build (requires GMP; run install_deps.sh first):
    cargo build --release
    ./target/release/factorial [N]
*/

fn main() {
    println!("factorial-rs: not yet implemented");
}

#[cfg(test)]
mod tests {
    #[test]
    fn placeholder() {
        assert_eq!(1 + 1, 2);
    }
}
```

- [ ] **Step 6: Verify it builds**

```bash
cd factorial/factorial-rs && cargo build 2>&1 | tail -5
```

Expected: `Compiling factorial ...` then `Finished`.

- [ ] **Step 7: Commit**

```bash
git add factorial/factorial-rs/
git commit -m "chore: add factorial-rs Rust scaffold

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Rust — `sieve` (TDD)

**Files:**

- Modify: `factorial/factorial-rs/src/main.rs`

- [ ] **Step 1: Add sieve tests to `src/main.rs`**

Replace the `#[cfg(test)]` block:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    // --- sieve ---

    #[test]
    fn test_sieve_below_2_empty() {
        assert_eq!(sieve(0), Vec::<u32>::new());
        assert_eq!(sieve(1), Vec::<u32>::new());
    }

    #[test]
    fn test_sieve_n_equals_2() {
        assert_eq!(sieve(2), vec![2u32]);
    }

    #[test]
    fn test_sieve_to_10() {
        assert_eq!(sieve(10), vec![2u32, 3, 5, 7]);
    }

    #[test]
    fn test_sieve_no_composites() {
        let primes = sieve(50);
        for &p in &primes {
            for d in 2..p {
                assert_ne!(p % d, 0, "{p} should be prime");
            }
        }
    }

    #[test]
    fn test_sieve_count_to_100() {
        // π(100) = 25
        assert_eq!(sieve(100).len(), 25);
    }
}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd factorial/factorial-rs && cargo test 2>&1 | grep -E "FAILED|error"
```

Expected: compiler error — `sieve` not defined.

- [ ] **Step 3: Implement `sieve` in `src/main.rs`**

Add before `fn main()`:

```rust
use rug::Integer;
use rayon::prelude::*;
use clap::Parser;
use std::io::{self, BufRead, BufWriter, Write};
use std::fs::File;
use std::time::Instant;

/// Return all primes ≤ n as Vec<u32>.
/// Uses a bit-packed odd sieve: 1 bit per odd number ≥ 3.
/// Memory: n/16 bytes (e.g. 62.5 MB for n = 10^9).
fn sieve(n: u64) -> Vec<u32> {
    if n < 2 {
        return vec![];
    }
    if n == 2 {
        return vec![2];
    }
    // Bit array covering odd numbers 3, 5, 7, ..., up to n.
    // Index i represents odd number 2*i + 3.
    let max_odd_idx = ((n - 3) / 2) as usize;
    let byte_len = (max_odd_idx / 8) + 1;
    let mut composite = vec![0u8; byte_len];

    let mark = |c: &mut Vec<u8>, i: usize| {
        c[i >> 3] |= 1 << (i & 7);
    };
    let is_composite = |c: &Vec<u8>, i: usize| -> bool {
        c[i >> 3] & (1 << (i & 7)) != 0
    };

    // Sieve odd numbers starting from 3.
    let mut p = 3usize;
    while (p as u64) * (p as u64) <= n {
        let pi = (p - 3) / 2;
        if !is_composite(&composite, pi) {
            // Mark odd multiples of p starting from p*p.
            let mut j = p * p;
            while j as u64 <= n {
                if j % 2 != 0 {
                    mark(&mut composite, (j - 3) / 2);
                }
                j += 2 * p;
            }
        }
        p += 2;
    }

    let mut primes = vec![2u32];
    let mut i = 0usize;
    let mut odd = 3u64;
    while odd <= n {
        if !is_composite(&composite, i) {
            primes.push(odd as u32);
        }
        odd += 2;
        i += 1;
    }
    primes
}
```

Also update the imports at the top of the file — replace the skeleton:

```rust
/*!
Compute N! (N factorial) to arbitrary precision using the prime swing algorithm.

Algorithm: n! = swing(n) × (floor(n/2)!)²  (Luschny prime swing)
  swing(m) = ∏ p^e_p  where e_p = Σ_{j≥1} (floor(m/p^j) mod 2)

Build (requires GMP; run install_deps.sh first):
    cargo build --release
    ./target/release/factorial [N]
*/

use rug::Integer;
use rayon::prelude::*;
use clap::Parser;
use std::io::{self, BufRead, BufWriter, Write};
use std::fs::File;
use std::time::Instant;
```

- [ ] **Step 4: Run sieve tests**

```bash
cd factorial/factorial-rs && cargo test 2>&1 | grep -E "test_sieve|FAILED|ok"
```

Expected: all 5 sieve tests pass.

- [ ] **Step 5: Commit**

```bash
git add factorial/factorial-rs/src/main.rs
git commit -m "feat: add Rust sieve for factorial-rs

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 11: Rust — `compute_swing_chunk` and `compute_swing` (TDD)

**Files:**

- Modify: `factorial/factorial-rs/src/main.rs`

- [ ] **Step 1: Add swing tests to the `#[cfg(test)]` block**

Add after the sieve tests:

```rust
    // --- compute_swing_chunk ---

    #[test]
    fn test_swing_chunk_empty() {
        assert_eq!(compute_swing_chunk(10, &[]), Integer::from(1u32));
    }

    #[test]
    fn test_swing_chunk_prime_exceeds_m() {
        // p=7 > m=5 → no contribution
        assert_eq!(compute_swing_chunk(5, &[7, 11]), Integer::from(1u32));
    }

    #[test]
    fn test_swing_chunk_m2_p2() {
        // p=2, m=2: q=1 (odd) → exp=1 → 2^1=2
        assert_eq!(compute_swing_chunk(2, &[2]), Integer::from(2u32));
    }

    #[test]
    fn test_swing_chunk_m6_p2() {
        // p=2, m=6: q=3 (odd, exp++), q=1 (odd, exp++) → exp=2 → 4
        assert_eq!(compute_swing_chunk(6, &[2]), Integer::from(4u32));
    }

    #[test]
    fn test_swing_chunk_m6_p3() {
        // p=3, m=6: q=2 (even), done → exp=0 → no contribution
        assert_eq!(compute_swing_chunk(6, &[3]), Integer::from(1u32));
    }

    #[test]
    fn test_swing_chunk_m6_p5() {
        // p=5, m=6: q=1 (odd) → exp=1 → 5
        assert_eq!(compute_swing_chunk(6, &[5]), Integer::from(5u32));
    }

    // --- compute_swing ---

    #[test]
    fn test_swing_zero() {
        let primes = sieve(0);
        assert_eq!(compute_swing(0, &primes), Integer::from(1u32));
    }

    #[test]
    fn test_swing_one() {
        let primes = sieve(1);
        assert_eq!(compute_swing(1, &primes), Integer::from(1u32));
    }

    #[test]
    fn test_swing_two() {
        let primes = sieve(2);
        assert_eq!(compute_swing(2, &primes), Integer::from(2u32));
    }

    #[test]
    fn test_swing_four() {
        // swing(4) = 2*3 = 6
        let primes = sieve(4);
        assert_eq!(compute_swing(4, &primes), Integer::from(6u32));
    }

    #[test]
    fn test_swing_six() {
        // swing(6) = 4*5 = 20
        let primes = sieve(6);
        assert_eq!(compute_swing(6, &primes), Integer::from(20u32));
    }

    #[test]
    fn test_swing_satisfies_recursion() {
        // 6! = swing(6) * (3!)^2 = 20 * 36 = 720
        let primes = sieve(6);
        let s = compute_swing(6, &primes);
        let factorial_3 = Integer::from(6u32); // 3! = 6
        let expected = s * Integer::from(&factorial_3 * &factorial_3);
        assert_eq!(expected, Integer::from(720u32));
    }
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd factorial/factorial-rs && cargo test 2>&1 | grep -E "error|FAILED" | head -5
```

Expected: compiler error — `compute_swing_chunk` and `compute_swing` not defined.

- [ ] **Step 3: Implement `compute_swing_chunk` and `compute_swing`**

Add after `fn sieve`:

```rust
/// Compute product of p^e_p for each prime in `chunk`, for swing(m).
/// e_p = number of odd values in {floor(m/p), floor(m/p²), ...}
fn compute_swing_chunk(m: u64, chunk: &[u32]) -> Integer {
    let mut result = Integer::from(1u32);
    for &p in chunk {
        if p as u64 > m {
            break;
        }
        let mut exp = 0u32;
        let mut q = m;
        while q >= p as u64 {
            q /= p as u64;
            if q & 1 == 1 {
                exp += 1;
            }
        }
        if exp > 0 {
            result *= Integer::from(p).pow(exp);
        }
    }
    result
}

/// Compute swing(m) = ∏ p^e_p for all primes p ≤ m.
/// Parallelises over prime chunks using Rayon.
fn compute_swing(m: u64, primes: &[u32]) -> Integer {
    if m < 2 {
        return Integer::from(1u32);
    }
    // Only primes ≤ m contribute.
    let bound = primes.partition_point(|&p| p as u64 <= m);
    let relevant = &primes[..bound];
    if relevant.is_empty() {
        return Integer::from(1u32);
    }
    let n_threads = rayon::current_num_threads().max(1);
    let chunk_size = (relevant.len() / n_threads).max(500);
    relevant
        .par_chunks(chunk_size)
        .map(|chunk| compute_swing_chunk(m, chunk))
        .reduce(|| Integer::from(1u32), |a, b| a * b)
}
```

- [ ] **Step 4: Run tests**

```bash
cd factorial/factorial-rs && cargo test 2>&1 | grep -E "test_swing|ok|FAILED"
```

Expected: all swing tests pass.

- [ ] **Step 5: Commit**

```bash
git add factorial/factorial-rs/src/main.rs
git commit -m "feat: add compute_swing_chunk and compute_swing for factorial-rs

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 12: Rust — `factorial_rec` and `calculate_factorial` (TDD)

**Files:**

- Modify: `factorial/factorial-rs/src/main.rs`

- [ ] **Step 1: Add factorial tests to the `#[cfg(test)]` block**

Add after the swing tests:

```rust
    // --- factorial_rec / calculate_factorial ---

    /// Known exact factorial values.
    const FACTORIAL_REF: &[(u64, &str)] = &[
        (0,  "1"),
        (1,  "1"),
        (2,  "2"),
        (3,  "6"),
        (4,  "24"),
        (5,  "120"),
        (10, "3628800"),
        (20, "2432902008176640000"),
    ];

    #[test]
    fn test_calculate_factorial_ref_values() {
        for &(n, expected) in FACTORIAL_REF {
            let primes = sieve(n);
            let result = factorial_rec(n, &primes);
            assert_eq!(
                result.to_string_radix(10),
                expected,
                "factorial({n}) mismatch"
            );
        }
    }

    #[test]
    fn test_calculate_factorial_100_digit_count() {
        // 100! has 158 digits
        let primes = sieve(100);
        let result = factorial_rec(100, &primes);
        assert_eq!(result.to_string_radix(10).len(), 158);
    }

    #[test]
    fn test_calculate_factorial_idempotent() {
        let primes = sieve(10);
        let r1 = factorial_rec(10, &primes);
        let r2 = factorial_rec(10, &primes);
        assert_eq!(r1, r2);
    }
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd factorial/factorial-rs && cargo test 2>&1 | grep -E "error|FAILED" | head -5
```

Expected: compiler error — `factorial_rec` not defined.

- [ ] **Step 3: Implement `factorial_rec`**

Add after `fn compute_swing`:

```rust
/// Recursive prime swing: n! = swing(n) × (floor(n/2)!)²
/// Recursion depth = floor(log₂(n)) ≈ 30 for n = 10^9.
fn factorial_rec(n: u64, primes: &[u32]) -> Integer {
    if n <= 1 {
        return Integer::from(1u32);
    }
    let half = factorial_rec(n >> 1, primes);
    let swing = compute_swing(n, primes);
    Integer::from(&half * &half) * swing
}
```

- [ ] **Step 4: Run tests**

```bash
cd factorial/factorial-rs && cargo test 2>&1 | grep -E "test_calculate|ok|FAILED"
```

Expected: all 3 factorial tests pass.

- [ ] **Step 5: Commit**

```bash
git add factorial/factorial-rs/src/main.rs
git commit -m "feat: add factorial_rec for factorial-rs

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 13: Rust — CLI and `main`

**Files:**

- Modify: `factorial/factorial-rs/src/main.rs`

- [ ] **Step 1: Add `fmt_int` test**

Add after the factorial tests:

```rust
    // --- fmt_int ---

    #[test]
    fn test_fmt_int_zero() { assert_eq!(fmt_int(0), "0"); }

    #[test]
    fn test_fmt_int_below_thousand() { assert_eq!(fmt_int(999), "999"); }

    #[test]
    fn test_fmt_int_thousands() { assert_eq!(fmt_int(1_000), "1,000"); }

    #[test]
    fn test_fmt_int_millions() { assert_eq!(fmt_int(1_234_567), "1,234,567"); }
```

- [ ] **Step 2: Replace `fn main()` and add CLI structs + helpers**

Replace the entire `fn main()` with the complete implementation. The full `src/main.rs` after this step should be:

```rust
/*!
Compute N! (N factorial) to arbitrary precision using the prime swing algorithm.

Algorithm: n! = swing(n) × (floor(n/2)!)²  (Luschny prime swing)
  swing(m) = ∏ p^e_p  where e_p = Σ_{j≥1} (floor(m/p^j) mod 2)

Build (requires GMP; run install_deps.sh first):
    cargo build --release
    ./target/release/factorial [N]
*/

use rug::Integer;
use rayon::prelude::*;
use clap::Parser;
use std::io::{self, BufRead, BufWriter, Write};
use std::fs::File;
use std::time::Instant;

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

#[derive(Parser)]
#[command(
    name = "factorial",
    about = "Compute N! to arbitrary precision",
    long_about = "Compute N! to arbitrary precision using the prime swing algorithm\n\
                  with Rayon parallelism and GMP arithmetic.\n\n\
                  Run without arguments to use interactive prompts."
)]
struct Cli {
    /// N: compute N!
    n: Option<u64>,
}

// ---------------------------------------------------------------------------
// Sieve
// ---------------------------------------------------------------------------

fn sieve(n: u64) -> Vec<u32> {
    if n < 2 { return vec![]; }
    if n == 2 { return vec![2]; }
    let max_odd_idx = ((n - 3) / 2) as usize;
    let byte_len = (max_odd_idx / 8) + 1;
    let mut composite = vec![0u8; byte_len];
    let mark = |c: &mut Vec<u8>, i: usize| { c[i >> 3] |= 1 << (i & 7); };
    let is_comp = |c: &Vec<u8>, i: usize| -> bool { c[i >> 3] & (1 << (i & 7)) != 0 };
    let mut p = 3usize;
    while (p as u64) * (p as u64) <= n {
        let pi = (p - 3) / 2;
        if !is_comp(&composite, pi) {
            let mut j = p * p;
            while j as u64 <= n {
                if j % 2 != 0 { mark(&mut composite, (j - 3) / 2); }
                j += 2 * p;
            }
        }
        p += 2;
    }
    let mut primes = vec![2u32];
    let mut i = 0usize;
    let mut odd = 3u64;
    while odd <= n {
        if !is_comp(&composite, i) { primes.push(odd as u32); }
        odd += 2;
        i += 1;
    }
    primes
}

// ---------------------------------------------------------------------------
// Prime swing
// ---------------------------------------------------------------------------

fn compute_swing_chunk(m: u64, chunk: &[u32]) -> Integer {
    let mut result = Integer::from(1u32);
    for &p in chunk {
        if p as u64 > m { break; }
        let mut exp = 0u32;
        let mut q = m;
        while q >= p as u64 {
            q /= p as u64;
            if q & 1 == 1 { exp += 1; }
        }
        if exp > 0 { result *= Integer::from(p).pow(exp); }
    }
    result
}

fn compute_swing(m: u64, primes: &[u32]) -> Integer {
    if m < 2 { return Integer::from(1u32); }
    let bound = primes.partition_point(|&p| p as u64 <= m);
    let relevant = &primes[..bound];
    if relevant.is_empty() { return Integer::from(1u32); }
    let n_threads = rayon::current_num_threads().max(1);
    let chunk_size = (relevant.len() / n_threads).max(500);
    relevant
        .par_chunks(chunk_size)
        .map(|chunk| compute_swing_chunk(m, chunk))
        .reduce(|| Integer::from(1u32), |a, b| a * b)
}

fn factorial_rec(n: u64, primes: &[u32]) -> Integer {
    if n <= 1 { return Integer::from(1u32); }
    let half = factorial_rec(n >> 1, primes);
    let swing = compute_swing(n, primes);
    Integer::from(&half * &half) * swing
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn fmt_int(n: u64) -> String {
    let s = n.to_string();
    let mut out = String::with_capacity(s.len() + s.len() / 3);
    for (i, ch) in s.chars().rev().enumerate() {
        if i > 0 && i % 3 == 0 { out.push(','); }
        out.push(ch);
    }
    out.chars().rev().collect()
}

fn read_line() -> String {
    let stdin = io::stdin();
    let mut line = String::new();
    stdin.lock().read_line(&mut line).unwrap();
    line.trim().to_string()
}

fn prompt_n() -> u64 {
    loop {
        print!("Enter N to compute N!: ");
        io::stdout().flush().unwrap();
        match read_line().parse::<u64>() {
            Ok(n) if n >= 1 => return n,
            _ => eprintln!("Please enter a positive integer."),
        }
    }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

fn main() {
    let cli = Cli::parse();

    println!("High-Precision Factorial Calculator (Rust/Rayon)");
    println!("{}", "=".repeat(48));

    let n = match cli.n {
        Some(v) => {
            if v < 1 { eprintln!("Error: N must be >= 1"); std::process::exit(1); }
            v
        }
        None => prompt_n(),
    };

    println!("Computing {}! ...", fmt_int(n));
    println!("Backend: prime swing / rug+GMP / rayon ({} threads)",
             rayon::current_num_threads());

    let t0 = Instant::now();

    let t_sieve = Instant::now();
    let primes = sieve(n);
    eprintln!("  Sieve: {} primes in {:.2}s", fmt_int(primes.len() as u64),
              t_sieve.elapsed().as_secs_f64());

    let t_fact = Instant::now();
    let result = factorial_rec(n, &primes);
    eprintln!("  Factorial: {:.2}s", t_fact.elapsed().as_secs_f64());

    let t_conv = Instant::now();
    let digits_str = result.to_string_radix(10);
    eprintln!("  Conversion: {:.2}s", t_conv.elapsed().as_secs_f64());

    let digit_count = digits_str.len();
    println!("\n{}! has {} digits", fmt_int(n), fmt_int(digit_count as u64));
    println!("Total time: {:.2}s", t0.elapsed().as_secs_f64());

    let filename = format!("factorial_{n}.txt");
    println!("Saving to {filename}...");

    let file = File::create(&filename).expect("failed to create output file");
    let mut writer = BufWriter::new(file);
    writeln!(writer, "{}! computed using prime swing", fmt_int(n)).unwrap();
    writeln!(writer, "{}", "=".repeat(60)).unwrap();
    writeln!(writer).unwrap();
    writer.write_all(digits_str.as_bytes()).unwrap();
    writeln!(writer, "\n\nTotal digits: {}", fmt_int(digit_count as u64)).unwrap();
    writer.flush().unwrap();

    println!("Saved to {filename}");
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // --- sieve ---

    #[test]
    fn test_sieve_below_2_empty() {
        assert_eq!(sieve(0), Vec::<u32>::new());
        assert_eq!(sieve(1), Vec::<u32>::new());
    }

    #[test]
    fn test_sieve_n_equals_2() {
        assert_eq!(sieve(2), vec![2u32]);
    }

    #[test]
    fn test_sieve_to_10() {
        assert_eq!(sieve(10), vec![2u32, 3, 5, 7]);
    }

    #[test]
    fn test_sieve_no_composites() {
        let primes = sieve(50);
        for &p in &primes {
            for d in 2..p {
                assert_ne!(p % d, 0, "{p} should be prime");
            }
        }
    }

    #[test]
    fn test_sieve_count_to_100() {
        assert_eq!(sieve(100).len(), 25);
    }

    // --- compute_swing_chunk ---

    #[test]
    fn test_swing_chunk_empty() {
        assert_eq!(compute_swing_chunk(10, &[]), Integer::from(1u32));
    }

    #[test]
    fn test_swing_chunk_prime_exceeds_m() {
        assert_eq!(compute_swing_chunk(5, &[7, 11]), Integer::from(1u32));
    }

    #[test]
    fn test_swing_chunk_m2_p2() {
        assert_eq!(compute_swing_chunk(2, &[2]), Integer::from(2u32));
    }

    #[test]
    fn test_swing_chunk_m6_p2() {
        assert_eq!(compute_swing_chunk(6, &[2]), Integer::from(4u32));
    }

    #[test]
    fn test_swing_chunk_m6_p3() {
        assert_eq!(compute_swing_chunk(6, &[3]), Integer::from(1u32));
    }

    #[test]
    fn test_swing_chunk_m6_p5() {
        assert_eq!(compute_swing_chunk(6, &[5]), Integer::from(5u32));
    }

    // --- compute_swing ---

    #[test]
    fn test_swing_zero() {
        assert_eq!(compute_swing(0, &[]), Integer::from(1u32));
    }

    #[test]
    fn test_swing_one() {
        assert_eq!(compute_swing(1, &[]), Integer::from(1u32));
    }

    #[test]
    fn test_swing_two() {
        let primes = sieve(2);
        assert_eq!(compute_swing(2, &primes), Integer::from(2u32));
    }

    #[test]
    fn test_swing_four() {
        let primes = sieve(4);
        assert_eq!(compute_swing(4, &primes), Integer::from(6u32));
    }

    #[test]
    fn test_swing_six() {
        let primes = sieve(6);
        assert_eq!(compute_swing(6, &primes), Integer::from(20u32));
    }

    #[test]
    fn test_swing_satisfies_recursion() {
        let primes = sieve(6);
        let s = compute_swing(6, &primes);
        let factorial_3 = Integer::from(6u32);
        let expected = s * Integer::from(&factorial_3 * &factorial_3);
        assert_eq!(expected, Integer::from(720u32));
    }

    // --- factorial_rec ---

    const FACTORIAL_REF: &[(u64, &str)] = &[
        (0, "1"), (1, "1"), (2, "2"), (3, "6"), (4, "24"),
        (5, "120"), (10, "3628800"), (20, "2432902008176640000"),
    ];

    #[test]
    fn test_calculate_factorial_ref_values() {
        for &(n, expected) in FACTORIAL_REF {
            let primes = sieve(n);
            let result = factorial_rec(n, &primes);
            assert_eq!(result.to_string_radix(10), expected, "factorial({n})");
        }
    }

    #[test]
    fn test_calculate_factorial_100_digit_count() {
        let primes = sieve(100);
        let result = factorial_rec(100, &primes);
        assert_eq!(result.to_string_radix(10).len(), 158);
    }

    #[test]
    fn test_calculate_factorial_idempotent() {
        let primes = sieve(10);
        assert_eq!(factorial_rec(10, &primes), factorial_rec(10, &primes));
    }

    // --- fmt_int ---

    #[test]
    fn test_fmt_int_zero() { assert_eq!(fmt_int(0), "0"); }

    #[test]
    fn test_fmt_int_below_thousand() { assert_eq!(fmt_int(999), "999"); }

    #[test]
    fn test_fmt_int_thousands() { assert_eq!(fmt_int(1_000), "1,000"); }

    #[test]
    fn test_fmt_int_millions() { assert_eq!(fmt_int(1_234_567), "1,234,567"); }
}
```

- [ ] **Step 3: Run the full test suite**

```bash
cd factorial/factorial-rs && cargo test 2>&1 | tail -10
```

Expected: all tests pass, no warnings.

- [ ] **Step 4: Run `make lint`**

```bash
cd factorial/factorial-rs && make lint
```

Expected: no clippy warnings.

- [ ] **Step 5: Run `make test`**

```bash
cd factorial/factorial-rs && make test
```

Expected: lint + all tests pass.

- [ ] **Step 6: Build release binary**

```bash
cd factorial/factorial-rs && cargo build --release 2>&1 | tail -3
```

Expected: `Finished release [optimized]`.

- [ ] **Step 7: Commit**

```bash
git add factorial/factorial-rs/src/main.rs
git commit -m "feat: complete factorial-rs CLI with prime swing + Rayon

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 14: Rust CLAUDE.md

**Files:**

- Create: `factorial/factorial-rs/CLAUDE.md`

- [ ] **Step 1: Create `factorial/factorial-rs/CLAUDE.md`**

````markdown
# CLAUDE.md

Rust CLI that computes N! using the prime swing algorithm with Rayon parallelism.

## Build

```bash
make factorial  # cargo build --release
make lint       # cargo clippy -- -D warnings
make test       # lint + cargo test
make clean      # cargo clean
```
````

## Algorithm

`n! = swing(n) × (⌊n/2⌋!)²` (recursive, depth = ⌊log₂(n)⌋ ≈ 30 for n=10^9).

`swing(m) = ∏ p^e_p` where `e_p = Σ_{j≥1} (⌊m/pʲ⌋ mod 2)`.

## Code Layout (`src/main.rs`)

- `fn sieve(n) -> Vec<u32>`: bit-packed odd sieve; memory = n/16 bytes
- `fn compute_swing_chunk(m, chunk) -> Integer`: per-chunk swing product
- `fn compute_swing(m, primes) -> Integer`: parallel via `rayon::par_chunks`
- `fn factorial_rec(n, primes) -> Integer`: recursive prime swing
- `fn fmt_int(n) -> String`: thousands-separator formatter
- `fn prompt_n() -> u64`: interactive stdin prompt
- `fn main()`: CLI → sieve → factorial → write file

## rug Arithmetic

`rug::Integer` operator overloading returns lazy "incomplete" types.
Always wrap with `Integer::from(...)`:

```rust
Integer::from(&a * &b)   // correct
&a * &b                  // does not compile as Integer
```

## Testing

Tests live in `#[cfg(test)] mod tests` at the bottom of `src/main.rs`.

```bash
cargo test
cargo tarpaulin --out Stdout
```

## Keeping This File Up To Date

Update when: function renamed/added, Makefile target change, dependency added,
test coverage changes, behavior change. Also update top-level and `factorial/CLAUDE.md`.

````

- [ ] **Step 2: Commit**

```bash
git add factorial/factorial-rs/CLAUDE.md
git commit -m "docs: add factorial-rs/CLAUDE.md

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
````

---

## Task 15: CI workflows

**Files:**

- Create: `.github/workflows/factorial-py.yml`
- Create: `.github/workflows/factorial-rs.yml`
- Create: `.github/workflows/release-factorial-rs.yml`

- [ ] **Step 1: Create `.github/workflows/factorial-py.yml`**

```yaml
name: factorial.py

on:
  pull_request:
    branches:
      - master

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  test:
    name: Test factorial.py
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: factorial
    steps:
      - uses: actions/checkout@v5

      - name: Install GMP and MPFR
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev libmpfr-dev

      - name: Install Python dependencies
        run: pip install mpmath gmpy2 coverage ruff

      - name: Run tests
        run: make test
```

- [ ] **Step 2: Create `.github/workflows/factorial-rs.yml`**

```yaml
name: factorial-rs

on:
  pull_request:
    branches:
      - master

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  test:
    name: Test factorial-rs
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: factorial/factorial-rs
    steps:
      - uses: actions/checkout@v5

      - name: Install GMP and MPFR
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev libmpfr-dev

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: factorial/factorial-rs

      - name: Run tests
        run: make test

  build:
    name: Build factorial-rs
    runs-on: ubuntu-latest
    needs: [test]
    defaults:
      run:
        working-directory: factorial/factorial-rs
    steps:
      - uses: actions/checkout@v5

      - name: Install GMP and MPFR
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev libmpfr-dev

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: factorial/factorial-rs

      - name: Build
        run: cargo build --release

      - name: Upload artifact
        uses: actions/upload-artifact@v7
        with:
          name: factorial
          path: factorial/factorial-rs/target/release/factorial
          retention-days: 7
```

- [ ] **Step 3: Create `.github/workflows/release-factorial-rs.yml`**

```yaml
name: release-factorial-rs

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version number without the v prefix (e.g. 1.2.0)"
        required: true
        type: string

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

permissions:
  contents: write

jobs:
  release:
    name: Release factorial-rs
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Install GMP and MPFR
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev libmpfr-dev

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: factorial/factorial-rs

      - name: Run tests
        run: make test
        working-directory: factorial/factorial-rs

      - name: Build release binary
        run: cargo build --release
        working-directory: factorial/factorial-rs

      - name: Generate release notes
        id: notes
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 --match="factorial-v*" 2>/dev/null || true)
          if [ -n "$PREV_TAG" ]; then
            NOTES=$(git log "${PREV_TAG}..HEAD" --pretty=format:"- %s" -- factorial/factorial-rs/ || true)
          else
            NOTES=$(git log HEAD --pretty=format:"- %s" -- factorial/factorial-rs/ || true)
          fi
          DELIMITER="EOF_$(openssl rand -hex 8)"
          {
            printf 'notes<<%s\n' "${DELIMITER}"
            printf '%s\n' "${NOTES}"
            printf '%s\n' "${DELIMITER}"
          } >> "$GITHUB_OUTPUT"

      - name: Create and push tag
        env:
          VERSION: ${{ inputs.version }}
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git tag "factorial-v${VERSION}"
          git push origin "factorial-v${VERSION}"

      - name: Create GitHub release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: "factorial-v${{ inputs.version }}"
          name: "factorial v${{ inputs.version }}"
          body: "${{ steps.notes.outputs.notes }}"
          files: factorial/factorial-rs/target/release/factorial
```

- [ ] **Step 4: Validate YAML syntax**

```bash
python3 -c "
import yaml
for f in ['.github/workflows/factorial-py.yml', '.github/workflows/factorial-rs.yml', '.github/workflows/release-factorial-rs.yml']:
    yaml.safe_load(open(f))
    print(f'OK: {f}')
"
```

Expected: three `OK:` lines.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/factorial-py.yml .github/workflows/factorial-rs.yml .github/workflows/release-factorial-rs.yml
git commit -m "ci: add factorial-py, factorial-rs, and release-factorial-rs workflows

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 16: Update pre-commit, pre-push, .gitignore

**Files:**

- Modify: `scripts/pre-commit`
- Modify: `scripts/pre-push`
- Modify: `.gitignore`

- [ ] **Step 1: Update `scripts/pre-commit`**

Change the dir loop line from:

```bash
for dir in pi pi/pi-rs prime/prime-rs fib fib/fib-rs sq sq/sq-rs twin-primes/twin-primes-rs e e/e-rs; do
```

to:

```bash
for dir in pi pi/pi-rs prime/prime-rs fib fib/fib-rs sq sq/sq-rs twin-primes/twin-primes-rs e e/e-rs factorial factorial/factorial-rs; do
```

- [ ] **Step 2: Update `scripts/pre-push`**

Change the dir loop line from:

```bash
    for dir in pi pi/pi-rs prime/prime-rs fib fib/fib-rs sq sq/sq-rs twin-primes/twin-primes-rs e e/e-rs; do
```

to:

```bash
    for dir in pi pi/pi-rs prime/prime-rs fib fib/fib-rs sq sq/sq-rs twin-primes/twin-primes-rs e e/e-rs factorial factorial/factorial-rs; do
```

- [ ] **Step 3: Add `factorial_*.txt` to `.gitignore`**

Add after `e_*_digits.txt`:

```
factorial_*.txt
```

- [ ] **Step 4: Verify hooks still work**

```bash
bash scripts/pre-commit
```

Expected: runs without error (no staged changes in factorial dirs yet, so no lint is run).

- [ ] **Step 5: Commit**

```bash
git add scripts/pre-commit scripts/pre-push .gitignore
git commit -m "chore: add factorial dirs to pre-commit/pre-push hooks; gitignore factorial output

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 17: Update README, CLAUDE.md, docs/superpowers/README.md

**Files:**

- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/README.md`

- [ ] **Step 1: Add CI badges to `README.md`**

After the `e-rs` badge line (line 12), add:

```markdown
[![factorial.py](https://github.com/brujack/math/actions/workflows/factorial-py.yml/badge.svg?event=pull_request)](https://github.com/brujack/math/actions/workflows/factorial-py.yml)
[![factorial-rs](https://github.com/brujack/math/actions/workflows/factorial-rs.yml/badge.svg?event=pull_request)](https://github.com/brujack/math/actions/workflows/factorial-rs.yml)
```

- [ ] **Step 2: Add factorial row to the project table in `README.md`**

After the `e/` row, add:

```markdown
| [`factorial/`](factorial/README.md) | Compute N! to arbitrary precision | Python + Rust | [![factorial.py](https://github.com/brujack/math/actions/workflows/factorial-py.yml/badge.svg?event=pull_request)](https://github.com/brujack/math/actions/workflows/factorial-py.yml) [![factorial-rs](https://github.com/brujack/math/actions/workflows/factorial-rs.yml/badge.svg?event=pull_request)](https://github.com/brujack/math/actions/workflows/factorial-rs.yml) |
```

- [ ] **Step 3: Add factorial section to `README.md`**

After the `## e` section, add:

```markdown
## factorial

Computes N! to arbitrary precision using the **prime swing algorithm** (Luschny).

- Python implementation (`factorial/factorial.py`) — gmpy2/GMP fast path, mpmath fallback; targets n up to ~10^7
- Rust implementation (`factorial/factorial-rs/`) — rug/GMP + Rayon; targets n up to ~10^9

See [`factorial/README.md`](factorial/README.md) for full details.

---
```

- [ ] **Step 4: Create `factorial/README.md`**

````markdown
# factorial

Computes N! to arbitrary precision using the **prime swing algorithm**.

## Algorithm

`n! = swing(n) × (⌊n/2⌋!)²` — recursive squaring via Luschny prime swing.

`swing(m) = ∏ p^e_p` where `e_p = Σ_{j≥1} (⌊m/pʲ⌋ mod 2)` — one pass over the
prime sieve, counting odd terms in each prime's Legendre sequence.

## Usage

### Python

```bash
cd factorial
bash install_deps.sh   # once
make run               # python3 factorial.py (interactive)
python3 factorial.py 1000000  # compute 1000000! directly
make test
```
````

### Rust

```bash
cd factorial/factorial-rs
bash install_deps.sh   # once
make factorial         # cargo build --release
./target/release/factorial 1000000
make test
```

Output is always saved to `factorial_<N>.txt`.

````

- [ ] **Step 5: Update top-level `CLAUDE.md`**

In `CLAUDE.md`:

**Repository Overview table** — add after the `e/` row:

```markdown
| [`factorial/`](factorial/)     | Python + Rust | Compute N! to arbitrary precision (prime swing) | [`factorial/CLAUDE.md`](factorial/CLAUDE.md) |
````

**Dependency Installation table** — add after the `e/e-rs/install_deps.sh` row:

```markdown
| `factorial/install_deps.sh` | GMP + MPFR, `mpmath`, `gmpy2`, `ruff`, `coverage` |
| `factorial/factorial-rs/install_deps.sh` | GMP + MPFR, Rust toolchain, `cargo-tarpaulin` |
```

**Quick Reference** — add two sections after `### Python (e/)` and `### Rust (e/e-rs/)`:

````markdown
### Python (`factorial/`)

```bash
cd factorial
make run       # python3 factorial.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_factorial -v
make coverage  # coverage run + report
```
````

### Rust (`factorial/factorial-rs/`)

```bash
cd factorial/factorial-rs
make factorial # cargo build --release
make lint      # cargo clippy -- -D warnings
make test      # lint, then cargo test
```

````

**CI table** — change "Seventeen workflow files" to "Twenty workflow files" and add three rows before the `auto-merge` row:

```markdown
| factorial.py           | `.github/workflows/factorial-py.yml`           | test                                                                         |
| factorial-rs           | `.github/workflows/factorial-rs.yml`           | test → build + artifact                                                      |
| release-factorial-rs   | `.github/workflows/release-factorial-rs.yml`   | release (manual dispatch)                                                    |
````

- [ ] **Step 6: Update `docs/superpowers/README.md`**

Add row to All Plans table (after the euler-number row):

```markdown
| 2026-04-24 | [factorial](plans/2026-04-24-factorial.md) | [spec](specs/2026-04-24-factorial-design.md) | In Progress |
```

Remove the factorial row from the Backlog table.

- [ ] **Step 7: Commit**

```bash
git add README.md factorial/README.md CLAUDE.md docs/superpowers/README.md
git commit -m "docs: add factorial to README, CLAUDE.md, and superpowers index

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review Checklist

**Spec coverage:**

- [x] Prime swing algorithm — Tasks 3–6 (Python), 10–12 (Rust)
- [x] Always save to file — Task 7 (`_write_factorial_file`), Task 13 (Rust main)
- [x] CLI: interactive + positional arg — Task 7, Task 13
- [x] Python gmpy2 fast path + mpmath fallback — Tasks 5–6
- [x] Rust rug + Rayon — Tasks 10–12
- [x] ProcessPoolExecutor parallelism (Python) — Task 5
- [x] Rayon par_chunks parallelism (Rust) — Task 11
- [x] TDD for all functions — every task follows red→green
- [x] All 9 test classes from spec — covered across Tasks 3–7
- [x] ADR for algorithm — Task 1
- [x] CI workflows (3 files) — Task 15
- [x] pre-commit/pre-push/gitignore — Task 16
- [x] README, CLAUDE.md, superpowers index — Task 17

**No placeholders found.**

**Type consistency:** `_compute_swing_chunk` returns `int`; `_compute_swing` returns `gmpy2.mpz` or `int`; `_factorial_rec` returns `gmpy2.mpz` or `int`; `calculate_factorial` returns same. `_write_factorial_file` calls `int(result)` to normalise before `str()` — handles both types.
