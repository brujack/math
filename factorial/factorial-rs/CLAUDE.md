# CLAUDE.md

This file provides guidance to Claude when working with code in the `factorial-rs` Rust implementation.

## Repository Overview

Rust CLI for computing N! (N factorial) to arbitrary precision using the prime swing algorithm: `n! = swing(n) × (⌊n/2⌋!)²` (Luschny prime swing identity).

Key characteristics:

- `rayon::par_chunks` for parallel prime swing computation -- primes divided into chunks, each chunk processed by a worker thread, results tree-reduced via `reduce()`
- `rug` wraps GMP (`Integer`) directly -- same C library as Python's gmpy2
- Single-pass sieve of Eratosthenes; primes stored as `u32` for memory efficiency

Build (requires GMP -- run `install_deps.sh` first):

```bash
cd factorial-rs
make factorial   # builds release binary and copies it to ~/Downloads/factorial
./target/release/factorial [N]
```

## rug Arithmetic Note

`rug::Integer` operator overloading uses lazy "incomplete" types: `&Integer * &Integer` returns `MulIncomplete<'_>`, not `Integer`. Always wrap with `Integer::from(...)` before using the result in further operations:

```rust
// Correct:
Integer::from(&half * &half) * swing

// Wrong (will not compile):
&half * &half * swing
```

This pattern appears in `factorial_rec` where the squared half-factorial is materialized before multiplying by the swing value.

## Code Layout (`src/main.rs`)

- `fn sieve(n: u64) -> Vec<u32>` — bytearray sieve of Eratosthenes; returns all primes ≤ n as `u32` (memory-efficient). Returns `vec![]` for `n < 2`. Marks composites in a `Vec<bool>` then filters.

- `fn compute_swing_chunk(m: u64, primes: &[u32]) -> Integer` — Legendre-formula bit-count loop for a slice of primes. For each prime `p ≤ m`, computes `e_p = Σ (⌊m/p^j⌋ mod 2)` by repeatedly dividing `q` by `p` and counting odd quotients. Multiplies `p^e_p` into the running product. Breaks early when `p > m` — **primes must be sorted ascending**. Returns `rug::Integer`.

- `fn compute_swing(m: u64, primes: &[u32]) -> Integer` — entry point for swing computation. Filters `primes` to those ≤ m. Returns `Integer::from(1)` for an empty relevant set. Divides relevant primes into `rayon::current_num_threads()` equal chunks (minimum size 1) and dispatches each to `compute_swing_chunk` via `par_chunks`. Tree-reduces results using `reduce()` with a multiply accumulator.

- `fn factorial_rec(n: u64, primes: &[u32]) -> Integer` — recursive prime swing. Base case `n ≤ 1` returns 1. Otherwise: recurse on `n/2`, compute `swing(n)`, return `Integer::from(&half * &half) * swing`. The `Integer::from(...)` wrapper materializes the incomplete-type product before the outer multiply.

- `fn calculate_factorial(n: u64) -> Integer` — public entry point. Returns 1 for `n ≤ 1`. Otherwise sieves to `n` once and calls `factorial_rec`.

- `fn fmt_int(n: u64) -> String` — formats an integer with thousands-separator commas (e.g. `1234567` → `"1,234,567"`).

- `fn read_line_from<R: BufRead>(reader: &mut R) -> io::Result<String>` — reads one line, trims trailing newline/whitespace. Returns empty string on EOF.

- `fn prompt_n_with<R: BufRead, W: Write, E: Write>(reader, out, err) -> io::Result<u64>` — interactive loop; prints prompt to `out`, reads from `reader`, errors to `err`. Retries on non-numeric input.

- `fn run<R: BufRead, W: Write, E: Write>(n_arg: Option<&str>, reader, out, err, dir: &Path) -> io::Result<i32>` — orchestrator. Parses `n_arg` (or prompts via `prompt_n_with`), computes factorial, writes result to `dir/factorial_<n>.txt`, reports to `err`. Returns exit code.

- `fn main()` — collects `std::env::args()`, calls `run` with locked stdio and `current_dir`.

## Build

```bash
cd factorial-rs
make factorial           # cargo build --release + copy to ~/Downloads/factorial
./target/release/factorial       # interactive mode
./target/release/factorial 1000  # compute 1000!
```

## Makefile Targets

- `make factorial` — runs `cargo build --release` and copies the binary to `~/Downloads/factorial`
- `make lint` — runs `cargo clippy -- -D warnings`
- `make test` — runs lint then `cargo test`
- `make clean` — runs `cargo clean` and removes `~/Downloads/factorial`

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass.

Tests live in a `#[cfg(test)] mod tests` block at the bottom of `src/main.rs`.

Run the full suite:

```bash
cd factorial-rs
cargo test
```

Check coverage (requires `cargo-tarpaulin`):

```bash
cargo install cargo-tarpaulin   # one-time install
cargo tarpaulin --out Stdout
```

### Test coverage (97.17% line coverage, 58 tests: 50 unit + 8 integration)

| Area                                | Tests | Notes                                                                       |
| ----------------------------------- | ----- | --------------------------------------------------------------------------- |
| `sieve`                             | 6     | empty (n<2), n=2, small known primes, no composites, π(100)=25, π(1000)=168 |
| `compute_swing_chunk`               | 6     | empty primes, prime exceeds m, m=2, p2/p3/p5 contributions for m=6          |
| `compute_swing`                     | 7     | swing(0..4,6), empty primes, factorial identity check (swing(6)×3!²=6!)     |
| `factorial_rec`                     | 4     | base cases 0 and 1, 2!, 5!                                                  |
| `calculate_factorial`               | 8     | 0!..5!, 10!, 20!                                                            |
| `fmt_int`                           | 5     | zero, sub-thousand, thousands, millions, large                              |
| `read_line_from`                    | 3     | trims newline, empty input, trims whitespace                                |
| `prompt_n_with`                     | 4     | valid input, zero, retry on non-numeric, retry on negative                  |
| `run` (unit)                        | 5     | invalid arg exits 1, valid arg creates file, no arg prompts, 0!, idempotent |
| `run_returns_err_on_stdout_failure` | 1     | `run()` propagates Err when stdout write fails (FailWriter injection)       |
| `run_returns_err_on_stderr_failure` | 1     | `run()` propagates Err when stderr write fails (FailWriter injection)       |
| `run` (integration)                 | 7     | invalid arg, 0!, 5!, no-arg prompt, retry on bad input, idempotent, backend |
| `cli_unwritable_output_dir`         | 1     | non-zero exit when output directory is read-only                            |

Uncovered lines: 3 macro expansion artifacts in `prompt_n_with` loop and `run` error branch.

### Adding new tests

- Add tests to the `#[cfg(test)] mod tests` block in `src/main.rs`.
- Use known factorial values for correctness assertions (e.g. `calculate_factorial(20) == 2432902008176640000`).
- When testing `compute_swing` identity: `swing(n) × (n/2)!² == n!` for even n.

## Keeping This File Up To Date

**Update this file whenever you change the code.** Future Claude sessions rely on it -- stale docs are worse than none. Specifically:

- New or renamed function / constant → update Code Layout
- Makefile target added or removed → update the Makefile targets list
- Dependency added → update `install_deps.sh` and parent `CLAUDE.md`
- Test added or coverage changes → update the Testing coverage table
- Behaviour or algorithm change → update the Repository Overview or Code Layout

Also update the top-level `CLAUDE.md` and `factorial/CLAUDE.md` if the change affects the repository overview or quick-reference targets.
