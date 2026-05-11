#!/usr/bin/env python3
"""
Find all perfect numbers up to 10^N.

A perfect number equals the sum of its proper divisors. All known even perfect
numbers have the form 2^(p-1) * (2^p - 1) where 2^p - 1 is a Mersenne prime.

Uses the Lucas-Lehmer primality test and the multiplicative sigma formula.

Run without arguments for an interactive prompt, or supply N directly:
    python3 perfect_numbers.py [N]
"""

import argparse
import sys


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
    sigma = mp * (mp + 1)   # (2^p - 1) * 2^p
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find all perfect numbers up to 10^N",
        epilog="Run without arguments for an interactive prompt.",
    )
    parser.add_argument(
        "exponent",
        type=int,
        nargs="?",
        help="N: finds perfect numbers up to 10^N (1-54)",
    )
    return parser.parse_args()


def get_exponent(args: argparse.Namespace) -> int:
    """Return validated N from CLI args, or prompt interactively."""
    if args.exponent is not None:
        n = args.exponent
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


def main() -> None:
    args = parse_args()
    n = get_exponent(args)
    limit = 10 ** n

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
                print(f"p={p}: M_{p}={mp} [Mersenne prime] -> {pn} ({digits} {s}, exceeds limit)")
                break
            verified = verify_perfect(p)
            status = "verified" if verified else "FAILED"
            print(f"p={p}: M_{p}={mp} [Mersenne prime] -> {pn} ({digits} {s}, {status})")
            results.append(pn)

        count = len(results)
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
