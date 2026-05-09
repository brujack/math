# Failure-Mode Test Matrix for Compute CLIs

**Date:** 2026-05-09
**Status:** Pending

---

## Context

The compute CLIs (pi, e, factorial, fib, sq in Python; pi-rs, e-rs, factorial-rs, fib-rs, sq-rs, prime-rs, twin-primes-rs in Rust) handle several environment failure modes in code — parallel-executor errors, missing dependencies, permission errors — but most of those paths are untested. This spec adds explicit failure-mode tests across all projects and, for fib and sq, drives implementation of the missing `KeyboardInterrupt` and file-write error handlers via TDD.

---

## Scope

- **Python:** pi, e, factorial, fib, sq
- **Rust:** pi-rs, e-rs, factorial-rs, fib-rs, sq-rs, prime-rs, twin-primes-rs
- **Not in scope:** memory exhaustion, subprocess timeout/hang, disk-full simulation (requires filesystem mocking beyond standard `unittest.mock`)

---

## Design

### Structure

Tests are added inline to existing test files — no new test files for Python. Each Rust crate gets one new file `tests/unit_errors.rs` for write-injection tests; subprocess failures extend the existing `tests/cli.rs`. Every project's `make test` already discovers all test files, so no Makefile changes are needed.

Coverage gate: all changes must keep each project at or above its current coverage floor (≥90% line coverage for all projects — enforced via `cargo tarpaulin` for Rust, `coverage report` for Python).

---

### Python Failure Test Matrix

New test classes appended to each project's existing `test_*.py`. Follow the existing class-per-behavior convention already used in these files.

#### pi, e, factorial (have `ProcessPoolExecutor` parallel paths)

| Test class                           | Failure simulated               | Mock target                                             | Expected behavior                                |
| ------------------------------------ | ------------------------------- | ------------------------------------------------------- | ------------------------------------------------ |
| `TestProcessPoolPermissionError`     | `PermissionError` from executor | `ProcessPoolExecutor.__init__` raises `PermissionError` | Falls back to serial; prints serial-mode message |
| `TestProcessPoolSemaphoreExhaustion` | Semaphore limit hit             | See semaphore section below                             | Falls back to serial; prints serial-mode message |
| `TestMissingGmpy2`                   | `gmpy2` not installed           | `sys.modules['gmpy2'] = None` blocks import             | Falls back to `mpmath`; no crash                 |
| `TestFileWritePermissionError`       | Output file unwritable          | `builtins.open` raises `PermissionError`                | Prints error; exits non-zero                     |
| `TestKeyboardInterruptDuringCompute` | User hits Ctrl-C                | Patch compute function to raise `KeyboardInterrupt`     | Exits cleanly with exit code 1                   |

**Note:** `factorial` currently has no `main()` `KeyboardInterrupt` handler. `TestKeyboardInterruptDuringCompute` will be RED first — implement the handler to go green (TDD).

#### fib, sq (no parallel execution)

| Test class                     | Failure simulated      | Mock target                                                | Expected behavior              |
| ------------------------------ | ---------------------- | ---------------------------------------------------------- | ------------------------------ |
| `TestFileWritePermissionError` | Output file unwritable | `builtins.open` raises `PermissionError`                   | Prints error; exits non-zero   |
| `TestKeyboardInterrupt`        | User hits Ctrl-C       | Patch main loop / output loop to raise `KeyboardInterrupt` | Exits cleanly with exit code 1 |

**Note:** Neither `fib` nor `sq` currently handle `KeyboardInterrupt` or file-write errors. Both test classes will be RED first — drive the handlers into the implementation to go green.

---

### Semaphore Exhaustion (pi, e, factorial)

Two test methods inside `TestProcessPoolSemaphoreExhaustion`:

**Pattern-based** (closes the immediate gap) — validates the fallback fires for any `OSError`:

```python
@patch('concurrent.futures.ProcessPoolExecutor', side_effect=OSError("semaphore"))
def test_oserror_falls_back_to_serial(self, mock_pool):
    ...
```

**Semaphore-specific** (stretch goal, same class) — validates the exact macOS signal that triggered the original fallback implementation:

```python
@patch('multiprocessing.Semaphore', side_effect=OSError(errno.ENOSPC, "No space left on device"))
def test_semaphore_exhaustion_falls_back_to_serial(self, mock_sem):
    ...
```

Both are `unittest.mock.patch` one-liners. The exact mock target path (`concurrent.futures.ProcessPoolExecutor` vs the module-local import) must match the import site in each source file.

---

### Rust Failure Test Matrix

#### Subprocess tests (additions to `tests/cli.rs`)

| Test                        | Failure simulated             | Method                                            | Expected behavior                                |
| --------------------------- | ----------------------------- | ------------------------------------------------- | ------------------------------------------------ |
| `cli_unwritable_output_dir` | Output file in unwritable dir | `std::fs::set_permissions` on tempdir, run binary | Non-zero exit; stderr contains error message     |
| `cli_zero_input`            | N=0 or exponent=0             | Pass `"0"` as argument                            | Non-zero exit (verify uniform across all crates) |
| `cli_empty_input`           | No argument, empty stdin      | Spawn with no args; write empty bytes to stdin    | Non-zero exit or clean prompt-loop exit          |

#### Unit injection tests (new `tests/unit_errors.rs` per crate)

A `FailWriter` struct implements `Write` and returns `Err` on the first write:

```rust
use std::io::{self, Write};

struct FailWriter;

impl Write for FailWriter {
    fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
        Err(io::Error::other("injected write failure"))
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
```

| Test                                | Injected failure           | Expected behavior                                 |
| ----------------------------------- | -------------------------- | ------------------------------------------------- |
| `run_returns_err_on_stdout_failure` | `FailWriter` as stdout `W` | `run()` returns `Err` or exits non-zero; no panic |
| `run_returns_err_on_stderr_failure` | `FailWriter` as stderr `E` | Error propagates without panic                    |

**Refactoring rule:** If `run()` does not return `Result` today, change the return type if the modification is a straightforward single-function signature change. If the call chain is deeply entangled (requires threading `Result` through many layers), document as a known gap and skip the injection test for that crate rather than introducing a large refactor.

---

## TDD Requirements

All new tests follow the standard red-green-refactor cycle:

1. Write the failing test first
2. Confirm it fails for the right reason
3. Write the minimum implementation to make it pass
4. Commit

For `fib` and `sq`: `TestFileWritePermissionError` and `TestKeyboardInterrupt` must be RED before any handler code is written. For `factorial`: `TestKeyboardInterruptDuringCompute` must be RED before the `KeyboardInterrupt` handler is added to `main()`.

---

## Success Criteria

- All new test classes pass (`make test` green) for every project
- Python projects: `PermissionError`, semaphore exhaustion (both variants), missing `gmpy2`, file-write errors, and `KeyboardInterrupt` are tested in pi, e, and factorial
- `fib` and `sq` each have file-write error and `KeyboardInterrupt` handlers driven in by TDD
- Every Rust crate has at least one new subprocess failure test in `tests/cli.rs`
- Every Rust crate where `run()` returns `Result` (or can be trivially changed to) has injection tests in `tests/unit_errors.rs`
- No project drops below its coverage floor

---

## Out of Scope

- Disk-full simulation (requires real filesystem quota manipulation)
- Subprocess timeout / hung-worker injection
- Memory exhaustion
- Cross-project shared Python test helper infrastructure
