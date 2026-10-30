"""Tests for scripts/cosmic_ray_shard.py, driven by real `cosmic-ray init` sessions.

Fixtures (tests/fixtures/cosmic_ray/fib-init-{a,b}.sqlite) are two independent
inits of fib/; their job_ids differ but their spec keys are identical.
Regenerate with tests/fixtures/cosmic_ray/regen.sh.
"""

import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cosmic_ray_shard.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "cosmic_ray"

SpecKey = tuple[str, str, str, int, int, int, int, int]
KEY_SQL = (
    "SELECT module_path, operator_name, operator_args, occurrence, "
    "start_pos_row, start_pos_col, end_pos_row, end_pos_col FROM mutation_specs"
)


def run_shard(path: pathlib.Path, k: str, n: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), k, n],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def keys(path: pathlib.Path) -> set[SpecKey]:
    with sqlite3.connect(path) as conn:
        return {tuple(r) for r in conn.execute(KEY_SQL)}  # type: ignore[misc]


def job_ids(path: pathlib.Path) -> tuple[set[str], set[str]]:
    with sqlite3.connect(path) as conn:
        specs = {r[0] for r in conn.execute("SELECT job_id FROM mutation_specs")}
        items = {r[0] for r in conn.execute("SELECT job_id FROM work_items")}
    return specs, items


class ShardTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)

    def copy(self, name: str, as_name: str | None = None) -> pathlib.Path:
        dest = self.tmp / (as_name or name)
        shutil.copy(FIXTURES / name, dest)
        return dest


class TestPartition(ShardTestCase):
    def shards(self, fixture: str, n: int) -> list[set[SpecKey]]:
        out = []
        for k in range(n):
            p = self.copy(fixture, f"{fixture}.{k}")
            r = run_shard(p, str(k), str(n))
            self.assertEqual(r.returncode, 0, r.stderr)
            out.append(keys(p))
        return out

    def test_n10_disjoint_and_union_is_full(self) -> None:
        full = keys(FIXTURES / "fib-init-a.sqlite")
        self.assertGreater(len(full), 10)
        parts = self.shards("fib-init-a.sqlite", 10)
        for i, a in enumerate(parts):
            self.assertTrue(a, f"shard {i} empty")
            for b in parts[i + 1 :]:
                self.assertFalse(a & b)
        self.assertEqual(set().union(*parts), full)
        self.assertEqual(sum(len(p) for p in parts), len(full))

    def test_sessions_a_and_b_partition_identically_with_different_ids(self) -> None:
        a = self.shards("fib-init-a.sqlite", 10)
        b = self.shards("fib-init-b.sqlite", 10)
        self.assertEqual(a, b)
        ids_a, _ = job_ids(FIXTURES / "fib-init-a.sqlite")
        ids_b, _ = job_ids(FIXTURES / "fib-init-b.sqlite")
        self.assertTrue(ids_a.isdisjoint(ids_b))

    def test_specs_and_work_items_stay_consistent(self) -> None:
        p = self.copy("fib-init-a.sqlite")
        self.assertEqual(run_shard(p, "3", "10").returncode, 0)
        specs, items = job_ids(p)
        self.assertEqual(specs, items)
        self.assertTrue(specs)

    def test_n1_keeps_everything(self) -> None:
        p = self.copy("fib-init-a.sqlite")
        total = len(keys(p))
        r = run_shard(p, "0", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), f"kept {total} of {total}")
        self.assertEqual(keys(p), keys(FIXTURES / "fib-init-a.sqlite"))

    def test_last_shard_boundary_and_stdout(self) -> None:
        p = self.copy("fib-init-a.sqlite")
        total = len(keys(p))
        r = run_shard(p, "9", "10")
        self.assertEqual(r.returncode, 0, r.stderr)
        expected = len(range(9, total, 10))
        self.assertEqual(r.stdout.strip(), f"kept {expected} of {total}")
        self.assertEqual(len(keys(p)), expected)

    def test_n_larger_than_total_leaves_high_shard_empty(self) -> None:
        p = self.copy("fib-init-a.sqlite")
        total = len(keys(p))
        r = run_shard(p, str(total), str(total + 1))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), f"kept 0 of {total}")


class TestErrors(ShardTestCase):
    def assert_fails_unchanged(self, path: pathlib.Path, k: str, n: str) -> None:
        before = path.read_bytes() if path.exists() else None
        r = run_shard(path, k, n)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(r.stderr.strip())
        after = path.read_bytes() if path.exists() else None
        self.assertEqual(before, after)

    def test_missing_file(self) -> None:
        missing = self.tmp / "nope.sqlite"
        self.assert_fails_unchanged(missing, "0", "10")
        self.assertFalse(missing.exists())

    def test_zero_work_items(self) -> None:
        p = self.tmp / "empty.sqlite"
        shutil.copy(FIXTURES / "fib-init-a.sqlite", p)
        with sqlite3.connect(p) as conn:
            conn.execute("DELETE FROM mutation_specs")
            conn.execute("DELETE FROM work_items")
        self.assert_fails_unchanged(p, "0", "10")

    def test_n_below_one(self) -> None:
        p = self.copy("fib-init-a.sqlite")
        self.assert_fails_unchanged(p, "0", "0")
        self.assert_fails_unchanged(p, "0", "-1")

    def test_k_out_of_range(self) -> None:
        p = self.copy("fib-init-a.sqlite")
        self.assert_fails_unchanged(p, "10", "10")
        self.assert_fails_unchanged(p, "-1", "10")

    def test_non_integer_args(self) -> None:
        p = self.copy("fib-init-a.sqlite")
        self.assert_fails_unchanged(p, "x", "10")
        self.assert_fails_unchanged(p, "0", "ten")
        self.assert_fails_unchanged(p, "1.5", "10")


if __name__ == "__main__":
    unittest.main()
