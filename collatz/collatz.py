#!/usr/bin/env python3
"""
Find Collatz chain record-setters up to 10^N.

Vector memoization: cache[n] = chain_length(n) + 1 (0 = not computed).
Seed: cache[1] = 1. For each n, walk until a cached value, back-fill.

Run without arguments for an interactive prompt, or supply N directly:
    python3 collatz.py [N]
"""


if __name__ == "__main__":
    pass
