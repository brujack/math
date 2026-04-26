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

```bash
cd sq/sq-rs
make sq        # cargo build --release, copies binary to ~/Downloads/sq
make lint      # cargo clippy -- -D warnings
make test      # lint, then cargo test
make clean     # cargo clean + remove ~/Downloads/sq
```

Or directly:

```bash
./target/release/sq        # interactive prompt
./target/release/sq 1      # generate all perfect squares with up to 10 digits
```

## Code Layout (`src/main.rs`)

- `struct Cli` — clap derive struct; `exponent: Option<u32>` optional positional arg.
- `fn generate_squares<W: Write>(max_digits, out)` — iterates k=1,2,... writing `"k² | k"` per line until k²≥10^max_digits. Uses `checked_mul` for clarity. Returns total count.
- `fn fmt_int(n)` — formats `u64` with thousands separators.
- `fn read_line()` — reads one trimmed line from stdin.
- `fn prompt_exponent()` — interactive prompt loop; validates N=1 only.
- `fn main()` — parses CLI, validates N=1, buffers output, prompts to display or save.

## Important Behavior

- **Valid N:** 1 only. Any other value exits with code 1.
- **Output:** always buffered in `Vec<u8>` and always saved to `sq_1eN.txt`. User is then prompted to also display on screen.
- **Stopping criterion:** `k.checked_mul(k)` where `limit = 10u64.pow(max_digits)`.
- **No GMP/rug:** all values fit in u64 for N=1 (max square = 99,999² = 9,999,800,001 << u64::MAX).

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass. Never write implementation before the test. Tests must be added in the same commit as the code they cover.

Every test must cover more than the happy path. Three categories are required for every function:

- **Boundary value tests** — empty/zero/null input, single vs multiple elements, min/max valid values, one above/below valid range
- **Error path tests** — what happens on failure, dependency failure, partial failure
- **State transition tests** — before/after assertions, no unintended side effects, idempotency

### Test coverage (35% line coverage, 16 tests)

Below the project standard of >=90% — `prompt_exponent`, `read_line`, `write_squares_file`, and `main()` are integration-level uncovered.

| Area               | Tests                                                                                                                                                                       |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fmt_int`          | 4 — zero, sub-thousand, thousands, millions                                                                                                                                 |
| `generate_squares` | 11 — empty (max_digits=0), 1-digit exact, 2-digit count/last/exclusion, perfect-square property, strictly increasing, 10-digit count/last/exclusion, write error propagates |

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Add a Makefile target → update Build section
- Change the valid exponent range → update Important Behavior
- Add tests or change coverage → update Testing table
