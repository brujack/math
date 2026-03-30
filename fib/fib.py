#!/usr/bin/env python3
"""
Generate all Fibonacci numbers with at most 10^X decimal digits.

Uses Python built-in arbitrary-precision integers — no external libraries needed.

Run without arguments for an interactive prompt, or supply X directly:
    python3 fib.py [X]
"""

import argparse
import io
import sys


def generate_fibonacci(max_digits: int):
    """Yield every Fibonacci number with at most max_digits decimal digits.

    Uses b < 10^max_digits as the stopping criterion (equivalent to
    len(str(b)) <= max_digits and avoids per-iteration string conversion).
    """
    limit = 10 ** max_digits
    a, b = 0, 1
    while b < limit:
        yield b
        a, b = b, a + b


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate all Fibonacci numbers with up to 10^X digits",
        epilog="Run without arguments for an interactive prompt.",
    )
    parser.add_argument(
        "exponent",
        type=int,
        nargs="?",
        help="X: generates Fibonacci numbers with up to 10^X digits (e.g. 3 → up to 1,000 digits)",
    )
    return parser.parse_args()


def get_exponent(args: argparse.Namespace) -> int:
    """Return the validated exponent from CLI args, or prompt interactively."""
    if args.exponent is not None:
        x = args.exponent
        if x < 1 or x > 5:
            print("Error: X must be between 1 and 5.", file=sys.stderr)
            sys.exit(1)
        return x
    while True:
        try:
            raw = input(
                "Enter X (finds all Fibonacci numbers with up to 10^X digits, max 5): "
            )
            x = int(raw)
            if 1 <= x <= 5:
                return x
            print("X must be between 1 and 5.")
        except ValueError:
            print("Please enter a positive integer.")


def main() -> None:
    args = parse_args()
    x = get_exponent(args)
    max_digits = 10 ** x

    print("Fibonacci Number Generator (Python)")
    print("=" * 40)

    if x >= 4:
        print(
            f"Warning: X={x} means Fibonacci numbers with up to {max_digits:,} digits "
            f"— this may take a long time"
        )
        print("         and produce a very large output file.")
        answer = input("Continue? (y/n): ").strip().lower()
        if answer not in ("y", "yes"):
            return

    print(
        f"Generating all Fibonacci numbers with up to 10^{x} = {max_digits:,} digits"
    )

    if x <= 2:
        # Small result: buffer in memory, let user choose to display or save.
        buf = io.StringIO()
        count = 0
        for fib in generate_fibonacci(max_digits):
            buf.write(str(fib))
            buf.write("\n")
            count += 1

        print(f"\nFound {count:,} Fibonacci numbers with up to 10^{x} digits")
        answer = input(
            f"Display all {count:,} Fibonacci numbers? (y/n): "
        ).strip().lower()
        if answer in ("y", "yes"):
            print(buf.getvalue(), end="")
        else:
            filename = f"fib_1e{x}.txt"
            with open(filename, "w") as f:
                f.write(buf.getvalue())
            print(f"Saved to {filename}")
    else:
        # Large result: stream directly to file.
        filename = f"fib_1e{x}.txt"
        print(f"\nSaving to {filename}...")
        count = 0
        with open(filename, "w", buffering=8 * 1024 * 1024) as f:
            for fib in generate_fibonacci(max_digits):
                f.write(str(fib))
                f.write("\n")
                count += 1

        print(f"Found {count:,} Fibonacci numbers with up to 10^{x} digits")
        print(f"Saved to {filename}")


if __name__ == "__main__":
    main()
