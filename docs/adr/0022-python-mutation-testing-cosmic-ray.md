# ADR 0022: Python mutation testing with cosmic-ray (supersedes ADR-0012)

- **Date:** 2026-06-13
- **Status:** Accepted
- **Supersedes:** ADR-0012

## Context

ADR-0012 adopted **mutmut** for Python mutation testing. After the Python 3.14 upgrade, mutmut tracebacks on every run: its pytest-based discovery copies tests into a `mutants/` directory and re-imports them, which fails for the `test_*.py` modules in each math sub-project. Patching mutmut's runner is open-ended; pinning Python 3.13 for one optional tool forces downgrades on every dev machine and CI runner.

The goal of mutation testing — verifying that tests detect behavior changes, not just that lines execute — is unchanged. Only the tool needs to swap.

## Decision

Adopt **cosmic-ray** as the Python mutation testing tool across all 8 Python sub-projects (`fib`, `amicable`, `collatz`, `e`, `factorial`, `perfect-numbers`, `pi`, `sq`). Mirrors ai-config ADR-0011.

Per sub-project:

- `cosmic-ray.toml` declares `module-path = "<name>.py"`, `test-command = "python3 -m unittest test_<name>"`, `timeout = 30.0` (60.0 for `e` and `pi` because of larger gmpy2 runs), and the in-process `local` distributor
- `make mutants` runs `cosmic-ray init` + `cosmic-ray exec` + `cr-report`
- `make mutants-report` regenerates `mutants-report.txt` from the existing session DB without re-running mutations
- `make mutants-clean` removes both the session SQLite and the report
- `install_deps.sh` installs `cosmic-ray` in place of `mutmut`

CI:

- `.github/workflows/mutation-testing-python.yml` retains the existing `workflow_dispatch` + monthly schedule (1st of month, 09:00 UTC, 2 h after Rust mutation testing). The artifact name moves from `mutmut-output` (`.mutmut-cache`) to `mutants-report-python` (`**/mutants-report.txt`), 30-day retention. 120-minute job timeout unchanged.

Mutation testing remains **non-blocking** — never gates merges, never fails CI. Monthly reports drive targeted test additions, not PR status.

## Consequences

Positive:

- Python 3.14 compatible; no toolchain pin.
- Same test-runner contract (`python3 -m unittest`); zero test rewrites — the existing 28 (sq) to 84 (pi) test classes work as-is.
- SQLite session DB persists between `cosmic-ray exec` and `cr-report`, enabling re-querying without re-running.
- Smoke test on `sq`: 116 mutations, 13 surviving (88.8 % kill rate) — the surviving mutants are real signal for tests to strengthen.

Negative:

- `cosmic-ray-session.sqlite` must be `.gitignore`d in addition to `.mutmut-cache` (kept the latter entry for cleanup safety on stale checkouts).
- An interrupted `cosmic-ray exec` (timeout, Ctrl-C) leaves the target Python file in its mutated state on disk — discovered during this PR's setup. ai-config memory `cosmic-ray-mid-run-mutation-leak` captures the gotcha; check `git diff` after any interrupted run.

Neutral:

- Cargo-mutants (Rust) is the equivalent for Rust crates — see ADR-0014; unchanged.

## Related

- ADR 0012: Python mutation testing with mutmut (superseded)
- ADR 0014: Cargo-mutants for Rust mutation testing
- ai-config ADR-0011: cosmic-ray over mutmut (the cross-cutting decision)
- `.claude/standards/python.md`: mutation testing usage and Makefile target pattern
