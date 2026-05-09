# CLAUDE.md

This file provides guidance to Claude when working with code in the `e-rs` Rust implementation.

## Repository Overview

Rust CLI for calculating Euler's number _e_ to an arbitrary number of decimal places using the Taylor series with binary splitting, parallelised via `rayon::join()`.

Key characteristics:

- `rayon::join()` for recursive parallel binary splitting -- threads share memory, zero IPC/serialisation cost
- `rug` wraps GMP (`Integer`) and MPFR (`Float`) directly -- same C libraries as Python's gmpy2
- Parallel file I/O via `FileExt::write_at` (POSIX pwrite equivalent) dispatched by rayon

Build (requires GMP + MPFR -- run `install_deps.sh` first):

```bash
cd e-rs
make e           # builds release binary and copies it to ~/Downloads/e
./target/release/e [digits]
```

## rug Arithmetic Note

`rug::Integer` operator overloading uses lazy "incomplete" types: `&Integer * &Integer` returns `MulIncomplete<'_>`, not `Integer`. Always wrap with `Integer::from(...)` before using the result in further operations:

```rust
// Correct:
Integer::from(&l.p * &r.p)
Integer::from(&l.q * &r.p) + &r.q
// Wrong (will not compile):
&l.p * &r.p + &l.q * &r.q
```

## Code Layout (`src/main.rs`)

- `BS_PAR_THRESHOLD`: switch from `rayon::join()` to serial recursion below this range size (512 terms); rayon work-stealing handles load-balancing
- `BS_LEAF_COUNT` (`static AtomicU64`): counts completed leaf nodes during `bs()`; read every 200 ms by the series progress thread to display percentage
- `struct Pq { p, q: Integer }`: accumulator for a Taylor series range `[a, b)`
- `fn bs(a, b)`: recursive binary splitting; uses `rayon::join()` above threshold, serial recursion below
- `fn bs_leaf(a)`: leaf computation with `rug::Integer`; increments `BS_LEAF_COUNT` on every call
- `fn bs_merge(l, r)`: combines two adjacent ranges
- `fn compute_e(digits)`: resets `BS_LEAF_COUNT`, spawns a progress thread that prints series completion % every 200 ms, runs `bs(0, n)`, joins the thread, then builds `rug::Float` and calls `e_to_string`
- `fn e_to_string(e, digits)`: uses `e.to_string_radix(10, Some(digits+5))`, trims to exact decimal places
- `fn write_e_file(dir, e_str, digits)`: `#[cfg(unix)]` -- builds `dir/e_<digits>_digits.txt`, pre-allocates with `file.set_len()`, spawns a progress thread reporting write % and MB/s every 200 ms, parallel pwrite via rayon `par_chunks` (each chunk updates an `Arc<AtomicU64>` byte counter), joins thread and prints final MB/s; returns the written `PathBuf`
- `fn save_e(dir, e_str, digits, out)`: `#[cfg(unix)]` -- announces the filename then delegates to `write_e_file`
- `fn fmt_int(n)`: formats with thousands separators
- `fn format_series_progress(completed, n)`: pure formatter for the compute progress line (testable in isolation)
- `fn format_write_progress(written, e_total, elapsed)`: pure formatter for the write progress line (testable in isolation)
- `fn read_line_from<R: BufRead>(reader)`: reads one trimmed line from any `BufRead`
- `fn prompt_digits_with<R, W, E>(reader, out, err)`: trait-injected interactive prompt (loops until valid; defers to `confirm_large_digits_with` for n > 1_000_000)
- `fn confirm_large_digits_with<R, W, E>(reader, out, err, n)`: y/n confirmation for large digit counts
- `fn run<R, W, E>(cli, reader, out, err, dir)`: orchestration — returns process exit code; injects all I/O so tests can use pipes + temp dirs
- `fn main()`: thin wrapper — locks stdio, calls `run`, exits with the returned code

## Important Behavior

- `write_e_file` is `#[cfg(unix)]` only -- it uses POSIX `pwrite(2)` via `std::os::unix::fs::FileExt::write_at`
- The progress thread pattern (spawn thread, `AtomicBool` flag, join after computation) is used for both series computation and file writing
- Term count estimation: `N = digits / log10(digits + 1) + 50` -- enough terms so that `N!` exceeds `10^digits`

## Makefile Targets

- `make e` -- runs `cargo build --release` and copies the binary to `~/Downloads/e`
- `make lint` -- runs `cargo clippy -- -D warnings`
- `make test` -- runs lint then `cargo test`
- `make clean` -- runs `cargo clean` and removes `~/Downloads/e`

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass.

Tests live in a `#[cfg(test)] mod tests` block at the bottom of `src/main.rs`.

Run the full suite:

```bash
cd e-rs
cargo test
```

Check coverage (requires `cargo-tarpaulin`):

```bash
cargo install cargo-tarpaulin   # one-time install
cargo tarpaulin --out Stdout
```

### Test coverage (94.58% line coverage, 63 tests: 58 unit + 5 integration)

| Area                                    | Tests | Notes                                                                                                 |
| --------------------------------------- | ----- | ----------------------------------------------------------------------------------------------------- |
| `fmt_int`                               | 5     | zero, sub-thousand, thousands, millions, billions                                                     |
| `bs_leaf`                               | 4     | base case, index-1, index-2, counter delta                                                            |
| `bs_merge`                              | 1     | result matches manual merge of two leaves                                                             |
| `bs` split consistency                  | 3     | n=4, n=8, and n=600 (exercises rayon::join branch above 512 threshold)                                |
| `e_to_string`                           | 7     | format, exact length, no exponent, known digits, single decimal place, exponent strip, no-dot path    |
| `compute_e`                             | 4     | digits=1 (else branch), end-to-end accuracy at 10 / 50, long enough to fire compute progress thread   |
| `format_series_progress`                | 4     | zero/partial/complete/zero-total                                                                      |
| `format_write_progress`                 | 4     | normal speed, zero-elapsed, zero-total, complete                                                      |
| `read_line_from`                        | 3     | trims newline, empty input, trims whitespace                                                          |
| `prompt_digits_with`                    | 6     | valid, minimum=1, zero retry, non-numeric retry, large decline + accept                               |
| `confirm_large_digits_with`             | 4     | "y", "yes", "n", other input                                                                          |
| `write_e_file`                          | 4     | contents, filename format, idempotency, missing-dir error                                             |
| `save_e`                                | 1     | writes file + announces                                                                               |
| `run`                                   | 5     | digits=0 → exit 1, display=y, save=n, no-arg prompts, digits>10000 auto-saves                         |
| `run_returns_err_on_stdout_failure`     | 1     | `run()` propagates Err when stdout write fails (FailWriter injection)                                 |
| `run_returns_err_on_stderr_failure`     | 1     | `run()` propagates Err when stderr write fails (FailWriter injection)                                 |
| `tests/cli.rs` (subprocess integration) | 5     | arg=0 exit 1, arg=10 + "y" displays, arg=10 + "n" saves, no-arg + "10\\nn\\n" prompts, unwritable dir |

Uncovered lines (10/210):

- Compute and write progress-thread loop bodies (timing-dependent — only fire after a 200 ms tick)
- e_to_string pad branch when raw is shorter than wanted (defensive; unreachable for normal MPFR floats)
- write speed `else 0.0` branch when `elapsed <= 0.001` (writes always take >1 ms)
- `loop {` line in `prompt_digits_with` (tarpaulin reporting quirk)
- `if d > 1_000_000` warning in `run` (would require running compute_e at million-digit scale)

### Adding new tests

- Unit tests live in the `#[cfg(test)] mod tests` block in `src/main.rs`.
- Subprocess integration tests live in `tests/cli.rs` and invoke the binary via `env!("CARGO_BIN_EXE_e")`.
- Use `const E_REF: &str = "2.71828182845904523536028747135266249775724709369995"` for accuracy assertions.
- `BS_LEAF_COUNT` is a global atomic -- check deltas, not absolute values, since tests run in parallel threads.
- For interactive functions, inject `&[u8]` as `BufRead` and `Vec<u8>` as `Write` for in-memory I/O.
- For file output, use `tempfile::tempdir()` so each test has a clean directory.

## Keeping This File Up To Date

**Update this file whenever you change the code.** Future Claude sessions rely on it -- stale docs are worse than none. Specifically:

- New or renamed function / constant -> update Code Layout
- Makefile target added or removed -> update the Makefile targets list
- Dependency added -> update `install_deps.sh` and parent `CLAUDE.md`
- Test added or coverage changes -> update the Testing coverage table
- Behaviour or algorithm change -> update Important Behavior

Also update the top-level `CLAUDE.md` and `e/CLAUDE.md` if the change affects the repository overview or quick-reference targets.
