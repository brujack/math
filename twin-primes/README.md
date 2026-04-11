# twin-primes

Finds every twin prime pair (p, p+2) where both primes are less than 10^N.

## Implementation

- Rust (`twin-primes/twin-primes-rs/`) — segmented Sieve of Eratosthenes; packed bitset segments (32 KB each, fits in L2 cache); memory usage is constant regardless of N.

## Usage

```bash
cd twin-primes/twin-primes-rs
make twin-primes
./target/release/twin-primes <N>
```

Output is written to `twin-primes_1e{N}.txt`, one pair per line:

```
3 | 5
5 | 7
11 | 13
...
```

## Quick Reference

```bash
make twin-primes   # build release binary
make lint          # cargo clippy -- -D warnings
make test          # lint + cargo test
make clean         # remove build artifacts
```
