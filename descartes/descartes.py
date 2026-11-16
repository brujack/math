#!/usr/bin/env python3
"""Descartes circle theorem helpers and integral Apollonian packings.

Three pieces so far: the fourth-curvature formula, root validation with
reduction to the packing's canonical root, and an enumerator that counts every
circle of curvature at most n and records which curvatures occur.
Standard library only.
"""

import math

# Largest n pack accepts: Python's N = 10^K ceiling (K <= 6, spec R7), about
# 2.7e7 circles. The core enforces it so no caller can request an unbounded run.
N_MAX = 10**6


class BadInput(Exception):
    """The input is malformed (CLI exit 2)."""


class NoSolution(Exception):
    """The input is well formed but has no answer (CLI exit 1)."""


def descartes_fourth(k1: float, k2: float, k3: float) -> tuple[float, float]:
    """Return both curvatures tangent to three mutually tangent circles."""
    s = k1 * k2 + k2 * k3 + k3 * k1
    if s < -1e-12 * (abs(k1 * k2) + abs(k2 * k3) + abs(k3 * k1)):
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


def _check_reduced_root(root: tuple[int, int, int, int]) -> None:
    """Raise BadInput unless root is a sorted, reduced Descartes root."""
    total = sum(root)
    problem = ""
    if list(root) != sorted(root):
        problem = "not sorted ascending"
    elif total * total != 2 * sum(k * k for k in root):
        problem = "not a Descartes quadruple"
    elif sum(1 for k in root if k < 0) != 1:
        problem = "needs exactly one negative curvature"
    elif 2 * (root[0] + root[1] + root[2]) - root[3] < root[3]:
        problem = "not reduced (use validate_root first)"
    if problem:
        raise BadInput(f"pack(root={root}, ...): root is {problem}")


def _check_n(n: int) -> None:
    """Raise BadInput unless 0 <= n <= N_MAX."""
    if n < 0:
        raise BadInput(f"pack(n={n}): n must not be negative")
    if n > N_MAX:
        raise BadInput(f"pack(n={n}): n must be at most {N_MAX}")


def pack(root: tuple[int, int, int, int], n: int) -> tuple[int, bytearray]:
    """Count circles of curvature at most n in the packing and mark their curvatures.

    The root must come from validate_root. Termination does not rest on that:
    a reflection is pushed only when it strictly increases the curvature it
    replaces and stays at most n, so every DFS path climbs a finite integer
    range. For a reduced root the increase always holds, so the guard never
    prunes a valid circle; it exists to bound the walk if the invariant breaks.
    """
    _check_n(n)
    _check_reduced_root(root)
    bitmap = bytearray(n // 8 + 1)
    count = 0
    for k in root[1:]:
        if k <= n:
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
