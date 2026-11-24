"""Pin the structure and behaviour of the three mutation workflows.

Covers mutation-testing-python.yml (monthly: `setup` -> per-project x 10 `mutants`
matrix -> `notify`), mutation-pr.yml (per-PR Python baseline, Rust loop, canary and
read-only token) and mutation-testing.yml (monthly Rust sweep: `setup` -> per-crate
`mutants` -> `notify`). Each assertion parses the file with `yaml.safe_load` so a
comment cannot fake a directive; PyYAML parses the `on:` key as the boolean True,
which these tests do not need. Run blocks execute against stubs where noted.
"""

import fnmatch
import json
import os
import pathlib
import re
import shutil
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
    "descartes",
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

    def test_empty_input_yields_all_one_hundred_units(self):
        proc, out = run_setup("")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = dict(line.split("=", 1) for line in out.splitlines())
        units = lines["units"].split()
        self.assertEqual(len(units), 100)
        self.assertEqual(len(set(units)), 100)
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
TAIKI_USES = "taiki-e/install-action@cfdb7ed4ccc7c7dce37759eae89dc5674b469b39"
RS_RUN_STEP = "Run Rust mutants on one shard"
CANARY_STEP = "Gate canary (amicable-rs)"
CANARY_FILE = "amicable/amicable-rs/src/lib.rs"
CANARY_LIB = "fn f() {\n    let mut m = 2 * d;\n}\n"
SHELL_FLAGS = (["-e"], ["-eo", "pipefail"])  # GitHub's default, and the pipefail form


def pr_steps():
    """The steps of `mutation-rs`, the Rust shard job."""
    return load(PR_WORKFLOW)["jobs"]["mutation-rs"]["steps"]


def run_block(step, cwd, env, flags):
    return subprocess.run(
        ["bash", "--noprofile", "--norc", *flags, "-c", step["run"]],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def stub_run_script(path, log):
    """A mutation-pr-run.sh stub that logs its argv, prints $STUB_OUT, exits $RUN_RC.

    - `log`: one argument per line, so a regrouped argument list is visible;
    - `log.diff`: `git diff --name-only HEAD~1` (empty outside a git repo), so a
      test can tell whether the canary commit happened before the call.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f'printf \'%s\n\' "$@" >> "{log}"\n'
        f'git diff --name-only HEAD~1 >> "{log}.diff" 2>/dev/null\n'
        "printf '%b' \"${STUB_OUT:-stub verdict\n}\"\n"
        'exit "${RUN_RC}"\n'
    )
    path.chmod(0o755)


def stub_plan_script(path, log):
    """A mutation-rs-plan.sh stub: logs argv, prints $PLAN_JSON on stdout only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f'printf \'%s\n\' "$@" >> "{log}"\n'
        "printf 'plan: stderr noise\n' >&2\n"
        "printf '%s\n' \"${PLAN_JSON}\"\n"
        'exit "${PLAN_RC:-0}"\n'
    )
    path.chmod(0o755)


class ShardRun(NamedTuple):
    proc: subprocess.CompletedProcess[str]
    calls: list[str]
    summary: str
    log: str


def run_shard_step(flags, run_rc=0, stdout="stub verdict\n"):
    """Run the mutation-rs run block against a stub run script."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        calls = root / "calls"
        stub_run_script(root / "repo" / "scripts" / "mutation-pr-run.sh", calls)
        (root / "temp").mkdir()
        summary = root / "summary"
        summary.touch()
        env = {
            "PATH": os.environ["PATH"],
            "CRATE": "a/a-rs",
            "K": "1",
            "N": "3",
            "COUNT": "7",
            "GITHUB_BASE_REF": "master",
            "RUNNER_TEMP": str(root / "temp"),
            "GITHUB_STEP_SUMMARY": str(summary),
            "RUN_RC": str(run_rc),
            "STUB_OUT": stdout,
        }
        proc = run_block(
            named_step("mutation-rs", RS_RUN_STEP), root / "repo", env, flags
        )
        log = root / "temp" / "rs.log"
        return ShardRun(
            proc,
            calls.read_text().splitlines() if calls.exists() else [],
            summary.read_text(),
            log.read_text() if log.exists() else "",
        )


class MutationPrTests(unittest.TestCase):
    def test_no_cosmic_ray_exec_in_rust_jobs(self):
        for job in ("mutation-rs-plan", "mutation-rs", "mutation-rs-canary"):
            for step in job_steps(job):
                self.assertNotIn("cosmic-ray exec", step.get("run", ""), job)
                self.assertNotIn("mutants-baseline", step.get("run", ""), job)

    def test_python_baseline_runs_per_dir_in_its_own_job(self):
        step = named_step(
            "mutation-py-baseline",
            "Run Python mutation baseline on changed sub-projects",
        )
        self.assertIn("for dir in ${PY_DIRS}", step["run"])
        self.assertIn('make -C "${dir}" mutants-baseline || exit 1', step["run"])
        self.assertNotIn("continue-on-error", step)
        self.assertNotIn("if", step)
        self.assertEqual(
            step["env"]["PY_DIRS"], "${{ needs.mutation-py-plan.outputs.py_dirs }}"
        )

    def test_baseline_installs_run_unconditionally_inside_the_job(self):
        for fragment in ("libgmp-dev", "pip install"):
            found = [
                s
                for s in job_steps("mutation-py-baseline")
                if fragment in s.get("run", "")
            ]
            self.assertEqual(len(found), 1, fragment)
            self.assertNotIn("if", found[0])

    def test_setup_python_is_314_in_baseline_only(self):
        for job in ("mutation-rs-plan", "mutation-rs", "mutation-rs-canary"):
            self.assertEqual(
                [s for s in job_steps(job) if "setup-python" in s.get("uses", "")], []
            )
        found = [
            s
            for s in job_steps("mutation-py-baseline")
            if "setup-python" in s.get("uses", "")
        ]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["with"]["python-version"], "3.14")

    def test_detect_calls_script_in_rs_plan(self):
        found = [s for s in job_steps("mutation-rs-plan") if s.get("id") == "detect"]
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

    def test_no_cargo_install_of_cargo_mutants(self):
        self.assertNotIn("cargo install", PR_WORKFLOW.read_text())

    def test_each_rust_job_installs_pinned_prebuilt_cargo_mutants(self):
        for job in ("mutation-rs-plan", "mutation-rs", "mutation-rs-canary"):
            found = [
                s for s in job_steps(job) if s.get("uses", "").startswith(TAIKI_USES)
            ]
            self.assertEqual(len(found), 1, job)
            self.assertEqual(
                found[0]["with"],
                {"tool": "cargo-mutants@27.1.0", "fallback": "none"},
                job,
            )
            self.assertNotIn("if", found[0], job)

    def test_plan_job_has_no_toolchain_or_gmp_step(self):
        for step in job_steps("mutation-rs-plan"):
            self.assertNotIn("rust-toolchain", step.get("uses", ""))
            self.assertNotIn("gmp-cache-key", step.get("run", ""))

    def test_toolchain_and_gmp_restore_in_shard_and_canary_jobs(self):
        for job in ("mutation-rs", "mutation-rs-canary"):
            steps = job_steps(job)
            names = [s.get("name") for s in steps]
            tool = [s for s in steps if "rust-toolchain" in s.get("uses", "")]
            self.assertEqual(len(tool), 1, job)
            self.assertEqual(tool[0]["with"]["toolchain"], "stable")
            key = named_step(job, "GMP cache key")
            self.assertEqual(key["id"], "gmpkey")
            self.assertNotIn("if", key)
            self.assertIn("scripts/gmp-cache-key.sh", key["run"])
            self.assertIn("GMP_MPFR_SYS_CACHE", key["run"])
            restore = named_step(job, "Restore GMP/MPFR build cache")
            self.assertIn("cache/restore", restore["uses"])
            self.assertEqual(restore["if"], "steps.gmpkey.outputs.enabled == 'true'")
            self.assertEqual(restore["with"]["key"], "${{ steps.gmpkey.outputs.key }}")
            self.assertLess(
                names.index("Restore GMP/MPFR build cache"),
                names.index(RS_RUN_STEP if job == "mutation-rs" else CANARY_STEP),
            )

    def test_shard_step_wiring_and_no_min_caught(self):
        step = named_step("mutation-rs", RS_RUN_STEP)
        self.assertEqual(
            step["env"],
            {
                "CRATE": "${{ matrix.crate }}",
                "K": "${{ matrix.k }}",
                "N": "${{ matrix.n }}",
                "COUNT": "${{ matrix.count }}",
                "GITHUB_BASE_REF": "${{ github.base_ref }}",
            },
        )
        self.assertNotIn("if", step)
        self.assertNotIn("continue-on-error", step)
        for s in pr_steps():
            self.assertNotIn("--min-caught", s.get("run", ""))

    def test_shard_step_run_block_is_the_r6_form(self):
        lines = named_step("mutation-rs", RS_RUN_STEP)["run"].splitlines()
        self.assertEqual(
            lines[:4],
            [
                "set +e",
                'scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" --shard "${K}/${N}" --expect "${COUNT}" "${CRATE}" 2>&1 | tee "${RUNNER_TEMP}/rs.log"',
                "rc=${PIPESTATUS[0]}",
                "set -e",
            ],
        )
        self.assertEqual(lines[-1], 'exit "${rc}"')

    def test_shard_step_passes_shard_expect_and_crate(self):
        for flags in SHELL_FLAGS:
            res = run_shard_step(flags)
            self.assertEqual(res.proc.returncode, 0, res.proc.stderr)
            self.assertEqual(
                res.calls,
                ["origin/master", "--shard", "1/3", "--expect", "7", "a/a-rs"],
            )

    def test_shard_step_propagates_red_under_both_shells(self):
        for flags in SHELL_FLAGS:
            for rc in (1, 2, 3):
                res = run_shard_step(flags, run_rc=rc, stdout="red: boom\n")
                self.assertEqual(res.proc.returncode, rc, (flags, rc, res.proc.stderr))
                self.assertIn("red: boom", res.summary)

    def test_shard_step_streams_the_log_and_fences_matched_lines(self):
        out = "noise\nred: one\nMISSED x\nTIMEOUT y\nrepro: z\nerror: e\ngreen: g\n"
        for flags in SHELL_FLAGS:
            res = run_shard_step(flags, run_rc=3, stdout=out)
            self.assertIn("noise", res.log)
            self.assertIn("noise", res.proc.stdout)
            self.assertEqual(
                res.summary,
                "```\nred: one\nMISSED x\nTIMEOUT y\nrepro: z\nerror: e\ngreen: g\n```\n",
            )

    def test_shard_step_green_with_no_matching_lines_is_green(self):
        for flags in SHELL_FLAGS:
            res = run_shard_step(flags, run_rc=0, stdout="nothing relevant\n")
            self.assertEqual(res.proc.returncode, 0, res.proc.stderr)
            self.assertEqual(res.summary, "```\n```\n")

    def test_canary_step_wiring(self):
        step = named_step("mutation-rs-canary", CANARY_STEP)
        self.assertNotIn("if", step)
        self.assertNotIn("continue-on-error", step)

    def test_canary_edits_commits_only_the_file_plans_and_runs(self):
        res = run_canary()
        self.assertEqual(res.proc.returncode, 0, res.proc.stderr)
        self.assertEqual(res.plan_calls, ["HEAD~1", "amicable/amicable-rs"])
        self.assertEqual(
            res.calls,
            [
                "HEAD~1",
                "--shard",
                "0/1",
                "--expect",
                "5",
                "--min-caught",
                "1",
                "amicable/amicable-rs",
            ],
        )
        # At call time HEAD~1 is the clean tree: the canary commit must precede it.
        # The staged unrelated file shows in the tree-vs-HEAD~1 diff, but the commit
        # itself holds only the canary file (asserted below).
        self.assertEqual(res.diff_at_call, [CANARY_FILE, "other.txt"])
        self.assertEqual(res.committed, [CANARY_FILE])
        repro, fenced = res.summary.split("\n", 1)
        self.assertRegex(
            repro,
            r"^canary repro: git checkout [0-9a-f]{40}, append a space to the "
            r'"let mut m = 2 \* d;" line in amicable/amicable-rs/src/lib\.rs, commit it, '
            r"then scripts/mutation-pr-run\.sh HEAD~1 --shard 0/1 --expect 5 "
            r"--min-caught 1 amicable/amicable-rs$",
        )
        self.assertEqual(fenced, "```\n```\n")
        self.assertIn("let mut m = 2 * d; \n", res.lib)
        self.assertEqual(res.lib.count("let mut m = 2 * d;"), 1)
        self.assertEqual(res.staged_other, ["other.txt"])

    def test_canary_reads_shard_fields_from_the_plan(self):
        res = run_canary(plan='[{"k":2,"n":3,"count":41}]')
        self.assertEqual(res.proc.returncode, 0, res.proc.stderr)
        self.assertEqual(res.calls[1:5], ["--shard", "2/3", "--expect", "41"])

    def test_canary_run_failure_propagates_under_both_shells(self):
        for flags in SHELL_FLAGS:
            for rc in (1, 3):
                res = run_canary(run_rc=rc, flags=flags, run_out="red: nope\n")
                self.assertEqual(res.proc.returncode, rc, (flags, rc, res.proc.stderr))
                self.assertTrue(
                    res.summary.endswith("```\nred: nope\n```\n"), res.summary
                )

    def test_canary_plan_of_zero_or_two_units_is_red_without_a_run(self):
        two = '[{"k":0,"n":1,"count":5},{"k":0,"n":1,"count":6}]'
        for plan, count in (("[]", 0), (two, 2)):
            res = run_canary(plan=plan)
            self.assertEqual(res.proc.returncode, 1, res.proc.stderr)
            self.assertEqual(res.calls, [])
            self.assertIn(
                f"red: canary planned {count} units, expected exactly 1",
                res.summary,
            )

    def test_canary_planner_failure_is_red_without_a_run(self):
        res = run_canary(plan_rc=1)
        self.assertEqual(res.proc.returncode, 1)
        self.assertEqual(res.calls, [])

    def test_canary_zero_matches_is_red_without_edit_or_plan(self):
        res = run_canary(lib="fn main() {}\n")
        self.assertNotEqual(res.proc.returncode, 0)
        self.assertEqual(res.calls, [])
        self.assertEqual(res.plan_calls, [])
        self.assertEqual(res.commit_count, 1)
        self.assertEqual(res.lib, "fn main() {}\n")

    def test_canary_two_matches_is_red_without_edit_or_plan(self):
        lib = "let mut m = 2 * d;\nlet mut m = 2 * d;\n"
        res = run_canary(lib=lib)
        self.assertNotEqual(res.proc.returncode, 0)
        self.assertEqual(res.calls, [])
        self.assertEqual(res.plan_calls, [])
        self.assertEqual(res.commit_count, 1)
        self.assertEqual(res.lib, lib)

    def test_pip_line_matches_template(self):
        # One install line per Python-running job (plan, py, canary, baseline), each
        # identical to the template's, so one version per package across sites.
        lines = pip_lines(PR_WORKFLOW)
        template = pip_lines(TEMPLATE)
        self.assertEqual(len(template), 1)
        self.assertEqual(lines, template * 4)
        for job in (
            "mutation-py-baseline",
            "mutation-py-plan",
            "mutation-py",
            "mutation-py-canary",
        ):
            found = pip_steps(job)
            self.assertEqual(len(found), 1, job)
            self.assertIn("hypothesis", found[0]["run"])
            self.assertEqual(f"run: {found[0]['run'].strip()}", template[0], job)
        for job in ("mutation-rs-plan", "mutation-rs", "mutation-rs-canary"):
            self.assertEqual(pip_steps(job), [], job)


class CanaryRun(NamedTuple):
    proc: subprocess.CompletedProcess[str]
    calls: list[str]
    plan_calls: list[str]
    summary: str
    lib: str
    committed: list[str]
    staged_other: list[str]
    commit_count: int
    diff_at_call: list[str]


def run_canary(
    lib=CANARY_LIB,
    run_rc=0,
    plan='[{"k":0,"n":1,"count":5}]',
    plan_rc=0,
    flags=("-eo", "pipefail"),
    run_out="stub verdict\n",
):
    """Run the canary step in a real throwaway git repo with stub planner and runner."""
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
        plan_log = root / "plan-calls"
        stub_run_script(repo / "scripts" / "mutation-pr-run.sh", log)
        stub_plan_script(repo / "scripts" / "mutation-rs-plan.sh", plan_log)
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
                "STUB_OUT": run_out,
                "PLAN_JSON": plan,
                "PLAN_RC": str(plan_rc),
            }
        )
        proc = run_block(
            named_step("mutation-rs-canary", CANARY_STEP), repo, env, list(flags)
        )
        count = int(run_git("rev-list", "--count", "HEAD").strip())
        committed = run_git("show", "--name-only", "--format=", "HEAD").split()
        staged = run_git("diff", "--cached", "--name-only").split()
        calls = log.read_text().splitlines() if log.exists() else []
        plan_calls = plan_log.read_text().splitlines() if plan_log.exists() else []
        diff_log = pathlib.Path(f"{log}.diff")
        at_call = diff_log.read_text().split() if diff_log.exists() else []
        return CanaryRun(
            proc,
            calls,
            plan_calls,
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


DEFAULT_MANIFESTS = ("a/a-rs/Cargo.toml", "b/b-rs/Cargo.toml")
DEFAULT_PLAN = [
    {"crate": "a/a-rs", "slug": "a-rs-0", "k": 0, "n": 2, "count": 4},
    {"crate": "a/a-rs", "slug": "a-rs-1", "k": 1, "n": 2, "count": 3},
    {"crate": "b/b-rs", "slug": "b-rs-0", "k": 0, "n": 1, "count": 5},
    {
        "crate": "b/b-rs",
        "slug": "b-rs-plan",
        "k": 0,
        "n": 0,
        "count": 0,
        "fault": "listing failed",
    },
]


class SetupRun(NamedTuple):
    proc: "subprocess.CompletedProcess[str]"
    outputs: dict[str, str]
    lines: list[str]
    planner_args: list[str]


def run_rs_setup(
    crate="",
    manifests=DEFAULT_MANIFESTS,
    plan=DEFAULT_PLAN,
    plan_rc=0,
):
    """Execute the setup job's `plan` step against a stub git and planner.

    The stub `git ls-files` prints `manifests`; the stub planner records its
    argv, prints `plan` as JSON on stdout and a `plan:` line on stderr, and exits
    `plan_rc`. Returns a `SetupRun` (proc, outputs dict, raw lines, planner argv).
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        bindir = root / "bin"
        bindir.mkdir()
        listing = root / "manifests"
        listing.write_text("".join(f"{m}\n" for m in manifests))
        git = bindir / "git"
        git.write_text(f'#!/bin/sh\ncat "{listing}"\n')
        git.chmod(0o755)
        ws = root / "ws"
        (ws / "scripts").mkdir(parents=True)
        planner = ws / "scripts" / "mutation-rs-plan.sh"
        planner.write_text(
            "#!/bin/sh\n"
            f'printf \'%s\\n\' "$@" > "{root / "planner-args"}"\n'
            "printf 'plan: stub\\n' >&2\n"
            f'cat "{root / "plan.json"}"\n'
            'exit "$PLAN_RC"\n'
        )
        planner.chmod(0o755)
        (root / "plan.json").write_text(json.dumps(plan))
        out = root / "out"
        out.touch()
        env = {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(out),
            "CRATE": crate,
            "PLAN_RC": str(plan_rc),
        }
        proc = subprocess.run(
            [
                "bash",
                "--noprofile",
                "--norc",
                "-e",
                "-c",
                rs_step("setup", "plan")["run"],
            ],
            env=env,
            cwd=ws,
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
        args_file = root / "planner-args"
        args = args_file.read_text().splitlines() if args_file.exists() else []
        return SetupRun(proc, outputs, raw_lines, args)


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
    def test_empty_crate_plans_every_tracked_crate_whole(self):
        run = run_rs_setup("")
        self.assertEqual(run.proc.returncode, 0, run.proc.stderr)
        self.assertEqual(run.planner_args, ["--whole", "a/a-rs", "b/b-rs"])

    def test_matrix_is_the_plan_and_units_are_its_slugs(self):
        run = run_rs_setup("")
        self.assertEqual(run.proc.returncode, 0, run.proc.stderr)
        self.assertEqual(len(run.lines), 2, run.lines)
        self.assertTrue(run.lines[0].startswith("matrix="), run.lines)
        self.assertTrue(run.lines[1].startswith("units="), run.lines)
        self.assertEqual(json.loads(run.outputs["matrix"]), {"include": DEFAULT_PLAN})
        self.assertEqual(
            run.outputs["units"].split(),
            ["a-rs-0", "a-rs-1", "b-rs-0", "b-rs-plan"],
        )

    def test_planner_stderr_stays_out_of_the_outputs(self):
        run = run_rs_setup("")
        self.assertIn("plan: stub", run.proc.stderr)
        self.assertNotIn("plan: stub", "".join(run.lines))

    def test_planner_failure_fails_setup_with_no_outputs(self):
        run = run_rs_setup("", plan_rc=1)
        self.assertEqual(run.proc.returncode, 1)
        self.assertEqual(run.lines, [])

    def test_empty_plan_refuses_green(self):
        run = run_rs_setup("", plan=[])
        self.assertEqual(run.proc.returncode, 1)
        self.assertIn("refusing to report green", run.proc.stderr)
        self.assertEqual(run.lines, [])

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

    def test_known_crate_is_the_only_planner_argument(self):
        run = run_rs_setup("b/b-rs")
        self.assertEqual(run.proc.returncode, 0, run.proc.stderr)
        self.assertEqual(run.planner_args, ["--whole", "b/b-rs"])

    def test_unknown_crate_refused_before_the_planner_runs(self):
        run = run_rs_setup("nope/nope-rs")
        self.assertEqual(run.proc.returncode, 1)
        self.assertIn("nope/nope-rs", run.proc.stderr)
        self.assertEqual(run.lines, [])
        self.assertEqual(run.planner_args, [])

    def test_newline_injection_refused(self):
        run = run_rs_setup("a/a-rs\nevil=1")
        self.assertEqual(run.proc.returncode, 1)
        self.assertIn("evil=1", run.proc.stderr)
        self.assertNotIn("evil", run.outputs)
        self.assertEqual(run.lines, [])
        self.assertEqual(run.planner_args, [])

    def test_no_tracked_crates_refuses_green(self):
        run = run_rs_setup("", manifests=())
        self.assertEqual(run.proc.returncode, 1)
        self.assertIn("refusing to report green", run.proc.stderr)
        self.assertEqual(run.lines, [])
        self.assertEqual(run.planner_args, [])

    def test_every_real_tracked_crate_passes_the_input_check(self):
        dirs = tracked_crate_dirs()
        self.assertEqual(len(dirs), 13)
        self.assertFalse([d for d in dirs if d.startswith("tests/")])
        manifests = [f"{d}/Cargo.toml" for d in dirs]
        for d in dirs:
            with self.subTest(crate=d):
                run = run_rs_setup(d, manifests=manifests)
                self.assertEqual(run.proc.returncode, 0, run.proc.stderr)
                self.assertEqual(run.planner_args, ["--whole", d])

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

    def test_setup_installs_pinned_cargo_mutants_before_planning(self):
        steps = rs_job("setup")["steps"]
        names = [s.get("name") for s in steps]
        install = names.index("Install cargo-mutants")
        self.assertLess(install, names.index("List crates and build matrix"))
        self.assertEqual(steps[install]["with"]["tool"], "cargo-mutants@27.1.0")
        self.assertEqual(steps[install]["with"]["fallback"], "none")


class JobResult(tuple):  # type: ignore[type-arg]
    """The (proc, make calls, statuses, summary) tuple plus classifier records.

    `classifier_argc` lists the argument count of each mutation-classify.sh call;
    `classifier_args` lists its fourth and fifth arguments, one string per call;
    `shards` lists the MUTANT_SHARD argument of each make call.
    """

    classifier_argc: list[str]
    classifier_args: list[str]
    shards: list[str]

    def __new__(cls, fields, classifier_argc, classifier_args, shards):
        self = super().__new__(cls, fields)
        self.classifier_argc = classifier_argc
        self.classifier_args = classifier_args
        self.shards = shards
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
    shard=("0", "2"),
    count: int | str = 3,
    total=None,
    fault="",
):
    """Execute a `mutants` job step against stub make/classifier.

    Returns (proc, make_calls, {status filename: content}, step summary). The
    make stub exits `stub.make_rc` (cargo-mutants exits 2 for survivors, 3 for
    timeouts, both green by policy) and writes `<crate>/mutants.out/exit-code`
    holding `stub.exit_code` (default: `make_rc`; None writes no file, as when the
    recipe died before cargo-mutants ran). The classifier stub echoes the exit code
    and outcomes path it was given, and reports red (exit 1) when `stub.red`, green
    otherwise. `pre_status` seeds status/<slug> before the step runs. The make
    stub writes `<crate>/mutants.out/outcomes.json` with `total` mutants (default
    `count`, the plan's figure) and records its MUTANT_SHARD argument; `shard` is
    the plan's (k, n) and `fault` its fault text (empty for a normal unit).
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
            f'printf \'%s\\n\' "$4" >> "{root / "shards"}"\n'
            'mkdir -p "$2/mutants.out"\n'
            'printf \'{"total_mutants": %s}\\n\' "$OUTCOMES_TOTAL" > "$2/mutants.out/outcomes.json"\n'
            'if [ -n "${EXIT_CODE_FILE_VALUE+x}" ]; then\n'
            '  mkdir -p "$2/mutants.out"\n'
            '  printf \'%s\\n\' "$EXIT_CODE_FILE_VALUE" > "$2/mutants.out/exit-code"\n'
            "fi\n"
            'exit "$MAKE_RC"\n'
        )
        make.chmod(0o755)
        workspace = root / "ws"
        (workspace / "scripts").mkdir(parents=True)
        for helper in ("mutation-exit-code.sh", "mutation-shard-count.sh"):
            shutil.copy(REPO_ROOT / "scripts" / helper, workspace / "scripts" / helper)
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
            "K": shard[0],
            "N": shard[1],
            "COUNT": str(count),
            "FAULT": fault,
            "OUTCOMES_TOTAL": str(count if total is None else total),
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
                "-e",
                "-c",
                rs_step("mutants", step)["run"],
            ],
            env=env,
            cwd=workspace,
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
        shards_file = root / "shards"
        shards = shards_file.read_text().splitlines() if shards_file.exists() else []
        return JobResult(
            (proc, made, statuses, summary.read_text()), argc, args, shards
        )


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
                line = (
                    f"red: a/a-rs - mutants.out/exit-code '{bad}' is not an integer\n"
                )
                self.assertEqual(statuses, {"a-a-rs": line})
                self.assertEqual(summary, line)
                self.assertEqual(result.classifier_argc, [])

    def test_step_calls_shared_exit_code_helper_not_inline_rules(self):
        run = rs_step("mutants", "Run mutants")["run"]
        self.assertIn('bash scripts/mutation-exit-code.sh "${CRATE_DIR}"', run)
        self.assertNotIn("code_file=", run)
        self.assertNotIn("[0-9]{0,2}", run)

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
        taiki = rs_step("mutants", "Install cargo-mutants")
        self.assertEqual(taiki["uses"].split("@")[0], "taiki-e/install-action")
        self.assertEqual(taiki["with"]["tool"], "cargo-mutants@27.1.0")
        self.assertEqual(taiki["with"]["fallback"], "none")
        self.assertNotIn("run", taiki)
        restore = rs_step("mutants", "Restore GMP/MPFR build cache")
        self.assertEqual(restore["uses"].split("@")[0], "actions/cache/restore")
        self.assertEqual(restore["if"], "steps.gmpkey.outputs.enabled == 'true'")
        self.assertEqual(
            rs_step("mutants", "Record unfinished crate")["if"], "cancelled()"
        )

    def test_run_step_env_from_matrix(self):
        env = rs_step("mutants", "Run mutants")["env"]
        self.assertEqual(env["CRATE_DIR"], "${{ matrix.crate }}")
        self.assertEqual(env["SLUG"], "${{ matrix.slug }}")
        self.assertEqual(env["K"], "${{ matrix.k }}")
        self.assertEqual(env["N"], "${{ matrix.n }}")
        self.assertEqual(env["COUNT"], "${{ matrix.count }}")
        self.assertEqual(env["FAULT"], "${{ matrix.fault }}")

    def test_job_name_is_the_slug(self):
        self.assertEqual(rs_job("mutants")["name"], "Mutation ${{ matrix.slug }}")

    def test_shard_reaches_make(self):
        result = run_crate_job("a/a-rs", "a-rs-3", shard=("3", "4"))
        self.assertEqual(result[0].returncode, 0, result[0].stderr)
        self.assertEqual(result.shards, ["MUTANT_SHARD=3/4"])

    def test_count_mismatch_is_red_never_classified(self):
        result = run_crate_job("a/a-rs", "a-rs-0", count=3, total=2)
        proc, made, statuses, summary = result
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(made, ["a/a-rs"])
        line = "red: a-rs-0 tested 2 mutants, plan expected 3\n"
        self.assertEqual(statuses, {"a-rs-0": line})
        self.assertEqual(summary, line)
        self.assertEqual(result.classifier_argc, [])

    def test_count_check_usage_error_is_red_never_classified(self):
        # An empty COUNT makes the helper exit 2 with nothing on stdout; the
        # step must still write a red line rather than a blank status.
        result = run_crate_job("a/a-rs", "a-rs-0", count="", total=0)
        proc, _made, statuses, summary = result
        self.assertEqual(proc.returncode, 1)
        line = "red: a-rs-0 - shard count check failed (exit 2)\n"
        self.assertEqual(statuses, {"a-rs-0": line})
        self.assertEqual(summary, line)
        self.assertEqual(result.classifier_argc, [])

    def test_count_match_goes_on_to_the_classifier(self):
        result = run_crate_job("a/a-rs", "a-rs-0", count=3, total=3)
        self.assertEqual(result[0].returncode, 0, result[0].stderr)
        self.assertEqual(result.classifier_argc, ["5"])

    def test_fault_unit_is_red_and_never_runs_make(self):
        result = run_crate_job(
            "a/a-rs",
            "a-rs-plan",
            shard=("0", "0"),
            count=0,
            fault="listing failed",
        )
        proc, made, statuses, summary = result
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(made, [])
        line = "red: a-rs-plan - plan fault: listing failed\n"
        self.assertEqual(statuses, {"a-rs-plan": line})
        self.assertEqual(summary, line)
        self.assertEqual(result.classifier_argc, [])

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


# --- mutation-pr.yml: Python jobs and the aggregator (slice 8) ---------------

PR_JOB_IDS = {
    "mutation-py-plan",
    "mutation-py",
    "mutation-py-canary",
    "mutation-py-baseline",
    "mutation-rs-plan",
    "mutation-rs",
    "mutation-rs-canary",
    "mutation-pr",
}
RS_PLAN_OUT = "needs.mutation-rs-plan.outputs"
PLAN_OUT = "needs.mutation-py-plan.outputs"


def pr_jobs():
    return load(PR_WORKFLOW)["jobs"]


def job_steps(job):
    return pr_jobs()[job]["steps"]


def pip_steps(job):
    return [s for s in job_steps(job) if s.get("run", "").startswith("pip install")]


def named_step(job, name):
    found = [s for s in job_steps(job) if s.get("name") == name]
    assert len(found) == 1, (job, name)
    return found[0]


class PrJobGraphTests(unittest.TestCase):
    def test_eight_job_ids(self):
        self.assertEqual(set(pr_jobs()), PR_JOB_IDS)

    def test_needs(self):
        jobs = pr_jobs()
        self.assertNotIn("needs", jobs["mutation-py-plan"])
        self.assertNotIn("needs", jobs["mutation-rs-plan"])
        self.assertEqual(jobs["mutation-py"]["needs"], ["mutation-py-plan"])
        self.assertEqual(jobs["mutation-py-canary"]["needs"], ["mutation-py-plan"])
        self.assertEqual(jobs["mutation-py-baseline"]["needs"], ["mutation-py-plan"])
        self.assertEqual(jobs["mutation-rs"]["needs"], ["mutation-rs-plan"])
        self.assertEqual(jobs["mutation-rs-canary"]["needs"], ["mutation-rs-plan"])
        self.assertEqual(
            set(jobs["mutation-pr"]["needs"]), PR_JOB_IDS - {"mutation-pr"}
        )

    def test_conditions(self):
        jobs = pr_jobs()
        self.assertNotIn("if", jobs["mutation-py-plan"])
        self.assertNotIn("if", jobs["mutation-rs-plan"])
        self.assertEqual(jobs["mutation-py"]["if"], f"{PLAN_OUT}.units != '[]'")
        self.assertEqual(
            jobs["mutation-py-canary"]["if"], f"{PLAN_OUT}.py_canary == 'true'"
        )
        self.assertEqual(
            jobs["mutation-py-baseline"]["if"], f"{PLAN_OUT}.has_py == 'true'"
        )
        self.assertEqual(jobs["mutation-rs"]["if"], f"{RS_PLAN_OUT}.units != '[]'")
        self.assertEqual(
            jobs["mutation-rs-canary"]["if"], f"{RS_PLAN_OUT}.rs_canary == 'true'"
        )
        self.assertEqual(jobs["mutation-pr"]["if"], "always()")

    def test_timeouts(self):
        jobs = pr_jobs()
        expected = {
            "mutation-py": 30,
            "mutation-py-baseline": 30,
            "mutation-rs-plan": 30,
            "mutation-rs": 60,
            "mutation-rs-canary": 30,
        }
        for job, minutes in expected.items():
            self.assertEqual(jobs[job]["timeout-minutes"], minutes, job)
        for job in PR_JOB_IDS:
            self.assertIsInstance(jobs[job]["timeout-minutes"], int, job)

    def test_rs_matrix_from_plan_units_and_leg_name(self):
        job = pr_jobs()["mutation-rs"]
        self.assertEqual(
            job["strategy"],
            {
                "fail-fast": False,
                "matrix": {
                    "include": "${{ fromJSON(needs.mutation-rs-plan.outputs.units) }}"
                },
            },
        )
        self.assertEqual(job["name"], "mutation-rs ${{ matrix.slug }}")

    def test_rs_plan_outputs(self):
        self.assertEqual(
            pr_jobs()["mutation-rs-plan"]["outputs"],
            {
                "units": "${{ steps.plan.outputs.units }}",
                "rs_canary": "${{ steps.detect.outputs.rs_canary }}",
            },
        )

    def test_rs_units_shape_supplies_every_matrix_key_the_job_uses(self):
        units = json.loads('[{"crate":"a/a-rs","slug":"a-0","k":0,"n":1,"count":5}]')
        text = yaml.safe_dump(pr_jobs()["mutation-rs"])
        used = set(re.findall(r"matrix\.(\w+)", text))
        self.assertEqual(used, {"crate", "slug", "k", "n", "count"})
        self.assertTrue(used <= set(units[0]))

    def test_aggregator_keeps_required_check_name(self):
        # The branch-protection context is the job id; a `name:` would rename it.
        self.assertNotIn("name", pr_jobs()["mutation-pr"])

    def test_every_action_is_sha_pinned_and_no_continue_on_error(self):
        for job, body in pr_jobs().items():
            self.assertNotIn("continue-on-error", body, job)
            for step in body["steps"]:
                self.assertNotIn("continue-on-error", step, (job, step))
                uses = step.get("uses")
                if uses:
                    self.assertRegex(uses, r"@[0-9a-f]{40}$", (job, uses))

    def test_no_expression_syntax_in_any_run_block(self):
        for job in pr_jobs():
            for step in job_steps(job):
                self.assertNotIn("${{", step.get("run", ""), (job, step))

    def test_permissions_stay_read_only(self):
        self.assertEqual(load(PR_WORKFLOW)["permissions"], {"contents": "read"})
        for job, body in pr_jobs().items():
            self.assertNotIn("permissions", body, job)

    def test_rust_jobs_never_execute_cosmic_ray(self):
        # The Rust jobs run no Python mutation session; sessions belong to mutation-py*.
        for job in ("mutation-rs-plan", "mutation-rs", "mutation-rs-canary"):
            for step in job_steps(job):
                self.assertNotIn("cosmic-ray exec", step.get("run", ""))
                self.assertNotIn("mutants-diff", step.get("run", ""))


class PrPlanJobTests(unittest.TestCase):
    def test_outputs(self):
        outs = pr_jobs()["mutation-py-plan"]["outputs"]
        self.assertEqual(
            set(outs),
            {"units", "base", "py_src_dirs", "py_canary", "has_py", "py_dirs"},
        )
        self.assertEqual(outs["has_py"], "${{ steps.detect.outputs.has_py }}")
        self.assertEqual(outs["py_dirs"], "${{ steps.detect.outputs.py_dirs }}")
        self.assertEqual(outs["units"], "${{ steps.plan.outputs.units }}")
        self.assertEqual(outs["base"], "${{ steps.base.outputs.sha }}")
        self.assertEqual(outs["py_src_dirs"], "${{ steps.detect.outputs.py_src_dirs }}")
        self.assertEqual(outs["py_canary"], "${{ steps.detect.outputs.py_canary }}")

    def test_checkout_is_full_depth(self):
        step = job_steps("mutation-py-plan")[0]
        self.assertIn("actions/checkout@", step["uses"])
        self.assertEqual(step["with"]["fetch-depth"], 0)

    def test_detect_and_merge_base(self):
        detect = named_step("mutation-py-plan", "Detect changed sub-projects")
        self.assertEqual(detect["id"], "detect")
        self.assertEqual(
            detect["run"].strip(),
            'scripts/mutation-pr-detect.sh "origin/${GITHUB_BASE_REF}" >> "${GITHUB_OUTPUT}"',
        )
        self.assertEqual(detect["env"]["GITHUB_BASE_REF"], "${{ github.base_ref }}")
        base = named_step("mutation-py-plan", "Resolve merge base")
        self.assertEqual(base["id"], "base")
        self.assertIn('git merge-base "origin/${GITHUB_BASE_REF}" HEAD', base["run"])
        self.assertIn("sha=", base["run"])

    def test_plan_step_is_unconditional_and_always_sets_units(self):
        step = named_step("mutation-py-plan", "Plan Python mutation units")
        self.assertEqual(step["id"], "plan")
        self.assertNotIn("if", step)
        self.assertEqual(
            step["env"]["PY_SRC_DIRS"], "${{ steps.detect.outputs.py_src_dirs }}"
        )
        self.assertEqual(step["env"]["BASE_SHA"], "${{ steps.base.outputs.sha }}")
        self.assertIn("scripts/mutation-pr-plan-python.sh", step["run"])
        self.assertIn('"${BASE_SHA}"', step["run"])
        self.assertIn("units=", step["run"])
        self.assertIn("units.json", step["run"])

    def test_install_conditions_follow_py_src_dirs(self):
        cond = "steps.detect.outputs.py_src_dirs != ''"
        for fragment in ("libgmp-dev", "pip install"):
            found = [
                s for s in job_steps("mutation-py-plan") if fragment in s.get("run", "")
            ]
            self.assertEqual(len(found), 1, fragment)
            self.assertEqual(found[0]["if"], cond)
        setup = [
            s
            for s in job_steps("mutation-py-plan")
            if "setup-python" in s.get("uses", "")
        ]
        self.assertEqual(len(setup), 1)
        self.assertEqual(setup[0]["if"], cond)
        self.assertEqual(setup[0]["with"]["python-version"], "3.14")

    def test_installs_precede_plan(self):
        names = [s.get("name") for s in job_steps("mutation-py-plan")]
        plan = names.index("Plan Python mutation units")
        detect = names.index("Detect changed sub-projects")
        for step in job_steps("mutation-py-plan"):
            if "pip install" in step.get("run", "") or "libgmp-dev" in step.get(
                "run", ""
            ):
                idx = job_steps("mutation-py-plan").index(step)
                self.assertGreater(idx, detect)
                self.assertLess(idx, plan)

    def test_plan_artifact_uploaded_for_aggregator(self):
        found = [
            s
            for s in job_steps("mutation-py-plan")
            if "upload-artifact" in s.get("uses", "")
        ]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["with"]["name"], "mutants-pr-plan")
        self.assertIn("plan.txt", found[0]["with"]["path"])
        self.assertEqual(found[0]["if"], "always()")
        # Overwrite so a re-run attempt replaces the earlier plan artifact.
        self.assertIs(found[0]["with"]["overwrite"], True)


class PrRsPlanJobTests(unittest.TestCase):
    def plan_step(self):
        return named_step("mutation-rs-plan", "Plan Rust mutation shards")

    def run_plan(self, rs_dirs, plan_json="[]", plan_rc=0):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            log = root / "calls"
            stub_plan_script(root / "repo" / "scripts" / "mutation-rs-plan.sh", log)
            (root / "temp").mkdir()
            out = root / "out"
            out.touch()
            env = {
                "PATH": os.environ["PATH"],
                "RS_DIRS": rs_dirs,
                "GITHUB_BASE_REF": "master",
                "RUNNER_TEMP": str(root / "temp"),
                "GITHUB_OUTPUT": str(out),
                "PLAN_JSON": plan_json,
                "PLAN_RC": str(plan_rc),
            }
            proc = run_block(self.plan_step(), root / "repo", env, ["-e"])
            calls = log.read_text().splitlines() if log.exists() else []
            return proc, calls, out.read_text()

    def test_checkout_is_full_depth(self):
        step = job_steps("mutation-rs-plan")[0]
        self.assertIn("actions/checkout@", step["uses"])
        self.assertEqual(step["with"]["fetch-depth"], 0)

    def test_plan_step_wiring(self):
        step = self.plan_step()
        self.assertEqual(step["id"], "plan")
        self.assertNotIn("if", step)
        self.assertEqual(step["env"]["RS_DIRS"], "${{ steps.detect.outputs.rs_dirs }}")
        self.assertEqual(step["env"]["GITHUB_BASE_REF"], "${{ github.base_ref }}")

    def test_plan_step_follows_detect_and_install(self):
        names = [s.get("name") for s in job_steps("mutation-rs-plan")]
        self.assertLess(
            names.index("Detect changed sub-projects"),
            names.index("Plan Rust mutation shards"),
        )
        self.assertLess(
            names.index("Install cargo-mutants"),
            names.index("Plan Rust mutation shards"),
        )

    def test_empty_dirs_write_empty_units_without_planning(self):
        proc, calls, out = self.run_plan("")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(calls, [])
        self.assertEqual(out, "units=[]\n")

    def test_dirs_are_planned_against_the_base_and_units_come_from_stdout(self):
        units = '[{"crate":"a/a-rs","slug":"a-0","k":0,"n":1,"count":5}]'
        proc, calls, out = self.run_plan("a/a-rs b/b-rs", plan_json=units)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(calls, ["origin/master", "a/a-rs", "b/b-rs"])
        # The planner's stderr lines never reach the output.
        self.assertEqual(out, f"units={units}\n")

    def test_red_plan_fails_the_step_without_writing_units(self):
        proc, calls, out = self.run_plan("a/a-rs", plan_json="[]", plan_rc=1)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(calls, ["origin/master", "a/a-rs"])
        self.assertEqual(out, "")


class PrBaselineJobTests(unittest.TestCase):
    def test_checkout_full_depth(self):
        self.assertEqual(job_steps("mutation-py-baseline")[0]["with"]["fetch-depth"], 0)

    def test_baseline_step_is_last(self):
        steps = job_steps("mutation-py-baseline")
        self.assertIn("mutants-baseline", steps[-1]["run"])


class PrPyJobTests(unittest.TestCase):
    def test_matrix_from_plan_units(self):
        # strategy.matrix must be a mapping: a bare fromJSON array is rejected at
        # evaluation, so the units array goes under `include`.
        strategy = pr_jobs()["mutation-py"]["strategy"]
        self.assertEqual(
            strategy["matrix"],
            {"include": "${{ fromJSON(needs.mutation-py-plan.outputs.units) }}"},
        )
        self.assertIs(strategy["fail-fast"], False)

    def test_units_shape_supplies_every_matrix_key_the_job_uses(self):
        # The plan script writes units.json as an array of {dir, k, n} objects.
        units = json.loads('[{"dir":"sq","k":0,"n":1}]')
        self.assertIsInstance(units, list)
        include = pr_jobs()["mutation-py"]["strategy"]["matrix"]["include"]
        self.assertIn("outputs.units", include)
        text = yaml.safe_dump(pr_jobs()["mutation-py"]["steps"])
        used = set(re.findall(r"matrix\.(\w+)", text))
        self.assertEqual(used, {"dir", "k", "n"})
        self.assertTrue(used <= set(units[0]))

    def test_checkout_full_depth_and_python_314(self):
        steps = job_steps("mutation-py")
        self.assertEqual(steps[0]["with"]["fetch-depth"], 0)
        setup = [s for s in steps if "setup-python" in s.get("uses", "")]
        self.assertEqual(setup[0]["with"]["python-version"], "3.14")

    def test_installs_run_unconditionally_inside_the_job(self):
        for fragment in ("libgmp-dev", "pip install"):
            found = [
                s for s in job_steps("mutation-py") if fragment in s.get("run", "")
            ]
            self.assertEqual(len(found), 1, fragment)
            self.assertNotIn("if", found[0])

    def test_mutants_diff_step(self):
        step = named_step("mutation-py", "Run mutants on changed lines")
        self.assertEqual(step["env"]["DIR"], "${{ matrix.dir }}")
        self.assertEqual(step["env"]["K"], "${{ matrix.k }}")
        self.assertEqual(step["env"]["N"], "${{ matrix.n }}")
        self.assertEqual(
            step["env"]["BASE_SHA"], "${{ needs.mutation-py-plan.outputs.base }}"
        )
        self.assertNotIn("if", step)
        run = step["run"]
        self.assertIn('scripts/mutation-pr-diff.sh "${BASE_SHA}" "${DIR}"', run)
        self.assertIn('make -C "${DIR}" mutants-diff', run)
        self.assertIn('MUTANT_SHARD="${K}/${N}"', run)
        self.assertIn('STATUS_OUT="${RUNNER_TEMP}/status/${DIR}-${K}"', run)

    def test_status_upload_survives_a_red_unit(self):
        steps = job_steps("mutation-py")
        up = [s for s in steps if "upload-artifact" in s.get("uses", "")]
        self.assertEqual(len(up), 1)
        self.assertEqual(up[0]["if"], "always()")
        self.assertEqual(
            up[0]["with"]["name"], "mutants-pr-status-${{ matrix.dir }}-${{ matrix.k }}"
        )
        self.assertIs(up[0]["with"]["overwrite"], True)
        self.assertEqual(
            up[0]["with"]["path"],
            "${{ runner.temp }}/status/${{ matrix.dir }}-${{ matrix.k }}",
        )
        run_idx = [s.get("name") for s in steps].index("Run mutants on changed lines")
        self.assertGreater(steps.index(up[0]), run_idx)


class PrCanaryJobTests(unittest.TestCase):
    def setUp(self):
        self.step = named_step("mutation-py-canary", "Gate canary (sq)")

    def test_installs_toolchain_unconditionally_inside_the_job(self):
        steps = job_steps("mutation-py-canary")
        for fragment in ("libgmp-dev", "pip install"):
            found = [s for s in steps if fragment in s.get("run", "")]
            self.assertEqual(len(found), 1, fragment)
            self.assertNotIn("if", found[0])
        self.assertEqual(steps[0]["with"]["fetch-depth"], 0)

    def test_timeout(self):
        self.assertEqual(pr_jobs()["mutation-py-canary"]["timeout-minutes"], 30)

    def run_canary_step(self, make_rc, verdict_rc):
        """Run the real canary run: text against stub make, plan, diff and verdict."""
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            make = bin_dir / "make"
            make.write_text('#!/bin/sh\nexit "${MAKE_RC}"\n')
            make.chmod(0o755)
            scripts = root / "scripts"
            scripts.mkdir()
            stubs = {
                "mutation-pr-plan-python.sh": "exit 0\n",
                "mutation-pr-diff.sh": "exit 0\n",
                "mutation-pr-verdict-python.sh": 'exit "${VERDICT_RC}"\n',
            }
            for name, body in stubs.items():
                stub = scripts / name
                stub.write_text("#!/bin/sh\n" + body)
                stub.chmod(0o755)
            (root / "sq").mkdir()
            (root / "sq" / "sq.py").write_text(
                "def f(max_digits):\n    limit = 10**max_digits\n"
            )
            summary = root / "summary"
            summary.touch()
            temp = root / "temp"
            temp.mkdir()
            env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
            env.update(
                PATH=f"{bin_dir}:{os.environ['PATH']}",
                RUNNER_TEMP=str(temp),
                GITHUB_STEP_SUMMARY=str(summary),
                MAKE_RC=str(make_rc),
                VERDICT_RC=str(verdict_rc),
            )
            ident = ["-c", "user.name=t", "-c", "user.email=t@localhost"]
            for cmd in (
                ["init", "-q"],
                ["add", "."],
                [*ident, "commit", "-q", "-m", "base"],
            ):
                subprocess.run(
                    ["git", *cmd],
                    cwd=root,
                    env=env,
                    check=True,
                    capture_output=True,
                    stdin=subprocess.DEVNULL,
                )
            proc = subprocess.run(
                [
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-eo",
                    "pipefail",
                    "-c",
                    self.step["run"],
                ],
                env=env,
                cwd=root,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
            return proc

    def test_exit_is_green_only_when_make_and_verdict_are_green(self):
        for make_rc in (0, 1):
            for verdict_rc in (0, 1):
                proc = self.run_canary_step(make_rc, verdict_rc)
                expected = 0 if (make_rc, verdict_rc) == (0, 0) else 1
                self.assertEqual(
                    proc.returncode, expected, (make_rc, verdict_rc, proc.stderr)
                )

    def test_mechanics(self):
        run = self.step["run"]
        self.assertIn("sq/sq.py", run)
        self.assertIn("limit = 10", run)
        self.assertIn("git -c user.name=ci -c user.email=ci@localhost commit", run)
        self.assertNotIn("git config", run)
        self.assertIn("mutation-pr-plan-python.sh HEAD~1 sq", run)
        self.assertIn("mutation-pr-diff.sh HEAD~1 sq", run)
        self.assertIn("MUTANT_SHARD=0/1", run)
        self.assertIn("--min-killed 1", run)
        self.assertIn("--expected-dirs sq", run)
        self.assertIn("mutation-pr-plan-python.sh", run)
        self.assertIn("mutation-pr-verdict-python.sh", run)
        self.assertNotIn("if", self.step)

    def test_guard_runs_before_any_edit(self):
        run = self.step["run"]
        self.assertLess(run.index("exit 1"), run.index("sed -i"))
        commit = run.index("git -c user.name=ci")
        self.assertLess(run.index("sed -i"), commit)
        self.assertLess(commit, run.index("make -C sq mutants-diff"))

    def test_wrong_match_count_is_red_without_edit(self):
        for body in ("def f():\n    pass\n", "    limit = 10**max_digits\n" * 2):
            with tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                (root / "sq").mkdir()
                (root / "sq" / "sq.py").write_text(body)
                summary = root / "summary"
                summary.touch()
                env = {
                    "PATH": os.environ["PATH"],
                    "RUNNER_TEMP": str(root),
                    "GITHUB_STEP_SUMMARY": str(summary),
                }
                proc = subprocess.run(
                    [
                        "bash",
                        "--noprofile",
                        "--norc",
                        "-eo",
                        "pipefail",
                        "-c",
                        self.step["run"],
                    ],
                    env=env,
                    cwd=root,
                    capture_output=True,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    check=False,
                )
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertEqual((root / "sq" / "sq.py").read_text(), body)
                self.assertIn("red:", summary.read_text())


class PrAggregatorTests(unittest.TestCase):
    def setUp(self):
        self.check = named_step("mutation-pr", "Check job results")

    def run_check(self, **overrides):
        env = {
            "PATH": os.environ["PATH"],
            "RS_PLAN_RESULT": "success",
            "RS_RESULT": "success",
            "RS_UNITS": '[{"crate":"a/a-rs"}]',
            "RS_CANARY_RESULT": "success",
            "RS_CANARY": "true",
            "PYB_RESULT": "success",
            "HAS_PY": "true",
            "PLAN_RESULT": "success",
            "PY_RESULT": "success",
            "CANARY_RESULT": "success",
            "UNITS": '[{"dir":"pi","k":0,"n":1}]',
            "PY_CANARY": "true",
        }
        env.update(overrides)
        with tempfile.TemporaryDirectory() as tmp:
            summary = pathlib.Path(tmp) / "summary"
            summary.touch()
            env["GITHUB_STEP_SUMMARY"] = str(summary)
            proc = subprocess.run(
                [
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-eo",
                    "pipefail",
                    "-c",
                    self.check["run"],
                ],
                env=env,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
            return proc.returncode

    def test_verdict_runs_after_a_failed_result_check(self):
        # A unit with a survivor makes its make step fail, so mutation-py's
        # result is failure and the check step exits 1. The verdict must still
        # run then, or the survivor keys and the MUTANT_SHARD repro it prints
        # never reach the author. The job stays red through the check step.
        plan = named_step("mutation-pr", "Download plan")
        statuses = named_step("mutation-pr", "Download unit statuses")
        verdict = named_step("mutation-pr", "Python verdict")
        self.assertEqual(plan["if"], "${{ !cancelled() }}")
        self.assertEqual(verdict["if"], "${{ !cancelled() }}")
        self.assertEqual(
            statuses["if"],
            "${{ !cancelled() && needs.mutation-py-plan.outputs.units != '[]' }}",
        )

    def test_check_step_env_wiring(self):
        env = self.check["env"]
        self.assertEqual(env["RS_PLAN_RESULT"], "${{ needs.mutation-rs-plan.result }}")
        self.assertEqual(env["RS_RESULT"], "${{ needs.mutation-rs.result }}")
        self.assertEqual(env["RS_UNITS"], f"${{{{ {RS_PLAN_OUT}.units }}}}")
        self.assertEqual(
            env["RS_CANARY_RESULT"], "${{ needs.mutation-rs-canary.result }}"
        )
        self.assertEqual(env["RS_CANARY"], f"${{{{ {RS_PLAN_OUT}.rs_canary }}}}")
        self.assertEqual(env["PYB_RESULT"], "${{ needs.mutation-py-baseline.result }}")
        self.assertEqual(env["HAS_PY"], f"${{{{ {PLAN_OUT}.has_py }}}}")
        self.assertEqual(env["PLAN_RESULT"], "${{ needs.mutation-py-plan.result }}")
        self.assertEqual(env["PY_RESULT"], "${{ needs.mutation-py.result }}")
        self.assertEqual(env["CANARY_RESULT"], "${{ needs.mutation-py-canary.result }}")
        self.assertEqual(env["UNITS"], f"${{{{ {PLAN_OUT}.units }}}}")
        self.assertEqual(env["PY_CANARY"], f"${{{{ {PLAN_OUT}.py_canary }}}}")
        self.assertNotIn("if", self.check)

    def test_all_success_is_green(self):
        self.assertEqual(self.run_check(), 0)

    def test_nothing_to_test_with_every_skip_explained_is_green(self):
        self.assertEqual(
            self.run_check(
                PY_RESULT="skipped",
                CANARY_RESULT="skipped",
                UNITS="[]",
                PY_CANARY="false",
                RS_RESULT="skipped",
                RS_UNITS="[]",
                RS_CANARY_RESULT="skipped",
                RS_CANARY="false",
                PYB_RESULT="skipped",
                HAS_PY="false",
            ),
            0,
        )

    def test_unexplained_skips_are_red(self):
        # py skipped although units exist; canary skipped although it was due.
        self.assertEqual(self.run_check(PY_RESULT="skipped"), 1)
        self.assertEqual(self.run_check(CANARY_RESULT="skipped"), 1)

    def test_skip_explained_only_by_its_own_condition(self):
        # canary success while not due still passes the result check (a run is not a skip).
        self.assertEqual(self.run_check(PY_CANARY="false"), 0)

    def test_rs_plan_must_be_success(self):
        self.assertEqual(self.run_check(RS_PLAN_RESULT="success"), 0)
        for bad in ("failure", "cancelled", "skipped", ""):
            self.assertEqual(self.run_check(RS_PLAN_RESULT=bad), 1, bad)

    def test_rs_result_rule(self):
        self.assertEqual(self.run_check(RS_RESULT="success"), 0)
        self.assertEqual(self.run_check(RS_RESULT="skipped", RS_UNITS="[]"), 0)
        # skipped with units pending, or with an unset units output, is red.
        self.assertEqual(self.run_check(RS_RESULT="skipped"), 1)
        self.assertEqual(self.run_check(RS_RESULT="skipped", RS_UNITS=""), 1)
        for bad in ("failure", "cancelled", ""):
            self.assertEqual(self.run_check(RS_RESULT=bad, RS_UNITS="[]"), 1, bad)

    def test_rs_canary_rule(self):
        self.assertEqual(self.run_check(RS_CANARY_RESULT="success"), 0)
        self.assertEqual(
            self.run_check(RS_CANARY_RESULT="skipped", RS_CANARY="false"), 0
        )
        self.assertEqual(
            self.run_check(RS_CANARY_RESULT="skipped", RS_CANARY="true"), 1
        )
        for bad in ("failure", "cancelled", ""):
            self.assertEqual(
                self.run_check(RS_CANARY_RESULT=bad, RS_CANARY="false"), 1, bad
            )

    def test_py_baseline_rule(self):
        self.assertEqual(self.run_check(PYB_RESULT="success"), 0)
        self.assertEqual(self.run_check(PYB_RESULT="skipped", HAS_PY="false"), 0)
        self.assertEqual(self.run_check(PYB_RESULT="skipped", HAS_PY="true"), 1)
        for bad in ("failure", "cancelled", ""):
            self.assertEqual(self.run_check(PYB_RESULT=bad, HAS_PY="false"), 1, bad)

    def test_failure_and_cancelled_are_red_for_each_job(self):
        for var in (
            "RS_PLAN_RESULT",
            "RS_RESULT",
            "RS_CANARY_RESULT",
            "PYB_RESULT",
            "PLAN_RESULT",
            "PY_RESULT",
            "CANARY_RESULT",
        ):
            for bad in ("failure", "cancelled", "skipped", ""):
                # Defaults have units pending and every canary due, so no skip is explained.
                self.assertEqual(self.run_check(**{var: bad}), 1, (var, bad))

    def test_plan_skipped_is_always_red(self):
        self.assertEqual(
            self.run_check(
                PLAN_RESULT="skipped",
                RS_PLAN_RESULT="skipped",
                RS_RESULT="skipped",
                RS_UNITS="[]",
                PY_RESULT="skipped",
                UNITS="[]",
                PY_CANARY="false",
                CANARY_RESULT="skipped",
                RS_CANARY_RESULT="skipped",
                RS_CANARY="false",
                PYB_RESULT="skipped",
                HAS_PY="false",
            ),
            1,
        )

    def test_empty_units_output_is_red(self):
        # plan failed to set units: a skipped mutation-py is not explained by "[]".
        self.assertEqual(self.run_check(UNITS="", PY_RESULT="skipped"), 1)

    def test_steps_after_check_gate_on_it(self):
        steps = job_steps("mutation-pr")
        names = [s.get("name") for s in steps]
        check = names.index("Check job results")
        for step in steps[check + 1 :]:
            self.assertNotIn("always()", step.get("if", ""), step)

    def test_downloads(self):
        steps = job_steps("mutation-pr")
        plan = [s for s in steps if s.get("with", {}).get("name") == "mutants-pr-plan"]
        self.assertEqual(len(plan), 1)
        self.assertIn("download-artifact", plan[0]["uses"])
        status = [
            s
            for s in steps
            if s.get("with", {}).get("pattern") == "mutants-pr-status-*"
        ]
        self.assertEqual(len(status), 1)
        self.assertIs(status[0]["with"]["merge-multiple"], True)
        self.assertEqual(status[0]["with"]["path"], "status")
        self.assertEqual(
            status[0]["if"], f"${{{{ !cancelled() && {PLAN_OUT}.units != '[]' }}}}"
        )

    def test_verdict_step(self):
        step = named_step("mutation-pr", "Python verdict")
        self.assertEqual(
            step["env"]["PY_SRC_DIRS"], f"${{{{ {PLAN_OUT}.py_src_dirs }}}}"
        )
        self.assertIn("scripts/mutation-pr-verdict-python.sh", step["run"])
        self.assertIn('--expected-dirs "${PY_SRC_DIRS}"', step["run"])
        self.assertNotIn("--min-killed", step["run"])
        self.assertIn("plan/plan.txt", step["run"])
        self.assertEqual(step["if"], "${{ !cancelled() }}")

    def test_checkout_provides_scripts(self):
        self.assertIn("actions/checkout@", job_steps("mutation-pr")[0]["uses"])
