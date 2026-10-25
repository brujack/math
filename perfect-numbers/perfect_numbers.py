#!/usr/bin/env python3
"""Find all perfect numbers up to 10^N.

A perfect number equals the sum of its proper divisors. All known even perfect
numbers have the form 2^(p-1) * (2^p - 1) where 2^p - 1 is a Mersenne prime.

Uses the Lucas-Lehmer primality test and the multiplicative sigma formula.

Run with no arguments at a terminal for interactive prompts, or supply SIZE:
    python3 perfect_numbers.py [SIZE] [--show] [--yes] [--smoke]
"""

import argparse
import sys

SMOKE_SIZE = 6
LARGE_RUN_THRESHOLD: int | None = None


def lucas_lehmer(p: int) -> bool:
    """Return True if M_p = 2^p - 1 is a Mersenne prime.

    Lucas-Lehmer test: s_0 = 4; s_i = s_{i-1}^2 - 2 mod M_p.
    M_p is prime iff s_{p-2} == 0. Special case: M_2 = 3 is prime.
    """
    if p == 2:
        return True
    mp = (1 << p) - 1
    s = 4
    for _ in range(p - 2):
        s = (s * s - 2) % mp
    return s == 0


def verify_perfect(p: int) -> bool:
    """Verify 2^(p-1) * (2^p - 1) is perfect using the sigma formula.

    sigma(2^(p-1) * M_p) = (2^p - 1) * 2^p = 2n.
    """
    mp = (1 << p) - 1
    n = (1 << (p - 1)) * mp
    sigma = mp * (mp + 1)  # (2^p - 1) * 2^p
    return sigma == 2 * n


def generate_perfect_numbers(limit: int):
    """Yield (p, n) for each perfect number n <= limit.

    Tests every prime p up to the bound derived from limit.
    """
    if limit < 6:
        return
    # 2^(2p-1) <= limit => p <= (bit_length + 1) / 2
    max_p = (limit.bit_length() // 2) + 3
    for p in range(2, max_p + 1):
        if not is_prime(p):
            continue
        if not lucas_lehmer(p):
            continue
        mp = (1 << p) - 1
        n = (1 << (p - 1)) * mp
        if n > limit:
            return
        yield p, n


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find all perfect numbers up to 10^N",
        epilog="Run with no arguments at a terminal for interactive prompts.",
    )
    parser.add_argument(
        "size",
        nargs="?",
        type=int,
        metavar="N",
        help="N: finds perfect numbers up to 10^N (1-54)",
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
        if n < 1 or n > 54:
            print("Error: N must be between 1 and 54.", file=sys.stderr)
            sys.exit(1)
        return n
    while True:
        try:
            raw = input("Enter N (finds perfect numbers up to 10^N, max 54): ")
            n = int(raw)
            if 1 <= n <= 54:
                return n
            print("N must be between 1 and 54.")
        except ValueError:
            print("Please enter a positive integer.")
        except EOFError:
            print()
            print(
                "Error: no input; pass SIZE as an argument "
                f"(e.g. python3 perfect_numbers.py {SMOKE_SIZE}).",
                file=sys.stderr,
            )
            sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    n = get_exponent(args)
    refuse_large_run(n, args.yes)
    limit = 10**n

    print("Perfect Number Finder (Python)")
    print("=" * 40)
    print(f"Finding perfect numbers up to 10^{n} = {limit:,}")
    print()

    try:
        results = []
        max_p = (limit.bit_length() // 2) + 3
        for p in range(2, max_p + 1):
            if not is_prime(p):
                continue
            mp = (1 << p) - 1
            if not lucas_lehmer(p):
                print(f"p={p}: M_{p}={mp} [not prime]")
                continue
            pn = (1 << (p - 1)) * mp
            digits = len(str(pn))
            s = "digit" if digits == 1 else "digits"
            if pn > limit:
                print(
                    f"p={p}: M_{p}={mp} [Mersenne prime] -> {pn} ({digits} {s}, exceeds limit)"
                )
                break
            verified = verify_perfect(p)
            status = "verified" if verified else "FAILED"
            print(
                f"p={p}: M_{p}={mp} [Mersenne prime] -> {pn} ({digits} {s}, {status})"
            )
            results.append(pn)

        count = len(results)
        if args.show:
            for pn in results:
                print(pn)
        print()
        s = "number" if count == 1 else "numbers"
        print(f"Found {count} perfect {s} up to 10^{n}")

        filename = f"perfect-numbers_1e{n}.txt"
        with open(filename, "w") as f:
            for pn in results:
                f.write(str(pn))
                f.write("\n")
        print(f"Saved to {filename}")

    except KeyboardInterrupt:
        print("\nGeneration interrupted.")
        sys.exit(1)
    except PermissionError as err:
        print(f"Error: {err}")
        sys.exit(1)


def is_prime(n: int) -> bool:
    """Return True if n is prime. Trial division — only called for small values."""
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True


if __name__ == "__main__":
    main()
