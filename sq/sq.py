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
        yield k * k
        k += 1


def parse_args() -> argparse.Namespace:
    pass


def get_exponent(args: argparse.Namespace) -> int:
    pass


def main() -> None:
    pass


if __name__ == "__main__":
    main()
