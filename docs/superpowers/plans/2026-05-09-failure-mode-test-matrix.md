> **Status: DONE**

# Failure-Mode Test Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit failure-mode tests to all compute CLIs (pi, e, factorial, fib, sq in Python; all 7 Rust crates), and drive new error handlers into factorial, fib, and sq via TDD.

**Architecture:** Inline additions to existing test files — no new Python test files. Each Rust crate gets new unit injection tests added to the `#[cfg(test)] mod tests` block inside `src/main.rs` (not a separate integration test file, since `run()` is private). Subprocess failure tests extend each crate's `tests/cli.rs`.

**Tech Stack:** Python unittest.mock, Rust std::io::Write, tempfile crate, subprocess Command API.

---

## File Map

| File                                      | Change                                                           |
| ----------------------------------------- | ---------------------------------------------------------------- |
| `pi/test_pi.py`                           | Add 4 new test classes                                           |
| `e/test_e.py`                             | Add 4 new test classes                                           |
| `factorial/test_factorial.py`             | Add 5 new test classes                                           |
| `factorial/factorial.py`                  | Add `KeyboardInterrupt` + `PermissionError` handlers to `main()` |
| `fib/test_fib.py`                         | Add 2 new test classes                                           |
| `fib/fib.py`                              | Add `KeyboardInterrupt` + `PermissionError` handlers to `main()` |
| `sq/test_sq.py`                           | Add 2 new test classes                                           |
| `sq/sq.py`                                | Add `KeyboardInterrupt` + `PermissionError` handlers to `main()` |
| `pi/pi-rs/tests/cli.rs`                   | Add `cli_unwritable_output_dir`                                  |
| `pi/pi-rs/src/main.rs`                    | Add `FailWriter` + injection tests in `#[cfg(test)] mod tests`   |
| `e/e-rs/tests/cli.rs`                     | Add `cli_unwritable_output_dir`                                  |
| `e/e-rs/src/main.rs`                      | Add `FailWriter` + injection tests                               |
| `factorial/factorial-rs/tests/cli.rs`     | Add `cli_unwritable_output_dir`                                  |
| `factorial/factorial-rs/src/main.rs`      | Add `FailWriter` + injection tests                               |
| `fib/fib-rs/tests/cli.rs`                 | Add `cli_unwritable_output_dir`                                  |
| `fib/fib-rs/src/main.rs`                  | Add `FailWriter` + injection tests                               |
| `sq/sq-rs/tests/cli.rs`                   | Add `cli_unwritable_output_dir`                                  |
| `sq/sq-rs/src/main.rs`                    | Add `FailWriter` + injection tests                               |
| `prime/prime-rs/tests/cli.rs`             | Add `cli_unwritable_output_dir`                                  |
| `prime/prime-rs/src/main.rs`              | Add `FailWriter` + injection tests                               |
| `twin-primes/twin-primes-rs/tests/cli.rs` | Add `cli_unwritable_output_dir`                                  |
| `twin-primes/twin-primes-rs/src/main.rs`  | Add `FailWriter` + injection tests                               |
| `pi/CLAUDE.md`, `e/CLAUDE.md`, etc.       | Update test coverage tables                                      |

---

## Task 1: pi — Python failure tests

**Files:**

- Modify: `pi/test_pi.py` (append 4 new test classes after `TestSavePiToFilePhaseAFallback`)

All 4 classes are GREEN on first run — pi.py already handles every exception being tested. No implementation changes needed.

- [ ] **Step 1: Add TestProcessPoolPermissionError**

Append to `pi/test_pi.py` before the `TestMain` class:

```python
class TestProcessPoolPermissionError(unittest.TestCase):
    """save_pi_to_file serial fallback when ProcessPoolExecutor raises PermissionError."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_falls_back_to_serial(self):
        import mpmath
        mpmath.mp.dps = 25
        pi_val = +mpmath.pi
        path = os.path.join(self._tmp, "pi_perm_error.txt")
        buf = io.StringIO()
        with unittest.mock.patch(
            "pi.concurrent.futures.ProcessPoolExecutor",
            side_effect=PermissionError("permission denied"),
        ), redirect_stdout(buf):
            save_pi_to_file(pi_val, 20, path)
        with open(path) as f:
            content = f.read()
        self.assertIn("3.14159265358979323846", content)
        self.assertIn("Parallel mode unavailable", buf.getvalue())
```

- [ ] **Step 2: Add TestProcessPoolSemaphoreExhaustion**

Append directly after `TestProcessPoolPermissionError`:

```python
class TestProcessPoolSemaphoreExhaustion(unittest.TestCase):
    """save_pi_to_file serial fallback: generic OSError + macOS semaphore errno."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def _pi_val(self):
        import mpmath
        mpmath.mp.dps = 25
        return +mpmath.pi

    def test_oserror_falls_back_to_serial(self):
        path = os.path.join(self._tmp, "pi_sem1.txt")
        buf = io.StringIO()
        with unittest.mock.patch(
            "pi.concurrent.futures.ProcessPoolExecutor",
            side_effect=OSError("semaphore limit"),
        ), redirect_stdout(buf):
            save_pi_to_file(self._pi_val(), 20, path)
        self.assertIn("Parallel mode unavailable", buf.getvalue())
        with open(path) as f:
            self.assertIn("3.14159265358979323846", f.read())

    def test_semaphore_exhaustion_enospc_falls_back_to_serial(self):
        import errno
        path = os.path.join(self._tmp, "pi_sem2.txt")
        buf = io.StringIO()
        with unittest.mock.patch(
            "pi.concurrent.futures.ProcessPoolExecutor",
            side_effect=OSError(errno.ENOSPC, "No space left on device"),
        ), redirect_stdout(buf):
            save_pi_to_file(self._pi_val(), 20, path)
        self.assertIn("Parallel mode unavailable", buf.getvalue())
        with open(path) as f:
            self.assertIn("3.14159265358979323846", f.read())
```

- [ ] **Step 3: Add TestMissingGmpy2**

```python
class TestMissingGmpy2(unittest.TestCase):
    """calculate_pi_high_precision uses mpmath path when gmpy2 is absent."""

    def test_missing_gmpy2_uses_mpmath_fallback(self):
        import pi as pi_module
        buf = io.StringIO()
        with unittest.mock.patch.object(pi_module, "_HAS_GMPY2", False), \
             unittest.mock.patch.object(pi_module, "_gmpy2", None), \
             redirect_stdout(buf):
            pi_val = calculate_pi_high_precision(20)
        result = _pi_to_str(pi_val, 20)
        self.assertTrue(result.startswith("3.141592653589793"), f"got: {result!r}")
        self.assertNotIn("Error", buf.getvalue())
```

- [ ] **Step 4: Add TestFileWritePermissionError**

```python
class TestFileWritePermissionError(unittest.TestCase):
    """main() handles PermissionError when the output file cannot be created."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_exits_nonzero_on_permission_error(self):
        from pi import main
        buf = io.StringIO()
        with unittest.mock.patch("sys.argv", ["pi.py", "10"]), \
             unittest.mock.patch("builtins.input", return_value="n"), \
             unittest.mock.patch(
                 "pi.os.open",
                 side_effect=PermissionError("[Errno 13] Permission denied: 'pi_10_digits.txt'"),
             ), \
             redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Error", buf.getvalue())
```

- [ ] **Step 5: Run tests and verify all pass**

```bash
cd pi && make test
```

Expected: all existing tests pass + the 4 new classes pass (GREEN on first run).

- [ ] **Step 6: Commit**

```bash
cd pi
git add test_pi.py
git commit -m "test: pi — add ProcessPool PermissionError, semaphore exhaustion, missing gmpy2, and file-write failure tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: e — Python failure tests

**Files:**

- Modify: `e/test_e.py` (append 4 new test classes after `TestSaveEToFilePhaseAFallback`)

All 4 classes are GREEN on first run — e.py already handles every exception.

- [ ] **Step 1: Add TestProcessPoolPermissionError**

Append to `e/test_e.py` before `TestGetTargetDigitsInteractive`:

```python
class TestProcessPoolPermissionError(unittest.TestCase):
    """save_e_to_file serial fallback when ProcessPoolExecutor raises PermissionError."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_falls_back_to_serial(self):
        import mpmath
        from e import save_e_to_file
        mpmath.mp.dps = 25
        e_val = +mpmath.e
        path = os.path.join(self._tmp, "e_perm_error.txt")
        buf = io.StringIO()
        with unittest.mock.patch(
            "e.concurrent.futures.ProcessPoolExecutor",
            side_effect=PermissionError("permission denied"),
        ), redirect_stdout(buf):
            save_e_to_file(e_val, 20, path)
        with open(path) as f:
            content = f.read()
        self.assertIn("2.71828182845904523536", content)
        self.assertIn("Parallel mode unavailable", buf.getvalue())
```

- [ ] **Step 2: Add TestProcessPoolSemaphoreExhaustion**

```python
class TestProcessPoolSemaphoreExhaustion(unittest.TestCase):
    """save_e_to_file serial fallback: generic OSError + macOS semaphore errno."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def _e_val(self):
        import mpmath
        mpmath.mp.dps = 25
        return +mpmath.e

    def test_oserror_falls_back_to_serial(self):
        from e import save_e_to_file
        path = os.path.join(self._tmp, "e_sem1.txt")
        buf = io.StringIO()
        with unittest.mock.patch(
            "e.concurrent.futures.ProcessPoolExecutor",
            side_effect=OSError("semaphore limit"),
        ), redirect_stdout(buf):
            save_e_to_file(self._e_val(), 20, path)
        self.assertIn("Parallel mode unavailable", buf.getvalue())
        with open(path) as f:
            self.assertIn("2.71828182845904523536", f.read())

    def test_semaphore_exhaustion_enospc_falls_back_to_serial(self):
        import errno
        from e import save_e_to_file
        path = os.path.join(self._tmp, "e_sem2.txt")
        buf = io.StringIO()
        with unittest.mock.patch(
            "e.concurrent.futures.ProcessPoolExecutor",
            side_effect=OSError(errno.ENOSPC, "No space left on device"),
        ), redirect_stdout(buf):
            save_e_to_file(self._e_val(), 20, path)
        self.assertIn("Parallel mode unavailable", buf.getvalue())
        with open(path) as f:
            self.assertIn("2.71828182845904523536", f.read())
```

- [ ] **Step 3: Add TestMissingGmpy2**

```python
class TestMissingGmpy2(unittest.TestCase):
    """calculate_e uses mpmath path when gmpy2 is absent."""

    def test_missing_gmpy2_uses_mpmath_fallback(self):
        import e as e_module
        buf = io.StringIO()
        with unittest.mock.patch.object(e_module, "_HAS_GMPY2", False), \
             unittest.mock.patch.object(e_module, "_gmpy2", None), \
             redirect_stdout(buf):
            e_val = calculate_e(20)
        result = _e_to_str(e_val, 20)
        self.assertTrue(result.startswith("2.718281828459045"), f"got: {result!r}")
        self.assertNotIn("Error", buf.getvalue())
```

Note: check whether `calculate_e` and `_e_to_str` are imported at the top of `test_e.py`; add to the existing imports if missing.

- [ ] **Step 4: Add TestFileWritePermissionError**

```python
class TestFileWritePermissionError(unittest.TestCase):
    """main() handles PermissionError when the output file cannot be created."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_exits_nonzero_on_permission_error(self):
        from e import main
        buf = io.StringIO()
        with unittest.mock.patch("sys.argv", ["e.py", "10"]), \
             unittest.mock.patch("builtins.input", return_value="n"), \
             unittest.mock.patch(
                 "e.os.open",
                 side_effect=PermissionError("[Errno 13] Permission denied: 'e_10_digits.txt'"),
             ), \
             redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Error", buf.getvalue())
```

- [ ] **Step 5: Run tests and verify all pass**

```bash
cd e && make test
```

Expected: all existing tests pass + all 4 new classes pass (GREEN on first run).

- [ ] **Step 6: Commit**

```bash
cd e
git add test_e.py
git commit -m "test: e — add ProcessPool PermissionError, semaphore exhaustion, missing gmpy2, and file-write failure tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: factorial — Python failure tests + main() error handlers

**Files:**

- Modify: `factorial/test_factorial.py` (append 5 new test classes)
- Modify: `factorial/factorial.py` (add error handling to `main()`)

Two test classes will be RED first (no handlers in factorial's main()), driving new implementation.

- [ ] **Step 1: Add TestProcessPoolPermissionError (GREEN on first run)**

Append to `factorial/test_factorial.py` after `TestOutputFile`:

```python
class TestProcessPoolPermissionError(unittest.TestCase):
    """_compute_swing serial fallback when ProcessPoolExecutor raises PermissionError."""

    def test_falls_back_to_serial(self):
        from unittest.mock import patch
        buf = io.StringIO()
        with patch(
            "factorial.concurrent.futures.ProcessPoolExecutor",
            side_effect=PermissionError("permission denied"),
        ), patch("builtins.print"):
            result = calculate_factorial(10)
        self.assertEqual(int(result), FACTORIAL_REF[10])
```

- [ ] **Step 2: Add TestProcessPoolSemaphoreExhaustion (GREEN on first run)**

```python
class TestProcessPoolSemaphoreExhaustion(unittest.TestCase):
    """_compute_swing serial fallback for semaphore exhaustion (both patterns)."""

    def test_oserror_falls_back_to_serial(self):
        from unittest.mock import patch
        with patch(
            "factorial.concurrent.futures.ProcessPoolExecutor",
            side_effect=OSError("semaphore limit"),
        ), patch("builtins.print"):
            result = calculate_factorial(10)
        self.assertEqual(int(result), FACTORIAL_REF[10])

    def test_semaphore_exhaustion_enospc_falls_back_to_serial(self):
        import errno
        from unittest.mock import patch
        with patch(
            "factorial.concurrent.futures.ProcessPoolExecutor",
            side_effect=OSError(errno.ENOSPC, "No space left on device"),
        ), patch("builtins.print"):
            result = calculate_factorial(10)
        self.assertEqual(int(result), FACTORIAL_REF[10])
```

- [ ] **Step 3: Add TestMissingGmpy2 (GREEN on first run)**

```python
class TestMissingGmpy2(unittest.TestCase):
    """calculate_factorial uses plain int when gmpy2 is absent."""

    def test_missing_gmpy2_uses_int_fallback(self):
        import factorial as factorial_module
        with unittest.mock.patch.object(factorial_module, "_HAS_GMPY2", False), \
             unittest.mock.patch.object(factorial_module, "_gmpy2", None), \
             unittest.mock.patch("builtins.print"):
            result = calculate_factorial(5)
        self.assertIsInstance(result, int)
        self.assertEqual(result, FACTORIAL_REF[5])
```

- [ ] **Step 4: Write TestFileWritePermissionError — expect RED**

```python
class TestFileWritePermissionError(unittest.TestCase):
    """main() handles PermissionError when the output file cannot be written."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_exits_nonzero_on_permission_error(self):
        from factorial import main
        buf = io.StringIO()
        with unittest.mock.patch("sys.argv", ["factorial.py", "5"]), \
             unittest.mock.patch(
                 "builtins.open",
                 side_effect=PermissionError("[Errno 13] Permission denied: 'factorial_5.txt'"),
             ), \
             redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Error", buf.getvalue())
```

- [ ] **Step 5: Run test — confirm RED**

```bash
cd factorial && python3 -m unittest test_factorial.TestFileWritePermissionError -v
```

Expected: FAIL — `PermissionError` propagates uncaught out of `main()`, no `SystemExit` raised.

- [ ] **Step 6: Write TestKeyboardInterruptDuringCompute — expect RED**

```python
class TestKeyboardInterruptDuringCompute(unittest.TestCase):
    """main() handles KeyboardInterrupt during calculation."""

    def test_exits_nonzero_on_keyboard_interrupt(self):
        from factorial import main
        buf = io.StringIO()
        with unittest.mock.patch("sys.argv", ["factorial.py", "5"]), \
             unittest.mock.patch(
                 "factorial.calculate_factorial",
                 side_effect=KeyboardInterrupt,
             ), \
             redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("interrupted", buf.getvalue())
```

- [ ] **Step 7: Run test — confirm RED**

```bash
cd factorial && python3 -m unittest test_factorial.TestKeyboardInterruptDuringCompute -v
```

Expected: FAIL — `KeyboardInterrupt` propagates uncaught, no `SystemExit`.

- [ ] **Step 8: Add error handlers to factorial/factorial.py main()**

Replace the current `main()` body in `factorial/factorial.py`:

```python
def main():
    """Entry point: parse args, compute factorial, write to file."""
    args = parse_args()
    try:
        n = get_target_n(args)
        print(f"Computing {n:,}! ...")
        start = time.time()
        result = calculate_factorial(n)
        elapsed = time.time() - start
        print(f"Computed in {elapsed:.2f}s")
        _write_factorial_file(result, n)
    except KeyboardInterrupt:
        print("\nComputation interrupted.")
        sys.exit(1)
    except PermissionError as err:
        print(f"Error: {err}")
        sys.exit(1)
```

Also add `import sys` at the top of `factorial.py` if it is not already imported (check the imports section).

- [ ] **Step 9: Run all new tests — confirm GREEN**

```bash
cd factorial && python3 -m unittest test_factorial.TestFileWritePermissionError test_factorial.TestKeyboardInterruptDuringCompute -v
```

Expected: both PASS.

- [ ] **Step 10: Run full test suite**

```bash
cd factorial && make test
```

Expected: all tests pass.

- [ ] **Step 11: Commit**

```bash
cd factorial
git add test_factorial.py factorial.py
git commit -m "feat: factorial — add failure-mode tests + KeyboardInterrupt and PermissionError handlers in main()

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: fib — Python failure tests + main() error handlers

**Files:**

- Modify: `fib/test_fib.py` (append 2 new test classes)
- Modify: `fib/fib.py` (add error handling to `main()`)

Both test classes will be RED first.

- [ ] **Step 1: Write TestFileWritePermissionError — expect RED**

Append to `fib/test_fib.py` before `TestEntryPoint`:

```python
class TestFileWritePermissionError(unittest.TestCase):
    """main() handles PermissionError when the output file cannot be written."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_exits_nonzero_on_permission_error(self):
        old_argv = sys.argv
        sys.argv = ["fib.py", "1"]
        try:
            buf = io.StringIO()
            with patch("builtins.input", return_value="n"), \
                 patch(
                     "builtins.open",
                     side_effect=PermissionError("[Errno 13] Permission denied: 'fib_1e1.txt'"),
                 ), \
                 redirect_stdout(buf):
                with self.assertRaises(SystemExit) as cm:
                    main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("Error", buf.getvalue())
        finally:
            sys.argv = old_argv
```

- [ ] **Step 2: Run test — confirm RED**

```bash
cd fib && python3 -m unittest test_fib.TestFileWritePermissionError -v
```

Expected: FAIL — `PermissionError` propagates uncaught.

- [ ] **Step 3: Write TestKeyboardInterrupt — expect RED**

```python
class TestKeyboardInterrupt(unittest.TestCase):
    """main() handles KeyboardInterrupt during generation."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_exits_nonzero_on_keyboard_interrupt(self):
        old_argv = sys.argv
        sys.argv = ["fib.py", "1"]
        try:
            buf = io.StringIO()
            with patch("fib.generate_fibonacci", side_effect=KeyboardInterrupt), \
                 redirect_stdout(buf):
                with self.assertRaises(SystemExit) as cm:
                    main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("interrupted", buf.getvalue())
        finally:
            sys.argv = old_argv
```

- [ ] **Step 4: Run test — confirm RED**

```bash
cd fib && python3 -m unittest test_fib.TestKeyboardInterrupt -v
```

Expected: FAIL — `KeyboardInterrupt` propagates uncaught.

- [ ] **Step 5: Add error handlers to fib/fib.py main()**

In `fib/fib.py`, wrap the body of `main()` after the header prints:

```python
def main() -> None:
    args = parse_args()
    x = get_exponent(args)
    max_digits = 10 ** x

    print("Fibonacci Number Generator (Python)")
    print("=" * 40)

    try:
        if x >= 4:
            print(
                f"Warning: X={x} means Fibonacci numbers with up to {max_digits:,} digits "
                f"— this may take a long time"
            )
            print("         and produce a very large output file.")
            answer = input("Continue? (y/n): ").strip().lower()
            if answer not in ("y", "yes"):
                return

        print(
            f"Generating all Fibonacci numbers with up to 10^{x} = {max_digits:,} digits"
        )

        if x <= 2:
            buf = io.StringIO()
            count = 0
            for fib in generate_fibonacci(max_digits):
                buf.write(str(fib))
                buf.write("\n")
                count += 1

            print(f"\nFound {count:,} Fibonacci numbers with up to 10^{x} digits")
            answer = input(
                f"Display all {count:,} Fibonacci numbers? (y/n): "
            ).strip().lower()
            if answer in ("y", "yes"):
                print(buf.getvalue(), end="")
            else:
                filename = f"fib_1e{x}.txt"
                with open(filename, "w") as f:
                    f.write(buf.getvalue())
                print(f"Saved to {filename}")
        else:
            filename = f"fib_1e{x}.txt"
            print(f"\nSaving to {filename}...")
            count = 0
            with open(filename, "w", buffering=8 * 1024 * 1024) as f:
                for fib in generate_fibonacci(max_digits):
                    f.write(str(fib))
                    f.write("\n")
                    count += 1

            print(f"Found {count:,} Fibonacci numbers with up to 10^{x} digits")
            print(f"Saved to {filename}")
    except KeyboardInterrupt:
        print("\nGeneration interrupted.")
        sys.exit(1)
    except PermissionError as err:
        print(f"Error: {err}")
        sys.exit(1)
```

Ensure `import sys` is present at the top of `fib.py` (it already imports `sys` for `sys.exit` in `get_exponent` — verify before adding a duplicate).

- [ ] **Step 6: Run both new tests — confirm GREEN**

```bash
cd fib && python3 -m unittest test_fib.TestFileWritePermissionError test_fib.TestKeyboardInterrupt -v
```

Expected: both PASS.

- [ ] **Step 7: Run full test suite**

```bash
cd fib && make test
```

Expected: all tests pass including the 5 existing classes.

- [ ] **Step 8: Commit**

```bash
cd fib
git add test_fib.py fib.py
git commit -m "feat: fib — add file-write and KeyboardInterrupt failure tests + error handlers in main()

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: sq — Python failure tests + main() error handlers

**Files:**

- Modify: `sq/test_sq.py` (append 2 new test classes)
- Modify: `sq/sq.py` (add error handling to `main()`)

Both test classes will be RED first.

- [ ] **Step 1: Write TestFileWritePermissionError — expect RED**

Append to `sq/test_sq.py` before `TestEntryPoint`:

```python
class TestFileWritePermissionError(unittest.TestCase):
    """main() handles PermissionError when the output file cannot be written."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_exits_nonzero_on_permission_error(self):
        old_argv = sys.argv
        sys.argv = ["sq.py", "1"]
        try:
            buf = io.StringIO()
            with patch(
                "builtins.open",
                side_effect=PermissionError("[Errno 13] Permission denied: 'sq_1e1.txt'"),
            ), redirect_stdout(buf):
                with self.assertRaises(SystemExit) as cm:
                    main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("Error", buf.getvalue())
        finally:
            sys.argv = old_argv
```

- [ ] **Step 2: Run test — confirm RED**

```bash
cd sq && python3 -m unittest test_sq.TestFileWritePermissionError -v
```

Expected: FAIL — `PermissionError` propagates uncaught.

- [ ] **Step 3: Write TestKeyboardInterrupt — expect RED**

```python
class TestKeyboardInterrupt(unittest.TestCase):
    """main() handles KeyboardInterrupt during generation."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_exits_nonzero_on_keyboard_interrupt(self):
        old_argv = sys.argv
        sys.argv = ["sq.py", "1"]
        try:
            buf = io.StringIO()
            with patch("sq.generate_squares", side_effect=KeyboardInterrupt), \
                 redirect_stdout(buf):
                with self.assertRaises(SystemExit) as cm:
                    main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("interrupted", buf.getvalue())
        finally:
            sys.argv = old_argv
```

- [ ] **Step 4: Run test — confirm RED**

```bash
cd sq && python3 -m unittest test_sq.TestKeyboardInterrupt -v
```

Expected: FAIL — `KeyboardInterrupt` propagates uncaught.

- [ ] **Step 5: Add error handlers to sq/sq.py main()**

In `sq/sq.py`, wrap the computation and file-write section:

```python
def main() -> None:
    args = parse_args()
    x = get_exponent(args)
    max_digits = 10 ** x

    print("Perfect Square Generator (Python)")
    print("=" * 40)
    print(
        f"Generating all perfect squares with up to 10^{x} = {max_digits:,} digits"
    )

    try:
        buf = io.StringIO()
        count = 0
        for sq, root in generate_squares(max_digits):
            buf.write(f"{sq} | {root}\n")
            count += 1

        filename = f"sq_1e{x}.txt"
        with open(filename, "w") as f:
            f.write(buf.getvalue())

        print(f"\nFound {count:,} perfect squares with up to 10^{x} digits")
        print(f"Saved to {filename}")
        answer = input(
            f"Also display all {count:,} perfect squares? (y/n): "
        ).strip().lower()
        if answer in ("y", "yes"):
            print(buf.getvalue(), end="")
    except KeyboardInterrupt:
        print("\nGeneration interrupted.")
        sys.exit(1)
    except PermissionError as err:
        print(f"Error: {err}")
        sys.exit(1)
```

Ensure `import sys` is present at the top of `sq.py`.

- [ ] **Step 6: Run both new tests — confirm GREEN**

```bash
cd sq && python3 -m unittest test_sq.TestFileWritePermissionError test_sq.TestKeyboardInterrupt -v
```

Expected: both PASS.

- [ ] **Step 7: Run full test suite**

```bash
cd sq && make test
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
cd sq
git add test_sq.py sq.py
git commit -m "feat: sq — add file-write and KeyboardInterrupt failure tests + error handlers in main()

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Rust — subprocess failure tests (all 7 crates)

**Files:**

- Modify: `tests/cli.rs` in each of the 7 Rust crates

Add `cli_unwritable_output_dir` to each crate's `tests/cli.rs`. The test creates a read-only temp directory, runs the binary with a file-saving command, and asserts a non-zero exit code.

**Pattern (adapt the binary reference for each crate):**

```rust
#[cfg(unix)]
#[test]
fn cli_unwritable_output_dir() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempdir().unwrap();
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o555)).unwrap();

    let mut child = Command::new(<BINARY_REF>)
        .arg(<VALID_ARG>)
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();

    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(<STDIN_TO_TRIGGER_SAVE>);
    }

    let output = child.wait_with_output().unwrap();
    // Restore permissions so tempdir can be cleaned up.
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o755)).unwrap();

    assert_ne!(
        output.status.code().unwrap_or(0),
        0,
        "expected non-zero exit for unwritable directory, stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}
```

Substitute the following per crate:

| Crate        | `<BINARY_REF>`                                     | `<VALID_ARG>` | `<STDIN_TO_TRIGGER_SAVE>`                   |
| ------------ | -------------------------------------------------- | ------------- | ------------------------------------------- |
| pi-rs        | `env!("CARGO_BIN_EXE_pi")`                         | `"10"`        | `b"n\n"`                                    |
| e-rs         | `env!("CARGO_BIN_EXE_e")`                          | `"10"`        | `b"n\n"`                                    |
| factorial-rs | `PathBuf::from(env!("CARGO_BIN_EXE_factorial"))`   | `"5"`         | `b""` (no prompt — factorial always writes) |
| fib-rs       | `env!("CARGO_BIN_EXE_fib")`                        | `"3"`         | `b""` (x=3 streams directly, no prompt)     |
| sq-rs        | `env!("CARGO_BIN_EXE_sq")`                         | `"1"`         | `b"n\n"`                                    |
| prime-rs     | `env!("CARGO_BIN_EXE_prime")`                      | `"1"`         | `b"n\n"`                                    |
| twin-primes  | `PathBuf::from(env!("CARGO_BIN_EXE_twin-primes"))` | `"1"`         | `b""` (always writes)                       |

Notes:

- factorial-rs and fib-rs (x≥3) always write to a file without prompting — close stdin immediately with no input.
- `use std::io::Write;` and `use std::path::PathBuf;` must be present in the file's imports (check before adding).
- The `use std::os::unix::fs::PermissionsExt;` import is inside the test function, so no top-level change needed.

- [ ] **Step 1: Add to pi/pi-rs/tests/cli.rs and run**

Add the test using the pi-rs substitutions above.

```bash
cd pi/pi-rs && make test
```

Expected: new test passes (pi-rs propagates IO errors via `?` to main).

- [ ] **Step 2: Add to e/e-rs/tests/cli.rs and run**

```bash
cd e/e-rs && make test
```

- [ ] **Step 3: Add to factorial/factorial-rs/tests/cli.rs and run**

Note: `factorial-rs` uses `PathBuf::from(env!("CARGO_BIN_EXE_factorial"))` as the binary reference (matching the existing helper function pattern in that file). Close stdin immediately (`b""`).

```bash
cd factorial/factorial-rs && make test
```

- [ ] **Step 4: Add to fib/fib-rs/tests/cli.rs and run**

Use `x=3` (no prompt, streams directly to file).

```bash
cd fib/fib-rs && make test
```

- [ ] **Step 5: Add to sq/sq-rs/tests/cli.rs and run**

```bash
cd sq/sq-rs && make test
```

- [ ] **Step 6: Add to prime/prime-rs/tests/cli.rs and run**

```bash
cd prime/prime-rs && make test
```

- [ ] **Step 7: Add to twin-primes/twin-primes-rs/tests/cli.rs and run**

Use `PathBuf::from(env!("CARGO_BIN_EXE_twin-primes"))`. No prompt — always writes.

```bash
cd twin-primes/twin-primes-rs && make test
```

- [ ] **Step 8: Commit all 7 cli.rs changes**

```bash
git add \
  pi/pi-rs/tests/cli.rs \
  e/e-rs/tests/cli.rs \
  factorial/factorial-rs/tests/cli.rs \
  fib/fib-rs/tests/cli.rs \
  sq/sq-rs/tests/cli.rs \
  prime/prime-rs/tests/cli.rs \
  twin-primes/twin-primes-rs/tests/cli.rs
git commit -m "test: all Rust crates — add cli_unwritable_output_dir subprocess failure test

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Rust — unit injection tests (all 7 crates)

**Files:**

- Modify: `src/main.rs` in each of the 7 Rust crates (add to `#[cfg(test)] mod tests` block)

Note: `run()` is private, so injection tests must live inside `#[cfg(test)] mod tests` in `src/main.rs` — not in `tests/unit_errors.rs`. This deviates from the spec's filename but is required by Rust's visibility rules.

**FailWriter struct** — add once inside each crate's `#[cfg(test)] mod tests` block:

```rust
struct FailWriter;

impl std::io::Write for FailWriter {
    fn write(&mut self, _buf: &[u8]) -> std::io::Result<usize> {
        Err(std::io::Error::other("injected write failure"))
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}
```

**Stdout failure test** — `run()` writes a header to stdout first; FailWriter causes immediate Err:

**Stderr failure test** — use an invalid argument so `run()` writes an error to stderr; FailWriter on stderr causes Err.

The exact call for each crate:

**pi-rs** (add inside `mod tests { use super::*; ... }`):

```rust
#[test]
fn run_returns_err_on_stdout_failure() {
    let dir = tempdir().unwrap();
    let mut err = Vec::new();
    let mut reader = std::io::Cursor::new("n\n");
    let cli = Cli { digits: Some(10) };
    let result = run(cli, &mut reader, &mut FailWriter, &mut err, dir.path());
    assert!(result.is_err(), "expected Err on stdout failure, got {:?}", result);
}

#[test]
fn run_returns_err_on_stderr_failure() {
    // digits=0 is invalid; run() writes error to stderr → FailWriter → Err
    let dir = tempdir().unwrap();
    let mut out = Vec::new();
    let mut reader = std::io::Cursor::new("");
    let cli = Cli { digits: Some(0) };
    let result = run(cli, &mut reader, &mut out, &mut FailWriter, dir.path());
    assert!(result.is_err(), "expected Err on stderr failure for digits=0, got {:?}", result);
}
```

**e-rs** (same pattern, substitute `Cli { digits: Some(10) }` and `Cli { digits: Some(0) }`):

```rust
#[test]
fn run_returns_err_on_stdout_failure() {
    let dir = tempdir().unwrap();
    let mut err = Vec::new();
    let mut reader = std::io::Cursor::new("n\n");
    let cli = Cli { digits: Some(10) };
    let result = run(cli, &mut reader, &mut FailWriter, &mut err, dir.path());
    assert!(result.is_err(), "expected Err on stdout failure");
}

#[test]
fn run_returns_err_on_stderr_failure() {
    let dir = tempdir().unwrap();
    let mut out = Vec::new();
    let mut reader = std::io::Cursor::new("");
    let cli = Cli { digits: Some(0) };
    let result = run(cli, &mut reader, &mut out, &mut FailWriter, dir.path());
    assert!(result.is_err(), "expected Err on stderr failure for digits=0");
}
```

**factorial-rs** (uses `n_arg: Option<&str>` not `Cli`):

```rust
#[test]
fn run_returns_err_on_stdout_failure() {
    let dir = tempdir().unwrap();
    let mut err = Vec::new();
    let mut reader = std::io::Cursor::new("");
    let result = run(Some("5"), &mut reader, &mut FailWriter, &mut err, dir.path());
    assert!(result.is_err(), "expected Err on stdout failure");
}

#[test]
fn run_returns_err_on_stderr_failure() {
    // "abc" is invalid; run() writes parse error to stderr
    let dir = tempdir().unwrap();
    let mut out = Vec::new();
    let mut reader = std::io::Cursor::new("");
    let result = run(Some("abc"), &mut reader, &mut out, &mut FailWriter, dir.path());
    assert!(result.is_err(), "expected Err on stderr failure for invalid arg");
}
```

**fib-rs** (`Cli { exponent: Some(1) }`):

```rust
#[test]
fn run_returns_err_on_stdout_failure() {
    let dir = tempdir().unwrap();
    let mut err = Vec::new();
    let mut reader = std::io::Cursor::new("n\n");
    let cli = Cli { exponent: Some(1) };
    let result = run(cli, &mut reader, &mut FailWriter, &mut err, dir.path());
    assert!(result.is_err(), "expected Err on stdout failure");
}

#[test]
fn run_returns_err_on_stderr_failure() {
    // exponent=6 is out of range; run() writes error to stderr
    let dir = tempdir().unwrap();
    let mut out = Vec::new();
    let mut reader = std::io::Cursor::new("");
    let cli = Cli { exponent: Some(6) };
    let result = run(cli, &mut reader, &mut out, &mut FailWriter, dir.path());
    assert!(result.is_err(), "expected Err on stderr failure for exponent=6");
}
```

**sq-rs** (`Cli { exponent: Some(1) }`, exponent=2 is out of range):

```rust
#[test]
fn run_returns_err_on_stdout_failure() {
    let dir = tempdir().unwrap();
    let mut err = Vec::new();
    let mut reader = std::io::Cursor::new("n\n");
    let cli = Cli { exponent: Some(1) };
    let result = run(cli, &mut reader, &mut FailWriter, &mut err, dir.path());
    assert!(result.is_err(), "expected Err on stdout failure");
}

#[test]
fn run_returns_err_on_stderr_failure() {
    // exponent=2 is invalid for sq (only 1 is valid)
    let dir = tempdir().unwrap();
    let mut out = Vec::new();
    let mut reader = std::io::Cursor::new("");
    let cli = Cli { exponent: Some(2) };
    let result = run(cli, &mut reader, &mut out, &mut FailWriter, dir.path());
    assert!(result.is_err(), "expected Err on stderr failure for exponent=2");
}
```

**prime-rs** (`Cli { digits: Some(1) }`, digits=0 is out of range):

```rust
#[test]
fn run_returns_err_on_stdout_failure() {
    let dir = tempdir().unwrap();
    let mut err = Vec::new();
    let mut reader = std::io::Cursor::new("n\n");
    let cli = Cli { digits: Some(1) };
    let result = run(cli, &mut reader, &mut FailWriter, &mut err, dir.path());
    assert!(result.is_err(), "expected Err on stdout failure");
}

#[test]
fn run_returns_err_on_stderr_failure() {
    let dir = tempdir().unwrap();
    let mut out = Vec::new();
    let mut reader = std::io::Cursor::new("");
    let cli = Cli { digits: Some(0) };
    let result = run(cli, &mut reader, &mut out, &mut FailWriter, dir.path());
    assert!(result.is_err(), "expected Err on stderr failure for digits=0");
}
```

**twin-primes-rs** (no `Cli`, takes `digits: u32` directly; no reader parameter):

```rust
#[test]
fn run_returns_err_on_stdout_failure() {
    let dir = tempdir().unwrap();
    let mut err = Vec::new();
    let result = run(1, &mut FailWriter, &mut err, dir.path());
    assert!(result.is_err(), "expected Err on stdout failure");
}

#[test]
fn run_returns_err_on_stderr_failure() {
    // digits=0 is out of range; run() writes error to stderr (FailWriter)
    let dir = tempdir().unwrap();
    let mut out = Vec::new();
    let result = run(0, &mut out, &mut FailWriter, dir.path());
    assert!(result.is_err(), "expected Err on stderr failure for digits=0");
}
```

- [ ] **Step 1: Add FailWriter + tests to pi/pi-rs/src/main.rs and run**

Find the `#[cfg(test)] mod tests {` block. Add `FailWriter` after the `use super::*;` block, then add the two test functions.

```bash
cd pi/pi-rs && make test
```

Expected: 2 new tests pass. Tarpaulin coverage ≥90%.

- [ ] **Step 2: Add to e/e-rs/src/main.rs and run**

```bash
cd e/e-rs && make test
```

- [ ] **Step 3: Add to factorial/factorial-rs/src/main.rs and run**

```bash
cd factorial/factorial-rs && make test
```

- [ ] **Step 4: Add to fib/fib-rs/src/main.rs and run**

```bash
cd fib/fib-rs && make test
```

- [ ] **Step 5: Add to sq/sq-rs/src/main.rs and run**

```bash
cd sq/sq-rs && make test
```

- [ ] **Step 6: Add to prime/prime-rs/src/main.rs and run**

```bash
cd prime/prime-rs && make test
```

- [ ] **Step 7: Add to twin-primes/twin-primes-rs/src/main.rs and run**

```bash
cd twin-primes/twin-primes-rs && make test
```

- [ ] **Step 8: Commit all 7 src/main.rs changes**

```bash
git add \
  pi/pi-rs/src/main.rs \
  e/e-rs/src/main.rs \
  factorial/factorial-rs/src/main.rs \
  fib/fib-rs/src/main.rs \
  sq/sq-rs/src/main.rs \
  prime/prime-rs/src/main.rs \
  twin-primes/twin-primes-rs/src/main.rs
git commit -m "test: all Rust crates — add FailWriter injection tests for run() stdout/stderr error propagation

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Update CLAUDE.md and docs indexes

**Files:**

- Modify: `pi/CLAUDE.md`, `e/CLAUDE.md`, `factorial/CLAUDE.md`, `fib/CLAUDE.md`, `sq/CLAUDE.md` (test coverage tables)
- Modify: `pi/pi-rs/CLAUDE.md`, `e/e-rs/CLAUDE.md`, `factorial/factorial-rs/CLAUDE.md`, `fib/fib-rs/CLAUDE.md`, `sq/sq-rs/CLAUDE.md`, `prime/prime-rs/CLAUDE.md`, `twin-primes/twin-primes-rs/CLAUDE.md` (test tables + coverage)
- Modify: `docs/superpowers/README.md` and `docs/cursor/README.md` (mark plan as Done, add plan row)

- [ ] **Step 1: Update each Python CLAUDE.md test coverage table**

For each Python project, update the test class table to include the new classes, and update the total test count and coverage percentage after running `make coverage`.

Run coverage for each:

```bash
cd pi && make coverage
cd e && make coverage
cd factorial && make coverage
cd fib && make coverage
cd sq && make coverage
```

- [ ] **Step 2: Update each Rust CLAUDE.md test coverage table**

Run tarpaulin for each Rust crate after the test changes:

```bash
cd pi/pi-rs && cargo tarpaulin --out Stdout 2>&1 | tail -5
# (repeat for each crate)
```

Update the coverage % and test counts in each crate's CLAUDE.md.

- [ ] **Step 3: Update docs indexes**

In `docs/superpowers/README.md`, update the failure-mode-test-matrix row:

- Change status from `Pending` to `Done`
- Add plan file reference

In `docs/cursor/README.md`, same update.

Add `> **Status: DONE**` banner at the top of this plan file.

- [ ] **Step 4: Commit documentation updates**

```bash
git add \
  pi/CLAUDE.md e/CLAUDE.md factorial/CLAUDE.md fib/CLAUDE.md sq/CLAUDE.md \
  pi/pi-rs/CLAUDE.md e/e-rs/CLAUDE.md factorial/factorial-rs/CLAUDE.md \
  fib/fib-rs/CLAUDE.md sq/sq-rs/CLAUDE.md prime/prime-rs/CLAUDE.md \
  twin-primes/twin-primes-rs/CLAUDE.md \
  docs/superpowers/README.md docs/cursor/README.md \
  docs/superpowers/plans/2026-05-09-failure-mode-test-matrix.md
git commit -m "docs: update CLAUDE.md coverage tables and mark failure-mode test matrix done

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```
