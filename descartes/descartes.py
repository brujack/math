#!/usr/bin/env python3
"""Descartes circle theorem helpers and integral Apollonian packings.

Three pieces so far: the fourth-curvature formula, root validation with
reduction to the packing's canonical root, and an enumerator that counts every
circle of curvature at most n and records which curvatures occur.
Standard library only.
"""

import math


class BadInput(Exception):
    """The input is malformed (CLI exit 2)."""


class NoSolution(Exception):
    """The input is well formed but has no answer (CLI exit 1)."""


def descartes_fourth(k1: float, k2: float, k3: float) -> tuple[float, float]:
    """Return both curvatures tangent to three mutually tangent circles."""
    s = k1 * k2 + k2 * k3 + k3 * k1
    if s < -1e-12 * max(abs(k1), abs(k2), abs(k3)):
        raise NoSolution(
            f"descartes_fourth({k1}, {k2}, {k3}): no circle is tangent to all "
            f"three, k1k2+k2k3+k3k1 = {s} is negative"
        )
    root = 2.0 * math.sqrt(max(s, 0.0))
    total = k1 + k2 + k3
    return total + root, total - root


def validate_root(
    a: object, b: object, c: object, d: object
) -> tuple[int, int, int, int]:
    """Check a root quadruple and reduce it to the packing's canonical root."""
    values: list[int] = []
    for v in (a, b, c, d):
        if isinstance(v, bool) or not isinstance(v, int):
            raise BadInput(
                f"root ({a}, {b}, {c}, {d}): curvatures must be integers, got {v!r}"
            )
        values.append(v)
    shown = f"({values[0]}, {values[1]}, {values[2]}, {values[3]})"
    total = sum(values)
    squares = 2 * sum(v * v for v in values)
    if total * total != squares:
        raise NoSolution(
            f"root {shown} is not a Descartes quadruple: "
            f"(Σk)²={total * total}, 2Σk²={squares}"
        )
    if sum(1 for v in values if v < 0) != 1:
        raise NoSolution(
            f"root {shown} needs exactly one negative curvature (the bounding circle)"
        )
    values.sort()
    while True:
        reflected = 2 * (values[0] + values[1] + values[2]) - values[3]
        if reflected >= values[3]:
            break
        values[3] = reflected
        values.sort()
    return values[0], values[1], values[2], values[3]


def _mark(bitmap: bytearray, k: int) -> None:
    """Set bit k of the bitmap."""
    bitmap[k >> 3] |= 1 << (k & 7)


def pack(root: tuple[int, int, int, int], n: int) -> tuple[int, bytearray]:
    """Count circles of curvature 1..n in the packing and mark their curvatures."""
    bitmap = bytearray(n // 8 + 1)
    count = 0
    for k in root:
        if 0 < k <= n:
            count += 1
            _mark(bitmap, k)
    total = sum(root)
    stack: list[tuple[list[int], int]] = []
    for i in range(4):
        k = 2 * (total - root[i]) - root[i]
        if k <= n:
            quad = list(root)
            quad[i] = k
            stack.append((quad, i))
    while stack:
        quad, j = stack.pop()
        count += 1
        _mark(bitmap, quad[j])
        total = sum(quad)
        for i in range(4):
            if i == j:
                continue
            k = 2 * (total - quad[i]) - quad[i]
            if quad[i] < k <= n:
                child = list(quad)
                child[i] = k
                stack.append((child, i))
    return count, bitmap


def distinct(bitmap: bytearray) -> list[int]:
    """Return the curvatures marked in the bitmap, ascending."""
    return [k for k in range(len(bitmap) * 8) if bitmap[k >> 3] >> (k & 7) & 1]
