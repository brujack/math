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
```

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

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass. Never write implementation before the test. Tests must be added in the same commit as the code they cover.

Every test must cover more than the happy path. Three categories are required for every function:

- **Boundary value tests** — empty/zero/null input, single vs multiple elements, min/max valid values, one above/below valid range
- **Error path tests** — what happens on failure, dependency failure, partial failure
- **State transition tests** — before/after assertions, no unintended side effects, idempotency

```bash
cd fib/fib-rs
cargo test
```

### Test coverage

| Area | Tests |
|------|-------|
| `fmt_int` | 4 — zero, sub-thousand, thousands, millions |
| `generate_fibonacci` | 8 — single-digit sequence, two-digit count, last value, first 10 values, Fibonacci property, all positive, max_digits=0 empty, write error propagates |

Uncovered: `prompt_exponent`, `read_line`, `main()` — interactive/integration only.

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Change the valid exponent range or large-N threshold → update Important Behavior
- Add tests or change coverage → update Testing table
- Add a Makefile target → update Build section
