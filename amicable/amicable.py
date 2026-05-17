#!/usr/bin/env python3
"""
Find all amicable pairs (a, b) with a < b and b <= 10^N.

Uses a proper-divisor sum sieve: s[n] = sum of proper divisors of n.
Built in O(N log N) by iterating each divisor d and accumulating into multiples.

Run without arguments for an interactive prompt, or supply N directly:
    python3 amicable.py [N]
"""

import argparse
import sys


def proper_divisor_sum_sieve(limit: int) -> list[int]:
    """
    Compute the sum of proper divisors for all integers up to limit.

    Returns a list s where s[n] = sum of proper divisors of n.
    """
    s = [0] * (limit + 1)
    for d in range(1, limit // 2 + 1):
        for multiple in range(2 * d, limit + 1, d):
            s[multiple] += d
    return s


def find_amicable_pairs(limit: int):
    """
    Find all amicable pairs (a, b) with a < b and b <= limit.

    Yields tuples (a, b) in ascending order of a.
    """
    s = proper_divisor_sum_sieve(limit)
    for a in range(2, limit + 1):
        b = s[a]
        if b > a and b <= limit and s[b] == a:
            yield a, b


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("n", nargs="?", type=int, help="Find amicable pairs up to 10^N")
    args = parser.parse_args()

    if args.n is None:
        try:
            _n = int(input("Enter N (find pairs up to 10^N): "))
        except (ValueError, EOFError):
            sys.exit(1)
    else:
        _n = args.n
    # TODO: use _n to compute amicable pairs


if __name__ == "__main__":
    main()
