"""Tiny module whose cosmic-ray session fixture holds survivors and timeouts."""


def bump(x: int) -> int:
    return x + 2


def count_down(n: int) -> int:
    while n > 0:
        n -= 1
    return n
