# Python Mutant Killing — Design Spec

**Date:** 2026-07-03
**Status:** Approved
**Backlog item:** Kill surviving mutants in remaining Python modules

---

## Problem

All 8 Python sub-projects have cosmic-ray configured but no surviving mutant reports have
been acted on. PR #83 killed mutants in Rust crates (goldbach-rs, perfect-numbers-rs,
amicable-rs, collatz-rs); the Python modules remain untouched. The monthly CI workflow
generates advisory reports but nothing has consumed them.

---

## Scope

All 8 Python sub-projects:

| Module          | Source file        | cosmic-ray timeout |
| --------------- | ------------------ | ------------------ |
| sq              | sq.py              | 30s                |
| fib             | fib.py             | 30s                |
| factorial       | factorial.py       | 30s                |
| collatz         | collatz.py         | 30s                |
| amicable        | amicable.py        | 30s                |
| perfect-numbers | perfect_numbers.py | 30s                |
| pi              | pi.py              | 60s                |
| e               | e.py               | 60s                |

---

## Workflow

### Phase 1: Discovery

Run `make mutants` in each module directory. Each invocation:

1. Clears the SQLite session: `rm -f cosmic-ray-session.sqlite`
2. Initialises: `cosmic-ray init cosmic-ray.toml cosmic-ray-session.sqlite`
3. Executes mutations: `cosmic-ray exec cosmic-ray.toml cosmic-ray-session.sqlite`
4. Reports: `cr-report cosmic-ray-session.sqlite --show-output --show-diff > mutants-report.txt`

Run the fast 6 (30s timeout) first. pi and e (60s timeout) run after — they may take
60–90 minutes each.

**Session files are ephemeral** — `cosmic-ray-session.sqlite` and `mutants-report.txt`
are `.gitignore`d and not committed.

### Phase 2: Triage

For each surviving mutant, apply one of two verdicts:

**Real gap** — the mutation changes observable behavior (return value, output string,
file contents, comparison direction) that tests should detect but don't. Fix: write a
test targeting the specific behavior.

**Equivalent mutation** — code changes but all valid inputs produce identical output.
Common patterns in math algorithms:

- Loop bound over-estimate caught by a break/yield condition (e.g., `p*p <= n` →
  `p+p <= n` where the inner loop terminates at the same point)
- Dead branch unreachable by any valid integer input
- Algebraic identity: two expressions evaluate identically for all domain values

Fix: add an operator exclusion to the module's `cosmic-ray.toml` and document why.

### Phase 3: Fix

**Tests (real gaps):**

- Add to the existing `test_<module>.py` in the appropriate `unittest.TestCase` subclass
- Follow existing patterns: boundary values, stdout assertions via `io.StringIO`, file
  existence assertions, prompt-driven tests via `unittest.mock.patch`
- Tests must pass under both `python3 -m unittest test_<module>` and `pytest test_<module>.py`
  (all existing test classes use `unittest.TestCase`)

**Exclusions (equivalent mutations):**

cosmic-ray 8.x supports per-module operator configuration via `cosmic-ray.toml`. Add
an `[cosmic-ray.operators.<OperatorName>]` block with a `skip` list, or disable the
operator entirely via the `[cosmic-ray.operators]` section. Always include a comment
explaining the invariant that makes the mutation equivalent.

Example:

```toml
# Equivalent: p*p→p+p changes the sieve loop bound but the inner break/yield
# condition produces identical output for all valid inputs.
[cosmic-ray.operators.ReplaceArithmeticOperator]
skip = ["Multiply_Mul_Add"]
```

If cosmic-ray's operator API doesn't support per-mutation granularity, restructure the
source to make the equivalent branch explicitly unreachable (guard with an assert or
precondition check that the mutation cannot satisfy).

### Phase 4: Verify

After fixes for each module:

1. `make test` — confirm no regressions
2. `make mutants` — confirm surviving count drops to 0 (or all remaining are documented
   equivalents that have been excluded in the toml)

---

## PR Structure

One feature branch. One commit per module (up to 8 commits). Single PR titled:

```
test(mutation): kill surviving mutants in Python modules
```

Commit messages follow the pattern from PR #83:

```
test(mutation): kill surviving mutants in <module>

Real gaps fixed (new tests):
- <module>: <description of what the test catches>

Equivalent mutations excluded:
- <module>: <invariant reason>
```

---

## Risks

- **pi/e runtime**: 100+ mutations at 60s each = up to 2h per module. If local runtime
  is prohibitive, fall back to CI artifact from `mutation-testing-python.yml`.
- **cosmic-ray operator API**: If `[cosmic-ray.operators]` granularity is insufficient
  for per-mutation exclusions, restructure source to make the branch unreachable.
- **Test command mismatch**: cosmic-ray.toml uses `python3 -m unittest` while Makefiles
  now run `pytest`. Both work because all test classes are `unittest.TestCase` subclasses.
  No toml updates needed.

---

## Out of Scope

- Updating cosmic-ray.toml `test-command` to pytest (no functional difference)
- pi/e type-checking upgrades (Pyright standard mode — separate backlog item)
- Mutation score threshold gating (separate backlog item)
