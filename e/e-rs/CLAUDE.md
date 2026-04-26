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
- `fn write_e_file`: `#[cfg(unix)]` -- pre-allocates with `file.set_len()`, spawns a progress thread reporting write % and MB/s every 200 ms, parallel pwrite via rayon `par_chunks` (each chunk updates an `Arc<AtomicU64>` byte counter), joins thread and prints final MB/s
- `fn fmt_int(n)`: formats with thousands separators

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

### Test coverage (35% line coverage, 19 tests)

Below the project standard of >=90% — `write_e_file` (parallel pwrite I/O), `prompt_digits` / `read_line` (interactive stdin), and `main()` are integration-level uncovered.

| Area                   | Tests | Notes                                                                          |
| ---------------------- | ----- | ------------------------------------------------------------------------------ |
| `fmt_int`              | 5     | zero, sub-thousand, thousands, millions, billions                              |
| `bs_leaf`              | 4     | base case, index-1 formulas, index-2, counter delta                            |
| `bs_merge`             | 1     | result matches manual merge of two leaves                                      |
| `bs` split consistency | 2     | n=4 and n=8 split/merge round-trip                                             |
| `e_to_string`          | 5     | format, exact length, no exponent notation, known digits, single decimal place |
| `compute_e`            | 2     | end-to-end accuracy at 10 and 50 decimal places                                |

Uncovered lines: `write_e_file` (parallel pwrite I/O), `prompt_digits` / `read_line` (interactive stdin), `main()` -- all integration-level only.

### Adding new tests

- Add tests to the `#[cfg(test)] mod tests` block in `src/main.rs`.
- Use `const E_REF: &str = "2.71828182845904523536028747135266249775724709369995"` for accuracy assertions.
- `BS_LEAF_COUNT` is a global atomic -- check deltas, not absolute values, since tests run in parallel threads.

## Keeping This File Up To Date

**Update this file whenever you change the code.** Future Claude sessions rely on it -- stale docs are worse than none. Specifically:

- New or renamed function / constant -> update Code Layout
- Makefile target added or removed -> update the Makefile targets list
- Dependency added -> update `install_deps.sh` and parent `CLAUDE.md`
- Test added or coverage changes -> update the Testing coverage table
- Behaviour or algorithm change -> update Important Behavior

Also update the top-level `CLAUDE.md` and `e/CLAUDE.md` if the change affects the repository overview or quick-reference targets.
