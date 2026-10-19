"""Behavioural tests for the auto-merge `hold` guard in .github/workflows/auto-merge.yml.

The guard's `run:` text is extracted from the workflow (no PyYAML) and executed
under `bash -e` against a stub `gh`, so the test exercises the shipped script
rather than a copy. Point BOTHOLD_WORKFLOW at an older workflow to confirm the
test fails against the pre-change guard.

This file uses its own `gh` stub instead of tests/mocks/gh because that mock
does not apply `--jq` and cannot tell the author call from the labels call
(both are `gh pr view`); the guard's behaviour depends on both.
"""

import json
import os
import re
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

WORKFLOW = os.environ.get("BOTHOLD_WORKFLOW", ".github/workflows/auto-merge.yml")

STUB_GH = """#!/usr/bin/env bash
if [ "${GH_FAIL:-}" = "1" ]; then
  exit 1
fi
if [ "${GH_FAIL_LABELS:-}" = "1" ]; then
  for a in "$@"; do
    if [ "$a" = "labels" ]; then
      exit 1
    fi
  done
fi
expr=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--jq" ]; then
    expr="$2"
    break
  fi
  shift
done
jq -r "${expr}" "${GH_FIXTURE}"
"""


def extract_hold_run(path):
    """Return the dedented `run: |` text of the step whose id is `hold`."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    id_idx = next(
        (i for i, ln in enumerate(lines) if re.match(r"^\s*(-\s+)?id:\s*hold\s*$", ln)),
        None,
    )
    assert id_idx is not None, "no `id: hold` step in " + path
    step_indent = len(lines[id_idx]) - len(lines[id_idx].lstrip())
    run_idx = None
    for i in range(id_idx + 1, len(lines)):
        ln = lines[i]
        if ln.strip() and not ln.lstrip().startswith("#"):
            indent = len(ln) - len(ln.lstrip())
            if indent < step_indent:
                break
            if indent == step_indent and re.match(r"^\s*run:\s*\|\s*$", ln):
                run_idx = i
                break
    assert run_idx is not None, "hold step has no `run: |` block"
    run_indent = len(lines[run_idx]) - len(lines[run_idx].lstrip())
    body = []
    for ln in lines[run_idx + 1 :]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= run_indent:
            break
        body.append(ln)
    text = textwrap.dedent("\n".join(body)).strip("\n")
    assert text.strip(), "hold step run block is empty"
    return text + "\n"


def run_guard(fixture, gh_fail=False, labels_fail=False):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        stub_dir = tmp_path / "bin"
        stub_dir.mkdir()
        gh = stub_dir / "gh"
        gh.write_text(STUB_GH)
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        fixture_file = tmp_path / "fixture.json"
        fixture_file.write_text(json.dumps(fixture))
        out_file = tmp_path / "github_output"
        out_file.write_text("")
        env = {
            "PATH": f"{stub_dir}:{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "PR_NUMBER": "1",
            "GH_TOKEN": "x",
            "GITHUB_TOKEN": "x",
            "GITHUB_OUTPUT": str(out_file),
            "GH_FIXTURE": str(fixture_file),
            "GH_FAIL": "1" if gh_fail else "0",
            "GH_FAIL_LABELS": "1" if labels_fail else "0",
        }
        proc = subprocess.run(
            ["bash", "-e", "-c", extract_hold_run(WORKFLOW)],
            env=env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        return proc.returncode, out_file.read_text()


def fx(is_bot, login, labels=()):
    return {
        "author": {"is_bot": is_bot, "login": login},
        "labels": [{"name": n} for n in labels],
    }


# (id, fixture, gh_fail, expected rc, expected GITHUB_OUTPUT)
CASES = [
    ("1-human-no-label", fx(False, "human"), False, 0, "merge=true\n"),
    (
        "2-renovate-labelled",
        fx(True, "app/renovate", ["automerge-ok"]),
        False,
        0,
        "merge=true\n",
    ),
    ("3-renovate-unlabelled", fx(True, "app/renovate"), False, 0, "merge=false\n"),
    ("4-dependabot-unlabelled", fx(True, "app/dependabot"), False, 0, "merge=false\n"),
    (
        "5-dependabot-labelled",
        fx(True, "app/dependabot", ["automerge-ok"]),
        False,
        0,
        "merge=true\n",
    ),
    ("6-empty-login", fx(True, ""), False, 1, ""),
    ("7-unreadable-is-bot", fx("maybe", "x"), False, 1, ""),
    ("8-gh-fails", fx(True, "app/renovate"), True, 1, ""),
    (
        "9-label-prefix-is-not-a-match",
        fx(True, "app/renovate", ["automerge-ok-pending"]),
        False,
        0,
        "merge=false\n",
    ),
    (
        "10-github-actions-unlabelled",
        fx(True, "app/github-actions"),
        False,
        0,
        "merge=false\n",
    ),
    # Real Renovate PRs carry `renovate` and `automerge-ok` (renovate.json
    # labels + addLabels). Single-label fixtures let a string-equality or a
    # position-dependent match pass while it holds every real Renovate PR.
    (
        "11-several-labels-automerge-ok-last",
        fx(True, "app/renovate", ["renovate", "automerge-ok"]),
        False,
        0,
        "merge=true\n",
    ),
    (
        "12-several-labels-automerge-ok-first",
        fx(True, "app/renovate", ["automerge-ok", "renovate"]),
        False,
        0,
        "merge=true\n",
    ),
]


class HoldGuardTest(unittest.TestCase):
    def test_hold_guard_cases(self):
        for case_id, fixture, gh_fail, rc, output in CASES:
            with self.subTest(case=case_id):
                got_rc, got_out = run_guard(fixture, gh_fail)
                self.assertEqual(got_rc, rc)
                self.assertEqual(got_out, output)

    def test_label_query_failure_exits_1_without_a_merge_line(self):
        """Author query succeeds, label query fails: broken instrument, not a hold."""
        got_rc, got_out = run_guard(
            fx(True, "app/renovate", ["automerge-ok"]), labels_fail=True
        )
        self.assertEqual(got_rc, 1)
        self.assertNotIn("merge=", got_out)


if __name__ == "__main__":
    unittest.main()
