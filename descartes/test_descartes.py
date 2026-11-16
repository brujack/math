"""Tests for descartes: Descartes fourth circle, root reduction and packing.

The oracle below is test-only and shares no code with descartes.py: it builds
the four root circles in the plane and grows the packing by the complex
Descartes theorem, so it checks the integer recurrence against geometry.
"""

import cmath
import math
import unittest
from collections import deque
from fractions import Fraction
from unittest import mock

import descartes
from descartes import (
    BadInput,
    Circle,
    NoSolution,
    check_tangent,
    descartes_fourth,
    distinct,
    pack,
    root_centres,
    solve,
    validate_root,
    visible,
)

Root = tuple[int, int, int, int]
OracleCircle = tuple[float, complex]

ROOT_A: Root = (-1, 2, 2, 3)
ROOT_B: Root = (-2, 3, 6, 7)
ROOT_C: Root = (-3, 4, 12, 13)
ROOT_D: Root = (-11, 21, 24, 28)
ROOT_E: Root = (-3, 5, 8, 8)

PINNED: list[tuple[Root, int, int, int]] = [
    (ROOT_A, 30, 38, 11),
    (ROOT_A, 100, 168, 33),
    (ROOT_A, 1000, 3328, 324),
    (ROOT_A, 10**4, 67166, 3299),
    (ROOT_A, 10**5, 1359170, 33273),
    (ROOT_B, 30, 14, 8),
    (ROOT_B, 100, 66, 28),
    (ROOT_B, 1000, 1300, 297),
    (ROOT_C, 30, 10, 6),
    (ROOT_C, 100, 40, 17),
    (ROOT_C, 1000, 744, 200),
    (ROOT_D, 10, 0, 0),
    (ROOT_D, 30, 3, 3),
    (ROOT_D, 100, 9, 9),
    (ROOT_D, 1000, 144, 114),
    (ROOT_E, 10, 3, 2),
    (ROOT_E, 30, 10, 6),
    (ROOT_E, 100, 38, 16),
    (ROOT_E, 1000, 785, 203),
]

ROOT_A_DISTINCT_30 = [2, 3, 6, 11, 14, 15, 18, 23, 26, 27, 30]
ALL_ROOTS = [ROOT_A, ROOT_B, ROOT_C, ROOT_D, ROOT_E]
ORACLE_N = 1000


def _reflect(quad: Root, i: int) -> Root:
    """Descartes reflection: replace curvature i by 2 * (sum of the others) - itself."""
    others = sum(quad) - quad[i]
    a, b, c, d = (2 * others - quad[j] if j == i else quad[j] for j in range(4))
    return (a, b, c, d)


def _descendants(root: Root, depth: int) -> list[Root]:
    """Sorted quads reachable from root in at most depth reflections.

    Only quads with exactly one negative curvature are kept (reflecting the
    bounding circle yields an all-positive quad that is not a valid root), and
    the root itself is left out. Every kept quad is a valid but unreduced root
    whose canonical root is `root`, derived from the reflection theorem alone.
    """
    seen = {root}
    frontier = [root]
    found: list[Root] = []
    for _ in range(depth):
        nxt: list[Root] = []
        for quad in frontier:
            for i in range(4):
                a, b, c, d = sorted(_reflect(quad, i))
                child = (a, b, c, d)
                if child in seen:
                    continue
                seen.add(child)
                nxt.append(child)
                if sum(1 for k in child if k < 0) == 1:
                    found.append(child)
        frontier = nxt
    return found


UNREDUCED = [(root, quad) for root in ALL_ROOTS for quad in _descendants(root, 3)]


# --- geometric oracle (test only) -------------------------------------------


def _residual(c: OracleCircle, others: list[OracleCircle]) -> float:
    """Largest tangency error of circle c against each of the others."""
    k, z = c
    worst = 0.0
    for ko, zo in others:
        gap = abs(abs(z - zo) - abs(1.0 / k + 1.0 / ko))
        worst = max(worst, gap)
    return worst


def _tangent_candidates(
    c1: OracleCircle, c2: OracleCircle, c3: OracleCircle
) -> list[OracleCircle]:
    """Circles tangent to all three, by the complex Descartes theorem."""
    (k1, z1), (k2, z2), (k3, z3) = c1, c2, c3
    s = max(k1 * k2 + k2 * k3 + k3 * k1, 0.0)
    w = k1 * k2 * z1 * z2 + k2 * k3 * z2 * z3 + k3 * k1 * z3 * z1
    root_w = cmath.sqrt(w)
    ksum = k1 + k2 + k3
    zsum = k1 * z1 + k2 * z2 + k3 * z3
    found: list[OracleCircle] = []
    for ksign in (1, -1):
        k = ksum + ksign * 2 * math.sqrt(s)
        if abs(k) < 1e-9:
            continue
        for zsign in (1, -1):
            cand = (k, (zsum + zsign * 2 * root_w) / k)
            if _residual(cand, [c1, c2, c3]) > 1e-6:
                continue
            # A zero radicand makes both signs give the same circle.
            if all(
                abs(cand[1] - f[1]) > 1e-6 or abs(cand[0] - f[0]) > 1e-6 for f in found
            ):
                found.append(cand)
    return found


def _root_circles(root: Root) -> list[OracleCircle]:
    a, b, c, d = root
    big_r = 1.0 / abs(a)
    r2 = 1.0 / b
    x2 = big_r - r2
    r3 = 1.0 / c
    x3 = ((big_r - r3) ** 2 - (r2 + r3) ** 2 + x2**2) / (2 * x2)
    y3_sq = (big_r - r3) ** 2 - x3**2
    # A centre on the axis leaves a rounding residue that sqrt would amplify.
    y3 = math.sqrt(y3_sq) if y3_sq > 1e-12 else 0.0
    c1: OracleCircle = (float(a), 0j)
    c2: OracleCircle = (float(b), complex(x2, 0.0))
    c3: OracleCircle = (float(c), complex(x3, y3))
    fourth = [
        cand for cand in _tangent_candidates(c1, c2, c3) if abs(cand[0] - d) < 1e-6
    ]
    assert fourth, f"no fourth circle of curvature {d} for root {root}"
    return [c1, c2, c3, fourth[0]]


def _oracle(root: Root, n_max: int) -> list[OracleCircle]:
    """Every distinct circle of the packing with curvature <= n_max."""
    circles: list[OracleCircle] = []
    by_k: dict[int, list[int]] = {}

    def intern(k: float, z: complex) -> int:
        key = round(k)
        for idx in by_k.get(key, []):
            if abs(circles[idx][1] - z) < 1e-6:
                return idx
        circles.append((float(key), z))
        by_k.setdefault(key, []).append(len(circles) - 1)
        return len(circles) - 1

    start = tuple(intern(k, z) for k, z in _root_circles(root))
    seen = {frozenset(start)}
    queue = deque([start])
    while queue:
        quad = queue.popleft()
        for i in range(4):
            keep = [circles[idx] for j, idx in enumerate(quad) if j != i]
            dropped = circles[quad[i]]
            fresh = [
                cand
                for cand in _tangent_candidates(keep[0], keep[1], keep[2])
                if abs(cand[0] - dropped[0]) > 1e-6 or abs(cand[1] - dropped[1]) > 1e-6
            ]
            assert len(fresh) == 1, f"{len(fresh)} new circles for {root}"
            k, z = fresh[0]
            assert abs(k - round(k)) < 1e-6, f"non-integral curvature {k}"
            if round(k) > n_max:
                continue
            new_quad = tuple(
                intern(k, z) if j == i else idx for j, idx in enumerate(quad)
            )
            if frozenset(new_quad) not in seen:
                seen.add(frozenset(new_quad))
                queue.append(new_quad)
    return circles


_ORACLE_CACHE: dict[Root, list[OracleCircle]] = {}


def _oracle_cached(root: Root) -> list[OracleCircle]:
    if root not in _ORACLE_CACHE:
        _ORACLE_CACHE[root] = _oracle(root, ORACLE_N)
    return _ORACLE_CACHE[root]


# --- descartes_fourth ---------------------------------------------------------


class TestDescartesFourth(unittest.TestCase):
    def test_returns_both_solutions(self) -> None:
        self.assertEqual(descartes_fourth(2, 3, 6), (23.0, -1.0))

    def test_double_root_when_radicand_zero(self) -> None:
        self.assertEqual(descartes_fourth(-1, 2, 2), (3.0, 3.0))

    def test_tiny_negative_radicand_is_clamped(self) -> None:
        plus, minus = descartes_fourth(1.0, 1.0, -0.5000000000000001)
        self.assertEqual(plus, minus)
        self.assertAlmostEqual(plus, 1.5)

    def test_negative_radicand_raises_naming_inputs(self) -> None:
        with self.assertRaisesRegex(NoSolution, r"1.*1.*-1"):
            descartes_fourth(1, 1, -1)

    def test_radicand_just_below_tolerance_raises(self) -> None:
        # s = -2e-9 against a threshold of -1e-12 * 1.
        with self.assertRaises(NoSolution):
            descartes_fourth(1.0, 1.0, -0.5 - 1e-9)

    def test_radicand_just_inside_tolerance_clamps(self) -> None:
        # s = -2e-13 is inside the -1e-12 * 1 window.
        plus, minus = descartes_fourth(1.0, 1.0, -0.5 - 1e-13)
        self.assertEqual(plus, minus)

    def test_tolerance_scales_with_magnitude(self) -> None:
        # s is exactly 0 in real arithmetic; rounding error grows like x**2.
        for x in [1e3, 7.3e4, 1e6, 3.1e7, 1e9]:
            with self.subTest(x=x):
                descartes_fourth(-2 * x / 7, 3 * x / 7, 6 * x / 7)

    def test_tolerance_is_one_ppt_of_the_summed_products(self) -> None:
        cases: list[tuple[tuple[float, float, float], bool]] = [
            # Products of comparable size and all three terms of the tolerance
            # live: s sits at 2x the tolerance (raise) or 0.5x it (clamp).
            ((0.003, 0.004, -0.0017142857142925713), True),
            ((-0.20473980815368198, 0.361, 0.473), False),
            ((0.203, 1.144, -0.1724068299927485), False),
            # s is exactly -4 and the tolerance is 1e-12 * 4e12 = 4: equal is
            # inside the window, so it clamps.
            ((2.0, 999999999999.0, -2.0), False),
        ]
        for curvatures, raises in cases:
            with self.subTest(curvatures=curvatures, raises=raises):
                k1, k2, k3 = curvatures
                a, b, c = (Fraction(k) for k in curvatures)
                s = a * b + b * c + c * a
                tolerance = Fraction(abs(a * b) + abs(b * c) + abs(c * a), 10**12)
                self.assertLess(s, 0)
                # the fixture is what it claims to be
                self.assertIs(-s > tolerance, raises)
                if raises:
                    with self.assertRaises(NoSolution):
                        descartes_fourth(k1, k2, k3)
                else:
                    plus, minus = descartes_fourth(k1, k2, k3)
                    self.assertEqual(plus, minus)
                    self.assertEqual(plus, k1 + k2 + k3)

    def test_result_satisfies_descartes_relation(self) -> None:
        for fourth in descartes_fourth(2, 3, 6):
            total = 2 + 3 + 6 + fourth
            self.assertAlmostEqual(total**2, 2 * (4 + 9 + 36 + fourth**2))


# --- validate_root --------------------------------------------------------------


class TestValidateRoot(unittest.TestCase):
    def test_valid_reduced_root_unchanged(self) -> None:
        self.assertEqual(validate_root(-1, 2, 2, 3), ROOT_A)

    def test_unordered_input_is_sorted(self) -> None:
        self.assertEqual(validate_root(3, 2, -1, 2), ROOT_A)

    def test_reduces_to_root_a(self) -> None:
        for root in [(-1, 2, 3, 6), (-1, 3, 6, 14), (-1, 2, 2, 3)]:
            with self.subTest(root=root):
                self.assertEqual(validate_root(*root), ROOT_A)

    def test_every_descendant_reduces_to_its_root(self) -> None:
        # quad was built from root by reflections, so root is its canonical root.
        for root, quad in UNREDUCED:
            with self.subTest(root=root, quad=quad):
                self.assertEqual(validate_root(*quad), root)

    def test_reduction_stops_at_a_tied_maximum(self) -> None:
        # (-3, 5, 8, 12) reflects to (-3, 5, 8, 8); the reflected 8 ties the
        # third curvature, and a tie must not end the reduction early.
        self.assertEqual(validate_root(-3, 5, 8, 12), ROOT_E)

    def test_already_reduced_roots_are_fixed_points(self) -> None:
        for root in ALL_ROOTS:
            self.assertEqual(validate_root(*root), root)

    def test_float_is_bad_input(self) -> None:
        with self.assertRaises(BadInput):
            validate_root(-1, 2, 2.5, 3)

    def test_bool_is_bad_input(self) -> None:
        with self.assertRaises(BadInput):
            validate_root(-1, 2, 2, True)

    def test_not_descartes_quadruple(self) -> None:
        with self.assertRaises(NoSolution) as info:
            validate_root(-1, 2, 2, 4)
        message = str(info.exception)
        self.assertIn("(-1, 2, 2, 4)", message)
        self.assertIn("(Σk)²=49, 2Σk²=50", message)

    def test_relation_fails_with_square_sum_below(self) -> None:
        # (Σk)²=64 exceeds 2Σk²=56, so the relation fails in the other direction.
        with self.assertRaisesRegex(NoSolution, "not a Descartes"):
            validate_root(-1, 3, 3, 3)

    def test_zero_is_not_negative(self) -> None:
        # (0, 1, 1, 4) satisfies the relation; zero must not count as negative.
        with self.assertRaisesRegex(NoSolution, "exactly one negative"):
            validate_root(0, 1, 1, 4)

    def test_zero_curvatures_have_no_single_negative(self) -> None:
        with self.assertRaisesRegex(NoSolution, r"\(0, 0, 1, 1\)"):
            validate_root(0, 0, 1, 1)

    def test_two_negatives_rejected(self) -> None:
        # (-1, -1, 0, 0) satisfies the Descartes equation with two negatives.
        with self.assertRaisesRegex(NoSolution, r"\(-1, -1, 0, 0\)"):
            validate_root(-1, -1, 0, 0)

    def test_all_positive_rejected(self) -> None:
        # (2, 2, 3, 15) is a genuine Descartes quadruple (22**2 = 484 =
        # 2 * (4 + 4 + 9 + 225)) with no negative curvature.
        with self.assertRaisesRegex(NoSolution, "exactly one negative"):
            validate_root(2, 2, 3, 15)


# --- pack ---------------------------------------------------------------------


class TestPackPinned(unittest.TestCase):
    def test_pinned_values(self) -> None:
        for root, n, count, n_distinct in PINNED:
            with self.subTest(root=root, n=n):
                got_count, bitmap = pack(root, n)
                self.assertEqual(
                    (got_count, len(distinct(bitmap))), (count, n_distinct)
                )

    def test_distinct_list_root_a_30(self) -> None:
        _, bitmap = pack(ROOT_A, 30)
        self.assertEqual(distinct(bitmap), ROOT_A_DISTINCT_30)

    def test_bitmap_size(self) -> None:
        _, bitmap = pack(ROOT_A, 30)
        self.assertEqual(len(bitmap), 30 // 8 + 1)


class TestPackBoundaries(unittest.TestCase):
    def test_n_below_every_curvature_is_empty(self) -> None:
        count, bitmap = pack(ROOT_A, 1)
        self.assertEqual(count, 0)
        self.assertEqual(distinct(bitmap), [])
        self.assertFalse(any(bitmap))

    def test_n_zero(self) -> None:
        count, bitmap = pack(ROOT_A, 0)
        self.assertEqual((count, distinct(bitmap), len(bitmap)), (0, [], 1))

    def test_n_equal_to_smallest_curvature_counts_it_once_per_circle(self) -> None:
        count, bitmap = pack(ROOT_A, 2)
        self.assertEqual(count, 2)
        self.assertEqual(distinct(bitmap), [2])

    def test_n_one_below_curvature_excludes_it(self) -> None:
        # Every curvature c of ROOT_A_DISTINCT_30 is absent at n = c - 1 and
        # present at n = c.
        for c in ROOT_A_DISTINCT_30:
            with self.subTest(c=c):
                self.assertNotIn(c, distinct(pack(ROOT_A, c - 1)[1]))
                self.assertIn(c, distinct(pack(ROOT_A, c)[1]))

    def test_bounding_circle_is_never_counted(self) -> None:
        _, bitmap = pack(ROOT_A, 30)
        self.assertTrue(all(k > 0 for k in distinct(bitmap)))


class TestPackPreconditions(unittest.TestCase):
    def test_negative_n_rejected(self) -> None:
        for n in [-1, -9]:
            with (
                self.subTest(n=n),
                self.assertRaisesRegex(BadInput, rf"pack.*{n}"),
            ):
                pack(ROOT_A, n)

    def test_unreduced_root_rejected(self) -> None:
        with self.assertRaisesRegex(BadInput, r"pack.*\(-1, 2, 3, 6\)"):
            pack((-1, 2, 3, 6), 100)

    def test_unsorted_root_rejected(self) -> None:
        with self.assertRaisesRegex(BadInput, "pack"):
            pack((2, -1, 2, 3), 100)

    def test_non_descartes_root_rejected(self) -> None:
        with self.assertRaisesRegex(BadInput, "pack"):
            pack((-1, 2, 2, 4), 100)

    def test_two_negative_root_rejected(self) -> None:
        with self.assertRaisesRegex(BadInput, "exactly one negative"):
            pack((-1, -1, 0, 0), 100)

    def test_zero_is_not_a_negative_curvature(self) -> None:
        # (0, 1, 1, 4) satisfies the relation with no negative curvature.
        with self.assertRaisesRegex(BadInput, "exactly one negative"):
            pack((0, 1, 1, 4), 100)

    def test_no_negative_root_rejected(self) -> None:
        # (0, 0, 1, 1) and (2, 2, 3, 15) are sorted and satisfy the relation.
        # (2, 2, 3, 15) would also fail the reduction test (2 * 7 - 15 < 15),
        # so the negative-count check must be reached, and named, first.
        for root in [(0, 0, 1, 1), (2, 2, 3, 15)]:
            with (
                self.subTest(root=root),
                self.assertRaisesRegex(BadInput, "exactly one negative"),
            ):
                pack(root, 100)

    def test_unsorted_root_is_named_unsorted(self) -> None:
        with self.assertRaisesRegex(BadInput, "not sorted"):
            pack((2, -1, 2, 3), 100)

    def test_relation_failure_is_named(self) -> None:
        cases: list[tuple[Root, str]] = [
            # (Σk)² = 49 is below 2Σk² = 50, and 64 above 56: both directions.
            ((-1, 2, 2, 4), "not a Descartes quadruple"),
            ((-1, 3, 3, 3), "not a Descartes quadruple"),
        ]
        for root, what in cases:
            with (
                self.subTest(root=root),
                self.assertRaisesRegex(BadInput, what),
            ):
                pack(root, 100)

    def test_every_unreduced_descendant_is_rejected(self) -> None:
        for root, quad in UNREDUCED:
            with (
                self.subTest(root=root, quad=quad),
                self.assertRaisesRegex(BadInput, "not reduced"),
            ):
                pack(quad, 100)

    def test_reduced_roots_are_accepted(self) -> None:
        for root in ALL_ROOTS:
            with self.subTest(root=root):
                pack(root, 100)


class TestPackLimits(unittest.TestCase):
    """pack is bounded by construction: a ceiling on n and a strictly
    increasing curvature on every pushed reflection."""

    def test_ceiling_matches_largest_k(self) -> None:
        self.assertEqual(descartes.N_MAX, 10**6)

    # Every ceiling test lowers N_MAX first. Called with the real ceiling, a
    # missing or broken check would make the test itself a ~1e10-circle run.
    def test_n_above_ceiling_rejected(self) -> None:
        with (
            mock.patch.object(descartes, "N_MAX", 30),
            self.assertRaisesRegex(BadInput, r"pack\(n=31\): n must be at most 30"),
        ):
            pack(ROOT_A, 31)

    def test_n_at_ceiling_accepted(self) -> None:
        with mock.patch.object(descartes, "N_MAX", 30):
            self.assertEqual(pack(ROOT_A, 30)[0], 38)

    # For any real Descartes quadruple the only decreasing reflection is the one
    # just made, which the DFS already skips, so the guard cannot be tested on
    # valid input. Both roots break the Descartes relation: without the guard
    # (-1, 1, 1, 1) reflects forever, and with only k != quad[i] (-1, 1, 1, 2)
    # pushes a falling curvature that goes negative. _mark is budgeted so a
    # missing guard fails fast instead of eating RAM.
    def test_dfs_terminates_when_root_invariant_is_broken(self) -> None:
        real_mark = descartes._mark
        for root in [(-1, 1, 1, 1), (-1, 1, 1, 2)]:
            with self.subTest(root=root):
                calls = 0

                def budgeted_mark(bitmap: bytearray, k: int) -> None:
                    nonlocal calls
                    calls += 1
                    self.assertLess(calls, 10_000, "pack DFS did not terminate")
                    real_mark(bitmap, k)

                with (
                    mock.patch.object(
                        descartes, "_check_reduced_root", lambda _root: None
                    ),
                    mock.patch.object(descartes, "_mark", budgeted_mark),
                ):
                    count, bitmap = pack(root, 30)
                self.assertEqual(count, calls)
                self.assertTrue(all(0 <= k <= 30 for k in distinct(bitmap)))


class TestPackState(unittest.TestCase):
    def test_repeated_calls_equal(self) -> None:
        self.assertEqual(pack(ROOT_A, 100), pack(ROOT_A, 100))

    def test_smaller_run_after_larger_is_unaffected(self) -> None:
        pack(ROOT_A, 1000)
        self.assertEqual(pack(ROOT_A, 30)[0], 38)

    def test_each_call_returns_fresh_bitmap(self) -> None:
        _, first = pack(ROOT_A, 30)
        _, second = pack(ROOT_A, 30)
        self.assertIsNot(first, second)

    def test_count_monotone_in_n(self) -> None:
        counts = [pack(ROOT_A, n)[0] for n in range(80)]
        self.assertEqual(counts, sorted(counts))


# --- oracle agreement ------------------------------------------------------------


def _oracle_view(root: Root, n: int) -> tuple[int, list[int]]:
    ks = [round(k) for k, _ in _oracle_cached(root) if 0 < round(k) <= n]
    return len(ks), sorted(set(ks))


class TestOracle(unittest.TestCase):
    def test_oracle_matches_pack_at_pinned_n(self) -> None:
        for root in ALL_ROOTS:
            for r, n, _, _ in PINNED:
                if r != root or n > ORACLE_N:
                    continue
                with self.subTest(root=root, n=n):
                    count, bitmap = pack(root, n)
                    self.assertEqual((count, distinct(bitmap)), _oracle_view(root, n))

    def test_oracle_matches_pack_for_small_n_sweep(self) -> None:
        for root in ALL_ROOTS:
            for n in range(61):
                with self.subTest(root=root, n=n):
                    count, bitmap = pack(root, n)
                    self.assertEqual((count, distinct(bitmap)), _oracle_view(root, n))

    def test_oracle_root_circles_are_mutually_tangent(self) -> None:
        for root in ALL_ROOTS:
            circles = _root_circles(root)
            for i, ci in enumerate(circles):
                with self.subTest(root=root, i=i):
                    others = [c for j, c in enumerate(circles) if j != i]
                    self.assertLess(_residual(ci, others), 1e-6)


# --- geometry: root_centres, check_tangent, solve, visible ------------------------

R9_C1: Circle = (-1.0, 0.0, 0.0)
R9_C2: Circle = (2.0, 0.5, 0.0)
R9_C3: Circle = (3.0, 0.0, 0.6666666666666666)


def _gap(a: Circle, b: Circle) -> float:
    """Tangency error of two circles relative to their summed |radii|.

    Written separately from descartes.py: signed radii, so |r_a + r_b| is the
    sum for two positive circles and the difference against the bounding one.
    """
    ra, rb = 1.0 / a[0], 1.0 / b[0]
    dist = math.hypot(a[1] - b[1], a[2] - b[2])
    return abs(dist - abs(ra + rb)) / (abs(ra) + abs(rb))


def _close(a: Circle, b: Circle, tol: float = 1e-9) -> bool:
    return all(abs(u - v) <= tol for u, v in zip(a, b, strict=True))


class TestRootCentres(unittest.TestCase):
    def test_root_a_values(self) -> None:
        # Hand-derived: radius-1 bounding circle, two radius-1/2 circles side by
        # side at x = +-1/2, and the curvature-3 circle at y = 2/3 (spec R9).
        got = root_centres(ROOT_A)
        want: list[Circle] = [
            (-1.0, 0.0, 0.0),
            (2.0, 0.5, 0.0),
            (2.0, -0.5, 0.0),
            (3.0, 0.0, 2.0 / 3.0),
        ]
        self.assertEqual(len(got), 4)
        for g, w in zip(got, want, strict=True):
            with self.subTest(circle=w):
                self.assertTrue(_close(g, w, 1e-12), f"{g} != {w}")

    def test_root_e_values(self) -> None:
        # Hand-derived from the centre-distance triangle with R=1/3, r2=1/5,
        # r3=1/8: x2 = 2/15, d1 = 5/24, d2 = 13/40, x3 = -1/6, y3^2 = 1/64.
        # The two curvature-8 circles are mirror images in the x axis.
        got = root_centres(ROOT_E)
        want: list[Circle] = [
            (-3.0, 0.0, 0.0),
            (5.0, 2.0 / 15.0, 0.0),
            (8.0, -1.0 / 6.0, 0.125),
            (8.0, -1.0 / 6.0, -0.125),
        ]
        for g, w in zip(got, want, strict=True):
            with self.subTest(circle=w):
                self.assertTrue(_close(g, w, 1e-12), f"{g} != {w}")

    def test_curvatures_follow_the_root(self) -> None:
        for root in ALL_ROOTS:
            with self.subTest(root=root):
                self.assertEqual([c[0] for c in root_centres(root)], list(root))

    def test_placement_convention(self) -> None:
        for root in ALL_ROOTS:
            first, second, third, _ = root_centres(root)
            with self.subTest(root=root):
                self.assertEqual((first[1], first[2]), (0.0, 0.0))
                self.assertEqual(second[2], 0.0)
                self.assertAlmostEqual(
                    second[1], 1.0 / abs(root[0]) - 1.0 / root[1], places=12
                )
                self.assertGreater(second[1], 0.0)
                self.assertGreaterEqual(third[2], 0.0)

    def test_all_six_pairs_tangent(self) -> None:
        for root in ALL_ROOTS:
            circles = root_centres(root)
            for i in range(4):
                for j in range(i + 1, 4):
                    with self.subTest(root=root, pair=(i + 1, j + 1)):
                        self.assertLessEqual(_gap(circles[i], circles[j]), 1e-9)

    def test_collinear_roots_have_exactly_zero_y(self) -> None:
        # In A, B and C the three circles' centres lie on one line (the
        # bounding diameter equals the sum of the other two diameters). Float
        # rounding of that triangle leaves y^2 of about +1e-16, which would
        # surface as y = 1e-8, so the third centre must come out as exactly 0.
        for root in (ROOT_A, ROOT_B, ROOT_C):
            with self.subTest(root=root):
                self.assertEqual(root_centres(root)[2][2], 0.0)

    def test_non_collinear_roots_have_positive_y(self) -> None:
        for root in (ROOT_D, ROOT_E):
            with self.subTest(root=root):
                self.assertGreater(root_centres(root)[2][2], 0.01)

    def test_agrees_with_independent_oracle(self) -> None:
        for root in ALL_ROOTS:
            got = root_centres(root)
            for g, (k, z) in zip(got[:3], _root_circles(root)[:3], strict=True):
                with self.subTest(root=root, k=k):
                    self.assertTrue(_close(g, (k, z.real, z.imag)))

    def test_fourth_circles_of_non_collinear_roots_match_the_oracle(self) -> None:
        # Root D's first three circles (-11, 21, 24) have two tangent
        # candidates, curvatures 28 and 40; the root names 28. Expected values
        # come from the independent oracle above, not from descartes.py.
        for root in (ROOT_D, ROOT_E):
            got = root_centres(root)[3]
            k, z = _root_circles(root)[3]
            with self.subTest(root=root):
                self.assertEqual(got[0], float(root[3]))
                self.assertTrue(_close(got, (k, z.real, z.imag)), f"{got} != {(k, z)}")

    def test_fourth_is_the_larger_y_among_candidates_of_curvature_d(self) -> None:
        # Candidates of curvature 28 at y = -1 and y = 1 plus a curvature-40
        # one with the largest y overall: the root names 28, so 40 is out and
        # of the two 28s the one with y = 1 wins.
        candidates: list[Circle] = [
            (28.0, 0.0, -1.0),
            (40.0, 0.0, 5.0),
            (28.0, 0.0, 1.0),
        ]
        with mock.patch.object(descartes, "_tangent_circles", return_value=candidates):
            self.assertEqual(root_centres(ROOT_D)[3], (28.0, 0.0, 1.0))

    def test_fourth_is_chosen_by_y_not_by_x_or_list_order(self) -> None:
        candidates: list[Circle] = [
            (28.0, 7.0, -1.0),
            (28.0, -7.0, 1.0),
            (28.0, 0.0, 0.5),
        ]
        with mock.patch.object(descartes, "_tangent_circles", return_value=candidates):
            self.assertEqual(root_centres(ROOT_D)[3], (28.0, -7.0, 1.0))

    def test_no_candidate_of_curvature_d_is_no_solution(self) -> None:
        # Both the empty list and a list holding only another curvature must
        # name the root and the missing curvature, not leak a bare ValueError.
        for candidates in ([], [(40.0, 0.0, 5.0)]):
            for call in (root_centres, lambda r: visible(r, 30)):
                with (
                    self.subTest(candidates=candidates),
                    mock.patch.object(
                        descartes, "_tangent_circles", return_value=candidates
                    ),
                    self.assertRaisesRegex(
                        NoSolution, r"\(-11, 21, 24, 28\).*curvature 28"
                    ),
                ):
                    call(ROOT_D)

    def test_curvature_match_is_relative_to_d(self) -> None:
        # Spec R26: tolerance 1e-9 * |d|. Offsets of 0.5e-9 are kept and 2e-9
        # rejected at every magnitude of d.
        for root in (ROOT_A, ROOT_B, ROOT_D):
            d = float(root[3])
            with self.subTest(root=root):
                near: list[Circle] = [(d * (1 + 0.5e-9), 0.0, 1.0)]
                with mock.patch.object(
                    descartes, "_tangent_circles", return_value=near
                ):
                    self.assertEqual(root_centres(root)[3], near[0])
                below: list[Circle] = [(d * (1 - 0.5e-9), 0.0, 1.0)]
                with mock.patch.object(
                    descartes, "_tangent_circles", return_value=below
                ):
                    self.assertEqual(root_centres(root)[3], below[0])
                for other in (d * (1 + 2e-9), d * (1 - 2e-9), 2 * d, d / 2):
                    far: list[Circle] = [(other, 0.0, 1.0)]
                    with (
                        mock.patch.object(
                            descartes, "_tangent_circles", return_value=far
                        ),
                        self.assertRaises(NoSolution),
                    ):
                        root_centres(root)

    def test_curvature_match_accepts_exactly_the_tolerance(self) -> None:
        # With the tolerance patched to 0.5 and d = 3 the bound is exactly 1.5.
        with mock.patch.object(descartes, "TANGENT_TOL", 0.5):
            with mock.patch.object(
                descartes, "_tangent_circles", return_value=[(4.5, 0.0, 1.0)]
            ):
                self.assertEqual(root_centres(ROOT_A)[3], (4.5, 0.0, 1.0))
            with (
                mock.patch.object(
                    descartes, "_tangent_circles", return_value=[(4.75, 0.0, 1.0)]
                ),
                self.assertRaises(NoSolution),
            ):
                root_centres(ROOT_A)

    def test_root_with_a_high_third_circle_is_placed_and_tangent(self) -> None:
        # (-15, 32, 32, 33): the third circle's squared height y^2 is more than
        # twice x^2 (A-E stay below that), which separates y^2 = d1^2 - x^2
        # from any remainder-style slip. Every pair must be tangent
        # (independent _gap) and the first three circles must match the oracle.
        root: Root = (-15, 32, 32, 33)
        got = root_centres(root)
        for i in range(4):
            for j in range(i + 1, 4):
                with self.subTest(pair=(i + 1, j + 1)):
                    self.assertLessEqual(_gap(got[i], got[j]), 1e-9)
        for g, (k, z) in zip(got[:3], _root_circles(root)[:3], strict=True):
            self.assertTrue(_close(g, (k, z.real, z.imag)), f"{g} != {(k, z)}")

    def test_never_runs_the_tangency_check(self) -> None:
        with mock.patch.object(descartes, "check_tangent", side_effect=AssertionError):
            self.assertEqual(len(root_centres(ROOT_B)), 4)

    def test_repeated_calls_equal(self) -> None:
        self.assertEqual(root_centres(ROOT_D), root_centres(ROOT_D))

    def test_invalid_roots_rejected_naming_the_operation(self) -> None:
        cases: list[tuple[Root, str]] = [
            ((-1, 2, 3, 6), "not reduced"),
            ((2, -1, 2, 3), "not sorted"),
            ((-1, 2, 2, 4), "not a Descartes quadruple"),
            ((0, 1, 1, 4), "exactly one negative"),
        ]
        for root, what in cases:
            with (
                self.subTest(root=root),
                self.assertRaisesRegex(BadInput, rf"root_centres.*{what}"),
            ):
                root_centres(root)


class TestCheckTangent(unittest.TestCase):
    def test_r9_triple_passes(self) -> None:
        self.assertIsNone(check_tangent([R9_C1, R9_C2, R9_C3]))

    def test_r9_scaled_by_100_passes(self) -> None:
        # Spec R10: curvatures x100, centres divided by 100.
        scaled: list[Circle] = [
            (-100.0, 0.0, 0.0),
            (200.0, 0.5 / 100, 0.0),
            (300.0, 0.0, 0.6666666666666666 / 100),
        ]
        self.assertIsNone(check_tangent(scaled))

    def test_external_triple_passes(self) -> None:
        # Two unit circles at (0,0) and (2,0) and a radius-1/4 circle at
        # (1, 3/4): every centre distance is 2, 5/4 and 5/4 by Pythagoras.
        self.assertIsNone(check_tangent([(1, 0, 0), (1, 2, 0), (4, 1, 0.75)]))

    def test_empty_and_pair_lists_pass(self) -> None:
        self.assertIsNone(check_tangent([]))
        self.assertIsNone(check_tangent([(1, 0, 0), (1, 2, 0)]))

    def test_zero_curvature_is_bad_input(self) -> None:
        for position in range(3):
            triple = [R9_C1, R9_C2, R9_C3]
            triple[position] = (0.0, 0.0, 0.0)
            with (
                self.subTest(position=position + 1),
                self.assertRaisesRegex(
                    BadInput, rf"solve.*circle {position + 1} has zero curvature"
                ),
            ):
                check_tangent(triple)

    def test_zero_curvature_wins_over_non_tangency(self) -> None:
        with self.assertRaises(BadInput):
            check_tangent([(1, 0, 0), (1, 9, 9), (0, 0, 0)])

    def test_third_circle_moved_names_one_and_three_with_measurements(self) -> None:
        # Moving the R9 third centre to y = 0.7 leaves 1-2 tangent. For 1-3 the
        # measured distance is 0.7, the expected |-1 + 1/3| = 2/3 and the
        # tolerance 1e-9 * (1 + 1/3).
        with self.assertRaises(NoSolution) as ctx:
            check_tangent([R9_C1, R9_C2, (3.0, 0.0, 0.7)])
        message = str(ctx.exception)
        self.assertRegex(message, r"solve.*circles 1 and 3 are not tangent")
        self.assertRegex(message, r"measured distance 0\.7,")
        self.assertRegex(message, r"expected 0\.66666666666666\d*,")
        self.assertRegex(message, r"tolerance 1\.33333333\d*e-09")

    def test_pairs_checked_in_order_and_first_failure_named(self) -> None:
        # Circle 2 at (0, 0.5): tangent to 1 (distance 0.5), but 1.5 away... no,
        # 1/6 from circle 3 at (0, 2/3) where 5/6 is needed, so only 2-3 fails.
        only_23: list[Circle] = [R9_C1, (2.0, 0.0, 0.5), R9_C3]
        with self.assertRaisesRegex(NoSolution, "circles 2 and 3 are not tangent"):
            check_tangent(only_23)
        # Circle 3 far away: 1-3 and 2-3 both fail, 1-3 is reported first.
        with self.assertRaisesRegex(NoSolution, "circles 1 and 3 are not tangent"):
            check_tangent([R9_C1, R9_C2, (3.0, 5.0, 5.0)])
        # Circle 2 far away: 1-2 and 2-3 both fail, 1-2 is reported first.
        with self.assertRaisesRegex(NoSolution, "circles 1 and 2 are not tangent"):
            check_tangent([R9_C1, (2.0, 5.0, 5.0), R9_C3])

    def test_tolerance_is_relative_to_the_pair(self) -> None:
        # Moving the third centre up by d changes the 1-3 gap by d (tolerance
        # 1.333e-9) and the 2-3 gap by 0.8 d (tolerance 0.833e-9).
        near: list[Circle] = [R9_C1, R9_C2, (3.0, 0.0, 0.6666666666666666 + 0.9e-9)]
        self.assertIsNone(check_tangent(near))
        far: list[Circle] = [R9_C1, R9_C2, (3.0, 0.0, 0.6666666666666666 + 3e-9)]
        with self.assertRaisesRegex(NoSolution, "circles 1 and 3"):
            check_tangent(far)

    def test_hint_for_inputs_with_six_or_fewer_decimals(self) -> None:
        for third_y in (0.6667, 0.7, 0.123456):
            with (
                self.subTest(y=third_y),
                self.assertRaisesRegex(NoSolution, "full-precision"),
            ):
                check_tangent([R9_C1, R9_C2, (3.0, 0.0, third_y)])

    def test_no_hint_for_integer_coordinates(self) -> None:
        with self.assertRaises(NoSolution) as ctx:
            check_tangent([(1, 0, 0), (1, 3, 0), (4, 1, 1)])
        self.assertNotIn("full-precision", str(ctx.exception))

    def test_no_hint_for_full_precision_coordinates(self) -> None:
        # 1.0000000000000002 has 16 decimals and 1e-07 prints in exponent form;
        # 0.1234567 has 7 decimals, one past the hint's limit.
        for third_y in (0.3333333333333333, 0.1234567, 1e-07):
            with self.subTest(y=third_y):
                with self.assertRaises(NoSolution) as ctx:
                    check_tangent(
                        [(1, 0, 0), (1, 2, 0), (4, 1.0000000000000002, third_y)]
                    )
                self.assertNotIn("full-precision", str(ctx.exception))

    def test_hint_looks_at_every_coordinate_of_every_circle(self) -> None:
        # Only the first circle's x has few decimals; the failing pair is 2-3.
        self.assertTrue(self._hint_for([(1, 0.25, 0), (1, 2, 0), (4, 1, 3)]))
        # Only the last circle's y has few decimals.
        self.assertTrue(self._hint_for([(1, 0, 0), (1, 2, 0), (4, 1, 0.9)]))
        # Only the middle circle's x does.
        self.assertTrue(self._hint_for([(1, 0, 0), (1, 2.5, 0), (4, 1, 3)]))

    def _hint_for(self, circles: list[Circle]) -> bool:
        """Whether the NoSolution for a non-tangent triple carries the hint."""
        with self.assertRaises(NoSolution) as ctx:
            check_tangent(circles)
        return "full-precision" in str(ctx.exception)

    def test_hint_counts_positional_decimals_of_exponent_forms(self) -> None:
        # R24(b): the hint is about the positional form. repr(1e-05) is the
        # exponent form of 0.00001 (5 decimals) and repr(1.5e-05) of 0.000015
        # (6); 1e-07 is 0.0000001 (7), one past the limit.
        wanted = {1e-05: True, 1.5e-05: True, 1e-07: False, 1.5e-07: False}
        for third_y, hint in wanted.items():
            with self.subTest(y=third_y):
                self.assertEqual(
                    self._hint_for([(1, 0, 0), (1, 2, 0), (4, 1, third_y)]), hint
                )

    def test_hint_for_short_and_negative_decimals(self) -> None:
        for third_y in (0.6667, -0.6667, 0.5, -0.5, 0.123456):
            with self.subTest(y=third_y):
                self.assertTrue(self._hint_for([(1, 0, 0), (1, 2, 0), (4, 1, third_y)]))

    def test_no_hint_for_long_decimals(self) -> None:
        for third_y in (0.6666666666666666, -0.6666666666666666, 0.1234567):
            with self.subTest(y=third_y):
                self.assertFalse(
                    self._hint_for([(1, 0, 0), (1, 2, 0), (4, 1, third_y)])
                )

    def test_no_hint_for_integer_valued_floats_or_ints(self) -> None:
        # Integer coordinates are exact whether typed as int or float.
        self.assertFalse(self._hint_for([(1, 0, 0), (1, 2, 0), (4, 1, 1)]))
        self.assertFalse(self._hint_for([(1, 0.0, 0.0), (1, 2.0, 0.0), (4, 1.0, 1.0)]))
        self.assertFalse(self._hint_for([(1, -3.0, 0.0), (1, 2.0, 0.0), (4, 1.0, 1e5)]))

    def test_hint_ignores_short_decimal_curvatures(self) -> None:
        # R24(b) is about centre coordinates only: curvatures 0.5 and 0.25
        # have short decimal forms, the coordinates are all integers, and the
        # triple is not tangent.
        triple: list[Circle] = [(0.5, 0, 0), (0.5, 4, 0), (0.25, 1, 1)]
        self.assertFalse(self._hint_for(triple))

    def test_non_finite_values_are_bad_input_at_every_position(self) -> None:
        # R26. Every case names solve and the circle number. Even the all-
        # tangent R9 triple with one value replaced must be refused, and with
        # an infinite tolerance it would otherwise pass every pair.
        nan, inf = math.nan, math.inf
        slots = {"k": 0, "x": 1, "y": 2}
        cases = [
            ("x", nan),
            ("y", inf),
            ("y", -inf),
            ("k", inf),
            ("k", nan),
            ("k", 5e-324),
            ("k", -5e-324),
        ]
        for position in range(3):
            for slot, value in cases:
                triple = [R9_C1, R9_C2, R9_C3]
                parts = list(triple[position])
                parts[slots[slot]] = value
                triple[position] = (parts[0], parts[1], parts[2])
                for call in (check_tangent, lambda t: solve(t[0], t[1], t[2])):
                    with (
                        self.subTest(position=position + 1, slot=slot, value=value),
                        self.assertRaisesRegex(
                            BadInput, rf"solve.*circle {position + 1} has"
                        ),
                    ):
                        call(triple)

    def test_radius_overflow_boundary(self) -> None:
        # DBL_MAX is 1.797e308. k = 5.6e-309 has radius 1.786e308 (finite, so
        # the circle is an input and only fails tangency); k = 5.5e-309 has
        # radius 1.818e308, which overflows to inf (BadInput).
        rest: list[Circle] = [(1, 3, 0), (1, 0, 3)]
        with self.assertRaises(NoSolution):
            check_tangent([(5.6e-309, 0, 0), *rest])
        with self.assertRaisesRegex(BadInput, "circle 1 has"):
            check_tangent([(5.5e-309, 0, 0), *rest])

    def test_non_finite_is_bad_input_even_when_pairs_are_far_apart(self) -> None:
        with self.assertRaisesRegex(BadInput, "circle 3 has"):
            check_tangent([(1, 0, 0), (1, 9, 9), (4, math.nan, 0)])

    def test_first_bad_circle_is_the_one_named(self) -> None:
        with self.assertRaisesRegex(BadInput, "circle 2 has"):
            check_tangent([(1, 0, 0), (1, math.inf, 0), (4, math.nan, 0)])

    def test_pair_tolerance_includes_exactly_the_bound(self) -> None:
        # Tolerance patched to 0.5: unit circles at distance 3 miss the
        # expected 2 by exactly 1 = 0.5 * (1 + 1), which is still tangent; a
        # further 0.25 is not.
        with mock.patch.object(descartes, "TANGENT_TOL", 0.5):
            self.assertIsNone(check_tangent([(1, 0, 0), (1, 3, 0)]))
            self.assertTrue(descartes._is_tangent((1, 0, 0), (1, 3, 0)))
            with self.assertRaises(NoSolution):
                check_tangent([(1, 0, 0), (1, 3.25, 0)])
            self.assertFalse(descartes._is_tangent((1, 0, 0), (1, 3.25, 0)))

    def test_r10_example_names_the_pair_and_carries_the_hint(self) -> None:
        # CLI: --solve -1,0,0 2,0.5,0 3,0,0.6667. Pair 1-2 is tangent, pair
        # 1-3 misses by 3.3e-5 and the 0.6667 is a rounded short decimal.
        with self.assertRaises(NoSolution) as ctx:
            solve((-1, 0, 0), (2, 0.5, 0), (3, 0, 0.6667))
        message = str(ctx.exception)
        self.assertIn("circles 1 and 3 are not tangent", message)
        self.assertIn("full-precision", message)

    def test_input_not_mutated(self) -> None:
        circles: list[Circle] = [R9_C1, R9_C2, R9_C3]
        before = list(circles)
        check_tangent(circles)
        self.assertEqual(circles, before)


class TestSolve(unittest.TestCase):
    def test_r9_values(self) -> None:
        # Spec R9: curvature 2 at (-0.5, 0), curvature 6 at (0.5, 2/3).
        got = solve(R9_C1, R9_C2, R9_C3)
        self.assertEqual(len(got), 2)
        self.assertTrue(_close(got[0], (2.0, -0.5, 0.0)), got[0])
        self.assertTrue(_close(got[1], (6.0, 0.5, 0.6666666666666666)), got[1])

    def test_every_result_tangent_to_all_three_inputs(self) -> None:
        for result in solve(R9_C1, R9_C2, R9_C3):
            for given in (R9_C1, R9_C2, R9_C3):
                with self.subTest(result=result, given=given):
                    self.assertLessEqual(_gap(result, given), 1e-9)

    def test_scaled_by_100(self) -> None:
        got = solve(
            (-100.0, 0.0, 0.0),
            (200.0, 0.005, 0.0),
            (300.0, 0.0, 0.6666666666666666 / 100),
        )
        self.assertEqual([round(c[0]) for c in got], [200, 600])
        self.assertTrue(_close(got[0], (200.0, -0.005, 0.0), 1e-11))
        self.assertTrue(_close(got[1], (600.0, 0.005, 0.6666666666666666 / 100), 1e-11))

    def test_pasting_a_result_back_recovers_the_third_circle(self) -> None:
        # Four mutually tangent circles are symmetric: replacing the third
        # input by a result must give the third input back among the results.
        for result in solve(R9_C1, R9_C2, R9_C3):
            again = solve(R9_C1, R9_C2, result)
            with self.subTest(result=result):
                self.assertTrue(any(_close(c, R9_C3) for c in again), again)

    def test_straight_line_fourth_is_omitted(self) -> None:
        # Curvatures 1, 1, 4 give 6 +- 2*sqrt(9) = 12 and 0. The complex
        # theorem (hand-evaluated: k4*z4 = 6+3i +- 2(3+i)) puts the curvature-12
        # circle at 1 + 5i/12; the curvature-0 line is dropped.
        got = solve((1, 0, 0), (1, 2, 0), (4, 1, 0.75))
        self.assertEqual(len(got), 1)
        self.assertTrue(_close(got[0], (12.0, 1.0, 5.0 / 12.0)), got[0])

    def test_zero_radicand_gives_two_centres_ordered_by_y(self) -> None:
        # (-1, 2, 2): radicand 0, one curvature 3 with centres y = -+2/3.
        got = solve((-1, 0, 0), (2, 0.5, 0), (2, -0.5, 0))
        self.assertEqual(len(got), 2)
        self.assertTrue(_close(got[0], (3.0, 0.0, -2.0 / 3.0)), got[0])
        self.assertTrue(_close(got[1], (3.0, 0.0, 2.0 / 3.0)), got[1])

    def test_zero_radicand_pair_survives_at_scale_1e10(self) -> None:
        # R26. Curvatures x1e10 and centres /1e10 of the (-1, 2, 2) case: still
        # two curvature-3e10 circles at y = -+(2/3)e-10, which an absolute
        # tolerance of 1e-9 would merge into one.
        got = solve((-1e10, 0, 0), (2e10, 0.5e-10, 0), (2e10, -0.5e-10, 0))
        self.assertEqual(len(got), 2)
        for circle, sign in zip(got, (-1, 1), strict=True):
            want = (3e10, 0.0, sign * 2e-10 / 3)
            with self.subTest(sign=sign):
                self.assertAlmostEqual(circle[0] / want[0], 1.0, delta=1e-9)
                self.assertEqual(circle[1], 0.0)
                self.assertAlmostEqual(circle[2] / want[2], 1.0, delta=1e-9)

    def test_zero_radicand_pair_survives_at_small_scale(self) -> None:
        got = solve((-1e-5, 0, 0), (2e-5, 5e4, 0), (2e-5, -5e4, 0))
        self.assertEqual([round(c[0] / 1e-5) for c in got], [3, 3])
        self.assertLess(got[0][2], 0.0)
        self.assertGreater(got[1][2], 0.0)

    def _scaled_line_triple(self, scale: float) -> list[Circle]:
        # The hand-derived (1, 1, 4) triple (fourth curvatures 12 and a line)
        # with curvatures x scale and centres / scale.
        base = ((1, 0, 0), (1, 2, 0), (4, 1, 0.75))
        return [(k * scale, x / scale, y / scale) for k, x, y in base]

    def test_rounding_ghost_of_a_line_is_not_a_circle(self) -> None:
        # At scale 0.3 and 1e-3 float rounding turns the line's curvature 0
        # into -2.2e-16 and 8.7e-19; without the R25 threshold a fake circle
        # of radius ~1e15 passes tangency. Exactly one circle must come back:
        # curvature 12 * scale at (1, 5/12) / scale.
        for scale in (0.3, 1e-3, 1.0, 7.0, 1e10, 1e-10):
            got = solve(*self._scaled_line_triple(scale))
            with self.subTest(scale=scale):
                self.assertEqual(len(got), 1)
                self.assertAlmostEqual(got[0][0] / (12 * scale), 1.0, delta=1e-9)
                self.assertAlmostEqual(got[0][1] * scale, 1.0, delta=1e-9)
                self.assertAlmostEqual(got[0][2] * scale, 5.0 / 12.0, delta=1e-9)

    def test_line_listed_first_does_not_hide_the_circle(self) -> None:
        # All-negative curvatures: descartes_fourth returns (0, -12) with the
        # line first. By the sign symmetry of the theorem (k -> -k leaves every
        # centre unchanged) the answer is (-12, 1, 5/12).
        got = solve((-1, 0, 0), (-1, 2, 0), (-4, 1, 0.75))
        self.assertEqual(len(got), 1)
        self.assertTrue(_close(got[0], (-12.0, 1.0, 5.0 / 12.0)), got)

    def test_line_threshold_includes_exactly_the_bound(self) -> None:
        # Tolerance patched to 2: for curvatures 1, 1, 4 the bound is 2 * 6 =
        # 12 and the fourth curvatures are 12 and 0, so both count as the line.
        with mock.patch.object(descartes, "TANGENT_TOL", 2.0):
            self.assertEqual(
                descartes._tangent_circles((1, 0, 0), (1, 2, 0), (4, 1, 0.75)), []
            )

    def test_equal_curvature_and_y_are_ordered_by_x(self) -> None:
        # The (-1, 2, 2) case turned on its side: both curvature-3 circles sit
        # on the x axis at x = -+2/3 (y exactly 0), so only x can order them.
        got = solve((-1, 0, 0), (2, 0, 0.5), (2, 0, -0.5))
        self.assertEqual(len(got), 2)
        self.assertTrue(_close(got[0], (3.0, -2.0 / 3.0, 0.0)), got[0])
        self.assertTrue(_close(got[1], (3.0, 2.0 / 3.0, 0.0)), got[1])

    def test_equal_curvatures_are_ordered_by_y_not_x(self) -> None:
        # (-1, 2, 2) rotated by the 3-4-5 angle (cos 0.8, sin 0.6): the two
        # curvature-3 centres are +-(2/3)(-0.6, 0.8) = +-(-0.4, 0.5333). The
        # circle with the smaller y has the larger x, so y and x disagree.
        got = solve((-1, 0, 0), (2, 0.4, 0.3), (2, -0.4, -0.3))
        self.assertEqual(len(got), 2)
        self.assertTrue(_close(got[0], (3.0, 0.4, -8.0 / 15.0)), got[0])
        self.assertTrue(_close(got[1], (3.0, -0.4, 8.0 / 15.0)), got[1])

    def test_results_ordered_by_curvature(self) -> None:
        got = solve(R9_C1, R9_C2, R9_C3)
        self.assertEqual(got, sorted(got, key=lambda c: (c[0], c[2])))

    def test_any_three_circles_of_a_root_give_the_fourth(self) -> None:
        for root in ALL_ROOTS:
            circles = root_centres(root)
            for omitted in range(4):
                triple = [c for i, c in enumerate(circles) if i != omitted]
                with self.subTest(root=root, omitted=omitted):
                    got = solve(triple[0], triple[1], triple[2])
                    self.assertTrue(
                        any(_close(c, circles[omitted], 1e-7) for c in got), got
                    )

    def test_non_tangent_input_rejected_before_solving(self) -> None:
        with (
            mock.patch.object(
                descartes, "_tangent_circles", side_effect=AssertionError
            ),
            self.assertRaisesRegex(NoSolution, "circles 1 and 3 are not tangent"),
        ):
            solve(R9_C1, R9_C2, (3.0, 0.0, 0.6667))

    def test_zero_curvature_is_bad_input(self) -> None:
        with self.assertRaisesRegex(BadInput, "zero curvature"):
            solve((0.0, 0.0, 0.0), R9_C2, R9_C3)

    def test_no_surviving_circle_is_no_solution(self) -> None:
        with (
            mock.patch.object(descartes, "_tangent_circles", return_value=[]),
            self.assertRaisesRegex(NoSolution, "solve.*no circle is tangent"),
        ):
            solve(R9_C1, R9_C2, R9_C3)

    def test_repeated_calls_equal(self) -> None:
        self.assertEqual(solve(R9_C1, R9_C2, R9_C3), solve(R9_C1, R9_C2, R9_C3))


class TestSameCircle(unittest.TestCase):
    """R26: distinct when curvatures differ by more than 1e-9 * |k| or centres
    by more than 1e-9 * |1/k|, at every scale."""

    SCALES = (1e-10, 0.5, 3.0, 1e10)

    def test_identical_circles_are_the_same(self) -> None:
        for k in self.SCALES:
            with self.subTest(k=k):
                self.assertTrue(descartes._same_circle((k, 1.0, 2.0), (k, 1.0, 2.0)))

    def test_curvatures_within_the_relative_tolerance_are_the_same(self) -> None:
        for k in self.SCALES:
            with self.subTest(k=k):
                self.assertTrue(
                    descartes._same_circle((k, 0.0, 0.0), (k * (1 + 0.5e-9), 0.0, 0.0))
                )

    def test_curvatures_beyond_the_relative_tolerance_are_distinct(self) -> None:
        for k in self.SCALES:
            with self.subTest(k=k):
                self.assertFalse(
                    descartes._same_circle((k, 0.0, 0.0), (k * (1 + 2e-9), 0.0, 0.0))
                )

    def test_centres_within_the_relative_tolerance_are_the_same(self) -> None:
        for k in self.SCALES:
            shift = 0.5e-9 / k
            for dx, dy in ((shift, 0.0), (0.0, shift)):
                with self.subTest(k=k, dx=dx, dy=dy):
                    self.assertTrue(descartes._same_circle((k, dx, dy), (k, 0.0, 0.0)))

    def test_centres_beyond_the_relative_tolerance_are_distinct(self) -> None:
        for k in self.SCALES:
            shift = 2e-9 / k
            for dx, dy in ((shift, 0.0), (0.0, shift)):
                with self.subTest(k=k, dx=dx, dy=dy):
                    self.assertFalse(descartes._same_circle((k, dx, dy), (k, 0.0, 0.0)))

    def test_centre_distance_is_euclidean(self) -> None:
        # Each coordinate is off by 0.8 of the bound, the distance by 1.13.
        for k in self.SCALES:
            shift = 0.8e-9 / k
            with self.subTest(k=k):
                self.assertFalse(
                    descartes._same_circle((k, shift, shift), (k, 0.0, 0.0))
                )

    def test_both_conditions_are_required(self) -> None:
        # Same centre but another curvature, and the same curvature but
        # another centre, are different circles.
        self.assertFalse(descartes._same_circle((3.0, 0.0, 0.0), (6.0, 0.0, 0.0)))
        self.assertFalse(descartes._same_circle((3.0, 0.0, 0.0), (3.0, 1.0, 0.0)))

    def test_bounds_are_inclusive(self) -> None:
        # Tolerance patched to 0.5: |3 - 2| = 1 = 0.5 * 2 and a centre shift of
        # 0.25 = 0.5 * |1/2|, both exact in binary.
        with mock.patch.object(descartes, "TANGENT_TOL", 0.5):
            self.assertTrue(descartes._same_circle((3.0, 0.0, 0.0), (2.0, 0.0, 0.0)))
            self.assertFalse(descartes._same_circle((3.5, 0.0, 0.0), (2.0, 0.0, 0.0)))
            self.assertTrue(descartes._same_circle((2.0, 0.25, 0.0), (2.0, 0.0, 0.0)))
            self.assertFalse(
                descartes._same_circle((2.0, 0.3125, 0.0), (2.0, 0.0, 0.0))
            )


def _positive_set(
    circles: list[tuple[float, float, float]], mirror: bool = False
) -> set[tuple[int, float, float]]:
    sign = -1.0 if mirror else 1.0
    return {
        (round(k), round(x, 7) + 0.0, round(sign * y, 7) + 0.0) for k, x, y in circles
    }


class TestVisible(unittest.TestCase):
    def test_r2_circle_count(self) -> None:
        self.assertEqual(len(visible(ROOT_A, 30)), 38)

    def test_count_and_curvatures_match_pack(self) -> None:
        for root in ALL_ROOTS:
            for n in (0, 1, 2, 3, 10, 30, 100, 300):
                count, bitmap = pack(root, n)
                got = visible(root, n)
                with self.subTest(root=root, n=n):
                    self.assertEqual(len(got), count)
                    self.assertEqual(
                        sorted({round(c[0]) for c in got}), distinct(bitmap)
                    )

    def test_pinned_counts(self) -> None:
        for root, n, count, _ in PINNED:
            if n <= 1000:
                with self.subTest(root=root, n=n):
                    self.assertEqual(len(visible(root, n)), count)

    def test_centres_match_the_oracle_at_30(self) -> None:
        # Spec: the (k, x, y) set agrees with the oracle up to reflection in
        # the x axis, rounded to 7 places.
        for root in ALL_ROOTS:
            want = {
                (round(k), round(z.real, 7) + 0.0, round(z.imag, 7) + 0.0)
                for k, z in _oracle_cached(root)
                if 0 < k <= 30
            }
            got = visible(root, 30)
            with self.subTest(root=root):
                self.assertEqual(len(got), len(want))
                self.assertIn(
                    _positive_set(got),
                    (want, {(k, x, -y + 0.0) for k, x, y in want}),
                )

    def test_centres_match_the_oracle_at_1000(self) -> None:
        # At n = 1000 a coordinate can sit within 1e-7 of a rounding boundary,
        # so each circle is matched to an oracle circle within 1e-6 instead.
        for root in ALL_ROOTS:
            pool = [
                (round(k), z.real, z.imag)
                for k, z in _oracle_cached(root)
                if 0 < k <= 1000
            ]
            got = visible(root, 1000)
            self.assertEqual(len(got), len(pool))
            for k, x, y in got:
                with self.subTest(root=root, k=k):
                    hit = next(
                        (
                            c
                            for c in pool
                            if c[0] == round(k)
                            and abs(c[1] - x) < 1e-6
                            and abs(c[2] - y) < 1e-6
                        ),
                        None,
                    )
                    self.assertIsNotNone(hit, f"no oracle circle for {(k, x, y)}")
                    if hit is not None:
                        pool.remove(hit)
            self.assertEqual(pool, [])

    def test_only_positive_circles(self) -> None:
        for root in ALL_ROOTS:
            with self.subTest(root=root):
                self.assertTrue(all(c[0] > 0 for c in visible(root, 100)))

    def test_hand_derived_small_case(self) -> None:
        # At limit 3 the (-1,2,2,3) packing shows the root's own 2, 2, 3 and the
        # mirror curvature-3 circle: centres (+-1/2, 0) and (0, +-2/3).
        got = sorted(visible(ROOT_A, 3))
        want: list[Circle] = [
            (2.0, -0.5, 0.0),
            (2.0, 0.5, 0.0),
            (3.0, 0.0, -2.0 / 3.0),
            (3.0, 0.0, 2.0 / 3.0),
        ]
        self.assertEqual(len(got), 4)
        for g, w in zip(got, want, strict=True):
            self.assertTrue(_close(g, w), f"{g} != {w}")

    def test_limit_zero_and_below_smallest_curvature(self) -> None:
        self.assertEqual(visible(ROOT_A, 0), [])
        self.assertEqual(visible(ROOT_A, 1), [])
        self.assertEqual(visible(ROOT_D, 10), [])

    def test_limit_equal_to_smallest_curvature(self) -> None:
        self.assertEqual(sorted(round(c[0]) for c in visible(ROOT_A, 2)), [2, 2])

    def test_negative_limit_rejected(self) -> None:
        with self.assertRaisesRegex(BadInput, r"visible\(limit=-1\)"):
            visible(ROOT_A, -1)

    def test_limit_above_ceiling_rejected(self) -> None:
        with (
            mock.patch.object(descartes, "N_MAX", 30),
            self.assertRaisesRegex(
                BadInput, r"visible\(limit=31\): limit must be at most 30"
            ),
        ):
            visible(ROOT_A, 31)

    def test_limit_at_ceiling_accepted(self) -> None:
        with mock.patch.object(descartes, "N_MAX", 30):
            self.assertEqual(len(visible(ROOT_A, 30)), 38)

    def test_invalid_roots_rejected_naming_visible(self) -> None:
        cases: list[tuple[Root, str]] = [
            ((-1, 2, 3, 6), "not reduced"),
            ((2, -1, 2, 3), "not sorted"),
            ((-1, 2, 2, 4), "not a Descartes quadruple"),
            ((0, 1, 1, 4), "exactly one negative"),
        ]
        for root, what in cases:
            with (
                self.subTest(root=root),
                self.assertRaisesRegex(BadInput, rf"visible.*{what}"),
            ):
                visible(root, 100)

    # As for pack: no valid quadruple can fail the growth test, so it is tested
    # on roots that break the Descartes relation. The placement and the root
    # check are stubbed because they cannot handle such a root; _child is
    # budgeted so a missing guard fails fast instead of eating RAM. Without the
    # guard (-1, 1, 1, 1) reflects forever; with only quad[i] != k, (-1, 1, 3, 5)
    # pushes a falling curvature and runs past the budget (the guard-weakened
    # walk was measured to run past the budget on it, the intact one to finish).
    def test_walk_terminates_when_root_invariant_is_broken(self) -> None:
        real_child = descartes._child
        for root in [(-1, 1, 1, 1), (-1, 1, 3, 5), (-1, 2, 2, 2)]:
            with self.subTest(root=root):
                calls = 0

                def budgeted_child(
                    ks: list[int], zs: list[complex], i: int, k: int
                ) -> tuple[list[int], list[complex], int]:
                    nonlocal calls
                    calls += 1
                    self.assertLess(calls, 10_000, "visible walk did not terminate")
                    return real_child(ks, zs, i, k)

                with (
                    mock.patch.object(descartes, "_check_reduced_root"),
                    mock.patch.object(
                        descartes,
                        "_place_root",
                        lambda r: [(float(k), 0.0, 0.0) for k in r],
                    ),
                    mock.patch.object(descartes, "_child", budgeted_child),
                ):
                    got = visible(root, 30)
                self.assertTrue(all(0 <= c[0] <= 30 for c in got))

    def test_repeated_calls_equal_and_fresh(self) -> None:
        first = visible(ROOT_A, 100)
        second = visible(ROOT_A, 100)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)

    def test_smaller_run_after_larger_is_unaffected(self) -> None:
        visible(ROOT_A, 1000)
        self.assertEqual(len(visible(ROOT_A, 30)), 38)


class TestModule(unittest.TestCase):
    def test_module_exports(self) -> None:
        self.assertTrue(issubclass(descartes.BadInput, Exception))
        self.assertTrue(issubclass(descartes.NoSolution, Exception))


if __name__ == "__main__":
    unittest.main()
