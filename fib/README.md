# fib

Generate every Fibonacci number with at most 10^X decimal digits.

Two implementations:

| Implementation | File      | Description                                             |
| -------------- | --------- | ------------------------------------------------------- |
| Python         | `fib.py`  | Built-in arbitrary-precision integers, no external deps |
| Rust           | `fib-rs/` | `rug`/GMP for best performance at large digit counts    |

## Quick Start

### Python

```bash
cd fib
bash install_deps.sh   # install ruff + coverage (one time)
make run               # interactive prompts (terminal only)
python3 fib.py 3       # generate Fibonacci numbers with up to 1,000 digits
python3 fib.py 3 --show  # also print them
python3 fib.py 4 --yes   # X >= 4 needs --yes (else exit 1)
python3 fib.py --smoke   # quick check at X=3
make test              # run unit tests
```

The Python program never reads stdin when X is given and always writes to `fib_1eX.txt`; with no arguments and stdin not a terminal it exits 2 with usage.

### Rust

```bash
cd fib/fib-rs
bash install_deps.sh   # install GMP + Rust toolchain (one time)
make fib               # cargo build --release (binary in target/release/fib)
make install           # build, then copy to ${XDG_BIN_HOME:-~/.local/bin}/fib
./target/release/fib 3
make test
```

## Usage

Both implementations accept an optional positional argument X (1–5):

```
fib [X]
```

| X   | Max digits | Approx count | Approx output size |
| --- | ---------- | ------------ | ------------------ |
| 1   | 10         | ~47          | tiny               |
| 2   | 100        | ~478         | tiny               |
| 3   | 1,000      | ~4,785       | ~2.4 MB            |
| 4   | 10,000     | ~47,847      | ~240 MB (warns)    |
| 5   | 100,000    | ~478,468     | ~24 GB (warns)     |

Output: one Fibonacci number per line. The Python program writes to `fib_1eX.txt`; `--show` also prints the numbers.

## Output Files

Generated `fib_1eX.txt` files are large artifacts and are not committed to git.
