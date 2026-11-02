"""Solve a triangle from any three of its sides and angles.

Three sections: solver (this task), renderer and CLI (later tasks).
Standard library only.
"""

import math
import sys
from dataclasses import dataclass


class TriangleInputError(ValueError):
    """The input cannot describe a triangle problem (CLI exit 2)."""


class NoTriangle(ValueError):
    """The input is well formed but no triangle fits it (CLI exit 1)."""


@dataclass(frozen=True)
class Triangle:
    a: float
    b: float
    c: float
    A: float
    B: float
    C: float
    area: float
    perimeter: float


@dataclass(frozen=True)
class Extra:
    name: str
    given: float
    solved: float


@dataclass(frozen=True)
class Solved:
    solutions: list[Triangle]
    extras: list[Extra]


def _kahan_angle(p: float, q: float, r: float) -> float:
    """Angle opposite side r, from sides alone, stable for needle triangles.

    Kahan, "Miscalculating Area and Angles of a Needle-like Triangle".  The
    other two sides are labelled so that p >= q.  The parentheses matter.
    """
    if p < q:
        p, q = q, p
    mu = r - (p - q) if q >= r else q - (p - r)
    ratio = ((p - q) + r) * mu / ((p + (q + r)) * ((p - r) + q))
    return 2.0 * math.atan(math.sqrt(ratio))


def _kahan_area(a: float, b: float, c: float) -> float:
    """Heron's formula in Kahan's stable form (sides sorted a >= b >= c)."""
    a, b, c = sorted((a, b, c), reverse=True)
    return 0.25 * math.sqrt(
        (a + (b + c)) * (c - (a - b)) * (c + (a - b)) * (a + (b - c))
    )


def _from_sides(a: float, b: float, c: float) -> Triangle:
    """Build a Triangle from three sides, every angle by Kahan's formula.

    No inequality check: the SSA and SAS paths guarantee a triangle by
    construction, and a float sum such as 7.9999999999 + 1e-10 can round
    to exactly 8 although the triangle is valid.
    """
    return Triangle(
        a=a,
        b=b,
        c=c,
        A=_kahan_angle(b, c, a),
        B=_kahan_angle(a, c, b),
        C=_kahan_angle(a, b, c),
        area=_kahan_area(a, b, c),
        perimeter=a + b + c,
    )


_SIDES = ("a", "b", "c")
_ANGLES = ("A", "B", "C")
_OPPOSITE = {"a": "A", "b": "B", "c": "C", "A": "a", "B": "b", "C": "c"}
# Each pair of sides with the angle they include (the angle opposite the third side).
_SAS_SETS = ((("a", "b"), "C"), (("a", "c"), "B"), (("b", "c"), "A"))


def _from_angles_and_side(
    side_name: str, side: float, angles: dict[str, float]
) -> Triangle:
    """ASA/AAS: the law of sines from one side and all three angles."""
    k = side / math.sin(angles[_OPPOSITE[side_name]])
    sides = {n: k * math.sin(angles[_OPPOSITE[n]]) for n in _SIDES}
    sides[side_name] = side
    a, b, c = sides["a"], sides["b"], sides["c"]
    return Triangle(
        a=a,
        b=b,
        c=c,
        A=angles["A"],
        B=angles["B"],
        C=angles["C"],
        area=_kahan_area(a, b, c),
        perimeter=a + b + c,
    )


def _from_two_sides_and_included(
    x: float, y: float, included: float
) -> tuple[float, float, float]:
    """SAS: the third side and the sides in order (x, y, z).

    Law of cosines in the form (x - y)^2 + 4xy sin^2(C/2), which equals
    x^2 + y^2 - 2xy cos C but does not cancel when C is small.
    """
    half = math.sin(included / 2.0)
    z = math.sqrt((x - y) ** 2 + 4.0 * x * y * half * half)
    return x, y, z


def _to_unit(value: float, radians: bool) -> float:
    return value if radians else math.degrees(value)


def _ssa_third_sides(
    angle: float, x: float, y: float, x_name: str, y_name: str
) -> list[float]:
    """Third sides for SSA, longest first: 0 (raises), 1 or 2 of them.

    angle is opposite x; y is the other known side.  The third side is
    computed directly, never from angle differences, which cancel when x is
    near y.
    """
    cos_x = math.cos(angle)
    if angle >= math.pi / 2:
        if x <= y:
            raise NoTriangle(
                f"no triangle: side {x_name} must be longer than {y_name} "
                "opposite an angle of 90 degrees or more"
            )
        root = math.sqrt((x - y * math.sin(angle)) * (x + y * math.sin(angle)))
        # y*cos(angle) <= 0 here, so the sum cancels when x is near y; the
        # roots multiply to y^2 - x^2, which gives the same value without it.
        return [(x - y) * (x + y) / (root - y * cos_x)]
    h = y * math.sin(angle)
    if x >= y:
        return [y * cos_x + math.sqrt((x - h) * (x + h))]
    if abs(x - h) <= 4.0 * sys.float_info.epsilon * max(x, h):
        # Tangent: the right angle is opposite y.  The square root would
        # amplify the 1-ulp error in h into a visibly non-right angle.
        return [y * cos_x]
    if x < h:
        raise NoTriangle(f"no triangle: side {x_name} is shorter than the height {h:g}")
    z1 = y * cos_x + math.sqrt((x - h) * (x + h))
    return [z1, (y - x) * (y + x) / z1]


def _solve_ssa(values: dict[str, float], names: tuple[str, ...]) -> list[Triangle]:
    angle_name = next(n for n in names if n in _ANGLES)
    x_name = _OPPOSITE[angle_name]
    y_name = next(n for n in names if n in _SIDES and n != x_name)
    z_name = next(n for n in _SIDES if n not in (x_name, y_name))
    zs = _ssa_third_sides(
        values[angle_name], values[x_name], values[y_name], x_name, y_name
    )
    solutions = []
    for z in zs:
        sides = {x_name: values[x_name], y_name: values[y_name], z_name: z}
        solutions.append(_from_sides(sides["a"], sides["b"], sides["c"]))
    return solutions


def _solve_determined(
    values: dict[str, float],
) -> tuple[list[Triangle], set[str]]:
    """Pick the determining set, solve it, and return the names it used."""
    sides = [n for n in _SIDES if n in values]
    angles = [n for n in _ANGLES if n in values]
    if len(sides) == 3:
        a, b, c = values["a"], values["b"], values["c"]
        if a + b <= c or a + c <= b or b + c <= a:
            raise NoTriangle(
                "no triangle: the sides do not satisfy the triangle inequality"
            )
        return [_from_sides(a, b, c)], set(_SIDES)
    for (s1, s2), included in _SAS_SETS:
        if s1 in values and s2 in values and included in values:
            x, y, z = _from_two_sides_and_included(
                values[s1], values[s2], values[included]
            )
            third = next(n for n in _SIDES if n not in (s1, s2))
            built = {s1: x, s2: y, third: z}
            t = _from_sides(built["a"], built["b"], built["c"])
            return [t], {s1, s2, included}
    if sides and len(angles) >= 2:
        first, second = angles[0], angles[1]
        angle_set = {first: values[first], second: values[second]}
        third_name = next(n for n in _ANGLES if n not in angle_set)
        angle_set[third_name] = math.pi - (values[first] + values[second])
        t = _from_angles_and_side(sides[0], values[sides[0]], angle_set)
        return [t], {sides[0], first, second}
    used = tuple(sides + angles)
    return _solve_ssa(values, used), set(used)


def _check_each_value(values: dict[str, float], limit: float, limit_text: str) -> None:
    for name in _SIDES + _ANGLES:
        if name not in values:
            continue
        v = values[name]
        if not math.isfinite(v) or v <= 0:
            raise TriangleInputError(f"{name} must be a positive finite number")
        if name in _ANGLES and v >= limit:
            raise TriangleInputError(f"angle {name} must be less than {limit_text}")


def _check_angle_pairs(internal: dict[str, float], limit_text: str) -> None:
    angles = [n for n in _ANGLES if n in internal]
    for i, first in enumerate(angles):
        for second in angles[i + 1 :]:
            if internal[first] + internal[second] >= math.pi:
                raise TriangleInputError(
                    f"angles {first} and {second} must sum to less than {limit_text}"
                )


def _validate(values: dict[str, float], radians: bool) -> dict[str, float]:
    """Check the input and return it with angles converted to radians."""
    for name in values:
        if name not in _SIDES + _ANGLES:
            raise TriangleInputError(f"unknown value {name}")
    if len(values) < 3:
        raise TriangleInputError("need at least three values")
    limit_text = "pi radians" if radians else "180 degrees"
    _check_each_value(values, math.pi if radians else 180.0, limit_text)
    if not any(n in values for n in _SIDES):
        raise TriangleInputError("need at least one side")
    internal = {
        n: (v if n in _SIDES or radians else math.radians(v)) for n, v in values.items()
    }
    _check_angle_pairs(internal, limit_text)
    return internal


def _check(t: Triangle) -> None:
    """Post-check: a failure here is a bug in the solver, never user input."""
    parts = (t.a, t.b, t.c, t.A, t.B, t.C)
    if not all(p > 0 and math.isfinite(p) for p in parts):
        raise RuntimeError(f"solver produced a non-positive or non-finite value: {t}")
    if abs(t.A + t.B + t.C - math.pi) > 1e-12 * math.pi:
        raise RuntimeError(f"solver produced angles that do not sum to pi: {t}")


def solve(values: dict[str, float], radians: bool = False) -> Solved:
    """Solve a triangle from any three or more of a b c A B C.

    Angles are degrees unless radians is set.  Given values are never
    replaced: values outside the determining set come back as extras, in
    the input unit.
    """
    internal = _validate(values, radians)
    solutions, used = _solve_determined(internal)
    for t in solutions:
        _check(t)
    extras = [
        Extra(
            name,
            values[name],
            getattr(solutions[0], name)
            if name in _SIDES
            else _to_unit(getattr(solutions[0], name), radians),
        )
        for name in _SIDES + _ANGLES
        if name in values and name not in used
    ]
    return Solved(solutions, extras)


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

# One cell is 2 dots wide and 4 dots tall, and is drawn twice as tall as it is
# wide, so a unit of length is the same number of dots in x and in y.
_MIN_WIDTH = 6
_MIN_HEIGHT = 3
_BRAILLE_BASE = 0x2800
# Dot bits by (column within the cell, row within the cell).
_DOT_BITS = (
    (0x01, 0x02, 0x04, 0x40),
    (0x08, 0x10, 0x20, 0x80),
)


def _project(t: Triangle, width: int, height: int) -> list[tuple[int, int]]:
    """Dot coordinates (x, y) of vertices A, B, C; y grows downward.

    A is the origin, B is on the x-axis and C is above it.  One cell is kept
    free on every side so a label always fits beside its vertex.
    """
    corners = [(0.0, 0.0), (t.c, 0.0), (t.b * math.cos(t.A), t.b * math.sin(t.A))]
    x_min = min(x for x, _ in corners)
    x_span = max(x for x, _ in corners) - x_min
    y_span = corners[2][1]
    area_w = 2 * width - 5  # dots between the first and last usable column
    area_h = 4 * height - 9
    scale = min(area_w / x_span, area_h / y_span)
    left = 2 + (area_w - x_span * scale) / 2
    top = 4 + (area_h - y_span * scale) / 2
    return [
        (round(left + (x - x_min) * scale), round(top + (y_span - y) * scale))
        for x, y in corners
    ]


def _bresenham(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Integer points on the line between two dots, ends included."""
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    step_x = 1 if x0 < x1 else -1
    step_y = 1 if y0 < y1 else -1
    err = dx + dy
    points = []
    while True:
        points.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return points
        doubled = 2 * err
        if doubled >= dy:
            err += dy
            x0 += step_x
        if doubled <= dx:
            err += dx
            y0 += step_y


def _label_cell(
    vertex: tuple[int, int], centre: tuple[float, float]
) -> tuple[int, int]:
    """(row, col) of the cell just outside a vertex, away from the centroid."""
    dx, dy = vertex[0] - centre[0], vertex[1] - centre[1]
    row, col = vertex[1] // 4, vertex[0] // 2
    # Compare in cells: a cell is 2 dots wide and 4 dots tall.
    if abs(dx) / 2 >= abs(dy) / 4:
        return row, col + (1 if dx >= 0 else -1)
    return row + (1 if dy >= 0 else -1), col


def render(t: Triangle, width: int, height: int) -> list[str]:
    """Draw the triangle as braille text, width x height character cells.

    Vertices A, B and C are labelled in the cell just outside each corner.
    Raises ValueError when the canvas is too small to hold the drawing.
    """
    if width < _MIN_WIDTH or height < _MIN_HEIGHT:
        raise ValueError(
            f"canvas {width}x{height} is too small, need at least "
            f"{_MIN_WIDTH}x{_MIN_HEIGHT}"
        )
    cells = [[0] * width for _ in range(height)]
    pts = _project(t, width, height)
    for i in range(3):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % 3]
        for x, y in _bresenham(x0, y0, x1, y1):
            cells[y // 4][x // 2] |= _DOT_BITS[x % 2][y % 4]
    rows = [[chr(_BRAILLE_BASE + bits) for bits in row] for row in cells]
    centre = (sum(p[0] for p in pts) / 3, sum(p[1] for p in pts) / 3)
    for label, vertex in zip("ABC", pts, strict=True):
        row, col = _label_cell(vertex, centre)
        rows[row][col] = label
    return ["".join(row) for row in rows]
