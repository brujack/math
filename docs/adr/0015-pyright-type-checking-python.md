# ADR 0015: Pyright type checking for Python sub-projects

- **Date:** 2026-05-22
- **Status:** Accepted

## Context

Python sub-projects had no static type checking. Type errors in mathematical functions — wrong argument types, None returns used without null checks, incorrect numeric types passed to C extensions — were caught only at runtime or by tests, never statically. As sub-projects grew more complex (gmpy2 integration, defusedxml parsing, multiprocessing), static analysis became necessary to maintain correctness with confidence.

## Decision

Add pyright to all Python sub-projects in CI (`pyright` step in each `*-py.yml` workflow). Each sub-project gets a `pyrightconfig.json` with `typeCheckingMode: "basic"`.

Standard `pyrightconfig.json`:

```json
{
  "include": ["<module>.py", "test_<module>.py"],
  "pythonVersion": "3.11",
  "typeCheckingMode": "basic",
  "reportMissingImports": true,
  "reportMissingModuleSource": false
}
```

`reportMissingModuleSource: false` is required across all sub-projects — Rust extension modules (compiled `.so` files) have no Python source for pyright to find.

**Two necessary suppressions:**

**gmpy2:** No type stubs, no `py.typed`. Suppress `reportAttributeAccessIssue` and `reportOptionalMemberAccess` in `pyrightconfig.json` for sub-projects using gmpy2 heavily (`pi/`, `e/`). These fire as errors (not warnings) in `basic` mode on CI (Ubuntu), where pyright cannot see `mpz`, `mpfr`, `get_context`, etc.

**defusedxml:** No `.pyi` stubs. `tree.getroot()` return type is unresolvable, making every downstream attribute access an error. Fix with a local type annotation at one line rather than suppressing globally:

```python
import xml.etree.ElementTree as ET           # stdlib — for type annotations only
from defusedxml import ElementTree as _defused_ET

root: ET.Element = tree.getroot()  # type: ignore[union-attr]
```

**Pyright exit code trap:** Never capture pyright's exit code via a pipeline:

```bash
# Wrong — tail's exit code (always 0) masks pyright's
pyright 2>&1 | tail -5

# Correct
pyright
```

**Mode upgrade:** 6 sub-projects that do not use gmpy2 are upgraded to `standard` mode (stricter) where the additional strictness adds value without false positives from missing stubs.

## Consequences

- Type errors caught in CI before they reach tests
- gmpy2-heavy sub-projects (`pi/`, `e/`) stay at `basic` mode with attribute suppressions
- `standard` mode used where gmpy2 is absent — stricter checking at no cost
- `reportMissingModuleSource: false` required across all sub-projects (Rust extension modules)
- defusedxml: one `# type: ignore[union-attr]` at `getroot()` rather than a global suppression

## Related

- ADR 0017: defusedxml for XXE-safe XML parsing in scripts
- ADR 0016: pip-audit advisory security scan in CI
- `.claude/standards/python.md`: Pyright configuration, gmpy2 suppression, defusedxml pattern, exit code trap
