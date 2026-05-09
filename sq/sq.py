#!/usr/bin/env python3
"""Generate all perfect squares with at most 10^N decimal digits."""

import argparse
import io
import sys


def generate_squares(max_digits: int):
    """Yield every perfect square with at most max_digits decimal digits.

    Uses k*k < 10^max_digits as the stopping criterion (equivalent to
    len(str(k*k)) <= max_digits but avoids per-iteration string conversion).
    """
    limit = 10 ** max_digits
    k = 1
    while k * k < limit:
        yield k * k, k
        k += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate all perfect squares with up to 10^N digits",
        epilog="Run without arguments for an interactive prompt.",
    )
    parser.add_argument(
        "exponent",
        type=int,
        nargs="?",
        help="N: generates perfect squares with up to 10^N digits (max 1)",
    )
    return parser.parse_args()


def get_exponent(args: argparse.Namespace) -> int:
    """Return validated exponent from CLI args, or prompt interactively."""
    if args.exponent is not None:
        x = args.exponent
        if x != 1:
            print("Error: N must be 1.", file=sys.stderr)
            sys.exit(1)
        return x
    while True:
        try:
            raw = input(
                "Enter N (finds all perfect squares with up to 10^N digits, max 1): "
            )
            x = int(raw)
            if x == 1:
                return x
            print("N must be 1.")
        except ValueError:
            print("Please enter a positive integer.")


def main() -> None:
    args = parse_args()
    x = get_exponent(args)
    max_digits = 10 ** x

    print("Perfect Square Generator (Python)")
    print("=" * 40)
    print(
        f"Generating all perfect squares with up to 10^{x} = {max_digits:,} digits"
    )

    try:
        buf = io.StringIO()
        count = 0
        for sq, root in generate_squares(max_digits):
            buf.write(f"{sq} | {root}\n")
            count += 1

        filename = f"sq_1e{x}.txt"
        with open(filename, "w") as f:
            f.write(buf.getvalue())

        print(f"\nFound {count:,} perfect squares with up to 10^{x} digits")
        print(f"Saved to {filename}")
        answer = input(
            f"Also display all {count:,} perfect squares? (y/n): "
        ).strip().lower()
        if answer in ("y", "yes"):
            print(buf.getvalue(), end="")
    except KeyboardInterrupt:
        print("\nGeneration interrupted.")
        sys.exit(1)
    except PermissionError as err:
        print(f"Error: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
