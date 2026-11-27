"""Standing canary for the PR test-weakening check (spec R18).

Each directory under `tests/fixtures/mutation_weakening/` is a base/head pair over a
one-mutant module (`sq.py`: `ok()` returns True, so cosmic-ray's only mutant is
`ReplaceTrueWithFalse`). The base test kills that mutant; the head test does not. The
test builds a throwaway repo laid out like a sub-project named `sq` (the Makefile and
scripts come from `git archive HEAD`, so a peer's uncommitted edit is not tested),
commits the base test and then the head test, and runs the real entry point
`make -C sq mutants-weakening BASE=<sha> JOB=<operator>@<occurrence>`. Each case must
report `weakened: 1` naming the operator and occurrence in its `expected.txt`.

Skips, with a printed reason, when cosmic-ray is not importable; under CI=true that is a
failure. The tracked fixtures are never written: tearDown re-hashes them and checks that
no process started by the case is still alive.
"""

import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "mutation_weakening"
CASES = ("drop", "mask", "raises", "raises_cm")
TIMEOUT_S = 900
GIT_ENV_UNSET = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
IN_CI = os.environ.get("CI") == "true"
HAVE_COSMIC_RAY = importlib.util.find_spec("cosmic_ray") is not None
SKIP_REASON = "cosmic_ray is not importable; the canary needs the real cosmic-ray"
SQ_FROM_REPO = ("Makefile", "mutants-equivalent.toml")


def clean_env(home: Path) -> dict[str, str]:
    """Environment for every child: no inherited git or GitHub state, HOME inside the fixture."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in GIT_ENV_UNSET and not k.startswith("GITHUB_")
    }
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env["HOME"] = str(home)
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


def fixture_digests() -> dict[str, str]:
    """sha256 of every file under the fixture directory."""
    return {
        str(p.relative_to(FIXTURES)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(FIXTURES.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
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


def build_repo(root: Path, case: str, env: dict[str, str]) -> tuple[Path, str]:
    """A repo with the base commit then the head commit of `case`; returns (repo, base sha)."""
    repo = root / "repo"
    (repo / "sq").mkdir(parents=True)
    archive = subprocess.run(
        ["git", "archive", "HEAD", "scripts"] + [f"sq/{name}" for name in SQ_FROM_REPO],
        cwd=REPO_ROOT,
        env={k: v for k, v in os.environ.items() if k not in GIT_ENV_UNSET},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=TIMEOUT_S,
        check=True,
    )
    subprocess.run(
        ["tar", "-x", "-C", str(repo)],
        input=archive.stdout,
        capture_output=True,
        timeout=TIMEOUT_S,
        check=True,
    )
    src = FIXTURES / case
    for name in ("sq.py", "cosmic-ray.toml"):
        (repo / "sq" / name).write_bytes((src / name).read_bytes())
    (repo / ".gitignore").write_text(".mutants-tmp/\n__pycache__/\n*.sqlite\n")

    def git(*args: str) -> str:
        result = run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], repo, env
        )
        if result.returncode != 0:
            raise AssertionError(f"git {args} failed: {result.stderr}")
        return result.stdout.strip()

    git("init", "-q")
    (repo / "sq" / "test_sq.py").write_bytes((src / "test_sq_base.py").read_bytes())
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = git("rev-parse", "HEAD")
    (repo / "sq" / "test_sq.py").write_bytes((src / "test_sq_head.py").read_bytes())
    git("add", "-A")
    git("commit", "-q", "-m", "head")
    return repo, base


@unittest.skipUnless(HAVE_COSMIC_RAY or IN_CI, SKIP_REASON)
class WeakeningCanary(unittest.TestCase):
    def setUp(self) -> None:
        if not HAVE_COSMIC_RAY:
            raise AssertionError(f"{SKIP_REASON}; CI=true requires it")
        self.before = fixture_digests()
        self.markers: list[str] = []

    def tearDown(self) -> None:
        self.assertEqual(
            fixture_digests(), self.before, "a case wrote a tracked fixture"
        )
        for marker in self.markers:
            self.assertEqual(live_processes(marker), [])

    def check_case(self, case: str) -> None:
        job = (FIXTURES / case / "expected.txt").read_text().strip()
        operator, _, occurrence = job.partition("@")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            env = clean_env(home)
            repo, base = build_repo(root, case, env)
            self.markers = [f"BASE={base}", str(root)]
            result = run(
                ["make", "-C", "sq", "mutants-weakening", f"BASE={base}", f"JOB={job}"],
                repo,
                env,
            )
        out = result.stdout
        detail = f"stdout:\n{out[-2000:]}\nstderr:\n{result.stderr[-2000:]}"
        self.assertIn(
            "weakened: 1 mutants killed by base tests survive head tests", out, detail
        )
        self.assertIn(f"  operator: {operator}", out, detail)
        self.assertIn(f"  occurrence: {occurrence}", out, detail)

    def test_drop(self) -> None:
        self.check_case("drop")

    def test_mask(self) -> None:
        self.check_case("mask")

    def test_raises(self) -> None:
        self.check_case("raises")

    def test_raises_cm(self) -> None:
        self.check_case("raises_cm")


if __name__ == "__main__":
    unittest.main()
