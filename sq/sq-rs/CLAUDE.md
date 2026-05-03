# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

Rust CLI for generating all perfect squares with at most 10^N decimal digits. N=1 is the only valid value. Uses plain u64 arithmetic — no big-integer library required.

Current structure:

- `src/main.rs` — full implementation + unit tests
- `tests/cli.rs` — subprocess integration tests for the binary entry point
- `Cargo.toml` — deps: clap; dev-deps: tempfile
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
- `fn generate_squares<W: Write>(max_digits, out)` — iterates k=1,2,... writing `"k² | k"` per line until k²≥10^max_digits. Uses `k.checked_mul(k).filter(|&sq| sq < limit)` in the `while let` to avoid an explicit `break;` (Linux ptrace tarpaulin marks `break;` in `while let` loops as an uncoverable probe). Returns total count.
- `fn fmt_int(n)` — formats `u64` with thousands separators.
- `fn read_line_from<R: BufRead>(reader)` — reads one trimmed line from any `BufRead`.
- `fn prompt_exponent_with<R: BufRead, W: Write, E: Write>(reader, out, err)` — interactive prompt loop; validates N=1 only. Writes prompts to `out` and errors to `err`.
- `fn write_squares_file(dir, exponent, buf)` — writes the buffered output to `<dir>/sq_1eN.txt` and returns the path.
- `fn run<R: BufRead, W: Write, E: Write>(cli, reader, out, err, dir)` — full request lifecycle: validates exponent, generates squares, saves the file, optionally re-displays. Returns the process exit code (`0` success, `1` invalid N).
- `fn main()` — thin wrapper: parses CLI, locks stdin/stdout/stderr, calls `run` against `current_dir()`, exits with the returned code.

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

### Test coverage (96% line coverage, 41 tests)

| Area                   | Tests                                                                                                                                                                                    |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fmt_int`              | 4 — zero, sub-thousand, thousands, millions                                                                                                                                              |
| `generate_squares`     | 12 — empty (max_digits=0), 1-digit exact, 2-digit count/last/exclusion, perfect-square property, strictly increasing, 10-digit count/last/exclusion, write error propagates, idempotency |
| `read_line_from`       | 4 — trims trailing newline, trims whitespace, EOF on empty, returns only first line                                                                                                      |
| `prompt_exponent_with` | 5 — accepts 1, retries on 0/too-high/non-integer/negative                                                                                                                                |
| `write_squares_file`   | 4 — creates file, overwrites, exponent in filename, error on bad dir                                                                                                                     |
| `run`                  | 8 — arg=1 writes file, arg=0/2 returns 1, no-arg prompts then succeeds, "y"/"yes"/"n" branches, idempotency                                                                              |
| `tests/cli.rs`         | 4 subprocess tests — arg=1 writes file (stdin "n"), arg=2 exits 1, no-arg prompts then succeeds, "y" displays buffer                                                                     |

`main()` itself is a thin wrapper around `run`; the subprocess tests in `tests/cli.rs` exercise it end-to-end.

## Keeping This File Up To Date

Update this file whenever you:

- Rename or add a function → update Code Layout
- Add a Makefile target → update Build section
- Change the valid exponent range → update Important Behavior
- Add tests or change coverage → update Testing table
