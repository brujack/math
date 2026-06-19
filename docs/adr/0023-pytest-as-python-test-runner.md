---
name: 0023-pytest-as-python-test-runner
status: Accepted
date: 2026-06-19
---

# 0023 — pytest as Python test runner

## Context

All 8 Python sub-projects (`factorial`, `fib`, `pi`, `e`, `amicable`, `collatz`,
`perfect-numbers`, `sq`) used `python3 -m unittest <module> -v` as their test
runner in Makefile `test` and `coverage` targets. The `coverage` target used the
`coverage` CLI directly (`coverage run -m unittest …` + `coverage report`).

`unittest` is adequate for test discovery and assertions, but:

- Invocation is verbose (`python3 -m unittest discover -s . -p 'test_*.py'`)
- Coverage integration requires a separate `coverage` CLI invocation chain
- No `--fail-under` threshold enforcement at the coverage gate
- Output formatting is minimal; `pytest`'s detailed failure output is more useful

`pytest` discovers and runs `unittest.TestCase` subclasses natively — test file
contents are unchanged. The switch is an invocation-layer change only.

Simultaneously, the `lint` target was extended to include `ruff format --check .`
alongside `ruff check .`. The format gate ensures consistent style is enforced at
pre-commit time and not only on CI.

## Decision

Migrate all 8 Python sub-project Makefiles:

- `test` target: `python3 -m unittest …` → `pytest <test_file>.py -v`
- `coverage` target: `coverage run … && coverage report` → `pytest --cov=<module> --cov-report=term-missing --cov-fail-under=90 <test_file>.py`
- `lint` target: `ruff check .` → `ruff check . && ruff format --check .`

All test file `.py` contents remain unchanged — `pytest` runs `unittest.TestCase`
subclasses natively.

## Consequences

- `pytest` binary must be present in the active Python environment. Added to the
  `ansible` pyenv virtualenv in `lib/developer.sh` (same session, ec12372).
- `--cov-fail-under=90` enforces the ≥90% coverage gate at the Makefile layer, not
  only in CI — consistent with ADR-0019.
- `ruff format --check .` blocks commits when formatting is inconsistent. A one-time
  `ruff format .` pass was applied to all 8 sub-projects before adding the gate.
- CI Python workflows (`*-py.yml`) are unaffected — they run `make test` which now
  calls `pytest` transparently.

## Related

- [ADR-0019](0019-90-percent-coverage-gate-ci.md) — ≥90% coverage gate
- [ADR-0015](0015-pyright-type-checking-python.md) — Pyright type checking
- [ADR-0011](0011-cargo-nextest-rust-test-runner.md) — analogous decision for Rust (nextest)
