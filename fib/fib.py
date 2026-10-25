#!/usr/bin/env python3
"""Generate all Fibonacci numbers with at most 10^X decimal digits.

Uses Python built-in arbitrary-precision integers — no external libraries needed.

Run with no arguments at a terminal for interactive prompts, or supply SIZE:
    python3 fib.py [SIZE] [--show] [--yes] [--smoke]
"""

import argparse
import io
import sys


def generate_fibonacci(max_digits: int):
    """Yield every Fibonacci number with at most max_digits decimal digits.

    Uses b < 10^max_digits as the stopping criterion (equivalent to
    len(str(b)) <= max_digits and avoids per-iteration string conversion).
    """
    limit = 10**max_digits
    a, b = 0, 1
    while b < limit:
        yield b
        a, b = b, a + b


SMOKE_SIZE = 3
LARGE_RUN_THRESHOLD: int | None = 4


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate all Fibonacci numbers with up to 10^X digits",
        epilog="Run with no arguments at a terminal for interactive prompts.",
    )
    parser.add_argument(
        "size",
        nargs="?",
        type=int,
        metavar="X",
        help="X: generates Fibonacci numbers with up to 10^X digits (e.g. 3 → up to 1,000 digits)",
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
    """Return the validated exponent from CLI args, or prompt interactively."""
    if args.size is not None:
        x = args.size
        if x < 1 or x > 5:
            print("Error: X must be between 1 and 5.", file=sys.stderr)
            sys.exit(1)
        refuse_large_run(x, args.yes)
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
        except EOFError:
            print()  # end the prompt line, as ask_yes does
            print(
                f"Error: no input; pass SIZE as an argument (e.g. python3 fib.py {SMOKE_SIZE}).",
                file=sys.stderr,
            )
            sys.exit(1)
        except ValueError:
            print("Please enter a positive integer.")


def ask_yes(prompt: str) -> bool:
    """Ask a y/n question; end of input (stdin closed, as in CI) reads as no."""
    try:
        answer = input(prompt)
    except EOFError:
        print()
        return False
    return answer.strip().lower() in ("y", "yes")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    x = get_exponent(args)
    max_digits = 10**x
    # Python 3.11+ refuses str() on ints over 4,300 digits; X >= 4 writes up to
    # 10^X-digit numbers, so lift the cap for this CLI process.
    sys.set_int_max_str_digits(0)

    print("Fibonacci Number Generator (Python)")
    print("=" * 40)

    try:
        # The argument path was gated by refuse_large_run; only the interactive
        # path still asks.
        if (
            args.size is None
            and LARGE_RUN_THRESHOLD is not None
            and x >= LARGE_RUN_THRESHOLD
        ):
            print(
                f"Warning: X={x} means Fibonacci numbers with up to {max_digits:,} digits "
                f"— this may take a long time"
            )
            print("         and produce a very large output file.")
            if not ask_yes("Continue? (y/n): "):
                return

        print(
            f"Generating all Fibonacci numbers with up to 10^{x} = {max_digits:,} digits"
        )
        filename = f"fib_1e{x}.txt"

        if x <= 2:
            # Small result: buffer in memory, then write the file.
            buf = io.StringIO()
            count = 0
            for fib in generate_fibonacci(max_digits):
                buf.write(str(fib))
                buf.write("\n")
                count += 1

            with open(filename, "w") as f:
                f.write(buf.getvalue())
            if args.show:
                print(buf.getvalue(), end="")
            print(f"\nFound {count:,} Fibonacci numbers with up to 10^{x} digits")
            print(f"Saved to {filename}")
        else:
            # Large result: stream directly to file.
            print(f"\nSaving to {filename}...")
            count = 0
            with open(filename, "w", buffering=8 * 1024 * 1024) as f:
                for fib in generate_fibonacci(max_digits):
                    line = str(fib)
                    f.write(line)
                    f.write("\n")
                    if args.show:
                        print(line)
                    count += 1

            print(f"Found {count:,} Fibonacci numbers with up to 10^{x} digits")
            print(f"Saved to {filename}")
    except KeyboardInterrupt:
        print("\nGeneration interrupted.")
        sys.exit(1)
    except PermissionError as err:
        print(f"Error: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
