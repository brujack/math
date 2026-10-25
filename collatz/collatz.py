#!/usr/bin/env python3
"""Find Collatz chain record-setters up to 10^N.

Vector memoization: cache[n] = chain_length(n) + 1 (0 = not computed).
Seed: cache[1] = 1. For each n, walk until a cached value, back-fill.

Run with no arguments at a terminal for interactive prompts, or supply SIZE:
    python3 collatz.py [SIZE] [--show] [--yes] [--smoke]
"""

import argparse
import array
import sys

SMOKE_SIZE = 5
LARGE_RUN_THRESHOLD: int | None = None


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find Collatz chain record-setters up to 10^N",
        epilog="Run with no arguments at a terminal for interactive prompts.",
    )
    parser.add_argument(
        "size",
        nargs="?",
        type=int,
        metavar="N",
        help="N: scans 1..10^N for chain-length records (1-12)",
    )
    parser.add_argument(
        "--show", action="store_true", help="also print each result line to stdout"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a large run (ignored when this program has none)",
    )
    parser.add_argument(
        "--smoke", action="store_true", help=f"quick check at SMOKE_SIZE ({SMOKE_SIZE})"
    )
    args = parser.parse_args(argv)
    if args.smoke:
        if args.size is not None:
            parser.error("--smoke takes no SIZE")
        args.size, args.show = SMOKE_SIZE, False
    elif args.size is None and not sys.stdin.isatty():
        parser.error("SIZE is required when stdin is not a terminal")
    return args


def refuse_large_run(size: int, yes: bool) -> None:
    """Exit 1 naming --yes when size needs confirmation and --yes is absent."""
    if LARGE_RUN_THRESHOLD is not None and size >= LARGE_RUN_THRESHOLD and not yes:
        print(f"Error: {size} is a large run; pass --yes to proceed.", file=sys.stderr)
        sys.exit(1)


def get_exponent(args: argparse.Namespace) -> int:
    """Return validated N from CLI args, or prompt interactively."""
    if args.size is not None:
        n = args.size
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
        except EOFError:
            print()
            print(
                "Error: no input; pass SIZE as an argument "
                f"(e.g. python3 collatz.py {SMOKE_SIZE}).",
                file=sys.stderr,
            )
            sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    n = get_exponent(args)
    refuse_large_run(n, args.yes)
    limit = 10**n

    print("Collatz Record Finder (Python)")
    print("=" * 40)
    print(f"Scanning 1..10^{n} = {limit:,} for chain-length records")
    print()

    try:
        records = list(generate_records(limit))

        filename = f"collatz_1e{n}.txt"
        with open(filename, "w") as f:
            for num, length in records:
                f.write(f"{num} {length}\n")
        if args.show:
            for num, length in records:
                print(f"{num} {length}")
        print(f"\nSaved {len(records)} records to {filename}")

    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except PermissionError as err:
        print(f"Error: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
