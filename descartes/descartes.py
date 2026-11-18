#!/usr/bin/env python3
"""Descartes circle theorem helpers and integral Apollonian packings.

Pieces so far: the fourth-curvature formula, root validation with reduction
to the packing's canonical root, an enumerator that counts every circle of
curvature at most n and records which curvatures occur, the geometry
(centres of a root, the tangency check, the three-circle solver and the
enumerator that carries centres), a braille renderer and the command line.
Standard library only.

Run with no arguments at a terminal for an interactive prompt, or supply K:
    python3 descartes.py K [--root A B C D] [--show] [--yes] [--no-draw]
    python3 descartes.py --smoke
    python3 descartes.py --solve K,X,Y K,X,Y K,X,Y [--precision P] [--no-draw]
"""

import argparse
import cmath
import contextlib
import math
import os
import shutil
import sys
import time
from collections.abc import Iterator
from decimal import Decimal
from fractions import Fraction
from typing import NoReturn, TextIO

# Largest n pack accepts: Python's N = 10^K ceiling (K <= 6, spec R7), about
# 2.7e7 circles. The core enforces it so no caller can request an unbounded run.
N_MAX = 10**6
# Largest |curvature| validate_root accepts (spec R28). Reduction takes one step
# per reflection, and (-1, 2, n²+2, (n+1)²+2) needs n of them, so an uncapped
# root can run for hours; curvatures grow at least quadratically along a chain,
# so this bounds reduction at about 10^4 steps.
ROOT_MAX = 10**8


# (curvature, x, y): a circle of radius 1/k centred at (x, y).
Circle = tuple[float, float, float]

# Relative tolerance of the tangency check (spec Component 2, R24(a)).
TANGENT_TOL = 1e-9


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
    for v in values:
        if abs(v) > ROOT_MAX:
            raise BadInput(
                f"root {shown}: curvatures must be at most 10^8 in absolute value, "
                f"got {v}"
            )
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


def _check_reduced_root(root: tuple[int, int, int, int], op: str = "pack") -> None:
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
        raise BadInput(f"{op}(root={root}, ...): root is {problem}")


def _check_n(n: int, op: str = "pack", arg: str = "n") -> None:
    """Raise BadInput unless 0 <= n <= N_MAX; op and arg name the caller's argument."""
    if n < 0:
        raise BadInput(f"{op}({arg}={n}): {arg} must not be negative")
    if n > N_MAX:
        raise BadInput(f"{op}({arg}={n}): {arg} must be at most {N_MAX}")


def pack(root: tuple[int, int, int, int], n: int) -> tuple[int, bytearray]:
    """Count circles of curvature at most n in the packing and mark their curvatures.

    The root must come from validate_root. Termination does not rest on that:
    the root's four reflections are seeded when at most n, and every later
    reflection is pushed only when it strictly increases the curvature it
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


def _place_root(root: tuple[int, int, int, int]) -> list[Circle]:
    """Centres of a reduced root: bounding circle at the origin, second on +x.

    The third circle sits in the triangle of centre distances with y >= 0. That
    triangle is done in exact rationals: float rounding on a collinear root
    leaves a y squared of +-1e-16, whose square root (1e-8) would break the
    fourth circle's tangency, while exact arithmetic gives 0 and never a
    negative. The fourth is the candidate of curvature d (within the tangency
    tolerance) with the larger y, from the complex theorem; no candidate of
    that curvature is NoSolution. No tangency check runs here.
    """
    a, b, c, d = root
    big_r = Fraction(1, -a)
    r2 = Fraction(1, b)
    r3 = Fraction(1, c)
    x2 = big_r - r2
    d1 = big_r - r3
    d2 = r2 + r3
    x3 = (d1 * d1 - d2 * d2 + x2 * x2) / (2 * x2)
    y3 = math.sqrt(d1 * d1 - x3 * x3)
    c1: Circle = (float(a), 0.0, 0.0)
    c2: Circle = (float(b), float(x2), 0.0)
    c3: Circle = (float(c), float(x3), y3)
    fourths = [
        f for f in _tangent_circles(c1, c2, c3) if abs(f[0] - d) <= TANGENT_TOL * abs(d)
    ]
    if not fourths:
        raise NoSolution(
            f"root {root}: no circle of curvature {d} is tangent to its first "
            "three circles"
        )
    return [c1, c2, c3, max(fourths, key=lambda f: f[2])]


def root_centres(root: tuple[int, int, int, int]) -> list[Circle]:
    """Return the four circles (k, x, y) of a reduced root, for drawing."""
    _check_reduced_root(root, "root_centres")
    return _place_root(root)


def _pair_gap(a: Circle, b: Circle) -> tuple[float, float, float]:
    """Return (measured distance, expected distance, tolerance) for two circles.

    Radii are signed (r = 1/k), so a pair is tangent when the centre distance
    equals |r_a + r_b|: the sum for two positive circles, the difference when
    one is the bounding circle.
    """
    r_a = 1.0 / a[0]
    r_b = 1.0 / b[0]
    measured = math.hypot(a[1] - b[1], a[2] - b[2])
    return measured, abs(r_a + r_b), TANGENT_TOL * (abs(r_a) + abs(r_b))


def _is_tangent(a: Circle, b: Circle) -> bool:
    measured, expected, tol = _pair_gap(a, b)
    return abs(measured - expected) <= tol


def _short_decimal(v: float) -> bool:
    """True for a non-integer whose positional shortest round-trip form has at most 6 decimals.

    A non-integer has at least one decimal, so only the upper bound is tested;
    counting from the Decimal exponent makes 1e-05 (repr's exponent form of
    0.00001) count as 5 decimals.
    """
    if not math.isfinite(v) or v == int(v):
        return False
    return -int(Decimal(repr(v)).as_tuple().exponent) <= 6


def _input_problem(k: float, x: float, y: float) -> str:
    """Describe why a circle cannot be an input (spec R26), or return ''."""
    if not all(math.isfinite(v) for v in (k, x, y)):
        return "has a NaN or infinite value"
    if k == 0:
        return "has zero curvature"
    if not math.isfinite(1.0 / k):
        return "has a curvature whose radius 1/k is not finite"
    return ""


def check_tangent(circles: list[Circle]) -> None:
    """Raise unless the circles are mutually tangent (pairs 1-2, 1-3, 2-3).

    A non-finite value, a zero curvature or a non-finite radius is BadInput,
    checked for every circle before any pair; the first failing pair is
    NoSolution.
    """
    for number, (k, x, y) in enumerate(circles, start=1):
        problem = _input_problem(k, x, y)
        if problem:
            raise BadInput(
                f"solve{tuple(circles)}: circle {number} {problem} "
                f"(curvature {k}, centre ({x}, {y}))"
            )
    for i in range(len(circles)):
        for j in range(i + 1, len(circles)):
            measured, expected, tol = _pair_gap(circles[i], circles[j])
            if abs(measured - expected) <= tol:
                continue
            message = (
                f"solve{tuple(circles)}: circles {i + 1} and {j + 1} are not "
                f"tangent: measured distance {measured!r}, expected "
                f"{expected!r}, tolerance {tol!r}"
            )
            if any(_short_decimal(v) for c in circles for v in c[1:]):
                message += (
                    "; a coordinate has 6 or fewer decimal places, so it may "
                    "be rounded: use full-precision values"
                )
            raise NoSolution(message)


def _same_circle(a: Circle, b: Circle) -> bool:
    """True unless a and b differ in curvature or centre (spec R26).

    Different means curvatures more than TANGENT_TOL * |k| apart or centres
    more than TANGENT_TOL * |1/k| apart, so the test holds at every scale.
    """
    curvature_gap = abs(a[0] - b[0])
    centre_gap = math.hypot(a[1] - b[1], a[2] - b[2])
    return curvature_gap <= TANGENT_TOL * abs(b[0]) and centre_gap <= TANGENT_TOL * abs(
        1.0 / b[0]
    )


def _circle_order(circle: Circle) -> tuple[float, float, float]:
    """Sort key for solve's results: curvature, then y, then x (unpacked, so no index to slip)."""
    k, x, y = circle
    return (k, y, x)


def _tangent_circles(c1: Circle, c2: Circle, c3: Circle) -> list[Circle]:
    """Distinct circles tangent to all three, ordered by curvature, y, then x.

    The four sign combinations of the complex theorem are tried and kept only
    when tangent to all three inputs. A fourth curvature of 0 is a straight
    line and is omitted.
    """
    (k1, x1, y1), (k2, x2, y2), (k3, x3, y3) = c1, c2, c3
    z1, z2, z3 = complex(x1, y1), complex(x2, y2), complex(x3, y3)
    w = k1 * k2 * z1 * z2 + k2 * k3 * z2 * z3 + k3 * k1 * z3 * z1
    root_w = cmath.sqrt(w)
    zsum = k1 * z1 + k2 * z2 + k3 * z3
    line_limit = TANGENT_TOL * (abs(k1) + abs(k2) + abs(k3))
    found: list[Circle] = []
    for k in descartes_fourth(k1, k2, k3):
        if abs(k) <= line_limit:
            continue
        for sign in (1, -1):
            z = (zsum + sign * 2 * root_w) / k
            cand: Circle = (k, z.real, z.imag)
            if not all(_is_tangent(cand, c) for c in (c1, c2, c3)):
                continue
            if not any(_same_circle(cand, f) for f in found):
                found.append(cand)
    return sorted(found, key=_circle_order)


def solve(c1: Circle, c2: Circle, c3: Circle) -> list[Circle]:
    """Return the circles tangent to three mutually tangent circles."""
    check_tangent([c1, c2, c3])
    found = _tangent_circles(c1, c2, c3)
    if not found:
        raise NoSolution(f"solve({c1}, {c2}, {c3}): no circle is tangent to all three")
    return found


def _child(
    ks: list[int], zs: list[complex], i: int, k: int
) -> tuple[list[int], list[complex], int]:
    """Replace circle i of the quadruple by its reflection of curvature k.

    The new centre is (2 * sum(k*z) of the other three - k_i*z_i) / k.
    """
    others = sum(ks[m] * zs[m] for m in range(4) if m != i)
    child_ks = list(ks)
    child_zs = list(zs)
    child_ks[i] = k
    child_zs[i] = (2 * others - ks[i] * zs[i]) / k
    return child_ks, child_zs, i


def visible(root: tuple[int, int, int, int], limit: int) -> list[Circle]:
    """Return every positive circle of the packing with curvature <= limit.

    The same search as pack, carrying centres, so len(visible(root, n)) equals
    pack(root, n)[0]. The growth test k_i < k' keeps the walk bounded as in
    pack (spec R21). The bounding circle is not returned (spec R24(d)).
    """
    _check_n(limit, "visible", "limit")
    _check_reduced_root(root, "visible")
    placed = _place_root(root)
    ks = list(root)
    zs = [complex(x, y) for _, x, y in placed]
    found = [c for c in placed[1:] if c[0] <= limit]
    total = sum(ks)
    stack: list[tuple[list[int], list[complex], int]] = []
    for i in range(4):
        k = 2 * (total - ks[i]) - ks[i]
        if k <= limit:
            stack.append(_child(ks, zs, i, k))
    while stack:
        quad, centres, j = stack.pop()
        found.append((float(quad[j]), centres[j].real, centres[j].imag))
        total = sum(quad)
        for i in range(4):
            if i == j:
                continue
            k = 2 * (total - quad[i]) - quad[i]
            if quad[i] < k <= limit:
                stack.append(_child(quad, centres, i, k))
    return found


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

# The canvas when stdout is not a terminal (spec Component 7, R11).
PIPE_WIDTH = 60
PIPE_HEIGHT = 24

# Braille as in triangle.py: a cell is 2 dots wide and 4 tall, and is drawn
# twice as tall as wide, so a unit of length is the same number of dots in x
# and in y.
_BRAILLE_BASE = 0x2800
# Dot bits by (column within the cell, row within the cell).
_DOT_BITS = (
    (0x01, 0x02, 0x04, 0x40),
    (0x08, 0x10, 0x20, 0x80),
)


def _check_render_input(circles: list[Circle], width: int, height: int) -> None:
    """Raise BadInput for a canvas under 1 x 1 or a circle that cannot be drawn."""
    # Unlike triangle's 6 x 3 there are no labels to fit, so 1 x 1 is enough.
    if width < 1 or height < 1:
        raise BadInput(
            f"render: canvas {width}x{height} is too small, need at least 1x1"
        )
    for number, (k, x, y) in enumerate(circles, start=1):
        problem = _input_problem(k, x, y)
        if problem:
            raise BadInput(
                f"render: circle {number} {problem} (curvature {k}, centre ({x}, {y}))"
            )


def _dot_circles(
    circles: list[Circle], width: int, height: int
) -> list[tuple[int, int, int]]:
    """Centre and radius in dots (x right, y down) of each circle on the grid.

    The bounding box of all circles is fitted into dots 0.5 .. W-1.5 (and
    likewise in y) at one scale and centred, so rounding a centre and a radius
    to whole dots moves an edge by under one dot and never off the grid.
    Rounding is floor(v + 0.5).
    """
    radii = [abs(1.0 / k) for k, _, _ in circles]
    x_min = min(x - r for (_, x, _), r in zip(circles, radii, strict=True))
    x_max = max(x + r for (_, x, _), r in zip(circles, radii, strict=True))
    y_min = min(y - r for (_, _, y), r in zip(circles, radii, strict=True))
    y_max = max(y + r for (_, _, y), r in zip(circles, radii, strict=True))
    x_span, y_span = x_max - x_min, y_max - y_min
    scale = (
        min((2 * width - 2) / x_span, (4 * height - 2) / y_span)
        if math.isfinite(x_span) and math.isfinite(y_span)
        else math.nan
    )
    if not math.isfinite(scale):
        raise BadInput(
            f"render: the circles' bounding box ({x_span} x {y_span}) cannot be "
            f"scaled onto a {width}x{height} canvas"
        )
    left = (2 * width - 1 - x_span * scale) / 2
    top = (4 * height - 1 - y_span * scale) / 2
    return [
        (
            math.floor(left + (x - x_min) * scale + 0.5),
            math.floor(top + (y_max - y) * scale + 0.5),
            math.floor(r * scale + 0.5),
        )
        for (_, x, y), r in zip(circles, radii, strict=True)
    ]


def _midpoint_circle(cx: int, cy: int, radius: int) -> set[tuple[int, int]]:
    """Dots on the circle of the given radius (midpoint algorithm).

    A radius of 0 is the centre dot alone.
    """
    dots: set[tuple[int, int]] = set()
    x, y = radius, 0
    decision = 1 - radius
    while x >= y:
        for dx, dy in ((x, y), (y, x)):
            for sign_x in (1, -1):
                for sign_y in (1, -1):
                    dots.add((cx + sign_x * dx, cy + sign_y * dy))
        y += 1
        if decision <= 0:
            decision += 2 * y + 1
        else:
            x -= 1
            decision += 2 * (y - x) + 1
    return dots


def _plot(cells: list[list[int]], x: int, y: int, width: int, height: int) -> None:
    """Light dot (x, y) in the cell grid; a dot off the grid is ignored.

    The bounds check matters: a negative index would wrap to the far edge.
    """
    if 0 <= x < 2 * width and 0 <= y < 4 * height:
        cells[y // 4][x // 2] |= _DOT_BITS[x % 2][y % 4]


def render(circles: list[Circle], width: int, height: int) -> list[str]:
    """Draw circles as braille text, width x height cells, y up on the page.

    Reads only the (k, x, y) list. Raises BadInput for a canvas under 1 x 1 or
    a circle with a non-finite value or zero curvature.
    """
    _check_render_input(circles, width, height)
    cells = [[0] * width for _ in range(height)]
    if circles:
        for cx, cy, radius in _dot_circles(circles, width, height):
            for x, y in _midpoint_circle(cx, cy, radius):
                _plot(cells, x, y, width, height)
    return ["".join(chr(_BRAILLE_BASE + bits) for bits in row) for row in cells]


# ---------------------------------------------------------------------------
# SVG output
# ---------------------------------------------------------------------------

# The picture is a 1000 x 1000 user-unit square; the Rust crate emits the
# same text, so the format below is fixed (numbers may differ in the last digit).
_SVG_SIZE = 1000
_SVG_HEAD = (
    '<?xml version="1.0" encoding="UTF-8"?>',
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_SVG_SIZE} {_SVG_SIZE}">',
    f'<rect width="{_SVG_SIZE}" height="{_SVG_SIZE}" fill="white"/>',
)
# A circle needs at least this radius (user units) to get a curvature label.
_SVG_LABEL_MIN_RADIUS = 20


def _fmt3(value: float) -> str:
    """Format with three decimals; a negative zero prints as 0.000."""
    text = f"{value:.3f}"
    return "0.000" if text == "-0.000" else text


def _svg_circle(x: float, y: float, r: float, style: str) -> str:
    """One <circle> element; style is the stroke attributes before stroke-width."""
    width = _fmt3(min(1, r / 4))
    return (
        f'<circle cx="{_fmt3(x)}" cy="{_fmt3(y)}" r="{_fmt3(r)}" fill="none" '
        f'{style} stroke-width="{width}"/>'
    )


def _svg_label(x: float, y: float, r: float, k: float) -> str:
    """One <text> element centred on a circle, showing its integer curvature."""
    size = _fmt3(min(48, 0.6 * r))
    return (
        f'<text x="{_fmt3(x)}" y="{_fmt3(y)}" font-size="{size}" '
        f'text-anchor="middle" dominant-baseline="central">{round(k)}</text>'
    )


def _svg_document(elements: list[str]) -> str:
    """Join the fixed header, the elements and the closing tag, newline-ended."""
    return "\n".join([*_SVG_HEAD, *elements, "</svg>"]) + "\n"


def svg_limit(root: tuple[int, int, int, int], k: int) -> int:
    """Return the largest curvature the SVG draws: min(10^k, 1000 x |outer|).

    Past 1000 x |outer curvature| a circle's radius drops below 0.5 of the
    1000-unit square, so it is not drawn. root[0] is the outer curvature of a
    reduced root, so the result is always an int.
    """
    return min(10**k, 1000 * abs(root[0]))


def svg_packing(root: tuple[int, int, int, int], k: int) -> tuple[str, int]:
    """Return the packing up to svg_limit as SVG text and its drawn-circle count.

    The outer circle fills the square; every other circle of radius at least
    20 units is labelled with its curvature. The count excludes the outer
    circle. A comment before the first circle states the cut-off.
    """
    outer = root_centres(root)[0]
    k0, x0, y0 = outer
    scale = 500 * abs(k0)
    limit = svg_limit(root, k)
    inner = visible(root, limit)
    comment = (
        f"<!-- circles with curvature <= {limit}; "
        "cut-off min(10^K, 1000 x |outer curvature|) -->"
    )
    elements: list[str] = [comment]
    for index, (kc, x, y) in enumerate([outer, *inner]):
        px = 500 + (x - x0) * scale
        py = 500 - (y - y0) * scale
        r = scale / abs(kc)
        elements.append(_svg_circle(px, py, r, 'stroke="black"'))
        if index > 0 and r >= _SVG_LABEL_MIN_RADIUS:
            elements.append(_svg_label(px, py, r, kc))
    return _svg_document(elements), len(inner)


def svg_solve(given: list[Circle], solutions: list[Circle]) -> str:
    """Return the three given circles (black) and the solutions (red dashed) as SVG.

    The view is the bounding box of the givens and every enclosing solution
    (k < 0), centred and padded by 10%; no labels (spec R10-R11).
    """
    boxed = [*given, *(c for c in solutions if c[0] < 0)]
    x_lo = min(x - 1 / abs(k) for k, x, _ in boxed)
    x_hi = max(x + 1 / abs(k) for k, x, _ in boxed)
    y_lo = min(y - 1 / abs(k) for k, _, y in boxed)
    y_hi = max(y + 1 / abs(k) for k, _, y in boxed)
    cx, cy = (x_lo + x_hi) / 2, (y_lo + y_hi) / 2
    scale = _SVG_SIZE / (1.1 * max(x_hi - x_lo, y_hi - y_lo))
    elements = []
    for kc, x, y in given:
        elements.append(
            _svg_circle(
                500 + (x - cx) * scale,
                500 - (y - cy) * scale,
                scale / abs(kc),
                'stroke="black"',
            )
        )
    for kc, x, y in solutions:
        elements.append(
            _svg_circle(
                500 + (x - cx) * scale,
                500 - (y - cy) * scale,
                scale / abs(kc),
                'stroke="#c00" stroke-dasharray="6 4"',
            )
        )
    return _svg_document(elements)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

# ADR-0030 contract constants: the smoke run size, and no large-run
# confirmation (K <= 6 is always quick enough; spec R7).
SMOKE_SIZE = 2
LARGE_RUN_THRESHOLD: int | None = None

K_MAX = 6
# 17 significant digits round-trip any double; `--precision` caps decimal places at 17
# to bound output size, since more only lets a flag write gigabytes.
PRECISION_MAX = 17
# Canvas bounds in cells (spec R27): a hostile terminal size cannot make the
# drawing limit, and so the memory used, unbounded.
CANVAS_MAX_WIDTH = 1000
CANVAS_MAX_HEIGHT = 500
# A braille cell is two dots wide.
DOTS_PER_CELL_X = 2
DEFAULT_ROOT = (-1, 2, 2, 3)


def _circle_arg(text: str) -> Circle:
    """Parse one --solve value, K,X,Y, into a circle."""
    parts = text.split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"{text!r} is not K,X,Y (three values)")
    try:
        k, x, y = (float(part) for part in parts)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not K,X,Y (values must be numbers)"
        ) from None
    return k, x, y


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Enumerate an integral Apollonian packing up to curvature 10^K, or "
            "solve for the circles tangent to three given circles"
        ),
        epilog=(
            "The packing drawing shows circles with curvature at most "
            "min(10^K, 2 x canvas width in braille dots), so its circle set "
            "depends on terminal width. --solve prints full-precision values "
            "that paste back into --solve; that stops passing the 1e-9 "
            "tangency tolerance near curvature 2.6e7, and nearly collinear "
            "inputs are ill-conditioned. Run with no arguments at a terminal "
            "for interactive prompts."
        ),
    )
    parser.add_argument(
        "size",
        nargs="?",
        type=int,
        metavar="K",
        help=f"exponent (curvature limit = 10^K, 1 to {K_MAX})",
    )
    parser.add_argument(
        "--root",
        nargs=4,
        type=int,
        metavar=("A", "B", "C", "D"),
        help="root quadruple, one negative value (default -1 2 2 3)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="also print each result line to stdout",
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
    parser.add_argument(
        "--solve",
        nargs=3,
        type=_circle_arg,
        metavar="K,X,Y",
        help="three mutually tangent circles (curvature, centre x, centre y); "
        "prints the circles tangent to all three. Excludes K",
    )
    parser.add_argument(
        "--precision",
        type=int,
        metavar="P",
        help="--solve only: round the displayed table to P decimal places "
        "(default: full precision)",
    )
    parser.add_argument(
        "--no-draw", action="store_true", help="do not draw the circles in braille"
    )
    parser.add_argument(
        "--svg", metavar="PATH", help="also write the drawing as SVG to PATH"
    )
    args = parser.parse_args(argv)
    if args.precision is not None and not 0 <= args.precision <= PRECISION_MAX:
        parser.error(f"--precision must be between 0 and {PRECISION_MAX}")
    if args.solve is not None:
        extras = [
            name
            for name, used in (
                ("K", args.size is not None),
                ("--root", args.root is not None),
                ("--smoke", args.smoke),
                ("--show", args.show),
                ("--yes", args.yes),
            )
            if used
        ]
        if extras:
            parser.error(f"--solve takes no {', '.join(extras)}")
    elif args.precision is not None:
        parser.error("--precision needs --solve")
    elif args.smoke:
        if args.size is not None:
            parser.error("--smoke takes no K")
        args.size, args.show = SMOKE_SIZE, False
    elif args.size is None and not sys.stdin.isatty():
        parser.error("K is required when stdin is not a terminal")
    return args


def refuse_large_run(size: int, yes: bool) -> None:
    """Exit 1 naming --yes when size needs confirmation and --yes is absent."""
    if LARGE_RUN_THRESHOLD is not None and size >= LARGE_RUN_THRESHOLD and not yes:
        print(f"Error: {size} is a large run; pass --yes to proceed.", file=sys.stderr)
        sys.exit(1)


def get_exponent(args: argparse.Namespace) -> int:
    """
    Get and validate the exponent K from args.

    If args.size is None, prompt interactively until the answer is an integer
    in 1..K_MAX, reporting each bad answer on stderr; exit 1 on end of input.
    A K given as an argument that is out of range exits 2.

    Returns the validated exponent.
    """
    if args.size is not None:
        if args.size < 1 or args.size > K_MAX:
            print(f"K must be between 1 and {K_MAX}, got {args.size}.", file=sys.stderr)
            sys.exit(2)
        return args.size
    while True:
        try:
            text = input(f"Enter exponent K (limit = 10^K, max {K_MAX}): ")
        except EOFError:
            print()
            print(
                "Error: no input; pass K as an argument "
                f"(e.g. python3 descartes.py {SMOKE_SIZE}).",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            k = int(text)
        except ValueError:
            shown = text.rstrip("\r")  # as descartes-rs: a CRLF terminal leaves "\r"
            print(f"Invalid input: '{shown}' is not an integer K.", file=sys.stderr)
            continue
        if 1 <= k <= K_MAX:
            return k
        print(f"K must be between 1 and {K_MAX}, got {k}.", file=sys.stderr)


def _fail(error: Exception, code: int) -> NoReturn:
    """Print the error to stderr and exit with code."""
    print(f"Error: {error}", file=sys.stderr)
    sys.exit(code)


def _check_svg_path(path: str) -> None:
    """Refuse an SVG path whose directory is missing or that names a directory."""
    parent = os.path.dirname(path) or "."
    if not os.path.isdir(parent):
        _fail(
            OSError(f"cannot write SVG '{path}': directory '{parent}' does not exist"),
            1,
        )
    if os.path.isdir(path):
        _fail(OSError(f"cannot write SVG '{path}': it is a directory"), 1)


def _svg_error(path: str, error: OSError) -> NoReturn:
    """Exit 1 with the SVG write-failure message."""
    _fail(OSError(f"cannot write SVG '{path}': {error.strerror or error}"), 1)


@contextlib.contextmanager
def _open_svg(path: str | None) -> Iterator[TextIO | None]:
    """Open the SVG file before any computation; yield None when not asked."""
    if path is None:
        yield None
        return
    with contextlib.ExitStack() as stack:
        try:
            handle = stack.enter_context(
                open(path, "w", newline="\n", encoding="utf-8")
            )
        except OSError as error:
            _svg_error(path, error)
        yield handle


def _write_svg(handle: TextIO | None, path: str | None, text: str) -> None:
    """Write the SVG text, flushed so a full disk fails here, not at close."""
    if handle is None or path is None:
        return
    try:
        handle.write(text)
        handle.flush()
    except OSError as error:
        # close() would flush the unwritten buffer again and raise over the exit.
        with contextlib.suppress(OSError):
            handle.close()
        _svg_error(path, error)


def _canvas_size() -> tuple[int, int]:
    """Terminal size in cells, one row spared and clamped, else 60 x 24."""
    if not sys.stdout.isatty():
        return PIPE_WIDTH, PIPE_HEIGHT
    size = shutil.get_terminal_size()
    width = min(max(size.columns, 1), CANVAS_MAX_WIDTH)
    height = min(max(size.lines - 1, 1), CANVAS_MAX_HEIGHT)
    return width, height


def _packing_filename(k: int, root: tuple[int, int, int, int]) -> str:
    """The output file name: the root joins the name unless it is the default."""
    if root == DEFAULT_ROOT:
        return f"descartes_1e{k}.txt"
    return f"descartes_1e{k}_root_{root[0]}_{root[1]}_{root[2]}_{root[3]}.txt"


def _draw_packing(root: tuple[int, int, int, int], n: int) -> None:
    """Print the bounding circle and the circles that fit the canvas."""
    width, height = _canvas_size()
    # Circles above twice the canvas width in dots are under half a dot across.
    limit = min(n, 2 * DOTS_PER_CELL_X * width)
    circles = [root_centres(root)[0], *visible(root, limit)]
    print("\n".join(render(circles, width, height)))


def _run_packing(args: argparse.Namespace) -> None:
    k = get_exponent(args)
    refuse_large_run(k, args.yes)
    try:
        root = validate_root(*(args.root or DEFAULT_ROOT))
    except BadInput as error:
        _fail(error, 2)
    except NoSolution as error:
        _fail(error, 1)
    n = 10**k
    filename = _packing_filename(k, root)
    with _open_svg(args.svg) as svg_file:
        try:
            # Open first: a path or permission error must not cost a computation.
            with open(filename, "w") as f:
                start = time.perf_counter()
                count, bitmap = pack(root, n)
                curvatures = distinct(bitmap)
                f.writelines(f"{curvature}\n" for curvature in curvatures)
        except OSError as error:
            _fail(error, 1)
        _write_svg(svg_file, args.svg, svg_packing(root, k)[0] if svg_file else "")
    elapsed = time.perf_counter() - start
    if args.show:
        for curvature in curvatures:
            print(curvature)
    print(f"root {root[0]} {root[1]} {root[2]} {root[3]}")
    print(f"circles {count}")
    print(f"distinct {len(curvatures)}")
    print(f"Saved to {filename}")
    if args.svg is not None:
        print(f"Saved SVG to {args.svg}")
    print(f"Elapsed: {elapsed:.2f}s", file=sys.stderr)
    if count and not args.no_draw:
        _draw_packing(root, n)


def _format_value(value: float, precision: int | None) -> str:
    """Full-precision repr by default, else fixed decimals; never '-0'."""
    if precision is None:
        return repr(value + 0.0)
    text = f"{value:.{precision}f}"
    if text.startswith("-") and float(text) == 0:
        return text[1:]
    return text


def _print_table(
    given: list[Circle], solutions: list[Circle], precision: int | None
) -> None:
    """Print the given and solution circles, columns padded to align."""
    rows = [["kind", "#", "curvature", "radius", "x", "y"]]
    for kind, circles in (("given", given), ("solution", solutions)):
        for number, (k, x, y) in enumerate(circles, start=1):
            values = (k, 1.0 / k, x, y)
            rows.append(
                [kind, str(number), *(_format_value(v, precision) for v in values)]
            )
    widths = [max(map(len, column)) for column in zip(*rows, strict=True)]
    for row in rows:
        print(
            "  ".join(
                cell.ljust(w) for cell, w in zip(row, widths, strict=True)
            ).rstrip()
        )


def _run_solve(args: argparse.Namespace) -> None:
    given: list[Circle] = args.solve
    with _open_svg(args.svg) as svg_file:
        try:
            solutions = solve(given[0], given[1], given[2])
        except BadInput as error:
            _fail(error, 2)
        except NoSolution as error:
            _fail(error, 1)
        _print_table(given, solutions, args.precision)
        _write_svg(svg_file, args.svg, svg_solve(given, solutions) if svg_file else "")
    if args.svg is not None:
        print(f"Saved SVG to {args.svg}")
    if not args.no_draw:
        width, height = _canvas_size()
        print("\n".join(render(given + solutions, width, height)))


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    args = parse_args(argv)
    if args.svg is not None:
        _check_svg_path(args.svg)
    if args.solve is not None:
        _run_solve(args)
    else:
        _run_packing(args)


if __name__ == "__main__":
    main()
