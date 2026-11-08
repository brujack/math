"""scripts/cosmic_ray_prune.py is a vendored copy of ai-config's script.

Line 2 of the vendored file pins the ai-config commit it was copied from. This
test reads that sha, fetches the canonical file at that commit, and requires
every other line to match, so a local edit to the vendored copy fails here. When
ai-config's master has moved past the pin the test only warns: re-syncing is a
deliberate act, not a reason to turn math's CI red.
"""

import os
import pathlib
import re
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
VENDORED = REPO_ROOT / "scripts" / "cosmic_ray_prune.py"
AI_CONFIG = pathlib.Path("~/git-repos/personal/ai-config").expanduser()
CANONICAL_PATH = ".claude/scripts/cosmic_ray_prune.py"
LINE2 = re.compile(
    r"^# Vendored from ai-config \.claude/scripts/cosmic_ray_prune\.py"
    r" @ (?P<sha>[0-9a-f]{12})\. Edit there, re-sync here\.$"
)
_GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


def _git_show(rev: str) -> str | None:
    """Return the canonical file at `rev` in the ai-config checkout, or None."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_VARS}
    result = subprocess.run(
        ["git", "-C", str(AI_CONFIG), "show", f"{rev}:{CANONICAL_PATH}"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return None
    return result.stdout


class VendoredPruneTest(unittest.TestCase):
    def test_vendored_copy_matches_pinned_canonical(self) -> None:
        local_lines = VENDORED.read_text().splitlines()
        self.assertGreaterEqual(len(local_lines), 2, "vendored file too short")
        match = LINE2.match(local_lines[1])
        self.assertIsNotNone(
            match, f"line 2 is not the vendoring header: {local_lines[1]!r}"
        )
        assert match is not None
        sha = match.group("sha")

        if not AI_CONFIG.is_dir():
            self.skipTest(f"ai-config checkout absent: {AI_CONFIG}")
        pinned = _git_show(sha)
        if pinned is None:
            self.skipTest(f"sha {sha} not present in {AI_CONFIG}")
        assert pinned is not None

        canonical_lines = pinned.splitlines()
        self.assertEqual(len(local_lines), len(canonical_lines), "line count differs")
        for number, (local, canon) in enumerate(
            zip(local_lines, canonical_lines, strict=True), start=1
        ):
            if number == 2:
                continue
            self.assertEqual(local, canon, f"line {number} differs from {sha}")

        latest = _git_show("origin/master")
        if latest is not None and latest != pinned:
            print(
                f"re-sync warning: ai-config origin/master copy of {CANONICAL_PATH}"
                f" differs from pinned {sha}",
                file=sys.stderr,
            )

    def test_line2_pattern_rejects_malformed_headers(self) -> None:
        bad = [
            "# Canonical copy. Vendored by: math/scripts/cosmic_ray_prune.py.",
            "# Vendored from ai-config .claude/scripts/cosmic_ray_prune.py @ 9b588ce. Edit there, re-sync here.",
            "# Vendored from ai-config .claude/scripts/cosmic_ray_prune.py @ 9B588CE3F4FB. Edit there, re-sync here.",
            "",
        ]
        for line in bad:
            self.assertIsNone(LINE2.match(line), line)
        good = (
            "# Vendored from ai-config .claude/scripts/cosmic_ray_prune.py"
            " @ 9b588ce3f4fb. Edit there, re-sync here."
        )
        self.assertIsNotNone(LINE2.match(good))


if __name__ == "__main__":
    unittest.main()
