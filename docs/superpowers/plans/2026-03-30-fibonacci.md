# Fibonacci Project Implementation Plan

> **Status: DONE** — Implemented 2026-03-30. fib/ directory with Python and Rust implementations on master.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `fib/` project that generates all Fibonacci numbers with at most 10^X decimal digits, with Python (`fib.py`) and Rust (`fib-rs/`) implementations, following the existing `pi/` and `prime/` patterns.

**Architecture:** Simple iterative generation (`a, b = b, a+b`), stopping when `b >= 10^max_digits`. Python uses built-in arbitrary-precision integers. Rust uses `rug::Integer` (GMP), same library already installed for `pi-rs`. Both follow the prime-rs UX pattern: optional CLI arg, interactive fallback, large-output warning for X ≥ 4, stream to file for X ≥ 3.

**Tech Stack:** Python 3 (stdlib only), Rust + `rug` (GMP integer feature) + `clap`, GitHub Actions (Node.js 24), `ruff`, `cargo-tarpaulin`

---

## File Map

**Create:**

- `fib/Makefile`
- `fib/install_deps.sh`
- `fib/fib.py`
- `fib/test_fib.py`
- `fib/fib-rs/Cargo.toml`
- `fib/fib-rs/src/main.rs`
- `fib/fib-rs/Makefile`
- `fib/fib-rs/install_deps.sh`
- `fib/CLAUDE.md`
- `fib/README.md`
- `fib/fib-rs/CLAUDE.md`
- `.github/workflows/fib-py.yml`
- `.github/workflows/fib-rs.yml`
- `.gitignore`

**Modify:**

- `CLAUDE.md` (top-level) — add fib row to project table and quick reference
- `README.md` (top-level) — add fib row, two badges

---

## Task 1: Python scaffolding — Makefile and install_deps.sh

**Files:**

- Create: `fib/Makefile`
- Create: `fib/install_deps.sh`

- [ ] **Step 1: Create fib/ directory and Makefile**

```makefile
# fib/Makefile
.PHONY: run lint test coverage clean

run:
	python3 fib.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_fib -v

coverage:
	python3 -m coverage run -m unittest test_fib
	python3 -m coverage report

clean:
	rm -rf __pycache__ .coverage
```

- [ ] **Step 2: Create fib/install_deps.sh**

```bash
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
echo "  make run       — run the generator"
echo "  make test      — run unit tests"
echo "  make coverage  — run tests with coverage report"
```

- [ ] **Step 3: Make install_deps.sh executable**

```bash
chmod +x fib/install_deps.sh
```

- [ ] **Step 4: Commit**

```bash
git add fib/Makefile fib/install_deps.sh
git commit -m "feat: add fib Python project scaffolding (Makefile, install_deps.sh)"
```

---

## Task 2: Python — write failing tests

**Files:**

- Create: `fib/test_fib.py`

- [ ] **Step 1: Write test_fib.py**

```python
#!/usr/bin/env python3
"""Unit tests for fib.py."""

import argparse
import sys
import unittest

from fib import generate_fibonacci, parse_args, get_exponent


class TestGenerateFibonacci(unittest.TestCase):

    def test_single_digit_sequence(self):
        # max_digits=1, limit=10^1=10: yields 1,1,2,3,5,8 (all < 10); 13 >= 10 stops
        result = list(generate_fibonacci(1))
        self.assertEqual(result, [1, 1, 2, 3, 5, 8])

    def test_count_single_digit(self):
        self.assertEqual(len(list(generate_fibonacci(1))), 6)

    def test_count_two_digits(self):
        # max_digits=2, limit=100: 1,1,2,3,5,8,13,21,34,55,89 (11 total); 144 >= 100 stops
        self.assertEqual(len(list(generate_fibonacci(2))), 11)

    def test_last_two_digit_value(self):
        result = list(generate_fibonacci(2))
        self.assertEqual(result[-1], 89)

    def test_three_digit_excluded(self):
        result = list(generate_fibonacci(2))
        self.assertNotIn(144, result)

    def test_each_is_sum_of_previous_two(self):
        result = list(generate_fibonacci(3))
        for i in range(2, len(result)):
            self.assertEqual(result[i], result[i - 1] + result[i - 2])

    def test_all_positive(self):
        result = list(generate_fibonacci(2))
        self.assertTrue(all(n > 0 for n in result))

    def test_known_first_ten_values(self):
        result = list(generate_fibonacci(2))
        self.assertEqual(result[:10], [1, 1, 2, 3, 5, 8, 13, 21, 34, 55])


class TestParseArgs(unittest.TestCase):

    def test_no_args(self):
        old_argv = sys.argv
        sys.argv = ["fib.py"]
        args = parse_args()
        sys.argv = old_argv
        self.assertIsNone(args.exponent)

    def test_with_valid_arg(self):
        old_argv = sys.argv
        sys.argv = ["fib.py", "3"]
        args = parse_args()
        sys.argv = old_argv
        self.assertEqual(args.exponent, 3)


class TestGetExponent(unittest.TestCase):

    def _args(self, exponent):
        return argparse.Namespace(exponent=exponent)

    def test_valid_low_boundary(self):
        self.assertEqual(get_exponent(self._args(1)), 1)

    def test_valid_high_boundary(self):
        self.assertEqual(get_exponent(self._args(5)), 5)

    def test_valid_midrange(self):
        self.assertEqual(get_exponent(self._args(3)), 3)

    def test_zero_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._args(0))

    def test_too_high_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._args(6))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to confirm they fail (fib.py does not exist yet)**

```bash
cd fib
python3 -m unittest test_fib -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'fib'`

- [ ] **Step 3: Commit**

```bash
git add fib/test_fib.py
git commit -m "test: add failing tests for fib Python implementation"
```

---

## Task 3: Python — implement fib.py and pass tests

**Files:**

- Create: `fib/fib.py`

- [ ] **Step 1: Write fib.py**

```python
#!/usr/bin/env python3
"""
Generate all Fibonacci numbers with at most 10^X decimal digits.

Uses Python built-in arbitrary-precision integers — no external libraries needed.

Run without arguments for an interactive prompt, or supply X directly:
    python3 fib.py [X]
"""

import argparse
import io
import sys


def generate_fibonacci(max_digits: int):
    """Yield every Fibonacci number with at most max_digits decimal digits.

    Uses b < 10^max_digits as the stopping criterion (equivalent to
    len(str(b)) <= max_digits and avoids per-iteration string conversion).
    """
    limit = 10 ** max_digits
    a, b = 0, 1
    while b < limit:
        yield b
        a, b = b, a + b


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate all Fibonacci numbers with up to 10^X digits",
        epilog="Run without arguments for an interactive prompt.",
    )
    parser.add_argument(
        "exponent",
        type=int,
        nargs="?",
        help="X: generates Fibonacci numbers with up to 10^X digits (e.g. 3 → up to 1,000 digits)",
    )
    return parser.parse_args()


def get_exponent(args: argparse.Namespace) -> int:
    """Return the validated exponent from CLI args, or prompt interactively."""
    if args.exponent is not None:
        x = args.exponent
        if x < 1 or x > 5:
            print("Error: X must be between 1 and 5.", file=sys.stderr)
            sys.exit(1)
        return x
    while True:
        try:
            raw = input(
                "Enter X (finds all Fibonacci numbers with up to 10^X digits, max 5): "
            )
            x = int(raw)
            if 1 <= x <= 5:
                return x
            print("X must be between 1 and 5.")
        except ValueError:
            print("Please enter a positive integer.")


def main() -> None:
    args = parse_args()
    x = get_exponent(args)
    max_digits = 10 ** x

    print("Fibonacci Number Generator (Python)")
    print("=" * 40)

    if x >= 4:
        print(
            f"Warning: X={x} means Fibonacci numbers with up to {max_digits:,} digits "
            f"— this may take a long time"
        )
        print("         and produce a very large output file.")
        answer = input("Continue? (y/n): ").strip().lower()
        if answer not in ("y", "yes"):
            return

    print(
        f"Generating all Fibonacci numbers with up to 10^{x} = {max_digits:,} digits"
    )

    if x <= 2:
        # Small result: buffer in memory, let user choose to display or save.
        buf = io.StringIO()
        count = 0
        for fib in generate_fibonacci(max_digits):
            buf.write(str(fib))
            buf.write("\n")
            count += 1

        print(f"\nFound {count:,} Fibonacci numbers with up to 10^{x} digits")
        answer = input(
            f"Display all {count:,} Fibonacci numbers? (y/n): "
        ).strip().lower()
        if answer in ("y", "yes"):
            print(buf.getvalue(), end="")
        else:
            filename = f"fib_1e{x}.txt"
            with open(filename, "w") as f:
                f.write(buf.getvalue())
            print(f"Saved to {filename}")
    else:
        # Large result: stream directly to file.
        filename = f"fib_1e{x}.txt"
        print(f"\nSaving to {filename}...")
        count = 0
        with open(filename, "w", buffering=8 * 1024 * 1024) as f:
            for fib in generate_fibonacci(max_digits):
                f.write(str(fib))
                f.write("\n")
                count += 1

        print(f"Found {count:,} Fibonacci numbers with up to 10^{x} digits")
        print(f"Saved to {filename}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run lint**

```bash
cd fib
python3 -m ruff check .
```

Expected: no output (clean).

- [ ] **Step 3: Run tests**

```bash
cd fib
python3 -m unittest test_fib -v
```

Expected: all tests pass, output ends with `OK`.

- [ ] **Step 4: Commit**

```bash
git add fib/fib.py
git commit -m "feat: implement fib.py — generate all Fibonacci numbers up to 10^X digits"
```

---

## Task 4: Rust scaffolding — Cargo.toml and stub main.rs with failing tests

**Files:**

- Create: `fib/fib-rs/Cargo.toml`
- Create: `fib/fib-rs/src/main.rs` (stubs + tests)

- [ ] **Step 1: Create Cargo.toml**

```toml
[package]
name = "fib"
version = "0.1.0"
edition = "2021"
description = "Fibonacci sequence generator — all F(n) with up to 10^X decimal digits"

[[bin]]
name = "fib"
path = "src/main.rs"

[dependencies]
# rug wraps GMP for arbitrary-precision integers.
# Same C library already installed for pi-rs — no new system deps needed.
rug = { version = "1", features = ["integer"] }

# CLI argument parsing (same as prime-rs).
clap = { version = "4", features = ["derive"] }

[profile.release]
opt-level     = 3
lto           = "thin"
codegen-units = 1
```

- [ ] **Step 2: Create src/main.rs with stubs and tests**

Note the stubs return wrong values so the tests will fail at runtime (not compile time).

```rust
use std::io::{self, BufRead, BufWriter, Write};
use std::fs::File;
use std::time::Instant;

use clap::Parser;
use rug::Integer;

#[derive(Parser)]
#[command(
    name = "fib",
    about = "Generate all Fibonacci numbers with up to 10^X digits",
    long_about = "Generate all Fibonacci numbers whose decimal digit count is at most 10^X.\n\n\
                  Run without arguments for interactive prompts."
)]
struct Cli {
    /// X: generates Fibonacci numbers with up to 10^X digits (e.g. 3 → up to 1,000 digits)
    exponent: Option<u32>,
}

/// Stub: always returns 0 (tests will fail).
fn generate_fibonacci<W: Write>(_max_digits: usize, _out: &mut W) -> io::Result<u64> {
    Ok(0)
}

/// Stub: no comma formatting (tests will fail).
fn fmt_int(n: u64) -> String {
    n.to_string()
}

fn read_line() -> String {
    let stdin = io::stdin();
    let mut line = String::new();
    stdin.lock().read_line(&mut line).unwrap();
    line.trim().to_string()
}

fn prompt_exponent() -> u32 {
    loop {
        print!("Enter X (finds all Fibonacci numbers with up to 10^X digits, max 5): ");
        io::stdout().flush().unwrap();
        match read_line().parse::<u32>() {
            Ok(x) if x >= 1 && x <= 5 => return x,
            Ok(_) => eprintln!("X must be between 1 and 5."),
            _ => eprintln!("Please enter a positive integer."),
        }
    }
}

fn main() {
    let cli = Cli::parse();

    println!("Fibonacci Number Generator (Rust/GMP)");
    println!("{}", "=".repeat(40));

    let exponent = match cli.exponent {
        Some(x) => {
            if x < 1 || x > 5 {
                eprintln!("Error: X must be between 1 and 5.");
                std::process::exit(1);
            }
            x
        }
        None => prompt_exponent(),
    };

    let max_digits = 10usize.pow(exponent);

    if exponent >= 4 {
        eprintln!(
            "Warning: X={} means Fibonacci numbers with up to {} digits — this may take a long time",
            exponent,
            fmt_int(max_digits as u64)
        );
        eprintln!("         and produce a very large output file.");
        print!("Continue? (y/n): ");
        io::stdout().flush().unwrap();
        if !matches!(read_line().as_str(), "y" | "yes") {
            return;
        }
    }

    println!(
        "Generating all Fibonacci numbers with up to 10^{} = {} digits",
        exponent,
        fmt_int(max_digits as u64)
    );

    let t_total = Instant::now();

    if exponent <= 2 {
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_fibonacci(max_digits, &mut buf).expect("generation error");

        println!(
            "\nFound {} Fibonacci numbers with up to 10^{} digits",
            fmt_int(count),
            exponent
        );
        print!("Display all {} Fibonacci numbers? (y/n): ", fmt_int(count));
        io::stdout().flush().unwrap();
        if matches!(read_line().as_str(), "y" | "yes") {
            io::stdout().write_all(&buf).unwrap();
        } else {
            let filename = format!("fib_1e{}.txt", exponent);
            std::fs::write(&filename, &buf).expect("file write failed");
            println!("Saved to {}", filename);
        }
    } else {
        let filename = format!("fib_1e{}.txt", exponent);
        println!("\nSaving to {}...", filename);
        let file = File::create(&filename).expect("cannot create output file");
        let mut writer = BufWriter::with_capacity(8 * 1024 * 1024, file);
        let count = generate_fibonacci(max_digits, &mut writer).expect("generation error");
        writer.flush().expect("flush error");

        println!(
            "Found {} Fibonacci numbers with up to 10^{} digits",
            fmt_int(count),
            exponent
        );
        println!("Saved to {}", filename);
    }

    println!("Total time: {:.2}s", t_total.elapsed().as_secs_f64());
}

#[cfg(test)]
mod tests {
    use super::*;

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
    }

    #[test]
    fn test_fmt_int_millions() {
        assert_eq!(fmt_int(1_234_567), "1,234,567");
    }

    // --- generate_fibonacci ---

    #[test]
    fn test_single_digit_sequence() {
        // max_digits=1, limit=10: yields 1,1,2,3,5,8 then 13 >= 10 stops
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_fibonacci(1, &mut buf).unwrap();
        assert_eq!(count, 6);
        assert_eq!(String::from_utf8(buf).unwrap(), "1\n1\n2\n3\n5\n8\n");
    }

    #[test]
    fn test_two_digit_count() {
        // max_digits=2, limit=100: 11 numbers ending at 89, then 144 >= 100 stops
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_fibonacci(2, &mut buf).unwrap();
        assert_eq!(count, 11);
    }

    #[test]
    fn test_two_digit_last_value() {
        let mut buf: Vec<u8> = Vec::new();
        generate_fibonacci(2, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert_eq!(output.lines().last().unwrap(), "89");
    }

    #[test]
    fn test_known_first_ten_values() {
        // F: 1,1,2,3,5,8,13,21,34,55,...
        let mut buf: Vec<u8> = Vec::new();
        generate_fibonacci(2, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        let nums: Vec<u64> = output.lines().take(10).map(|l| l.parse().unwrap()).collect();
        assert_eq!(nums, vec![1, 1, 2, 3, 5, 8, 13, 21, 34, 55]);
    }

    #[test]
    fn test_each_is_sum_of_previous_two() {
        let mut buf: Vec<u8> = Vec::new();
        generate_fibonacci(3, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        // 3-digit numbers are small enough to parse as u64
        let nums: Vec<u64> = output.lines().map(|l| l.parse().unwrap()).collect();
        for i in 2..nums.len() {
            assert_eq!(nums[i], nums[i - 1] + nums[i - 2]);
        }
    }

    #[test]
    fn test_all_positive() {
        let mut buf: Vec<u8> = Vec::new();
        generate_fibonacci(2, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        for line in output.lines() {
            let n: u64 = line.parse().unwrap();
            assert!(n > 0);
        }
    }
}
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd fib/fib-rs
cargo test 2>&1 | tail -20
```

Expected: several test failures. `test_single_digit_sequence` fails because count is 0 not 6. `test_fmt_int_thousands` fails because "1000" != "1,000".

- [ ] **Step 4: Commit**

```bash
git add fib/fib-rs/Cargo.toml fib/fib-rs/src/main.rs
git commit -m "test: add failing Rust tests for fib-rs implementation"
```

---

## Task 5: Rust — implement generate_fibonacci and fmt_int, pass all tests

**Files:**

- Modify: `fib/fib-rs/src/main.rs`

Replace the two stub functions with real implementations. All other code in the file stays the same.

- [ ] **Step 1: Replace the stub generate_fibonacci**

Find this block in `fib/fib-rs/src/main.rs`:

```rust
/// Stub: always returns 0 (tests will fail).
fn generate_fibonacci<W: Write>(_max_digits: usize, _out: &mut W) -> io::Result<u64> {
    Ok(0)
}
```

Replace with:

```rust
/// Generate all Fibonacci numbers with at most max_digits decimal digits,
/// writing one number per line to `out`. Returns the total count.
///
/// Uses b < 10^max_digits as the stopping criterion. The limit is computed
/// once with GMP — cheaper than converting b to a decimal string each iteration.
fn generate_fibonacci<W: Write>(max_digits: usize, out: &mut W) -> io::Result<u64> {
    // limit = 10^max_digits; stop when b >= limit (b would have > max_digits digits)
    let mut limit = Integer::from(10u32);
    limit.pow_assign(max_digits as u32);

    let mut a = Integer::from(0u32);
    let mut b = Integer::from(1u32);
    let mut count = 0u64;

    while b < limit {
        writeln!(out, "{}", b)?;
        count += 1;
        // rug lazy arithmetic: wrap Integer::from() around incomplete expressions
        let next = Integer::from(&a + &b);
        a = b;
        b = next;
    }

    Ok(count)
}
```

- [ ] **Step 2: Replace the stub fmt_int**

Find this block:

```rust
/// Stub: no comma formatting (tests will fail).
fn fmt_int(n: u64) -> String {
    n.to_string()
}
```

Replace with:

```rust
fn fmt_int(n: u64) -> String {
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

- [ ] **Step 3: Run clippy**

```bash
cd fib/fib-rs
cargo clippy -- -D warnings
```

Expected: no warnings.

- [ ] **Step 4: Run tests**

```bash
cd fib/fib-rs
cargo test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add fib/fib-rs/src/main.rs
git commit -m "feat: implement fib-rs — generate all Fibonacci numbers up to 10^X digits via GMP"
```

---

## Task 6: Rust support files — Makefile and install_deps.sh

**Files:**

- Create: `fib/fib-rs/Makefile`
- Create: `fib/fib-rs/install_deps.sh`

- [ ] **Step 1: Create fib/fib-rs/Makefile**

```makefile
.PHONY: fib lint test clean

fib:
	cargo build --release
	cp target/release/fib ~/Downloads/fib

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/fib
```

- [ ] **Step 2: Create fib/fib-rs/install_deps.sh**

```bash
#!/usr/bin/env bash
# install_deps.sh — install dependencies for fib-rs
#
# Installs:
#   C libraries  — GMP (required by rug integer feature)
#   Rust         — rustup toolchain + cargo-tarpaulin (build, test, coverage)
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
    echo "==> Installing GMP via Homebrew..."
    brew install gmp
}

install_debian() {
    echo "==> Detected Debian / Ubuntu"
    echo "==> Installing GMP via apt..."
    sudo apt-get update -qq
    sudo apt-get install -y libgmp-dev
}

install_rhel() {
    echo "==> Detected RHEL / Fedora / CentOS"
    echo "==> Installing GMP via dnf (or yum)..."
    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y gmp-devel
    elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y gmp-devel
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

echo "=== fib-rs dependency installer ==="
echo ""

# ---- C library (GMP, required by rug integer feature) ----
case "${OS}" in
    Darwin)
        install_macos
        ;;
    Linux)
        if [[ -f /etc/debian_version ]]; then
            install_debian
        elif [[ -f /etc/redhat-release ]] || [[ -f /etc/fedora-release ]] || [[ -f /etc/centos-release ]]; then
            install_rhel
        else
            echo "Warning: unrecognised Linux distribution." >&2
            echo "Please install libgmp-dev (or equivalent) manually, then re-run." >&2
            exit 1
        fi
        ;;
    *)
        echo "Error: unsupported OS '${OS}'." >&2
        echo "Supported: macOS, Debian/Ubuntu, RHEL/Fedora/CentOS" >&2
        exit 1
        ;;
esac

# ---- Rust toolchain ----
echo ""
install_rust

# ---- cargo-tarpaulin ----
echo ""
install_cargo_tarpaulin

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

echo ""
echo "==> Verifying installation..."
echo "  rustc     $(rustc --version)  OK"
echo "  cargo     $(cargo --version)  OK"
echo "  tarpaulin $(cargo tarpaulin --version)  OK"

echo ""
echo "All dependencies installed successfully."
echo ""
echo "  make fib   — build release binary"
echo "  make test  — run unit tests"
```

- [ ] **Step 3: Make install_deps.sh executable**

```bash
chmod +x fib/fib-rs/install_deps.sh
```

- [ ] **Step 4: Verify make test still passes**

```bash
cd fib/fib-rs
make test
```

Expected: clippy clean, then all tests pass.

- [ ] **Step 5: Commit**

```bash
git add fib/fib-rs/Makefile fib/fib-rs/install_deps.sh
git commit -m "feat: add fib-rs Makefile and install_deps.sh"
```

---

## Task 7: CI workflows

**Files:**

- Create: `.github/workflows/fib-py.yml`
- Create: `.github/workflows/fib-rs.yml`

- [ ] **Step 1: Create fib-py.yml**

```yaml
name: fib.py

on:
  push:
    branches: [master]
  pull_request:
    branches: [master]

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  test:
    name: Test fib.py
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: fib
    steps:
      - uses: actions/checkout@v5

      - name: Install Python dependencies
        run: pip install ruff coverage

      - name: Run tests
        run: python3 -m unittest test_fib -v
```

- [ ] **Step 2: Create fib-rs.yml**

```yaml
name: fib-rs

on:
  push:
    branches: [master]
  pull_request:
    branches: [master]

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  test:
    name: Test fib-rs
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: fib/fib-rs
    steps:
      - uses: actions/checkout@v5

      - name: Install GMP
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: fib/fib-rs

      - name: Run tests
        run: cargo test

  build:
    name: Build fib-rs
    runs-on: ubuntu-latest
    needs: [test]
    defaults:
      run:
        working-directory: fib/fib-rs
    steps:
      - uses: actions/checkout@v5

      - name: Install GMP
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: fib/fib-rs

      - name: Build
        run: cargo build --release

      - name: Upload artifact
        uses: actions/upload-artifact@v5
        with:
          name: fib
          path: fib/fib-rs/target/release/fib
          retention-days: 7
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/fib-py.yml .github/workflows/fib-rs.yml
git commit -m "ci: add fib-py and fib-rs GitHub Actions workflows"
```

---

## Task 8: Documentation, CLAUDE.md files, and top-level updates

**Files:**

- Create: `fib/CLAUDE.md`
- Create: `fib/fib-rs/CLAUDE.md`
- Create: `fib/README.md`
- Create: `.gitignore`
- Modify: `CLAUDE.md` (top-level)
- Modify: `README.md` (top-level)

- [ ] **Step 1: Create fib/CLAUDE.md**

````markdown
# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This directory contains a Python CLI for generating all Fibonacci numbers with at most 10^X decimal digits.

Current structure:

- `fib.py` — interactive generator script (Python built-in integers, no external deps)
- `fib-rs/` — Rust implementation using rug/GMP for large digit counts
- `install_deps.sh` — installs ruff and coverage
- `test_fib.py` — unit tests

## Running the Script

```bash
make run       # python3 fib.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_fib -v
make coverage  # run tests and print coverage report
```
````

Or directly:

```bash
python3 fib.py        # interactive prompt
python3 fib.py 3      # generate Fibonacci numbers with up to 1,000 digits
```

## Code Layout

- `generate_fibonacci(max_digits)` — generator that yields every Fibonacci number with at most `max_digits` decimal digits. Uses `b < 10^max_digits` stopping criterion; limit precomputed once before the loop.
- `parse_args()` — parses CLI via `argparse`; returns `Namespace` with optional `exponent` int.
- `get_exponent(args)` — returns validated exponent from args, or prompts interactively. Valid range: 1–5. Calls `sys.exit(1)` for out-of-range CLI args.
- `main()` — top-level entry: parses args, validates, warns for X ≥ 4, buffers or streams output.

## Important Behavior

- **Small output (X ≤ 2):** result buffered in a `StringIO`, user prompted to display or save to `fib_1eX.txt`.
- **Large output (X ≥ 3):** streamed directly to `fib_1eX.txt` with 8 MB write buffer.
- **Large-N warning:** X ≥ 4 prints a warning and requires `y/yes` confirmation.
- **Stopping criterion:** `b < 10^max_digits` (precomputed once). Equivalent to `len(str(b)) <= max_digits` but avoids per-iteration string conversion.

## Testing

```bash
make test      # lint + unittest
make coverage  # coverage run + report
```

### Test coverage

| Class                   | Tests                                                      |
| ----------------------- | ---------------------------------------------------------- |
| `TestGenerateFibonacci` | 8 — sequence correctness, known values, Fibonacci property |
| `TestParseArgs`         | 2 — no-arg and with-arg CLI parsing                        |
| `TestGetExponent`       | 5 — boundary validation, sys.exit for out-of-range         |

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Add or remove a Makefile target → update Running section and `README.md`
- Change the valid exponent range or large-N threshold → update Important Behavior
- Add test classes or change coverage → update Testing table

````

- [ ] **Step 2: Create fib/fib-rs/CLAUDE.md**

```markdown
# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

Rust CLI for generating all Fibonacci numbers with at most 10^X decimal digits. Uses `rug::Integer` (wraps libGMP) for arbitrary-precision arithmetic.

Current structure:

- `src/main.rs` — full implementation + unit tests
- `Cargo.toml` — deps: rug (integer feature), clap
- `Makefile` — fib, lint, test, clean targets
- `install_deps.sh` — installs GMP, Rust toolchain, cargo-tarpaulin

## Build

```bash
cd fib/fib-rs
make fib       # cargo build --release, copies binary to ~/Downloads/fib
make lint      # cargo clippy -- -D warnings
make test      # lint, then cargo test
make clean     # cargo clean + remove ~/Downloads/fib
````

Or directly:

```bash
./target/release/fib        # interactive prompt
./target/release/fib 3      # generate Fibonacci numbers with up to 1,000 digits
```

## Code Layout (`src/main.rs`)

- `struct Cli` — clap derive struct; `exponent: Option<u32>` optional positional arg.
- `fn generate_fibonacci<W: Write>(max_digits, out)` — iterates `a, b = b, a+b` until `b >= 10^max_digits`. Precomputes limit with `Integer::pow_assign`. Returns total count.
- `fn fmt_int(n)` — formats `u64` with thousands separators (same as prime-rs).
- `fn read_line()` — reads one trimmed line from stdin.
- `fn prompt_exponent()` — interactive prompt loop; validates 1–5.
- `fn main()` — parses CLI, validates, warns for X ≥ 4, buffers (X ≤ 2) or streams (X ≥ 3) to `fib_1eX.txt`.

## rug Integer Arithmetic

`rug::Integer` operator overloading returns lazy "incomplete" types. Always wrap with `Integer::from(...)`:

```rust
// Correct:
let next = Integer::from(&a + &b);

// Wrong (will not compile — returns AddIncomplete, not Integer):
let next = &a + &b;
```

`pow_assign` raises in place:

```rust
let mut limit = Integer::from(10u32);
limit.pow_assign(max_digits as u32);
```

## Important Behavior

- **Small output (X ≤ 2):** buffered in `Vec<u8>`, user prompted to display or save to `fib_1eX.txt`.
- **Large output (X ≥ 3):** streamed to `fib_1eX.txt` via `BufWriter` (8 MB buffer).
- **Large-N warning:** X ≥ 4 warns and requires `y/yes` confirmation before proceeding.
- **Stopping criterion:** `b < limit` where `limit = 10^max_digits` (rug::Integer). Computed once before the loop.

## Testing

```bash
cd fib/fib-rs
cargo test
```

### Test coverage

| Area                 | Tests                                                                                                     |
| -------------------- | --------------------------------------------------------------------------------------------------------- |
| `fmt_int`            | 4 — zero, sub-thousand, thousands, millions                                                               |
| `generate_fibonacci` | 6 — single-digit sequence, two-digit count, last value, first 10 values, Fibonacci property, all positive |

Uncovered: `prompt_exponent`, `read_line`, `main()` — interactive/integration only.

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Change the valid exponent range or large-N threshold → update Important Behavior
- Add tests or change coverage → update Testing table
- Add a Makefile target → update Build section

````

- [ ] **Step 3: Create fib/README.md**

```markdown
# fib

Generate every Fibonacci number with at most 10^X decimal digits.

Two implementations:

| Implementation | File | Description |
|----------------|------|-------------|
| Python | `fib.py` | Built-in arbitrary-precision integers, no external deps |
| Rust | `fib-rs/` | `rug`/GMP for best performance at large digit counts |

## Quick Start

### Python

```bash
cd fib
bash install_deps.sh   # install ruff + coverage (one time)
make run               # interactive prompt
python3 fib.py 3       # generate Fibonacci numbers with up to 1,000 digits
make test              # run unit tests
````

### Rust

```bash
cd fib/fib-rs
bash install_deps.sh   # install GMP + Rust toolchain (one time)
make fib               # build release binary → ~/Downloads/fib
./target/release/fib 3
make test
```

## Usage

Both implementations accept an optional positional argument X (1–5):

```
fib [X]
```

- X=1 → up to 10 digits (~47 numbers)
- X=2 → up to 100 digits (~478 numbers)
- X=3 → up to 1,000 digits (~4,785 numbers, ~2.4 MB)
- X=4 → up to 10,000 digits (~47,847 numbers, ~240 MB) — warns before proceeding
- X=5 → up to 100,000 digits (~478,468 numbers, ~24 GB) — warns before proceeding

Output: one Fibonacci number per line. Small results (X ≤ 2) are buffered and offered for display or file save. Larger results stream directly to `fib_1eX.txt`.

## Output Files

Generated `fib_1eX.txt` files are large artifacts and are not committed to git.

````

- [ ] **Step 4: Create root .gitignore**

```gitignore
# Generated output files — can be very large
pi_*_digits.txt
primes_1e*.txt
fib_1e*.txt
````

- [ ] **Step 5: Update top-level CLAUDE.md**

In the Repository Overview table, add a row for fib:

Find:

```markdown
| [`prime/`](prime/) | Rust | Find all primes up to 10^N (segmented sieve) | [`prime/CLAUDE.md`](prime/CLAUDE.md) |
```

Replace with:

```markdown
| [`prime/`](prime/) | Rust | Find all primes up to 10^N (segmented sieve) | [`prime/CLAUDE.md`](prime/CLAUDE.md) |
| [`fib/`](fib/) | Python + Rust | Generate all Fibonacci numbers with up to 10^X digits | [`fib/CLAUDE.md`](fib/CLAUDE.md) |
```

In the Quick Reference section, add after the prime section:

````markdown
### Python (`fib/`)

```bash
cd fib
make run       # python3 fib.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_fib -v
make coverage  # coverage run + report
```
````

### Rust (`fib/fib-rs/`)

```bash
cd fib/fib-rs
make fib       # cargo build --release
make lint      # cargo clippy -- -D warnings
make test      # lint, then cargo test
```

````

In the CI table, add a row:

```markdown
| fib.py | `.github/workflows/fib-py.yml` | test |
| fib-rs | `.github/workflows/fib-rs.yml` | test → build + artifact |
````

- [ ] **Step 6: Update top-level README.md**

Add two badges after the existing three, at the top of the file:

```markdown
[![fib.py](https://github.com/brujack/math/actions/workflows/fib-py.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/fib-py.yml)
[![fib-rs](https://github.com/brujack/math/actions/workflows/fib-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/fib-rs.yml)
```

Add a fib row to the project table:

```markdown
| [`fib/`](fib/README.md) | Generate all Fibonacci numbers with up to 10^X digits | Python + Rust | [![fib.py](https://github.com/brujack/math/actions/workflows/fib-py.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/fib-py.yml) [![fib-rs](https://github.com/brujack/math/actions/workflows/fib-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/fib-rs.yml) |
```

Add a fib section after the prime section:

```markdown
---

## fib

Generates every Fibonacci number with at most 10^X decimal digits.

- Python implementation (`fib/fib.py`) — uses Python's built-in arbitrary-precision `int`; no external dependencies
- Rust implementation (`fib/fib-rs/`) — uses `rug`/GMP for best performance at large digit counts

See [`fib/README.md`](fib/README.md) for full details.
```

- [ ] **Step 7: Commit everything**

```bash
git add fib/CLAUDE.md fib/fib-rs/CLAUDE.md fib/README.md .gitignore CLAUDE.md README.md
git commit -m "docs: add fib project docs, CLAUDE.md files, .gitignore, update top-level README and CLAUDE.md"
```

```

```
