#!/usr/bin/env python3
"""
Find Collatz chain record-setters up to 10^N.

Vector memoization: cache[n] = chain_length(n) + 1 (0 = not computed).
Seed: cache[1] = 1. For each n, walk until a cached value, back-fill.

Run without arguments for an interactive prompt, or supply N directly:
    python3 collatz.py [N]
"""

import argparse
import array
import sys


def collatz_next(n: int) -> int:
    return n // 2 if n % 2 == 0 else 3 * n + 1


def collatz_length(n: int, cache: array.array) -> int:
    """Return chain_length(n), back-filling cache for all values encountered.

    cache[k] = chain_length(k) + 1, or 0 if not yet computed.
    cache[1] must be pre-seeded to 1 by the caller.
    Short-circuit: curr <= limit is checked before cache[curr] to avoid IndexError.
    """
    limit = len(cache) - 1
    path: list[int] = []
    curr = n
    while not (curr <= limit and cache[curr] != 0):
        path.append(curr)
        curr = collatz_next(curr)
    base = cache[curr]
    for i, val in enumerate(reversed(path)):
        if val <= limit:
            cache[val] = base + i + 1
    return cache[n] - 1


def generate_records(limit: int):
    """Yield (n, chain_length) for each record-setter in 1..limit.

    Allocates array.array('I', ...) of size limit+1 (4 bytes per entry).
    """
    cache: array.array = array.array("I", [0] * (limit + 1))
    cache[1] = 1
    max_len = -1
    for n in range(1, limit + 1):
        length = collatz_length(n, cache)
        if length > max_len:
            max_len = length
            yield n, length


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find Collatz chain record-setters up to 10^N",
        epilog="Run without arguments for an interactive prompt.",
    )
    parser.add_argument(
        "exponent",
        type=int,
        nargs="?",
        help="N: scans 1..10^N for chain-length records (1-12)",
    )
    return parser.parse_args()


def get_exponent(args: argparse.Namespace) -> int:
    """Return validated N from CLI args, or prompt interactively."""
    if args.exponent is not None:
        n = args.exponent
        if n < 1 or n > 12:
            print("Error: N must be between 1 and 12.", file=sys.stderr)
            sys.exit(1)
        if n > 7:
            mb = 4 * 10**n // 1_000_000
            print(
                f"Warning: N={n} requires ~{mb} MB and may be very slow in Python.",
                file=sys.stderr,
            )
        return n
    while True:
        try:
            raw = input("Enter N (scans 1..10^N for Collatz records, max 12): ")
            n = int(raw)
            if 1 <= n <= 12:
                if n > 7:
                    mb = 4 * 10**n // 1_000_000
                    print(f"Warning: N={n} requires ~{mb} MB and may be very slow.")
                return n
            print("N must be between 1 and 12.")
        except ValueError:
            print("Please enter a positive integer.")


def main() -> None:
    args = parse_args()
    n = get_exponent(args)
    limit = 10**n

    print("Collatz Record Finder (Python)")
    print("=" * 40)
    print(f"Scanning 1..10^{n} = {limit:,} for chain-length records")
    print()

    try:
        records = []
        for num, length in generate_records(limit):
            print(f"{num} {length}")
            records.append((num, length))

        filename = f"collatz_1e{n}.txt"
        with open(filename, "w") as f:
            for num, length in records:
                f.write(f"{num} {length}\n")
        print(f"\nSaved {len(records)} records to {filename}")

    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except PermissionError as err:
        print(f"Error: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
