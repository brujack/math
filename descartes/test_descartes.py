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
    NoSolution,
    descartes_fourth,
    distinct,
    pack,
    validate_root,
)

Root = tuple[int, int, int, int]
Circle = tuple[float, complex]

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


def _residual(c: Circle, others: list[Circle]) -> float:
    """Largest tangency error of circle c against each of the others."""
    k, z = c
    worst = 0.0
    for ko, zo in others:
        gap = abs(abs(z - zo) - abs(1.0 / k + 1.0 / ko))
        worst = max(worst, gap)
    return worst


def _tangent_candidates(c1: Circle, c2: Circle, c3: Circle) -> list[Circle]:
    """Circles tangent to all three, by the complex Descartes theorem."""
    (k1, z1), (k2, z2), (k3, z3) = c1, c2, c3
    s = max(k1 * k2 + k2 * k3 + k3 * k1, 0.0)
    w = k1 * k2 * z1 * z2 + k2 * k3 * z2 * z3 + k3 * k1 * z3 * z1
    root_w = cmath.sqrt(w)
    ksum = k1 + k2 + k3
    zsum = k1 * z1 + k2 * z2 + k3 * z3
    found: list[Circle] = []
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


def _root_circles(root: Root) -> list[Circle]:
    a, b, c, d = root
    big_r = 1.0 / abs(a)
    r2 = 1.0 / b
    x2 = big_r - r2
    r3 = 1.0 / c
    x3 = ((big_r - r3) ** 2 - (r2 + r3) ** 2 + x2**2) / (2 * x2)
    y3_sq = (big_r - r3) ** 2 - x3**2
    # A centre on the axis leaves a rounding residue that sqrt would amplify.
    y3 = math.sqrt(y3_sq) if y3_sq > 1e-12 else 0.0
    c1: Circle = (float(a), 0j)
    c2: Circle = (float(b), complex(x2, 0.0))
    c3: Circle = (float(c), complex(x3, y3))
    fourth = [
        cand for cand in _tangent_candidates(c1, c2, c3) if abs(cand[0] - d) < 1e-6
    ]
    assert fourth, f"no fourth circle of curvature {d} for root {root}"
    return [c1, c2, c3, fourth[0]]


def _oracle(root: Root, n_max: int) -> list[Circle]:
    """Every distinct circle of the packing with curvature <= n_max."""
    circles: list[Circle] = []
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


_ORACLE_CACHE: dict[Root, list[Circle]] = {}


def _oracle_cached(root: Root) -> list[Circle]:
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


class TestModule(unittest.TestCase):
    def test_module_exports(self) -> None:
        self.assertTrue(issubclass(descartes.BadInput, Exception))
        self.assertTrue(issubclass(descartes.NoSolution, Exception))


if __name__ == "__main__":
    unittest.main()
