"""Solve a triangle from any three of its sides and angles.

Three sections: solver, renderer and CLI.
Standard library only.
"""

import argparse
import math
import shutil
import sys
from dataclasses import dataclass, replace


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
    """SSS: every angle by Kahan's formula, the area by Kahan's Heron.

    Only for three given sides, which the caller has checked against the
    triangle inequality.  A computed side may round onto a + b for a valid
    near-flat triangle, so the other paths never come through here.
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
    side_name: str, side: float, angles: dict[str, float], sines: dict[str, float]
) -> Triangle:
    """ASA/AAS: the law of sines from one side, all three angles and their sines.

    The caller passes the third angle's sine from whichever of A + B and
    pi - (A + B) is the smaller, since that one holds its relative accuracy.
    """
    k = side / sines[_OPPOSITE[side_name]]
    sides = {n: k * sines[_OPPOSITE[n]] for n in _SIDES}
    sides[side_name] = side
    other, third = (n for n in _SIDES if n != side_name)
    # Half the product of two sides and their included angle: Heron on the
    # rounded law-of-sines sides cancels for a sliver angle.
    area = 0.5 * side * sides[other] * sines[_OPPOSITE[third]]
    return _build(sides, angles, area)


def _close_angles(known: float, p: float, q: float) -> tuple[float, float]:
    """Make two derived angles sum with a known one to pi.

    Computed independently, the two derived angles of an ill-conditioned
    triangle can each be as accurate as the problem allows and still miss
    pi by more than the post-check accepts.  The larger one, when it is at
    least pi/4, becomes pi - known - smaller, which costs it about 1e-15
    relative.  Below pi/4 both are small, so are their absolute errors, and
    each keeps its direct value.  SSA needs this; SAS does not (its two
    atan2 angles were never measured to miss pi), so SAS does not call it.
    """
    if p >= q and p >= math.pi / 4:
        return (math.pi - known) - q, q
    if q > p and q >= math.pi / 4:
        return p, (math.pi - known) - p
    return p, q


def _build(sides: dict[str, float], angles: dict[str, float], area: float) -> Triangle:
    a, b, c = sides["a"], sides["b"], sides["c"]
    return Triangle(
        a=a,
        b=b,
        c=c,
        A=angles["A"],
        B=angles["B"],
        C=angles["C"],
        area=area,
        perimeter=a + b + c,
    )


def _opposite_angle(p: float, q: float, between: float) -> float:
    """The angle opposite p, from sides p and q and the angle between them.

    tan = p sin(between) / (q - p cos(between)), with q - p cos written as
    (q - p) + 2p sin^2(between/2) so it does not cancel for a small angle.
    """
    half = math.sin(between / 2.0)
    return math.atan2(p * math.sin(between), (q - p) + 2.0 * p * half * half)


def _from_two_sides_and_included(
    x: float, y: float, included: float
) -> tuple[float, float, float]:
    """SAS: the third side and the sides in order (x, y, z).

    Law of cosines in the form (x - y)^2 + 4xy sin^2(C/2), which equals
    x^2 + y^2 - 2xy cos C but does not cancel when C is small; hypot keeps
    sin^2(C/2) from underflowing to zero for a tiny C.
    """
    half = math.sin(included / 2.0)
    z = math.hypot(x - y, 2.0 * math.sqrt(x * y) * half)
    return x, y, z


def _to_unit(value: float, radians: bool) -> float:
    return value if radians else math.degrees(value)


def _ssa_third_sides(
    angle: float, x: float, y: float, x_name: str, y_name: str, exponent: int
) -> list[tuple[float, float]]:
    """Third sides for SSA, longest first: 0 (raises), 1 or 2 of them.

    angle is opposite x; y is the other known side.  Each entry is (z, r)
    with r = z - y cos(angle), which is the signed square-root term, so the
    angle opposite y is atan2(y sin(angle), r) without any cancellation.
    The third side is computed directly, never from angle differences,
    which cancel when x is near y.  The sides arrive scaled by
    2**-exponent; messages unscale them.
    """
    cos_x = math.cos(angle)
    if angle >= math.pi / 2:
        if x <= y:
            raise NoTriangle(
                f"no triangle: side {x_name} must be longer than {y_name} "
                "opposite an angle of 90 degrees or more"
            )
        # Each factor rooted alone: their product can underflow when x is tiny.
        root = math.sqrt(x - y * math.sin(angle)) * math.sqrt(x + y * math.sin(angle))
        # y*cos(angle) <= 0 here, so the sum cancels when x is near y; the
        # roots multiply to y^2 - x^2, which gives the same value without it.
        return [((x - y) * (x + y) / (root - y * cos_x), root)]
    h = y * math.sin(angle)
    if x >= y:
        root = math.sqrt(x - h) * math.sqrt(x + h)
        return [(y * cos_x + root, root)]
    if abs(x - h) <= 4.0 * sys.float_info.epsilon * max(x, h):
        # Tangent: the right angle is opposite y.  The square root would
        # amplify the 1-ulp error in h into a visibly non-right angle.
        return [(y * cos_x, 0.0)]
    if x < h:
        height = math.ldexp(h, exponent)
        raise NoTriangle(
            f"no triangle: side {x_name} is shorter than the height {height:g}"
        )
    root = math.sqrt(x - h) * math.sqrt(x + h)
    z1 = y * cos_x + root
    return [(z1, root), ((y - x) * (y + x) / z1, -root)]


def _solve_ssa(
    values: dict[str, float], names: tuple[str, ...], exponent: int
) -> list[Triangle]:
    angle_name = next(n for n in names if n in _ANGLES)
    x_name = _OPPOSITE[angle_name]
    y_name = next(n for n in names if n in _SIDES and n != x_name)
    z_name = next(n for n in _SIDES if n not in (x_name, y_name))
    angle, x, y = values[angle_name], values[x_name], values[y_name]
    solutions = []
    for z, root in _ssa_third_sides(angle, x, y, x_name, y_name, exponent):
        y_angle, z_angle = _close_angles(
            angle,
            math.atan2(y * math.sin(angle), root),
            # y - z cos(angle) is y sin^2(angle) - root cos(angle); written
            # from root, it does not inherit the rounding of z, which cancels
            # against y when x is much shorter than y.
            math.atan2(
                z * math.sin(angle),
                y * math.sin(angle) ** 2 - root * math.cos(angle),
            ),
        )
        angles = {
            angle_name: angle,
            _OPPOSITE[y_name]: y_angle,
            _OPPOSITE[z_name]: z_angle,
        }
        sides = {x_name: x, y_name: y, z_name: z}
        solutions.append(_build(sides, angles, 0.5 * y * z * math.sin(angle)))
    return solutions


def _solve_determined(
    values: dict[str, float], exponent: int
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
            angle = values[included]
            angles = {
                included: angle,
                _OPPOSITE[s1]: _opposite_angle(x, y, angle),
                _OPPOSITE[s2]: _opposite_angle(y, x, angle),
            }
            area = 0.5 * x * y * math.sin(angle)
            return [_build({s1: x, s2: y, third: z}, angles, area)], {s1, s2, included}
    if sides and len(angles) >= 2:
        first, second = angles[0], angles[1]
        angle_set = {first: values[first], second: values[second]}
        third_name = next(n for n in _ANGLES if n not in angle_set)
        angle_set[third_name] = math.pi - (values[first] + values[second])
        sines = {n: math.sin(v) for n, v in angle_set.items()}
        given_sum = values[first] + values[second]
        sines[third_name] = math.sin(min(given_sum, angle_set[third_name]))
        t = _from_angles_and_side(sides[0], values[sides[0]], angle_set, sines)
        return [t], {sides[0], first, second}
    used = tuple(sides + angles)
    return _solve_ssa(values, used, exponent), set(used)


def _determining_names(values: dict[str, float]) -> set[str]:
    """The names _solve_determined uses, in the same precedence order."""
    sides = [n for n in _SIDES if n in values]
    angles = [n for n in _ANGLES if n in values]
    if len(sides) == 3:
        return set(_SIDES)
    for (s1, s2), included in _SAS_SETS:
        if s1 in values and s2 in values and included in values:
            return {s1, s2, included}
    if sides and len(angles) >= 2:
        return {sides[0], angles[0], angles[1]}
    return set(sides + angles)


def _check_each_value(values: dict[str, float], limit: float, limit_text: str) -> None:
    for name in _SIDES + _ANGLES:
        if name not in values:
            continue
        v = values[name]
        if not math.isfinite(v) or v <= 0:
            raise TriangleInputError(f"{name} must be a positive finite number")
        if name in _ANGLES and v >= limit:
            raise TriangleInputError(f"angle {name} must be less than {limit_text}")


def _check_angle_pairs(
    values: dict[str, float],
    internal: dict[str, float],
    limit: float,
    limit_text: str,
) -> None:
    """Refuse any two angles that leave no room for a third.

    Checked in the input unit and in radians: radians(10.8) + radians(169.2)
    rounds to 1 ulp below pi, and a radians sum can round up onto it.
    """
    angles = [n for n in _ANGLES if n in internal]
    for i, first in enumerate(angles):
        for second in angles[i + 1 :]:
            if (
                values[first] + values[second] >= limit
                or internal[first] + internal[second] >= math.pi
            ):
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
    limit = math.pi if radians else 180.0
    _check_each_value(values, limit, limit_text)
    if not any(n in values for n in _SIDES):
        raise TriangleInputError("need at least one side")
    internal = {
        n: (v if n in _SIDES or radians else math.radians(v)) for n, v in values.items()
    }
    for name in _ANGLES:
        if name in internal and internal[name] < sys.float_info.min:
            raise TriangleInputError(f"angle {name} is too small for a double")
    _check_angle_pairs(values, internal, limit, limit_text)
    return internal


def _check(t: Triangle) -> None:
    """Post-check: a failure here is a bug in the solver, never user input."""
    parts = (t.a, t.b, t.c, t.A, t.B, t.C)
    if not all(p > 0 and math.isfinite(p) for p in parts):
        raise RuntimeError(f"solver produced a non-positive or non-finite value: {t}")
    if abs(t.A + t.B + t.C - math.pi) > 1e-12 * math.pi:
        raise RuntimeError(f"solver produced angles that do not sum to pi: {t}")


_RANGE_ERROR = "values out of floating-point range: a side, the area or the perimeter"


def _scale_sides(values: dict[str, float]) -> tuple[dict[str, float], int]:
    """Scale every side by a power of two so the longest lies in [0.5, 1).

    Every formula is homogeneous in the sides and a power-of-two scale is
    exact, so the results are bit-identical to unscaled ones wherever those
    do not overflow or underflow.
    """
    exponent = math.frexp(max(values[n] for n in _SIDES if n in values))[1]
    scaled = {
        n: math.ldexp(v, -exponent) if n in _SIDES else v for n, v in values.items()
    }
    if min(scaled[n] for n in _SIDES if n in scaled) < sys.float_info.min:
        raise TriangleInputError(
            "the sides differ by more than a double can carry in one triangle"
        )
    return scaled, exponent


def _check_scaled_range(t: Triangle) -> None:
    """Range errors in the scaled solve, before the post-check sees them.

    A subnormal scaled side or area has already lost bits that unscaling
    cannot restore.  Nothing scaled can overflow: the longest given side is
    below 1 and _validate refuses an angle below the smallest normal double.
    """
    scaled = (t.a, t.b, t.c, t.area)
    if not all(v >= sys.float_info.min for v in scaled):
        raise TriangleInputError(f"{_RANGE_ERROR} is too small for a double")


def _unscale(t: Triangle, exponent: int) -> Triangle:
    """Undo _scale_sides; a result a double cannot hold is an input error.

    The scaled values were checked by _check_scaled_range first.
    """
    try:
        u = replace(
            t,
            a=math.ldexp(t.a, exponent),
            b=math.ldexp(t.b, exponent),
            c=math.ldexp(t.c, exponent),
            area=math.ldexp(t.area, 2 * exponent),
            perimeter=math.ldexp(t.perimeter, exponent),
        )
    except OverflowError:
        raise TriangleInputError(f"{_RANGE_ERROR} exceeds the largest double") from None
    if not all(v >= sys.float_info.min for v in (u.a, u.b, u.c, u.area)):
        raise TriangleInputError(f"{_RANGE_ERROR} is too small for a double")
    return u


def solve(values: dict[str, float], radians: bool = False) -> Solved:
    """Solve a triangle from any three or more of a b c A B C.

    Angles are degrees unless radians is set.  Given values are never
    replaced: values outside the determining set come back as extras, in
    the input unit.
    """
    internal = _validate(values, radians)
    # Only the determining set is solved, and only it sets the scale: an
    # extra side far from the others must not push the real ones out of range.
    determining, exponent = _scale_sides(
        {n: internal[n] for n in _determining_names(internal)}
    )
    solutions, used = _solve_determined(determining, exponent)
    for t in solutions:
        _check_scaled_range(t)
        _check(t)
    solutions = [_unscale(t, exponent) for t in solutions]
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# Closed-form kind of scripts/cli_contract.py: run these args, expect this token.
CONTRACT_ARGS = ["-a", "3", "-b", "4", "-c", "5"]
CONTRACT_EXPECT = "6.0000"

_ALL_NAMES = _SIDES + _ANGLES
_DEFAULT_PRECISION = 4
_PIPE_WIDTH = 60
_MAX_HEIGHT = 20


def _precision(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="triangle.py",
        description="Solve a triangle from three of its sides and angles.",
    )
    for name in _ALL_NAMES:
        kind = "side" if name in _SIDES else "angle"
        parser.add_argument(f"-{name}", type=float, default=None, help=f"{kind} {name}")
    parser.add_argument("--radians", action="store_true", help="angles in radians")
    parser.add_argument(
        "--precision",
        type=_precision,
        default=_DEFAULT_PRECISION,
        metavar="N",
        help="decimals in the table (default 4)",
    )
    parser.add_argument("--no-draw", action="store_true", help="table only")
    parser.add_argument("--smoke", action="store_true", help="solve and draw 3-4-5")
    return parser


def _reject_reason(text: str) -> str | None:
    """Why this prompt answer is unusable, or None when it is a positive number."""
    try:
        value = float(text)
    except ValueError:
        return f"{text!r} is not a number"
    if not math.isfinite(value):
        return f"{text!r} is not finite"
    if value <= 0:
        return f"{text!r} must be greater than zero"
    return None


def _prompt_values(radians: bool) -> dict[str, float]:
    """Ask for each of a b c A B C; an empty answer means unknown."""
    unit = "radians" if radians else "degrees"
    values: dict[str, float] = {}
    for name in _ALL_NAMES:
        label = name if name in _SIDES else f"{name} ({unit})"
        while True:
            answer = input(f"{label}: ").strip()
            if not answer:
                break
            reason = _reject_reason(answer)
            if reason is None:
                values[name] = float(answer)
                break
            print(reason, file=sys.stderr)
    return values


def _canvas_size() -> tuple[int, int]:
    if not sys.stdout.isatty():
        return _PIPE_WIDTH, _MAX_HEIGHT
    size = shutil.get_terminal_size()
    return max(size.columns, _MIN_WIDTH), max(min(_MAX_HEIGHT, size.lines), _MIN_HEIGHT)


def _print_table(t: Triangle, given: set[str], precision: int, radians: bool) -> None:
    for name in _ALL_NAMES:
        value = getattr(t, name)
        if name in _ANGLES:
            value = _to_unit(value, radians)
        status = "given" if name in given else "derived"
        print(f"{name:<10}{value:>{precision + 12}.{precision}f}  {status}")
    print(f"{'area':<10}{t.area:>{precision + 12}.{precision}f}")
    print(f"{'perimeter':<10}{t.perimeter:>{precision + 12}.{precision}f}")


def _print_extras(solved: Solved, precision: int) -> None:
    # given is printed with format(x, "g"), so a typed 53.13 prints as 53.13.
    for e in solved.extras:
        print(
            f"extra {e.name} given {format(e.given, 'g')} "
            f"solved {e.solved:.{precision + 2}f} diff {e.solved - e.given:+.6g}"
        )


def _report(solved: Solved, values: dict[str, float], args: argparse.Namespace) -> None:
    given = set(values)
    width, height = _canvas_size()
    many = len(solved.solutions) > 1
    for i, t in enumerate(solved.solutions, start=1):
        if many:
            print(f"Solution {i}")
        _print_table(t, given, args.precision, args.radians)
        if not args.no_draw:
            print("\n".join(render(t, width, height)))
    _print_extras(solved, args.precision)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.smoke:
        values: dict[str, float] = {"a": 3.0, "b": 4.0, "c": 5.0}
    else:
        values = {
            n: getattr(args, n) for n in _ALL_NAMES if getattr(args, n) is not None
        }
        if not values:
            if not sys.stdin.isatty():
                parser.print_usage(sys.stderr)
                return 2
            try:
                values = _prompt_values(args.radians)
            except EOFError:
                print("input ended before the values were read", file=sys.stderr)
                return 2
    try:
        solved = solve(values, radians=args.radians)
    except TriangleInputError as error:
        print(error, file=sys.stderr)
        return 2
    except NoTriangle as error:
        print(error, file=sys.stderr)
        return 1
    _report(solved, values, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
