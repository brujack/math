# Parallel Fallback Consistency — Design Spec

**Date:** 2026-05-05
**Status:** Draft

## Context

Three Python calculators (`pi`, `e`, `factorial`) fall back from `ProcessPoolExecutor`
to serial execution when the OS raises `PermissionError` or `OSError` (e.g. semaphore
unavailable). Each has its own fallback message wording. Four Rust crates (`pi-rs`,
`e-rs`, `prime-rs`, `factorial-rs`) use rayon thread pools; three of the four print a
Backend line showing the thread count. The contract is inconsistent in two ways:

1. Python fallback messages differ in prefix, label, and formatting across five sites.
2. `factorial-rs` uses rayon but does not print a Backend/threads line.

## Goal

- One standard Python fallback message across all five sites.
- All Rust crates that use rayon print a consistent Backend line showing thread count.
- Tests exercise every fallback site so regressions are caught.

## Out of Scope

- `fib-rs`, `sq-rs`, `twin-primes-rs` — do not use rayon; no Backend line needed.
- Rust-side fallback: rayon threads do not have OS semaphore restrictions; no
  process-level fallback concept applies.
- Changing which exceptions trigger Python fallback (`PermissionError`, `OSError`).

---

## Python Changes

### Standard Message Template

All five fallback sites use this exact string (newline, message, newline, hint):

```
\nParallel mode unavailable ({err}); falling back to serial.\nInstall project requirements and ensure OS multiprocessing semaphore support is available to re-enable parallel mode.
```

Printed via `print(...)` immediately before the serial fallback path executes,
matching the existing pattern.

### Affected Sites

| File                     | Site                             | Current label                              |
| ------------------------ | -------------------------------- | ------------------------------------------ |
| `pi/pi.py`               | Phase A — Chudnovsky computation | `"  Parallel unavailable"`                 |
| `pi/pi.py`               | Phase B — string conversion      | `"Multiprocessing conversion unavailable"` |
| `e/e.py`                 | Phase A — Taylor computation     | `"  Parallel unavailable"`                 |
| `e/e.py`                 | Phase B — string conversion      | `"Multiprocessing conversion unavailable"` |
| `factorial/factorial.py` | Swing computation                | `"Parallel swing unavailable"`             |

Each site: replace the existing `print(...)` call with the standard template, keeping
the surrounding `except (PermissionError, OSError) as err:` and serial fallback logic
unchanged.

---

## Rust Changes

### `factorial-rs` Backend Line

Add one `writeln!` call in `run()`, immediately before `"Computing {}! ..."`:

```rust
writeln!(err, "Backend: prime swing / rug+GMP / rayon ({} threads)", rayon::current_num_threads())?;
```

This matches the position and format used by `pi-rs`, `e-rs`, and `prime-rs`.

---

## Tests

### Python — per fallback site

For each of the five sites, add a test class to the calculator's existing test file
(`test_pi.py`, `test_e.py`, `test_factorial.py`) that:

1. Patches the `ProcessPoolExecutor` class via `unittest.mock.patch` (e.g.
   `"pi.concurrent.futures.ProcessPoolExecutor"`) with `side_effect=OSError("semaphore
unavailable")` so instantiation raises immediately.
2. Calls the function that contains the fallback site.
3. Asserts the return value / result matches the known-good serial output.
4. Asserts the captured stdout contains `"Parallel mode unavailable"`.

Two new test classes in `test_pi.py` (phase A, phase B), two in `test_e.py`
(phase A, phase B), one in `test_factorial.py` (swing).

### Rust — `factorial-rs`

Add one test to `factorial-rs/tests/cli.rs` that runs the binary with a small input
and asserts stderr contains `"rayon ("` and `"threads)"`, matching the pattern
used in `pi-rs` and `e-rs` CLI tests.

---

## Acceptance Criteria

- `make test` passes in `pi/`, `e/`, `factorial/`, and `factorial/factorial-rs/`.
- `grep` across the three Python files finds no remnant of the old message labels
  (`"Parallel unavailable"`, `"Multiprocessing conversion unavailable"`,
  `"Parallel swing unavailable"`).
- `factorial-rs` binary output includes a Backend line with thread count.
- Coverage does not drop below 90% in any affected project.
