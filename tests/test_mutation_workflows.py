"""Pin the structure of the monthly Python mutation workflow.

The workflow is `setup` -> per-project x 10 `mutants` matrix -> `notify`. Each assertion parses
the file with `yaml.safe_load` so a comment cannot fake a directive. PyYAML parses
the `on:` key as the boolean True, which these tests do not need.
"""

import fnmatch
import json
import os
import pathlib
import re
import subprocess
import tempfile
import unittest
from typing import NamedTuple

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "mutation-testing-python.yml"
TEMPLATE = REPO_ROOT / "scripts" / "crate_templates" / "python" / "py.yml"

DIRS = [
    "amicable",
    "collatz",
    "e",
    "factorial",
    "fib",
    "perfect-numbers",
    "pi",
    "sq",
    "triangle",
]


def load(path=WORKFLOW):
    return yaml.safe_load(path.read_text())


def steps_of(job):
    return load()["jobs"][job]["steps"]


def pip_lines(path):
    """Return the `pip install` lines of a workflow or placeholder template.

    The template carries `@CRATE@` placeholders and is not valid YAML, so both
    files are scanned as text for `run: pip install ...` lines.
    """
    lines = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("run: pip install"):
            lines.append(stripped)
    return lines


def setup_step():
    steps = [s for s in steps_of("setup") if "matrix=" in s.get("run", "")]
    return steps


def run_setup(subproject):
    steps = setup_step()
    assert len(steps) == 1
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "out"
        out.touch()
        env = {
            "PATH": os.environ["PATH"],
            "GITHUB_OUTPUT": str(out),
            "SUBPROJECT": subproject,
        }
        env.update(
            {
                k: str(v)
                for k, v in steps[0].get("env", {}).items()
                if "${{" not in str(v)
            }
        )
        proc = subprocess.run(
            ["bash", "-c", steps[0]["run"]],
            env=env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        return proc, out.read_text()


class SetupJobTests(unittest.TestCase):
    def test_matrix_and_units_come_from_one_step(self):
        steps = setup_step()
        self.assertEqual(len(steps), 1)
        run = steps[0]["run"]
        self.assertIn("units=", run)
        self.assertIn("GITHUB_OUTPUT", run)

    def test_setup_passes_input_through_env(self):
        step = setup_step()[0]
        self.assertNotIn("${{", step["run"])
        self.assertIn(
            "inputs.subproject", " ".join(str(v) for v in step["env"].values())
        )

    def test_outputs_declared(self):
        outputs = load()["jobs"]["setup"]["outputs"]
        self.assertIn("matrix", outputs)
        self.assertIn("units", outputs)

    def test_empty_input_yields_all_ninety_units(self):
        proc, out = run_setup("")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = dict(line.split("=", 1) for line in out.splitlines())
        units = lines["units"].split()
        self.assertEqual(len(units), 90)
        self.assertEqual(len(set(units)), 90)
        import json

        matrix = json.loads(lines["matrix"])
        self.assertEqual(matrix["dir"], DIRS)
        self.assertEqual(matrix["shard"], list(range(10)))
        self.assertEqual(len(out.splitlines()), 2)

    def test_single_subproject_yields_ten_units(self):
        proc, out = run_setup("fib")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = dict(line.split("=", 1) for line in out.splitlines())
        self.assertEqual(lines["units"].split(), [f"fib-{k}" for k in range(10)])
        import json

        self.assertEqual(json.loads(lines["matrix"])["dir"], ["fib"])

    def test_unknown_subproject_fails_with_message(self):
        proc, out = run_setup("bogus")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("bogus", proc.stderr)
        self.assertEqual(out, "")


class MutantsJobTests(unittest.TestCase):
    def setUp(self):
        self.job = load()["jobs"]["mutants"]

    def test_matrix_job_settings(self):
        self.assertEqual(self.job["needs"], "setup")
        self.assertIs(self.job["strategy"]["fail-fast"], False)
        self.assertEqual(self.job["timeout-minutes"], 90)
        self.assertEqual(
            self.job["strategy"]["matrix"],
            "${{ fromJSON(needs.setup.outputs.matrix) }}",
        )

    def test_cell_script_invoked_with_ten_shards(self):
        runs = [s.get("run", "") for s in self.job["steps"]]
        self.assertTrue(
            any(
                'scripts/mutation-python-cell.sh "${DIR}" "${SHARD}" 10' in r
                for r in runs
            )
        )

    def test_cancelled_step_present(self):
        cancelled = [s for s in self.job["steps"] if s.get("if") == "cancelled()"]
        self.assertEqual(len(cancelled), 1)
        self.assertIn("did not finish", cancelled[0]["run"])

    def test_python_version_and_apt(self):
        text = yaml.safe_dump(self.job["steps"])
        self.assertIn("libgmp-dev libmpfr-dev", text)
        versions = [
            s["with"]["python-version"]
            for s in self.job["steps"]
            if "with" in s and "python-version" in s["with"]
        ]
        self.assertEqual(versions, ["3.14"])

    def test_two_distinct_uploads_with_dir_and_shard(self):
        uploads = [
            s
            for s in self.job["steps"]
            if str(s.get("uses", "")).startswith("actions/upload-artifact@")
        ]
        names = [u["with"]["name"] for u in uploads]
        self.assertEqual(
            sorted(names),
            [
                "mutants-report-python-${{ matrix.dir }}-${{ matrix.shard }}",
                "mutants-status-python-${{ matrix.dir }}-${{ matrix.shard }}",
            ],
        )
        for u in uploads:
            self.assertEqual(u["if"], "always()")
            self.assertEqual(u["with"]["retention-days"], 30)

    def test_status_upload_paths(self):
        status = next(
            s
            for s in self.job["steps"]
            if "with" in s
            and s["with"].get("name", "").startswith("mutants-status-python-")
        )
        for p in ("status/", "survivors/", "marker/"):
            self.assertIn(p, status["with"]["path"])


class NotifyJobTests(unittest.TestCase):
    def setUp(self):
        self.job = load()["jobs"]["notify"]

    def test_needs_and_condition(self):
        self.assertEqual(self.job["needs"], ["setup", "mutants"])
        self.assertEqual(self.job["if"], "always()")
        self.assertEqual(self.job["permissions"]["issues"], "write")

    def test_download_merges_status_artifacts_only(self):
        dl = [
            s
            for s in self.job["steps"]
            if str(s.get("uses", "")).startswith("actions/download-artifact@")
        ]
        self.assertEqual(len(dl), 1)
        self.assertEqual(dl[0]["with"]["pattern"], "mutants-status-python-*")
        self.assertIs(dl[0]["with"]["merge-multiple"], True)

    def test_every_step_after_checkout_runs_always(self):
        for step in self.job["steps"][1:]:
            self.assertIn("always()", str(step.get("if", "")), step)

    def test_notify_step_runs_always(self):
        notify = [
            s for s in self.job["steps"] if s.get("run") == "scripts/mutation-notify.sh"
        ]
        self.assertEqual(len(notify), 1)
        self.assertEqual(notify[0].get("if"), "always()")

    def test_expected_units_wired(self):
        notify = [
            s for s in self.job["steps"] if s.get("run") == "scripts/mutation-notify.sh"
        ]
        self.assertEqual(len(notify), 1)
        self.assertEqual(
            notify[0]["env"]["EXPECTED_STATUS_UNITS"],
            "${{ needs.setup.outputs.units }}",
        )
        self.assertEqual(notify[0]["env"]["ISSUE_LABEL"], "mutation-failure-python")

    def test_survivor_report_and_upload(self):
        report = [
            s
            for s in self.job["steps"]
            if s.get("run") == "scripts/mutation-survivor-report.sh"
        ]
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["if"], "always()")
        self.assertEqual(
            report[0]["env"]["EXPECTED_STATUS_UNITS"],
            "${{ needs.setup.outputs.units }}",
        )
        up = [
            s
            for s in self.job["steps"]
            if "with" in s and s["with"].get("name") == "mutants-survivors-python"
        ]
        self.assertEqual(len(up), 1)
        self.assertEqual(up[0]["with"]["retention-days"], 90)
        self.assertEqual(up[0]["if"], "always()")


class PipLineTests(unittest.TestCase):
    def test_pip_line_matches_template(self):
        lines = pip_lines(WORKFLOW)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0])
        self.assertIn("hypothesis", lines[0])
        self.assertEqual(lines, pip_lines(TEMPLATE))


PR_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "mutation-pr.yml"


def pr_steps():
    return load(PR_WORKFLOW)["jobs"]["mutation-pr"]["steps"]


def pr_step(fragment):
    found = [s for s in pr_steps() if fragment in s.get("run", "")]
    return found


class MutationPrTests(unittest.TestCase):
    def test_no_cosmic_ray_exec(self):
        for step in pr_steps():
            self.assertNotIn("cosmic-ray exec", step.get("run", ""))

    def test_python_step_runs_baseline_per_dir(self):
        found = pr_step("mutants-baseline")
        self.assertEqual(len(found), 1)
        step = found[0]
        self.assertIn("for dir in ${PY_DIRS}", step["run"])
        self.assertIn('make -C "${dir}" mutants-baseline || exit 1', step["run"])
        self.assertNotIn("continue-on-error", step)
        self.assertEqual(step["if"], "steps.detect.outputs.has_py == 'true'")
        self.assertEqual(step["env"]["PY_DIRS"], "${{ steps.detect.outputs.py_dirs }}")

    def test_gmp_and_pip_gated_after_detect(self):
        steps = pr_steps()
        names = [s.get("name") for s in steps]
        detect = names.index("Detect changed sub-projects")
        for fragment in ("libgmp-dev", "pip install"):
            found = pr_step(fragment)
            self.assertEqual(len(found), 1, fragment)
            self.assertEqual(found[0]["if"], "steps.detect.outputs.has_py == 'true'")
            self.assertGreater(steps.index(found[0]), detect)

    def test_setup_python_is_314(self):
        found = [s for s in pr_steps() if "setup-python" in s.get("uses", "")]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["with"]["python-version"], "3.14")

    def test_detect_calls_script(self):
        found = [s for s in pr_steps() if s.get("id") == "detect"]
        self.assertEqual(len(found), 1)
        self.assertEqual(
            found[0]["run"].strip(),
            'scripts/mutation-pr-detect.sh "origin/${GITHUB_BASE_REF}" >> "${GITHUB_OUTPUT}"',
        )
        self.assertEqual(found[0]["env"]["GITHUB_BASE_REF"], "${{ github.base_ref }}")

    def test_no_factorial_only_rust_step_or_fixed_timeout(self):
        text = PR_WORKFLOW.read_text()
        self.assertNotIn("factorial-rs", text)
        self.assertNotIn("/tmp/pr.diff", text)
        self.assertIsNone(re.search(r"--timeout\s+\d", text))
        for step in pr_steps():
            self.assertNotIn("Get PR diff", step.get("name", ""))

    def test_job_timeout_is_sixty_minutes(self):
        self.assertEqual(
            load(PR_WORKFLOW)["jobs"]["mutation-pr"]["timeout-minutes"], 60
        )

    def test_skip_step_waits_for_canary_too(self):
        found = [s for s in pr_steps() if s.get("name", "").startswith("Skip")]
        self.assertEqual(len(found), 1)
        cond = found[0]["if"]
        for output in ("has_rs", "has_py", "rs_canary"):
            self.assertIn(f"steps.detect.outputs.{output} == 'false'", cond)

    def test_gmp_cache_restored_for_rust_or_canary(self):
        need = "steps.detect.outputs.has_rs == 'true' || steps.detect.outputs.rs_canary == 'true'"
        key = next(s for s in pr_steps() if s.get("id") == "gmpkey")
        self.assertEqual(key["if"], need)
        self.assertIn("scripts/gmp-cache-key.sh", key["run"])
        self.assertIn("GMP_MPFR_SYS_CACHE", key["run"])
        restore = next(s for s in pr_steps() if "cache/restore" in s.get("uses", ""))
        self.assertEqual(
            restore["if"], f"({need}) && steps.gmpkey.outputs.enabled == 'true'"
        )
        self.assertEqual(restore["with"]["key"], "${{ steps.gmpkey.outputs.key }}")
        names = [s.get("name") for s in pr_steps()]
        self.assertLess(
            names.index(restore["name"]),
            names.index("Run Rust mutants on changed crates"),
        )

    def test_rust_step_wiring(self):
        step = pr_rs_step("Run Rust mutants on changed crates")
        self.assertEqual(step["if"], "steps.detect.outputs.has_rs == 'true'")
        self.assertEqual(step["env"]["RS_DIRS"], "${{ steps.detect.outputs.rs_dirs }}")
        self.assertEqual(step["env"]["GITHUB_BASE_REF"], "${{ github.base_ref }}")
        self.assertNotIn("continue-on-error", step)

    def test_canary_step_wiring(self):
        step = pr_rs_step("Gate canary (amicable-rs)")
        self.assertEqual(step["if"], "steps.detect.outputs.rs_canary == 'true'")
        self.assertNotIn("continue-on-error", step)

    def test_no_expression_syntax_in_any_run_block(self):
        for step in pr_steps():
            self.assertNotIn("${{", step.get("run", ""), step)

    def test_rust_step_passes_base_ref_dirs_and_log_to_summary(self):
        proc, calls, summary = run_pr_rust_step(RS_STEP, dirs="a/a-rs b/b-rs")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(calls, ["origin/master", "a/a-rs", "b/b-rs"])
        self.assertEqual(summary, "stub verdict\n")

    def test_rust_step_propagates_red_after_logging(self):
        proc, calls, summary = run_pr_rust_step(RS_STEP, dirs="a/a-rs", run_rc=1)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(calls, ["origin/master", "a/a-rs"])
        self.assertEqual(summary, "stub verdict\n")

    def test_rust_step_propagates_usage_error(self):
        proc, _calls, _summary = run_pr_rust_step(RS_STEP, dirs="a/a-rs", run_rc=2)
        self.assertEqual(proc.returncode, 2)

    def test_canary_edits_commits_only_the_file_and_runs_loop(self):
        res = run_canary()
        self.assertEqual(res.proc.returncode, 0, res.proc.stderr)
        self.assertEqual(
            res.calls, ["HEAD~1", "--min-caught", "1", "amicable/amicable-rs"]
        )
        # At call time HEAD~1 is the clean tree: the canary commit must precede it.
        # The staged unrelated file shows in the tree-vs-HEAD~1 diff, but the commit
        # itself holds only the canary file (asserted below).
        self.assertEqual(res.diff_at_call, [CANARY_FILE, "other.txt"])
        self.assertEqual(res.committed, [CANARY_FILE])
        self.assertEqual(res.summary, "stub verdict\n")
        self.assertIn("let mut m = 2 * d; \n", res.lib)
        self.assertEqual(res.lib.count("let mut m = 2 * d;"), 1)
        self.assertEqual(res.staged_other, ["other.txt"])

    def test_canary_stub_failure_fails_step(self):
        res = run_canary(run_rc=1)
        self.assertEqual(res.proc.returncode, 1)
        self.assertEqual(res.calls[0], "HEAD~1")

    def test_canary_zero_matches_is_red_without_edit_or_call(self):
        res = run_canary(lib="fn main() {}\n")
        self.assertNotEqual(res.proc.returncode, 0)
        self.assertEqual(res.calls, [])
        self.assertEqual(res.commit_count, 1)
        self.assertEqual(res.lib, "fn main() {}\n")

    def test_canary_two_matches_is_red_without_edit_or_call(self):
        lib = "let mut m = 2 * d;\nlet mut m = 2 * d;\n"
        res = run_canary(lib=lib)
        self.assertNotEqual(res.proc.returncode, 0)
        self.assertEqual(res.calls, [])
        self.assertEqual(res.commit_count, 1)
        self.assertEqual(res.lib, lib)

    def test_pip_line_matches_template(self):
        lines = pip_lines(PR_WORKFLOW)
        self.assertEqual(len(lines), 1)
        self.assertIn("hypothesis", lines[0])
        self.assertEqual(lines, pip_lines(TEMPLATE))

    def test_cargo_mutants_install_unconditional(self):
        found = pr_step("cargo install cargo-mutants --locked --version 27.1.0")
        self.assertEqual(len(found), 1)
        self.assertNotIn("if", found[0])


RS_STEP = "Run Rust mutants on changed crates"
CANARY_STEP = "Gate canary (amicable-rs)"
CANARY_FILE = "amicable/amicable-rs/src/lib.rs"
CANARY_LIB = "fn f() {\n    let mut m = 2 * d;\n}\n"


def pr_rs_step(name):
    found = [s for s in pr_steps() if s.get("name") == name]
    assert len(found) == 1, name
    return found[0]


def stub_run_script(path, log, rc_env="RUN_RC"):
    """A mutation-pr-run.sh stub that exits $RUN_RC after logging, at call time:

    - `log`: one argument per line, so a regrouped argument list is visible;
    - `log.diff`: `git diff --name-only HEAD~1` (empty outside a git repo), so a
      test can tell whether the canary commit happened before the call.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f'printf \'%s\\n\' "$@" >> "{log}"\n'
        f'git diff --name-only HEAD~1 >> "{log}.diff" 2>/dev/null\n'
        "printf 'stub verdict\\n'\n"
        f'exit "${rc_env}"\n'
    )
    path.chmod(0o755)


def run_pr_step_block(name, cwd, env):
    return subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-eo",
            "pipefail",
            "-c",
            pr_rs_step(name)["run"],
        ],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def run_pr_rust_step(name, dirs, run_rc=0):
    """Run the Rust loop step against a stub run script; returns (proc, argv lines, summary)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        log = root / "calls"
        stub_run_script(root / "repo" / "scripts" / "mutation-pr-run.sh", log)
        (root / "temp").mkdir()
        summary = root / "summary"
        summary.touch()
        env = {
            "PATH": os.environ["PATH"],
            "RS_DIRS": dirs,
            "GITHUB_BASE_REF": "master",
            "RUNNER_TEMP": str(root / "temp"),
            "GITHUB_STEP_SUMMARY": str(summary),
            "RUN_RC": str(run_rc),
        }
        proc = run_pr_step_block(name, root / "repo", env)
        calls = log.read_text().splitlines() if log.exists() else []
        return proc, calls, summary.read_text()


class CanaryRun(NamedTuple):
    proc: subprocess.CompletedProcess[str]
    calls: list[str]
    summary: str
    lib: str
    committed: list[str]
    staged_other: list[str]
    commit_count: int
    diff_at_call: list[str]


def run_canary(lib=CANARY_LIB, run_rc=0):
    """Run the canary step in a real throwaway git repo with a stub run script."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        repo = root / "repo"
        env = clean_git_env()
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]

        def run_git(*args):
            return subprocess.run(
                [*git, *args],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout

        lib_path = repo / CANARY_FILE
        lib_path.parent.mkdir(parents=True)
        lib_path.write_text(lib)
        log = root / "calls"
        stub_run_script(repo / "scripts" / "mutation-pr-run.sh", log)
        run_git("init", "-q")
        run_git("add", ".")
        run_git("commit", "-q", "-m", "base")
        # A staged unrelated file: a commit that is not path-limited would sweep it in.
        (repo / "other.txt").write_text("x\n")
        run_git("add", "other.txt")
        (root / "temp").mkdir()
        summary = root / "summary"
        summary.touch()
        env.update(
            {
                "RUNNER_TEMP": str(root / "temp"),
                "GITHUB_STEP_SUMMARY": str(summary),
                "RUN_RC": str(run_rc),
            }
        )
        proc = run_pr_step_block(CANARY_STEP, repo, env)
        count = int(run_git("rev-list", "--count", "HEAD").strip())
        committed = run_git("show", "--name-only", "--format=", "HEAD").split()
        staged = run_git("diff", "--cached", "--name-only").split()
        calls = log.read_text().splitlines() if log.exists() else []
        diff_log = pathlib.Path(f"{log}.diff")
        at_call = diff_log.read_text().split() if diff_log.exists() else []
        return CanaryRun(
            proc,
            calls,
            summary.read_text(),
            lib_path.read_text(),
            committed,
            staged,
            count,
            at_call,
        )


RS_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "mutation-testing.yml"
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


def clean_git_env():
    """Return os.environ minus the GIT_* vars a worktree hook exports."""
    return {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}


def rs_job(name):
    return yaml.safe_load(RS_WORKFLOW.read_text())["jobs"][name]


def rs_step(job, name):
    """Return the one step of `job` whose id or name is `name`."""
    found = [s for s in rs_job(job)["steps"] if name in (s.get("id"), s.get("name"))]
    assert len(found) == 1, f"expected exactly one step {name!r} in job {job!r}"
    return found[0]


class SetupRun(NamedTuple):
    proc: "subprocess.CompletedProcess[str]"
    outputs: dict[str, str]
    lines: list[str]


def run_rs_setup(crate="", path=None):
    """Execute the setup job's `plan` step; return (proc, outputs, lines)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "out"
        out.touch()
        env = {
            "PATH": path if path is not None else os.environ["PATH"],
            "GITHUB_OUTPUT": str(out),
            "CRATE": crate,
        }
        proc = subprocess.run(
            [
                "bash",
                "--noprofile",
                "--norc",
                "-eo",
                "pipefail",
                "-c",
                rs_step("setup", "plan")["run"],
            ],
            env=env,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        outputs = {}
        raw_lines = []
        for line in out.read_text().splitlines():
            if not line:
                continue
            raw_lines.append(line)
            if not re.fullmatch(r"[A-Za-z_]+=.*", line):
                raise AssertionError(f"malformed GITHUB_OUTPUT line: {line!r}")
            key, _, value = line.partition("=")
            outputs[key] = value
        return SetupRun(proc, outputs, raw_lines)


def tracked_crate_dirs():
    proc = subprocess.run(
        ["git", "ls-files", "*/*-rs/Cargo.toml"],
        cwd=REPO_ROOT,
        env=clean_git_env(),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=True,
    )
    return sorted(os.path.dirname(f) for f in proc.stdout.split())


class RustSetupJobTests(unittest.TestCase):
    def test_empty_crate_lists_tracked_crates_only(self):
        proc, outputs, lines = run_rs_setup("")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(lines[0].startswith("matrix="), lines)
        self.assertTrue(lines[1].startswith("units="), lines)
        units = outputs["units"].split()
        dirs = tracked_crate_dirs()
        self.assertEqual(len(units), 11)
        self.assertEqual(units, [d.replace("/", "-") for d in dirs])
        self.assertFalse([u for u in units if u.startswith("tests-")])

    def test_matrix_crates_and_slugs_match_units(self):
        proc, outputs, _lines = run_rs_setup("")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        include = json.loads(outputs["matrix"])["include"]
        self.assertEqual([i["crate"] for i in include], tracked_crate_dirs())
        self.assertEqual([i["slug"] for i in include], outputs["units"].split())
        for item in include:
            self.assertEqual(item["slug"], item["crate"].replace("/", "-"))

    def test_fixture_cargo_tomls_exist_as_positive_control(self):
        proc = subprocess.run(
            ["git", "ls-files", "tests/fixtures/**/Cargo.toml"],
            cwd=REPO_ROOT,
            env=clean_git_env(),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=True,
        )
        self.assertTrue(proc.stdout.strip())

    def test_known_crate_gives_single_entry_matrix(self):
        proc, outputs, _lines = run_rs_setup("sq/sq-rs")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(outputs["units"], "sq-sq-rs")
        self.assertEqual(
            json.loads(outputs["matrix"])["include"],
            [{"crate": "sq/sq-rs", "slug": "sq-sq-rs"}],
        )

    def test_unknown_crate_refused_naming_it(self):
        proc, outputs, lines = run_rs_setup("nope/nope-rs")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("nope/nope-rs", proc.stderr)
        self.assertEqual(lines, [])
        self.assertEqual(outputs, {})

    def test_newline_injection_refused(self):
        proc, outputs, lines = run_rs_setup("sq/sq-rs\nevil=1")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("evil=1", proc.stderr)
        self.assertNotIn("evil", outputs)
        self.assertEqual(lines, [])

    def test_empty_list_refuses_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = pathlib.Path(tmp) / "git"
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
            proc, _outputs, lines = run_rs_setup("", path=f"{tmp}:{os.environ['PATH']}")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("refusing to report green", proc.stderr)
        self.assertEqual(lines, [])

    def test_crate_env_reads_dispatch_input(self):
        self.assertEqual(
            rs_step("setup", "plan")["env"]["CRATE"], "${{ github.event.inputs.crate }}"
        )

    def test_outputs_declared_from_plan_step(self):
        outputs = rs_job("setup")["outputs"]
        self.assertEqual(outputs["matrix"], "${{ steps.plan.outputs.matrix }}")
        self.assertEqual(outputs["units"], "${{ steps.plan.outputs.units }}")

    def test_no_expression_syntax_in_run_block(self):
        self.assertNotIn("${{", rs_step("setup", "plan")["run"])


class JobResult(tuple):  # type: ignore[type-arg]
    """The (proc, make calls, statuses, summary) tuple plus classifier records.

    `classifier_argc` lists the argument count of each mutation-classify.sh call;
    `classifier_args` lists its fourth and fifth arguments, one string per call.
    """

    classifier_argc: list[str]
    classifier_args: list[str]

    def __new__(cls, fields, classifier_argc, classifier_args):
        self = super().__new__(cls, fields)
        self.classifier_argc = classifier_argc
        self.classifier_args = classifier_args
        return self


_SAME = object()  # exit-code file holds the same value as the make stub's status


class CrateStub(NamedTuple):
    """Behaviour of the stubbed make and classifier for one `mutants` job run."""

    red: bool = False
    make_rc: int = 0
    exit_code: object = _SAME  # int or str to write, None for no file, _SAME


def run_crate_job(
    crate,
    slug,
    stub: CrateStub | None = None,
    pre_status=None,
    step="Run mutants",
):
    """Execute a `mutants` job step against stub make/classifier.

    Returns (proc, make_calls, {status filename: content}, step summary). The
    make stub exits `stub.make_rc` (cargo-mutants exits 2 for survivors, 3 for
    timeouts, both green by policy) and writes `<crate>/mutants.out/exit-code`
    holding `stub.exit_code` (default: `make_rc`; None writes no file, as when the
    recipe died before cargo-mutants ran). The classifier stub echoes the exit code
    and outcomes path it was given, and reports red (exit 1) when `stub.red`, green
    otherwise. `pre_status` seeds status/<slug> before the step runs.
    """
    red, make_rc, exit_code = stub or CrateStub()
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        bindir = root / "bin"
        bindir.mkdir()
        calls = root / "make-calls"
        make = bindir / "make"
        make.write_text(
            f'#!/bin/sh\nprintf \'%s\\n\' "$2" >> "{calls}"\n'
            'if [ -n "${EXIT_CODE_FILE_VALUE+x}" ]; then\n'
            '  mkdir -p "$2/mutants.out"\n'
            '  printf \'%s\\n\' "$EXIT_CODE_FILE_VALUE" > "$2/mutants.out/exit-code"\n'
            "fi\n"
            'exit "$MAKE_RC"\n'
        )
        make.chmod(0o755)
        workspace = root / "ws"
        (workspace / "scripts").mkdir(parents=True)
        classify = workspace / "scripts" / "mutation-classify.sh"
        classify.write_text(
            "#!/bin/sh\n"
            f'printf \'%s\\n\' "$#" >> "{root / "classify-argc"}"\n'
            f'printf \'%s\\n\' "$4 $5" >> "{root / "classify-args"}"\n'
            'if [ "$RED" = "1" ]; then printf "red: %s rc=%s %s\\n" "$3" "$1" "$2" >&2; exit 1; fi\n'
            'printf \'green: %s rc=%s %s\\n\' "$3" "$1" "$2"\n'
        )
        classify.chmod(0o755)
        if pre_status is not None:
            (workspace / "status").mkdir()
            (workspace / "status" / slug).write_text(pre_status)
        summary = root / "summary"
        summary.touch()
        env = {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "GITHUB_WORKSPACE": str(workspace),
            "GITHUB_STEP_SUMMARY": str(summary),
            "CRATE_DIR": crate,
            "SLUG": slug,
            "RED": "1" if red else "0",
            "MAKE_RC": str(make_rc),
        }
        if exit_code is not None:
            env["EXIT_CODE_FILE_VALUE"] = str(
                make_rc if exit_code is _SAME else exit_code
            )
        proc = subprocess.run(
            [
                "bash",
                "--noprofile",
                "--norc",
                "-eo",
                "pipefail",
                "-c",
                rs_step("mutants", step)["run"],
            ],
            env=env,
            cwd=root,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        made = calls.read_text().splitlines() if calls.exists() else []
        statuses = {p.name: p.read_text() for p in (workspace / "status").glob("*")}
        argc_file = root / "classify-argc"
        argc = argc_file.read_text().split() if argc_file.exists() else []
        args_file = root / "classify-args"
        args = args_file.read_text().splitlines() if args_file.exists() else []
        return JobResult((proc, made, statuses, summary.read_text()), argc, args)


class RustMutantsJobTests(unittest.TestCase):
    def test_green_crate_writes_green_status(self):
        proc, made, statuses, summary = run_crate_job("a/a-rs", "a-a-rs")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(made, ["a/a-rs"])
        line = "green: a/a-rs rc=0 a/a-rs/mutants.out/outcomes.json\n"
        self.assertEqual(statuses, {"a-a-rs": line})
        self.assertEqual(summary, line)

    def test_make_failure_rc_reaches_classifier_and_status(self):
        # cargo-mutants exits 2 when mutants survive; under `bash -e` the step
        # must capture it, hand it to the classifier and still write status.
        proc, made, statuses, summary = run_crate_job(
            "a/a-rs", "a-a-rs", CrateStub(make_rc=2)
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(made, ["a/a-rs"])
        line = "green: a/a-rs rc=2 a/a-rs/mutants.out/outcomes.json\n"
        self.assertEqual(statuses, {"a-a-rs": line})
        self.assertEqual(summary, line)

    def test_classifier_reads_exit_code_file_not_make_status(self):
        # make exits 2 for ANY failed recipe; the true cargo-mutants code (4,
        # baseline failed) is only in mutants.out/exit-code.
        proc, _made, statuses, summary = run_crate_job(
            "a/a-rs", "a-a-rs", CrateStub(make_rc=2, exit_code=4)
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        line = "green: a/a-rs rc=4 a/a-rs/mutants.out/outcomes.json\n"
        self.assertEqual(statuses, {"a-a-rs": line})
        self.assertEqual(summary, line)

    def test_classifier_gets_limit_zero_and_min_caught_one(self):
        # Worldclass slice 6 / ADR-0042: survivors are red in the sweep, so the
        # classifier gets max_missed 0 and min_caught 1 after the crate dir.
        result = run_crate_job("a/a-rs", "a-a-rs")
        self.assertEqual(result.classifier_argc, ["5"])
        self.assertEqual(result.classifier_args, ["0 1"])

    def test_non_integer_exit_code_is_red_and_never_classified(self):
        # '' and 'x' both read as 0 inside the classifier's `-eq`, which turns
        # a garbage file into a green verdict.
        for bad in ("", "x", "4x", "-1", "0004", "1000"):
            with self.subTest(bad=bad):
                result = run_crate_job("a/a-rs", "a-a-rs", CrateStub(exit_code=bad))
                proc, _made, statuses, summary = result
                self.assertEqual(proc.returncode, 1)
                line = "red: a/a-rs - mutants.out/exit-code is not an integer\n"
                self.assertEqual(statuses, {"a-a-rs": line})
                self.assertEqual(summary, line)
                self.assertEqual(result.classifier_argc, [])

    def test_missing_exit_code_file_is_red_and_never_classified(self):
        proc, made, statuses, summary = run_crate_job(
            "a/a-rs", "a-a-rs", CrateStub(make_rc=2, exit_code=None)
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(made, ["a/a-rs"])
        line = "red: a/a-rs - no mutants.out/exit-code\n"
        self.assertEqual(statuses, {"a-a-rs": line})
        self.assertEqual(summary, line)

    def test_red_crate_fails_step_and_writes_red_status(self):
        proc, made, statuses, summary = run_crate_job(
            "a/a-rs", "a-a-rs", CrateStub(red=True, make_rc=1)
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(made, ["a/a-rs"])
        line = "red: a/a-rs rc=1 a/a-rs/mutants.out/outcomes.json\n"
        self.assertEqual(statuses, {"a-a-rs": line})
        self.assertEqual(summary, line)

    def test_cancelled_step_records_red_when_no_status(self):
        proc, _made, statuses, _summary = run_crate_job(
            "a/a-rs", "a-a-rs", step="Record unfinished crate"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            statuses,
            {"a-a-rs": "red: a-a-rs \u2014 did not finish (cancelled or timed out)\n"},
        )

    def test_cancelled_step_keeps_existing_status(self):
        proc, _made, statuses, _summary = run_crate_job(
            "a/a-rs",
            "a-a-rs",
            pre_status="green: a/a-rs\n",
            step="Record unfinished crate",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(statuses, {"a-a-rs": "green: a/a-rs\n"})

    def test_job_structure(self):
        job = rs_job("mutants")
        self.assertIs(job["strategy"]["fail-fast"], False)
        self.assertEqual(job["timeout-minutes"], 60)
        self.assertEqual(
            job["strategy"]["matrix"], "${{ fromJSON(needs.setup.outputs.matrix) }}"
        )
        self.assertEqual(job["needs"], "setup")
        self.assertEqual(
            rs_step("mutants", "Record unfinished crate")["if"], "cancelled()"
        )

    def test_run_step_env_from_matrix(self):
        env = rs_step("mutants", "Run mutants")["env"]
        self.assertEqual(env["CRATE_DIR"], "${{ matrix.crate }}")
        self.assertEqual(env["SLUG"], "${{ matrix.slug }}")

    def test_uploads_are_per_crate_and_always(self):
        status = rs_step("mutants", "Upload crate status")
        output = rs_step("mutants", "Upload crate output")
        self.assertEqual(status["if"], "always()")
        self.assertEqual(output["if"], "always()")
        self.assertEqual(status["with"]["name"], "mutants-status-${{ matrix.slug }}")
        self.assertEqual(output["with"]["name"], "mutants-output-${{ matrix.slug }}")
        self.assertEqual(
            set(status["with"]["path"].splitlines()), {"status/", "marker/"}
        )
        self.assertEqual(
            set(output["with"]["path"].splitlines()),
            {"${{ matrix.crate }}/mutants.out/", "marker/"},
        )

    def test_no_expression_syntax_in_any_run_block(self):
        for step in rs_job("mutants")["steps"]:
            self.assertNotIn("${{", step.get("run", ""), step)


class RustNotifyJobTests(unittest.TestCase):
    ISSUE = "File, comment, or close the tracking issue"

    def test_job_shape(self):
        job = rs_job("notify")
        self.assertEqual(job["needs"], ["setup", "mutants"])
        self.assertEqual(job["if"], "always()")
        self.assertEqual(job["permissions"]["issues"], "write")

    def test_status_download_merges_per_crate_artifacts(self):
        dl = rs_step("notify", "dl")
        self.assertEqual(dl["with"]["pattern"], "mutants-status-*")
        self.assertIs(dl["with"]["merge-multiple"], True)
        self.assertEqual(dl["with"]["path"], "artifact")
        self.assertIs(dl["continue-on-error"], True)
        self.assertNotIn("name", dl["with"])
        self.assertEqual(dl["with"]["digest-mismatch"], "error")

    def test_issue_step_env_and_run(self):
        step = rs_step("notify", self.ISSUE)
        self.assertEqual(step["if"], "always()")
        env = step["env"]
        self.assertEqual(
            env["EXPECTED_STATUS_UNITS"], "${{ needs.setup.outputs.units }}"
        )
        self.assertEqual(env["UNIT_NOUN"], "crate")
        self.assertEqual(env["ISSUE_LABEL"], "mutation-failure")
        self.assertEqual(step["run"], "scripts/mutation-notify.sh")

    def test_notify_does_not_reaggregate_outputs(self):
        # Slice 6 (ADR-0042): the only reader of a merged `mutants-output`
        # artifact was ai-config's mutation-review cargo-mutants leg, retired by
        # a coordinated ai-config change that merges first, so notify neither
        # downloads the per-crate outputs nor re-uploads them.
        for step in rs_job("notify")["steps"]:
            with_ = step.get("with") or {}
            self.assertNotEqual(with_.get("pattern"), "mutants-output-*", step)
            self.assertNotEqual(with_.get("name"), "mutants-output", step)
        names = [s.get("name") for s in rs_job("notify")["steps"]]
        self.assertEqual(names[-1], self.ISSUE)

    def test_issue_step_runs_always(self):
        self.assertEqual(rs_step("notify", self.ISSUE)["if"], "always()")

    def test_status_pattern_does_not_match_outputs(self):
        status = rs_step("notify", "dl")["with"]["pattern"]
        self.assertFalse(fnmatch.fnmatch("mutants-output-x", status))

    def test_only_dl_step_continues_on_error(self):
        for step in rs_job("notify")["steps"]:
            if step.get("id") != "dl":
                self.assertNotIn("continue-on-error", step, step)

    def test_no_expression_syntax_in_any_run_block(self):
        for step in rs_job("notify")["steps"]:
            self.assertNotIn("${{", step.get("run", ""), step)


class MutationPrPermissionsTests(unittest.TestCase):
    """mutation-pr runs PR-authored code, so its token must be read-only."""

    PR_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "mutation-pr.yml"

    def test_top_level_permissions_are_contents_read(self):
        self.assertEqual(
            load(self.PR_WORKFLOW).get("permissions"), {"contents": "read"}
        )

    def test_no_job_overrides_with_write_scope(self):
        for name, job in load(self.PR_WORKFLOW)["jobs"].items():
            perms = job.get("permissions", {})
            if isinstance(perms, str):
                self.assertNotIn("write", perms, name)
            else:
                self.assertNotIn("write", perms.values(), name)


if __name__ == "__main__":
    unittest.main()
