# factorial

Compute N! (N factorial) to arbitrary precision using the **prime swing algorithm**.

Two implementations:

| Implementation | Directory       | Description                                                                           |
| -------------- | --------------- | ------------------------------------------------------------------------------------- |
| Python         | `factorial.py`  | gmpy2/GMP fast path with plain int fallback; parallel swing via `ProcessPoolExecutor` |
| Rust           | `factorial-rs/` | `rug`/GMP with rayon parallel chunks                                                  |

## Algorithm

Prime swing identity: `n! = swing(n) × (⌊n/2⌋!)²` (Luschny).

`swing(m) = ∏ p^e_p` where `e_p = Σ_{j≥1} (⌊m/p^j⌋ mod 2)`. The recursion bottoms out at `n ≤ 1`. Primes are computed once with a sieve of Eratosthenes, then reused across all recursive levels.

## Requirements

| Component   | Python                        | Rust              |
| ----------- | ----------------------------- | ----------------- |
| Runtime     | Python 3.9+                   | Rust 1.85+        |
| Math lib    | `gmpy2` (optional, fast path) | `rug` (wraps GMP) |
| Native libs | GMP + MPFR (for gmpy2)        | GMP + MPFR        |

## Quick Start

### Python

```bash
cd factorial
bash install_deps.sh   # install GMP, gmpy2, ruff, coverage (one time)
make run               # interactive prompt
python3 factorial.py 1000  # compute 1000!
make test              # run unit tests
```

### Rust

```bash
cd factorial/factorial-rs
bash install_deps.sh   # install GMP + Rust toolchain (one time)
make factorial         # build release binary → ~/Downloads/factorial
./target/release/factorial 1000
make test
```

## Makefile Targets

### Python (`factorial/`)

| Target     | Command                                            |
| ---------- | -------------------------------------------------- |
| `run`      | `python3 factorial.py`                             |
| `lint`     | `ruff check .`                                     |
| `test`     | lint, then `python3 -m unittest test_factorial -v` |
| `coverage` | `coverage run` + report                            |
| `clean`    | remove `__pycache__` and `.coverage`               |

### Rust (`factorial/factorial-rs/`)

| Target      | Command                                          |
| ----------- | ------------------------------------------------ |
| `factorial` | `cargo build --release` + copy to `~/Downloads/` |
| `lint`      | `cargo clippy -- -D warnings`                    |
| `test`      | lint, then `cargo test`                          |
| `clean`     | `cargo clean` + remove `~/Downloads/factorial`   |

## Output

Both implementations always write the result to `factorial_<N>.txt` in the current working directory and print the digit count and elapsed time. The output file is overwritten on each run (idempotent).

Generated `factorial_*.txt` files are large artifacts and are not committed to git.
