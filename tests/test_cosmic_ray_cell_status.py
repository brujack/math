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
FIRST_JOB = "(SELECT min(job_id) FROM work_results)"

# Pinned from the committed fixture (a real `cosmic-ray exec` of crfix.py).
GREEN_LINE = f"green: cell {DASH} 13 surviving, 1 timed out, 23 jobs\n"
SURVIVORS = (
    "crfix.py:5 core/NumberReplacer\n"
    "crfix.py:5 core/NumberReplacer\n"
    "crfix.py:5 core/ReplaceBinaryOperator_Add_BitAnd\n"
    "crfix.py:5 core/ReplaceBinaryOperator_Add_BitOr\n"
    "crfix.py:5 core/ReplaceBinaryOperator_Add_BitXor\n"
    "crfix.py:5 core/ReplaceBinaryOperator_Add_FloorDiv\n"
    "crfix.py:5 core/ReplaceBinaryOperator_Add_LShift\n"
    "crfix.py:5 core/ReplaceBinaryOperator_Add_Mod\n"
    "crfix.py:5 core/ReplaceBinaryOperator_Add_Mul\n"
    "crfix.py:5 core/ReplaceBinaryOperator_Add_Pow\n"
    "crfix.py:5 core/ReplaceBinaryOperator_Add_RShift\n"
    "crfix.py:5 core/ReplaceBinaryOperator_Add_Sub\n"
    "crfix.py:9 core/ReplaceComparisonOperator_Gt_NotEq\n"
)


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
        self.assertNotIn("green:", proc.stdout)
        self.assertTrue(needle, "needle must name the specific reason")
        self.assertIn(needle, proc.stdout)


class TestGreen(CellStatusTestCase):
    def test_fixture_has_survivors_and_timeouts(self) -> None:
        self.assertEqual(
            scalar(
                self.db,
                "SELECT count(*) FROM work_results WHERE test_outcome='SURVIVED'",
            ),
            13,
        )
        self.assertEqual(
            scalar(
                self.db,
                "SELECT count(*) FROM work_results "
                "WHERE test_outcome='KILLED' AND output='timeout'",
            ),
            1,
        )
        self.assertEqual(scalar(self.db, "SELECT count(*) FROM work_items"), 23)

    def test_exact_green_line(self) -> None:
        proc = run_status(str(self.db), "cell")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, GREEN_LINE)

    def test_out_file_equals_stdout(self) -> None:
        out = self.tmp / "status.txt"
        proc = run_status(str(self.db), "cell", "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out.read_text(encoding="utf-8"), proc.stdout)

    def test_survivors_file_exact_and_sorted(self) -> None:
        out = self.tmp / "survivors.txt"
        proc = run_status(str(self.db), "cell", "--survivors", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out.read_text(encoding="utf-8"), SURVIVORS)

    def test_timeouts_alone_are_not_red(self) -> None:
        self.execute(
            "UPDATE work_results SET test_outcome='KILLED' WHERE test_outcome='SURVIVED'"
        )
        proc = run_status(str(self.db), "cell")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("0 surviving, 1 timed out", proc.stdout)

    def test_session_path_with_uri_metacharacters(self) -> None:
        odd = self.tmp / "dir#with?odd%chars"
        odd.mkdir()
        db = odd / "session.sqlite"
        shutil.copyfile(FIXTURE, db)
        proc = run_status(str(db), "cell")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout, GREEN_LINE)

    def test_status_check_does_not_modify_session(self) -> None:
        before = self.db.read_bytes()
        run_status(str(self.db), "cell")
        self.assertEqual(self.db.read_bytes(), before)


class TestRed(CellStatusTestCase):
    def test_deleted_result_row(self) -> None:
        self.execute(f"DELETE FROM work_results WHERE job_id = {FIRST_JOB}")
        self.assert_red(
            run_status(str(self.db), "cell"), "1 work items without a result"
        )

    def test_orphan_result_replacing_a_deleted_one(self) -> None:
        # Count still equals K, but one item has no result and one result no item.
        self.execute(
            "INSERT INTO work_results (worker_outcome, output, test_outcome, diff, job_id) "
            "SELECT worker_outcome, output, test_outcome, diff, 'orphan-job' "
            f"FROM work_results WHERE job_id = {FIRST_JOB}"
        )
        self.execute(f"DELETE FROM work_results WHERE job_id = {FIRST_JOB}")
        self.assertEqual(
            scalar(self.db, "SELECT count(*) FROM work_results"),
            scalar(self.db, "SELECT count(*) FROM work_items"),
        )
        self.assert_red(run_status(str(self.db), "cell"), "without a result")

    def test_orphan_result_alone(self) -> None:
        self.execute(
            "INSERT INTO work_results (worker_outcome, output, test_outcome, diff, job_id) "
            "VALUES ('NORMAL', '', 'KILLED', '', 'orphan-job')"
        )
        self.assert_red(
            run_status(str(self.db), "cell"), "1 results without a work item"
        )

    def test_all_work_items_deleted(self) -> None:
        self.execute("DELETE FROM work_items")
        self.assert_red(run_status(str(self.db), "cell"), "no work items")

    def test_incompetent_outcome(self) -> None:
        self.execute(
            f"UPDATE work_results SET test_outcome='INCOMPETENT' WHERE job_id = {FIRST_JOB}"
        )
        self.assert_red(run_status(str(self.db), "cell"), "INCOMPETENT")

    def test_exception_worker_outcome(self) -> None:
        self.execute(
            f"UPDATE work_results SET worker_outcome='EXCEPTION' WHERE job_id = {FIRST_JOB}"
        )
        self.assert_red(run_status(str(self.db), "cell"), "EXCEPTION")

    def test_null_test_outcome(self) -> None:
        self.execute(
            f"UPDATE work_results SET test_outcome=NULL WHERE job_id = {FIRST_JOB}"
        )
        self.assert_red(run_status(str(self.db), "cell"), "NULL")

    def test_null_worker_outcome(self) -> None:
        self.execute(
            f"UPDATE work_results SET worker_outcome=NULL WHERE job_id = {FIRST_JOB}"
        )
        self.assert_red(run_status(str(self.db), "cell"), "NULL")

    def test_all_worker_outcomes_null(self) -> None:
        self.execute("UPDATE work_results SET worker_outcome=NULL")
        self.assert_red(run_status(str(self.db), "cell"), "NULL")

    def test_red_line_written_to_out(self) -> None:
        self.execute("DELETE FROM work_items")
        out = self.tmp / "status.txt"
        proc = run_status(str(self.db), "cell", "--out", str(out))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(out.read_text(encoding="utf-8"), proc.stdout)

    def test_red_cell_empties_stale_survivors_file(self) -> None:
        stale = self.tmp / "survivors.txt"
        stale.write_text("stale:1 old\n", encoding="utf-8")
        self.execute("DELETE FROM work_items")
        proc = run_status(str(self.db), "cell", "--survivors", str(stale))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(stale.read_text(encoding="utf-8"), "")

    def test_lowercase_outcomes_do_not_read_green(self) -> None:
        self.execute("UPDATE work_results SET test_outcome=lower(test_outcome)")
        proc = run_status(str(self.db), "cell")
        self.assert_red(proc, "NORMAL/killed")

    def test_garbage_sqlite(self) -> None:
        self.db.write_bytes(b"not a database at all")
        self.assert_red(run_status(str(self.db), "cell"), "unreadable session")

    def test_missing_sqlite(self) -> None:
        proc = run_status(str(self.tmp / "absent.sqlite"), "cell")
        self.assert_red(proc, "no such session file")
        self.assertFalse((self.tmp / "absent.sqlite").exists())

    def test_unwritable_out_never_prints_green(self) -> None:
        out = self.tmp / "missing-dir" / "status.txt"
        proc = run_status(str(self.db), "cell", "--out", str(out))
        self.assert_red(proc, "cannot write")

    def test_failed_survivors_write_leaves_out_untouched(self) -> None:
        out = self.tmp / "status.txt"
        out.write_text("previous\n", encoding="utf-8")
        bad = self.tmp / "missing-dir" / "survivors.txt"
        proc = run_status(
            str(self.db), "cell", "--out", str(out), "--survivors", str(bad)
        )
        self.assert_red(proc, "cannot write")
        self.assertEqual(out.read_text(encoding="utf-8"), "previous\n")
        self.assertEqual(
            sorted(p.name for p in self.tmp.iterdir()), ["session.sqlite", "status.txt"]
        )


if __name__ == "__main__":
    unittest.main()
