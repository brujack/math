# collatz

Find Collatz chain record-setters up to 10^N.

## Usage

```bash
python3 collatz.py        # interactive prompt
python3 collatz.py 6      # scan 1..10^6
```

Output: one line per record `<n> <chain_length>`, saved to `collatz_1eN.txt`.

## Build

```bash
make run       # python3 collatz.py
make lint      # ruff check .
make test      # lint + unittest
make coverage  # coverage run + report
```
