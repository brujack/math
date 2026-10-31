"""Every binary a workflow downloads is sha256-verified before anything uses it.

The gitleaks install used `wget -qO` and extracted the tarball unchecked, in the
job that holds repository secrets. Same rule as ci-002: a directly downloaded
file pins its version and passes `sha256sum -c` before it is read again.

`check_run` judges one step's `run:` text; the live-tree test applies it to every
step in `.github/workflows/*.yml` and `.github/actions/**/action.yml`.
"""

import pathlib
import re
import shlex
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GITHUB = REPO_ROOT / ".github"
AUTO_MERGE = GITHUB / "workflows" / "auto-merge.yml"
GITLEAKS_SHA256 = "5bc41815076e6ed6ef8fbecc9d9b75bcae31f39029ceb55da08086315316e3ba"


def _download_path(tokens: list[str]) -> str | None:
    """Return the output path of a recognised curl/wget download, else None."""
    flag = "-o" if "curl" in tokens else "-O"
    if flag not in tokens:
        return None
    index = tokens.index(flag)
    if index + 1 >= len(tokens):
        return None
    return tokens[index + 1]


def _check_after(lines: list[str], start: int, path: str) -> str | None:
    """Return a problem if no clean checksum line for `path` follows `start`."""
    for later in range(start + 1, len(lines)):
        line = lines[later]
        if "sha256sum -c" in line and path in line:
            if "||" in line:
                return f"checksum for {path} can be ignored: {line.strip()}"
            return None
        if path in line:
            return f"{path} used before its checksum is verified: {line.strip()}"
    return f"no sha256sum -c for {path}"


def check_run(text: str) -> tuple[int, list[str]]:
    """Return (download count, problems) for one step's `run:` text."""
    lines = text.replace("\\\n", " ").splitlines()
    downloads = 0
    problems: list[str] = []
    for i, line in enumerate(lines):
        if not re.search(r"\b(curl|wget)\b", line):
            continue
        if re.search(r"\|\s*(sh|bash)\b", line):
            problems.append(f"piped to shell: {line.strip()}")
            continue
        try:
            tokens = shlex.split(line.split("|")[0])
        except ValueError:
            problems.append(f"unparseable curl/wget line: {line.strip()}")
            continue
        if "curl" in tokens and "-o" not in tokens and "| jq" in line:
            continue
        path = _download_path(tokens)
        if path is None:
            problems.append(f"unrecognised curl/wget shape: {line.strip()}")
            continue
        downloads += 1
        problem = _check_after(lines, i, path)
        if problem is not None:
            problems.append(problem)
    return downloads, problems


def _steps(document: object, workflow: bool) -> list[dict]:
    if not isinstance(document, dict):
        return []
    if workflow:
        found: list[dict] = []
        for job in (document.get("jobs") or {}).values():
            found.extend(job.get("steps") or [])
        return found
    return list((document.get("runs") or {}).get("steps") or [])


def live_tree() -> tuple[int, list[str]]:
    sources = [(p, True) for p in sorted((GITHUB / "workflows").glob("*.yml"))]
    sources += [(p, False) for p in sorted((GITHUB / "actions").glob("**/action.yml"))]
    total = 0
    problems: list[str] = []
    for path, workflow in sources:
        job_steps = _steps(yaml.safe_load(path.read_text()), workflow)
        for step in job_steps:
            run = step.get("run")
            if not isinstance(run, str):
                continue
            count, found = check_run(run)
            total += count
            name = step.get("name", "<unnamed>")
            problems.extend(
                f"{path.relative_to(REPO_ROOT)} step {name!r}: {p}" for p in found
            )
    return total, problems


class TestCheckRun(unittest.TestCase):
    def test_no_checksum_is_a_problem(self):
        _, problems = check_run("curl -fsSL -o /tmp/a https://x\ntar -xf /tmp/a\n")
        self.assertEqual(len(problems), 1, problems)

    def test_checksum_after_use_is_a_problem(self):
        text = (
            "curl -fsSL -o /tmp/a https://x\n"
            "tar -xf /tmp/a\n"
            'echo "h  /tmp/a" | sha256sum -c -\n'
        )
        _, problems = check_run(text)
        self.assertEqual(len(problems), 1, problems)

    def test_checksum_naming_another_path_is_a_problem(self):
        text = (
            "curl -fsSL -o /tmp/a https://x\n"
            'echo "h  /tmp/b" | sha256sum -c -\n'
            "tar -xf /tmp/a\n"
        )
        _, problems = check_run(text)
        self.assertEqual(len(problems), 1, problems)

    def test_ignored_checksum_failure_is_a_problem(self):
        text = (
            "curl -fsSL -o /tmp/a https://x\n"
            'echo "h  /tmp/a" | sha256sum -c - || true\n'
            "tar -xf /tmp/a\n"
        )
        _, problems = check_run(text)
        self.assertEqual(len(problems), 1, problems)

    def test_piped_to_shell_is_a_problem(self):
        count, problems = check_run("curl -fsSL https://x | sh\n")
        self.assertEqual(count, 0)
        self.assertEqual(len(problems), 1, problems)

    def test_bash_pipe_is_a_problem(self):
        _, problems = check_run("curl -fsSL https://x | bash -s\n")
        self.assertEqual(len(problems), 1, problems)

    def test_wget_qo_is_unrecognised(self):
        _, problems = check_run("wget -qO /tmp/a https://x\n")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("unrecognised", problems[0])

    def test_curl_without_output_flag_is_unrecognised(self):
        _, problems = check_run("curl -fsSL https://x > /tmp/a\n")
        self.assertEqual(len(problems), 1, problems)

    def test_unbalanced_quote_is_a_problem(self):
        _, problems = check_run('curl -fsSL -o /tmp/a "https://x\n')
        self.assertEqual(len(problems), 1, problems)

    def test_trailing_output_flag_is_unrecognised(self):
        _, problems = check_run("curl -fsSL -o\n")
        self.assertEqual(len(problems), 1, problems)

    def test_verified_download_is_clean(self):
        text = (
            "curl -fsSL -o /tmp/a https://x\n"
            'echo "h  /tmp/a" | sha256sum -c -\n'
            "tar -xf /tmp/a\n"
        )
        self.assertEqual(check_run(text), (1, []))

    def test_continuation_lines_are_joined(self):
        text = (
            "curl -fsSL -o /tmp/a \\\n"
            "  https://x\n"
            'echo "h  /tmp/a" | sha256sum -c -\n'
        )
        self.assertEqual(check_run(text), (1, []))

    def test_wget_with_capital_o_is_a_download(self):
        text = 'wget -O /tmp/a https://x\necho "h  /tmp/a" | sha256sum -c -\n'
        self.assertEqual(check_run(text), (1, []))

    def test_api_query_piped_to_jq_is_not_a_download(self):
        self.assertEqual(check_run("curl -s https://api | jq .x\n"), (0, []))

    def test_text_without_downloads_is_clean(self):
        self.assertEqual(check_run("make test\n"), (0, []))


class TestLiveTree(unittest.TestCase):
    def test_every_download_is_verified(self):
        total, problems = live_tree()
        self.assertGreaterEqual(total, 1, "no downloads found: scan is vacuous")
        self.assertEqual(problems, [])


class TestGitleaksPinned(unittest.TestCase):
    def setUp(self):
        steps = yaml.safe_load(AUTO_MERGE.read_text())["jobs"]["secret-scan"]["steps"]
        matches = [s for s in steps if s.get("name") == "Install gitleaks"]
        self.assertEqual(len(matches), 1, "expected one 'Install gitleaks' step")
        self.env = matches[0].get("env") or {}

    def test_version_is_pinned(self):
        self.assertEqual(self.env.get("GITLEAKS_VER"), "8.21.2")

    def test_sha256_is_pinned(self):
        self.assertEqual(self.env.get("GITLEAKS_SHA256"), GITLEAKS_SHA256)


if __name__ == "__main__":
    unittest.main()
