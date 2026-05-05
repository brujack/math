# Parallel Fallback Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardize the parallel→serial fallback message across all five Python fallback sites and add a Backend/threads line to `factorial-rs` to match the other Rust crates.

**Architecture:** Six independent red→green→commit cycles — one per fallback site (pi Phase A, pi Phase B, e Phase A, e Phase B, factorial Python) plus one for the Rust crate. Each cycle writes a failing test first, then makes the minimal change to pass it. No shared modules; all changes are in-place.

**Tech Stack:** Python `unittest.mock`, `io.StringIO`, `redirect_stdout`; Rust `std::process::Command`; rayon; existing `concurrent.futures.ProcessPoolExecutor` pattern.

---

## File Map

| File                                  | Change                                                   |
| ------------------------------------- | -------------------------------------------------------- |
| `pi/test_pi.py`                       | Add 2 test classes (Phase A fallback, Phase B fallback)  |
| `pi/pi.py`                            | Replace 2 fallback `print()` calls with standard message |
| `e/test_e.py`                         | Add 2 test classes (Phase A fallback, Phase B fallback)  |
| `e/e.py`                              | Replace 2 fallback `print()` calls with standard message |
| `factorial/test_factorial.py`         | Add 1 test class (swing fallback)                        |
| `factorial/factorial.py`              | Replace 1 fallback `print()` call with standard message  |
| `factorial/factorial-rs/tests/cli.rs` | Add 1 test asserting Backend line in stderr              |
| `factorial/factorial-rs/src/main.rs`  | Add `writeln!` Backend line before "Computing…"          |

---

## Standard Message

All five Python sites use this exact `print()` call (replace the old one):

```python
print(
    f"\nParallel mode unavailable ({err}); falling back to serial.\n"
    "Install project requirements and ensure OS multiprocessing "
    "semaphore support is available to re-enable parallel mode."
)
```

---

## Task 1: pi.py Phase A fallback — test + fix

**Files:**

- Modify: `pi/test_pi.py` (add test class after `TestCalculatePiParallel`)
- Modify: `pi/pi.py:185-192`

- [ ] **Step 1: Write the failing test**

  Add this class to `pi/test_pi.py` immediately after the `TestCalculatePiParallel` class:

  ```python
  @unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
  class TestCalculatePiGmpy2PhaseAFallback(unittest.TestCase):
      """_calculate_pi_gmpy2 serial fallback when ProcessPoolExecutor raises OSError."""

      def test_fallback_result_correct_and_message_printed(self):
          buf = io.StringIO()
          # digits=2000 -> N=152 terms -> n_workers=2, triggering the parallel path
          with unittest.mock.patch(
              "pi.concurrent.futures.ProcessPoolExecutor",
              side_effect=OSError("semaphore unavailable"),
          ), redirect_stdout(buf):
              pi_val = calculate_pi_high_precision(2000)
          self.assertEqual(_pi_to_str(pi_val, 20)[:22], PI_REF[:22])
          self.assertIn("Parallel mode unavailable", buf.getvalue())
  ```

- [ ] **Step 2: Run to confirm RED**

  ```bash
  cd pi && python -m unittest test_pi.TestCalculatePiGmpy2PhaseAFallback -v
  ```

  Expected: FAIL — `AssertionError: 'Parallel mode unavailable' not found in '...'`
  (the current message is `"Parallel unavailable"`, not `"Parallel mode unavailable"`)

- [ ] **Step 3: Fix pi.py Phase A message**

  In `pi/pi.py`, find the `except (PermissionError, OSError) as err:` block inside `_calculate_pi_gmpy2` (around line 185). Replace:

  ```python
          except (PermissionError, OSError) as err:
              print(
                  "\n  Parallel unavailable "
                  f"({err}); running in serial mode. "
                  "Install project requirements and ensure OS multiprocessing "
                  "semaphore support is available to re-enable parallel mode."
              )
              _, Q, T = _chudnovsky_bs(0, N)
  ```

  With:

  ```python
          except (PermissionError, OSError) as err:
              print(
                  f"\nParallel mode unavailable ({err}); falling back to serial.\n"
                  "Install project requirements and ensure OS multiprocessing "
                  "semaphore support is available to re-enable parallel mode."
              )
              _, Q, T = _chudnovsky_bs(0, N)
  ```

- [ ] **Step 4: Run to confirm GREEN**

  ```bash
  cd pi && python -m unittest test_pi.TestCalculatePiGmpy2PhaseAFallback -v
  ```

  Expected: OK

- [ ] **Step 5: Run the full pi test suite**

  ```bash
  cd pi && make test
  ```

  Expected: all tests pass

- [ ] **Step 6: Commit**

  ```bash
  git add pi/pi.py pi/test_pi.py
  git commit -m "fix: standardize parallel fallback message in pi.py Phase A"
  ```

---

## Task 2: pi.py Phase B fallback — test + fix

**Files:**

- Modify: `pi/test_pi.py` (add test class after `TestSavePiEstimateAndProgress`)
- Modify: `pi/pi.py:551-556`

- [ ] **Step 1: Write the failing test**

  Add this class to `pi/test_pi.py` after `TestSavePiEstimateAndProgress`:

  ```python
  class TestSavePiToFilePhaseAFallback(unittest.TestCase):
      """save_pi_to_file serial fallback when ProcessPoolExecutor raises OSError."""

      def setUp(self):
          self._cwd = os.getcwd()
          self._tmp = tempfile.mkdtemp()
          os.chdir(self._tmp)

      def tearDown(self):
          os.chdir(self._cwd)
          for f in os.listdir(self._tmp):
              os.unlink(os.path.join(self._tmp, f))
          os.rmdir(self._tmp)

      def test_fallback_writes_file_and_prints_message(self):
          import mpmath
          mpmath.mp.dps = 25
          pi_val = +mpmath.pi
          path = os.path.join(self._tmp, "pi_fallback.txt")
          buf = io.StringIO()
          with unittest.mock.patch(
              "pi.concurrent.futures.ProcessPoolExecutor",
              side_effect=OSError("semaphore unavailable"),
          ), redirect_stdout(buf):
              save_pi_to_file(pi_val, 20, path)
          content = open(path).read()
          self.assertTrue(
              content.startswith("3.14159265358979323846"),
              f"unexpected content: {content[:30]}",
          )
          self.assertIn("Parallel mode unavailable", buf.getvalue())
  ```

- [ ] **Step 2: Run to confirm RED**

  ```bash
  cd pi && python -m unittest test_pi.TestSavePiToFilePhaseAFallback -v
  ```

  Expected: FAIL — `AssertionError: 'Parallel mode unavailable' not found`

- [ ] **Step 3: Fix pi.py Phase B message**

  In `pi/pi.py`, find the `except (PermissionError, OSError) as err:` block inside `save_pi_to_file` (around line 551). Replace:

  ```python
      except (PermissionError, OSError) as err:
          print(
              "\nMultiprocessing conversion unavailable "
              f"({err}); running in serial mode. "
              "Install project requirements and ensure OS multiprocessing "
              "semaphore support is available to re-enable parallel mode."
          )
  ```

  With:

  ```python
      except (PermissionError, OSError) as err:
          print(
              f"\nParallel mode unavailable ({err}); falling back to serial.\n"
              "Install project requirements and ensure OS multiprocessing "
              "semaphore support is available to re-enable parallel mode."
          )
  ```

- [ ] **Step 4: Run to confirm GREEN**

  ```bash
  cd pi && python -m unittest test_pi.TestSavePiToFilePhaseAFallback -v
  ```

  Expected: OK

- [ ] **Step 5: Run the full pi test suite**

  ```bash
  cd pi && make test
  ```

  Expected: all tests pass

- [ ] **Step 6: Commit**

  ```bash
  git add pi/pi.py pi/test_pi.py
  git commit -m "fix: standardize parallel fallback message in pi.py Phase B"
  ```

---

## Task 3: e.py Phase A fallback — test + fix

**Files:**

- Modify: `e/test_e.py` (add test class after `TestCalculateEParallel`, line 321)
- Modify: `e/e.py:190-197`

- [ ] **Step 1: Write the failing test**

  Add this class to `e/test_e.py` immediately after `TestCalculateEParallel` (line 321):

  ```python
  @unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
  class TestCalculateEGmpy2PhaseAFallback(unittest.TestCase):
      """_calculate_e_gmpy2 serial fallback when ProcessPoolExecutor raises OSError."""

      def test_fallback_result_correct_and_message_printed(self):
          from e import _e_to_str
          buf = io.StringIO()
          # digits=2000 -> N large enough for n_workers > 1
          with unittest.mock.patch(
              "e.concurrent.futures.ProcessPoolExecutor",
              side_effect=OSError("semaphore unavailable"),
          ), redirect_stdout(buf):
              e_val = calculate_e(2000)
          self.assertEqual(_e_to_str(e_val, 20)[:22], E_REF[:22])
          self.assertIn("Parallel mode unavailable", buf.getvalue())
  ```

- [ ] **Step 2: Run to confirm RED**

  ```bash
  cd e && python -m unittest test_e.TestCalculateEGmpy2PhaseAFallback -v
  ```

  Expected: FAIL — `AssertionError: 'Parallel mode unavailable' not found`

- [ ] **Step 3: Fix e.py Phase A message**

  In `e/e.py`, find the `except (PermissionError, OSError) as err:` block inside `_calculate_e_gmpy2` (around line 190). Replace:

  ```python
          except (PermissionError, OSError) as err:
              print(
                  "\n  Parallel unavailable "
                  f"({err}); running in serial mode. "
                  "Install project requirements and ensure OS multiprocessing "
                  "semaphore support is available to re-enable parallel mode."
              )
              P, Q = _taylor_bs(0, N)
  ```

  With:

  ```python
          except (PermissionError, OSError) as err:
              print(
                  f"\nParallel mode unavailable ({err}); falling back to serial.\n"
                  "Install project requirements and ensure OS multiprocessing "
                  "semaphore support is available to re-enable parallel mode."
              )
              P, Q = _taylor_bs(0, N)
  ```

- [ ] **Step 4: Run to confirm GREEN**

  ```bash
  cd e && python -m unittest test_e.TestCalculateEGmpy2PhaseAFallback -v
  ```

  Expected: OK

- [ ] **Step 5: Run the full e test suite**

  ```bash
  cd e && make test
  ```

  Expected: all tests pass

- [ ] **Step 6: Commit**

  ```bash
  git add e/e.py e/test_e.py
  git commit -m "fix: standardize parallel fallback message in e.py Phase A"
  ```

---

## Task 4: e.py Phase B fallback — test + fix

**Files:**

- Modify: `e/test_e.py` (add test class after `TestSaveEEstimateAndProgress` or equivalent)
- Modify: `e/e.py:443-448`

- [ ] **Step 1: Write the failing test**

  Add this class to `e/test_e.py` after the estimate/progress test class:

  ```python
  class TestSaveEToFilePhaseAFallback(unittest.TestCase):
      """save_e_to_file serial fallback when ProcessPoolExecutor raises OSError."""

      def setUp(self):
          self._cwd = os.getcwd()
          self._tmp = tempfile.mkdtemp()
          os.chdir(self._tmp)

      def tearDown(self):
          os.chdir(self._cwd)
          for f in os.listdir(self._tmp):
              os.unlink(os.path.join(self._tmp, f))
          os.rmdir(self._tmp)

      def test_fallback_writes_file_and_prints_message(self):
          import mpmath
          from e import save_e_to_file
          mpmath.mp.dps = 25
          e_val = +mpmath.e
          path = os.path.join(self._tmp, "e_fallback.txt")
          buf = io.StringIO()
          with unittest.mock.patch(
              "e.concurrent.futures.ProcessPoolExecutor",
              side_effect=OSError("semaphore unavailable"),
          ), redirect_stdout(buf):
              save_e_to_file(e_val, 20, path)
          content = open(path).read()
          self.assertTrue(
              content.startswith("2.71828182845904523536"),
              f"unexpected content: {content[:30]}",
          )
          self.assertIn("Parallel mode unavailable", buf.getvalue())
  ```

- [ ] **Step 2: Run to confirm RED**

  ```bash
  cd e && python -m unittest test_e.TestSaveEToFilePhaseAFallback -v
  ```

  Expected: FAIL — `AssertionError: 'Parallel mode unavailable' not found`

- [ ] **Step 3: Fix e.py Phase B message**

  In `e/e.py`, find the `except (PermissionError, OSError) as err:` block inside `save_e_to_file` (around line 443). Replace:

  ```python
      except (PermissionError, OSError) as err:
          print(
              "\nMultiprocessing conversion unavailable "
              f"({err}); running in serial mode. "
              "Install project requirements and ensure OS multiprocessing "
              "semaphore support is available to re-enable parallel mode."
          )
  ```

  With:

  ```python
      except (PermissionError, OSError) as err:
          print(
              f"\nParallel mode unavailable ({err}); falling back to serial.\n"
              "Install project requirements and ensure OS multiprocessing "
              "semaphore support is available to re-enable parallel mode."
          )
  ```

- [ ] **Step 4: Run to confirm GREEN**

  ```bash
  cd e && python -m unittest test_e.TestSaveEToFilePhaseAFallback -v
  ```

  Expected: OK

- [ ] **Step 5: Run the full e test suite**

  ```bash
  cd e && make test
  ```

  Expected: all tests pass

- [ ] **Step 6: Commit**

  ```bash
  git add e/e.py e/test_e.py
  git commit -m "fix: standardize parallel fallback message in e.py Phase B"
  ```

---

## Task 5: factorial.py fallback — test + fix

**Files:**

- Modify: `factorial/test_factorial.py` (add test class after `TestComputeSwing`)
- Modify: `factorial/factorial.py:127-133`

- [ ] **Step 1: Write the failing test**

  Add this class to `factorial/test_factorial.py` after `TestComputeSwing`:

  ```python
  class TestComputeSwingFallback(unittest.TestCase):
      """_compute_swing serial fallback when ProcessPoolExecutor raises OSError."""

      def test_fallback_gives_correct_result_and_prints_message(self):
          buf = io.StringIO()
          # n=5: _compute_swing(5, [2,3,5]) -> 3 chunks with default _CPU_COUNT,
          # triggering ProcessPoolExecutor. With it raising, serial fallback runs.
          with unittest.mock.patch(
              "factorial.concurrent.futures.ProcessPoolExecutor",
              side_effect=OSError("semaphore unavailable"),
          ), redirect_stdout(buf):
              result = calculate_factorial(5)
          self.assertEqual(int(result), FACTORIAL_REF[5])
          self.assertIn("Parallel mode unavailable", buf.getvalue())
  ```

- [ ] **Step 2: Run to confirm RED**

  ```bash
  cd factorial && python -m unittest test_factorial.TestComputeSwingFallback -v
  ```

  Expected: FAIL — `AssertionError: 'Parallel mode unavailable' not found`
  (current message is `"Parallel swing unavailable"`)

- [ ] **Step 3: Fix factorial.py message**

  In `factorial/factorial.py`, find the `except (PermissionError, OSError) as err:` block inside `_compute_swing` (around line 127). Replace:

  ```python
      except (PermissionError, OSError) as err:
          print(
              "Parallel swing unavailable "
              f"({err}); running in serial mode. "
              "Install project requirements and ensure OS multiprocessing "
              "semaphore support is available to re-enable parallel mode."
          )
          partial_results = [_compute_swing_chunk(m, chunk) for chunk in chunks]
  ```

  With:

  ```python
      except (PermissionError, OSError) as err:
          print(
              f"\nParallel mode unavailable ({err}); falling back to serial.\n"
              "Install project requirements and ensure OS multiprocessing "
              "semaphore support is available to re-enable parallel mode."
          )
          partial_results = [_compute_swing_chunk(m, chunk) for chunk in chunks]
  ```

- [ ] **Step 4: Run to confirm GREEN**

  ```bash
  cd factorial && python -m unittest test_factorial.TestComputeSwingFallback -v
  ```

  Expected: OK

- [ ] **Step 5: Run the full factorial test suite**

  ```bash
  cd factorial && make test
  ```

  Expected: all tests pass

- [ ] **Step 6: Commit**

  ```bash
  git add factorial/factorial.py factorial/test_factorial.py
  git commit -m "fix: standardize parallel fallback message in factorial.py"
  ```

---

## Task 6: factorial-rs Backend line — test + implementation

**Files:**

- Modify: `factorial/factorial-rs/tests/cli.rs` (add 1 test)
- Modify: `factorial/factorial-rs/src/main.rs` (add `writeln!` in `run()`)

- [ ] **Step 1: Write the failing test**

  Add this test to `factorial/factorial-rs/tests/cli.rs` after the last `#[test]`:

  ```rust
  #[test]
  fn cli_backend_line_shows_thread_count() {
      let dir = tempdir().unwrap();
      let output = Command::new(factorial_bin())
          .arg("5")
          .current_dir(dir.path())
          .output()
          .unwrap();
      assert_eq!(output.status.code().unwrap(), 0);
      let stderr = String::from_utf8_lossy(&output.stderr);
      assert!(
          stderr.contains("rayon (") && stderr.contains("threads)"),
          "expected Backend line with thread count in stderr, got: {stderr}",
      );
  }
  ```

- [ ] **Step 2: Build the binary and run to confirm RED**

  ```bash
  cd factorial/factorial-rs && cargo build --release 2>&1 | tail -3
  cargo test cli_backend_line_shows_thread_count -- --nocapture 2>&1
  ```

  Expected: test FAILS — stderr does not contain `"rayon ("` because the Backend line is not yet printed

- [ ] **Step 3: Add the Backend line to factorial-rs**

  In `factorial/factorial-rs/src/main.rs`, find the `run()` function body. Locate this line (around line 161):

  ```rust
      writeln!(err, "Computing {}! ...", fmt_int(n))?;
  ```

  Add the Backend line immediately before it:

  ```rust
      writeln!(err, "Backend: prime swing / rug+GMP / rayon ({} threads)", rayon::current_num_threads())?;
      writeln!(err, "Computing {}! ...", fmt_int(n))?;
  ```

- [ ] **Step 4: Run to confirm GREEN**

  ```bash
  cd factorial/factorial-rs && cargo test cli_backend_line_shows_thread_count -- --nocapture 2>&1
  ```

  Expected: test passes

- [ ] **Step 5: Run the full factorial-rs test suite**

  ```bash
  cd factorial/factorial-rs && make test
  ```

  Expected: all tests pass, tarpaulin coverage ≥ 90%

- [ ] **Step 6: Commit**

  ```bash
  git add factorial/factorial-rs/src/main.rs factorial/factorial-rs/tests/cli.rs
  git commit -m "feat: add Backend/threads line to factorial-rs output"
  ```

---

## Acceptance Verification

After all six tasks are committed, run this sweep to confirm no old labels remain:

```bash
grep -rn "Parallel unavailable\|Multiprocessing conversion unavailable\|Parallel swing unavailable" \
  pi/pi.py e/e.py factorial/factorial.py
```

Expected: no output (zero matches).

Run all affected test suites:

```bash
cd pi && make test && cd ../e && make test && cd ../factorial && make test && \
  cd factorial-rs && make test
```

Expected: all pass.
