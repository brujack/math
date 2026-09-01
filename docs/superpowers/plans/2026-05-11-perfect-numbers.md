# Perfect Numbers Implementation Plan

> **Status: DONE** — merged; index row marked Done. Banner added retroactively by a 2026-09-01 docs audit, which found the row and the banner had drifted apart.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `perfect-numbers/` project (Python + Rust) that finds all perfect numbers up to 10^N using the Lucas-Lehmer Mersenne primality test and the multiplicative σ formula for verification.

**Architecture:** Python CLI (`perfect_numbers.py`) uses built-in arbitrary-precision integers — no external deps. Rust CLI (`perfect-numbers-rs/`) uses `rug::Integer` (GMP) for big-integer arithmetic. Both follow the `run<R,W,E>(dir)` injectable-IO pattern used by all other Rust CLIs in the repo. N range 1–54 covers all 10 known perfect numbers.

**Tech Stack:** Python stdlib only (no gmpy2), Rust + rug (GMP) + clap, unittest, cargo-tarpaulin.

---

## File Map

| File                                                 | Action                              |
| ---------------------------------------------------- | ----------------------------------- |
| `perfect-numbers/perfect_numbers.py`                 | Create                              |
| `perfect-numbers/test_perfect_numbers.py`            | Create                              |
| `perfect-numbers/Makefile`                           | Create                              |
| `perfect-numbers/install_deps.sh`                    | Create                              |
| `perfect-numbers/CLAUDE.md`                          | Create                              |
| `perfect-numbers/README.md`                          | Create                              |
| `perfect-numbers/perfect-numbers-rs/Cargo.toml`      | Create                              |
| `perfect-numbers/perfect-numbers-rs/rustfmt.toml`    | Create                              |
| `perfect-numbers/perfect-numbers-rs/Makefile`        | Create                              |
| `perfect-numbers/perfect-numbers-rs/install_deps.sh` | Create                              |
| `perfect-numbers/perfect-numbers-rs/src/main.rs`     | Create                              |
| `perfect-numbers/perfect-numbers-rs/tests/cli.rs`    | Create                              |
| `perfect-numbers/perfect-numbers-rs/CLAUDE.md`       | Create                              |
| `.github/workflows/perfect-numbers-py.yml`           | Create                              |
| `.github/workflows/perfect-numbers-rs.yml`           | Create                              |
| `scripts/pre-commit`                                 | Modify — add dirs to loop           |
| `scripts/pre-push`                                   | Modify — add dirs to loop           |
| `CLAUDE.md`                                          | Modify — add project to tables      |
| `README.md`                                          | Modify — add badges and project row |
| `docs/superpowers/README.md`                         | Modify — add plan row               |
| `docs/cursor/README.md`                              | Modify — add plan row               |

---

## Task 1: Python — core algorithm functions

**Files:**

- Create: `perfect-numbers/perfect_numbers.py`
- Create: `perfect-numbers/test_perfect_numbers.py`

### Step 1 — Create the source file stub and test file

Create `perfect-numbers/perfect_numbers.py`:

```python
#!/usr/bin/env python3
"""
Find all perfect numbers up to 10^N.

A perfect number equals the sum of its proper divisors. All known even perfect
numbers have the form 2^(p-1) * (2^p - 1) where 2^p - 1 is a Mersenne prime.

Uses the Lucas-Lehmer primality test and the multiplicative sigma formula.

Run without arguments for an interactive prompt, or supply N directly:
    python3 perfect_numbers.py [N]
"""

import argparse
import sys
```

Create `perfect-numbers/test_perfect_numbers.py`:

```python
import argparse
import io
import os
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout

from perfect_numbers import (
    generate_perfect_numbers,
    get_exponent,
    is_prime,
    lucas_lehmer,
    main,
    verify_perfect,
)

PERFECT_NUMBERS = {
    2: 6,
    3: 28,
    5: 496,
    7: 8128,
    13: 33550336,
    17: 8589869056,
    19: 137438691328,
}
```

### Step 2 — Write TestIsPrime

Append to `test_perfect_numbers.py`:

```python
class TestIsPrime(unittest.TestCase):
    def test_zero_not_prime(self):
        self.assertFalse(is_prime(0))

    def test_one_not_prime(self):
        self.assertFalse(is_prime(1))

    def test_negative_not_prime(self):
        self.assertFalse(is_prime(-7))

    def test_two_is_prime(self):
        self.assertTrue(is_prime(2))

    def test_even_composite_not_prime(self):
        self.assertFalse(is_prime(4))

    def test_small_primes(self):
        for p in [3, 5, 7, 11, 13, 17, 19, 23, 29, 31]:
            with self.subTest(p=p):
                self.assertTrue(is_prime(p))

    def test_small_composites(self):
        for n in [6, 8, 9, 10, 15, 25, 49]:
            with self.subTest(n=n):
                self.assertFalse(is_prime(n))

    def test_89_is_prime(self):
        self.assertTrue(is_prime(89))

    def test_91_is_composite(self):
        # 91 = 7 * 13
        self.assertFalse(is_prime(91))
```

### Step 3 — Run test → confirm RED

```bash
cd perfect-numbers
python3 -m unittest test_perfect_numbers.TestIsPrime -v 2>&1 | tail -5
```

Expected: `ImportError: cannot import name 'is_prime'`

### Step 4 — Implement `is_prime`

Add to `perfect_numbers.py`:

```python
def is_prime(n: int) -> bool:
    """Return True if n is prime. Trial division — only called for n <= 90."""
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True
```

### Step 5 — Run test → confirm GREEN

```bash
python3 -m unittest test_perfect_numbers.TestIsPrime -v 2>&1 | tail -3
```

Expected: `Ran 9 tests in 0.XXXs  OK`

### Step 6 — Write TestLucasLehmer

Append to `test_perfect_numbers.py`:

```python
class TestLucasLehmer(unittest.TestCase):
    def test_p2_mersenne(self):
        # M_2 = 3 is prime
        self.assertTrue(lucas_lehmer(2))

    def test_known_mersenne_prime_exponents(self):
        for p in [3, 5, 7, 13, 17, 19, 31, 61, 89]:
            with self.subTest(p=p):
                self.assertTrue(lucas_lehmer(p), f"p={p} should be Mersenne prime")

    def test_known_non_mersenne_prime_exponents(self):
        for p in [11, 23, 29, 37, 41]:
            with self.subTest(p=p):
                self.assertFalse(lucas_lehmer(p), f"p={p} should not be Mersenne prime")
```

### Step 7 — Run → RED, implement `lucas_lehmer`, run → GREEN

```bash
python3 -m unittest test_perfect_numbers.TestLucasLehmer -v 2>&1 | tail -3
```

Expected: `ImportError` or `AttributeError`

Add to `perfect_numbers.py`:

```python
def lucas_lehmer(p: int) -> bool:
    """Return True if M_p = 2^p - 1 is a Mersenne prime.

    Lucas-Lehmer test: s_0 = 4; s_i = s_{i-1}^2 - 2 mod M_p.
    M_p is prime iff s_{p-2} == 0. Special case: M_2 = 3 is prime.
    """
    if p == 2:
        return True
    mp = (1 << p) - 1
    s = 4
    for _ in range(p - 2):
        s = (s * s - 2) % mp
    return s == 0
```

```bash
python3 -m unittest test_perfect_numbers.TestLucasLehmer -v 2>&1 | tail -3
```

Expected: `Ran 3 tests in X.XXXs  OK`

### Step 8 — Write TestVerifyPerfect

Append to `test_perfect_numbers.py`:

```python
class TestVerifyPerfect(unittest.TestCase):
    def test_known_exponents_verify(self):
        for p in [2, 3, 5, 7, 13, 17, 19]:
            with self.subTest(p=p):
                self.assertTrue(verify_perfect(p))

    def test_sigma_equals_2n(self):
        # Algebraic check: (2^p - 1) * 2^p == 2 * 2^(p-1) * (2^p - 1)
        for p in [2, 3, 5, 7]:
            mp = (1 << p) - 1
            n = (1 << (p - 1)) * mp
            sigma = mp * (mp + 1)
            self.assertEqual(sigma, 2 * n)
```

### Step 9 — Run → RED, implement `verify_perfect`, run → GREEN

Add to `perfect_numbers.py`:

```python
def verify_perfect(p: int) -> bool:
    """Verify 2^(p-1) * (2^p - 1) is perfect using the sigma formula.

    sigma(2^(p-1) * M_p) = (2^p - 1) * 2^p = 2n.
    """
    mp = (1 << p) - 1
    n = (1 << (p - 1)) * mp
    sigma = mp * (mp + 1)   # (2^p - 1) * 2^p
    return sigma == 2 * n
```

```bash
python3 -m unittest test_perfect_numbers.TestVerifyPerfect -v 2>&1 | tail -3
```

Expected: `Ran 2 tests in X.XXXs  OK`

### Step 10 — Write TestGeneratePerfectNumbers

Append to `test_perfect_numbers.py`:

```python
class TestGeneratePerfectNumbers(unittest.TestCase):
    def test_limit_below_6_yields_empty(self):
        self.assertEqual(list(generate_perfect_numbers(5)), [])

    def test_limit_1_yields_6(self):
        result = list(generate_perfect_numbers(10 ** 1))
        self.assertEqual(result, [(2, 6)])

    def test_limit_n4_yields_first_4(self):
        result = list(generate_perfect_numbers(10 ** 4))
        self.assertEqual([n for _, n in result], [6, 28, 496, 8128])

    def test_limit_n8_yields_5_numbers(self):
        result = list(generate_perfect_numbers(10 ** 8))
        self.assertEqual(len(result), 5)
        self.assertEqual(result[4][0], 13)   # p=13 gives 33550336

    def test_limit_n54_yields_all_10(self):
        result = list(generate_perfect_numbers(10 ** 54))
        self.assertEqual(len(result), 10)
        last_p, last_n = result[-1]
        self.assertEqual(last_p, 89)
        self.assertEqual(
            last_n,
            191561942608236107294793378084303638130997321548169216,
        )

    def test_results_in_ascending_order(self):
        result = list(generate_perfect_numbers(10 ** 20))
        ns = [n for _, n in result]
        self.assertEqual(ns, sorted(ns))
```

### Step 11 — Run → RED, implement `generate_perfect_numbers`, run → GREEN

Add to `perfect_numbers.py`:

```python
def generate_perfect_numbers(limit: int):
    """Yield (p, n) for each perfect number n <= limit.

    Tests every prime p up to the bound derived from limit.
    """
    if limit < 6:
        return
    # 2^(2p-1) <= limit => p <= (bit_length + 1) / 2
    max_p = (limit.bit_length() // 2) + 3
    for p in range(2, max_p + 1):
        if not is_prime(p):
            continue
        if not lucas_lehmer(p):
            continue
        mp = (1 << p) - 1
        n = (1 << (p - 1)) * mp
        if n > limit:
            return
        yield p, n
```

```bash
python3 -m unittest test_perfect_numbers.TestGeneratePerfectNumbers -v 2>&1 | tail -3
```

Expected: `Ran 6 tests in X.XXXs  OK`

### Step 12 — Commit

```bash
cd perfect-numbers
git add perfect_numbers.py test_perfect_numbers.py
git commit -m "feat: perfect-numbers Python core — is_prime, lucas_lehmer, verify_perfect, generate

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Python — CLI (get_exponent, main)

**Files:**

- Modify: `perfect-numbers/perfect_numbers.py`
- Modify: `perfect-numbers/test_perfect_numbers.py`

### Step 1 — Write TestGetExponent

Append to `test_perfect_numbers.py`:

```python
class TestGetExponent(unittest.TestCase):
    def _ns(self, exponent):
        return argparse.Namespace(exponent=exponent)

    def test_valid_minimum(self):
        self.assertEqual(get_exponent(self._ns(1)), 1)

    def test_valid_maximum(self):
        self.assertEqual(get_exponent(self._ns(54)), 54)

    def test_zero_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._ns(0))

    def test_55_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._ns(55))

    def test_negative_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._ns(-1))

    def test_interactive_valid_first_try(self):
        with unittest.mock.patch("builtins.input", return_value="8"):
            self.assertEqual(get_exponent(self._ns(None)), 8)

    def test_interactive_invalid_then_valid(self):
        with unittest.mock.patch("builtins.input", side_effect=["0", "abc", "5"]), \
             unittest.mock.patch("builtins.print"):
            self.assertEqual(get_exponent(self._ns(None)), 5)
```

### Step 2 — Run → RED, implement `parse_args` + `get_exponent`, run → GREEN

Add to `perfect_numbers.py`:

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find all perfect numbers up to 10^N",
        epilog="Run without arguments for an interactive prompt.",
    )
    parser.add_argument(
        "exponent",
        type=int,
        nargs="?",
        help="N: finds perfect numbers up to 10^N (1-54)",
    )
    return parser.parse_args()


def get_exponent(args: argparse.Namespace) -> int:
    """Return validated N from CLI args, or prompt interactively."""
    if args.exponent is not None:
        n = args.exponent
        if n < 1 or n > 54:
            print("Error: N must be between 1 and 54.", file=sys.stderr)
            sys.exit(1)
        return n
    while True:
        try:
            raw = input("Enter N (finds perfect numbers up to 10^N, max 54): ")
            n = int(raw)
            if 1 <= n <= 54:
                return n
            print("N must be between 1 and 54.")
        except ValueError:
            print("Please enter a positive integer.")
```

```bash
cd perfect-numbers
python3 -m unittest test_perfect_numbers.TestGetExponent -v 2>&1 | tail -3
```

Expected: `Ran 7 tests in X.XXXs  OK`

### Step 3 — Write TestMain

Append to `test_perfect_numbers.py`:

```python
class TestMain(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_n1_creates_file_with_6(self):
        with unittest.mock.patch("sys.argv", ["perfect_numbers.py", "1"]), \
             redirect_stdout(io.StringIO()):
            main()
        with open("perfect-numbers_1e1.txt") as f:
            self.assertEqual(f.read().splitlines(), ["6"])

    def test_n4_creates_file_with_4_numbers(self):
        with unittest.mock.patch("sys.argv", ["perfect_numbers.py", "4"]), \
             redirect_stdout(io.StringIO()):
            main()
        with open("perfect-numbers_1e4.txt") as f:
            self.assertEqual(f.read().splitlines(), ["6", "28", "496", "8128"])

    def test_keyboard_interrupt_exits_1(self):
        with unittest.mock.patch("sys.argv", ["perfect_numbers.py", "1"]), \
             unittest.mock.patch(
                 "perfect_numbers.lucas_lehmer", side_effect=KeyboardInterrupt
             ), \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)

    def test_permission_error_exits_1(self):
        with unittest.mock.patch("sys.argv", ["perfect_numbers.py", "1"]), \
             unittest.mock.patch(
                 "builtins.open",
                 side_effect=PermissionError("Permission denied"),
             ), \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
```

### Step 4 — Run TestMain → RED (main not defined)

```bash
cd perfect-numbers
python3 -m unittest test_perfect_numbers.TestMain -v 2>&1 | tail -5
```

Expected: `ImportError` or `AttributeError: main`

### Step 5 — Implement `main`

Add to `perfect_numbers.py`:

```python
def main() -> None:
    args = parse_args()
    n = get_exponent(args)
    limit = 10 ** n

    print("Perfect Number Finder (Python)")
    print("=" * 40)
    print(f"Finding perfect numbers up to 10^{n} = {limit:,}")
    print()

    try:
        results = []
        max_p = (limit.bit_length() // 2) + 3
        for p in range(2, max_p + 1):
            if not is_prime(p):
                continue
            mp = (1 << p) - 1
            if not lucas_lehmer(p):
                print(f"p={p}: M_{p}={mp} [not prime]")
                continue
            pn = (1 << (p - 1)) * mp
            digits = len(str(pn))
            s = "digit" if digits == 1 else "digits"
            if pn > limit:
                print(f"p={p}: M_{p}={mp} [Mersenne prime] -> {pn} ({digits} {s}, exceeds limit)")
                break
            verified = verify_perfect(p)
            status = "verified" if verified else "FAILED"
            print(f"p={p}: M_{p}={mp} [Mersenne prime] -> {pn} ({digits} {s}, {status})")
            results.append(pn)

        count = len(results)
        print()
        s = "number" if count == 1 else "numbers"
        print(f"Found {count} perfect {s} up to 10^{n}")

        filename = f"perfect-numbers_1e{n}.txt"
        with open(filename, "w") as f:
            for pn in results:
                f.write(str(pn))
                f.write("\n")
        print(f"Saved to {filename}")

    except KeyboardInterrupt:
        print("\nGeneration interrupted.")
        sys.exit(1)
    except PermissionError as err:
        print(f"Error: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Step 6 — Run full suite → GREEN

```bash
cd perfect-numbers
python3 -m unittest test_perfect_numbers -v 2>&1 | tail -5
```

Expected: all tests pass.

### Step 7 — Commit

```bash
cd perfect-numbers
git add perfect_numbers.py test_perfect_numbers.py
git commit -m "feat: perfect-numbers Python CLI — parse_args, get_exponent, main

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Python infrastructure

**Files:**

- Create: `perfect-numbers/Makefile`
- Create: `perfect-numbers/install_deps.sh`
- Create: `perfect-numbers/CLAUDE.md`
- Create: `perfect-numbers/README.md`

### Step 1 — Create Makefile

```makefile
.PHONY: run lint test coverage clean

run:
	python3 perfect_numbers.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_perfect_numbers -v

coverage:
	python3 -m coverage run -m unittest test_perfect_numbers
	python3 -m coverage report

clean:
	rm -rf __pycache__ .coverage
```

### Step 2 — Create install_deps.sh

```bash
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
python3 -m pip install --upgrade ruff coverage

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
```

```bash
chmod +x perfect-numbers/install_deps.sh
```

### Step 3 — Create CLAUDE.md

Create `perfect-numbers/CLAUDE.md` with the project overview, function list, testing section (use `make coverage` output for current % and test class table), and editing guidance. Model it after `fib/CLAUDE.md`.

Key sections to include:

- Repository overview (links to perfect-numbers-rs)
- Running the script (`make run/lint/test/coverage`)
- Code layout (all 6 functions with signatures)
- Important behavior (N range 1–54, algorithm, output file naming)
- Testing (test class table)
- Keeping this file up to date

### Step 4 — Create README.md

One-sentence description plus the same make target table as the project CLAUDE.md.

### Step 5 — Run make test to verify infrastructure

```bash
cd perfect-numbers && make test 2>&1 | tail -3
```

Expected: all tests pass via lint + unittest.

### Step 6 — Commit

```bash
cd perfect-numbers
git add Makefile install_deps.sh CLAUDE.md README.md
git commit -m "chore: perfect-numbers Python infrastructure — Makefile, install_deps.sh, CLAUDE.md, README.md

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Rust scaffolding + core functions

**Files:**

- Create: `perfect-numbers/perfect-numbers-rs/Cargo.toml`
- Create: `perfect-numbers/perfect-numbers-rs/rustfmt.toml`
- Create: `perfect-numbers/perfect-numbers-rs/Makefile`
- Create: `perfect-numbers/perfect-numbers-rs/install_deps.sh`
- Create: `perfect-numbers/perfect-numbers-rs/src/main.rs` (skeleton + core functions)

### Step 1 — Create Cargo.toml

```toml
[package]
name = "perfect-numbers"
version = "0.1.0"
edition = "2021"
description = "Find all perfect numbers up to 10^N via Lucas-Lehmer + sigma verification"

[[bin]]
name = "perfect-numbers"
path = "src/main.rs"

[dependencies]
rug = { version = "1", features = ["integer"] }
clap = { version = "4", features = ["derive"] }

[dev-dependencies]
tempfile = "3"

[lints.rust]
unexpected_cfgs = { level = "warn", check-cfg = ['cfg(tarpaulin_include)'] }

[profile.release]
opt-level     = 3
lto           = "thin"
codegen-units = 1
```

### Step 2 — Create rustfmt.toml

```toml
use_small_heuristics = "Max"
```

### Step 3 — Create Makefile

```makefile
.PHONY: perfect-numbers lint test clean

perfect-numbers:
	cargo build --release

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

clean:
	cargo clean
```

### Step 4 — Create install_deps.sh

Copy from `fib/fib-rs/install_deps.sh` — it installs GMP + Rust toolchain + cargo-tarpaulin, which is exactly what perfect-numbers-rs needs. Change the description header to reference perfect-numbers.

### Step 5 — Create src/main.rs skeleton with core functions and unit tests

Create `perfect-numbers/perfect-numbers-rs/src/main.rs`:

```rust
/*!
Find all perfect numbers up to 10^N.

Uses the Lucas-Lehmer primality test to find Mersenne primes, constructs
perfect numbers of the form 2^(p-1) * (2^p - 1), and verifies each with
the multiplicative sigma formula: sigma(n) = (2^p - 1) * 2^p = 2n.
*/

use std::io::{self, BufRead, Write};
use std::path::Path;

use clap::Parser;
use rug::ops::PowAssign;
use rug::Integer;

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

#[derive(Parser)]
#[command(
    name = "perfect-numbers",
    about = "Find all perfect numbers up to 10^N",
    long_about = "Find all perfect numbers up to 10^N.\n\n\
                  Uses Lucas-Lehmer to find Mersenne primes and the sigma formula\n\
                  to verify perfect-ness. Valid N range: 1-54.\n\n\
                  Run without arguments for interactive prompts."
)]
struct Cli {
    /// N: finds perfect numbers up to 10^N (1-54)
    exponent: Option<u32>,
}

// ---------------------------------------------------------------------------
// Core algorithm
// ---------------------------------------------------------------------------

fn is_prime(n: u64) -> bool {
    if n < 2 { return false; }
    if n == 2 { return true; }
    if n % 2 == 0 { return false; }
    let mut i = 3u64;
    while i * i <= n {
        if n % i == 0 { return false; }
        i += 2;
    }
    true
}

fn lucas_lehmer(p: u64) -> bool {
    if p == 2 { return true; }
    let mut mp = Integer::from(1u32);
    mp <<= p as u32;
    mp -= 1u32;

    let mut s = Integer::from(4u32);
    for _ in 0..(p - 2) {
        s.square_mut();
        s -= 2i32;
        s %= &mp;
        if s < 0i32 { s += &mp; }
    }
    s == 0u32
}

fn verify_perfect(p: u64) -> bool {
    let mut mp = Integer::from(1u32);
    mp <<= p as u32;
    mp -= 1u32;

    let mut n = Integer::from(1u32);
    n <<= (p - 1) as u32;
    n *= &mp;

    // sigma(n) = mp * (mp + 1) = (2^p - 1) * 2^p
    let sigma = Integer::from(&mp * Integer::from(&mp + 1u32));
    sigma == n << 1u32
}

fn generate_perfect_numbers(limit: &Integer) -> Vec<(u64, Integer)> {
    let mut results = Vec::new();
    if limit < &Integer::from(6u32) {
        return results;
    }
    let max_p = (limit.significant_bits() as u64 / 2) + 3;
    for p in 2..=max_p {
        if !is_prime(p) { continue; }
        if !lucas_lehmer(p) { continue; }
        let mut mp = Integer::from(1u32);
        mp <<= p as u32;
        mp -= 1u32;
        let mut pn = Integer::from(1u32);
        pn <<= (p - 1) as u32;
        pn *= &mp;
        if &pn > limit { break; }
        results.push((p, pn));
    }
    results
}

// ---------------------------------------------------------------------------
// I/O helpers
// ---------------------------------------------------------------------------

fn read_line_from<R: BufRead>(reader: &mut R) -> io::Result<String> {
    let mut line = String::new();
    reader.read_line(&mut line)?;
    Ok(line.trim().to_string())
}

fn prompt_n_with<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    _err: &mut E,
) -> io::Result<u64> {
    loop {
        write!(out, "Enter N (finds perfect numbers up to 10^N, max 54): ")?;
        out.flush()?;
        match read_line_from(reader)?.parse::<u64>() {
            Ok(v) if (1..=54).contains(&v) => return Ok(v),
            _ => writeln!(out, "N must be between 1 and 54.")?,
        }
    }
}

// ---------------------------------------------------------------------------
// Orchestration
// ---------------------------------------------------------------------------

fn run<R: BufRead, W: Write, E: Write>(
    cli: Cli,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    dir: &Path,
) -> io::Result<i32> {
    writeln!(out, "Perfect Number Finder (Rust)")?;
    writeln!(out, "{}", "=".repeat(40))?;

    let n: u64 = match cli.exponent {
        Some(v) => {
            if !(1..=54).contains(&v) {
                writeln!(err, "Error: N must be between 1 and 54.")?;
                return Ok(1);
            }
            v as u64
        }
        None => prompt_n_with(reader, out, err)?,
    };

    let mut limit = Integer::from(10u32);
    limit.pow_assign(n as u32);

    writeln!(out, "Finding perfect numbers up to 10^{}", n)?;
    writeln!(out)?;

    let max_p = (limit.significant_bits() as u64 / 2) + 3;
    let mut results: Vec<Integer> = Vec::new();

    for p in 2..=max_p {
        if !is_prime(p) { continue; }
        let mut mp = Integer::from(1u32);
        mp <<= p as u32;
        mp -= 1u32;
        if !lucas_lehmer(p) {
            writeln!(out, "p={}: M_{}={} [not prime]", p, p, mp)?;
            continue;
        }
        let mut pn = Integer::from(1u32);
        pn <<= (p - 1) as u32;
        pn *= &mp;
        let pn_str = pn.to_string_radix(10);
        let digits = pn_str.len();
        let s = if digits == 1 { "digit" } else { "digits" };
        if pn > limit {
            writeln!(out, "p={}: M_{}={} [Mersenne prime] -> {} ({} {}, exceeds limit)",
                p, p, mp, pn_str, digits, s)?;
            break;
        }
        let verified = verify_perfect(p);
        writeln!(out, "p={}: M_{}={} [Mersenne prime] -> {} ({} {}, {})",
            p, p, mp, pn_str, digits, s,
            if verified { "verified" } else { "FAILED" })?;
        results.push(pn);
    }

    let count = results.len();
    writeln!(out)?;
    let s = if count == 1 { "number" } else { "numbers" };
    writeln!(out, "Found {} perfect {} up to 10^{}", count, s, n)?;

    let path = dir.join(format!("perfect-numbers_1e{}.txt", n));
    let mut file = std::fs::File::create(&path)?;
    for pn in &results {
        writeln!(file, "{}", pn.to_string_radix(10))?;
    }
    writeln!(out, "Saved to {}", path.display())?;

    Ok(0)
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

#[cfg(not(tarpaulin_include))]
fn main() {
    let cli = Cli::parse();
    let stdin = io::stdin();
    let stdout = io::stdout();
    let stderr = io::stderr();
    let mut reader = stdin.lock();
    let mut out = stdout.lock();
    let mut err = stderr.lock();
    let cwd = std::env::current_dir().expect("cwd unavailable");
    let code = run(cli, &mut reader, &mut out, &mut err, &cwd).expect("io error");
    std::process::exit(code);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    use tempfile::tempdir;

    struct FailWriter;
    impl Write for FailWriter {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::other("injected write failure"))
        }
        fn flush(&mut self) -> io::Result<()> { Ok(()) }
    }

    // --- is_prime ---
    #[test]
    fn test_is_prime_zero() { assert!(!is_prime(0)); }
    #[test]
    fn test_is_prime_one() { assert!(!is_prime(1)); }
    #[test]
    fn test_is_prime_two() { assert!(is_prime(2)); }
    #[test]
    fn test_is_prime_four() { assert!(!is_prime(4)); }
    #[test]
    fn test_is_prime_small_primes() {
        for p in [3u64, 5, 7, 11, 13, 17, 19, 23, 29, 31, 89] {
            assert!(is_prime(p), "{p} should be prime");
        }
    }
    #[test]
    fn test_is_prime_composites() {
        for n in [4u64, 6, 9, 15, 25, 91] {
            assert!(!is_prime(n), "{n} should be composite");
        }
    }

    // --- lucas_lehmer ---
    #[test]
    fn test_lucas_lehmer_known_mersenne_primes() {
        for p in [2u64, 3, 5, 7, 13, 17, 19, 31, 61, 89] {
            assert!(lucas_lehmer(p), "p={p} should be Mersenne prime");
        }
    }
    #[test]
    fn test_lucas_lehmer_known_failures() {
        for p in [11u64, 23, 29, 37, 41] {
            assert!(!lucas_lehmer(p), "p={p} should not be Mersenne prime");
        }
    }

    // --- verify_perfect ---
    #[test]
    fn test_verify_perfect_known_exponents() {
        for p in [2u64, 3, 5, 7, 13, 17, 19] {
            assert!(verify_perfect(p), "p={p} should verify as perfect");
        }
    }

    // --- generate_perfect_numbers ---
    #[test]
    fn test_generate_limit_5_empty() {
        assert!(generate_perfect_numbers(&Integer::from(5u32)).is_empty());
    }
    #[test]
    fn test_generate_limit_10_yields_6() {
        let result = generate_perfect_numbers(&Integer::from(10u32));
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].0, 2);
        assert_eq!(result[0].1, Integer::from(6u32));
    }
    #[test]
    fn test_generate_limit_10000_yields_4() {
        let result = generate_perfect_numbers(&Integer::from(10000u32));
        assert_eq!(result.len(), 4);
        assert_eq!(result[3].0, 7u64);
    }
    #[test]
    fn test_generate_limit_n54_yields_10() {
        let mut limit = Integer::from(10u32);
        limit.pow_assign(54u32);
        let result = generate_perfect_numbers(&limit);
        assert_eq!(result.len(), 10);
        assert_eq!(result[9].0, 89u64);
    }

    // --- run ---
    #[test]
    fn test_run_n0_returns_1() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(0) }, &mut reader, &mut out, &mut err_buf, dir.path()).unwrap();
        assert_eq!(code, 1);
        assert!(String::from_utf8_lossy(&err_buf).contains("between 1 and 54"));
    }
    #[test]
    fn test_run_n55_returns_1() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(55) }, &mut reader, &mut out, &mut err_buf, dir.path()).unwrap();
        assert_eq!(code, 1);
    }
    #[test]
    fn test_run_n1_creates_file_with_6() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(1) }, &mut reader, &mut out, &mut err_buf, dir.path()).unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("perfect-numbers_1e1.txt");
        assert!(path.exists());
        assert_eq!(std::fs::read_to_string(&path).unwrap().trim(), "6");
    }
    #[test]
    fn test_run_no_arg_prompts() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("1\n");
        let code = run(Cli { exponent: None }, &mut reader, &mut out, &mut err_buf, dir.path()).unwrap();
        assert_eq!(code, 0);
        assert!(String::from_utf8_lossy(&out).contains("Enter N"));
    }

    // --- injection tests ---
    #[test]
    fn run_returns_err_on_stdout_failure() {
        let dir = tempdir().unwrap();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let result = run(Cli { exponent: Some(1) }, &mut reader, &mut FailWriter, &mut err_buf, dir.path());
        assert!(result.is_err());
    }
    #[test]
    fn run_returns_err_on_stderr_failure() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut reader = Cursor::new("");
        let result = run(Cli { exponent: Some(0) }, &mut reader, &mut out, &mut FailWriter, dir.path());
        assert!(result.is_err());
    }
}
```

### Step 6 — Run Rust tests

```bash
cd perfect-numbers/perfect-numbers-rs
make test 2>&1 | tail -5
```

Expected: all tests pass, lint clean. If tarpaulin is installed locally: `cargo tarpaulin --fail-under 90`.

### Step 7 — Commit

```bash
cd perfect-numbers/perfect-numbers-rs
git add Cargo.toml rustfmt.toml Makefile install_deps.sh src/main.rs
git commit -m "feat: perfect-numbers-rs — core algorithm, run(), CLI, unit tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Rust integration tests + CLAUDE.md

**Files:**

- Create: `perfect-numbers/perfect-numbers-rs/tests/cli.rs`
- Create: `perfect-numbers/perfect-numbers-rs/CLAUDE.md`

### Step 1 — Create tests/cli.rs

```rust
use std::io::Write;
use std::process::{Command, Stdio};
use tempfile::tempdir;

fn bin() -> &'static str {
    env!("CARGO_BIN_EXE_perfect-numbers")
}

#[test]
fn cli_arg_zero_exits_one() {
    let dir = tempdir().unwrap();
    let output = Command::new(bin())
        .arg("0")
        .current_dir(dir.path())
        .stdin(Stdio::null())
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("between 1 and 54"), "stderr: {stderr}");
}

#[test]
fn cli_arg_one_creates_file_with_6() {
    let dir = tempdir().unwrap();
    let output = Command::new(bin())
        .arg("1")
        .current_dir(dir.path())
        .stdin(Stdio::null())
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(0));
    let path = dir.path().join("perfect-numbers_1e1.txt");
    assert!(path.exists(), "expected file to exist");
    assert_eq!(std::fs::read_to_string(&path).unwrap().trim(), "6");
}

#[test]
fn cli_no_arg_prompts_then_creates_file() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(bin())
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.as_mut().unwrap().write_all(b"1\n").unwrap();
    let output = child.wait_with_output().unwrap();
    assert_eq!(output.status.code(), Some(0));
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Enter N"), "stdout: {stdout}");
    assert!(dir.path().join("perfect-numbers_1e1.txt").exists());
}

#[cfg(unix)]
#[test]
fn cli_unwritable_output_dir() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempdir().unwrap();
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o555)).unwrap();
    let output = Command::new(bin())
        .arg("1")
        .current_dir(dir.path())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .unwrap();
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o755)).unwrap();
    assert_ne!(
        output.status.code().unwrap_or(0),
        0,
        "expected non-zero exit for unwritable directory"
    );
}
```

### Step 2 — Run full Rust test suite

```bash
cd perfect-numbers/perfect-numbers-rs
make test 2>&1 | tail -10
```

Expected: unit tests + integration tests all pass. Total test count increases by 4 (integration tests).

### Step 3 — Create CLAUDE.md

Create `perfect-numbers/perfect-numbers-rs/CLAUDE.md` following the same structure as `fib/fib-rs/CLAUDE.md`. Key sections:

- Build instructions (`make perfect-numbers`, `make lint`, `make test`)
- Code layout (all functions with signatures and descriptions)
- Testing (coverage %, test table with unit + integration tests)
- Keeping this file up to date

### Step 4 — Commit

```bash
cd perfect-numbers/perfect-numbers-rs
git add tests/cli.rs CLAUDE.md
git commit -m "test: perfect-numbers-rs integration tests + CLAUDE.md

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: CI workflows

**Files:**

- Create: `.github/workflows/perfect-numbers-py.yml`
- Create: `.github/workflows/perfect-numbers-rs.yml`

### Step 1 — Create perfect-numbers-py.yml

```yaml
name: perfect-numbers.py

on:
  pull_request:
    branches:
      - master
    paths:
      - "perfect-numbers/*.py"
      - "perfect-numbers/install_deps.sh"
      - "perfect-numbers/Makefile"
      - ".github/workflows/perfect-numbers-py.yml"

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  test:
    name: Test perfect-numbers.py
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: perfect-numbers
    steps:
      - uses: actions/checkout@v5

      - name: Install Python dependencies
        run: pip install ruff coverage

      - name: Run tests
        run: make test
```

### Step 2 — Create perfect-numbers-rs.yml

```yaml
name: perfect-numbers-rs

on:
  pull_request:
    branches:
      - master
    paths:
      - "perfect-numbers/perfect-numbers-rs/**"
      - ".github/workflows/perfect-numbers-rs.yml"

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  test:
    name: Test perfect-numbers-rs
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: perfect-numbers/perfect-numbers-rs
    steps:
      - uses: actions/checkout@v5

      - name: Install GMP
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: perfect-numbers/perfect-numbers-rs

      - name: Run tests
        run: make test

      - name: Install cargo-tarpaulin
        run: cargo install cargo-tarpaulin --locked

      - name: Check coverage (>=90%)
        run: cargo tarpaulin --fail-under 90

  build:
    name: Build perfect-numbers-rs
    runs-on: ubuntu-latest
    needs: [test]
    defaults:
      run:
        working-directory: perfect-numbers/perfect-numbers-rs
    steps:
      - uses: actions/checkout@v5

      - name: Install GMP
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: perfect-numbers/perfect-numbers-rs

      - name: Build
        run: cargo build --release

      - name: Upload artifact
        uses: actions/upload-artifact@v7
        with:
          name: perfect-numbers
          path: perfect-numbers/perfect-numbers-rs/target/release/perfect-numbers
          retention-days: 7
```

### Step 3 — Commit

```bash
git add .github/workflows/perfect-numbers-py.yml .github/workflows/perfect-numbers-rs.yml
git commit -m "ci: add perfect-numbers-py and perfect-numbers-rs workflows

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Hook updates + docs

**Files:**

- Modify: `scripts/pre-commit`
- Modify: `scripts/pre-push`
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `docs/superpowers/README.md`
- Modify: `docs/cursor/README.md`

### Step 1 — Update scripts/pre-commit

In `scripts/pre-commit`, find the line:

```bash
for dir in pi pi/pi-rs prime/prime-rs fib fib/fib-rs sq sq/sq-rs twin-primes/twin-primes-rs e e/e-rs factorial factorial/factorial-rs; do
```

Replace with:

```bash
for dir in pi pi/pi-rs prime/prime-rs fib fib/fib-rs sq sq/sq-rs twin-primes/twin-primes-rs e e/e-rs factorial factorial/factorial-rs perfect-numbers perfect-numbers/perfect-numbers-rs; do
```

### Step 2 — Update scripts/pre-push

In `scripts/pre-push`, find the same loop line and replace with:

```bash
for dir in pi pi/pi-rs prime/prime-rs fib fib/fib-rs sq sq/sq-rs twin-primes/twin-primes-rs e e/e-rs factorial factorial/factorial-rs perfect-numbers perfect-numbers/perfect-numbers-rs; do
```

### Step 3 — Reinstall hooks

```bash
make install-hooks
```

### Step 4 — Update top-level CLAUDE.md

Add `perfect-numbers/` row to the Repository Overview table:

```markdown
| [`perfect-numbers/`](perfect-numbers/) | Python + Rust | Find all perfect numbers up to 10^N (Lucas-Lehmer + sigma) | [`perfect-numbers/CLAUDE.md`](perfect-numbers/CLAUDE.md) |
```

Add to Dependency Installation table:

```markdown
| `perfect-numbers/install_deps.sh` | `ruff`, `coverage` |
| `perfect-numbers/perfect-numbers-rs/install_deps.sh` | GMP, Rust toolchain, `cargo-tarpaulin` |
```

Add to Quick Reference (Python and Rust sections).

Add to CI table:

```markdown
| perfect-numbers.py | `.github/workflows/perfect-numbers-py.yml` | test |
| perfect-numbers-rs | `.github/workflows/perfect-numbers-rs.yml` | test → build + artifact |
```

### Step 5 — Update README.md

Add two CI badges at the top (following existing badge pattern):

```markdown
[![perfect-numbers.py](https://github.com/brujack/math/actions/workflows/perfect-numbers-py.yml/badge.svg?event=pull_request)](https://github.com/brujack/math/actions/workflows/perfect-numbers-py.yml)
[![perfect-numbers-rs](https://github.com/brujack/math/actions/workflows/perfect-numbers-rs.yml/badge.svg?event=pull_request)](https://github.com/brujack/math/actions/workflows/perfect-numbers-rs.yml)
```

Add `perfect-numbers/` row to the project table in README.md.

### Step 6 — Update docs indexes

In `docs/superpowers/README.md`, update the perfect-numbers row:

```markdown
| 2026-05-11 | [perfect-numbers](plans/2026-05-11-perfect-numbers.md) | [spec](specs/2026-05-11-perfect-numbers-design.md) | In Progress |
```

Do the same in `docs/cursor/README.md`.

### Step 7 — Commit

```bash
git add scripts/pre-commit scripts/pre-push CLAUDE.md README.md \
        docs/superpowers/README.md docs/cursor/README.md \
        docs/superpowers/plans/2026-05-11-perfect-numbers.md
git commit -m "chore: wire perfect-numbers into hooks, docs, and plan index

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```
