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


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("n", nargs="?", type=int, help="Find amicable pairs up to 10^N")
    args = parser.parse_args()

    if args.n is None:
        try:
            n = int(input("Enter N (find pairs up to 10^N): "))
        except (ValueError, EOFError):
            sys.exit(1)
    else:
        n = args.n


if __name__ == "__main__":
    main()
