# π Calculator

High-precision π calculator using the **Chudnovsky algorithm** with binary splitting. Two implementations are provided:

|             | Python (`pi.py`)                            | Rust (`pi-rs/`)                         |
| ----------- | ------------------------------------------- | --------------------------------------- |
| Best for    | Up to ~50M digits                           | 50M+ digits                             |
| Parallelism | `ProcessPoolExecutor` (one process per CPU) | `rayon::join()` (shared-memory threads) |
| Arithmetic  | `gmpy2` / GMP + MPFR                        | `rug` / GMP + MPFR                      |
| File I/O    | `os.pwrite(2)` threads                      | `FileExt::write_at` rayon threads       |

Both implementations use the same underlying C libraries (GMP and MPFR) and produce identical results.

---

## Dependencies

Each implementation has its own installer:

```bash
bash pi/install_deps.sh        # pi.py — GMP + MPFR, mpmath, gmpy2, coverage
bash pi/pi-rs/install_deps.sh  # pi-rs — GMP + MPFR, Rust toolchain, cargo-tarpaulin
```

Supported platforms: macOS (Homebrew), Debian/Ubuntu (apt), RHEL/Fedora (dnf).

| Dependency          | Used by           | Notes                                   |
| ------------------- | ----------------- | --------------------------------------- |
| GMP + MPFR (C libs) | `pi.py`, `pi-rs`  | Required for GMP big-integer arithmetic |
| `mpmath` (Python)   | `pi.py`           | Required fallback path                  |
| `gmpy2` (Python)    | `pi.py`           | Optional but gives 5–50× speedup        |
| `coverage` (Python) | `make coverage`   | Line coverage for `test_pi.py`          |
| Rust 1.85+          | `pi-rs`           | Installed via rustup                    |
| `cargo-tarpaulin`   | `cargo tarpaulin` | Rust line coverage tool                 |

---

## Python (`pi.py`)

### Makefile targets

| Target          | Description                                                 |
| --------------- | ----------------------------------------------------------- |
| `make run`      | Run the calculator interactively (`python3 pi.py`)          |
| `make lint`     | Lint with `ruff check .`                                    |
| `make test`     | Run lint then unit tests (`python3 -m unittest test_pi -v`) |
| `make coverage` | Run tests and print line coverage report                    |
| `make clean`    | Remove `__pycache__` and `.coverage`                        |

### Usage

```
python3 pi.py [digits]
```

Run without arguments for interactive prompts, or pass the digit count directly:

```bash
python3 pi.py 1000000
```

### Flags

| Flag           | Description                                                  |
| -------------- | ------------------------------------------------------------ |
| `digits`       | Number of decimal places to calculate (positional, optional) |
| `-h`, `--help` | Show help and exit                                           |

### Behavior

- Digits ≤ 10,000: offers to print to terminal or save to file.
- Digits > 10,000: saves automatically to `pi_<digits>_digits.txt`.
- Falls back to `mpmath` if `gmpy2` is not installed (slower).

### Tests

```bash
make test      # python3 -m unittest test_pi -v
make coverage  # run tests + print coverage report
```

61 tests, 78% line coverage. Covers `_tree_combine`, `_pwrite_all`, `_chudnovsky_bs`, `_bs_chunk_worker`, `_pi_to_str`, `_convert_gmpy2_worker`, `_convert_mpmath_worker`, `show_pi_preview`, `save_pi_to_file`, `get_target_digits`, `parse_args`, and end-to-end accuracy against the known decimal expansion of π. gmpy2-dependent tests are skipped automatically when gmpy2 is not installed.

Check coverage:

```bash
make coverage
```

---

## Rust (`pi-rs/`)

Preferred for workloads above ~50M digits. Unlike the Python version, which
serialises each chunk's `(P, Q, T)` integers through OS pipes, the Rust binary
uses `rayon::join()` for recursive parallel binary splitting — threads share
memory with zero IPC cost, giving near-linear scaling across all cores.

### Build

Requires Rust 1.85+ and GMP + MPFR (run `pi/pi-rs/install_deps.sh` first):

```bash
cd pi-rs
make pi          # cargo build --release, copies binary to ~/Downloads/pi
```

Or manually:

```bash
cd pi-rs
cargo build --release
```

The binary is at `pi-rs/target/release/pi`.

### Makefile targets

| Target       | Description                                       |
| ------------ | ------------------------------------------------- |
| `make pi`    | Build release binary and copy to `~/Downloads/pi` |
| `make lint`  | Lint with `cargo clippy -- -D warnings`           |
| `make test`  | Run lint then unit tests (`cargo test`)           |
| `make clean` | Remove build artifacts and `~/Downloads/pi`       |

### Tests

```bash
cd pi-rs
cargo test
```

18 tests in a `#[cfg(test)]` module inside `src/main.rs`, 39% line coverage. Covers `fmt_int`, `bs_leaf` (base case, index formulas, sign, counter), `bs_merge` consistency, `bs` split consistency, `pi_to_string` (format, length, no exponent notation, known digits), and `compute_pi` end-to-end accuracy at 10 and 50 decimal places.

Uncovered lines are `write_pi_file` (parallel pwrite I/O), `prompt_digits` / `read_line` (interactive stdin), and `main()` — all integration-level only.

Check coverage (requires `cargo-tarpaulin`):

```bash
cargo install cargo-tarpaulin   # one-time install
cargo tarpaulin --out Stdout
```

### Usage

```
./target/release/pi [DIGITS]
```

Run without arguments for interactive prompts, or pass the digit count directly:

```bash
./target/release/pi 100000000
```

### Flags

| Flag     | Description                                                  |
| -------- | ------------------------------------------------------------ |
| `DIGITS` | Number of decimal places to calculate (positional, optional) |
| `-h`     | Show brief help                                              |
| `--help` | Show full help with long description                         |

### Output

- Digits ≤ 10,000: prints first 100 decimal places as a preview, then offers to display all digits or save to file.
- Digits > 10,000: saves automatically to `pi_<digits>_digits.txt` using parallel `pwrite` chunks.
- Progress and timing information is printed to stderr.

### Example

```
$ ./target/release/pi 50000000
High-Precision π Calculator (Rust/Rayon)
========================================
Calculating π to 50,000,000 decimal places…
Backend: Chudnovsky / rug+GMP+MPFR / rayon (20 threads)
  Series: 3,524,288 terms, 20 threads, threshold 512
  Computing series:  100%  (3,524,288 terms)
  Series done in 12.34s
  Computing final value (166,097,310 bits)…
  Value done in 8.21s
  Converting to decimal string…
  Conversion done in 4.56s

Done in 25.11s

Saving to pi_50000000_digits.txt…
  Writing: 100%  (47.7 MB)  38.5 MB/s
Full precision π saved to pi_50000000_digits.txt
```

---

## Performance Considerations

### Why both implementations exist

Both implementations call the same underlying C libraries (GMP and MPFR), so the
**arithmetic throughput is identical**. The difference is in how parallelism and
data movement are handled around that arithmetic.

### Python: process-per-core with IPC overhead

The Python implementation splits `[0, N)` into one chunk per CPU core and
dispatches each chunk to a subprocess via `ProcessPoolExecutor`. Each subprocess
computes its `(P, Q, T)` triple independently, then **pickles the result and sends
it back through an OS pipe** to the main process for tree-combination.

At small digit counts this is fine — the integers are small and pickling is cheap.
But the `(P, Q, T)` integers grow with digit count. At 50M digits, `P` and `Q`
are each on the order of **tens of megabytes**. Serialising and deserialising
those integers through a pipe starts to dominate the wall-clock time, and adding
more cores makes it worse (more data to pipe back).

String conversion has the same issue: it runs in a subprocess to bypass the GIL,
and the result (a string of 50M characters) must be passed back through a pipe.

### Rust: shared-memory threads with zero IPC

The Rust implementation uses `rayon::join()` to recursively split the binary tree
across all cores. All threads share the same address space — the `(P, Q, T)`
integers live in a single heap allocation and are never copied or serialised.
Merging two halves is a pointer operation, not a pipe write.

The practical effect:

| Digit count | Python bottleneck                               | Rust bottleneck                                     |
| ----------- | ----------------------------------------------- | --------------------------------------------------- |
| < 1M        | Negligible IPC; gmpy2 fast                      | Same; minimal parallelism gain                      |
| 1M–10M      | IPC cost noticeable on many-core machines       | Linear scaling to all cores                         |
| 10M–50M     | IPC cost significant; adding cores may not help | Still scaling; string conversion begins to dominate |
| 50M+        | IPC + pipe buffer pressure; wall time plateaus  | Series + MPFR conversion; both parallelize cleanly  |

### Where each implementation wins

**Use Python** when:

- Digit count is below ~10M (simpler, no build step required)
- You want the `mpmath` fallback for environments where GMP is unavailable
- Interactive experimentation

**Use Rust** when:

- Digit count exceeds ~50M
- Running on a many-core machine where IPC overhead would otherwise bottleneck Python
- You need deterministic, low-jitter wall times (no GC pauses, no pickle overhead)

### String conversion

Converting an arbitrary-precision float to a 50M-character decimal string is
itself a significant operation — MPFR's `mpfr_get_str` has roughly O(n log² n)
complexity via FFT-based multiplication. Both implementations spend a comparable
fraction of total time here at large digit counts. The Rust path calls MPFR
directly with no process-boundary overhead; the Python path ships the work to a
subprocess and polls for completion.

### File I/O

Both implementations use `pwrite(2)`-style parallel writes — the file is
pre-allocated to its final size and multiple threads write non-overlapping chunks
concurrently. At digit counts where the output file is larger than the page
cache, I/O time becomes significant and the parallel write strategy matters.
Wall-clock file write time scales roughly linearly with digit count and is similar
between the two implementations.

---

## Algorithm

Both implementations use **Chudnovsky binary splitting**:

```
π = 426880 × √10005 × Q / T
```

The series `[0, N)` is split recursively into halves, each half computed
independently, then merged. Each term contributes ≈14.18 decimal digits, so
roughly `digits / 14` terms are needed.

Merge formula for adjacent ranges `[a,m)` and `[m,b)`:

```
P(a,b) = P(a,m) × P(m,b)
Q(a,b) = Q(a,m) × Q(m,b)
T(a,b) = Q(m,b) × T(a,m) + P(a,m) × T(m,b)
```

---

## Output Files

Files named `pi_<digits>_digits.txt` are generated artifacts. They can be
large (1 byte per digit) and should not be committed to version control.
