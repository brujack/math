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
    limit = 10**max_digits
    k = 1
    while k * k < limit:
        yield k * k, k
        k += 1


SMOKE_SIZE = 1
LARGE_RUN_THRESHOLD: int | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate all perfect squares with up to 10^N digits",
        epilog="Run with no arguments at a terminal for interactive prompts.",
    )
    parser.add_argument(
        "size",
        nargs="?",
        type=int,
        metavar="N",
        help="N: generates perfect squares with up to 10^N digits (max 1)",
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
    """Return validated exponent from CLI args, or prompt interactively."""
    if args.size is not None:
        x = args.size
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
        except EOFError:
            print()  # end the prompt line
            print(
                "Error: no input; pass SIZE as an argument "
                f"(e.g. python3 sq.py {SMOKE_SIZE}).",
                file=sys.stderr,
            )
            sys.exit(1)
        except ValueError:
            print("Please enter a positive integer.")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    x = get_exponent(args)
    refuse_large_run(x, args.yes)
    max_digits = 10**x

    print("Perfect Square Generator (Python)")
    print("=" * 40)
    print(f"Generating all perfect squares with up to 10^{x} = {max_digits:,} digits")

    try:
        buf = io.StringIO()
        count = 0
        for sq, root in generate_squares(max_digits):
            buf.write(f"{sq} | {root}\n")
            count += 1

        filename = f"sq_1e{x}.txt"
        with open(filename, "w") as f:
            f.write(buf.getvalue())

        if args.show:
            print(buf.getvalue(), end="")
        print(f"\nFound {count:,} perfect squares with up to 10^{x} digits")
        print(f"Saved to {filename}")
    except KeyboardInterrupt:
        print("\nGeneration interrupted.")
        sys.exit(1)
    except PermissionError as err:
        print(f"Error: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
