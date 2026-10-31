"""Rust-only workflows must not apt-install system GMP/MPFR/MPC.

gmp-mpfr-sys builds its own copy from source and links it statically, so the
apt step was dead weight. The Python workflows are out of scope: whether
gmpy2 needs the system libraries is unmeasured.
"""

import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
FORBIDDEN = ("libgmp-dev", "libmpfr-dev", "libmpc-dev")


def rust_only_workflows() -> list[pathlib.Path]:
    files = sorted(WORKFLOWS.glob("*-rs.yml"))
    files += [WORKFLOWS / "gmp-cache.yml", WORKFLOWS / "benchmarks.yml"]
    return files


class TestNoSystemGmp(unittest.TestCase):
    def test_file_set_is_24(self):
        self.assertEqual(len(rust_only_workflows()), 24)

    def test_no_system_gmp_packages(self):
        for path in rust_only_workflows():
            text = path.read_text(encoding="utf-8")
            for pkg in FORBIDDEN:
                with self.subTest(file=path.name, pkg=pkg):
                    self.assertNotIn(pkg, text, f"{path.name} installs {pkg}")


if __name__ == "__main__":
    unittest.main()
