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


def get_exponent(n: int) -> int:
    """Stub — not yet implemented."""
    raise NotImplementedError


def main() -> None:
    """Stub — not yet implemented."""
    raise NotImplementedError


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
