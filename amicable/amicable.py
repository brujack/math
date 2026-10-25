#!/usr/bin/env python3
"""
Find all amicable pairs (a, b) with a < b and b <= 10^N.

Uses a proper-divisor sum sieve: s[n] = sum of proper divisors of n.
Built in O(N log N) by iterating each divisor d and accumulating into multiples.

Run without arguments at a terminal for an interactive prompt, or supply N:
    python3 amicable.py [N] [--show] [--yes] [--smoke]
"""

import argparse
import sys

SMOKE_SIZE = 5
LARGE_RUN_THRESHOLD: int | None = None


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns an argparse.Namespace with size (int or None), show, yes and smoke.
    """
    parser = argparse.ArgumentParser(
        description="Find all amicable pairs with b <= 10^N",
        epilog="Run with no arguments at a terminal for interactive prompts.",
    )
    parser.add_argument(
        "size", nargs="?", type=int, metavar="N", help="exponent (limit = 10^N)"
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
        "--smoke",
        action="store_true",
        help=f"quick check at SMOKE_SIZE ({SMOKE_SIZE})",
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
    """
    Get and validate the exponent N from args.

    If args.size is None, prompt interactively. Validate that 1 <= N <= 7.
    Exit with code 1 if validation fails.

    Returns the validated exponent.
    """
    n = args.size
    if n is None:
        try:
            n = int(input("Enter exponent N (limit = 10^N, max 7): "))
        except EOFError:
            print(
                "Error: no input; pass SIZE as an argument "
                f"(e.g. python3 amicable.py {SMOKE_SIZE}).",
                file=sys.stderr,
            )
            sys.exit(1)
        except ValueError:
            print("Invalid input.", file=sys.stderr)
            sys.exit(1)
    if n < 1 or n > 7:
        print(f"N must be between 1 and 7, got {n}.", file=sys.stderr)
        sys.exit(1)
    return n


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    args = parse_args(argv)
    n = get_exponent(args)
    refuse_large_run(n, args.yes)
    limit = 10**n
    filename = f"amicable_1e{n}.txt"
    count = 0
    try:
        with open(filename, "w") as f:
            for a, b in find_amicable_pairs(limit):
                line = f"{a} {b}"
                count += 1
                if args.show:
                    print(line)
                f.write(line + "\n")
    except PermissionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Found {count} amicable pairs up to 10^{n}")
    print(f"Saved to {filename}")


if __name__ == "__main__":
    main()
