"""R26/R27: signed Mutation-Gate-Reviewed trailers, verified with git verify-commit."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "mutation_gate_clearance", ROOT / "scripts" / "mutation_gate_clearance.py"
)
assert _SPEC is not None and _SPEC.loader is not None
mgc: Any = importlib.util.module_from_spec(_SPEC)
sys.modules["mutation_gate_clearance"] = mgc
_SPEC.loader.exec_module(mgc)

REASON = "reviewed the weakening by hand"


class RepoCase(unittest.TestCase):
    """A throwaway repo, home and keys; the real config and keys are never touched."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        env = {
            "HOME": str(self.tmp / "home"),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
        (self.tmp / "home").mkdir()
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "master")
        self.key = self.make_key("good")
        self.other_key = self.make_key("other")
        self.signers = self.tmp / "signers"
        self.signers.write_text(f'test@x namespaces="git" {self.pub(self.key)}\n')
        self.write("README", "x\n")
        self.commit("base")
        self.base = self.rev("HEAD")

    def git(self, *args: str, key: Path | None = None, sign: bool = False) -> str:
        cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        if sign and key is not None:
            cmd += ["-c", "gpg.format=ssh", "-c", f"user.signingkey={key}.pub"]
        cmd += list(args)
        result = subprocess.run(
            cmd,
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
        )
        return result.stdout.strip()

    def make_key(self, name: str) -> Path:
        path = self.tmp / name
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)],
            check=True,
            stdin=subprocess.DEVNULL,
        )
        return path

    @staticmethod
    def pub(key: Path) -> str:
        return Path(f"{key}.pub").read_text().strip()

    def write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def rev(self, ref: str) -> str:
        return self.git("rev-parse", ref)

    def commit(self, *messages: str, key: Path | None = None) -> str:
        self.git("add", "-A")
        args = ["commit", "-q", "--allow-empty"]
        for message in messages:
            args += ["-m", message]
        if key is not None:
            args.append("-S")
        self.git(*args, key=key, sign=key is not None)
        return self.rev("HEAD")

    def trailer(self, pr: int, target: str, reason: str = REASON) -> str:
        return f"Mutation-Gate-Reviewed: #{pr} {target}: {reason}"

    def collect(self, pr: int = 7) -> tuple[list[Any], list[str]]:
        return mgc.trailers(self.repo, self.base, "HEAD", pr, self.signers)


class TrailersTest(RepoCase):
    def test_valid_trailer_clears_its_target(self) -> None:
        sha = self.commit("review", self.trailer(7, "pi"), key=self.key)
        found, ignored = self.collect()
        self.assertEqual(found, [mgc.Clearance(sha, "pi", REASON)])
        self.assertEqual(ignored, [])

    def test_unsigned_commit_is_ignored(self) -> None:
        sha = self.commit("review", self.trailer(7, "pi"))
        found, ignored = self.collect()
        self.assertEqual(found, [])
        self.assertEqual(ignored, [f"trailer ignored: {sha}: unsigned"])

    def test_key_not_in_signers_file_is_not_accepted(self) -> None:
        sha = self.commit("review", self.trailer(7, "pi"), key=self.other_key)
        found, ignored = self.collect()
        self.assertEqual(found, [])
        self.assertEqual(ignored, [f"trailer ignored: {sha}: signature not accepted"])

    def test_another_prs_number_is_ignored(self) -> None:
        sha = self.commit("review", self.trailer(8, "pi"), key=self.key)
        found, ignored = self.collect()
        self.assertEqual(found, [])
        self.assertEqual(ignored, [f"trailer ignored: {sha}: names #8"])

    def test_nine_character_reason_does_not_clear(self) -> None:
        self.commit("review", self.trailer(7, "pi", "123456789"), key=self.key)
        self.assertEqual(self.collect(), ([], []))

    def test_ten_character_reason_clears(self) -> None:
        sha = self.commit("review", self.trailer(7, "pi", "1234567890"), key=self.key)
        self.assertEqual(self.collect()[0], [mgc.Clearance(sha, "pi", "1234567890")])

    def test_two_lines_in_one_commit_clear_two_targets(self) -> None:
        sha = self.commit(
            "review",
            self.trailer(7, "pi") + "\n" + self.trailer(7, "gate"),
            key=self.key,
        )
        found, _ = self.collect()
        self.assertEqual({c.target for c in found}, {"pi", "gate"})
        self.assertEqual({c.sha for c in found}, {sha})

    def test_commit_without_trailer_is_silent(self) -> None:
        self.commit("plain", key=self.key)
        self.assertEqual(self.collect(), ([], []))

    def test_commits_outside_the_range_are_not_read(self) -> None:
        self.commit("review", self.trailer(7, "pi"), key=self.key)
        head = self.rev("HEAD")
        self.assertEqual(
            mgc.trailers(self.repo, head, "HEAD", 7, self.signers), ([], [])
        )

    def test_malformed_lines_are_skipped(self) -> None:
        for bad in (
            "Mutation-Gate-Reviewed: pi: " + REASON,
            "Mutation-Gate-Reviewed: #7 pi " + REASON,
        ):
            self.commit("review", bad, key=self.key)
        self.assertEqual(self.collect(), ([], []))


class VerifyTest(RepoCase):
    def test_verify_true_for_accepted_signature(self) -> None:
        sha = self.commit("s", key=self.key)
        self.assertTrue(mgc.verify(self.repo, sha, self.signers))

    def test_verify_false_for_unsigned_and_for_unknown_key(self) -> None:
        unsigned = self.commit("u")
        unknown = self.commit("k", key=self.other_key)
        self.assertFalse(mgc.verify(self.repo, unsigned, self.signers))
        self.assertFalse(mgc.verify(self.repo, unknown, self.signers))

    def test_empty_signers_file_fails_closed(self) -> None:
        sha = self.commit("s", key=self.key)
        empty = self.tmp / "empty"
        empty.write_text("# no keys\n")
        self.assertFalse(mgc.verify(self.repo, sha, empty))

    def test_git_env_vars_do_not_redirect_the_check(self) -> None:
        sha = self.commit("s", key=self.key)
        decoy = {
            "GIT_DIR": str(self.tmp / "nowhere"),
            "GIT_INDEX_FILE": str(self.tmp / "ix"),
        }
        with mock.patch.dict(os.environ, decoy):
            self.assertTrue(mgc.verify(self.repo, sha, self.signers))


class ClearedForDirTest(RepoCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("pi/pi.py", "a = 1\n")
        self.write("pi/test_pi.py", "b = 1\n")
        self.commit("add pi")
        self.base = self.rev("HEAD")

    def cleared(self, directory: str = "pi") -> str | None:
        return mgc.cleared_for_dir(
            self.repo, self.base, "HEAD", 7, directory, self.signers
        )

    def test_returns_clearing_sha_when_files_unchanged(self) -> None:
        sha = self.commit("review", self.trailer(7, "pi"), key=self.key)
        self.write("README", "later\n")
        self.commit("unrelated")
        self.assertEqual(self.cleared(), sha)

    def test_none_when_module_changed_after_clearance(self) -> None:
        self.commit("review", self.trailer(7, "pi"), key=self.key)
        self.write("pi/pi.py", "a = 2\n")
        self.commit("edit module")
        self.assertIsNone(self.cleared())

    def test_none_when_test_file_changed_after_clearance(self) -> None:
        self.commit("review", self.trailer(7, "pi"), key=self.key)
        self.write("pi/test_pi.py", "b = 2\n")
        self.commit("edit test")
        self.assertIsNone(self.cleared())

    def test_other_target_does_not_clear(self) -> None:
        self.commit("review", self.trailer(7, "fib"), key=self.key)
        self.assertIsNone(self.cleared())

    def test_latest_clearance_wins_when_earlier_one_is_stale(self) -> None:
        self.commit("first", self.trailer(7, "pi"), key=self.key)
        self.write("pi/pi.py", "a = 2\n")
        self.commit("edit module")
        later = self.commit("second", self.trailer(7, "pi"), key=self.key)
        self.assertEqual(self.cleared(), later)

    def test_dash_in_dir_name_maps_to_underscore_module(self) -> None:
        self.write("perfect-numbers/perfect_numbers.py", "a = 1\n")
        self.write("perfect-numbers/test_perfect_numbers.py", "b = 1\n")
        sha = self.commit("review", self.trailer(7, "perfect-numbers"), key=self.key)
        self.assertEqual(self.cleared("perfect-numbers"), sha)
        self.write("perfect-numbers/test_perfect_numbers.py", "b = 2\n")
        self.commit("edit")
        self.assertIsNone(self.cleared("perfect-numbers"))

    def test_none_without_any_trailer(self) -> None:
        self.assertIsNone(self.cleared())


class RemedyCommandTest(unittest.TestCase):
    def test_single_target_matches_r26(self) -> None:
        got = mgc.remedy_command(7, ["pi"], "AAAA")
        spec_block = (
            "git -c gpg.format=ssh -c user.signingkey='key::AAAA' \\\n"
            "  commit --allow-empty -S -m 'chore: mutation gate review' \\\n"
            "  -m 'Mutation-Gate-Reviewed: #7 pi: <reason>'\n"
        )
        self.assertTrue(got.startswith(spec_block))

    def test_one_m_per_target(self) -> None:
        got = mgc.remedy_command(7, ["pi", "gate"], "AAAA")
        self.assertEqual(got.count("-m 'Mutation-Gate-Reviewed:"), 2)
        self.assertIn("#7 gate: <reason>", got)

    def test_note_says_merge_not_rebase(self) -> None:
        got = mgc.remedy_command(7, ["pi"], "AAAA")
        self.assertIn("merge master", got)
        self.assertIn("rebase", got)


if __name__ == "__main__":
    unittest.main()
