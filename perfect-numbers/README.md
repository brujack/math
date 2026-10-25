# perfect-numbers

Find all perfect numbers up to 10^N.

Uses the Lucas-Lehmer Mersenne primality test and the multiplicative sigma
formula to find and verify all even perfect numbers up to 10^N. Supports N up
to 54, covering all 10 known perfect numbers.

| Command         | Description            |
| --------------- | ---------------------- |
| `make run`      | Run interactively      |
| `make test`     | Lint + unit tests      |
| `make coverage` | Coverage report        |
| `make clean`    | Remove build artifacts |

```bash
python3 perfect_numbers.py           # interactive prompts (terminal only)
python3 perfect_numbers.py 6         # perfect numbers up to 10^6, written to file
python3 perfect_numbers.py 6 --show  # also print them
python3 perfect_numbers.py --smoke   # quick check at N=6
```

With N given the program never reads stdin; with no arguments and stdin not a terminal it exits 2 with usage. `--yes` is accepted and ignored.

For the optimised Rust implementation: `cd perfect-numbers-rs && make perfect-numbers`
