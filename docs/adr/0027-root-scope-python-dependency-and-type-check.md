# ADR-0027: Declare and type-check root-scope Python

**Date:** 2026-09-05
**Status:** Accepted

## Context

This repo's Python lives in two populations. Eight sub-projects each have a Makefile, an
`install_deps.sh`, a `pyrightconfig.json`, and a `*-py.yml` workflow — that population is
governed by ADR-0015 (pyright) and ADR-0023 (pytest). The other population is root scope:
`scripts/`, `tests/`, and `.claude/scripts/`, which has a Makefile but no installer and, until
now, almost no type checking. Two gaps followed from that asymmetry, both measured.

**Dependencies were declared nowhere a fresh checkout reads.** `tests/test_release_workflows.py`
imports `yaml` unguarded and `scripts/test_metrics.py` imports `defusedxml` unguarded, while
`pyyaml==6.0.3` and `defusedxml` appeared only in `.github/workflows/scripts.yml`. Since
`scripts/pre-push` runs the root `make test` on any change under `scripts/` or `tests/`, a fresh
checkout failed the hook:

```
baseline                       rc=0   Ran 82 tests   OK
yaml blocked                   rc=1   Ran 52 tests   FAILED (errors=1)
defusedxml blocked             rc=1   Ran 80 tests   FAILED (errors=1)
make test-python (no pyyaml)   rc=2
```

Note the 30 tests that vanish when `yaml` is blocked: `unittest discover` reports an
unimportable module as one error and continues, so the headline is a single failure while a
whole file's coverage is absent. The suite still exits non-zero, so this was an ergonomics gap
rather than a safety hole — nothing told you what to install.

**Root-scope type checking covered 2 of 8 tracked files.** CI ran `pyright` with
`working-directory: scripts` against a `scripts/pyrightconfig.json` whose `include` was
`["time_tests.py", "test_metrics.py"]`. Everything under `tests/` and `.claude/scripts/` was
checked by nothing.

## Decision

**Dependencies.** A tracked `requirements-dev.txt` at the repo root declares the third-party
modules root-scope Python *imports* — not the tools a gate runs. A root `make install-deps`
target consumes it, guarded on PEP 668:

```make
install-deps:
	@command -v python3 >/dev/null 2>&1 || { printf 'python3 not found on PATH.\n' >&2; exit 1; }
	@python3 -c '<venv-aware EXTERNALLY-MANAGED probe>' || { printf '<venv remedy>\n' >&2; exit 1; }
	python3 -m pip install -r requirements-dev.txt
```

The import/tool split is a real boundary, not a convenience: a missing import is a hard
`ImportError`, while `lint-python` guards a missing `ruff` with `ifndef RUFF` and exits 0 by
design. Different failure semantics, different declaration site. `ruff`, `pyright` and
`pip-audit` therefore stay on the workflow's install line.

A root `install_deps.sh` was rejected. The 19 sub-project installers exist for directories that
each have a Makefile; root already diverges, and `tests/scripts/install_deps.bats` derives its
population from `git ls-files '*/Makefile' '*/*/Makefile'`, neither of which matches a
zero-slash root `Makefile`. A `requirements*.txt` is also the artifact `dependency-review`'s
manifest regex can see, so two previously invisible hand-typed dependencies became reviewable.

**Type checking.** A root `pyrightconfig.json` replaces `scripts/pyrightconfig.json`:

```json
{
  "include": ["scripts", "tests", ".claude/scripts"],
  "exclude": ["**/node_modules", "**/__pycache__"],
  "pythonVersion": "3.11",
  "typeCheckingMode": "standard",
  "reportMissingImports": true,
  "reportMissingModuleSource": false
}
```

`working-directory: scripts` is dropped from the workflow step. The denominator moves from 2 of
8 to 10 of 10 tracked root-scope `.py` files.

Two properties of pyright govern that config and were measured rather than assumed:

- **`exclude` beats `include`.** pyright's default `exclude` carries `**/.*`, so naming
  `.claude/scripts` in `include` is not sufficient — 7 files analysed with the default list, 8
  without `**/.*`. Omitting it is the only reason `.claude/scripts/triage_log.py` is reachable,
  which is why the omission is pinned by a test rather than left to a reader's judgement.
- **pyright walks up for config**, like `ruff.toml`. `cd scripts && pyright` loads the root
  config. The 8 sub-project gates are unaffected because each has its own config, found before
  the walk-up reaches root — not because no walk-up happens.

`typeCheckingMode` is `standard` here, where ADR-0015 chose `basic` for sub-projects. Root
scope has no gmpy2 and no Rust extension modules, so neither suppression that motivated `basic`
applies.

**This extends ADR-0015 rather than superseding it.** All 8 sub-project configs are unchanged
and its decision still holds for the population it describes; it is simply silent about root
scope.

## Consequences

**Easier.** A fresh checkout has one command. Root-scope type errors are caught by CI instead of
never. Two dependencies that no filename rule could reach are now visible to
`dependency-review`. `pyright` is pinned in `scripts.yml`, so that gate's verdict no longer
floats with whatever `pip install pyright` resolves.

**Harder, and required going forward.**

- A third root-scope third-party import must be added to `requirements-dev.txt`.
  `tests/test_root_python_deps.py` derives every unguarded third-party import by AST and fails
  otherwise, so this is enforced rather than remembered. Its classifier excludes first-party
  roots derived from `git ls-files`; without that clause a `from scripts…` import would demand a
  `scripts` package that does not exist.
- The root config's `include`/`exclude` are pinned by identity in
  `tests/test_root_pyright_scope.py`. Widening the scope means editing that assertion
  deliberately.
- `pyright` now runs under `make test-python`, which the pre-push hook invokes, so it is no
  longer CI-only. Measured at `real 0.90` locally, so the cost is negligible — but CLAUDE.md's
  prior "CI only … slow on macOS" note is corrected rather than carried.
- `pyright` is pinned at 1 of 9 install sites. The other 8 `*-py.yml` workflows remain unpinned
  and are backlogged; each needs its own green check at a pinned version.
- `make install-deps` refuses on an externally-managed interpreter rather than using
  `--break-system-packages`. On the Linux 7950X (Python 3.12.3, marker present) this means a
  venv is required. The guard reproduces pip's own predicate including its virtualenv
  short-circuit; a marker-only check refuses *inside* the venv it recommends.

## Related

- [ADR-0015](0015-pyright-type-checking-python.md) — pyright for sub-projects; this extends it to root scope
- [ADR-0017](0017-defusedxml-xxe-safe-xml-parsing.md) — why `defusedxml` is imported at all
- [ADR-0023](0023-pytest-as-python-test-runner.md) — sub-project test runner; root scope uses `unittest`
- [Spec](../superpowers/specs/2026-09-05-root-python-gate-holes-design.md) · [Plan](../superpowers/plans/2026-09-05-root-python-gate-holes.md)
