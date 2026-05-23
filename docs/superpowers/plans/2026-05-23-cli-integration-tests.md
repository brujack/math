> **Status: DONE**

# CLI Integration Tests — amicable, collatz, perfect-numbers, factorial

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Append `TestEntryPointGuard` integration tests to 4 Python CLI test files that currently lack them.

**Architecture:** Each test invokes the CLI as a subprocess with a small positional argument, asserts exit 0, and asserts a known value appears in stdout. Pattern is identical to existing `TestEntryPointGuard` classes in `e/test_e.py`, `fib/test_fib.py`, `pi/test_pi.py`, `sq/test_sq.py`. No new files, no CI changes.

**Tech Stack:** Python `unittest`, `subprocess`, `pathlib`, `tempfile`

---

## Files Modified

- `amicable/test_amicable.py` — append `TestEntryPointGuard`
- `collatz/test_collatz.py` — append `TestEntryPointGuard`
- `perfect-numbers/test_perfect_numbers.py` — append `TestEntryPointGuard`
- `factorial/test_factorial.py` — append `TestEntryPointGuard`

---

### Task 1: Worktree setup

- [ ] **Create worktree on a feature branch**

```bash
git -C ~/git-repos/personal/math worktree add .worktrees/feat/cli-integration-tests -b feat/cli-integration-tests
```

All subsequent edits happen in `/Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests/`.

---

### Task 2: amicable TestEntryPointGuard

**Files:** Modify `amicable/test_amicable.py`

- [ ] **Append the test class**

Add to the end of `/Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests/amicable/test_amicable.py`:

```python


class TestEntryPointGuard(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` block."""

    def test_module_runs_via_subprocess(self):
        import pathlib
        import subprocess
        import sys

        module_path = pathlib.Path(__file__).parent / "amicable.py"
        proc = subprocess.run(
            [sys.executable, str(module_path), "3"],
            input="n\n",
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tempfile.gettempdir(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("220", proc.stdout)
```

- [ ] **Run the test to verify it passes**

```bash
cd /Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests/amicable
python3 -m unittest test_amicable.TestEntryPointGuard.test_module_runs_via_subprocess -v 2>&1
```

Expected: `test_module_runs_via_subprocess ... ok`

If it fails: check that `amicable.py 3` finds the pair (220, 284) and prints "220" to stdout.

- [ ] **Commit**

```bash
cd /Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests
git add amicable/test_amicable.py
git commit -m "test(amicable): add CLI entry-point integration test"
```

---

### Task 3: collatz TestEntryPointGuard

**Files:** Modify `collatz/test_collatz.py`

- [ ] **Append the test class**

Add to the end of `/Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests/collatz/test_collatz.py`:

```python


class TestEntryPointGuard(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` block."""

    def test_module_runs_via_subprocess(self):
        import pathlib
        import subprocess
        import sys

        module_path = pathlib.Path(__file__).parent / "collatz.py"
        proc = subprocess.run(
            [sys.executable, str(module_path), "4"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tempfile.gettempdir(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("6171", proc.stdout)
```

Note: no `input=` — collatz takes its arg via argparse and never calls `input()`.

- [ ] **Run the test to verify it passes**

```bash
cd /Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests/collatz
python3 -m unittest test_collatz.TestEntryPointGuard.test_module_runs_via_subprocess -v 2>&1
```

Expected: `test_module_runs_via_subprocess ... ok`

- [ ] **Commit**

```bash
cd /Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests
git add collatz/test_collatz.py
git commit -m "test(collatz): add CLI entry-point integration test"
```

---

### Task 4: perfect-numbers TestEntryPointGuard

**Files:** Modify `perfect-numbers/test_perfect_numbers.py`

- [ ] **Append the test class**

Add to the end of `/Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests/perfect-numbers/test_perfect_numbers.py`:

```python


class TestEntryPointGuard(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` block."""

    def test_module_runs_via_subprocess(self):
        import pathlib
        import subprocess
        import sys

        module_path = pathlib.Path(__file__).parent / "perfect_numbers.py"
        proc = subprocess.run(
            [sys.executable, str(module_path), "4"],
            input="n\n",
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tempfile.gettempdir(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("6", proc.stdout)
```

- [ ] **Run the test to verify it passes**

```bash
cd /Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests/perfect-numbers
python3 -m unittest test_perfect_numbers.TestEntryPointGuard.test_module_runs_via_subprocess -v 2>&1
```

Expected: `test_module_runs_via_subprocess ... ok`

- [ ] **Commit**

```bash
cd /Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests
git add perfect-numbers/test_perfect_numbers.py
git commit -m "test(perfect-numbers): add CLI entry-point integration test"
```

---

### Task 5: factorial TestEntryPointGuard

**Files:** Modify `factorial/test_factorial.py`

- [ ] **Append the test class**

Add to the end of `/Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests/factorial/test_factorial.py`:

```python


class TestEntryPointGuard(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` block."""

    def test_module_runs_via_subprocess(self):
        import pathlib
        import subprocess

        module_path = pathlib.Path(__file__).parent / "factorial.py"
        proc = subprocess.run(
            [sys.executable, str(module_path), "5"],
            input="n\n",
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tempfile.gettempdir(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("120", proc.stdout)
```

- [ ] **Run the test to verify it passes**

```bash
cd /Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests/factorial
python3 -m unittest test_factorial.TestEntryPointGuard.test_module_runs_via_subprocess -v 2>&1
```

Expected: `test_module_runs_via_subprocess ... ok`

- [ ] **Commit**

```bash
cd /Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests
git add factorial/test_factorial.py
git commit -m "test(factorial): add CLI entry-point integration test"
```

---

### Task 6: Push, PR, CI

- [ ] **Push from the worktree** (so the pre-push hook tests the worktree's code, not master)

```bash
git -C /Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests push origin feat/cli-integration-tests
```

These are Python math tests — no isolated git repo creation — so GIT_DIR leakage from the worktree context is harmless.

- [ ] **Open PR**

```bash
cd /Users/bruce/git-repos/personal/math/.worktrees/feat/cli-integration-tests
gh pr create \
  --title "test: add CLI entry-point integration tests for amicable, collatz, perfect-numbers, factorial" \
  --body "Adds TestEntryPointGuard to 4 CLIs that were missing it. Verifies the if __name__ == '__main__' guard works and the CLI exits 0 with correct output for a small valid input."
```

- [ ] **Watch CI**

```bash
gh pr checks <PR_NUMBER> --watch
```

---

### Task 7: Post-merge cleanup and docs update

**Do this directly on master after the PR merges — not inside the worktree.**

- [ ] **Remove worktree and clean up branches**

```bash
git -C ~/git-repos/personal/math worktree remove .worktrees/feat/cli-integration-tests
git -C ~/git-repos/personal/math branch -D feat/cli-integration-tests
git -C ~/git-repos/personal/math push origin --delete feat/cli-integration-tests
git -C ~/git-repos/personal/math fetch --prune && git -C ~/git-repos/personal/math pull
```

- [ ] **Update plan index on master**

In `~/git-repos/personal/math/docs/superpowers/README.md`, add to the All Plans table:

```markdown
| 2026-05-23 | [cli-integration-tests](plans/2026-05-23-cli-integration-tests.md) | [spec](specs/2026-05-23-cli-integration-tests-design.md) | Done |
```

Add `> **Status: DONE**` banner at the top of `docs/superpowers/plans/2026-05-23-cli-integration-tests.md`.

- [ ] **Commit**

```bash
cd ~/git-repos/personal/math
git add docs/superpowers/README.md docs/superpowers/plans/2026-05-23-cli-integration-tests.md
git commit -m "chore(docs): mark cli-integration-tests plan done"
git push
```
