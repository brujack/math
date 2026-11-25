"""Tests for the zeta results page: fixtures, parsing, computations and rendering."""

import ast
import contextlib
import dataclasses
import html
import importlib.util
import io
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from functools import partial
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import zeta_results as zr

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "zeta_results"
REFINED_TABLE = FIXTURES / "tr3" / "zeta_1e3.txt"
EXPECTED_DATA_LINES = 649


def _clean_git_env() -> dict[str, str]:
    """Environment with the GIT_* variables a hook or worktree exports removed."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


class TestFixtures(unittest.TestCase):
    def test_refined_table_is_tracked_by_git(self) -> None:
        rel = REFINED_TABLE.relative_to(REPO_ROOT).as_posix()
        result = subprocess.run(
            ["git", "ls-files", rel],
            cwd=REPO_ROOT,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), rel)

    def test_refined_table_header_and_row_count(self) -> None:
        lines = REFINED_TABLE.read_text().splitlines()
        self.assertEqual(lines[0], "# n a b t_n w_n")
        self.assertEqual(len(lines) - 1, EXPECTED_DATA_LINES)

    def test_every_run_fixture_has_out_and_err(self) -> None:
        for run_id in ("t2", "t3", "tr3"):
            for name in ("out.txt", "err.txt"):
                self.assertTrue(
                    (FIXTURES / run_id / name).is_file(), f"{run_id}/{name}"
                )


class _FixtureCopy(unittest.TestCase):
    """Base: a private copy of the fixtures that a test may edit freely."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "fx"
        shutil.copytree(FIXTURES, self.root)

    def edit(self, rel: str, old: str, new: str) -> Path:
        path = self.root / rel
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1))
        return path

    def text(self, rel: str) -> str:
        return (self.root / rel).read_text()

    def err(self, run: str = "tr3") -> str:
        return self.text(f"{run}/err.txt")

    def out(self, run: str = "tr3") -> str:
        return self.text(f"{run}/out.txt")


class TestParsing(_FixtureCopy):
    """Parsers for time reports, out.txt, runs.toml and refined tables."""

    def test_elapsed_minutes_seconds(self) -> None:
        self.assertEqual(zr.parse_elapsed("0:02.45"), 2.45)

    def test_elapsed_hours_minutes_seconds(self) -> None:
        self.assertEqual(zr.parse_elapsed("1:02:23"), 3743)

    def test_elapsed_zero(self) -> None:
        self.assertEqual(zr.parse_elapsed("0:00.00"), 0)

    def test_elapsed_over_an_hour_in_minutes_form(self) -> None:
        self.assertEqual(zr.parse_elapsed("75:00.5"), 4500.5)

    def test_elapsed_rejects_garbage(self) -> None:
        for bad in ("", "12", "a:bc", "1:2:3:4", "1:02:23.5x", "-1:00"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                zr.parse_elapsed(bad)

    def test_time_refined_fixture(self) -> None:
        rep = zr.parse_time_report(self.err(), "tr3")
        self.assertEqual(rep.n, 3)
        self.assertTrue(rep.refine)
        self.assertEqual(rep.binary_hash, "f935b23")
        self.assertGreater(rep.elapsed_s, 0)
        self.assertGreater(rep.peak_rss_kb, 0)

    def test_time_plain_fixture(self) -> None:
        rep = zr.parse_time_report(self.err("t2"), "t2")
        self.assertEqual((rep.n, rep.refine), (2, False))
        self.assertEqual(rep.elapsed_s, 0.53)
        self.assertEqual(rep.peak_rss_kb, 9388)

    def test_time_hour_long_elapsed(self) -> None:
        text = self.err()
        lines = [
            "\tElapsed (wall clock) time (h:mm:ss or m:ss): 1:02:23"
            if "Elapsed (wall clock)" in ln
            else ln
            for ln in text.splitlines()
        ]
        rep = zr.parse_time_report("\n".join(lines), "tr3")
        self.assertEqual(rep.elapsed_s, 3743)

    def test_time_signal_killed_with_exit_status_zero(self) -> None:
        bad = self.err().replace(
            "\tExit status: 0", "\tCommand terminated by signal 9\n\tExit status: 0"
        )
        self.assertIn("signal 9", bad)
        with self.assertRaisesRegex(
            zr.ResultsError, "^tr3: command terminated by signal 9"
        ):
            zr.parse_time_report(bad, "tr3")

    def test_time_nonzero_exit_status(self) -> None:
        bad = self.err().replace("Exit status: 0", "Exit status: 1")
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            zr.parse_time_report(bad, "tr3")

    def test_time_missing_field_each(self) -> None:
        for key in (
            "Command being timed",
            "Elapsed (wall clock)",
            "Maximum resident set size",
            "Exit status",
        ):
            kept = [ln for ln in self.err().splitlines() if key not in ln]
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(zr.ResultsError, "^tr3: "),
            ):
                zr.parse_time_report("\n".join(kept), "tr3")

    def test_time_bad_command_args(self) -> None:
        for args in ("8", "1", "3 --other", "3 --refine extra", ""):
            bad = self.err().replace("zeta-f935b23 3 --refine", f"zeta-f935b23 {args}")
            with (
                self.subTest(args=args),
                self.assertRaisesRegex(zr.ResultsError, "^tr3: "),
            ):
                zr.parse_time_report(bad, "tr3")

    def test_time_bad_elapsed(self) -> None:
        bad = self.err().replace("0:0", "x:0", 1)
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            zr.parse_time_report(bad, "tr3")

    def test_time_binary_hash_matches_and_mismatches(self) -> None:
        runs = zr.load_runs_toml(self.root / "runs.toml")
        rep = zr.parse_time_report(self.err(), "tr3")
        zr.check_binary(runs["tr3"], rep, "tr3")
        other = zr.RunMeta("tr3", "0" * 40, "m", "2026-11-24", None)
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            zr.check_binary(other, rep, "tr3")

    def test_out_refined_fixture(self) -> None:
        s = zr.parse_out(self.out(), "tr3", 3, refine=True)
        self.assertEqual(s.count, 649)
        self.assertEqual(s.spacings, 648)
        self.assertEqual(
            s.cli_counts,
            (0, 7, 26, 58, 96, 92, 109, 80, 58, 57, 28, 19, 8, 9, 1, 0, 0, 0, 0, 0),
        )
        self.assertEqual(s.cli_ks, "0.0448")

    def test_out_plain_fixture(self) -> None:
        s = zr.parse_out(self.out("t2"), "t2", 2, refine=False)
        self.assertEqual(s.count, 29)
        self.assertIsNone(s.spacings)
        self.assertIsNone(s.cli_counts)
        self.assertIsNone(s.cli_ks)

    def test_out_no_verified_line(self) -> None:
        bad = "\n".join(
            ln for ln in self.out().splitlines() if not ln.startswith("RH verified")
        )
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            zr.parse_out(bad, "tr3", 3, refine=True)

    def test_out_wrong_bound_for_n(self) -> None:
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            zr.parse_out(self.out(), "tr3", 4, refine=True)

    def test_out_refined_without_histogram(self) -> None:
        with self.assertRaisesRegex(zr.ResultsError, "^t3: "):
            zr.parse_out(self.out("t3"), "t3", 3, refine=True)

    def test_out_refined_missing_histogram_row(self) -> None:
        bad = self.out().replace("  0.15-0.30        7    0.0720        0.1539\n", "")
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            zr.parse_out(bad, "tr3", 3, refine=True)

    def test_out_refined_missing_ks(self) -> None:
        bad = "\n".join(
            ln for ln in self.out().splitlines() if not ln.startswith("KS distance")
        )
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            zr.parse_out(bad, "tr3", 3, refine=True)

    def test_out_refined_missing_spacings(self) -> None:
        bad = self.out().replace(", 648 spacings", "")
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            zr.parse_out(bad, "tr3", 3, refine=True)

    def load(self) -> dict[str, zr.RunMeta]:
        return zr.load_runs_toml(self.root / "runs.toml")

    def test_toml_fixture(self) -> None:
        runs = self.load()
        self.assertEqual(list(runs), ["t2", "t3", "tr3"])
        self.assertEqual(runs["tr3"].binary_sha[:7], "f935b23")
        self.assertIsNone(runs["tr3"].note)

    def test_toml_note_is_optional_and_kept(self) -> None:
        path = self.root / "runs.toml"
        path.write_text(path.read_text() + 'note = "hello"\n')
        self.assertEqual(self.load()["tr3"].note, "hello")

    def test_toml_unknown_key(self) -> None:
        path = self.root / "runs.toml"
        path.write_text(path.read_text() + 'extra = "x"\n')
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            self.load()

    def test_toml_missing_key(self) -> None:
        self.edit("runs.toml", 'date = "2026-11-24"\n', "")
        with self.assertRaisesRegex(zr.ResultsError, "^t2: "):
            self.load()

    def test_toml_bad_sha(self) -> None:
        for bad in ("f935b23", "G" * 40, "F935B233046FA0905C3198EFC93A15FB2412677A"):
            path = self.root / "runs.toml"
            text = (FIXTURES / "runs.toml").read_text()
            path.write_text(
                text.replace("f935b233046fa0905c3198efc93a15fb2412677a", bad)
            )
            with (
                self.subTest(bad=bad),
                self.assertRaisesRegex(zr.ResultsError, "^t2: "),
            ):
                self.load()

    def test_toml_duplicate_id(self) -> None:
        self.edit("runs.toml", 'id = "t3"', 'id = "t2"')
        with self.assertRaisesRegex(zr.ResultsError, "^t2: "):
            self.load()

    def test_toml_non_string_value(self) -> None:
        self.edit("runs.toml", 'date = "2026-11-24"', "date = 2026-11-24")
        with self.assertRaisesRegex(zr.ResultsError, "^t2: "):
            self.load()

    def test_toml_empty_file_has_no_runs(self) -> None:
        (self.root / "runs.toml").write_text("")
        with self.assertRaisesRegex(zr.ResultsError, "^runs.toml: "):
            self.load()

    def test_toml_non_table_run_entry(self) -> None:
        (self.root / "runs.toml").write_text("run = [1]\n")
        with self.assertRaisesRegex(
            zr.ResultsError, r"^runs.toml: run\[0\] is not a table"
        ):
            self.load()

    def test_toml_empty_run_array(self) -> None:
        (self.root / "runs.toml").write_text("run = []\n")
        with self.assertRaisesRegex(zr.ResultsError, "^runs.toml: no "):
            self.load()

    def test_toml_unparseable_toml(self) -> None:
        (self.root / "runs.toml").write_text("[[run\n")
        with self.assertRaisesRegex(zr.ResultsError, "^runs.toml: "):
            self.load()

    def read(self, count: int = 649) -> zr.RefinedTable:
        return zr.read_refined(self.root / "tr3" / "zeta_1e3.txt", "tr3", count)

    def test_table_fixture(self) -> None:
        t = self.read()
        self.assertEqual((len(t.a), len(t.b), len(t.m)), (649, 649, 649))
        self.assertEqual(t.m[0], t.a[0] + (t.b[0] - t.a[0]) / 2)
        self.assertTrue(all(x < y for x, y in zip(t.m, t.m[1:], strict=False)))

    def test_table_plain_header_rejected(self) -> None:
        self.edit("tr3/zeta_1e3.txt", "# n a b t_n w_n", "# n t_n w_n")
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            self.read()

    def test_table_count_mismatch_both_ways(self) -> None:
        for count in (648, 650):
            with (
                self.subTest(count=count),
                self.assertRaisesRegex(zr.ResultsError, "^tr3: "),
            ):
                self.read(count)

    def test_table_missing_line(self) -> None:
        path = self.root / "tr3" / "zeta_1e3.txt"
        lines = path.read_text().splitlines()
        del lines[10]
        path.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            self.read()

    def _write_row(self, mutate: Callable[[list[str]], list[str]]) -> None:
        lines = (FIXTURES / "tr3" / "zeta_1e3.txt").read_text().splitlines()
        edited = [*lines[:5], " ".join(mutate(lines[5].split())), *lines[6:]]
        (self.root / "tr3" / "zeta_1e3.txt").write_text("\n".join(edited) + "\n")

    @staticmethod
    def _replace_field(fields: list[str], column: int, token: str) -> list[str]:
        return [*fields[:column], token, *fields[column + 1 :]]

    def test_table_non_finite_values(self) -> None:
        for column in (2, 4):
            for token in ("nan", "inf"):
                with self.subTest(column=column, token=token):
                    self._write_row(
                        partial(self._replace_field, column=column, token=token)
                    )
                    with self.assertRaisesRegex(zr.ResultsError, "^tr3: .*non-finite"):
                        self.read()

    def test_table_wrong_field_count(self) -> None:
        for mutate in (lambda f: f[:4], lambda f: [*f, "1"]):
            with self.subTest():
                self._write_row(mutate)
                with self.assertRaisesRegex(
                    zr.ResultsError, "^tr3: .*fields, expected 5"
                ):
                    self.read()

    def test_table_unparseable_number(self) -> None:
        self._write_row(lambda f: [*f[:2], "x", *f[3:]])
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: .*non-number"):
            self.read()

    def test_table_non_increasing_midpoints(self) -> None:
        path = self.root / "tr3" / "zeta_1e3.txt"
        lines = path.read_text().splitlines()
        lines[3], lines[4] = (
            lines[3].replace(lines[3].split()[0], "4", 1),
            lines[4].replace(lines[4].split()[0], "3", 1),
        )
        # swap rows while keeping line numbers 1..N
        lines[3], lines[4] = lines[4], lines[3]
        path.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            self.read()

    def test_table_equal_midpoints_are_not_increasing(self) -> None:
        path = self.root / "tr3" / "zeta_1e3.txt"
        lines = path.read_text().splitlines()
        f1 = lines[1].split()
        f2 = lines[2].split()
        lines[2] = " ".join([f2[0], *f1[1:]])
        path.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            self.read()

    def test_table_t_outside_bracket(self) -> None:
        path = self.root / "tr3" / "zeta_1e3.txt"
        lines = path.read_text().splitlines()
        f = lines[1].split()
        f[3] = "14.2"
        lines[1] = " ".join(f)
        path.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            self.read()

    def test_table_wrong_row_number(self) -> None:
        path = self.root / "tr3" / "zeta_1e3.txt"
        lines = path.read_text().splitlines()
        lines[2] = lines[2].replace("2 ", "7 ", 1)
        path.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            self.read()


WIGNER_20 = [0, 7, 26, 58, 96, 92, 109, 80, 58, 57, 28, 19, 8, 9, 1, 0, 0, 0, 0, 0]
DISPLAY_60 = [
    0, 0, 0, 0, 4, 3, 3, 13, 10, 12, 22, 24, 26, 27, 43, 34, 22, 36, 37, 41,
    31, 31, 19, 30, 22, 23, 13, 20, 21, 16, 8, 9, 11, 6, 5, 8, 5, 3, 0, 7,
    2, 0, 0, 0, 1,
] + [0] * 15  # fmt: skip


def _bracket_table(brackets: list[tuple[float, float]]) -> "zr.RefinedTable":
    a = [x for x, _ in brackets]
    b = [y for _, y in brackets]
    return zr.RefinedTable(a, b, [x + (y - x) / 2 for x, y in brackets])


class TestComputations(_FixtureCopy):
    """Spacings, CLI cross-check, histograms and Gram statistics."""

    def setUp(self) -> None:
        super().setUp()
        self.table = zr.read_refined(REFINED_TABLE, "tr3", 649)
        self.d = zr.spacings(self.table.m)
        self.summary = zr.parse_out(self.out(), "tr3", 3, refine=True)

    def test_spacings_count_and_empty(self) -> None:
        self.assertEqual(len(self.d), 648)
        self.assertEqual(zr.spacings([]), [])
        self.assertEqual(zr.spacings([20.0]), [])

    def test_spacings_formula_order(self) -> None:
        got = zr.spacings([20.0, 21.0])[0]
        self.assertEqual(got, (21.0 - 20.0) * math.log(20.0 / math.tau) / math.tau)

    def test_ks_pins(self) -> None:
        self.assertEqual(f"{zr.ks_distance(self.d, zr.wigner_cdf):.4f}", "0.0448")
        self.assertEqual(f"{zr.ks_distance(self.d, zr.poisson_cdf):.4f}", "0.3260")

    def test_ks_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            zr.ks_distance([], zr.wigner_cdf)

    def test_erf_and_cdfs(self) -> None:
        self.assertAlmostEqual(zr.as_erf(0.0), 0.0, delta=1.5e-7)
        self.assertAlmostEqual(zr.as_erf(1.0), math.erf(1.0), delta=1.5e-7)
        self.assertEqual(zr.as_erf(-0.5), -zr.as_erf(0.5))
        self.assertEqual(zr.wigner_cdf(0.0), 0.0)
        self.assertEqual(zr.wigner_cdf(-1.0), 0.0)
        self.assertAlmostEqual(zr.wigner_cdf(10.0), 1.0, places=6)
        self.assertEqual(zr.poisson_cdf(0.0), 0.0)
        self.assertEqual(zr.poisson_cdf(1.0), 1 - math.exp(-1.0))
        self.assertAlmostEqual(
            zr.wigner_pdf(1.0), 32 / math.pi**2 * math.exp(-4 / math.pi)
        )

    def test_erf_port_values_pinned(self) -> None:
        self.assertAlmostEqual(zr.as_erf(1.0), 0.8427006897475899, delta=1e-12)
        self.assertAlmostEqual(zr.as_erf(0.5), 0.5205000163047472, delta=1e-12)

    def test_newton_non_convergence_raises(self) -> None:
        with (
            mock.patch.object(zr, "_NEWTON_MAX", 0),
            self.assertRaisesRegex(zr.ResultsError, "did not converge"),
        ):
            zr.gram_points_upto(100.0)
        with (
            mock.patch.object(zr, "_theta_slope", return_value=math.nan),
            self.assertRaisesRegex(zr.ResultsError, "did not converge"),
        ):
            zr.gram_points_upto(100.0)

    def test_cross_check_without_cli_counts_raises(self) -> None:
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            zr.cross_check("tr3", self.d, self._altered(cli_counts=None), 649)

    def test_cli_bins_pin_and_boundaries(self) -> None:
        self.assertEqual(zr.cli_bins(self.d), WIGNER_20)
        self.assertEqual(zr.cli_bins([3.0, 3.1]), [0] * 19 + [1])
        self.assertEqual(zr.cli_bins([]), [0] * 20)
        self.assertEqual(zr.cli_bins([0.0, -0.1]), [1] + [0] * 19)

    def test_display_bins(self) -> None:
        width, counts = zr.display_bins(self.d, threshold=0)
        self.assertEqual(width, 0.05)
        self.assertEqual(counts, DISPLAY_60)
        width, counts = zr.display_bins(self.d)
        self.assertEqual((width, counts), (0.15, WIGNER_20))
        self.assertEqual(zr.display_bins([1.0], threshold=1)[0], 0.05)
        self.assertEqual(zr.display_bins([1.0], threshold=2)[0], 0.15)

    def test_cross_check_passes_on_fixture(self) -> None:
        zr.cross_check("tr3", self.d, self.summary, 649)

    def _altered(self, **changes: object) -> "zr.OutSummary":
        return dataclasses.replace(self.summary, **changes)

    def test_cross_check_fails_closed(self) -> None:
        counts = list(self.summary.cli_counts or ())
        counts[3] += 1
        cases = {
            "count": (self.d, self._altered(), 650),
            "spacings": (self.d, self._altered(spacings=647), 649),
            "bins": (self.d, self._altered(cli_counts=tuple(counts)), 649),
            "ks": (self.d, self._altered(cli_ks="0.0449"), 649),
        }
        for name, (d, out, count) in cases.items():
            with self.subTest(name), self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
                zr.cross_check("tr3", d, out, count)

    def test_gram_points(self) -> None:
        gram = zr.gram_points_upto(1000.0)
        self.assertAlmostEqual(gram[0], 9.666908, places=5)
        self.assertAlmostEqual(gram[1], 17.845600, places=5)
        self.assertLessEqual(gram[-1], 1000.0)
        self.assertGreater(gram[-1] + 3.0, 1000.0)
        self.assertEqual(len(gram), 649)
        self.assertEqual(zr.gram_points_upto(9.0), [])
        self.assertAlmostEqual(zr.theta(gram[5]), 4 * math.pi, places=9)

    def test_gram_stats_pin(self) -> None:
        stats = zr.gram_stats(self.table, zr.gram_points_upto(1000.0))
        self.assertEqual(stats.counts, {0: 22, 1: 604, 2: 22, 3: 0, 4: 0})
        self.assertEqual(round(stats.share, 4), 0.9321)
        self.assertEqual(stats.straddles, 0)

    def test_gram_stats_four_or_more_and_edges(self) -> None:
        gram = [10.0, 20.0, 30.0]
        zeros = [(11.0, 11.0), (12.0, 12.0), (13.0, 13.0), (14.0, 14.0),
                 (15.0, 15.0), (25.0, 25.0), (5.0, 5.0), (30.0, 30.0)]  # fmt: skip
        stats = zr.gram_stats(_bracket_table(zeros), gram)
        self.assertEqual(stats.counts, {0: 0, 1: 1, 2: 0, 3: 0, 4: 1})
        self.assertEqual(stats.share, 0.5)

    def test_straddle_at_gram_point(self) -> None:
        g0 = zr.gram_points_upto(20.0)[1]
        gram = zr.gram_points_upto(20.0)
        cases = {
            "straddle": ((g0 - 0.01, g0 + 0.01), 1),
            "starts at g": ((g0, g0 + 0.01), 0),
            "ends at g": ((g0 - 0.01, g0), 0),
        }
        for name, (bracket, want) in cases.items():
            with self.subTest(name):
                stats = zr.gram_stats(_bracket_table([bracket]), gram)
                self.assertEqual(stats.straddles, want)

    def test_straddle_absolute_tolerance_high_up(self) -> None:
        g = zr.gram_points_upto(9.3e4)[-1]
        gram = [g - 3.0, g, g + 3.0]
        inside = _bracket_table([(g - 1e-5, g + 1e-5)])
        self.assertEqual(zr.gram_stats(inside, gram).straddles, 1)
        near = _bracket_table([(g - 2e-5 + 5e-9, g + 5e-9)])
        self.assertEqual(zr.gram_stats(near, gram).straddles, 0)

    def test_published_counts(self) -> None:
        self.assertEqual(
            zr.PUBLISHED_COUNTS,
            {2: 29, 3: 649, 4: 10142, 5: 138069, 6: 1747146, 7: 21136125},
        )


if __name__ == "__main__":
    unittest.main()


SPEC = (
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-11-24-zeta-results-page-design.md"
)
RUN_IDS = ("t2", "t3", "tr3")
ABSOLUTE_PATH = re.compile(r"(?<![\w.])/(home|tmp|Users|root|var)/")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _spec_claim() -> str:
    """The claim paragraph of the spec's 'Claim text (exact)' section, as plain text."""
    lines = SPEC.read_text().splitlines()
    start = lines.index("### Claim text (exact)")
    quoted = []
    for line in lines[start + 1 :]:
        if line.startswith("> "):
            quoted.append(line[2:])
        elif quoted:
            break
    return " ".join(quoted).replace("`", "")


def _plain(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


def _require_matplotlib(case: unittest.TestCase) -> None:
    if importlib.util.find_spec("matplotlib") is not None:
        return
    if os.environ.get("CI") == "true":
        case.fail("matplotlib not installed; run make install-deps")
    case.skipTest("matplotlib not installed; run make install-deps")


def _owned(path: Path) -> Path:
    """Make `path` a directory the generator would accept as its own."""
    path.mkdir(parents=True, exist_ok=True)
    (path / zr.MARKER).write_bytes(b"")
    return path


class TestRendering(_FixtureCopy):
    """SVGs, index.html, run copies, the atomic swap and the command line."""

    def setUp(self) -> None:
        super().setUp()
        self.site = self.root.parent / "site"
        self.runs_dir = self.root.parent / "runs"
        self.stderr = io.StringIO()

    def require_matplotlib(self) -> None:
        _require_matplotlib(self)

    def argv(
        self, out: Path | None = None, ids: tuple[str, ...] = RUN_IDS
    ) -> list[str]:
        args = ["--runs-toml", str(self.root / "runs.toml")]
        for run_id in ids:
            args += ["--run", f"{run_id}={self.root / run_id}"]
        args += ["--out", str(out or self.site), "--runs-out", str(self.runs_dir)]
        return args

    def generate(self, out: Path | None = None, ids: tuple[str, ...] = RUN_IDS) -> int:
        self.require_matplotlib()
        with contextlib.redirect_stderr(self.stderr):
            return zr.main(self.argv(out, ids))

    def page(self) -> str:
        return (self.site / "index.html").read_text()

    def test_gated_tests_skip_when_matplotlib_is_absent_outside_ci(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "CI"}
        with (
            mock.patch.object(importlib.util, "find_spec", return_value=None),
            mock.patch.dict(os.environ, env, clear=True),
            self.assertRaises(unittest.SkipTest) as caught,
        ):
            self.require_matplotlib()
        self.assertEqual(
            str(caught.exception), "matplotlib not installed; run make install-deps"
        )

    def test_gated_tests_fail_when_matplotlib_is_absent_in_ci(self) -> None:
        with (
            mock.patch.object(importlib.util, "find_spec", return_value=None),
            mock.patch.dict(os.environ, {"CI": "true"}),
            self.assertRaises(self.failureException),
        ):
            self.require_matplotlib()

    def test_smoke_run_writes_page_and_svgs(self) -> None:
        self.assertEqual(self.generate(), 0, self.stderr.getvalue())
        self.assertEqual(
            sorted(p.name for p in self.site.iterdir()),
            [zr.MARKER, "gaps-N3.svg", "gram-share.svg", "index.html"],
        )

    def test_two_runs_are_byte_identical(self) -> None:
        other = self.root.parent / "site2"
        self.assertEqual(self.generate(), 0)
        self.assertEqual(self.generate(other), 0)
        self.assertEqual(_snapshot(self.site), _snapshot(other))

    def test_failed_check_leaves_existing_site_unchanged(self) -> None:
        self.assertEqual(self.generate(), 0)
        before = _snapshot(self.site)
        self.edit("tr3/err.txt", "Exit status: 0", "Exit status: 1")
        self.assertEqual(self.generate(), 1)
        self.assertTrue(self.stderr.getvalue().startswith("tr3: "))
        self.assertEqual(_snapshot(self.site), before)

    def test_failed_check_writes_nothing_on_first_run(self) -> None:
        self.edit("tr3/err.txt", "Exit status: 0", "Exit status: 1")
        self.assertEqual(self.generate(), 1)
        self.assertFalse(self.site.exists())
        self.assertFalse(self.site.with_name("site.tmp").exists())
        self.assertFalse(self.runs_dir.exists())

    def test_crash_leftover_tmp_is_removed_and_other_siblings_survive(self) -> None:
        parent = self.root.parent
        for name in ("site.tmp", "runs.tmp"):
            _owned(parent / name)
            (parent / name / "junk").write_text("x")
        for name in ("site.toml", "site.partial"):
            (parent / name).write_text("keep")
        self.assertEqual(self.generate(), 0)
        self.assertFalse((parent / "site.tmp").exists())
        self.assertFalse((parent / "runs.tmp").exists())
        for name in ("site.toml", "site.partial"):
            self.assertEqual((parent / name).read_text(), "keep")

    def test_failed_check_still_removes_stale_tmp(self) -> None:
        stale = _owned(self.site.with_name("site.tmp"))
        self.edit("tr3/err.txt", "Exit status: 0", "Exit status: 1")
        self.assertEqual(self.generate(), 1)
        self.assertFalse(stale.exists())

    def test_crash_between_renames_is_recovered_at_start(self) -> None:
        for final, tmp_name in ((self.site, "site"), (self.runs_dir, "runs")):
            old = _owned(final.with_name(f"{tmp_name}.old"))
            (old / "last.txt").write_text("last good")
            _owned(final.with_name(f"{tmp_name}.tmp"))
        self.edit("tr3/err.txt", "Exit status: 0", "Exit status: 1")
        self.assertEqual(self.generate(), 1)
        for final, tmp_name in ((self.site, "site"), (self.runs_dir, "runs")):
            self.assertEqual((final / "last.txt").read_text(), "last good")
            self.assertFalse(final.with_name(f"{tmp_name}.old").exists())
            self.assertFalse(final.with_name(f"{tmp_name}.tmp").exists())

    def test_recovery_leaves_a_present_site_alone_and_drops_its_old(self) -> None:
        self.assertEqual(self.generate(), 0)
        before = _snapshot(self.site)
        _owned(self.site.with_name("site.old"))
        self.edit("tr3/err.txt", "Exit status: 0", "Exit status: 1")
        self.assertEqual(self.generate(), 1)
        self.assertEqual(_snapshot(self.site), before)
        self.assertFalse(self.site.with_name("site.old").exists())

    def test_dot_out_is_refused_and_deletes_nothing(self) -> None:
        self.require_matplotlib()
        cwd = self.root.parent / "cwd"
        (cwd / ".git").mkdir(parents=True)
        (cwd / ".git" / "HEAD").write_text("ref")
        (cwd / "site.tmp").mkdir()
        before = _snapshot(cwd)
        previous = Path.cwd()
        os.chdir(cwd)
        self.addCleanup(os.chdir, previous)
        for bad in (".", "..", "x/..", "/"):
            with self.subTest(out=bad):
                self.stderr = io.StringIO()
                with contextlib.redirect_stderr(self.stderr):
                    rc = zr.main(
                        [*self.argv(Path(bad))[:-4], "--out", bad, "--runs-out", "r"]
                    )
                self.assertEqual(rc, 1)
                self.assertIn("refusing", self.stderr.getvalue())
        self.assertEqual(_snapshot(cwd), before)

    def test_the_working_directory_is_refused_as_a_target(self) -> None:
        self.require_matplotlib()
        cwd = self.root.parent / "cwd2"
        (cwd / "sub").mkdir(parents=True)
        previous = Path.cwd()
        os.chdir(cwd)
        self.addCleanup(os.chdir, previous)
        with contextlib.redirect_stderr(self.stderr):
            rc = zr.main([*self.argv()[:-4], "--out", str(cwd), "--runs-out", "r"])
        self.assertEqual(rc, 1)
        self.assertTrue((cwd / "sub").is_dir())

    def data_dir(self) -> Path:
        """A private copy of the inputs, so a slip would have something to wipe."""
        data = self.root.parent / "data"
        shutil.copytree(self.root, data)
        return data

    def run_main(
        self, toml: Path, dirs: dict[str, Path], out: Path, runs_out: Path
    ) -> int:
        self.require_matplotlib()
        argv = [
            "--runs-toml",
            str(toml),
            "--out",
            str(out),
            "--runs-out",
            str(runs_out),
        ]
        for run_id, path in dirs.items():
            argv += ["--run", f"{run_id}={path}"]
        self.stderr = io.StringIO()
        with contextlib.redirect_stderr(self.stderr):
            return zr.main(argv)

    def assert_refused_untouched(self, rc: int, *roots: Path) -> None:
        before = [_snapshot(r) for r in roots]
        self.assertEqual(rc, 1, self.stderr.getvalue())
        self.assertIn("refusing", self.stderr.getvalue())
        self.assertEqual([_snapshot(r) for r in roots], before)

    def test_runs_out_may_not_be_the_input_directory(self) -> None:
        data = self.data_dir()
        before = _snapshot(data)
        dirs = {i: data / i for i in RUN_IDS}
        rc = self.run_main(data / "runs.toml", dirs, self.site, data)
        self.assertEqual(rc, 1)
        self.assertIn("refusing", self.stderr.getvalue())
        self.assertEqual(_snapshot(data), before)
        self.assertFalse(self.site.exists())

    def test_out_may_not_be_an_input_run_directory(self) -> None:
        data = self.data_dir()
        before = _snapshot(data)
        dirs = {i: data / i for i in RUN_IDS}
        rc = self.run_main(data / "runs.toml", dirs, data / "t2", self.runs_dir)
        self.assertEqual(rc, 1)
        self.assertIn("refusing", self.stderr.getvalue())
        self.assertEqual(_snapshot(data), before)

    def test_targets_may_not_sit_inside_or_be_inputs(self) -> None:
        data = self.data_dir()
        before = _snapshot(data)
        dirs = {i: data / i for i in RUN_IDS}
        cases = [
            (data / "t2" / "sub", self.runs_dir),
            (self.site, data / "tr3" / "inner" / "deep"),
            (self.site, data / "runs.toml"),
            (data / "runs.toml" / "x", self.runs_dir),
        ]
        for out, runs_out in cases:
            with self.subTest(out=out.name, runs_out=runs_out.name):
                rc = self.run_main(data / "runs.toml", dirs, out, runs_out)
                self.assertEqual(rc, 1)
                self.assertIn("refusing", self.stderr.getvalue())
        self.assertEqual(_snapshot(data), before)

    def test_old_or_tmp_sibling_may_not_be_an_input(self) -> None:
        parent = self.root.parent
        held = parent / "siteX.old"
        shutil.copytree(self.root / "t2", held)
        before = _snapshot(held)
        dirs = {"t2": held, "t3": self.root / "t3", "tr3": self.root / "tr3"}
        rc = self.run_main(
            self.root / "runs.toml", dirs, parent / "siteX", self.runs_dir
        )
        self.assertEqual(rc, 1)
        self.assertIn("refusing", self.stderr.getvalue())
        self.assertEqual(_snapshot(held), before)

    def test_out_and_runs_out_siblings_may_not_collide(self) -> None:
        dirs = {i: self.root / i for i in RUN_IDS}
        for name in ("site.old", "site.tmp"):
            with self.subTest(runs_out=name):
                victim = self.root.parent / name
                victim.mkdir()
                (victim / "keep.txt").write_text("keep")
                rc = self.run_main(self.root / "runs.toml", dirs, self.site, victim)
                self.assert_refused_untouched(rc, victim)
                shutil.rmtree(victim)

    def test_runs_out_may_not_equal_or_nest_with_out(self) -> None:
        self.require_matplotlib()
        base = self.root.parent / "t"
        cases = [
            (base, base),
            (base, base / "runs"),
            (base / "site", base),
            (base / "..", base / "runs"),
        ]
        for out, runs_out in cases:
            with self.subTest(out=str(out), runs_out=str(runs_out)):
                self.stderr = io.StringIO()
                argv = [
                    *self.argv()[:-4],
                    "--out",
                    str(out),
                    "--runs-out",
                    str(runs_out),
                ]
                with contextlib.redirect_stderr(self.stderr):
                    rc = zr.main(argv)
                self.assertEqual(rc, 1)
                self.assertIn("refusing", self.stderr.getvalue())
        self.assertFalse(base.exists())

    def test_runs_out_is_required(self) -> None:
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            zr.main(["--runs-toml", "x", "--out", "y"])

    def test_run_without_toml_entry_fails(self) -> None:
        self.assertEqual(self.generate(ids=(*RUN_IDS, "zz")), 1)
        self.assertRegex(self.stderr.getvalue(), r"^zz: ")

    def test_toml_entry_without_run_fails(self) -> None:
        self.assertEqual(self.generate(ids=("t2", "t3")), 1)
        self.assertRegex(self.stderr.getvalue(), r"^tr3: ")

    def test_malformed_run_spec_fails(self) -> None:
        self.require_matplotlib()
        with contextlib.redirect_stderr(self.stderr):
            rc = zr.main(
                [
                    "--runs-toml",
                    "x",
                    "--run",
                    "noequals",
                    "--out",
                    "y",
                    "--runs-out",
                    "z",
                ]
            )
        self.assertEqual(rc, 1)
        self.assertIn("expected <id>=<dir>", self.stderr.getvalue())

    def test_duplicate_run_spec_fails(self) -> None:
        self.require_matplotlib()
        with contextlib.redirect_stderr(self.stderr):
            rc = zr.main(
                [
                    "--runs-toml",
                    "x",
                    "--run",
                    "a=1",
                    "--run",
                    "a=2",
                    "--out",
                    "y",
                    "--runs-out",
                    "z",
                ]
            )
        self.assertEqual(rc, 1)
        self.assertRegex(self.stderr.getvalue(), r"^a: ")

    def test_two_runs_of_the_same_command_fail(self) -> None:
        shutil.copytree(self.root / "tr3", self.root / "tr3b")
        with (self.root / "runs.toml").open("a") as handle:
            handle.write(
                '\n[[run]]\nid = "tr3b"\n'
                'binary_sha = "f935b233046fa0905c3198efc93a15fb2412677a"\n'
                'machine = "m"\ndate = "2026-11-24"\n'
            )
        self.assertEqual(self.generate(ids=(*RUN_IDS, "tr3b")), 1)
        self.assertRegex(self.stderr.getvalue(), r"^tr3b: .*duplicate")

    def test_missing_run_file_names_the_run(self) -> None:
        (self.root / "t2" / "out.txt").unlink()
        self.assertEqual(self.generate(), 1)
        self.assertRegex(self.stderr.getvalue(), r"^t2: cannot read out\.txt")

    def test_page_hygiene(self) -> None:
        self.assertEqual(self.generate(), 0)
        page = self.page()
        self.assertNotIn("<script", page)
        self.assertIsNone(re.search(r'(?:src|href)="http', page))
        self.assertIn(
            '<meta name="viewport" content="width=device-width, initial-scale=1">', page
        )
        self.assertIn("img{max-width:100%;height:auto}", page)
        self.assertEqual(
            page.count("<table>"), page.count('<div style="overflow-x:auto">\n<table>')
        )
        self.assertGreater(page.count("<table>"), 0)
        self.assertEqual(
            len(re.findall(r"<img ", page)),
            len(re.findall(r'<img [^>]*alt="[^"]+"', page)),
        )
        self.assertIn('<a href="deployed-from.txt">', page)
        for name, data in _snapshot(self.site).items():
            self.assertNotIn(b"../zeta-f935b23", data, name)

    def test_claim_paragraph_is_verbatim_from_the_spec(self) -> None:
        self.assertEqual(self.generate(), 0)
        match = re.search(r'<p class="claim">(.*?)</p>', self.page(), re.DOTALL)
        assert match is not None
        self.assertEqual(_plain(match.group(1)), _spec_claim())

    def test_nothing_else_calls_the_result_new(self) -> None:
        self.assertEqual(self.generate(), 0)
        rest = re.sub(r'<p class="claim">.*?</p>', "", self.page(), flags=re.DOTALL)
        self.assertIsNone(re.search(r"\bnew\b", _plain(rest)))

    def test_definitions_and_contrast_are_present(self) -> None:
        self.assertEqual(self.generate(), 0)
        text = _plain(self.page())
        self.assertIn("A Gram point", text)
        self.assertIn("normalised gap", text)
        self.assertIn("m_n is the midpoint", text)
        self.assertIn("contrast with Poisson", text)
        self.assertIn("not certified", text)

    def test_counts_gram_and_run_tables_carry_the_fixture_values(self) -> None:
        self.assertEqual(self.generate(), 0)
        text = _plain(self.page())
        self.assertRegex(text, r"3\s*refine\s*649\s*649\s*equal")
        self.assertRegex(text, r"3\s*22\s*604\s*22\s*0\s*0\s*0\.9321\s*0")
        self.assertIn("Machine: Threadripper 3960X, 48 threads, Ubuntu 26.04", text)
        self.assertIn("2.45 s", text)

    def test_every_figure_has_a_provenance_line(self) -> None:
        self.assertEqual(self.generate(), 0)
        figures = re.findall(r"<figure>.*?</figure>", self.page(), re.DOTALL)
        self.assertEqual(len(figures), 2)
        for figure in figures:
            caption = re.search(
                r'<figcaption class="provenance">(.*?)</figcaption>', figure
            )
            assert caption is not None
            for part in (
                "command: zeta 3 --refine",
                "binary commit: f935b23",
                "machine: Threadripper",
                "date: 2026-11-24",
            ):
                self.assertIn(part, caption.group(1))

    def test_svg_files_equal_img_sources_and_show_bars_and_curves(self) -> None:
        self.assertEqual(self.generate(), 0)
        sources = set(re.findall(r'<img src="([^"]+)"', self.page()))
        self.assertEqual(sources, {p.name for p in self.site.glob("*.svg")})
        gaps = (self.site / "gaps-N3.svg").read_text()
        self.assertIn('id="hist-bar-0"', gaps)
        self.assertIn('id="hist-bar-19"', gaps)
        self.assertNotIn('id="hist-bar-20"', gaps)
        self.assertIn('id="wigner-curve"', gaps)
        self.assertIn('id="poisson-curve"', gaps)

    def test_run_copies_drop_the_binary_path(self) -> None:
        self.assertEqual(self.generate(), 0)
        for run_id in RUN_IDS:
            copied = (self.runs_dir / run_id / "err.txt").read_text()
            self.assertNotIn("../", copied)
            self.assertRegex(copied, r'Command being timed: "zeta-f935b23 \d')
            self.assertEqual(
                (self.runs_dir / run_id / "out.txt").read_text(),
                (self.root / run_id / "out.txt").read_text(),
            )

    def test_strip_command_path_leaves_other_lines_alone(self) -> None:
        text = 'x ../y\n\tCommand being timed: "/a/b/zeta-1234567 3 --refine"\nz /q/\n'
        want = 'x ../y\n\tCommand being timed: "zeta-1234567 3 --refine"\nz /q/\n'
        self.assertEqual(zr.strip_command_path(text, "1234567" + "0" * 33), want)
        self.assertEqual(zr.strip_command_path("no command", "1234567"), "no command")

    def test_strip_command_path_handles_absolute_and_spaced_paths(self) -> None:
        sha = "1234567" + "0" * 33
        for path in (
            "/home/u/zeta-1234567",
            "/home/u/my runs/zeta-1234567",
            "zeta-1234567",
        ):
            with self.subTest(path=path):
                text = f'\tCommand being timed: "{path} 3"\n'
                self.assertEqual(
                    zr.strip_command_path(text, sha),
                    '\tCommand being timed: "zeta-1234567 3"\n',
                )

    def test_published_err_fails_closed_on_an_unexpected_command_line(self) -> None:
        rep = zr.parse_time_report(self.err(), "tr3")
        good = zr.published_err(self.err(), rep, "f935b23" + "0" * 33, "tr3")
        self.assertIn('Command being timed: "zeta-f935b23 3 --refine"', good)
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            zr.published_err(self.err(), rep, "abcdef0" + "0" * 33, "tr3")

    def test_absolute_and_spaced_binary_paths_are_stripped_in_copies(self) -> None:
        self.edit(
            "tr3/err.txt",
            '"../zeta-f935b23 3 --refine"',
            '"/home/u/my runs/zeta-f935b23 3 --refine"',
        )
        self.assertEqual(self.generate(), 0, self.stderr.getvalue())
        copied = (self.runs_dir / "tr3" / "err.txt").read_text()
        self.assertIn('Command being timed: "zeta-f935b23 3 --refine"', copied)
        self.assertNotIn("/home", copied)

    def test_dropped_run_directory_does_not_linger(self) -> None:
        _owned(self.runs_dir)
        (self.runs_dir / "gone").mkdir()
        (self.runs_dir / "gone" / "out.txt").write_text("stale")
        self.assertEqual(self.generate(), 0)
        self.assertEqual(
            sorted(p.name for p in self.runs_dir.iterdir()),
            sorted([zr.MARKER, *RUN_IDS]),
        )

    def test_staging_failure_leaves_both_old_trees_untouched(self) -> None:
        self.assertEqual(self.generate(), 0)
        before = (_snapshot(self.site), _snapshot(self.runs_dir))
        calls = {"n": 0}
        real = Path.write_bytes

        def flaky(path: Path, data: bytes) -> int:
            calls["n"] += 1
            if calls["n"] > 3:
                raise OSError("disk full")
            return real(path, data)

        with mock.patch.object(Path, "write_bytes", flaky):
            self.assertEqual(self.generate(), 1)
        self.assertGreater(calls["n"], 3)
        self.assertEqual((_snapshot(self.site), _snapshot(self.runs_dir)), before)
        self.assertEqual(sorted(p.name for p in self.root.parent.glob("*.tmp")), [])

    def test_failed_runs_swap_rolls_the_site_back(self) -> None:
        self.assertEqual(self.generate(), 0)
        before = (_snapshot(self.site), _snapshot(self.runs_dir))
        real = Path.rename

        def flaky(src: Path, target: Path) -> Path:
            if src.name == "runs.tmp":
                raise OSError("boom")
            return real(src, target)

        with mock.patch.object(Path, "rename", flaky):
            self.assertEqual(self.generate(), 1)
        self.assertEqual((_snapshot(self.site), _snapshot(self.runs_dir)), before)

    def test_published_err_requires_exactly_one_command_line(self) -> None:
        rep = zr.parse_time_report(self.err(), "tr3")
        extra = '\tCommand being timed: "/home/u/zeta-f935b23 3 --refine"\n'
        sha = "f935b23" + "0" * 33
        for bad in (self.err() + extra, self.err() + "\tCommand being timed: x\n"):
            with (
                self.subTest(bad=bad[-30:]),
                self.assertRaisesRegex(zr.ResultsError, "^tr3: .*exactly one"),
            ):
                zr.published_err(bad, rep, sha, "tr3")
        without = self.err().replace("Command being timed", "Cmd")
        with self.assertRaisesRegex(zr.ResultsError, "^tr3: "):
            zr.published_err(without, rep, sha, "tr3")

    def test_count_verdict(self) -> None:
        self.assertEqual(zr.count_verdict(3, 649), "equal")
        self.assertEqual(zr.count_verdict(3, 648), "differs")
        self.assertEqual(zr.count_verdict(3, 650), "differs")

    def test_format_elapsed(self) -> None:
        self.assertEqual(zr.format_elapsed(2.45), "2.45 s")
        self.assertEqual(zr.format_elapsed(59.99), "59.99 s")
        self.assertEqual(zr.format_elapsed(60), "0:01:00")
        self.assertEqual(zr.format_elapsed(125), "0:02:05")
        self.assertEqual(zr.format_elapsed(3743), "1:02:23")
        self.assertEqual(zr.format_elapsed(3600), "1:00:00")

    def test_swap_restores_old_site_when_the_second_rename_fails(self) -> None:
        site = self.root.parent / "swap"
        site.mkdir()
        (site / "old.txt").write_text("old")
        tmp = self.root.parent / "swap.tmp"
        tmp.mkdir()
        (tmp / "new.txt").write_text("new")
        real = Path.rename

        def flaky(src: Path, target: Path) -> Path:
            if src.name == "swap.tmp":
                raise OSError("boom")
            return real(src, target)

        with mock.patch.object(Path, "rename", flaky), self.assertRaises(OSError):
            zr._swap_in(tmp, site)
        self.assertEqual((site / "old.txt").read_text(), "old")
        self.assertFalse((self.root.parent / "swap.old").exists())

    def test_swap_without_an_existing_site(self) -> None:
        site = self.root.parent / "fresh"
        tmp = self.root.parent / "fresh.tmp"
        tmp.mkdir()
        (tmp / "new.txt").write_text("new")
        zr._swap_in(tmp, site)
        self.assertEqual((site / "new.txt").read_text(), "new")
        self.assertFalse(tmp.exists())

    def test_matplotlib_missing_prints_the_remedy_and_exits_1(self) -> None:
        with (
            mock.patch.dict(sys.modules, {"matplotlib": None}),
            contextlib.redirect_stderr(self.stderr),
        ):
            rc = zr.main(self.argv())
        self.assertEqual(rc, 1)
        self.assertEqual(
            self.stderr.getvalue().strip(),
            "zeta_results: matplotlib missing; run make install-deps",
        )
        self.assertFalse(self.site.exists())
        self.assertFalse(self.runs_dir.exists())

    def test_only_matplotlib_is_third_party_and_its_imports_are_pinned(self) -> None:
        source = (REPO_ROOT / "scripts" / "zeta_results.py").read_text()
        lines = source.splitlines()
        third_party = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                if name not in sys.stdlib_module_names:
                    third_party.add(name)
                    self.assertIn(
                        "# pyright: ignore[reportMissingImports]",
                        lines[node.lineno - 1],
                    )
        self.assertEqual(third_party, {"matplotlib"})

    def test_no_absolute_path_in_committed_results_or_fixtures(self) -> None:
        for base in (REPO_ROOT / "zeta" / "results", FIXTURES):
            for path in base.rglob("*") if base.exists() else []:
                if path.is_file():
                    text = path.read_text(errors="replace")
                    self.assertIsNone(ABSOLUTE_PATH.search(text), str(path))


def _tree(root: Path) -> dict[str, tuple[str, bytes | str]]:
    """Every entry under `root`, links unfollowed, so a victim can be compared."""
    seen: dict[str, tuple[str, bytes | str]] = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(base) / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                seen[rel] = ("link", os.readlink(path))
            elif path.is_dir():
                seen[rel] = ("dir", b"")
            else:
                seen[rel] = ("file", path.read_bytes())
    return seen


class TestTargetSafety(_FixtureCopy):
    """The generator replaces only trees it wrote, and never through a symlink."""

    def setUp(self) -> None:
        super().setUp()
        self.work = self.root.parent / "work"
        self.work.mkdir()
        self.site = self.work / "site"
        self.runs = self.work / "runs"
        self.dirs = {i: self.root / i for i in RUN_IDS}
        self.stderr = io.StringIO()

    def inputs(self) -> list[Path]:
        return [self.root / "runs.toml", *self.dirs.values()]

    def refuse(self, out: Path, runs_out: Path, pattern: str) -> None:
        """`_check_targets` refuses with `pattern` and leaves everything as it was."""
        before = (_tree(self.work), _tree(self.root))
        with self.assertRaisesRegex(zr.ResultsError, pattern):
            zr._check_targets(out, runs_out, self.inputs())
        self.assertEqual((_tree(self.work), _tree(self.root)), before)

    def run_main(self, out: Path, runs_out: Path, dirs: dict[str, Path]) -> int:
        _require_matplotlib(self)
        argv = ["--runs-toml", str(self.root / "runs.toml")]
        for run_id, path in dirs.items():
            argv += ["--run", f"{run_id}={path}"]
        argv += ["--out", str(out), "--runs-out", str(runs_out)]
        self.stderr = io.StringIO()
        with contextlib.redirect_stderr(self.stderr):
            return zr.main(argv)

    def victim(self, name: str) -> Path:
        """A directory of someone else's, with content and no marker."""
        path = self.work / name
        (path / "sub").mkdir(parents=True)
        (path / "sub" / "keep.txt").write_text("keep")
        return path

    def test_symlinked_out_is_refused_and_its_old_input_survives(self) -> None:
        real = self.victim("real")
        lnk = self.work / "lnk"
        lnk.symlink_to(real)
        held = self.work / "lnk.old"
        shutil.copytree(self.root / "t2", held)
        dirs = {**self.dirs, "t2": held}
        before = _tree(self.work)
        _require_matplotlib(self)
        self.assertEqual(self.run_main(lnk, self.runs, dirs), 1)
        self.assertIn("refusing --out: lnk is a symlink", self.stderr.getvalue())
        self.assertEqual(_tree(self.work), before)
        self.assertTrue((held / "out.txt").is_file())

    def test_symlinked_out_is_refused_by_the_check_alone(self) -> None:
        lnk = self.work / "lnk"
        lnk.symlink_to(self.victim("real"))
        self.refuse(lnk, self.runs, "^refusing --out: lnk is a symlink$")

    def test_symlinked_old_or_tmp_sibling_is_refused(self) -> None:
        elsewhere = self.victim("elsewhere")
        for suffix in ("old", "tmp"):
            with self.subTest(suffix=suffix):
                link = self.work / f"site.{suffix}"
                link.symlink_to(elsewhere)
                self.refuse(
                    self.site,
                    self.runs,
                    f"^refusing --out: site.{suffix} is a symlink$",
                )
                link.unlink()

    def test_symlinked_runs_out_and_its_siblings_are_refused(self) -> None:
        elsewhere = self.victim("elsewhere")
        link = self.work / "runs"
        link.symlink_to(elsewhere)
        self.refuse(self.site, self.runs, "^refusing --runs-out: runs is a symlink$")
        link.unlink()
        sibling = self.work / "runs.old"
        sibling.symlink_to(elsewhere)
        self.refuse(
            self.site, self.runs, "^refusing --runs-out: runs.old is a symlink$"
        )

    def test_dangling_symlink_target_is_refused(self) -> None:
        (self.work / "site").symlink_to(self.work / "nowhere")
        self.refuse(self.site, self.runs, "is a symlink$")

    def test_foreign_directories_are_refused_for_both_flags(self) -> None:
        foreign = self.victim("foreign")
        pattern = "exists and was not written by this generator$"
        self.refuse(foreign, self.runs, f"^refusing --out: foreign {pattern}")
        self.refuse(self.site, foreign, f"^refusing --runs-out: foreign {pattern}")

    def test_foreign_directory_is_untouched_by_a_full_run(self) -> None:
        foreign = self.victim("foreign")
        before = _tree(foreign)
        self.assertEqual(self.run_main(foreign, self.runs, self.dirs), 1)
        self.assertIn("foreign exists and was not written", self.stderr.getvalue())
        self.assertEqual(_tree(foreign), before)
        self.assertFalse(self.runs.exists())

    def test_a_regular_file_target_is_refused(self) -> None:
        for flag, out, runs_out in (
            ("--out", self.work / "f", self.runs),
            ("--runs-out", self.site, self.work / "f"),
        ):
            with self.subTest(flag=flag):
                (self.work / "f").write_text("precious")
                self.refuse(out, runs_out, f"^refusing {flag}: f is not a directory$")
                self.assertEqual((self.work / "f").read_text(), "precious")
                (self.work / "f").unlink()

    def test_unmarked_old_or_tmp_sibling_is_refused_whatever_it_is(self) -> None:
        for suffix in ("old", "tmp"):
            for kind in ("full dir", "empty dir", "file"):
                with self.subTest(suffix=suffix, kind=kind):
                    path = self.work / f"site.{suffix}"
                    if kind == "file":
                        path.write_text("precious")
                    elif kind == "empty dir":
                        path.mkdir()
                    else:
                        path.mkdir()
                        (path / "x").write_text("precious")
                    pattern = (
                        "is not a directory$"
                        if kind == "file"
                        else "was not written by this generator$"
                    )
                    self.refuse(
                        self.site,
                        self.runs,
                        f"^refusing --out: site.{suffix} .*{pattern}",
                    )
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()

    def test_marked_old_and_tmp_are_recovered_as_before(self) -> None:
        old = _owned(self.work / "site.old")
        (old / "last.txt").write_text("last good")
        _owned(self.work / "site.tmp")
        zr._check_targets(self.site, self.runs, self.inputs())
        zr._recover(self.site)
        self.assertEqual((self.site / "last.txt").read_text(), "last good")
        self.assertFalse(old.exists())
        self.assertFalse((self.work / "site.tmp").exists())

    def test_missing_and_empty_targets_pass_the_check(self) -> None:
        zr._check_targets(self.site, self.runs, self.inputs())
        self.site.mkdir()
        self.runs.mkdir()
        zr._check_targets(self.site, self.runs, self.inputs())

    def test_an_empty_directory_is_replaced_and_marked(self) -> None:
        self.site.mkdir()
        self.runs.mkdir()
        self.assertEqual(self.run_main(self.site, self.runs, self.dirs), 0)
        self.assertTrue((self.site / zr.MARKER).is_file())
        self.assertTrue((self.runs / zr.MARKER).is_file())
        self.assertTrue((self.site / "index.html").is_file())

    def test_a_generator_directory_is_replaced(self) -> None:
        _owned(self.site)
        (self.site / "stale.txt").write_text("stale")
        _owned(self.runs)
        self.assertEqual(self.run_main(self.site, self.runs, self.dirs), 0)
        self.assertFalse((self.site / "stale.txt").exists())
        self.assertTrue((self.site / zr.MARKER).is_file())
        self.assertTrue((self.runs / zr.MARKER).is_file())

    def test_stage_writes_the_marker_before_any_other_file(self) -> None:
        real = Path.write_bytes
        calls: list[str] = []

        def flaky(path: Path, data: bytes) -> int:
            calls.append(path.name)
            if len(calls) > 1:
                raise OSError("disk full")
            return real(path, data)

        with (
            mock.patch.object(Path, "write_bytes", flaky),
            self.assertRaisesRegex(OSError, "disk full"),
        ):
            zr._stage(self.site, {"a.txt": b"1", "b.txt": b"2"})
        self.assertEqual(calls, [zr.MARKER, "a.txt"])
        self.assertTrue((self.work / "site.tmp" / zr.MARKER).is_file())
        zr._check_targets(self.site, self.runs, self.inputs())
        zr._recover(self.site)
        self.assertFalse((self.work / "site.tmp").exists())

    def test_publishing_twice_gives_identical_trees(self) -> None:
        self.assertEqual(self.run_main(self.site, self.runs, self.dirs), 0)
        first = (_tree(self.site), _tree(self.runs))
        self.assertEqual(
            self.run_main(self.site, self.runs, self.dirs), 0, self.stderr.getvalue()
        )
        self.assertEqual((_tree(self.site), _tree(self.runs)), first)
        self.assertIn(zr.MARKER, first[0])
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), ["runs", "site"])

    def test_the_marker_is_not_page_content(self) -> None:
        self.assertEqual(self.run_main(self.site, self.runs, self.dirs), 0)
        self.assertNotIn(zr.MARKER, (self.site / "index.html").read_text())
        self.assertEqual((self.site / zr.MARKER).read_bytes(), b"")


class TestCanonicalTargets(_FixtureCopy):
    """Checks and actions share one resolved path, so `..` after a symlink is safe."""

    def setUp(self) -> None:
        super().setUp()
        self.s = self.root.parent / "S"
        (self.s / "deep" / "a").mkdir(parents=True)
        (self.s / "link").symlink_to(self.s / "deep" / "a")
        for name in ("t2", "t3", "tr3"):
            shutil.copytree(self.root / name, self.s / name)
        shutil.copy(self.root / "runs.toml", self.s / "runs.toml")
        self.runs_out = self.s / "runsout"
        self.stderr = io.StringIO()

    def run_main(
        self,
        out: str | Path,
        runs_out: str | Path,
        extra: dict[str, Path] | None = None,
    ) -> int:
        _require_matplotlib(self)
        dirs = {i: self.s / i for i in RUN_IDS}
        dirs.update(extra or {})
        argv = ["--runs-toml", str(self.s / "runs.toml")]
        for run_id, path in dirs.items():
            argv += ["--run", f"{run_id}={path}"]
        argv += ["--out", str(out), "--runs-out", str(runs_out)]
        self.stderr = io.StringIO()
        with contextlib.redirect_stderr(self.stderr):
            return zr.main(argv)

    def dotdot(self, name: str) -> str:
        return f"{self.s}/link/../{name}"

    def test_dotdot_after_a_symlink_cannot_reach_an_unowned_directory(self) -> None:
        victim = self.s / "deep" / "victim"
        victim.mkdir()
        (victim / "keep.txt").write_text("keep")
        before = _tree(self.s / "deep")
        self.assertEqual(self.run_main(self.dotdot("victim"), self.runs_out), 1)
        self.assertIn("was not written by this generator", self.stderr.getvalue())
        self.assertEqual((victim / "keep.txt").read_text(), "keep")
        self.assertEqual(_tree(self.s / "deep"), before)
        self.assertFalse(self.runs_out.exists())

    def test_dotdot_after_a_symlink_publishes_at_the_real_location(self) -> None:
        victim = _owned(self.s / "deep" / "victim")
        (victim / "stale.txt").write_text("stale")
        self.assertEqual(
            self.run_main(self.dotdot("victim"), self.runs_out),
            0,
            self.stderr.getvalue(),
        )
        self.assertTrue((victim / "index.html").is_file())
        self.assertFalse((victim / "stale.txt").exists())
        self.assertFalse((self.s / "victim").exists())
        self.assertFalse((self.s / "victim.tmp").exists())

    def test_dotdot_after_a_symlink_overlapping_an_input_is_refused(self) -> None:
        (self.s / "deep" / "x").mkdir()
        shutil.copytree(self.s / "t2", self.s / "deep" / "x" / "run")
        moved = self.s / "deep" / "x"
        before = _tree(moved)
        extra = {"t2": moved / "run"}
        self.assertEqual(self.run_main(self.s / "site", self.dotdot("x"), extra), 1)
        self.assertIn("overlaps an input", self.stderr.getvalue())
        self.assertEqual(_tree(moved), before)

    def test_symlinked_parent_without_dotdot_still_publishes_into_it(self) -> None:
        self.assertEqual(
            self.run_main(self.s / "link" / "site", self.runs_out),
            0,
            self.stderr.getvalue(),
        )
        self.assertTrue((self.s / "deep" / "a" / "site" / "index.html").is_file())

    def test_a_symlinked_marker_does_not_prove_ownership(self) -> None:
        target = self.s / "deep" / "owned"
        target.mkdir()
        (target / "keep.txt").write_text("keep")
        real_file = self.s / "deep" / "real-marker"
        real_file.write_text("")
        (target / zr.MARKER).symlink_to(real_file)
        before = _tree(target)
        self.assertEqual(self.run_main(target, self.runs_out), 1)
        self.assertIn("was not written by this generator", self.stderr.getvalue())
        self.assertEqual(_tree(target), before)

    def test_a_regular_marker_still_proves_ownership(self) -> None:
        self.assertTrue(zr._has_marker(_owned(self.s / "deep" / "m")))
        self.assertFalse(zr._has_marker(self.s / "deep" / "none"))

    def test_nonexistent_parent_chain_is_created(self) -> None:
        out = self.s / "new" / "sub" / "out"
        self.assertEqual(self.run_main(out, self.runs_out), 0, self.stderr.getvalue())
        self.assertTrue((out / "index.html").is_file())

    def test_missing_name_and_leaf_symlink_are_refused_first(self) -> None:
        for raw in ("", "..", f"{self.s}/.."):
            with (
                self.subTest(raw=raw),
                self.assertRaisesRegex(zr.ResultsError, "no directory name"),
            ):
                zr._canonical("--out", Path(raw))
        lnk = self.s / "lnk"
        lnk.symlink_to(self.s / "deep")
        with self.assertRaisesRegex(
            zr.ResultsError, "^refusing --out: lnk is a symlink$"
        ):
            zr._canonical("--out", lnk)

    def test_canonical_returns_the_resolved_parent_and_raw_leaf(self) -> None:
        got = zr._canonical("--out", Path(self.dotdot("victim")))
        self.assertEqual(got, (self.s / "deep" / "victim").resolve())

    def test_one_tree_nested_in_the_others_tmp_or_old_is_refused(self) -> None:
        cases = (
            (self.s / "r.old" / "site", self.s / "r"),
            (self.s / "q.tmp" / "site", self.s / "q"),
            (self.s / "r", self.s / "r.old" / "site"),
            (self.s / "q", self.s / "q.tmp" / "site"),
        )
        for out, runs_out in cases:
            with self.subTest(out=out.name, runs_out=runs_out.name):
                before = _tree(self.s)
                self.assertEqual(self.run_main(out, runs_out), 1)
                self.assertIn("collide", self.stderr.getvalue())
                self.assertEqual(_tree(self.s), before)
                self.assertEqual(
                    sorted(p.name for p in self.s.iterdir()),
                    sorted(["deep", "link", "t2", "t3", "tr3", "runs.toml"]),
                )
