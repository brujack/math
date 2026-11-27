"""Pins the trust boundary of mutation-gate-items.yml (spec R20, N4).

The workflow runs on pull_request_target, so it holds a privileged context. It may only
run the base branch's code and must treat the PR as data.
"""

import re
import unittest
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "mutation-gate-items.yml"
SHA_USES = re.compile(r"^[\w./-]+@[0-9a-f]{40}$")
FORBIDDEN_RUN = re.compile(
    r"\bmake\b|pip\d?\s+install\s+(-\S+\s+)*-e\b|\bcargo\s+(build|test|run)\b"
    r"|git\s+(checkout|switch|worktree|archive)\b"
)


def load():
    text = WORKFLOW.read_text()
    return text, yaml.safe_load(text)


def steps():
    return load()[1]["jobs"]["mutation-gate-items"]["steps"]


class TriggerAndPermissions(unittest.TestCase):
    def test_trigger_is_pull_request_target_only_without_paths(self):
        doc = load()[1]
        on = doc.get("on", doc.get(True))
        self.assertEqual(list(on), ["pull_request_target"])
        cfg = on["pull_request_target"]
        self.assertEqual(
            cfg["types"], ["opened", "synchronize", "reopened", "ready_for_review"]
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

    def test_no_continue_on_error(self):
        self.assertNotIn("continue-on-error", load()[0])


class BaseOnlyExecution(unittest.TestCase):
    def test_checkout_is_base_sha_without_credentials(self):
        checkouts = [s for s in steps() if s.get("uses", "").startswith("actions/checkout@")]
        self.assertEqual(len(checkouts), 1)
        with_ = checkouts[0]["with"]
        self.assertEqual(with_["ref"], "${{ github.event.pull_request.base.sha }}")
        self.assertIs(with_["persist-credentials"], False)
        self.assertEqual(with_["fetch-depth"], 0)

    def test_every_uses_is_sha_pinned(self):
        for step in steps():
            if "uses" in step:
                self.assertRegex(step["uses"], SHA_USES)

    def test_no_run_step_executes_pr_code(self):
        for step in steps():
            self.assertIsNone(FORBIDDEN_RUN.search(step.get("run", "")), step)

    def test_no_event_expression_inside_run(self):
        for step in steps():
            self.assertNotIn("${{", step.get("run", ""), step)

    def test_pr_objects_are_fetched_not_checked_out(self):
        fetch = [s for s in steps() if "refs/pull/" in s.get("run", "")]
        self.assertEqual(len(fetch), 1)
        self.assertIn("git fetch --no-tags origin", fetch[0]["run"])
        self.assertIn('"+refs/pull/${PR}/head"', fetch[0]["run"])
        self.assertEqual(fetch[0]["env"]["PR"], "${{ github.event.pull_request.number }}")

    def test_run_step_invokes_gate_with_env_values(self):
        gate = [s for s in steps() if "mutation-gate-items.sh" in s.get("run", "")]
        self.assertEqual(len(gate), 1)
        self.assertIn(
            'scripts/mutation-gate-items.sh "${BASE_SHA}" "${HEAD_SHA}" --pr "${PR}"',
            gate[0]["run"],
        )
        env = gate[0]["env"]
        self.assertEqual(env["BASE_SHA"], "${{ github.event.pull_request.base.sha }}")
        self.assertEqual(env["HEAD_SHA"], "${{ github.event.pull_request.head.sha }}")
        self.assertEqual(env["PR"], "${{ github.event.pull_request.number }}")


class PinnedTooling(unittest.TestCase):
    def test_cosmic_ray_pinned(self):
        runs = " ".join(s.get("run", "") for s in steps())
        self.assertIn("pip install cosmic-ray==8.7.0", runs)

    def test_cargo_mutants_pinned_with_no_fallback(self):
        installs = [
            s for s in steps() if s.get("uses", "").startswith("taiki-e/install-action@")
        ]
        self.assertEqual(len(installs), 1)
        self.assertEqual(installs[0]["with"]["tool"], "cargo-mutants@27.1.0")
        self.assertEqual(installs[0]["with"]["fallback"], "none")

    def test_rust_toolchain_present(self):
        self.assertTrue(
            any(s.get("uses", "").startswith("dtolnay/rust-toolchain@") for s in steps())
        )


if __name__ == "__main__":
    unittest.main()
