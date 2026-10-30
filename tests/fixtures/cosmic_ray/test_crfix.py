import importlib
import unittest

# Sibling module resolved from the working directory cosmic-ray runs in; imported
# dynamically so root-scope import scans do not read it as a third-party package.
crfix = importlib.import_module("crfix")


class TestCrfix(unittest.TestCase):
    def test_bump_returns_int(self) -> None:
        # Deliberately weak: arithmetic mutants that stay int survive.
        self.assertIsInstance(crfix.bump(3), int)

    def test_count_down_reaches_zero(self) -> None:
        self.assertEqual(crfix.count_down(3), 0)


if __name__ == "__main__":
    unittest.main()
