# collatz

Find Collatz chain record-setters up to 10^N.

## Usage

```bash
python3 collatz.py           # interactive prompts (terminal only)
python3 collatz.py 6         # scan 1..10^6, written to file
python3 collatz.py 6 --show  # also print each record
python3 collatz.py --smoke   # quick check at N=5
```

With SIZE given the program never reads stdin; with no arguments and stdin not a terminal it exits 2 with usage. `--yes` is accepted and ignored.

Output: one line per record `<n> <chain_length>`, saved to `collatz_1eN.txt`.

## Build

```bash
make run       # python3 collatz.py
make lint      # ruff check .
make test      # lint + unittest
make coverage  # coverage run + report
```
