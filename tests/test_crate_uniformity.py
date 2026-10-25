"""All 11 math crates are treated identically (operator rule, 2026-10-24).

Every per-crate file listed in scripts/render_crate_files.py is rendered from one
template in scripts/crate_templates/ with only the crate's name substituted, and
must match the rendered text exactly. Drift between crates is how the ~/Downloads
copy hid in 7 of 11 Makefiles (math#166): no single file looked wrong, they only
differed. To change one crate's file, change the template and re-render all 11:

    python3 scripts/render_crate_files.py --write
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import render_crate_files as rcf


class TestRender(unittest.TestCase):
    def test_substitutes_every_placeholder(self):
        self.assertEqual(rcf.render("cd @CRATE@/@CRATE@-rs", "pi"), "cd pi/pi-rs")

    def test_template_without_placeholder_renders_unchanged(self):
        self.assertEqual(rcf.render("max_width = 100\n", "e"), "max_width = 100\n")

    def test_unknown_placeholder_is_an_error(self):
        with self.assertRaises(ValueError):
            rcf.render("@CRATE@ @VERSION@", "pi")


class TestCheckAndWrite(unittest.TestCase):
    def _tree(self, tmp, content):
        root = pathlib.Path(tmp)
        (root / "scripts" / "crate_templates").mkdir(parents=True)
        (root / "scripts" / "crate_templates" / "Makefile").write_text(
            "build @CRATE@\n"
        )
        for crate in rcf.CRATES:
            path = root / crate / f"{crate}-rs" / "Makefile"
            path.parent.mkdir(parents=True)
            path.write_text(content(crate))
        return root

    def test_check_reports_each_drifted_crate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(
                tmp, lambda c: "other\n" if c in ("e", "sq") else f"build {c}\n"
            )
            drift = rcf.check(root, {"Makefile": "{crate}/{crate}-rs/Makefile"})
        self.assertEqual(drift, ["e/e-rs/Makefile", "sq/sq-rs/Makefile"])

    def test_check_reports_a_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp, lambda c: f"build {c}\n")
            (root / "pi" / "pi-rs" / "Makefile").unlink()
            drift = rcf.check(root, {"Makefile": "{crate}/{crate}-rs/Makefile"})
        self.assertEqual(drift, ["pi/pi-rs/Makefile"])

    def test_write_fixes_drift_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp, lambda c: "other\n")
            kinds = {"Makefile": "{crate}/{crate}-rs/Makefile"}
            first = rcf.write(root, kinds)
            second = rcf.write(root, kinds)
            self.assertEqual(rcf.check(root, kinds), [])
            self.assertEqual(
                (root / "pi" / "pi-rs" / "Makefile").read_text(), "build pi\n"
            )
        self.assertEqual(len(first), 11)
        self.assertEqual(second, [])

    def test_cli_check_exits_1_on_drift_and_0_when_clean(self):
        script = REPO_ROOT / "scripts" / "render_crate_files.py"
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp, lambda c: "other\n")
            args = [
                sys.executable,
                str(script),
                "--root",
                str(root),
                "--kind",
                "Makefile",
            ]
            dirty = subprocess.run(
                [*args, "--check"], capture_output=True, text=True, check=False
            )
            subprocess.run(
                [*args, "--write"], capture_output=True, text=True, check=True
            )
            clean = subprocess.run(
                [*args, "--check"], capture_output=True, text=True, check=False
            )
        self.assertEqual(dirty.returncode, 1)
        self.assertIn("e/e-rs/Makefile", dirty.stdout)
        self.assertEqual(clean.returncode, 0, clean.stdout)


class TestRepoCratesMatchTemplates(unittest.TestCase):
    def test_every_kind_covers_all_11_crates(self):
        self.assertEqual(len(rcf.CRATES), 11)
        self.assertEqual(set(rcf.KINDS), {"Makefile", "rustfmt.toml", "release.yml"})

    def test_scripts_workflow_runs_on_every_rendered_file(self):
        # The check runs in scripts.yml, which is paths-filtered: a PR touching only
        # one crate's Makefile must still trigger it, or drift merges unchecked.
        import fnmatch

        import yaml

        workflow = yaml.safe_load(
            (REPO_ROOT / ".github/workflows/scripts.yml").read_text()
        )
        paths = workflow[True]["pull_request"]["paths"]
        for kind, pattern in rcf.KINDS.items():
            for crate in rcf.CRATES:
                rel = pattern.format(crate=crate)
                with self.subTest(kind=kind, path=rel):
                    self.assertTrue(
                        any(fnmatch.fnmatch(rel, glob) for glob in paths),
                        f"scripts.yml paths do not trigger on {rel}",
                    )

    def test_repo_matches_templates(self):
        drift = rcf.check(REPO_ROOT, rcf.KINDS)
        self.assertEqual(
            drift, [], "run: python3 scripts/render_crate_files.py --write"
        )


if __name__ == "__main__":
    unittest.main()
