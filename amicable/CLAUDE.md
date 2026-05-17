# CLAUDE.md

## Repository Overview

Python CLI that finds all amicable pairs (a, b) with a < b and b ≤ 10^N.
Uses a proper-divisor sum sieve: s[n] = sum of proper divisors of n, built
in O(N log N) by iterating each d and accumulating into multiples.

## Running

```bash
make run       # python3 amicable.py (interactive)
make lint      # ruff check .
make test      # lint + unittest
make coverage  # coverage run + report
```

## Code Layout

- `proper_divisor_sum_sieve(limit)` — O(N log N) sieve, returns list[int] of length limit+1
- `find_amicable_pairs(limit)` — generator yielding (a,b) pairs with a < b <= limit
- `parse_args(argv=None)` — argparse wrapper, N is optional positional
- `get_exponent(args)` — validates N in [1,7]; interactive prompt if None
- `main()` — entry point; writes to stdout and amicable_1eN.txt

## Testing

≥90% line coverage required. Run `make coverage` to check.
