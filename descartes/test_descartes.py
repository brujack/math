"""Tests for descartes: Descartes fourth circle, root reduction and packing.

The oracle below is test-only and shares no code with descartes.py: it builds
the four root circles in the plane and grows the packing by the complex
Descartes theorem, so it checks the integer recurrence against geometry.
"""

import cmath
import math
from collections import deque

import pytest

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

ALL_ROOTS = [ROOT_A, ROOT_B, ROOT_C, ROOT_D, ROOT_E]
ORACLE_N = 1000


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


class TestDescartesFourth:
    def test_returns_both_solutions(self) -> None:
        assert descartes_fourth(2, 3, 6) == (23.0, -1.0)

    def test_double_root_when_radicand_zero(self) -> None:
        assert descartes_fourth(-1, 2, 2) == (3.0, 3.0)

    def test_tiny_negative_radicand_is_clamped(self) -> None:
        plus, minus = descartes_fourth(1.0, 1.0, -0.5000000000000001)
        assert plus == minus
        assert plus == pytest.approx(1.5)

    def test_negative_radicand_raises_naming_inputs(self) -> None:
        with pytest.raises(NoSolution, match=r"1.*1.*-1"):
            descartes_fourth(1, 1, -1)

    def test_radicand_just_below_tolerance_raises(self) -> None:
        # s = -2e-9 against a threshold of -1e-12 * 1.
        with pytest.raises(NoSolution):
            descartes_fourth(1.0, 1.0, -0.5 - 1e-9)

    def test_radicand_just_inside_tolerance_clamps(self) -> None:
        # s = -2e-13 is inside the -1e-12 * 1 window.
        plus, minus = descartes_fourth(1.0, 1.0, -0.5 - 1e-13)
        assert plus == minus

    @pytest.mark.parametrize("x", [1e3, 7.3e4, 1e6, 3.1e7, 1e9])
    def test_tolerance_scales_with_magnitude(self, x: float) -> None:
        # s is exactly 0 in real arithmetic; rounding error grows like x**2.
        descartes_fourth(-2 * x / 7, 3 * x / 7, 6 * x / 7)

    def test_result_satisfies_descartes_relation(self) -> None:
        for fourth in descartes_fourth(2, 3, 6):
            total = 2 + 3 + 6 + fourth
            assert total**2 == pytest.approx(2 * (4 + 9 + 36 + fourth**2))


# --- validate_root --------------------------------------------------------------


class TestValidateRoot:
    def test_valid_reduced_root_unchanged(self) -> None:
        assert validate_root(-1, 2, 2, 3) == ROOT_A

    def test_unordered_input_is_sorted(self) -> None:
        assert validate_root(3, 2, -1, 2) == ROOT_A

    @pytest.mark.parametrize("root", [(-1, 2, 3, 6), (-1, 3, 6, 14), (-1, 2, 2, 3)])
    def test_reduces_to_root_a(self, root: Root) -> None:
        assert validate_root(*root) == ROOT_A

    def test_already_reduced_roots_are_fixed_points(self) -> None:
        for root in ALL_ROOTS:
            assert validate_root(*root) == root

    def test_float_is_bad_input(self) -> None:
        with pytest.raises(BadInput):
            validate_root(-1, 2, 2.5, 3)

    def test_bool_is_bad_input(self) -> None:
        with pytest.raises(BadInput):
            validate_root(-1, 2, 2, True)

    def test_not_descartes_quadruple(self) -> None:
        with pytest.raises(NoSolution) as info:
            validate_root(-1, 2, 2, 4)
        message = str(info.value)
        assert "(-1, 2, 2, 4)" in message
        assert "(Σk)²=49, 2Σk²=50" in message

    def test_relation_fails_with_square_sum_below(self) -> None:
        # (Σk)²=64 exceeds 2Σk²=56, so the relation fails in the other direction.
        with pytest.raises(NoSolution, match="not a Descartes"):
            validate_root(-1, 3, 3, 3)

    def test_zero_is_not_negative(self) -> None:
        # (0, 1, 1, 4) satisfies the relation; zero must not count as negative.
        with pytest.raises(NoSolution, match="exactly one negative"):
            validate_root(0, 1, 1, 4)

    def test_zero_curvatures_have_no_single_negative(self) -> None:
        with pytest.raises(NoSolution, match=r"\(0, 0, 1, 1\)"):
            validate_root(0, 0, 1, 1)

    def test_two_negatives_rejected(self) -> None:
        # (-1, -1, 0, 0) satisfies the Descartes equation with two negatives.
        with pytest.raises(NoSolution, match=r"\(-1, -1, 0, 0\)"):
            validate_root(-1, -1, 0, 0)

    def test_all_positive_rejected(self) -> None:
        # (0,0,0,0) satisfies the equation and has no negative value.
        with pytest.raises(NoSolution):
            validate_root(0, 0, 0, 0)


# --- pack ---------------------------------------------------------------------


class TestPackPinned:
    @pytest.mark.parametrize(("root", "n", "count", "n_distinct"), PINNED)
    def test_pinned_values(
        self, root: Root, n: int, count: int, n_distinct: int
    ) -> None:
        got_count, bitmap = pack(root, n)
        assert (got_count, len(distinct(bitmap))) == (count, n_distinct)

    def test_distinct_list_root_a_30(self) -> None:
        _, bitmap = pack(ROOT_A, 30)
        assert distinct(bitmap) == [2, 3, 6, 11, 14, 15, 18, 23, 26, 27, 30]

    def test_bitmap_size(self) -> None:
        _, bitmap = pack(ROOT_A, 30)
        assert len(bitmap) == 30 // 8 + 1


class TestPackBoundaries:
    def test_n_below_every_curvature_is_empty(self) -> None:
        count, bitmap = pack(ROOT_A, 1)
        assert count == 0
        assert distinct(bitmap) == []
        assert not any(bitmap)

    def test_n_zero(self) -> None:
        count, bitmap = pack(ROOT_A, 0)
        assert (count, distinct(bitmap), len(bitmap)) == (0, [], 1)

    def test_n_equal_to_smallest_curvature_counts_it_once_per_circle(self) -> None:
        count, bitmap = pack(ROOT_A, 2)
        assert count == 2
        assert distinct(bitmap) == [2]

    def test_n_one_below_curvature_excludes_it(self) -> None:
        count, bitmap = pack(ROOT_A, 1)
        assert (count, distinct(bitmap)) == (0, [])

    def test_bounding_circle_is_never_counted(self) -> None:
        _, bitmap = pack(ROOT_A, 30)
        assert all(k > 0 for k in distinct(bitmap))


class TestPackPreconditions:
    @pytest.mark.parametrize("n", [-1, -9])
    def test_negative_n_rejected(self, n: int) -> None:
        with pytest.raises(BadInput, match=rf"pack.*{n}"):
            pack(ROOT_A, n)

    def test_unreduced_root_rejected(self) -> None:
        with pytest.raises(BadInput, match=r"pack.*\(-1, 2, 3, 6\)"):
            pack((-1, 2, 3, 6), 100)

    def test_unsorted_root_rejected(self) -> None:
        with pytest.raises(BadInput, match="pack"):
            pack((2, -1, 2, 3), 100)

    def test_non_descartes_root_rejected(self) -> None:
        with pytest.raises(BadInput, match="pack"):
            pack((-1, 2, 2, 4), 100)

    def test_two_negative_root_rejected(self) -> None:
        with pytest.raises(BadInput, match="pack"):
            pack((-1, -1, 0, 0), 100)


class TestPackLimits:
    """pack is bounded by construction: a ceiling on n and a strictly
    increasing curvature on every pushed reflection."""

    def test_ceiling_matches_largest_k(self) -> None:
        assert descartes.N_MAX == 10**6

    # Every ceiling test lowers N_MAX first. Called with the real ceiling, a
    # missing or broken check would make the test itself a ~1e10-circle run.
    def test_n_above_ceiling_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(descartes, "N_MAX", 30)
        with pytest.raises(BadInput, match=r"pack\(n=31\): n must be at most 30"):
            pack(ROOT_A, 31)

    def test_n_at_ceiling_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(descartes, "N_MAX", 30)
        assert pack(ROOT_A, 30)[0] == 38

    # For any real Descartes quadruple the only decreasing reflection is the one
    # just made, which the DFS already skips, so the guard cannot be tested on
    # valid input. Both roots break the Descartes relation: without the guard
    # (-1, 1, 1, 1) reflects forever, and with only k != quad[i] (-1, 1, 1, 2)
    # pushes a falling curvature that goes negative. _mark is budgeted so a
    # missing guard fails fast instead of eating RAM.
    @pytest.mark.parametrize("root", [(-1, 1, 1, 1), (-1, 1, 1, 2)])
    def test_dfs_terminates_when_root_invariant_is_broken(
        self, monkeypatch: pytest.MonkeyPatch, root: Root
    ) -> None:
        calls = 0
        real_mark = descartes._mark

        def budgeted_mark(bitmap: bytearray, k: int) -> None:
            nonlocal calls
            calls += 1
            assert calls < 10_000, "pack DFS did not terminate"
            real_mark(bitmap, k)

        monkeypatch.setattr(descartes, "_check_reduced_root", lambda _root: None)
        monkeypatch.setattr(descartes, "_mark", budgeted_mark)
        count, bitmap = pack(root, 30)
        assert count == calls
        assert all(0 <= k <= 30 for k in distinct(bitmap))


class TestPackState:
    def test_repeated_calls_equal(self) -> None:
        assert pack(ROOT_A, 100) == pack(ROOT_A, 100)

    def test_smaller_run_after_larger_is_unaffected(self) -> None:
        pack(ROOT_A, 1000)
        assert pack(ROOT_A, 30)[0] == 38

    def test_each_call_returns_fresh_bitmap(self) -> None:
        _, first = pack(ROOT_A, 30)
        _, second = pack(ROOT_A, 30)
        assert first is not second

    def test_count_monotone_in_n(self) -> None:
        counts = [pack(ROOT_A, n)[0] for n in range(80)]
        assert counts == sorted(counts)


# --- oracle agreement ------------------------------------------------------------


def _oracle_view(root: Root, n: int) -> tuple[int, list[int]]:
    ks = [round(k) for k, _ in _oracle_cached(root) if 0 < round(k) <= n]
    return len(ks), sorted(set(ks))


class TestOracle:
    @pytest.mark.parametrize("root", ALL_ROOTS)
    def test_oracle_matches_pack_at_pinned_n(self, root: Root) -> None:
        for r, n, _, _ in PINNED:
            if r != root or n > ORACLE_N:
                continue
            count, bitmap = pack(root, n)
            assert (count, distinct(bitmap)) == _oracle_view(root, n), (root, n)

    @pytest.mark.parametrize("root", ALL_ROOTS)
    def test_oracle_matches_pack_for_small_n_sweep(self, root: Root) -> None:
        for n in range(61):
            count, bitmap = pack(root, n)
            assert (count, distinct(bitmap)) == _oracle_view(root, n), (root, n)

    def test_oracle_root_circles_are_mutually_tangent(self) -> None:
        for root in ALL_ROOTS:
            circles = _root_circles(root)
            for i, ci in enumerate(circles):
                assert (
                    _residual(ci, [c for j, c in enumerate(circles) if j != i]) < 1e-6
                )


def test_module_exports() -> None:
    assert issubclass(descartes.BadInput, Exception)
    assert issubclass(descartes.NoSolution, Exception)
