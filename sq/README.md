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
python3 sq.py      # interactive prompt
python3 sq.py 1    # generate all squares with up to 10 digits
```

## Rust

```bash
cd sq/sq-rs
make test      # lint + all tests
make sq        # build release binary
./target/release/sq 1
```

## Output

For N=1: 99,999 perfect squares (1, 4, 9, …, 9,999,800,001). Output is buffered; you are prompted to display on screen or save to `sq_1e1.txt`.
