"""Every binary a workflow downloads is sha256-verified before anything uses it.

The gitleaks install used `wget -qO` and extracted the tarball unchecked, in the
job that holds repository secrets. Same rule as ci-002: a directly downloaded
file pins its version and passes `sha256sum -c` before it is read again.

The check fails closed. It does not try to understand arbitrary shell: only two
canonical shapes are compliant, and anything else is reported.

  download:  a line holding one `curl ... -o /abs/path ...` or
             `wget ... -O /abs/path ...` and no shell operator
  checksum:  the whole line is `echo "<hash>  /abs/path" | sha256sum -c -`

`check_run` judges one step's `run:` text; the live-tree test applies it to every
step in `.github/workflows/*.yml` and `.github/actions/**/action.yml`.
"""

import pathlib
import posixpath
import re
import shlex
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GITHUB = REPO_ROOT / ".github"
AUTO_MERGE = GITHUB / "workflows" / "auto-merge.yml"
GITLEAKS_SHA256 = "5bc41815076e6ed6ef8fbecc9d9b75bcae31f39029ceb55da08086315316e3ba"

# `echo "<hash>  <path>" | sha256sum -c -`, nothing before or after.
CHECKSUM_LINE = re.compile(
    r'^echo "(?P<hash>[0-9a-f]{64}|\$\{\w+\}|\$\w+)  (?P<path>[^"]+)" '
    r"\| sha256sum -c -$"
)
OPERATOR_CHARS = set("();<>|&")


def _tokens(line: str) -> list[str]:
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _is_operator(token: str) -> bool:
    return bool(token) and set(token) <= OPERATOR_CHARS


def _mentions(line: str, name: str) -> bool:
    """True when `name` appears in `line` as a whole path token."""
    pattern = r"(?<![\w./-])" + re.escape(name) + r"(?![\w./-])"
    return re.search(pattern, line) is not None


def _is_jq_query(tokens: list[str]) -> bool:
    """A curl with no output file whose pipeline ends in jq and writes nowhere."""
    if "-o" in tokens or "-O" in tokens or "tee" in tokens:
        return False
    if any(">" in token for token in tokens):
        return False
    if "|" not in tokens:
        return False
    return "jq" in tokens[tokens.index("|") + 1 :]


def _verify(lines: list[str], start: int, path: str) -> str | None:
    """Return a problem unless a canonical checksum for `path` precedes any use."""
    names = (path, posixpath.basename(path))
    for line in lines[start + 1 :]:
        stripped = line.strip()
        found = CHECKSUM_LINE.match(stripped)
        if found and found.group("path") == path:
            return None
        mentioned = any(_mentions(stripped, name) for name in names)
        if mentioned and "sha256sum" in stripped:
            return f"non-canonical checksum line for {path}: {stripped}"
        if mentioned:
            return f"{path} used before its checksum is verified: {stripped}"
    return f"no sha256sum -c for {path}"


def _check_download(lines: list[str], index: int) -> tuple[bool, str | None]:
    """Judge one curl/wget line; return (counts as a download, problem)."""
    line = lines[index].strip()
    if re.search(r"\|\s*(sh|bash)\b", line):
        return False, f"piped to shell: {line}"
    try:
        tokens = _tokens(line)
    except ValueError:
        return False, f"unparseable curl/wget line: {line}"
    if "curl" in tokens:
        flag = "-o"
    elif "wget" in tokens:
        flag = "-O"
    else:
        return False, f"unrecognised curl/wget shape: {line}"
    if flag not in tokens:
        if flag == "-o" and _is_jq_query(tokens):
            return False, None
        return False, f"unrecognised curl/wget shape: {line}"
    if any(_is_operator(token) for token in tokens):
        return True, f"download line must stand alone (no && ; | >): {line}"
    position = tokens.index(flag) + 1
    target = tokens[position] if position < len(tokens) else ""
    if not target.startswith("/") or "$" in target:
        return True, f"download target is not a literal absolute path: {line}"
    return True, _verify(lines, index, target)


def check_run(text: str) -> tuple[int, list[str]]:
    """Return (download count, problems) for one step's `run:` text."""
    lines = text.replace("\\\n", " ").splitlines()
    downloads = 0
    problems: list[str] = []
    for index, line in enumerate(lines):
        if not re.search(r"\b(curl|wget)\b", line):
            continue
        counted, problem = _check_download(lines, index)
        downloads += int(counted)
        if problem is not None:
            problems.append(problem)
    return downloads, problems


def _steps(document: object, workflow: bool) -> list[tuple[str, dict]]:
    """Return (job key, step) pairs; a composite action has no job."""
    if not isinstance(document, dict):
        return []
    if workflow:
        found: list[tuple[str, dict]] = []
        for key, job in (document.get("jobs") or {}).items():
            found.extend((key, step) for step in job.get("steps") or [])
        return found
    return [("<action>", s) for s in (document.get("runs") or {}).get("steps") or []]


def live_tree() -> tuple[int, list[str]]:
    sources = [(p, True) for p in sorted((GITHUB / "workflows").glob("*.yml"))]
    sources += [(p, False) for p in sorted((GITHUB / "actions").glob("**/action.yml"))]
    total = 0
    problems: list[str] = []
    for path, workflow in sources:
        for job, step in _steps(yaml.safe_load(path.read_text()), workflow):
            run = step.get("run")
            if not isinstance(run, str):
                continue
            count, found = check_run(run)
            total += count
            where = (
                f"{path.relative_to(REPO_ROOT)} job {job!r} step {step.get('name')!r}"
            )
            problems.extend(f"{where}: {p}" for p in found)
    return total, problems


VERIFIED = (
    "curl -fsSL -o /tmp/a https://x\n"
    'echo "${SUM}  /tmp/a" | sha256sum -c -\n'
    "tar -xf /tmp/a\n"
)
SHA = "a" * 64


class ProblemTestCase(unittest.TestCase):
    def assert_one_problem(self, text: str, fragment: str) -> None:
        _, problems = check_run(text)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn(fragment, problems[0])


class TestCheckRunProblems(ProblemTestCase):
    def test_no_checksum(self):
        self.assert_one_problem(
            "curl -fsSL -o /tmp/a https://x\ntar -xf /tmp/a\n", "used before"
        )

    def test_download_and_nothing_else(self):
        self.assert_one_problem(
            "curl -fsSL -o /tmp/a https://x\n", "no sha256sum -c for /tmp/a"
        )

    def test_checksum_after_use(self):
        text = (
            "curl -fsSL -o /tmp/a https://x\n"
            "tar -xf /tmp/a\n"
            'echo "${SUM}  /tmp/a" | sha256sum -c -\n'
        )
        self.assert_one_problem(text, "used before")

    def test_checksum_naming_another_path(self):
        text = (
            "curl -fsSL -o /tmp/a https://x\n"
            'echo "${SUM}  /tmp/b" | sha256sum -c -\n'
            "tar -xf /tmp/a\n"
        )
        self.assert_one_problem(text, "used before")

    def test_checksum_naming_a_longer_path(self):
        text = 'curl -fsSL -o /tmp/a https://x\necho "${SUM}  /tmp/a.bak" | sha256sum -c -\n'
        self.assert_one_problem(text, "no sha256sum -c for /tmp/a")

    def test_checksum_of_a_checksum_file(self):
        text = "curl -fsSL -o /tmp/x.sha256 https://x\nsha256sum -c /tmp/x.sha256\n"
        self.assert_one_problem(text, "non-canonical checksum line")

    def test_checksum_failure_ignored_with_or(self):
        text = VERIFIED.replace("-c -\n", "-c - || true\n")
        self.assert_one_problem(text, "non-canonical checksum line")

    def test_checksum_failure_ignored_with_semicolon(self):
        text = VERIFIED.replace("-c -\n", "-c -; true\n")
        self.assert_one_problem(text, "non-canonical checksum line")

    def test_checksum_with_stdin_dropped(self):
        text = VERIFIED.replace("-c -\n", "-c\n")
        self.assert_one_problem(text, "non-canonical checksum line")

    def test_piped_to_shell(self):
        self.assert_one_problem("curl -fsSL https://x | sh\n", "piped to shell")

    def test_piped_to_bash(self):
        self.assert_one_problem("curl -fsSL https://x | bash -s\n", "piped to shell")

    def test_wget_qo_is_unrecognised(self):
        self.assert_one_problem("wget -qO /tmp/a https://x\n", "unrecognised")

    def test_redirect_instead_of_output_flag(self):
        self.assert_one_problem("curl -fsSL https://x > /tmp/a\n", "unrecognised")

    def test_unbalanced_quote(self):
        self.assert_one_problem('curl -fsSL -o /tmp/a "https://x\n', "unparseable")

    def test_output_flag_without_a_path(self):
        self.assert_one_problem("curl -fsSL -o\n", "literal absolute path")

    def test_curl_output_to_stdout(self):
        self.assert_one_problem("curl -fsSL -o - https://x\n", "literal absolute path")

    def test_wget_output_to_stdout(self):
        self.assert_one_problem("wget -O - https://x\n", "literal absolute path")

    def test_output_path_from_a_variable(self):
        self.assert_one_problem(
            'curl -fsSL -o "$OUT" https://x\n', "literal absolute path"
        )

    def test_relative_output_path(self):
        self.assert_one_problem("curl -fsSL -o a.tgz https://x\n", "literal absolute")

    def test_download_chained_with_and(self):
        text = VERIFIED.replace("https://x\n", "https://x && tar -xf /tmp/a\n", 1)
        self.assert_one_problem(text, "must stand alone")

    def test_download_followed_by_semicolon(self):
        self.assert_one_problem(
            "curl -fsSL -o /tmp/a https://x; true\n", "must stand alone"
        )

    def test_use_by_basename_before_checksum(self):
        text = (
            "curl -fsSL -o /tmp/g.tgz https://x\n"
            "cd /tmp && tar -xf g.tgz\n"
            'echo "${SUM}  /tmp/g.tgz" | sha256sum -c -\n'
        )
        self.assert_one_problem(text, "used before")

    def test_jq_query_writing_a_file(self):
        self.assert_one_problem(
            "curl -s https://api | jq . > /tmp/s.sh\n", "unrecognised"
        )

    def test_jq_query_through_tee(self):
        self.assert_one_problem(
            "curl -s https://api | jq . | tee /tmp/s.sh\n", "unrecognised"
        )

    def test_second_download_is_judged_on_its_own(self):
        text = VERIFIED + "curl -fsSL -o /tmp/b https://y\n"
        self.assert_one_problem(text, "no sha256sum -c for /tmp/b")


class TestCheckRunCompliant(unittest.TestCase):
    def test_verified_download(self):
        self.assertEqual(check_run(VERIFIED), (1, []))

    def test_literal_hash(self):
        text = VERIFIED.replace('"${SUM} ', f'"{SHA} ')
        self.assertEqual(check_run(text), (1, []))

    def test_braced_variable_hash(self):
        text = VERIFIED.replace('"${SUM} ', '"${SUM} ')
        self.assertEqual(check_run(text), (1, []))

    def test_bare_variable_hash(self):
        text = VERIFIED.replace('"${SUM} ', '"$SUM ')
        self.assertEqual(check_run(text), (1, []))

    def test_other_variable_in_the_checksum_line_passes_the_shape_check(self):
        text = VERIFIED.replace('"${SUM} ', '"${OTHER} ')
        self.assertEqual(check_run(text), (1, []))

    def test_continuation_lines_are_joined(self):
        text = 'curl -fsSL -o /tmp/a \\\n  https://x\necho "${SUM}  /tmp/a" | sha256sum -c -\n'
        self.assertEqual(check_run(text), (1, []))

    def test_quoted_url_with_variable(self):
        text = VERIFIED.replace("https://x", '"https://h/v${VER}/x"')
        self.assertEqual(check_run(text), (1, []))

    def test_wget_with_capital_o(self):
        text = 'wget -O /tmp/a https://x\necho "${SUM}  /tmp/a" | sha256sum -c -\n'
        self.assertEqual(check_run(text), (1, []))

    def test_two_verified_downloads(self):
        text = VERIFIED + VERIFIED.replace("/tmp/a", "/tmp/b")
        self.assertEqual(check_run(text), (2, []))

    def test_api_query_piped_to_jq(self):
        self.assertEqual(check_run("curl -s https://api | jq .x\n"), (0, []))

    def test_text_without_downloads(self):
        self.assertEqual(check_run("make test\n"), (0, []))

    def test_empty_text(self):
        self.assertEqual(check_run(""), (0, []))


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
        self.run_text = str(matches[0].get("run") or "")

    def test_version_is_pinned(self):
        self.assertEqual(self.env.get("GITLEAKS_VER"), "8.21.2")

    def test_sha256_is_pinned(self):
        self.assertEqual(self.env.get("GITLEAKS_SHA256"), GITLEAKS_SHA256)

    def test_checksum_line_uses_the_pinned_hash(self):
        self.assertIn(
            'echo "${GITLEAKS_SHA256}  /tmp/gitleaks.tar.gz" | sha256sum -c -',
            self.run_text,
        )

    def test_installed_version_is_asserted(self):
        self.assertRegex(
            self.run_text,
            r'(?m)^\s*gitleaks version \| grep -qx "\$\{GITLEAKS_VER\}"\s*$',
        )


if __name__ == "__main__":
    unittest.main()
