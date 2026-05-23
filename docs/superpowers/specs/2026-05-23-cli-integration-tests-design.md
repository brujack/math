# Spec: CLI Integration Tests for amicable, collatz, perfect-numbers, factorial

## Goal

Add `TestEntryPointGuard` integration tests to 4 Python CLIs that currently lack them. These verify the `if __name__ == "__main__"` guard works and the CLI exits 0 and produces correct output for a small valid input.

## Pattern

Identical to existing tests in `e/test_e.py`, `fib/test_fib.py`, `pi/test_pi.py`, `sq/test_sq.py`:

```python
class TestEntryPointGuard(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` block."""

    def test_module_runs_via_subprocess(self):
        import pathlib, subprocess
        module_path = pathlib.Path(__file__).parent / "MODULE.py"
        proc = subprocess.run(
            [sys.executable, str(module_path), "ARG"],
            input="INPUT",
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tempfile.gettempdir(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("EXPECTED", proc.stdout)
```

## Per-module parameters

| Module          | File                                 | Arg   | `input=` | Assert in stdout                            |
| --------------- | ------------------------------------ | ----- | -------- | ------------------------------------------- |
| amicable        | `amicable/amicable.py`               | `"3"` | `"n\n"`  | `"220"` (first amicable pair: 220, 284)     |
| collatz         | `collatz/collatz.py`                 | `"4"` | `None`   | `"6171"` (record-setter at step 261 ≤ 10^4) |
| perfect_numbers | `perfect-numbers/perfect_numbers.py` | `"4"` | `"n\n"`  | `"6"` (first perfect number)                |
| factorial       | `factorial/factorial.py`             | `"5"` | `"n\n"`  | `"120"` (5! = 120)                          |

Notes:

- `input="n\n"` answers any "save to file?" prompts with no
- `cwd=tempfile.gettempdir()` isolates any output files written by the CLI
- `timeout=30` is conservative — all 4 compute in <1s at these input sizes
- `collatz` takes its arg positionally via argparse; no interactive prompt is reached so `input=None`

## Files modified

- `amicable/test_amicable.py` — append `TestEntryPointGuard` class
- `collatz/test_collatz.py` — append `TestEntryPointGuard` class
- `perfect-numbers/test_perfect_numbers.py` — append `TestEntryPointGuard` class
- `factorial/test_factorial.py` — append `TestEntryPointGuard` class

No new files. No CI changes (all 4 already run `make test`).

## Out of Scope

- Testing invalid args or exit codes (error-path tests are separate)
- Testing file output content
- Rust equivalents (no integration tests for Rust CLIs in this pass)
