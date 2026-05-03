# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

Rust CLI for generating all Fibonacci numbers with at most 10^X decimal digits. Uses `rug::Integer` (wraps libGMP) for arbitrary-precision arithmetic.

Current structure:

- `src/main.rs` — full implementation + unit tests
- `tests/cli.rs` — subprocess integration tests for the binary entry point
- `Cargo.toml` — deps: rug (integer feature), clap; dev-deps: tempfile
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
- `fn read_line_from<R: BufRead>(reader)` — reads one trimmed line from any `BufRead`.
- `fn prompt_exponent_with<R: BufRead, W: Write, E: Write>(reader, out, err)` — interactive prompt loop; validates 1–5. Prompts to `out`, errors to `err`.
- `fn confirm_large_n_with<R, W, E>(reader, out, err, exponent, max_digits)` — emits the "this may take a long time" warning to `err`, the `Continue? (y/n)` prompt to `out`, returns `true` on `y`/`yes`.
- `fn write_fib_file(dir, exponent, buf)` — buffered (X ≤ 2) save path; writes `<dir>/fib_1eX.txt` and returns the path.
- `fn stream_fib_to_file(dir, exponent, max_digits)` — streaming (X ≥ 3) path; opens `<dir>/fib_1eX.txt` with an 8 MB `BufWriter`, runs `generate_fibonacci`, returns `(path, count)`.
- `fn run<R: BufRead, W: Write, E: Write>(cli, reader, out, err, dir)` — full lifecycle: validates exponent, optionally warns/confirms for X ≥ 4, dispatches buffered or streaming path. Returns the process exit code (`0` success/aborted, `1` invalid X). Uses captured-variable format syntax (`{c}`, `{m}`, `{exponent}`) in writeln!/write! calls to keep them single-line under `rustfmt.toml`'s `use_small_heuristics = "Max"` setting.
- `fn main()` — thin wrapper: parses CLI, locks stdin/stdout/stderr, calls `run` against `current_dir()`, exits with the returned code.

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

### Test coverage (97% line coverage, 43 tests)

| Area                   | Tests                                                                                                                                                              |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `fmt_int`              | 4 — zero, sub-thousand, thousands, millions                                                                                                                        |
| `generate_fibonacci`   | 9 — single-digit sequence, two-digit count, last value, first 10 values, Fibonacci property, all positive, max_digits=0 empty, write error propagates, idempotency |
| `read_line_from`       | 4 — trims newline, trims whitespace, EOF on empty, only first line                                                                                                 |
| `prompt_exponent_with` | 6 — accepts low/high boundary (1, 5), retries on 0/6/non-integer/negative                                                                                          |
| `confirm_large_n_with` | 4 — "y", "yes", "n", blank treated as no                                                                                                                           |
| `write_fib_file`       | 4 — creates file, overwrites, exponent in filename, error on bad dir                                                                                               |
| `stream_fib_to_file`   | 2 — writes all values, error on bad dir                                                                                                                            |
| `run`                  | 10 — arg=0/6 returns 1, X=1 save/display, X=2 yes alias, X=3 streams, X=4 warning aborts on "n"/blank, no-arg prompts, idempotency on save                         |
| `tests/cli.rs`         | 4 subprocess tests — X=1 save (stdin "n"), X=6 exits 1, X=3 streams, no-arg prompts then succeeds                                                                  |

`main()` itself is a thin wrapper around `run`; the subprocess tests in `tests/cli.rs` exercise it end-to-end.

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Change the valid exponent range or large-N threshold → update Important Behavior
- Add tests or change coverage → update Testing table
- Add a Makefile target → update Build section
