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

For the optimised Rust implementation: `cd perfect-numbers-rs && make perfect-numbers`
