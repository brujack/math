# ADR-0031: A Vendored, Exact gmpy2 Type Stub, So Every Python Project Runs Pyright Standard

**Date:** 2026-10-25
**Status:** Accepted. Spec: `docs/superpowers/specs/2026-10-25-uniform-project-cli-and-python-files-design.md` (R9).

## Context

gmpy2 2.3.x ships no `.pyi` and no `py.typed`. pi and e therefore ran pyright in `basic` mode
with `reportAttributeAccessIssue` and `reportOptionalMemberAccess` switched off, while the
other six projects ran `standard`. That made pyright a per-project difference, which the
operator rule (all projects treated the same) counts as a defect. At `standard` with no
overrides, master gave e 41 errors and pi 78.

`pyright --createstub gmpy2` produces a 7-line stub that only re-exports the C extension, which
removes no error. Wrapping gmpy2 calls in typed helpers only moves the unknown-attribute error
into the helper.

## Decision

- **One hand-written stub.** `typings/gmpy2/__init__.pyi` at the repo root types exactly the
  names, classes and methods e and pi use: `mpz`, `mpfr`, `context.precision`, `get_context`,
  `sqrt`, `mpfr.digits` and the version functions.
- **Every config uses it.** All 8 Python `pyrightconfig.json` files set
  `"stubPath": "../typings"` and `"typeCheckingMode": "standard"`, with no report overrides.
- **The stub is exact.** It never claims more than runtime does:
  - `mpz ** <non-negative literal>` returns `mpz`, but `mpz ** int` returns `mpz | mpfr`,
    because a negative exponent returns `mpfr`.
  - Arguments that gmpy2 accepts only positionally are positional-only.
  - It contains no `Any`. The only `object` is the `other` parameter of `__eq__`/`__ne__`.
  - Each rule was checked against the installed gmpy2 before it was written.
- **The optional import is narrowed per function.** e and pi narrow it with
  `_gmpy2 is not None` at each dispatch site. Each gmpy2-only function starts with
  `gm = _require_gmpy2()`, which raises `RuntimeError` if gmpy2 is absent. pyright does not
  carry a caller's check into the callee, so the check has to be in each function.
- **A test guards the stub.** `tests/test_gmpy2_stub.py` fails if the stub contains `Any`
  (including inside a string annotation) or an `object` outside `__eq__`/`__ne__`. It also
  fails if e or pi uses a gmpy2 name the stub lacks. The test runs whenever `typings/`
  changes, from both `scripts.yml` and pre-push.

## Consequences

- **All 8 projects share one pyright config.** It differs only in `include`. A gmpy2 typing
  mistake in e or pi now fails CI.
- **The stub has to be maintained.** A new gmpy2 name used anywhere must be added to it, and
  the guard test names the missing one. A gmpy2 upgrade that changes behaviour (Renovate) can
  make the stub stale, and nothing checks the stub against the runtime automatically.
- **pyright is the primary gate for attribute use.** The guard's alias scan is a cheap
  backstop. It covers direct, `import ... as` and simple-assignment aliases. Its remaining
  blind spots are a Backlog row.
- **gmpy2 missing at a gmpy2-only call is a clear error.** `_require_gmpy2()` raises a named
  `RuntimeError` instead of an `AttributeError` on `None`. The mpmath fallback paths never
  reach it.
