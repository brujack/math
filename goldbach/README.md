# goldbach

Find all Goldbach pairs for even numbers up to 10^N.

Goldbach's conjecture: every even integer > 2 is the sum of two primes.
This tool verifies the conjecture up to 10^N and records every pair.

## Usage

```bash
./target/release/goldbach        # interactive prompt
./target/release/goldbach 5      # all pairs for even n in 4..10^5
```

Output: one line per pair `n p q` (p ≤ q, p + q = n), saved to `goldbach_1eN.txt`.

## Build

```bash
cd goldbach-rs
make goldbach   # cargo build --release
make lint       # cargo fmt --check + clippy
make test       # lint + cargo test
```

## Output size

N=5: ~285 MB. N=6: ~20 GB. N>6: may exceed 1 TB — proceed with caution.
