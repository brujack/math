"""Tests for scripts/cosmic_ray_cell_status.py, driven by a real `cosmic-ray exec` session.

Fixture tests/fixtures/cosmic_ray/crfix-exec.sqlite is an executed session of
crfix.py (survivors and one timeout). Regenerate with
tests/fixtures/cosmic_ray/regen.sh.
"""

import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cosmic_ray_cell_status.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cosmic_ray" / "crfix-exec.sqlite"
DASH = "—"


def run_status(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def scalar(path: pathlib.Path, sql: str) -> int:
    with sqlite3.connect(path) as conn:
        return int(conn.execute(sql).fetchone()[0])


class CellStatusTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.db = self.tmp / "session.sqlite"
        shutil.copyfile(FIXTURE, self.db)

    def execute(self, sql: str) -> None:
        conn = sqlite3.connect(self.db)
        try:
            with conn:
                conn.execute(sql)
        finally:
            conn.close()

    def assert_red(self, proc: subprocess.CompletedProcess[str], needle: str) -> None:
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertTrue(proc.stdout.startswith(f"red: cell {DASH} "), proc.stdout)
        self.assertIn(needle, proc.stdout)


class TestGreen(CellStatusTestCase):
    def test_fixture_has_survivors_and_timeouts(self) -> None:
        s = scalar(
            self.db, "SELECT count(*) FROM work_results WHERE test_outcome='SURVIVED'"
        )
        t = scalar(
            self.db,
            "SELECT count(*) FROM work_results "
            "WHERE test_outcome='KILLED' AND output='timeout'",
        )
        self.assertGreater(s, 0)
        self.assertGreater(t, 0)

    def test_exact_green_line(self) -> None:
        s = scalar(
            self.db, "SELECT count(*) FROM work_results WHERE test_outcome='SURVIVED'"
        )
        t = scalar(
            self.db,
            "SELECT count(*) FROM work_results "
            "WHERE test_outcome='KILLED' AND output='timeout'",
        )
        k = scalar(self.db, "SELECT count(*) FROM work_items")
        proc = run_status(str(self.db), "cell")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout, f"green: cell {DASH} {s} surviving, {t} timed out, {k} jobs\n"
        )

    def test_out_file_equals_stdout(self) -> None:
        out = self.tmp / "status.txt"
        proc = run_status(str(self.db), "cell", "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out.read_text(encoding="utf-8"), proc.stdout)

    def test_survivors_file_exact_and_sorted(self) -> None:
        out = self.tmp / "survivors.txt"
        proc = run_status(str(self.db), "cell", "--survivors", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with sqlite3.connect(self.db) as conn:
            rows = conn.execute(
                "SELECT m.module_path, m.start_pos_row, m.operator_name "
                "FROM work_results r JOIN mutation_specs m USING (job_id) "
                "WHERE r.test_outcome='SURVIVED'"
            ).fetchall()
        expected = sorted(f"{p}:{row} {op}" for p, row, op in rows)
        self.assertGreater(len(expected), 0)
        self.assertEqual(
            out.read_text(encoding="utf-8"), "".join(f"{x}\n" for x in expected)
        )

    def test_timeouts_alone_are_not_red(self) -> None:
        self.execute(
            "UPDATE work_results SET test_outcome='KILLED' WHERE test_outcome='SURVIVED'"
        )
        proc = run_status(str(self.db), "cell")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("0 surviving, 1 timed out", proc.stdout)


class TestRed(CellStatusTestCase):
    def test_deleted_result_row(self) -> None:
        self.execute(
            "DELETE FROM work_results WHERE job_id = (SELECT min(job_id) FROM work_results)"
        )
        self.assert_red(run_status(str(self.db), "cell"), "results")

    def test_all_work_items_deleted(self) -> None:
        self.execute("DELETE FROM work_items")
        self.assert_red(run_status(str(self.db), "cell"), "no work items")

    def test_incompetent_outcome(self) -> None:
        self.execute(
            "UPDATE work_results SET test_outcome='INCOMPETENT' "
            "WHERE job_id = (SELECT min(job_id) FROM work_results)"
        )
        self.assert_red(run_status(str(self.db), "cell"), "INCOMPETENT")

    def test_exception_worker_outcome(self) -> None:
        self.execute(
            "UPDATE work_results SET worker_outcome='EXCEPTION' "
            "WHERE job_id = (SELECT min(job_id) FROM work_results)"
        )
        self.assert_red(run_status(str(self.db), "cell"), "EXCEPTION")

    def test_red_line_written_to_out(self) -> None:
        self.execute("DELETE FROM work_items")
        out = self.tmp / "status.txt"
        proc = run_status(str(self.db), "cell", "--out", str(out))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out.read_text(encoding="utf-8"), proc.stdout)

    def test_lowercase_outcomes_do_not_read_green(self) -> None:
        self.execute("UPDATE work_results SET test_outcome=lower(test_outcome)")
        proc = run_status(str(self.db), "cell")
        self.assert_red(proc, "killed")

    def test_garbage_sqlite(self) -> None:
        self.db.write_bytes(b"not a database at all")
        self.assert_red(run_status(str(self.db), "cell"), "")

    def test_missing_sqlite(self) -> None:
        proc = run_status(str(self.tmp / "absent.sqlite"), "cell")
        self.assert_red(proc, "")
        self.assertFalse((self.tmp / "absent.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
