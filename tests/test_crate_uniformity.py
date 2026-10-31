"""All 11 math crates are treated identically (operator rule, 2026-10-24).

Every per-crate file listed in scripts/render_crate_files.py is rendered from one
template in scripts/crate_templates/ with only the crate's name substituted, and
must match the rendered text exactly. Drift between crates is how the ~/Downloads
copy hid in 7 of 11 Makefiles (math#166): no single file looked wrong, they only
differed. To change one crate's file, change the template and re-render all 11:

    python3 scripts/render_crate_files.py --write
"""

import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

import tomllib

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

    def test_module_placeholder_uses_underscored_module_and_dir_name(self):
        text = rcf.render(
            "cd @CRATE@ && pytest test_@MODULE@.py",
            "perfect-numbers",
            "perfect_numbers",
        )
        self.assertEqual(text, "cd perfect-numbers && pytest test_perfect_numbers.py")

    def test_module_placeholder_without_a_module_is_an_error(self):
        with self.assertRaises(ValueError):
            rcf.render("@CRATE@ @MODULE@", "pi")

    def test_module_placeholder_with_a_module_still_rejects_unknown_names(self):
        with self.assertRaises(ValueError):
            rcf.render("@MODULE@ @VERSION@", "pi", "pi")

    def test_module_is_derived_from_the_project_dir(self):
        self.assertEqual(rcf.module_name("perfect-numbers"), "perfect_numbers")
        self.assertEqual(rcf.module_name("pi"), "pi")


_PY_KINDS = {"python/Makefile": "{project}/Makefile"}


class TestPythonKinds(unittest.TestCase):
    def _tree(self, tmp, content):
        root = pathlib.Path(tmp)
        (root / "scripts" / "crate_templates" / "python").mkdir(parents=True)
        (root / "scripts" / "crate_templates" / "python" / "Makefile").write_text(
            "test @CRATE@ @MODULE@\n"
        )
        for project in rcf.PYTHON_PROJECTS:
            path = root / project / "Makefile"
            path.parent.mkdir(parents=True)
            path.write_text(content(project))
        return root

    def _expected(self, project):
        return f"test {project} {project.replace('-', '_')}\n"

    def test_check_reports_drifted_python_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(
                tmp,
                lambda p: "other\n" if p == "pi" else self._expected(p),
            )
            drift = rcf.check(root, {}, _PY_KINDS)
        self.assertEqual(drift, ["pi/Makefile"])

    def test_write_renders_module_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp, lambda p: "other\n")
            first = rcf.write(root, {}, _PY_KINDS)
            second = rcf.write(root, {}, _PY_KINDS)
            self.assertEqual(rcf.check(root, {}, _PY_KINDS), [])
            text = (root / "perfect-numbers" / "Makefile").read_text()
        self.assertEqual(text, "test perfect-numbers perfect_numbers\n")
        self.assertEqual(len(first), 8)
        self.assertEqual(second, [])

    def test_rust_kind_with_module_placeholder_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "scripts" / "crate_templates").mkdir(parents=True)
            (root / "scripts" / "crate_templates" / "Makefile").write_text(
                "@CRATE@ @MODULE@\n"
            )
            with self.assertRaises(ValueError):
                rcf.check(root, {"Makefile": "{crate}/{crate}-rs/Makefile"})

    def test_cli_accepts_python_kind_names(self):
        script = REPO_ROOT / "scripts" / "render_crate_files.py"
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp, self._expected)
            done = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--root",
                    str(root),
                    "--check",
                    "--kind",
                    "python/Makefile",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(done.returncode, 0, done.stdout)


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

    def test_write_creates_missing_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp, lambda c: f"build {c}\n")
            kinds = {"Makefile": "{crate}/{crate}-rs/.config/Makefile"}
            written = rcf.write(root, kinds)
            self.assertEqual(rcf.check(root, kinds), [])
        self.assertEqual(len(written), 11)

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
        self.assertEqual(
            set(rcf.KINDS),
            {
                "Makefile",
                "rustfmt.toml",
                "release.yml",
                "ci.yml",
                "nextest.toml",
                "install_deps.sh",
            },
        )

    def test_python_workflow_is_a_rendered_python_kind(self):
        self.assertIn("python/py.yml", rcf.PYTHON_KINDS)
        self.assertEqual(
            rcf.PYTHON_KINDS["python/py.yml"], ".github/workflows/{project}-py.yml"
        )

    def test_python_projects_are_the_dirs_with_a_module_file(self):
        out = subprocess.run(
            ["git", "ls-files", "*/*.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        derived = sorted(
            d
            for d in {pathlib.PurePosixPath(f).parts[0] for f in out}
            if f"{d}/{d.replace('-', '_')}.py" in out
        )
        self.assertEqual(len(rcf.PYTHON_PROJECTS), 8)
        self.assertEqual(sorted(rcf.PYTHON_PROJECTS), derived)

    def test_scripts_workflow_runs_on_every_rendered_file(self):
        # The check runs in scripts.yml, which is paths-filtered: a PR touching only
        # one crate's Makefile must still trigger it, or drift merges unchecked.
        import fnmatch

        import yaml

        workflow = yaml.safe_load(
            (REPO_ROOT / ".github/workflows/scripts.yml").read_text()
        )
        paths = workflow[True]["pull_request"]["paths"]
        rendered = [
            (kind, pattern.format(crate=crate))
            for kind, pattern in rcf.KINDS.items()
            for crate in rcf.CRATES
        ] + [
            (kind, pattern.format(project=project))
            for kind, pattern in rcf.PYTHON_KINDS.items()
            for project in rcf.PYTHON_PROJECTS
        ]
        # The templates themselves are inputs to the render, so they must trigger too.
        rendered += [
            (kind, f"scripts/crate_templates/{kind}")
            for kind in (*rcf.KINDS, *rcf.PYTHON_KINDS)
        ]
        for kind, rel in rendered:
            with self.subTest(kind=kind, path=rel):
                self.assertTrue(
                    any(fnmatch.fnmatch(rel, glob) for glob in paths),
                    f"scripts.yml paths do not trigger on {rel}",
                )

    def test_repo_matches_templates(self):
        drift = rcf.check(REPO_ROOT, rcf.KINDS, rcf.PYTHON_KINDS)
        self.assertEqual(
            drift, [], "run: python3 scripts/render_crate_files.py --write"
        )


class TestCargoTomlShape(unittest.TestCase):
    """R1: the 11 Cargo.toml files differ only in name, description and extra deps."""

    # Sections every crate must carry identically (tomllib-parsed values).
    SHARED_TABLES = ("lints", "dev-dependencies")

    def _load(self, crate):
        path = REPO_ROOT / crate / f"{crate}-rs" / "Cargo.toml"
        text = path.read_text()
        return text, tomllib.loads(text)

    @staticmethod
    def _release_profile_text(text):
        match = re.search(r"^\[profile\.release\]\n(.*?)(?=^\[|\Z)", text, re.M | re.S)
        return match.group(1).strip() if match else None

    def test_every_crate_has_one_bin_named_after_its_directory(self):
        for crate in rcf.CRATES:
            with self.subTest(crate=crate):
                _, toml = self._load(crate)
                self.assertEqual([b["name"] for b in toml.get("bin", [])], [crate])

    def test_package_keys_match_apart_from_name_and_description(self):
        shapes = {}
        for crate in rcf.CRATES:
            _, toml = self._load(crate)
            shapes[crate] = {
                k: v
                for k, v in toml["package"].items()
                if k not in ("name", "description")
            }
        reference = shapes[rcf.CRATES[0]]
        for crate, shape in shapes.items():
            with self.subTest(crate=crate):
                self.assertEqual(shape, reference)

    def test_every_crate_is_edition_2024(self):
        for crate in rcf.CRATES:
            with self.subTest(crate=crate):
                _, toml = self._load(crate)
                self.assertEqual(toml["package"].get("edition"), "2024")

    def test_every_crate_forbids_unsafe_code(self):
        for crate in rcf.CRATES:
            with self.subTest(crate=crate):
                _, toml = self._load(crate)
                self.assertEqual(toml["lints"]["rust"].get("unsafe_code"), "forbid")

    def test_no_crate_declares_rust_version(self):
        # Nothing builds these binaries on an older toolchain, so an MSRV
        # declaration would be an unverified claim.
        for crate in rcf.CRATES:
            with self.subTest(crate=crate):
                _, toml = self._load(crate)
                self.assertNotIn("rust-version", toml["package"])

    def test_lints_and_dev_dependencies_match(self):
        for table in self.SHARED_TABLES:
            reference = self._load(rcf.CRATES[0])[1].get(table)
            for crate in rcf.CRATES:
                with self.subTest(table=table, crate=crate):
                    self.assertEqual(self._load(crate)[1].get(table), reference)

    def test_clap_dependency_entry_matches(self):
        for crate in rcf.CRATES:
            with self.subTest(crate=crate):
                _, toml = self._load(crate)
                self.assertEqual(
                    toml["dependencies"].get("clap"),
                    {"version": "4", "features": ["derive"]},
                )

    def test_release_profile_text_is_byte_identical(self):
        canonical = 'opt-level     = 3\nlto           = "thin"\ncodegen-units = 1'
        for crate in rcf.CRATES:
            with self.subTest(crate=crate):
                text, _ = self._load(crate)
                self.assertEqual(self._release_profile_text(text), canonical)

    def test_scripts_workflow_triggers_on_cargo_toml(self):
        import yaml

        workflow = yaml.safe_load(
            (REPO_ROOT / ".github/workflows/scripts.yml").read_text()
        )
        self.assertIn("*/*-rs/Cargo.toml", workflow[True]["pull_request"]["paths"])


class TestCrateClaudeMd(unittest.TestCase):
    def test_every_crate_has_its_own_claude_md(self):
        missing = [
            crate
            for crate in rcf.CRATES
            if not (REPO_ROOT / crate / f"{crate}-rs" / "CLAUDE.md").is_file()
        ]
        self.assertEqual(missing, [])

    def test_scripts_workflow_triggers_on_crate_claude_md(self):
        import yaml

        workflow = yaml.safe_load(
            (REPO_ROOT / ".github/workflows/scripts.yml").read_text()
        )
        self.assertIn("*/*-rs/CLAUDE.md", workflow[True]["pull_request"]["paths"])


if __name__ == "__main__":
    unittest.main()
