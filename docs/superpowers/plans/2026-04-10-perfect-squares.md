# Perfect Squares Calculator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `sq/` project generating all perfect squares with at most 10^N decimal digits (N=1 only), with Python and Rust implementations matching the existing fib/pi/prime project structure.

**Architecture:** Python uses a generator function with native int arithmetic; Rust uses a generic `Write`-based function with u64 arithmetic and clap CLI. Both follow the same interactive CLI pattern: prompt for N, validate (N=1 only), buffer output, prompt to display or save to `sq_1e1.txt`. No big-integer libraries needed — all values fit in u64.

**Tech Stack:** Python 3 (stdlib only), Rust stable + clap 4, ruff, coverage, cargo-clippy

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `sq/sq.py` | Python implementation + CLI |
| Create | `sq/test_sq.py` | Python unit tests |
| Create | `sq/Makefile` | run, lint, test, coverage targets |
| Create | `sq/install_deps.sh` | installs ruff, coverage |
| Create | `sq/CLAUDE.md` | Python project guidance |
| Create | `sq/sq-rs/src/main.rs` | Rust implementation + unit tests |
| Create | `sq/sq-rs/Cargo.toml` | deps: clap only |
| Create | `sq/sq-rs/Makefile` | sq, lint, test, clean targets |
| Create | `sq/sq-rs/install_deps.sh` | Rust toolchain |
| Create | `sq/sq-rs/CLAUDE.md` | Rust project guidance |
| Create | `.github/workflows/sq-py.yml` | Python CI workflow |
| Create | `.github/workflows/sq-rs.yml` | Rust CI workflow |
| Modify | `.gitignore` | add `sq_1e*.txt` |
| Modify | `CLAUDE.md` | add sq/ to project table and CI table |
| Modify | `README.md` | add sq/ row, two CI badges |

---

## Task 1: Create feature branch

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout -b feat/perfect-squares
```

- [ ] **Step 2: Confirm branch**

```bash
git branch --show-current
```
Expected output: `feat/perfect-squares`

---

## Task 2: Scaffold Python project (non-code files)

**Files:** Create `sq/Makefile`, `sq/install_deps.sh`

- [ ] **Step 1: Create directory**

```bash
mkdir -p sq
```

- [ ] **Step 2: Create `sq/Makefile`**

```makefile
.PHONY: run lint test coverage clean

run:
	python3 sq.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_sq -v

coverage:
	coverage run -m unittest test_sq -v
	coverage report -m
```

- [ ] **Step 3: Create `sq/install_deps.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

pip install ruff coverage
```

- [ ] **Step 4: Make it executable**

```bash
chmod +x sq/install_deps.sh
```

- [ ] **Step 5: Commit scaffold**

```bash
git add sq/Makefile sq/install_deps.sh
git commit -m "chore: scaffold sq/ Python project files"
```

---

## Task 3: Python `generate_squares` — TDD

**Files:** Create `sq/test_sq.py`, Create `sq/sq.py`

- [ ] **Step 1: Create `sq/test_sq.py` with failing tests for `generate_squares`**

```python
#!/usr/bin/env python3
"""Unit tests for sq.py."""

import argparse
import sys
import unittest

from sq import generate_squares, parse_args, get_exponent


class TestGenerateSquares(unittest.TestCase):

    def test_zero_max_digits_empty(self):
        # max_digits=0: limit=10^0=1, k=1, k*k=1 >= 1 → yields nothing
        self.assertEqual(list(generate_squares(0)), [])

    def test_one_digit_squares(self):
        # max_digits=1: limit=10, yields 1, 4, 9 then 16 >= 10 stops
        self.assertEqual(list(generate_squares(1)), [1, 4, 9])

    def test_two_digit_count(self):
        # max_digits=2: limit=100, k=1..9 (9^2=81 < 100, 10^2=100 >= 100)
        self.assertEqual(len(list(generate_squares(2))), 9)

    def test_two_digit_last_value(self):
        result = list(generate_squares(2))
        self.assertEqual(result[-1], 81)

    def test_two_digit_excludes_100(self):
        result = list(generate_squares(2))
        self.assertNotIn(100, result)

    def test_each_is_perfect_square(self):
        import math
        for sq in generate_squares(3):
            root = math.isqrt(sq)
            self.assertEqual(root * root, sq)

    def test_strictly_increasing(self):
        result = list(generate_squares(3))
        for i in range(1, len(result)):
            self.assertGreater(result[i], result[i - 1])

    def test_ten_digit_count(self):
        # max_digits=10: k=1..99999 → exactly 99,999 squares
        self.assertEqual(sum(1 for _ in generate_squares(10)), 99_999)

    def test_ten_digit_last_value(self):
        # Last square: 99999^2 = 9,999,800,001
        result = list(generate_squares(10))
        self.assertEqual(result[-1], 99_999 * 99_999)

    def test_ten_digit_excludes_100000_squared(self):
        result = list(generate_squares(10))
        self.assertNotIn(100_000 * 100_000, result)
```

- [ ] **Step 2: Create minimal `sq/sq.py` stub so the import doesn't crash**

```python
#!/usr/bin/env python3
"""Generate all perfect squares with at most 10^N decimal digits."""

import argparse
import io
import sys


def generate_squares(max_digits: int):
    pass


def parse_args() -> argparse.Namespace:
    pass


def get_exponent(args: argparse.Namespace) -> int:
    pass


def main() -> None:
    pass


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd sq && python3 -m unittest test_sq.TestGenerateSquares -v 2>&1 | head -30
```
Expected: multiple FAIL/ERROR lines (stub returns None, not an iterable)

- [ ] **Step 4: Implement `generate_squares` in `sq/sq.py`**

Replace the stub with:

```python
def generate_squares(max_digits: int):
    """Yield every perfect square with at most max_digits decimal digits.

    Uses k*k < 10^max_digits as the stopping criterion (equivalent to
    len(str(k*k)) <= max_digits but avoids per-iteration string conversion).
    """
    limit = 10 ** max_digits
    k = 1
    while k * k < limit:
        yield k * k
        k += 1
```

- [ ] **Step 5: Run `generate_squares` tests to confirm they pass**

```bash
cd sq && python3 -m unittest test_sq.TestGenerateSquares -v
```
Expected: 10 tests, all OK

- [ ] **Step 6: Commit**

```bash
git add sq/sq.py sq/test_sq.py
git commit -m "feat: implement Python generate_squares with TDD"
```

---

## Task 4: Python CLI (`parse_args`, `get_exponent`) — TDD

**Files:** Modify `sq/test_sq.py`, Modify `sq/sq.py`

- [ ] **Step 1: Add CLI test classes to `sq/test_sq.py`**

Append after `TestGenerateSquares`:

```python
class TestParseArgs(unittest.TestCase):

    def test_no_args(self):
        old_argv = sys.argv
        sys.argv = ["sq.py"]
        args = parse_args()
        sys.argv = old_argv
        self.assertIsNone(args.exponent)

    def test_with_valid_arg(self):
        old_argv = sys.argv
        sys.argv = ["sq.py", "1"]
        args = parse_args()
        sys.argv = old_argv
        self.assertEqual(args.exponent, 1)

    def test_invalid_non_integer_exits(self):
        old_argv = sys.argv
        sys.argv = ["sq.py", "abc"]
        try:
            with self.assertRaises(SystemExit):
                parse_args()
        finally:
            sys.argv = old_argv


class TestGetExponent(unittest.TestCase):

    def _args(self, exponent):
        return argparse.Namespace(exponent=exponent)

    def test_valid_value(self):
        self.assertEqual(get_exponent(self._args(1)), 1)

    def test_zero_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._args(0))

    def test_too_high_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._args(2))

    def test_negative_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._args(-1))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
cd sq && python3 -m unittest test_sq.TestParseArgs test_sq.TestGetExponent -v 2>&1 | head -20
```
Expected: failures/errors (stubs return None)

- [ ] **Step 3: Implement `parse_args` and `get_exponent` in `sq/sq.py`**

Replace the two stubs:

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate all perfect squares with up to 10^N digits",
        epilog="Run without arguments for an interactive prompt.",
    )
    parser.add_argument(
        "exponent",
        type=int,
        nargs="?",
        help="N: generates perfect squares with up to 10^N digits (max 1)",
    )
    return parser.parse_args()


def get_exponent(args: argparse.Namespace) -> int:
    """Return validated exponent from CLI args, or prompt interactively."""
    if args.exponent is not None:
        x = args.exponent
        if x != 1:
            print("Error: N must be 1.", file=sys.stderr)
            sys.exit(1)
        return x
    while True:
        try:
            raw = input(
                "Enter N (finds all perfect squares with up to 10^N digits, max 1): "
            )
            x = int(raw)
            if x == 1:
                return x
            print("N must be 1.")
        except ValueError:
            print("Please enter a positive integer.")
```

- [ ] **Step 4: Run all Python tests**

```bash
cd sq && python3 -m unittest test_sq -v
```
Expected: 17 tests, all OK

- [ ] **Step 5: Commit**

```bash
git add sq/sq.py sq/test_sq.py
git commit -m "feat: implement Python CLI parse_args and get_exponent with TDD"
```

---

## Task 5: Python `main()` and lint

**Files:** Modify `sq/sq.py`

- [ ] **Step 1: Implement `main()` in `sq/sq.py`**

Replace the stub:

```python
def main() -> None:
    args = parse_args()
    x = get_exponent(args)
    max_digits = 10 ** x

    print("Perfect Square Generator (Python)")
    print("=" * 40)
    print(
        f"Generating all perfect squares with up to 10^{x} = {max_digits:,} digits"
    )

    buf = io.StringIO()
    count = 0
    for sq in generate_squares(max_digits):
        buf.write(str(sq))
        buf.write("\n")
        count += 1

    print(f"\nFound {count:,} perfect squares with up to 10^{x} digits")
    answer = input(
        f"Display all {count:,} perfect squares? (y/n): "
    ).strip().lower()
    if answer in ("y", "yes"):
        print(buf.getvalue(), end="")
    else:
        filename = f"sq_1e{x}.txt"
        with open(filename, "w") as f:
            f.write(buf.getvalue())
        print(f"Saved to {filename}")
```

- [ ] **Step 2: Run lint**

```bash
cd sq && make lint
```
Expected: `All checks passed!`

- [ ] **Step 3: Run full test suite**

```bash
cd sq && make test
```
Expected: 17 tests, all OK

- [ ] **Step 4: Commit**

```bash
git add sq/sq.py
git commit -m "feat: implement Python main()"
```

---

## Task 6: Scaffold Rust project

**Files:** Create `sq/sq-rs/Cargo.toml`, `sq/sq-rs/Makefile`, `sq/sq-rs/install_deps.sh`, `sq/sq-rs/src/main.rs` (stub)

- [ ] **Step 1: Create directories**

```bash
mkdir -p sq/sq-rs/src
```

- [ ] **Step 2: Create `sq/sq-rs/Cargo.toml`**

```toml
[package]
name = "sq"
version = "0.1.0"
edition = "2021"

[dependencies]
clap = { version = "4", features = ["derive"] }
```

- [ ] **Step 3: Create `sq/sq-rs/Makefile`**

```makefile
.PHONY: sq lint test clean

sq:
	cargo build --release
	cp target/release/sq ~/Downloads/sq

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/sq
```

- [ ] **Step 4: Create `sq/sq-rs/install_deps.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

if ! command -v cargo &>/dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    # shellcheck source=/dev/null
    source "${HOME}/.cargo/env"
fi
```

- [ ] **Step 5: Make it executable**

```bash
chmod +x sq/sq-rs/install_deps.sh
```

- [ ] **Step 6: Create minimal `sq/sq-rs/src/main.rs` stub**

```rust
fn main() {}
```

- [ ] **Step 7: Verify it compiles**

```bash
cd sq/sq-rs && cargo build 2>&1 | tail -5
```
Expected: `Finished` line with no errors

- [ ] **Step 8: Commit scaffold**

```bash
git add sq/sq-rs/
git commit -m "chore: scaffold sq-rs Rust project"
```

---

## Task 7: Rust `fmt_int` — TDD

**Files:** Modify `sq/sq-rs/src/main.rs`

- [ ] **Step 1: Add `fmt_int` test and stub to `sq/sq-rs/src/main.rs`**

Replace the entire file:

```rust
use std::io::{self, BufRead, Write};

use clap::Parser;

#[derive(Parser)]
#[command(
    name = "sq",
    about = "Generate all perfect squares with up to 10^N digits",
    long_about = "Generate all perfect squares whose decimal digit count is at most 10^N.\n\n\
                  Run without arguments for interactive prompts."
)]
struct Cli {
    /// N: generates perfect squares with up to 10^N digits (max 1)
    exponent: Option<u32>,
}

fn generate_squares<W: Write>(_max_digits: u32, _out: &mut W) -> io::Result<u64> {
    Ok(0)
}

fn fmt_int(_n: u64) -> String {
    String::new()
}

fn read_line() -> String {
    let stdin = io::stdin();
    let mut line = String::new();
    stdin.lock().read_line(&mut line).unwrap();
    line.trim().to_string()
}

fn prompt_exponent() -> u32 {
    1
}

fn main() {}

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
}
```

- [ ] **Step 2: Run tests to confirm `fmt_int` tests fail**

```bash
cd sq/sq-rs && cargo test tests::test_fmt_int 2>&1 | tail -15
```
Expected: 4 failures (stub returns empty string)

- [ ] **Step 3: Implement `fmt_int`**

Replace the `fmt_int` stub:

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

- [ ] **Step 4: Run `fmt_int` tests to confirm they pass**

```bash
cd sq/sq-rs && cargo test tests::test_fmt_int 2>&1 | tail -10
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add sq/sq-rs/src/main.rs
git commit -m "feat: implement Rust fmt_int with TDD"
```

---

## Task 8: Rust `generate_squares` — TDD

**Files:** Modify `sq/sq-rs/src/main.rs`

- [ ] **Step 1: Add `generate_squares` tests and `FailWriter` to the `tests` module**

Add inside `mod tests { ... }`, after the `fmt_int` tests:

```rust
    // --- FailWriter helper ---

    struct FailWriter;
    impl Write for FailWriter {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::new(io::ErrorKind::Other, "write failed"))
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    // --- generate_squares ---

    #[test]
    fn test_zero_max_digits_empty() {
        // max_digits=0: limit=1, k=1, k*k=1 >= 1 → yields nothing
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_squares(0, &mut buf).unwrap();
        assert_eq!(count, 0);
        assert!(buf.is_empty());
    }

    #[test]
    fn test_one_digit_squares() {
        // max_digits=1: limit=10, yields 1, 4, 9
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_squares(1, &mut buf).unwrap();
        assert_eq!(count, 3);
        assert_eq!(String::from_utf8(buf).unwrap(), "1\n4\n9\n");
    }

    #[test]
    fn test_two_digit_count() {
        // max_digits=2: limit=100, k=1..9 → 9 squares
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_squares(2, &mut buf).unwrap();
        assert_eq!(count, 9);
    }

    #[test]
    fn test_two_digit_last_value() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(2, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert_eq!(output.lines().last().unwrap(), "81");
    }

    #[test]
    fn test_two_digit_excludes_100() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(2, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert!(!output.lines().any(|l| l == "100"));
    }

    #[test]
    fn test_each_is_perfect_square() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(3, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        for line in output.lines() {
            let n: u64 = line.parse().unwrap();
            let root = (n as f64).sqrt() as u64;
            assert_eq!(root * root, n, "{n} is not a perfect square");
        }
    }

    #[test]
    fn test_strictly_increasing() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(3, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        let nums: Vec<u64> = output.lines().map(|l| l.parse().unwrap()).collect();
        for i in 1..nums.len() {
            assert!(nums[i] > nums[i - 1]);
        }
    }

    #[test]
    fn test_ten_digit_count() {
        // max_digits=10: k=1..99999 → exactly 99,999 squares
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_squares(10, &mut buf).unwrap();
        assert_eq!(count, 99_999);
    }

    #[test]
    fn test_ten_digit_last_value() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(10, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert_eq!(output.lines().last().unwrap(), "9999800001");
    }

    #[test]
    fn test_ten_digit_excludes_100000_squared() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(10, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert!(!output.lines().any(|l| l == "10000000000"));
    }

    #[test]
    fn test_write_error_propagates() {
        let result = generate_squares(1, &mut FailWriter);
        assert!(result.is_err());
    }
```

- [ ] **Step 2: Run `generate_squares` tests to confirm they fail**

```bash
cd sq/sq-rs && cargo test tests::test_zero_max 2>&1 | tail -10
```
Expected: FAILED (stub always returns `Ok(0)`)

- [ ] **Step 3: Implement `generate_squares`**

Replace the stub:

```rust
/// Generate all perfect squares with at most max_digits decimal digits,
/// writing one square per line to `out`. Returns the total count.
///
/// Uses k*k < 10^max_digits as the stopping criterion. All values fit
/// in u64 for max_digits ≤ 10 (the maximum supported input).
fn generate_squares<W: Write>(max_digits: u32, out: &mut W) -> io::Result<u64> {
    let limit: u64 = 10u64.pow(max_digits);
    let mut k: u64 = 1;
    let mut count: u64 = 0;
    while let Some(sq) = k.checked_mul(k) {
        if sq >= limit {
            break;
        }
        writeln!(out, "{}", sq)?;
        count += 1;
        k += 1;
    }
    Ok(count)
}
```

- [ ] **Step 4: Run all Rust tests**

```bash
cd sq/sq-rs && make test
```
Expected: all tests pass (clippy clean + all test cases OK)

- [ ] **Step 5: Commit**

```bash
git add sq/sq-rs/src/main.rs
git commit -m "feat: implement Rust generate_squares with TDD"
```

---

## Task 9: Rust CLI (`prompt_exponent`, `main`)

**Files:** Modify `sq/sq-rs/src/main.rs`

- [ ] **Step 1: Implement `prompt_exponent` (replace stub)**

```rust
fn prompt_exponent() -> u32 {
    loop {
        print!("Enter N (finds all perfect squares with up to 10^N digits, max 1): ");
        io::stdout().flush().unwrap();
        match read_line().parse::<u32>() {
            Ok(1) => return 1,
            Ok(_) => eprintln!("N must be 1."),
            _ => eprintln!("Please enter a positive integer."),
        }
    }
}
```

- [ ] **Step 2: Implement `main` (replace stub)**

```rust
fn main() {
    let cli = Cli::parse();

    let exponent = match cli.exponent {
        Some(n) => {
            if n != 1 {
                eprintln!("Error: N must be 1.");
                std::process::exit(1);
            }
            n
        }
        None => prompt_exponent(),
    };

    let max_digits: u32 = 10u32.pow(exponent); // 10^1 = 10

    println!("Perfect Square Generator (Rust)");
    println!("{}", "=".repeat(40));
    println!(
        "Generating all perfect squares with up to 10^{} = {} digits",
        exponent,
        fmt_int(u64::from(max_digits))
    );

    let mut buf: Vec<u8> = Vec::new();
    let count = generate_squares(max_digits, &mut buf).expect("generation error");

    println!("\nFound {} perfect squares with up to 10^{} digits", fmt_int(count), exponent);
    print!("Display all {} perfect squares? (y/n): ", fmt_int(count));
    io::stdout().flush().unwrap();
    if matches!(read_line().as_str(), "y" | "yes") {
        io::stdout().write_all(&buf).unwrap();
    } else {
        let filename = format!("sq_1e{}.txt", exponent);
        std::fs::write(&filename, &buf).expect("file write failed");
        println!("Saved to {}", filename);
    }
}
```

- [ ] **Step 3: Run full test suite and lint**

```bash
cd sq/sq-rs && make test
```
Expected: all tests pass, clippy clean

- [ ] **Step 4: Commit**

```bash
git add sq/sq-rs/src/main.rs
git commit -m "feat: implement Rust CLI prompt_exponent and main"
```

---

## Task 10: `.gitignore` update

**Files:** Modify `.gitignore`

- [ ] **Step 1: Add `sq_1e*.txt` to `.gitignore`**

Open `.gitignore` and add after `fib_1e*.txt`:

```
sq_1e*.txt
```

- [ ] **Step 2: Verify**

```bash
echo "sq_1e1.txt" | git check-ignore --stdin
```
Expected: `sq_1e1.txt`

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: add sq_1e*.txt to .gitignore"
```

---

## Task 11: Sub-project CLAUDE.md files

**Files:** Create `sq/CLAUDE.md`, Create `sq/sq-rs/CLAUDE.md`

- [ ] **Step 1: Create `sq/CLAUDE.md`**

```markdown
# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This directory contains a Python CLI for generating all perfect squares with at most 10^N decimal digits. N=1 is the only valid value (10-digit squares); any other value exits with an error.

Current structure:

- `sq.py` — interactive generator script (Python stdlib only, no external deps)
- `sq-rs/` — Rust implementation (no big-integer library needed)
- `install_deps.sh` — installs ruff and coverage
- `test_sq.py` — unit tests

## Running the Script

\```bash
make run       # python3 sq.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_sq -v
make coverage  # run tests and print coverage report
\```

Or directly:

\```bash
python3 sq.py      # interactive prompt
python3 sq.py 1    # generate all perfect squares with up to 10 digits
\```

## Code Layout

- `generate_squares(max_digits)` — generator that yields every perfect square with at most `max_digits` decimal digits. Uses `k*k < 10^max_digits` stopping criterion; limit precomputed once before the loop.
- `parse_args()` — parses CLI via `argparse`; returns `Namespace` with optional `exponent` int.
- `get_exponent(args)` — returns validated exponent from args, or prompts interactively. Valid value: 1 only. Calls `sys.exit(1)` for any other value.
- `main()` — top-level entry: parses args, validates, buffers output, prompts to display or save to `sq_1e1.txt`.

## Important Behavior

- **Output:** always buffered in a `StringIO` (output is always small — ~100k lines, ~1 MB). User is prompted to display or save to `sq_1eN.txt`.
- **Valid N:** 1 only. `get_exponent` exits with code 1 for any other value.
- **Stopping criterion:** `k*k < 10^max_digits` (precomputed limit). For N=1: limit=10^10, last included square is 99,999² = 9,999,800,001.
- **No external dependencies:** uses Python stdlib only.

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass. Never write implementation before the test. Tests must be added in the same commit as the code they cover.

Every test must cover more than the happy path. Three categories are required for every function:

- **Boundary value tests** — empty/zero/null input, single vs multiple elements, min/max valid values, one above/below valid range
- **Error path tests** — what happens on failure, dependency failure, partial failure
- **State transition tests** — before/after assertions, no unintended side effects, idempotency

\```bash
make test      # lint + unittest
make coverage  # coverage run + report
\```

### Test coverage

| Class | Tests |
|-------|-------|
| `TestGenerateSquares` | 10 — boundary (empty, 1-digit, 2-digit, 10-digit), correctness (perfect square, increasing), count, last value, exclusion |
| `TestParseArgs` | 3 — no-arg, with-arg, invalid non-integer exits |
| `TestGetExponent` | 4 — valid (1), zero exits, too-high exits, negative exits |

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Add or remove a Makefile target → update Running section and `README.md`
- Change the valid exponent range → update Important Behavior
- Add test classes or change coverage → update Testing table
```

- [ ] **Step 2: Create `sq/sq-rs/CLAUDE.md`**

```markdown
# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

Rust CLI for generating all perfect squares with at most 10^N decimal digits. N=1 is the only valid value. Uses plain u64 arithmetic — no big-integer library required.

Current structure:

- `src/main.rs` — full implementation + unit tests
- `Cargo.toml` — deps: clap only
- `Makefile` — sq, lint, test, clean targets
- `install_deps.sh` — Rust toolchain

## Build

\```bash
cd sq/sq-rs
make sq        # cargo build --release, copies binary to ~/Downloads/sq
make lint      # cargo clippy -- -D warnings
make test      # lint, then cargo test
make clean     # cargo clean + remove ~/Downloads/sq
\```

Or directly:

\```bash
./target/release/sq        # interactive prompt
./target/release/sq 1      # generate all perfect squares with up to 10 digits
\```

## Code Layout (`src/main.rs`)

- `struct Cli` — clap derive struct; `exponent: Option<u32>` optional positional arg.
- `fn generate_squares<W: Write>(max_digits, out)` — iterates k=1,2,... writing k² per line until k²≥10^max_digits. Uses `checked_mul` for clarity. Returns total count.
- `fn fmt_int(n)` — formats `u64` with thousands separators.
- `fn read_line()` — reads one trimmed line from stdin.
- `fn prompt_exponent()` — interactive prompt loop; validates N=1 only.
- `fn main()` — parses CLI, validates N=1, buffers output, prompts to display or save.

## Important Behavior

- **Valid N:** 1 only. Any other value exits with code 1.
- **Output:** always buffered in `Vec<u8>` (~1 MB). User prompted to display or save to `sq_1eN.txt`.
- **Stopping criterion:** `k.checked_mul(k).map_or(false, |sq| sq < limit)` where `limit = 10u64.pow(max_digits)`.
- **No GMP/rug:** all values fit in u64 for N=1 (max square = 99,999² = 9,999,800,001 << u64::MAX).

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass. Never write implementation before the test. Tests must be added in the same commit as the code they cover.

Every test must cover more than the happy path. Three categories are required for every function:

- **Boundary value tests** — empty/zero/null input, single vs multiple elements, min/max valid values, one above/below valid range
- **Error path tests** — what happens on failure, dependency failure, partial failure
- **State transition tests** — before/after assertions, no unintended side effects, idempotency

### Test coverage

| Area | Tests |
|------|-------|
| `fmt_int` | 4 — zero, sub-thousand, thousands, millions |
| `generate_squares` | 11 — empty (max_digits=0), 1-digit exact, 2-digit count/last/exclusion, perfect-square property, strictly increasing, 10-digit count/last/exclusion, write error propagates |

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Add a Makefile target → update Build section
- Change the valid exponent range → update Important Behavior
- Add tests or change coverage → update Testing table
```

- [ ] **Step 3: Commit**

```bash
git add sq/CLAUDE.md sq/sq-rs/CLAUDE.md
git commit -m "docs: add CLAUDE.md files for sq/ and sq/sq-rs/"
```

---

## Task 12: Top-level `CLAUDE.md` and `README.md`

**Files:** Modify `CLAUDE.md`, Modify `README.md`

- [ ] **Step 1: Update `CLAUDE.md` — Repository Overview table**

In `CLAUDE.md`, add a row to the Repository Overview table:

```markdown
| [`sq/`](sq/) | Python + Rust | Find all perfect squares with up to 10^N digits (N=1 max) | [`sq/CLAUDE.md`](sq/CLAUDE.md) |
```

- [ ] **Step 2: Update `CLAUDE.md` — Quick Reference section**

Add two new Quick Reference blocks after the existing `fib/fib-rs/` block:

```markdown
### Python (`sq/`)

\```bash
cd sq
make run       # python3 sq.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_sq -v
make coverage  # coverage run + report
\```

### Rust (`sq/sq-rs/`)

\```bash
cd sq/sq-rs
make sq        # cargo build --release
make lint      # cargo clippy -- -D warnings
make test      # lint, then cargo test
\```
```

- [ ] **Step 3: Update `CLAUDE.md` — Testing Policy**

In the "Where to add tests" bullet list, add:

```markdown
- Python tests: add to `sq/test_sq.py` (sq), run with `make test` from the project directory
```

- [ ] **Step 4: Update `CLAUDE.md` — CI table**

Add two rows to the CI table:

```markdown
| sq.py | `.github/workflows/sq-py.yml` | test |
| sq-rs | `.github/workflows/sq-rs.yml` | test → build + artifact |
```

Update the workflow count in the CI section intro from "Six workflow files" to "Eight workflow files".

- [ ] **Step 5: Update `CLAUDE.md` — Dependency Installation table**

Add two rows:

```markdown
| `sq/install_deps.sh` | `ruff`, `coverage` |
| `sq/sq-rs/install_deps.sh` | Rust toolchain |
```

- [ ] **Step 6: Update `README.md` — badges**

Add two badges after the existing fib-rs badge line:

```markdown
[![sq.py](https://github.com/brujack/math/actions/workflows/sq-py.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/sq-py.yml)
[![sq-rs](https://github.com/brujack/math/actions/workflows/sq-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/sq-rs.yml)
```

- [ ] **Step 7: Update `README.md` — project table**

Add a row after the fib row:

```markdown
| [`sq/`](sq/) | Generate all perfect squares with up to 10^N digits (N=1 max) | Python + Rust | [![sq.py](https://github.com/brujack/math/actions/workflows/sq-py.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/sq-py.yml) [![sq-rs](https://github.com/brujack/math/actions/workflows/sq-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/sq-rs.yml) |
```

- [ ] **Step 8: Update `README.md` — sq section**

Add after the fib section (before `## Architectural Decisions`):

```markdown
---

## sq

Generates every perfect square with at most 10^N decimal digits. N=1 is the only valid value (produces 99,999 squares up to 10 digits).

- Python implementation (`sq/sq.py`) — Python stdlib only, no external dependencies
- Rust implementation (`sq/sq-rs/`) — plain u64 arithmetic, no GMP required
```

- [ ] **Step 9: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: add sq/ to top-level CLAUDE.md and README.md"
```

---

## Task 13: CI workflows

**Files:** Create `.github/workflows/sq-py.yml`, Create `.github/workflows/sq-rs.yml`

- [ ] **Step 1: Create `.github/workflows/sq-py.yml`**

```yaml
name: sq.py

on:
  push:
    branches-ignore:
      - master
  pull_request:
    branches:
      - master

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  test:
    name: Test sq.py
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: sq
    steps:
      - uses: actions/checkout@v5

      - name: Install Python dependencies
        run: pip install ruff coverage

      - name: Run tests
        run: make test
```

- [ ] **Step 2: Create `.github/workflows/sq-rs.yml`**

```yaml
name: sq-rs

on:
  push:
    branches-ignore:
      - master
  pull_request:
    branches:
      - master

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  test:
    name: Test sq-rs
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: sq/sq-rs
    steps:
      - uses: actions/checkout@v5

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: sq/sq-rs

      - name: Run tests
        run: make test

  build:
    name: Build sq-rs
    runs-on: ubuntu-latest
    needs: [test]
    defaults:
      run:
        working-directory: sq/sq-rs
    steps:
      - uses: actions/checkout@v5

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: sq/sq-rs

      - name: Build
        run: cargo build --release

      - name: Upload artifact
        uses: actions/upload-artifact@v5
        with:
          name: sq
          path: sq/sq-rs/target/release/sq
          retention-days: 7
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/sq-py.yml .github/workflows/sq-rs.yml
git commit -m "ci: add sq.py and sq-rs workflows"
```

---

## Task 14: Open PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin feat/perfect-squares
```

- [ ] **Step 2: Open PR**

```bash
gh pr create \
  --title "feat: add perfect squares calculator (Python + Rust)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `sq/` project with Python and Rust implementations
- Generates all perfect squares with at most 10^N digits (N=1 only; larger values are rejected)
- No big-integer library needed — all values fit in u64
- Follows existing project structure: Makefile, install_deps.sh, CLAUDE.md, CI workflows
- Output file `sq_1e1.txt` added to .gitignore

## Test plan
- [ ] `cd sq && make test` passes (17 Python tests)
- [ ] `cd sq/sq-rs && make test` passes (all Rust tests)
- [ ] CI workflows appear in GitHub Actions on push
EOF
)"
```
