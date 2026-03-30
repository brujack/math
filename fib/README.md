# fib

Generate every Fibonacci number with at most 10^X decimal digits.

Two implementations:

| Implementation | File | Description |
|----------------|------|-------------|
| Python | `fib.py` | Built-in arbitrary-precision integers, no external deps |
| Rust | `fib-rs/` | `rug`/GMP for best performance at large digit counts |

## Quick Start

### Python

```bash
cd fib
bash install_deps.sh   # install ruff + coverage (one time)
make run               # interactive prompt
python3 fib.py 3       # generate Fibonacci numbers with up to 1,000 digits
make test              # run unit tests
```

### Rust

```bash
cd fib/fib-rs
bash install_deps.sh   # install GMP + Rust toolchain (one time)
make fib               # build release binary → ~/Downloads/fib
./target/release/fib 3
make test
```

## Usage

Both implementations accept an optional positional argument X (1–5):

```
fib [X]
```

| X | Max digits | Approx count | Approx output size |
|---|-----------|--------------|-------------------|
| 1 | 10 | ~47 | tiny |
| 2 | 100 | ~478 | tiny |
| 3 | 1,000 | ~4,785 | ~2.4 MB |
| 4 | 10,000 | ~47,847 | ~240 MB (warns) |
| 5 | 100,000 | ~478,468 | ~24 GB (warns) |

Output: one Fibonacci number per line. Small results (X ≤ 2) are buffered and offered for display or file save. Larger results stream directly to `fib_1eX.txt`.

## Output Files

Generated `fib_1eX.txt` files are large artifacts and are not committed to git.
