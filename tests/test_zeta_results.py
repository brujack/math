"""Tests for the zeta results page: fixtures, parsing and (later) the generator."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from functools import partial
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
