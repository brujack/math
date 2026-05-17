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


def parse_args(argv=None) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns an argparse.Namespace with N attribute (int or None).
    """
    parser = argparse.ArgumentParser(
        description="Find all amicable pairs with b <= 10^N"
    )
    parser.add_argument("N", nargs="?", type=int, help="exponent (limit = 10^N)")
    return parser.parse_args(argv)


def get_exponent(args: argparse.Namespace) -> int:
    """
    Get and validate the exponent N from args.

    If args.N is None, prompt interactively. Validate that 1 <= N <= 7.
    Exit with code 1 if validation fails.

    Returns the validated exponent.
    """
    n = args.N
    if n is None:
        try:
            n = int(input("Enter exponent N (limit = 10^N, max 7): "))
        except (ValueError, EOFError):
            print("Invalid input.", file=sys.stderr)
            sys.exit(1)
    if n < 1 or n > 7:
        print(f"N must be between 1 and 7, got {n}.", file=sys.stderr)
        sys.exit(1)
    return n


def main() -> None:
    """Main entry point."""
    args = parse_args()
    n = get_exponent(args)
    limit = 10 ** n
    filename = f"amicable_1e{n}.txt"
    try:
        with open(filename, "w") as f:
            for a, b in find_amicable_pairs(limit):
                line = f"{a} {b}"
                print(line)
                f.write(line + "\n")
    except PermissionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
