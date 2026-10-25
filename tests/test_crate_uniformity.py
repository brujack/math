"""All 11 math crates are treated identically (operator rule, 2026-10-24).

Per-crate files are compared after replacing the crate's own name with a
placeholder. Drift between crates is how the ~/Downloads copy hid in 7 of 11
Makefiles (math#166): no single file looked wrong, they only differed. Each file
kind here must be byte-identical across all 11 crates once normalised; a real
per-crate need belongs in a declared parameter, not in an unexplained difference.
"""

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CRATES = [
    "amicable",
    "collatz",
    "e",
    "factorial",
    "fib",
    "goldbach",
    "perfect-numbers",
    "pi",
    "prime",
    "sq",
    "twin-primes",
]


def normalise(crate, text):
    """Replace the crate's own names with placeholders, longest form first."""
    forms = [(f"{crate}-rs", "{crate}-rs"), (crate, "{crate}")]
    snake = crate.replace("-", "_")
    if snake != crate:
        forms.append((snake, "{crate_snake}"))
    for name, placeholder in forms:
        text = re.sub(rf"(?<![\w-]){re.escape(name)}(?![\w-])", placeholder, text)
    return text


def variants(path_pattern):
    """Return {normalised text: [crates]} for one per-crate file kind."""
    groups = {}
    for crate in CRATES:
        text = (REPO_ROOT / path_pattern.format(crate=crate)).read_text()
        groups.setdefault(normalise(crate, text), []).append(crate)
    return groups


class TestNormalise(unittest.TestCase):
    def test_single_letter_crate_only_replaces_whole_words(self):
        self.assertEqual(normalise("e", "make e on master"), "make {crate} on master")

    def test_hyphenated_crate_and_snake_form(self):
        self.assertEqual(
            normalise("twin-primes", "twin-primes-rs twin-primes twin_primes"),
            "{crate}-rs {crate} {crate_snake}",
        )

    def test_crate_rs_dir_before_bare_name(self):
        self.assertEqual(normalise("pi", "cd pi/pi-rs"), "cd {crate}/{crate}-rs")


class TestCrateFilesAreUniform(unittest.TestCase):
    def assert_uniform(self, path_pattern):
        groups = variants(path_pattern)
        self.assertEqual(
            len(groups),
            1,
            f"{path_pattern} differs between crates: "
            + "; ".join(str(sorted(cs)) for cs in groups.values()),
        )

    def test_makefile(self):
        self.assert_uniform("{crate}/{crate}-rs/Makefile")

    def test_rustfmt_toml(self):
        self.assert_uniform("{crate}/{crate}-rs/rustfmt.toml")


if __name__ == "__main__":
    unittest.main()
