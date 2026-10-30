"""Pin the structure of the monthly Python mutation workflow.

The workflow is `setup` -> 8x10 `mutants` matrix -> `notify`. Each assertion parses
the file with `yaml.safe_load` so a comment cannot fake a directive. PyYAML parses
the `on:` key as the boolean True, which these tests do not need.
"""

import os
import pathlib
import subprocess
import tempfile
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "mutation-testing-python.yml"
TEMPLATE = REPO_ROOT / "scripts" / "crate_templates" / "python" / "py.yml"

DIRS = ["amicable", "collatz", "e", "factorial", "fib", "perfect-numbers", "pi", "sq"]


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

    def test_empty_input_yields_all_eighty_units(self):
        proc, out = run_setup("")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = dict(line.split("=", 1) for line in out.splitlines())
        units = lines["units"].split()
        self.assertEqual(len(units), 80)
        self.assertEqual(len(set(units)), 80)
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


if __name__ == "__main__":
    unittest.main()
