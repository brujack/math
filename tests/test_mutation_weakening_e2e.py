"""End-to-end tests of the PR test-weakening check on a copy of sq/ (spec R33).

Each case builds a throwaway git repo (a base commit and a head commit) from a copy of
`sq/` and `scripts/`, then runs the real entry point `make -C sq mutants-weakening
BASE=<sha> JOB=<operator>@<occurrence>` with the real cosmic-ray and base runner. The
tests under judgement are small purpose-built files over `generate_squares`, so one mutant
(on the `k = 1` line, which only the full-list assertion kills) decides each
case and runtime stays bounded. `setUpClass` finds that mutant by a real whole-module run
rather than naming it.

Exceptions to the single entry point, each stated in its test: R16 is enforced by the
`mutants-diff` path, not by `mutants-weakening`, so that case runs the documented
plan, `mutants-diff` and verdict steps; a replay forced to `no-test` needs a module that
differs between the head session and the replay, so it runs `judge` and `replay` directly
on a session it builds itself.

Skips, with a printed reason, when cosmic-ray is not importable; under CI=true that is a
failure. Tracked `sq/` is never written: tearDown re-hashes it and checks that no process
started by the case is still alive.
"""

import hashlib
import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMEOUT_S = 900
GIT_ENV_UNSET = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
IN_CI = os.environ.get("CI") == "true"
HAVE_COSMIC_RAY = importlib.util.find_spec("cosmic_ray") is not None
SKIP_REASON = (
    "cosmic_ray is not importable; the weakening cases need the real cosmic-ray"
)
SQ_FILES = ("Makefile", "sq.py", "cosmic-ray.toml", "mutants-equivalent.toml")
FULL_LIST = "[(1, 1), (4, 2), (9, 3)]"

# --- the tests under judgement -------------------------------------------------------
HEADER = "import unittest\n\nimport sq\n\n\nclass TestSq(unittest.TestCase):\n"
SMOKE = "        self.assertEqual(sq.SMOKE_SIZE, 1)\n"
KILLER = f"        self.assertEqual(list(sq.generate_squares(1)), {FULL_LIST})\n"


def suite(*bodies: str, header: str = HEADER) -> str:
    """A test file whose single test method has the given statement lines."""
    return header + "    def test_squares(self):\n" + "".join(bodies)


BASE_FULL = suite(SMOKE, KILLER)
HEAD_WITHOUT_KILLER = suite(SMOKE)
HYPOTHESIS_HEADER = (
    "import unittest\n\nfrom hypothesis import given, strategies as st\n\nimport sq\n\n\n"
    "class TestSq(unittest.TestCase):\n"
    "    def test_smoke(self):\n        self.assertEqual(sq.SMOKE_SIZE, 1)\n\n"
)
GIVEN_BASE = (
    HYPOTHESIS_HEADER
    + "    @given(st.integers(min_value=0, max_value=1))\n"
    + "    def test_count(self, n):\n"
    + "        squares = list(sq.generate_squares(n))\n"
    + "        self.assertLessEqual(len(squares), 3)\n"
    + "        self.assertTrue(all(s == r * r for s, r in squares))\n"
)
GIVEN_HEAD = (
    HYPOTHESIS_HEADER
    + "    @given(st.integers(min_value=0, max_value=1))\n"
    + "    def test_count(self, n):\n"
    + "        # cosmetic edit: renamed local, comment, blank lines\n\n"
    + "        produced = list(sq.generate_squares(n))\n\n"
    + "        self.assertLessEqual(len(produced), 3)\n"
    + "        self.assertTrue(all(s == r * r for s, r in produced))\n"
)


# --- process and file plumbing -------------------------------------------------------
def clean_env(home: Path) -> dict[str, str]:
    """Environment for every child: no inherited git or GitHub state, HOME and XDG inside the fixture."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in GIT_ENV_UNSET and not k.startswith("GITHUB_")
    }
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    env["XDG_STATE_HOME"] = str(home / ".local" / "state")
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def run(
    args: list[str], cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )


def tracked_sq_digests() -> dict[str, str]:
    """sha256 of every tracked file under the real sq/."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_UNSET}
    listing = subprocess.run(
        ["git", "ls-files", "-z", "sq"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        check=True,
    ).stdout.decode()
    return {
        name: hashlib.sha256((REPO_ROOT / name).read_bytes()).hexdigest()
        for name in listing.split("\0")
        if name
    }


def live_processes(marker: str) -> list[str]:
    """`ps` lines naming `marker`, other than the ps call itself."""
    listing = subprocess.run(
        ["ps", "-eo", "pid=,args="], capture_output=True, text=True, check=True
    ).stdout
    return [
        line.strip()
        for line in listing.splitlines()
        if marker in line and "ps -eo" not in line
    ]


class Scenario:
    """A throwaway repo: base commit, head commit, and the commands to run on it."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo = root / "repo"
        self.home = root / "home"
        self.home.mkdir()
        self.env = clean_env(self.home)
        self.repo.mkdir()
        self.extract_head()
        (self.repo / ".gitignore").write_text(".mutants-tmp/\n__pycache__/\n*.sqlite\n")
        self.base = ""

    def extract_head(self) -> None:
        """scripts/ and the sq/ files the Makefile needs, as committed at HEAD (a peer's
        uncommitted edit to the working tree is not part of what is tested)."""
        paths = ["scripts"] + [f"sq/{name}" for name in SQ_FILES]
        archive = subprocess.run(
            ["git", "archive", "HEAD", *paths],
            cwd=REPO_ROOT,
            env={k: v for k, v in os.environ.items() if k not in GIT_ENV_UNSET},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=True,
        )
        subprocess.run(
            ["tar", "-x", "-C", str(self.repo)],
            input=archive.stdout,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=True,
        )

    @property
    def sq(self) -> Path:
        return self.repo / "sq"

    def git(self, *args: str) -> str:
        result = run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            self.repo,
            self.env,
        )
        if result.returncode != 0:
            raise AssertionError(f"git {args} failed: {result.stderr}")
        return result.stdout.strip()

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def build(
        self,
        base_test: str,
        head_test: str,
        head_sq: str | None = None,
        toml_timeout: int | None = None,
        base_sq: str | None = None,
    ) -> None:
        """Commit the base (`base_test`), then the head (`head_test`, optionally another sq.py)."""
        self.git("init", "-q")
        if toml_timeout is not None:
            toml = self.sq / "cosmic-ray.toml"
            text = toml.read_text()
            self.must_replace(text, "timeout = 60.0", f"timeout = {toml_timeout}.0")
            toml.write_text(
                text.replace("timeout = 60.0", f"timeout = {toml_timeout}.0")
            )
        if base_sq is not None:
            (self.sq / "sq.py").write_text(base_sq)
        (self.sq / "test_sq.py").write_text(base_test)
        self.base = self.commit("base")
        (self.sq / "test_sq.py").write_text(head_test)
        if head_sq is not None:
            (self.sq / "sq.py").write_text(head_sq)
        self.commit("head")

    @staticmethod
    def must_replace(text: str, old: str, new: str) -> None:
        if old not in text or old == new:
            raise AssertionError(
                f"fixture edit {old!r} -> {new!r} would not change anything"
            )

    def weakening(
        self, job: str | None = None, **extra: str
    ) -> subprocess.CompletedProcess[str]:
        args = ["make", "-C", "sq", "mutants-weakening", f"BASE={self.base}"]
        args.append(f"JOB={job}" if job else "MUTANT_SHARD=0/1")
        args.extend(f"{key}={value}" for key, value in extra.items())
        return run(args, self.repo, self.env)


# --- the cases -----------------------------------------------------------------------
@unittest.skipUnless(HAVE_COSMIC_RAY or IN_CI, SKIP_REASON)
class WeakeningE2E(unittest.TestCase):
    target_job = ""

    @classmethod
    def candidate_jobs(cls, scenario: Scenario, line: str = "    k = 1") -> list[str]:
        """Mutants on `line` of sq.py, from a real `cosmic-ray init` of the module."""
        lines = (scenario.sq / "sq.py").read_text().splitlines()
        row = lines.index(line) + 1
        env = {**scenario.env, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
        session = scenario.root / "candidates.sqlite"
        init = run(
            ["cosmic-ray", "init", "cosmic-ray.toml", str(session)], scenario.sq, env
        )
        if init.returncode != 0:
            raise AssertionError("cosmic-ray init failed: " + init.stderr[-2000:])
        with sqlite3.connect(session) as db:
            rows = db.execute(
                "SELECT operator_name, occurrence FROM mutation_specs "
                "WHERE start_pos_row = ? ORDER BY occurrence",
                (row,),
            ).fetchall()
        session.unlink()
        return [f"{operator}@{occurrence}" for operator, occurrence in rows]

    @classmethod
    def setUpClass(cls) -> None:
        if not HAVE_COSMIC_RAY:
            raise AssertionError(f"{SKIP_REASON}; CI=true requires it")
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Scenario(Path(tmp))
            scenario.build(BASE_FULL, HEAD_WITHOUT_KILLER)
            tried = []
            for job in cls.candidate_jobs(scenario):
                result = scenario.weakening(job)
                tried.append(result.stdout[-600:] + result.stderr[-600:])
                if (
                    result.returncode != 0
                    and "weakened: 1 mutants killed" in result.stdout
                    and f"JOB={job}" in result.stdout
                ):
                    cls.target_job = job
                    return
        raise AssertionError(
            "no `k = 1` mutant is weakened by dropping the killer assertion:\n"
            + "\n".join(tried)
        )

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.sc = Scenario(self.root)
        self.marker = str(self.root)
        self.before = tracked_sq_digests()

    def tearDown(self) -> None:
        self.assertEqual(tracked_sq_digests(), self.before, "tracked sq/ changed")
        deadline = time.monotonic() + 10
        alive = live_processes(self.marker)
        while alive and time.monotonic() < deadline:
            time.sleep(0.5)
            alive = live_processes(self.marker)
        self.assertEqual(alive, [], "a process started by the case survived")

    # --- helpers ---
    def out(self, result: subprocess.CompletedProcess[str]) -> str:
        return result.stdout + "\n--- stderr ---\n" + result.stderr[-2500:]

    def assert_weakened_one(self, result: subprocess.CompletedProcess[str]) -> None:
        text = self.out(result)
        self.assertNotEqual(result.returncode, 0, text)
        self.assertIn(
            "weakened: 1 mutants killed by base tests survive head tests", text
        )
        self.assertIn(f"JOB={self.target_job}", text)

    def assert_not_weakened(self, result: subprocess.CompletedProcess[str]) -> None:
        """Green, with no weakened line: a head survivor on an unchanged line is not red."""
        text = self.out(result)
        self.assertNotIn("weakened:", text)
        self.assertNotIn("replay failed", text)
        self.assertNotIn("unjudgeable", text)
        self.assertNotIn("shard incomplete", text)
        self.assertIn("base suite judgeable", text)
        self.assertEqual(result.returncode, 0, text)

    def assert_unjudgeable(self, result: subprocess.CompletedProcess[str]) -> None:
        text = self.out(result)
        self.assertIn("base suite unjudgeable", text)
        self.assertNotEqual(result.returncode, 0, text)

    def case(self, base: str, head: str, **kwargs: str | int | None) -> None:
        self.sc.build(base, head, **kwargs)  # type: ignore[arg-type]

    def judge(self) -> subprocess.CompletedProcess[str]:
        return self.sc.weakening(self.target_job)

    # --- R33 clauses ---
    def test_dropped_assertion_reports_weakened_one(self) -> None:
        """Dropping an assertion that alone kills a known mutant reports it under `weakened: 1`."""
        self.case(BASE_FULL, HEAD_WITHOUT_KILLER)
        self.assert_weakened_one(self.judge())

    def test_only_adding_a_test_is_not_weakened(self) -> None:
        """Only adding a test reports `weakened: 0`."""
        head = (
            BASE_FULL
            + "\n    def test_extra(self):\n        self.assertEqual(sq.SMOKE_SIZE, 1)\n"
        )
        self.case(BASE_FULL, head)
        self.assert_not_weakened(self.judge())

    def test_cosmetic_given_edit_is_not_weakened(self) -> None:
        """A cosmetic edit to every `@given` body reports `weakened: 0`."""
        self.case(GIVEN_BASE, GIVEN_HEAD)
        self.assert_not_weakened(self.judge())

    def test_obsolete_first_assertion_then_deleted_later_assertion(self) -> None:
        """An obsolete first assertion followed by a deleted later assertion reports the later assertion's mutant."""
        base = suite("        self.assertEqual(sq.SMOKE_SIZE, 2)\n", KILLER)
        self.case(base, HEAD_WITHOUT_KILLER)
        self.assert_weakened_one(self.judge())

    def test_failing_assert_raises_block_then_deleted_later_assertion(self) -> None:
        """A failing `with self.assertRaises` block followed by a deleted later assertion reports the later assertion's mutant."""
        base = suite(
            "        with self.assertRaises(ValueError):\n"
            "            self.assertEqual(sq.SMOKE_SIZE, 1)\n",
            KILLER,
        )
        self.case(base, HEAD_WITHOUT_KILLER)
        self.assert_weakened_one(self.judge())

    def test_attribute_error_in_first_assertion_still_reports_later_kill(self) -> None:
        """A base test whose first assertion raises `AttributeError` on the head module still reports a mutant that only a later assertion kills."""
        base = suite("        self.assertEqual(sq.removed_name, 1)\n", KILLER)
        self.case(base, HEAD_WITHOUT_KILLER)
        self.assert_weakened_one(self.judge())

    def test_subtest_failure_counts_as_a_kill(self) -> None:
        """A `subTest` failure under a mutant counts as a kill."""
        base = suite(
            SMOKE,
            "        for n in (1,):\n"
            "            with self.subTest(n=n):\n"
            f"                self.assertEqual(list(sq.generate_squares(n)), {FULL_LIST})\n",
        )
        self.case(base, HEAD_WITHOUT_KILLER)
        self.assert_weakened_one(self.judge())

    def test_loop_assertion_already_failing_on_one_iteration_still_kills(self) -> None:
        """A loop assertion that already fails on one iteration still kills a mutant that breaks another iteration."""
        base = suite(
            SMOKE,
            f"        for n, want in ((0, [(1, 1)]), (1, {FULL_LIST})):\n"
            "            self.assertEqual(list(sq.generate_squares(n)), want)\n",
        )
        self.case(base, HEAD_WITHOUT_KILLER)
        self.assert_weakened_one(self.judge())

    def test_failing_assert_raises_as_cm_does_not_mask_later_assertions(self) -> None:
        """A failing `with self.assertRaises(...) as cm` block does not mask later assertions on `cm.exception`."""
        base = suite(
            "        with self.assertRaises(ValueError) as cm:\n"
            "            self.assertEqual(sq.SMOKE_SIZE, 1)\n"
            '        self.assertEqual(str(cm.exception), "never")\n',
            KILLER,
        )
        self.case(base, HEAD_WITHOUT_KILLER)
        self.assert_weakened_one(self.judge())

    def test_message_only_change_on_already_failing_assertion_is_not_weakened(
        self,
    ) -> None:
        """A behaviour change with its test updated, plus a mutant on an unchanged line that only changes the message of an already-failing assertion, reports `weakened: 0`."""
        base_sq = (REPO_ROOT / "sq" / "sq.py").read_text()
        head_sq = base_sq.replace("yield k * k, k", "yield k, k * k")
        Scenario.must_replace(base_sq, "yield k * k, k", "yield k, k * k")
        head = suite(
            SMOKE, "        self.assertEqual(next(sq.generate_squares(1)), (1, 1))\n"
        )
        self.case(BASE_FULL, head, head_sq=head_sq)
        self.assert_not_weakened(self.judge())

    def test_import_breaking_rename_is_unjudgeable(self) -> None:
        """An import-breaking rename is red with `base suite unjudgeable` and leaves no process running."""
        base_test = "from sq import generate_squares\n" + BASE_FULL
        base_sq = (REPO_ROOT / "sq" / "sq.py").read_text()
        head_sq = base_sq.replace("def generate_squares", "def generate_squares_v2")
        Scenario.must_replace(
            base_sq, "def generate_squares", "def generate_squares_v2"
        )
        head = HEAD_WITHOUT_KILLER.replace("generate_squares", "generate_squares_v2")
        self.case(base_test, head, head_sq=head_sq)
        self.assert_unjudgeable(self.judge())

    def test_setup_error_is_unjudgeable(self) -> None:
        """A per-test `setUp` error is red with `base suite unjudgeable` and leaves no process running."""
        base_test = HEADER + (
            "    def setUp(self):\n        self.helper = sq.removed_helper\n\n"
            "    def test_squares(self):\n" + SMOKE + KILLER
        )
        self.case(base_test, HEAD_WITHOUT_KILLER)
        self.assert_unjudgeable(self.judge())

    def test_sleeping_base_test_is_unjudgeable(self) -> None:
        """A base test sleeping past the timeout is red with `base suite unjudgeable` and leaves no process running."""
        base_test = (
            "import time\n\n" + HEADER + "    def test_squares(self):\n"
            "        time.sleep(120)\n" + SMOKE
        )
        self.case(base_test, HEAD_WITHOUT_KILLER, toml_timeout=5)
        started = time.monotonic()
        self.assert_unjudgeable(self.judge())
        self.assertLess(time.monotonic() - started, 100, "the sleep was waited out")

    def test_untested_added_line_is_red_under_r16(self) -> None:
        """An untested line added to `sq.py` with a test-file change is red under R16."""
        base_sq = (REPO_ROOT / "sq" / "sq.py").read_text()
        needle = "    limit = 10**max_digits\n"
        added = "    if max_digits == 123457:"
        Scenario.must_replace(base_sq, needle, needle + added)
        head_sq = base_sq.replace(needle, needle + added + "\n        return\n")
        head = (
            BASE_FULL
            + "\n    def test_extra(self):\n        self.assertEqual(sq.SMOKE_SIZE, 1)\n"
        )
        self.case(BASE_FULL, head, head_sq=head_sq)
        # A number change on the guard's literal cannot be seen by any test, unlike `==` -> `!=`.
        jobs = [
            job
            for job in self.candidate_jobs(self.sc, added)
            if job.startswith("core/NumberReplacer@")
        ]
        self.assertTrue(jobs, "no number mutant on the added line")
        result = self.sc.weakening(jobs[0])
        text = self.out(result)
        self.assertNotEqual(result.returncode, 0, text)
        self.assertIn("red: sq", text)
        self.assertRegex(text, r"sq\.py:[0-9]+ col [0-9]+ \S+ function")

    def test_replay_forced_to_no_test_is_red(self) -> None:
        """A replay forced to `no-test` is red with `replay failed`.

        The head session and the replay of `mutants-weakening` read the same module, so
        the fault is injected by running `judge` and `replay` directly: the replay copy
        lacks the occurrence the head session mutated.
        """
        self.case(BASE_FULL, HEAD_WITHOUT_KILLER)
        work = self.root / "work"
        head_copy = work / "head" / "sq"
        replay_copy = work / "replay" / "sq"
        for copy in (head_copy, replay_copy):
            copy.mkdir(parents=True)
            for name in ("sq.py", "test_sq.py", "cosmic-ray.toml"):
                shutil.copy(self.sc.sq / name, copy / name)
        session = work / "head.sqlite"
        env = {**self.sc.env, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
        init = run(
            ["cosmic-ray", "init", "cosmic-ray.toml", str(session)], head_copy, env
        )
        self.assertEqual(init.returncode, 0, self.out(init))
        operator, occurrence = self.target_job.rsplit("@", 1)
        with sqlite3.connect(session) as db:
            keep = db.execute(
                "SELECT job_id FROM mutation_specs WHERE operator_name=? AND occurrence=?",
                (operator, int(occurrence)),
            ).fetchall()
            self.assertEqual(len(keep), 1)
            db.execute("DELETE FROM mutation_specs WHERE job_id != ?", (keep[0][0],))
            db.execute("DELETE FROM work_items WHERE job_id != ?", (keep[0][0],))
        executed = run(
            ["cosmic-ray", "exec", "cosmic-ray.toml", str(session)], head_copy, env
        )
        self.assertEqual(executed.returncode, 0, self.out(executed))
        script = str(self.sc.repo / "scripts" / "mutation_weakening.py")
        judged = run(
            [
                sys.executable,
                script,
                "judge",
                "--dir",
                str(replay_copy),
                "--base",
                self.sc.base,
                "--work",
                str(work / "w"),
                "--after-head",
                "--repo",
                str(self.sc.repo),
            ],
            replay_copy,
            env,
        )
        self.assertEqual(judged.returncode, 0, self.out(judged))
        # No numeric literal is left, so the session's NumberReplacer occurrence is absent.
        (replay_copy / "sq.py").write_text("SMOKE_SIZE = None\n")
        replayed = run(
            [
                sys.executable,
                script,
                "replay",
                "--dir",
                str(replay_copy),
                "--session",
                str(session),
                "--shard",
                "0/1",
                "--planned",
                "1",
                "--base",
                self.sc.base,
                "--work",
                str(work / "w"),
                "--repo",
                str(self.sc.repo),
            ],
            replay_copy,
            env,
        )
        self.assertEqual(replayed.returncode, 1, self.out(replayed))
        self.assertIn("replay failed: no-test", replayed.stdout)

    def test_shard_that_skips_a_job_is_incomplete(self) -> None:
        """A shard that skips a job is red with `shard incomplete`."""
        self.case(BASE_FULL, BASE_FULL + "\n# head\n")
        result = self.sc.weakening(self.target_job, PLANNED="2")
        text = self.out(result)
        self.assertNotEqual(result.returncode, 0, text)
        self.assertIn(
            "shard incomplete: ran 1 of 2 jobs, replayed 0 of 0 survivors", text
        )

    def test_planted_sitecustomize_does_not_replace_the_generated_one(self) -> None:
        """A `sitecustomize.py` placed in the sandbox does not replace the generated one."""
        self.case(BASE_FULL, HEAD_WITHOUT_KILLER)
        marker = self.root / "planted-ran"
        planted = f"open({str(marker)!r}, 'w').close()\n"
        for where in (self.sc.sq, self.sc.repo, self.sc.repo / "scripts"):
            (where / "sitecustomize.py").write_text(planted)
        self.assert_weakened_one(self.judge())
        self.assertFalse(marker.exists(), "the planted sitecustomize.py ran")

    def test_broken_profile_is_red(self) -> None:
        """A broken generated profile is red with `hypothesis profile not active`."""
        script = self.sc.repo / "scripts" / "mutation_hypothesis_profile.py"
        text = script.read_text()
        patch = "hypothesis.core.function_digest = _name_keyed_digest"
        Scenario.must_replace(text, patch, "pass")
        script.write_text(text.replace(patch, "pass"))
        self.case(BASE_FULL, HEAD_WITHOUT_KILLER)
        result = self.judge()
        text = self.out(result)
        self.assertNotEqual(result.returncode, 0, text)
        self.assertIn("hypothesis profile not active", text)
        self.assertNotIn("weakened:", text)


if __name__ == "__main__":
    unittest.main()
