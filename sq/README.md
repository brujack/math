# sq — Perfect Squares Calculator

Generates every perfect square with at most 10^N decimal digits. N=1 is the only valid value (produces 99,999 squares up to 10 digits).

## Python

```bash
cd sq
make run       # interactive prompt
make test      # lint + all tests
make coverage  # coverage report
```

Or directly:

```bash
python3 sq.py           # interactive prompts (terminal only)
python3 sq.py 1         # generate all squares with up to 10 digits, written to file
python3 sq.py 1 --show  # also print them
python3 sq.py --smoke   # quick check at N=1
```

## Rust

```bash
cd sq/sq-rs
make test      # lint + all tests
make sq        # build release binary
./target/release/sq 1
```

## Output

For N=1: 99,999 perfect squares (1, 4, 9, …, 9,999,800,001). Output is always saved to `sq_1e1.txt`; `--show` also prints it. With N given the program never reads stdin; `--yes` is accepted and ignored.
