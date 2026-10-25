# ADR-0032: Per-Project Build and CI Files Are Rendered From One Template Per Kind

**Date:** 2026-10-25
**Status:** Accepted. Spec: `docs/superpowers/specs/2026-10-25-uniform-project-cli-and-python-files-design.md` (R10-R16).

## Context

The operator rule (2026-10-24) is that all 11 projects are treated the same, all of the time:
a per-project difference is a defect unless it is a declared, justified parameter.

Hand-copied per-project files drifted anyway. Before math#166-#170, the 11 Rust crates'
Makefiles, installers and workflows differed in ways nobody had chosen. Before this change the
8 Python projects differed in the same way:

- all 8 installers left every package but `ruff` unpinned, 5 of them with `--upgrade`, and 5 installed no C libraries;
- only 3 workflows installed GMP and MPFR or published test metrics;
- steps ran in 4 different orders;
- one project's check was named `test` instead of `Test <module>.py`;
- cosmic-ray timeouts were 30 s in six projects and 60 s in two;
- amicable's `clean` removed its output files, six others' `clean` did not, and sq had no `clean` target.

None of these differences was recorded as a decision.

## Decision

- **One template per kind.** Every per-project build and CI file is rendered from one
  template per file kind under `scripts/crate_templates/`:
  - Rust crates: `Makefile`, `rustfmt.toml`, `.config/nextest.toml`, `install_deps.sh`,
    `<crate>-rs.yml` and `release-<crate>-rs.yml`.
  - Python projects, from `python/`: `Makefile`, `install_deps.sh`, `<project>-py.yml`,
    `pyrightconfig.json` and `cosmic-ray.toml`.
- **Two placeholders only.** `@CRATE@` is the project directory. `@MODULE@` is the Python
  module name (the directory with `-` replaced by `_`), and Python templates only may use it.
  `scripts/render_crate_files.py` rejects any other `@NAME@`, so a template cannot grow a
  per-project parameter silently.
- **Drift fails a test.** `tests/test_crate_uniformity.py` fails when any rendered file
  differs from its template. `scripts.yml` triggers on every rendered path and on every
  template, so an edit to either runs that test.
- **Every Python pip install is pinned.** Each `pip install` in the rendered Python files
  pins `name==X.Y.Z`, with one version per package across the 16 sites. `tests/test_tool_pins.py`
  enforces this.
- **The Python `benchmark` target and its CI step are removed.** The CLI contract harness's
  `--smoke` run inside `make test` (ADR-0030) exercises the same sizes. A test asserts that
  no Python workflow has a benchmark step.

## Consequences

- **A per-project change is a template change.** It reaches every project by
  `render_crate_files.py --write`, never by editing one copy.
- **Program-specific detail cannot live in a rendered file.** Notes that were in rendered
  files now live in each project's `CLAUDE.md`, for example the equivalent-mutant notes that
  were in three `cosmic-ray.toml` files.
- **A legitimate difference needs a new placeholder.** Adding one is a renderer change with
  its own test, which is the point: the difference becomes a declared parameter.
- **Some installs are still unpinned.** The pip installs in `mutation-testing-python.yml`,
  `mutation-pr.yml` and `scripts.yml` are outside the scanned sites and carry no version.
  They are a Backlog row.
