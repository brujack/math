# CLAUDE.md

This file provides guidance to Claude when working with code in the `pi-rs` Rust implementation.

## Rust Implementation (`pi-rs/`)

The Rust binary targets >50M digit workloads where the Python subprocess IPC overhead becomes significant.

Key differences from Python:

- Uses `rayon::join()` for recursive parallel binary splitting — threads share memory, zero IPC/serialisation cost
- `rug` wraps GMP (`Integer`) and MPFR (`Float`) directly — same C libraries as Python's gmpy2
- Parallel file I/O via `FileExt::write_at` (POSIX pwrite equivalent) dispatched by rayon

Build (requires GMP + MPFR — run `install_deps.sh` first):

```bash
cd pi-rs
make pi          # cargo build --release (binary in target/release/pi)
make install     # build, then copy to ${XDG_BIN_HOME:-~/.local/bin}/pi
./target/release/pi [digits]
```

A `Makefile` is provided in `pi-rs/`:

- `make pi` — runs `cargo build --release`; the binary stays in `target/release/pi`
- `make install` — builds, then copies the binary to `${XDG_BIN_HOME:-~/.local/bin}/pi` (created if missing)
- `make lint` — runs `cargo clippy -- -D warnings`
- `make test` — runs lint then `cargo test`
- `make clean` — runs `cargo clean`

### Rust Code Layout (`pi-rs/src/main.rs`)

- `BS_PAR_THRESHOLD`: switch from `rayon::join()` to serial recursion below this range size (512 terms); rayon work-stealing handles load-balancing
- `BS_LEAF_COUNT` (`static AtomicU64`): counts completed leaf nodes during `bs()`; read every 200 ms by the series progress thread to display percentage
- `struct Pqt { p, q, t: Integer }`: accumulator for a Chudnovsky range `[a, b)`
- `fn bs(a, b)`: recursive binary splitting; uses `rayon::join()` above threshold, serial recursion below
- `fn bs_leaf(a)`: leaf computation with `rug::Integer`; increments `BS_LEAF_COUNT` on every call
- `fn bs_merge(l, r)`: combines two adjacent ranges
- `fn format_series_progress(completed, n)`: pure formatter for the compute progress line (testable in isolation)
- `fn compute_pi(digits)`: resets `BS_LEAF_COUNT`, spawns a progress thread that prints series completion % every 200 ms (a `recv_timeout(200 ms)` loop on an `mpsc` channel, so it exits the moment `bs` finishes), runs `bs(0, n)`, joins the thread, then builds `rug::Float` and calls `pi_to_string`
- `fn pi_to_string(pi, digits)`: uses `pi.to_string_radix(10, Some(digits+5))`, trims to exact decimal places
- `fn format_write_progress(written, pi_total, elapsed)`: pure formatter for the write progress line (testable in isolation)
- `fn write_pi_file(dir, pi_str, digits)`: `#[cfg(unix)]` — builds `dir/pi_<digits>_digits.txt`, pre-allocates with `file.set_len()`, spawns a progress thread reporting write % and MB/s every 200 ms, parallel pwrite via rayon `par_chunks` (each chunk updates an `Arc<AtomicU64>` byte counter), joins thread and prints final MB/s; returns the written `PathBuf`
- `fn save_pi(dir, pi_str, digits, out)`: `#[cfg(unix)]` — announces the filename then delegates to `write_pi_file`
- `fn fmt_int(n)`: formats with thousands separators
- `fn read_line_from<R: BufRead>(reader)`: reads one trimmed line from any `BufRead`
- `fn confirm_large_digits_with<R, W, E>(reader, out, err, n)`: y/n confirmation for large digit counts
- `fn prompt_digits_with<R, W, E>(reader, out, err)`: trait-injected interactive prompt (loops until valid; defers to `confirm_large_digits_with` for n > 1_000_000)
- `fn run<R, W, E>(cli, reader, out, err, dir)`: orchestration — returns process exit code; injects all I/O so tests can use pipes + temp dirs
- `fn main()`: thin wrapper — locks stdin/stdout, passes unlocked `io::stderr()` (a held `StderrLock` deadlocks the progress thread's `eprint!`), calls `run`, exits with the returned code

### rug Arithmetic Note

`rug::Integer` operator overloading uses lazy "incomplete" types: `&Integer * &Integer` returns `MulIncomplete<'_>`, not `Integer`. Always wrap with `Integer::from(...)` before using the result in further operations:

```rust
// Correct:
Integer::from(&l.p * &r.p)
Integer::from(&r.q * &l.t) + Integer::from(&l.p * &r.t)
// Wrong (will not compile):
&l.p * &r.p + &l.q * &r.q
```

### Rust (`pi-rs/`)

Tests live in a `#[cfg(test)] mod tests` block at the bottom of `src/main.rs`.

Run the full suite:

```bash
cd pi-rs
cargo test
```

Check coverage (requires `cargo-tarpaulin`):

```bash
cargo install cargo-tarpaulin   # one-time install
cargo tarpaulin --out Stdout
```

#### Test coverage (92.39% line coverage, 62 tests: 56 unit + 6 integration)

| Area                                    | Tests | Notes                                                                                                 |
| --------------------------------------- | ----- | ----------------------------------------------------------------------------------------------------- |
| `fmt_int`                               | 5     | zero, sub-thousand, thousands, millions, billions                                                     |
| `bs_leaf`                               | 4     | base case, index-1 formulas, even/odd sign, counter delta                                             |
| `bs_merge`                              | 1     | result matches manual merge of two leaves                                                             |
| `bs` split consistency                  | 3     | n=4, n=8, and n=600 (exercises rayon::join branch above 512 threshold)                                |
| `pi_to_string`                          | 7     | format, exact length, no exponent, known digits, single decimal place, exponent strip, no-dot path    |
| `compute_pi`                            | 2     | end-to-end accuracy at 10 and 50 decimal places                                                       |
| `format_series_progress`                | 4     | zero/partial/complete/zero-total                                                                      |
| `format_write_progress`                 | 4     | normal speed, zero-elapsed, zero-total, complete                                                      |
| `read_line_from`                        | 3     | trims newline, empty input, trims whitespace                                                          |
| `confirm_large_digits_with`             | 4     | "y", "yes", "n", other input                                                                          |
| `prompt_digits_with`                    | 6     | valid, minimum=1, zero retry, non-numeric retry, large decline + accept                               |
| `write_pi_file`                         | 4     | contents, filename format, idempotency, missing-dir error                                             |
| `save_pi`                               | 1     | writes file + announces                                                                               |
| `run`                                   | 5     | digits=0 → exit 1, display=y, save=n, no-arg prompts, digits>10000 auto-saves                         |
| `run_returns_err_on_stdout_failure`     | 1     | `run()` propagates Err when stdout write fails (FailWriter injection)                                 |
| `run_returns_err_on_stderr_failure`     | 1     | `run()` propagates Err when stderr write fails (FailWriter injection)                                 |
| `tests/cli.rs` (subprocess integration) | 6     | arg=0 exit 1, arg=10 + "y" displays, arg=10 + "n" saves, no-arg + "10\\ny\\n" prompts, unwritable dir, 10,000,000 digits exits within 60 s with a progress tick (stderr-lock deadlock regression) |

Uncovered lines (~17/224):

- Compute and write progress-thread loop bodies (timing-dependent — only fire after a 200 ms tick)
- `pi_to_string` pad branch when raw is shorter than wanted (defensive; unreachable for normal MPFR floats)
- Write speed `else 0.0` branch when `elapsed <= 0.001` (writes always take >1 ms)
- `#[cfg(not(unix))]` fallback stubs in `run` (macOS/Linux tests only hit the unix path)

#### Adding new tests

- Add tests to the `#[cfg(test)] mod tests` block in `src/main.rs`.
- Use `const PI_REF: &str = "3.14159265358979323846264338327950288419716939937510"` for accuracy assertions.
- `BS_LEAF_COUNT` is a global atomic — check deltas, not absolute values, since tests run in parallel threads.
