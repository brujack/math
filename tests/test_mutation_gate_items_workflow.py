"""Pins the trust boundary of mutation-gate-items.yml (spec R20, N4).

The workflow runs on pull_request_target, so it holds a privileged context. It may only
run the base branch's code and must treat the PR as data.
"""

import ast
import re
import sys
import unittest
from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "mutation-gate-items.yml"
)
SHA_USES = re.compile(r"^[\w./-]+@[0-9a-f]{40}$")
EXPECTED_RUNS = {
    'git fetch --no-tags origin "+refs/pull/${PR}/head"',
    "pip install cosmic-ray==8.7.0 pyyaml==6.0.3",
    'scripts/mutation-gate-items.sh "${BASE_SHA}" "${HEAD_SHA}"',
}
EXPECTED_CHECKOUT_KEYS = {"ref", "fetch-depth", "persist-credentials"}


def load():
    text = WORKFLOW.read_text()
    return text, yaml.safe_load(text)


def steps():
    return load()[1]["jobs"]["mutation-gate-items"]["steps"]


def allow_list_violations(doc):
    """Return what departs from the allow-list: the only commands, no PR checkout (N4)."""
    found = []
    job_steps = doc["jobs"]["mutation-gate-items"]["steps"]
    runs = {s["run"] for s in job_steps if "run" in s}
    if runs != EXPECTED_RUNS:
        found.append(f"run set differs: {sorted(runs ^ EXPECTED_RUNS)}")
    for step in job_steps:
        if "working-directory" in step:
            found.append("working-directory")
        if step.get("uses", "").startswith("actions/checkout@"):
            if set(step.get("with", {})) != EXPECTED_CHECKOUT_KEYS:
                found.append("checkout with-keys differ")
            if "repository" in step.get("with", {}):
                found.append("checkout repository")
    return found


class TriggerAndPermissions(unittest.TestCase):
    def test_trigger_is_pull_request_target_only_without_paths(self):
        doc = load()[1]
        on = doc.get("on", doc.get(True))
        self.assertEqual(list(on), ["pull_request_target"])
        cfg = on["pull_request_target"]
        self.assertEqual(
            cfg["types"],
            ["opened", "synchronize", "reopened", "ready_for_review", "edited"],
        )
        self.assertNotIn("paths", cfg)
        self.assertNotIn("paths-ignore", cfg)

    def test_permissions_are_contents_read_and_not_widened(self):
        doc = load()[1]
        self.assertEqual(doc["permissions"], {"contents": "read"})
        for job in doc["jobs"].values():
            self.assertNotIn("permissions", job)

    def test_no_secrets_or_token_in_text(self):
        text = load()[0]
        self.assertNotIn("secrets.", text)
        self.assertNotIn("GITHUB_TOKEN", text)
        self.assertNotIn("github.token", text)

    def test_single_job_named_mutation_gate_items(self):
        jobs = load()[1]["jobs"]
        self.assertEqual(list(jobs), ["mutation-gate-items"])
        self.assertEqual(jobs["mutation-gate-items"]["name"], "mutation-gate-items")

    def test_timeout_and_concurrency(self):
        doc = load()[1]
        self.assertIn("timeout-minutes", doc["jobs"]["mutation-gate-items"])
        conc = doc["concurrency"]
        self.assertIn("pull_request.number", conc["group"])
        self.assertIs(conc["cancel-in-progress"], True)

    def test_no_skip_condition_anywhere_so_every_edit_is_rejudged(self):
        doc = load()[1]
        job = doc["jobs"]["mutation-gate-items"]
        self.assertNotIn("if", job)
        self.assertEqual([s for s in job["steps"] if "if" in s], [])
        on = doc.get("on", doc.get(True))
        self.assertIn("edited", on["pull_request_target"]["types"])

    def test_trigger_is_limited_to_the_master_base_branch(self):
        doc = load()[1]
        on = doc.get("on", doc.get(True))
        self.assertEqual(on["pull_request_target"]["branches"], ["master"])

    def test_python_version_matches_mutation_pr(self):
        setups = [
            s for s in steps() if s.get("uses", "").startswith("actions/setup-python@")
        ]
        self.assertEqual([s["with"]["python-version"] for s in setups], ["3.14"])

    def test_no_continue_on_error(self):
        self.assertNotIn("continue-on-error", load()[0])


class BaseOnlyExecution(unittest.TestCase):
    def test_checkout_is_base_sha_without_credentials(self):
        checkouts = [
            s for s in steps() if s.get("uses", "").startswith("actions/checkout@")
        ]
        self.assertEqual(len(checkouts), 1)
        with_ = checkouts[0]["with"]
        self.assertEqual(with_["ref"], "${{ github.event.pull_request.base.sha }}")
        self.assertIs(with_["persist-credentials"], False)
        self.assertEqual(with_["fetch-depth"], 0)

    def test_every_uses_is_sha_pinned(self):
        for step in steps():
            if "uses" in step:
                self.assertRegex(step["uses"], SHA_USES)

    def test_run_commands_are_exactly_the_allow_list(self):
        self.assertEqual(allow_list_violations(load()[1]), [])
        self.assertEqual({s["run"] for s in steps() if "run" in s}, EXPECTED_RUNS)

    def test_no_working_directory_and_checkout_keys_exact(self):
        for step in steps():
            self.assertNotIn("working-directory", step)
        checkout = next(
            s for s in steps() if s.get("uses", "").startswith("actions/checkout@")
        )
        self.assertEqual(set(checkout["with"]), EXPECTED_CHECKOUT_KEYS)
        self.assertNotIn("repository", checkout["with"])

    def test_allow_list_catches_each_pr_code_path(self):
        import copy

        def mutate(change):
            doc = copy.deepcopy(load()[1])
            change(doc["jobs"]["mutation-gate-items"]["steps"])
            return allow_list_violations(doc)

        def add_run(cmd):
            return lambda st: st.append({"name": "x", "run": cmd})

        def head_repo_checkout(st):
            st[0]["with"]["repository"] = (
                "${{ github.event.pull_request.head.repo.full_name }}"
            )

        def workdir(st):
            st[-1]["working-directory"] = "."

        for label, change in {
            "reset": add_run("git reset --hard FETCH_HEAD"),
            "merge": add_run("git merge FETCH_HEAD"),
            "restore": add_run("git restore --source=FETCH_HEAD ."),
            "show-pipe": add_run("git show FETCH_HEAD:x | bash"),
            "head-repo checkout": head_repo_checkout,
            "working-directory": workdir,
        }.items():
            with self.subTest(label):
                self.assertTrue(mutate(change))

    def test_no_event_expression_inside_run(self):
        for step in steps():
            self.assertNotIn("${{", step.get("run", ""), step)

    def test_pr_objects_are_fetched_not_checked_out(self):
        fetch = [s for s in steps() if "refs/pull/" in s.get("run", "")]
        self.assertEqual(len(fetch), 1)
        self.assertIn("git fetch --no-tags origin", fetch[0]["run"])
        self.assertIn('"+refs/pull/${PR}/head"', fetch[0]["run"])
        self.assertEqual(
            fetch[0]["env"]["PR"], "${{ github.event.pull_request.number }}"
        )

    def test_run_step_invokes_gate_with_env_values(self):
        gate = [s for s in steps() if "mutation-gate-items.sh" in s.get("run", "")]
        self.assertEqual(len(gate), 1)
        self.assertIn(
            'scripts/mutation-gate-items.sh "${BASE_SHA}" "${HEAD_SHA}"',
            gate[0]["run"],
        )
        env = gate[0]["env"]
        self.assertEqual(env["BASE_SHA"], "${{ github.event.pull_request.base.sha }}")
        self.assertEqual(env["HEAD_SHA"], "${{ github.event.pull_request.head.sha }}")
        self.assertNotIn("PR", env)
        self.assertNotIn("--pr", gate[0]["run"])


class PinnedTooling(unittest.TestCase):
    def test_cosmic_ray_pinned(self):
        runs = " ".join(s.get("run", "") for s in steps())
        self.assertIn("cosmic-ray==8.7.0", runs)

    def test_every_third_party_import_is_installed_by_the_pip_step(self):
        scripts = WORKFLOW.parent.parent.parent / "scripts"
        dist_for = {"yaml": "pyyaml", "cosmic_ray": "cosmic-ray"}
        local = {p.stem for p in scripts.glob("*.py")}
        pending, seen, needed = ["mutation_gate_items"], set(), set()
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            tree = ast.parse((scripts / f"{name}.py").read_text())
            for node in tree.body:
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif (
                    isinstance(node, ast.ImportFrom) and node.level == 0 and node.module
                ):
                    mods = [node.module.split(".")[0]]
                for mod in mods:
                    if mod in local:
                        pending.append(mod)
                    elif mod not in sys.stdlib_module_names:
                        needed.add(mod)
        self.assertIn("yaml", needed)
        pip = " ".join(
            s.get("run", "")
            for s in steps()
            if s.get("run", "").startswith("pip install")
        )
        for mod in sorted(needed):
            self.assertIn(
                f"{dist_for.get(mod, mod)}==", pip, f"{mod} not pip-installed"
            )

    def test_cargo_mutants_pinned_with_no_fallback(self):
        installs = [
            s
            for s in steps()
            if s.get("uses", "").startswith("taiki-e/install-action@")
        ]
        self.assertEqual(len(installs), 1)
        self.assertEqual(installs[0]["with"]["tool"], "cargo-mutants@27.1.0")
        self.assertEqual(installs[0]["with"]["fallback"], "none")

    def test_rust_toolchain_present(self):
        self.assertTrue(
            any(
                s.get("uses", "").startswith("dtolnay/rust-toolchain@") for s in steps()
            )
        )


if __name__ == "__main__":
    unittest.main()
