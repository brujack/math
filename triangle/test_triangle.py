"""Unit tests for triangle.py (solver, renderer and CLI sections)."""

import contextlib
import io
import math
import pathlib
import random
import re
import subprocess
import sys
import unittest
from dataclasses import replace
from unittest import mock

from triangle import (
    CONTRACT_ARGS,
    CONTRACT_EXPECT,
    NoTriangle,
    Solved,
    Triangle,
    TriangleInputError,
    _check,
    _project,
    main,
    render,
    solve,
)


def _rel(got: float, want: float) -> float:
    return abs(got - want) / abs(want)


class TestSSS(unittest.TestCase):
    def test_3_4_5(self):
        s = solve({"a": 3, "b": 4, "c": 5})
        self.assertEqual(len(s.solutions), 1)
        t = s.solutions[0]
        self.assertIsInstance(t, Triangle)
        self.assertEqual(t.C, math.pi / 2)
        self.assertAlmostEqual(math.degrees(t.A), 36.86989764584402, places=12)
        self.assertEqual(t.area, 6.0)
        self.assertEqual(t.perimeter, 12.0)
        self.assertEqual(s.extras, [])
        self.assertIsInstance(s, Solved)

    def test_equilateral(self):
        t = solve({"a": 2, "b": 2, "c": 2}).solutions[0]
        for ang in (t.A, t.B, t.C):
            self.assertAlmostEqual(ang, math.pi / 3, places=15)
        self.assertAlmostEqual(t.area, math.sqrt(3), places=15)

    def test_needle_area_positive_finite(self):
        t = solve({"a": 1, "b": 1, "c": 1.9999999}).solutions[0]
        self.assertGreater(t.area, 0)
        self.assertTrue(math.isfinite(t.area))
        self.assertGreater(min(t.A, t.B, t.C), 0)

    def test_inequality_fails_on_equality(self):
        with self.assertRaises(NoTriangle):
            solve({"a": 1, "b": 2, "c": 3})

    def test_inequality_fails_on_violation_any_order(self):
        cases: list[dict[str, float]] = [
            {"a": 1, "b": 1, "c": 5},
            {"a": 5, "b": 1, "c": 1},
            {"a": 1, "b": 5, "c": 1},
            {"a": 1, "b": 3, "c": 2},
            {"a": 3, "b": 1, "c": 2},
        ]
        for sides in cases:
            with self.assertRaises(NoTriangle):
                solve(sides)

    def test_inequality_message(self):
        with self.assertRaises(NoTriangle) as cm:
            solve({"a": 1, "b": 2, "c": 3})
        self.assertEqual(
            str(cm.exception),
            "no triangle: the sides do not satisfy the triangle inequality",
        )


class TestNumericalAccuracy(unittest.TestCase):
    """References: mpmath at 60 digits from the double inputs, pasted as literals."""

    def test_thin_triangle_angles(self):
        t = solve({"a": 1e-4, "b": 1, "c": 1.00009}).solutions[0]
        self.assertLessEqual(_rel(t.A, 0.00004358702806688210832467), 1e-12)
        self.assertLessEqual(_rel(t.B, 0.4510050187743167058038), 1e-12)
        self.assertLessEqual(_rel(t.C, 2.690544047787409650551), 1e-12)

    def test_needle_angles(self):
        t = solve({"a": 1e5, "b": 99999.99979, "c": 0.00029}).solutions[0]
        self.assertLessEqual(_rel(t.A, 2.38057989002972644304), 1e-12)
        self.assertLessEqual(_rel(t.B, 0.761012761560066775818), 1e-12)
        self.assertLessEqual(_rel(t.C, 2.000000019604207673821e-9), 1e-12)

    def test_needle_kahan_area(self):
        t = solve({"a": 1e5, "b": 99999.99979, "c": 0.00029}).solutions[0]
        self.assertLessEqual(_rel(t.area, 10.0000000770210383233), 1e-12)

    def test_thin_triangle_area(self):
        t = solve({"a": 1e-4, "b": 1, "c": 1.00009}).solutions[0]
        self.assertLessEqual(_rel(t.area, 0.00002179547544280278274504), 1e-12)


class TestNearFlat(unittest.TestCase):
    """Triangles within a hair of flat.  References: mpmath at 60 digits from
    the solver's own radian doubles (math.radians of the input, and pi - (A + B)
    for a third angle), pasted as literals."""

    def test_sas_near_180(self):
        t = solve({"a": 1, "b": 1, "C": 179.999999}).solutions[0]
        self.assertLessEqual(_rel(t.c, 1.999999999999999923845643), 1e-15)
        self.assertLessEqual(_rel(t.A, 8.726646355709176331455384e-9), 1e-12)
        self.assertLessEqual(_rel(t.B, 8.726646355709176331455384e-9), 1e-12)
        self.assertLessEqual(_rel(t.area, 8.726646355709175888407291e-9), 1e-12)

    def test_sas_near_0(self):
        t = solve({"a": 1, "b": 1, "C": 1e-300}).solutions[0]
        self.assertLessEqual(_rel(t.c, 1.745329251994329541674244e-302), 1e-12)
        self.assertLessEqual(_rel(t.area, 8.726646259971647708371221e-303), 1e-12)

    def test_aas_sliver_area(self):
        # Heron's formula on the rounded law-of-sines sides printed 8.8412 here.
        t = solve({"b": 10, "A": 179.99, "B": 1e-5}).solutions[0]
        self.assertLessEqual(_rel(t.area, 8.717919525294126408248203), 1e-12)
        self.assertLessEqual(_rel(t.c, 9989.99994939336330924282), 1e-12)

    def test_aas_near_180(self):
        t = solve({"a": 1, "A": 179.9999999, "B": 0.00000005}).solutions[0]
        self.assertLessEqual(_rel(t.b, 0.4999999756616717356928688), 1e-12)
        self.assertLessEqual(_rel(t.c, 0.4999999649164552152657486), 1e-12)
        self.assertLessEqual(_rel(t.area, 2.181661411912069483346102e-10), 1e-12)

    def test_ssa_near_180(self):
        t = solve({"a": 2, "b": 1, "A": 179.999995}).solutions[0]
        self.assertLessEqual(_rel(t.c, 1.000000000000001903858875), 1e-12)
        self.assertLessEqual(_rel(t.B, 4.363323131157187536701764e-8), 1e-12)
        self.assertLessEqual(_rel(t.C, 4.363323131157195843853231e-8), 1e-12)
        self.assertLessEqual(_rel(t.area, 4.363323131157194459327986e-8), 1e-12)

    def test_ssa_tiny_opposite_side_two_solutions(self):
        # z ~ y here, so an angle taken from the rounded z cancels.
        s = solve({"A": 0.002976492691072458, "a": 5.699411820883214e-05, "b": 1})
        self.assertEqual(len(s.solutions), 2)
        t1, t2 = s.solutions
        self.assertLessEqual(_rel(t1.c, 1.000023441534825125265789), 1e-14)
        self.assertLessEqual(_rel(t1.B, 1.146893337921280259438125), 1e-14)
        self.assertLessEqual(_rel(t1.C, 1.994647366070892218203381), 1e-14)
        self.assertLessEqual(_rel(t2.c, 0.9999765557664141823821949), 1e-14)
        self.assertLessEqual(_rel(t2.B, 1.994699315668512979024518), 1e-14)
        self.assertLessEqual(_rel(t2.C, 1.146841388323659498616988), 1e-14)

    def test_bounded_ssa_tiny_opposite_side_property(self):
        rng = random.Random(7)
        for _ in range(2000):
            y = 10 ** rng.uniform(-3, 3)
            angle = 10 ** rng.uniform(-4, 1)
            h = y * math.sin(math.radians(angle))
            x = h * (1 + 10 ** rng.uniform(-6, 2))
            if x >= y:
                continue
            with self.subTest(a=x, b=y, A=angle):
                for t in solve({"a": x, "b": y, "A": angle}).solutions:
                    self.assertLessEqual(
                        _rel(t.c / math.sin(t.C), x / math.sin(t.A)), 1e-9
                    )

    def test_cli_near_flat_exits_0(self):
        rc, out, err, _ = _run(["-a", "1", "-b", "1", "-C", "179.999999", "--no-draw"])
        self.assertEqual((rc, err), (0, ""))
        self.assertRegex(out, r"\nc\s+2\.0000\s+derived")

    def test_bounded_near_flat_property(self):
        """Valid near-flat inputs solve, and every solution obeys the law of sines."""
        rng = random.Random(20261102)
        for _ in range(3000):
            d = 10 ** rng.uniform(-9, -2)
            x = round(rng.uniform(1, 20), 1)
            y = round(rng.uniform(1, 20), 1)
            cases = (
                {"a": x, "b": y, "C": 180 - d},
                {"a": x, "b": y, "C": d},
                {"a": x, "A": 180 - d, "B": d * rng.uniform(0.01, 0.99)},
                {"a": x + y, "b": y, "A": 180 - d},
            )
            for values in cases:
                with self.subTest(values=values):
                    t = solve(values).solutions[0]
                    # The sine of an angle near 180 degrees carries the
                    # rounding of pi, so check only the two smaller angles.
                    (p, small), (q, other), (r, _) = sorted(
                        ((t.a, t.A), (t.b, t.B), (t.c, t.C)), key=lambda e: e[1]
                    )
                    k = p / math.sin(small)
                    self.assertLessEqual(_rel(q / math.sin(other), k), 1e-9)
                    self.assertLessEqual(
                        _rel(t.area, 0.5 * q * r * math.sin(small)), 1e-9
                    )


class TestFloatRange(unittest.TestCase):
    """Sides far from 1 must not overflow or underflow the intermediate products."""

    def test_huge_sides_keep_exact_angles(self):
        t = solve({"a": 1e154, "b": 1e154, "c": 1e154}).solutions[0]
        for angle in (t.A, t.B, t.C):
            self.assertLessEqual(_rel(angle, math.pi / 3), 1e-15)
        self.assertLessEqual(_rel(t.area, math.sqrt(3) / 4 * 1e308), 1e-15)

    def test_tiny_sides_keep_exact_angles(self):
        t = solve({"a": 1e-150, "b": 1e-150, "c": 1e-150}).solutions[0]
        for angle in (t.A, t.B, t.C):
            self.assertLessEqual(_rel(angle, math.pi / 3), 1e-15)
        self.assertLessEqual(_rel(t.area, math.sqrt(3) / 4 * 1e-300), 1e-15)

    def test_area_too_large_is_an_input_error(self):
        with self.assertRaises(TriangleInputError) as cm:
            solve({"a": 1e200, "b": 1e200, "c": 1e200})
        self.assertIn("floating-point range", str(cm.exception))

    def test_area_too_small_is_an_input_error(self):
        with self.assertRaises(TriangleInputError) as cm:
            solve({"a": 1e-200, "b": 1e-200, "c": 1e-200})
        self.assertIn("floating-point range", str(cm.exception))

    def test_subnormal_area_is_an_input_error(self):
        # 1e-160 sides give an area near 4e-321: subnormal, so imprecise.
        with self.assertRaises(TriangleInputError) as cm:
            solve({"a": 1e-160, "b": 1e-160, "c": 1e-160})
        self.assertIn("too small", str(cm.exception))

    def test_perimeter_overflow_is_an_input_error(self):
        # Every side is finite, the sum is not.
        with self.assertRaises(TriangleInputError):
            solve({"a": 1e308, "b": 1e308, "A": 60})

    def test_side_overflow_from_law_of_sines_is_an_input_error(self):
        with self.assertRaises(TriangleInputError):
            solve({"c": 1e308, "A": 89.9999, "B": 89.9999})

    def test_side_ratio_beyond_a_double_is_an_input_error(self):
        cases: list[dict[str, float]] = [
            {"a": 1e300, "b": 1e-300, "C": 90},
            {"a": 1e170, "b": 1e-170, "C": 60},
            {"a": 1e300, "b": 1e-300, "A": 90},
            {"a": 1e160, "b": 1e-160, "C": 90},
        ]
        for values in cases:
            with (
                self.subTest(values=values),
                self.assertRaises(TriangleInputError) as cm,
            ):
                solve(values)
            self.assertIn("differ by more than", str(cm.exception))

    def test_wide_but_representable_side_ratio_solves(self):
        t = solve({"a": 1, "b": 1e-300, "C": 90}).solutions[0]
        self.assertEqual(t.b, 1e-300)
        self.assertLessEqual(_rel(t.area, 5e-301), 1e-15)

    def test_largest_double_does_not_crash_the_cli(self):
        rc, out, err, _ = _run(["-a", "1.7e308", "-b", "1.7e308", "-c", "1.7e308"])
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("floating-point range", err)


class TestSAS(unittest.TestCase):
    def test_acute_included_angle(self):
        t = solve({"a": 3, "b": 4, "C": 90}).solutions[0]
        self.assertAlmostEqual(t.c, 5.0, places=14)
        self.assertAlmostEqual(math.degrees(t.A), 36.86989764584402, places=10)
        self.assertAlmostEqual(t.area, 6.0, places=13)

    def test_obtuse_included_angle_uses_cosines_not_sines(self):
        # law of cosines: c^2 = 9 + 16 + 12 = 37; the law of sines on A would
        # return the acute supplement of an obtuse angle.
        t = solve({"a": 3, "b": 4, "C": 120}).solutions[0]
        self.assertAlmostEqual(t.c, math.sqrt(37), places=14)
        self.assertAlmostEqual(math.degrees(t.C), 120.0, places=12)
        self.assertLess(t.A, math.pi / 2)
        self.assertAlmostEqual(t.A + t.B + t.C, math.pi, places=14)

    def test_included_angle_other_sides(self):
        t = solve({"a": 3, "c": 4, "B": 90}).solutions[0]
        self.assertAlmostEqual(t.b, 5.0, places=14)
        t = solve({"b": 3, "c": 4, "A": 90}).solutions[0]
        self.assertAlmostEqual(t.a, 5.0, places=14)

    def test_tiny_included_angle_third_side_stable(self):
        t = solve({"a": 1, "b": 1, "C": 1e-9}).solutions[0]
        self.assertLessEqual(_rel(t.c, 1e-9 * math.pi / 180), 1e-12)


class TestASA_AAS(unittest.TestCase):
    def test_asa(self):
        t = solve({"c": 5, "A": 36.86989764584402, "B": 53.13010235415598}).solutions[0]
        self.assertAlmostEqual(t.a, 3.0, places=12)
        self.assertAlmostEqual(t.b, 4.0, places=12)
        self.assertAlmostEqual(t.C, math.pi / 2, places=12)

    def test_aas_side_opposite_typed_angle(self):
        t = solve({"a": 3, "A": 36.86989764584402, "C": 90}).solutions[0]
        self.assertAlmostEqual(t.b, 4.0, places=12)
        self.assertAlmostEqual(t.c, 5.0, places=12)
        self.assertAlmostEqual(math.degrees(t.B), 53.13010235415598, places=10)

    def test_third_angle_derived_from_two(self):
        t = solve({"b": 2, "A": 50, "B": 60}).solutions[0]
        self.assertAlmostEqual(math.degrees(t.C), 70.0, places=12)

    def test_angle_sum_is_pi(self):
        t = solve({"a": 2, "B": 40, "C": 100}).solutions[0]
        self.assertAlmostEqual(t.A + t.B + t.C, math.pi, places=14)

    def test_radians(self):
        t = solve(
            {"c": 5, "A": 0.6435011087932844, "B": 0.9272952180016122}, radians=True
        ).solutions[0]
        self.assertAlmostEqual(t.a, 3.0, places=12)
        self.assertAlmostEqual(t.C, math.pi / 2, places=12)

    def test_degrees_and_radians_agree(self):
        d = solve({"a": 3, "b": 4, "C": 90}).solutions[0]
        r = solve({"a": 3, "b": 4, "C": math.pi / 2}, radians=True).solutions[0]
        self.assertAlmostEqual(d.c, r.c, places=13)
        self.assertAlmostEqual(d.A, r.A, places=13)


class TestExtras(unittest.TestCase):
    def test_sss_with_extra_angle(self):
        s = solve({"a": 3, "b": 4, "c": 5, "B": 53.13})
        self.assertEqual(len(s.solutions), 1)
        self.assertEqual(len(s.extras), 1)
        e = s.extras[0]
        self.assertEqual(e.name, "B")
        self.assertEqual(e.given, 53.13)
        self.assertAlmostEqual(e.solved, 53.13010235415598, places=10)
        self.assertAlmostEqual(e.solved - e.given, 0.000102354, places=9)

    def test_sss_with_wrong_extra_angle(self):
        e = solve({"a": 3, "b": 4, "c": 5, "A": 37}).extras[0]
        self.assertEqual(e.name, "A")
        self.assertAlmostEqual(e.solved, 36.86989764584402, places=10)
        self.assertNotEqual(e.solved, e.given)

    def test_aas_from_a_A_B_reports_b(self):
        # a, b, A, B: no typed included angle, so AAS from a, A, B; b is extra.
        s = solve({"a": 3, "b": 4, "A": 36.86989764584402, "B": 53.13010235415598})
        t = s.solutions[0]
        self.assertAlmostEqual(t.a, 3.0, places=12)
        self.assertEqual([e.name for e in s.extras], ["b"])
        self.assertEqual(s.extras[0].given, 4)
        self.assertAlmostEqual(s.extras[0].solved, 4.0, places=12)

    def test_sas_from_a_b_C_reports_A_and_B(self):
        s = solve({"a": 3, "b": 4, "A": 36, "B": 54, "C": 90})
        self.assertEqual([e.name for e in s.extras], ["A", "B"])
        self.assertEqual([e.given for e in s.extras], [36, 54])
        self.assertAlmostEqual(s.extras[0].solved, 36.86989764584402, places=10)
        self.assertAlmostEqual(s.extras[1].solved, 53.13010235415598, places=10)
        self.assertAlmostEqual(s.solutions[0].c, 5.0, places=13)

    def test_three_typed_angles_third_is_extra(self):
        s = solve({"c": 1, "A": 60.1, "B": 60, "C": 60})
        self.assertEqual([e.name for e in s.extras], ["C"])
        self.assertEqual(s.extras[0].given, 60)
        self.assertAlmostEqual(s.extras[0].solved, 59.9, places=10)
        # the typed values A and B stay as typed
        self.assertAlmostEqual(math.degrees(s.solutions[0].A), 60.1, places=12)

    def test_extras_in_radians_are_in_radians(self):
        e = solve({"a": 3, "b": 4, "c": 5, "C": 1.5}, radians=True).extras[0]
        self.assertEqual(e.given, 1.5)
        self.assertAlmostEqual(e.solved, math.pi / 2, places=14)

    def test_no_extras_for_exactly_three_values(self):
        self.assertEqual(solve({"a": 3, "b": 4, "C": 90}).extras, [])


class TestSSA(unittest.TestCase):
    def test_two_solutions(self):
        s = solve({"a": 6, "b": 8, "A": 30})
        self.assertEqual(len(s.solutions), 2)
        bs = sorted(math.degrees(t.B) for t in s.solutions)
        self.assertAlmostEqual(bs[0], 41.8103148957786, places=9)
        self.assertAlmostEqual(bs[1], 138.1896851042214, places=9)
        for t in s.solutions:
            self.assertAlmostEqual(math.degrees(t.A), 30.0, places=12)
            self.assertAlmostEqual(t.a, 6.0, places=14)
            self.assertAlmostEqual(t.b, 8.0, places=14)
            self.assertAlmostEqual(t.A + t.B + t.C, math.pi, places=14)

    def test_first_solution_has_longer_third_side(self):
        s = solve({"a": 6, "b": 8, "A": 30})
        self.assertGreater(s.solutions[0].c, s.solutions[1].c)

    def test_third_side_label_follows_the_unknown(self):
        s = solve({"b": 6, "c": 8, "B": 30})
        self.assertEqual(len(s.solutions), 2)
        self.assertAlmostEqual(
            math.degrees(s.solutions[0].C), 41.8103148957786, places=9
        )
        self.assertAlmostEqual(s.solutions[0].b, 6.0, places=14)

    def test_zero_solutions_below_height(self):
        with self.assertRaises(NoTriangle) as cm:
            solve({"a": 3, "b": 8, "A": 30})
        self.assertEqual(
            str(cm.exception),
            "no triangle: side a is shorter than the height 4",
        )

    def test_right_angle_one_solution(self):
        s = solve({"a": 4, "b": 8, "A": 30})
        self.assertEqual(len(s.solutions), 1)
        t = s.solutions[0]
        self.assertAlmostEqual(math.degrees(t.B), 90.0, places=9)
        self.assertAlmostEqual(t.c, math.sqrt(48), places=12)

    def test_x_at_least_y_one_solution(self):
        for a in (8, 9, 100):
            self.assertEqual(len(solve({"a": a, "b": 8, "A": 30}).solutions), 1)

    def test_x_equal_y_is_isosceles(self):
        t = solve({"a": 8, "b": 8, "A": 30}).solutions[0]
        self.assertAlmostEqual(t.B, t.A, places=14)
        self.assertAlmostEqual(math.degrees(t.C), 120.0, places=12)

    def test_obtuse_known_angle(self):
        for a, b, a_ang in ((7, 8, 120), (8, 8, 120), (8, 8, 90)):
            with self.assertRaises(NoTriangle) as cm:
                solve({"a": a, "b": b, "A": a_ang})
            self.assertEqual(
                str(cm.exception),
                "no triangle: side a must be longer than b opposite an angle of 90 degrees or more",
            )
        s = solve({"a": 9, "b": 8, "A": 120})
        self.assertEqual(len(s.solutions), 1)
        self.assertAlmostEqual(math.degrees(s.solutions[0].A), 120.0, places=12)

    def test_boundary_just_inside_two_solutions(self):
        s = solve({"a": 7.9999999999, "b": 8, "A": 0.001})
        self.assertEqual(len(s.solutions), 2)
        self.assertLessEqual(_rel(s.solutions[0].c, 15.999999997463060633), 1e-12)
        self.assertLessEqual(_rel(s.solutions[1].c, 1.0000000828926797216e-10), 1e-12)
        for t in s.solutions:
            self.assertGreater(min(t.A, t.B, t.C), 0)

    def test_boundary_large_scale(self):
        s = solve({"a": 7.9999999999e12, "b": 8e12, "A": 0.001})
        self.assertEqual(len(s.solutions), 2)
        self.assertLessEqual(_rel(s.solutions[1].c, 100.00000001523087099), 1e-12)

    def test_tangency_band_catches_h_just_above_x(self):
        # Computed h lands 1-4 ulps above x: inside the band, so tangent.
        x = math.nextafter(math.nextafter(2 * math.sin(math.radians(15)), 0), 0)
        s = solve({"a": x, "b": 2, "A": 15})
        self.assertEqual(len(s.solutions), 1)
        self.assertAlmostEqual(math.degrees(s.solutions[0].B), 90.0, places=12)

    def test_tangency_band_upper_edge(self):
        # 8 ulps above the tangent is outside the 4-ulp band: two solutions.
        x = 8 * math.sin(math.radians(30)) * (1 + 8 * sys.float_info.epsilon)
        s = solve({"a": x, "b": 8, "A": 30})
        self.assertEqual(len(s.solutions), 2)

    def test_boundary_near_tangency_two_distinct(self):
        x = 4 * (1 + 5e-10)
        s = solve({"a": x, "b": 8, "A": 30})
        self.assertEqual(len(s.solutions), 2)
        self.assertLessEqual(_rel(s.solutions[0].c, 6.9283297213997446101), 1e-12)
        self.assertLessEqual(_rel(s.solutions[1].c, 6.9280767391512741975), 1e-12)
        self.assertNotEqual(s.solutions[0].c, s.solutions[1].c)

    def test_property_every_ssa_solution_is_valid(self):
        cases = [
            (6, 8, 30),
            (4, 8, 30),
            (9, 8, 120),
            (8, 8, 60),
            (7.9999999999, 8, 0.001),
            (7.9999999999e12, 8e12, 0.001),
            (4 * (1 + 5e-10), 8, 30),
            (6.499999, 6.5, 89.9),
            (1, 1.0000001, 45),
            (8.0000000001, 8, 120),
        ]
        for x, y, ang in cases:
            with self.subTest(x=x, y=y, ang=ang):
                s = solve({"a": x, "b": y, "A": ang})
                self.assertGreater(len(s.solutions), 0)
                for t in s.solutions:
                    for v in (t.a, t.b, t.c, t.A, t.B, t.C, t.area, t.perimeter):
                        self.assertGreater(v, 0)
                    self.assertAlmostEqual(
                        t.A + t.B + t.C, math.pi, delta=1e-12 * math.pi
                    )

    def test_ssa_in_radians(self):
        s = solve({"a": 6, "b": 8, "A": math.radians(30)}, radians=True)
        self.assertEqual(len(s.solutions), 2)

    def test_obtuse_x_near_y_third_side_stable(self):
        # y*cos(X) cancels against the root when x is near y; reference is
        # mpmath at 60 digits from the double inputs.
        t = solve({"a": 8.0000000001, "b": 8, "A": 120}).solutions[0]
        self.assertLessEqual(_rel(t.c, 2.0000001654432427876e-10), 1e-6)


class TestInputErrors(unittest.TestCase):
    def _msg(self, values, **kw):
        with self.assertRaises(TriangleInputError) as cm:
            solve(values, **kw)
        return str(cm.exception)

    def test_is_value_error(self):
        self.assertTrue(issubclass(TriangleInputError, ValueError))
        self.assertTrue(issubclass(NoTriangle, ValueError))
        self.assertFalse(issubclass(NoTriangle, TriangleInputError))

    def test_fewer_than_three_values(self):
        for vals in ({}, {"a": 3}, {"a": 3, "b": 4}):
            self.assertEqual(self._msg(vals), "need at least three values")

    def test_aaa_consistent_and_inconsistent(self):
        for vals in (
            {"A": 60, "B": 60, "C": 60},
            {"A": 50, "B": 50, "C": 50},
            {"A": 100, "B": 100, "C": 100},
        ):
            self.assertEqual(self._msg(vals), "need at least one side")

    def test_non_positive_and_non_finite(self):
        for bad in (0, -1, float("nan"), float("inf"), float("-inf")):
            self.assertEqual(
                self._msg({"a": bad, "b": 4, "c": 5}),
                "a must be a positive finite number",
            )
            self.assertEqual(
                self._msg({"a": 3, "b": 4, "C": bad}),
                "C must be a positive finite number",
            )

    def test_angle_180_or_more(self):
        self.assertEqual(
            self._msg({"a": 3, "b": 4, "C": 180}),
            "angle C must be less than 180 degrees",
        )
        self.assertEqual(
            self._msg({"a": 3, "b": 4, "C": 200}),
            "angle C must be less than 180 degrees",
        )
        self.assertEqual(
            self._msg({"a": 3, "b": 4, "C": math.pi}, radians=True),
            "angle C must be less than pi radians",
        )

    def test_angle_just_below_180_accepted(self):
        s = solve({"a": 3, "b": 4, "C": 179.9})
        self.assertGreater(s.solutions[0].c, 0)

    def test_two_angles_sum_180_or_more(self):
        self.assertEqual(
            self._msg({"a": 3, "A": 90, "B": 90}),
            "angles A and B must sum to less than 180 degrees",
        )
        self.assertEqual(
            self._msg({"a": 3, "A": 100, "C": 90}),
            "angles A and C must sum to less than 180 degrees",
        )
        self.assertEqual(
            self._msg({"a": 3, "B": 2, "C": 2}, radians=True),
            "angles B and C must sum to less than pi radians",
        )

    def test_pair_sum_checked_with_extra_angles(self):
        self.assertEqual(
            self._msg({"a": 3, "b": 4, "A": 100, "B": 90}),
            "angles A and B must sum to less than 180 degrees",
        )

    def test_unknown_name(self):
        self.assertEqual(self._msg({"a": 3, "b": 4, "x": 5}), "unknown value x")


class TestPostCheck(unittest.TestCase):
    def test_check_rejects_bad_triangles(self):
        good = solve({"a": 3, "b": 4, "c": 5}).solutions[0]
        _check(good)
        for bad in (
            replace(good, a=0.0),
            replace(good, C=-1.0),
            replace(good, b=float("nan")),
            replace(good, a=math.inf),
            replace(good, A=good.A + 1e-6),
        ):
            with self.assertRaises(RuntimeError):
                _check(bad)

    def test_solve_runs_the_post_check(self):
        good = solve({"a": 3, "b": 4, "c": 5}).solutions[0]
        bad = replace(good, A=good.A + 1e-6)
        result = ([bad], {"a", "b", "c"})
        with (
            mock.patch("triangle._solve_determined", return_value=result),
            self.assertRaises(RuntimeError),
        ):
            solve({"a": 3, "b": 4, "c": 5})

    def test_angle_sum_tolerance_accepts_rounding(self):
        good = solve({"a": 3, "b": 4, "c": 5}).solutions[0]
        _check(replace(good, A=good.A + 9e-16))


class TestAreaPerimeter(unittest.TestCase):
    def test_known_values(self):
        for sides, area, per in (
            ((3, 4, 5), 6.0, 12.0),
            ((5, 12, 13), 30.0, 30.0),
            ((13, 14, 15), 84.0, 42.0),
        ):
            t = solve(dict(zip("abc", sides, strict=True))).solutions[0]
            self.assertAlmostEqual(t.area, area, places=12)
            self.assertEqual(t.perimeter, per)

    def test_area_from_sas(self):
        t = solve({"a": 6, "b": 7, "C": 30}).solutions[0]
        self.assertAlmostEqual(t.area, 0.5 * 6 * 7 * 0.5, places=12)


_BLANK = "\u2800"


def _midpoint_column_has_dots(
    out: list[str], p: tuple[int, int], q: tuple[int, int]
) -> bool:
    """True if a dot is set in the edge's midpoint column, in a row it spans.

    The exact midpoint can sit on a cell boundary of a near-flat edge, so
    both rows the edge covers at that column are accepted.
    """
    col = (p[0] + q[0]) // 4
    rows = range(min(p[1], q[1]) // 4, max(p[1], q[1]) // 4 + 1)
    return any(out[r][col] not in (_BLANK, "A", "B", "C") for r in rows)


class TestRender(unittest.TestCase):
    def _t345(self) -> Triangle:
        return solve({"a": 3, "b": 4, "c": 5}).solutions[0]

    def test_3_4_5_exact_drawing(self):
        self.assertEqual(render(self._t345(), 20, 10), EXPECTED_345)

    def test_label_uses_the_cell_aspect(self):
        # Vertex A of 6-6-3 has |dy|/4 <= |dx|/2 < |dy|/2 from the centroid.
        out = render(solve({"a": 6, "b": 6, "c": 3}).solutions[0], 20, 10)
        self.assertEqual(out[8][4], "A")

    def test_every_line_has_width_and_height_rows(self):
        for w, h in ((20, 10), (6, 3), (40, 5), (7, 20)):
            out = render(self._t345(), w, h)
            self.assertEqual(len(out), h)
            for line in out:
                self.assertEqual(len(line), w)

    def test_labels_in_expected_cells(self):
        out = render(self._t345(), 20, 10)
        for label, (row, col) in EXPECTED_LABELS.items():
            self.assertEqual(out[row][col], label)
        self.assertEqual(sum(ch in "ABC" for line in out for ch in line), 3)

    def test_label_cells_are_next_to_their_vertices(self):
        t = self._t345()
        pts = _project(t, 20, 10)
        out = render(t, 20, 10)
        for label, (px, py) in zip("ABC", pts, strict=True):
            row, col = next(
                (r, line.index(label)) for r, line in enumerate(out) if label in line
            )
            self.assertLessEqual(abs(col - px // 2) + abs(row - py // 4), 1)

    def test_right_angle_at_c_long_side_at_bottom(self):
        out = render(self._t345(), 20, 10)
        a_row = next(r for r, line in enumerate(out) if "A" in line)
        b_row = next(r for r, line in enumerate(out) if "B" in line)
        c_row = next(r for r, line in enumerate(out) if "C" in line)
        self.assertEqual(a_row, b_row)
        self.assertLess(c_row, a_row)

    def test_needle_has_dots_along_every_edge(self):
        t = solve({"a": 1, "b": 1, "c": 1.9999999}).solutions[0]
        out = render(t, 40, 10)
        pts = _project(t, 40, 10)
        for i in range(3):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % 3]
            self.assertTrue(_midpoint_column_has_dots(out, (x0, y0), (x1, y1)))

    def test_too_small_canvas_raises(self):
        t = self._t345()
        for w, h in ((0, 0), (0, 10), (20, 0), (5, 3), (6, 2), (-1, 10)):
            with self.assertRaises(ValueError):
                render(t, w, h)

    def test_minimum_canvas_renders(self):
        out = render(self._t345(), 6, 3)
        self.assertEqual([len(line) for line in out], [6, 6, 6])

    def test_pure_and_repeatable(self):
        t = self._t345()
        self.assertEqual(render(t, 20, 10), render(t, 20, 10))

    def test_only_braille_and_labels(self):
        for line in render(self._t345(), 20, 10):
            for ch in line:
                self.assertTrue("\u2800" <= ch <= "\u28ff" or ch in "ABC")


EXPECTED_345: list[str] = [
    "\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800",
    "\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800C\u2800\u2800\u2800\u2800\u2800\u2800\u2800",
    "\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2840\u2800\u2800\u2800\u2800\u2800\u2800\u2800",
    "\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2880\u2814\u280a\u2808\u2886\u2800\u2800\u2800\u2800\u2800\u2800",
    "\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2860\u280a\u2801\u2800\u2800\u2800\u2800\u2831\u2840\u2800\u2800\u2800\u2800",
    "\u2800\u2800\u2800\u2800\u28c0\u2814\u2809\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2808\u2886\u2800\u2800\u2800",
    "\u2800\u2880\u2824\u280a\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2831\u2840\u2800",
    "A\u2809\u2809\u2809\u2809\u2809\u2809\u2809\u2809\u2809\u2809\u2809\u2809\u2809\u2809\u2809\u2809\u2809\u2809B",
    "\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800",
    "\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800\u2800",
]
EXPECTED_LABELS: dict[str, tuple[int, int]] = {"A": (7, 0), "B": (7, 19), "C": (1, 12)}


_BRAILLE = re.compile("[\u2800-\u28ff]")


def _run(argv, stdin_tty=False, stdout_tty=False, answers=()):
    out, err = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
        mock.patch("sys.stdin.isatty", return_value=stdin_tty),
        mock.patch("sys.stdout.isatty", return_value=stdout_tty),
        mock.patch("builtins.input", side_effect=list(answers)) as fake_input,
    ):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue(), fake_input


class TestCLI(unittest.TestCase):
    def test_contract_constants(self):
        rc, out, _, _ = _run(CONTRACT_ARGS)
        self.assertEqual(rc, 0)
        self.assertIn(CONTRACT_EXPECT, out)

    def test_table_marks_given_and_derived(self):
        rc, out, _, _ = _run(["-a", "3", "-b", "4", "-c", "5", "--no-draw"])
        self.assertEqual(rc, 0)
        lines = {ln.split()[0]: ln for ln in out.splitlines() if ln.split()}
        self.assertTrue(lines["a"].endswith("given"))
        self.assertTrue(lines["A"].endswith("derived"))
        self.assertIn("36.8699", lines["A"])
        self.assertIn("6.0000", lines["area"])
        self.assertIn("12.0000", lines["perimeter"])

    def test_no_draw_prints_no_braille(self):
        _, out, _, _ = _run(["-a", "3", "-b", "4", "-c", "5", "--no-draw"])
        self.assertIsNone(_BRAILLE.search(out))

    def test_draw_prints_braille(self):
        _, out, _, _ = _run(["-a", "3", "-b", "4", "-c", "5"])
        self.assertIsNotNone(_BRAILLE.search(out))

    def test_precision(self):
        _, out, _, _ = _run(
            ["-a", "3", "-b", "4", "-c", "5", "--no-draw", "--precision", "2"]
        )
        self.assertIn("6.00", out)
        self.assertNotIn("6.0000", out)
        self.assertRegex(out, r"perimeter\s+12\.00\n")
        self.assertRegex(out, r"\nc\s+5\.00\s+given")
        _, out0, _, _ = _run(
            ["-a", "3", "-b", "4", "-c", "5", "--no-draw", "--precision", "0"]
        )
        self.assertRegex(out0, r"area\s+6\n")
        self.assertRegex(out0, r"perimeter\s+12\n")

    def test_precision_rejects_negative_and_text(self):
        for bad in ("-1", "x"):
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as cm,
            ):
                main(["-a", "3", "-b", "4", "-c", "5", "--precision", bad])
            self.assertEqual(cm.exception.code, 2)

    def test_two_solutions_headed(self):
        rc, out, _, _ = _run(["-a", "6", "-b", "8", "-A", "30", "--no-draw"])
        self.assertEqual(rc, 0)
        self.assertLess(out.index("Solution 1"), out.index("Solution 2"))
        self.assertEqual(out.count("Solution"), 2)

    def test_two_solutions_each_drawn(self):
        _, out, _, _ = _run(["-a", "6", "-b", "8", "-A", "30"])
        self.assertEqual(out.count("Solution"), 2)
        first, second = out.split("Solution 2")
        self.assertIsNotNone(_BRAILLE.search(first))
        self.assertIsNotNone(_BRAILLE.search(second))

    def test_single_solution_has_no_heading(self):
        _, out, _, _ = _run(["-a", "3", "-b", "4", "-c", "5", "--no-draw"])
        self.assertNotIn("Solution", out)

    def test_extra_line_exact(self):
        rc, out, _, _ = _run(
            ["-a", "3", "-b", "4", "-c", "5", "-B", "53.13", "--no-draw"]
        )
        self.assertEqual(rc, 0)
        self.assertIn("extra B given 53.13 solved 53.130102 diff +0.000102354\n", out)

    def test_radians_output(self):
        rc, out, _, _ = _run(
            ["-a", "3", "-b", "4", "-c", "5", "--radians", "--no-draw"]
        )
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"C\s+1\.5708\s+derived")
        rc, out, _, _ = _run(
            ["-a", "3", "-b", "4", "-C", "1.5707963267948966", "--radians", "--no-draw"]
        )
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"c\s+5\.0000\s+derived")

    def test_smoke(self):
        rc, out, _, _ = _run(["--smoke"])
        self.assertEqual(rc, 0)
        self.assertIn("6.0000", out)
        self.assertIsNotNone(_BRAILLE.search(out))

    def test_input_error_exits_2(self):
        rc, out, err, _ = _run(["-a", "3", "-b", "4"])
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertTrue(err.strip())

    def test_no_triangle_exits_1(self):
        rc, out, err, _ = _run(["-a", "1", "-b", "2", "-c", "9"])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertTrue(err.strip())

    def test_bare_run_without_tty_prints_usage(self):
        rc, out, err, fake_input = _run([])
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("usage", err.lower())
        fake_input.assert_not_called()

    def test_bare_run_with_flags_only_still_bare(self):
        rc, _, err, _ = _run(["--no-draw"])
        self.assertEqual(rc, 2)
        self.assertIn("usage", err.lower())

    def test_prompts_with_empty_and_bad_answers(self):
        answers = ["3", "4", "5", "", "", ""]
        rc, out, err, fake_input = _run(
            [],
            stdin_tty=True,
            answers=answers,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")
        self.assertIn("6.0000", out)
        prompts = [c.args[0] for c in fake_input.call_args_list]
        self.assertEqual(len(prompts), 6)
        for prompt in prompts:
            self.assertTrue(prompt.endswith(": "))
            self.assertNotIn("?", prompt)

    def test_bad_answers_reprompt_with_reason(self):
        answers = ["x", "nan", "-2", "0", "3", "4", "5", "", "", ""]
        rc, out, err, fake_input = _run(["--no-draw"], stdin_tty=True, answers=answers)
        self.assertEqual(rc, 0)
        self.assertEqual(fake_input.call_count, 10)
        reasons = err.splitlines()
        self.assertEqual(len(reasons), 4)
        self.assertIn("not a number", reasons[0])
        self.assertIn("not finite", reasons[1])
        self.assertIn("greater than zero", reasons[2])
        self.assertIn("greater than zero", reasons[3])
        self.assertIn("6.0000", out)

    def test_prompt_eof_exits_2(self):
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch("builtins.input", side_effect=EOFError),
        ):
            rc = main([])
        self.assertEqual(rc, 2)
        self.assertTrue(err.getvalue().strip())

    def test_prompt_fewer_than_three_exits_2(self):
        rc, _, err, _ = _run([], stdin_tty=True, answers=["3", "4", "", "", "", ""])
        self.assertEqual(rc, 2)
        self.assertTrue(err.strip())

    def test_canvas_uses_terminal_size(self):
        size = mock.Mock(columns=30, lines=10)
        with mock.patch("shutil.get_terminal_size", return_value=size):
            _, out, _, _ = _run(["-a", "3", "-b", "4", "-c", "5"], stdout_tty=True)
        drawing = [ln for ln in out.splitlines() if _BRAILLE.search(ln)]
        self.assertEqual(len(drawing), 10)
        self.assertEqual({len(ln) for ln in drawing}, {30})

    def test_canvas_floored_at_render_minimum(self):
        size = mock.Mock(columns=2, lines=1)
        with mock.patch("shutil.get_terminal_size", return_value=size):
            rc, out, _, _ = _run(["-a", "3", "-b", "4", "-c", "5"], stdout_tty=True)
        self.assertEqual(rc, 0)
        drawing = [ln for ln in out.splitlines() if _BRAILLE.search(ln)]
        self.assertEqual((len(drawing), len(drawing[0])), (3, 6))

    def test_canvas_rows_capped_at_20(self):
        size = mock.Mock(columns=80, lines=50)
        with mock.patch("shutil.get_terminal_size", return_value=size):
            _, out, _, _ = _run(["-a", "3", "-b", "4", "-c", "5"], stdout_tty=True)
        drawing = [ln for ln in out.splitlines() if _BRAILLE.search(ln)]
        self.assertEqual(len(drawing), 20)

    def test_canvas_piped_is_60_by_20(self):
        _, out, _, _ = _run(["-a", "3", "-b", "4", "-c", "5"])
        drawing = [ln for ln in out.splitlines() if _BRAILLE.search(ln)]
        self.assertEqual((len(drawing), {len(ln) for ln in drawing}), (20, {60}))


class TestSubprocess(unittest.TestCase):
    def test_runs_as_program(self):
        script = pathlib.Path(__file__).with_name("triangle.py")
        done = subprocess.run(
            [sys.executable, str(script), "-a", "3", "-b", "4", "-c", "5"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
        self.assertEqual(done.returncode, 0)
        self.assertIn("6.0000", done.stdout)


if __name__ == "__main__":
    unittest.main()
