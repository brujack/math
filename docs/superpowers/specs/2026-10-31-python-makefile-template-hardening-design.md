# Python Makefile template hardening — design

Date: 2026-10-31. Repo: math. Source: two Backlog rows in `docs/superpowers/README.md`.

- "Interrupted local `make mutants` leaves mutated source".
- "Sub-project Python `Makefile` template runs ruff unguarded".

Both live in `scripts/crate_templates/python/Makefile`, which `scripts/render_crate_files.py` renders to the 8 Python projects. The operator chose to ship them as one spec, one plan and one PR.

## Problem

1. **An interrupted `make mutants` can leave a mutant in the source file.**
   - cosmic-ray 8.7.0 edits the module in place for each mutant and restores it when it exits normally.
   - On SIGTERM or SIGKILL it does not restore, so the checked-out `<module>.py` keeps the mutated line.
   - A later commit can then carry it: the hooks lint the file, they do not test its semantics, and a surviving mutant passes the tests by definition.
   - CI runners are thrown away, but local runs are exposed. A full pi run takes hours, and `timeout` sends TERM by default.
2. **The template's `lint` runs ruff unguarded.**
   - `lint` calls `ruff check .` and `ruff format --check .` directly.
   - On a pyenv machine whose active Python has no ruff, the shim answers and exits 127, so `make lint` (and so `make test`) fails instead of skipping.
   - math#192 fixed the same trap in the root `Makefile` (`RUFF := $(shell ruff --version >/dev/null 2>&1 && command -v ruff)`).

## Measurements

All on Linux `claude`, 2026-10-31, master `9b328bc`.

| What                       | Command                                                                                                                     | Result                                                                                                                                     | Population                                                                                                   |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| Interrupt behaviour        | `git archive HEAD` into a temp dir, then `cd fib && timeout -s <SIG> 25 make mutants`, then `git diff --stat -- fib/fib.py` | INT: rc 124, `fib.py` unchanged. TERM: rc 124, 1 line changed. KILL: rc 137, 1 line changed                                                | fib only, one run per signal, cosmic-ray 8.7.0. INT restores because cosmic-ray handles `KeyboardInterrupt`. |
| Where the outputs are read | `grep` across `mutation-testing-python.yml` and `mutation-python-cell.sh`                                                   | CI uploads `<dir>/cosmic-ray-session.sqlite` and `<dir>/mutants-report.txt`. The cell script passes `STATUS_OUT`/`SURVIVORS_OUT` as given. | both files as tracked                                                                                        |
| Template lint              | read of the template                                                                                                        | `lint:` runs `ruff check .` and `ruff format --check .` with no guard                                                                      | the template, which renders to all 8 projects                                                                |
| CI ruff                    | `scripts/crate_templates/python/py.yml`                                                                                     | `pip install ... ruff==0.16.4`, then `make test`                                                                                           | all 8 `*-py.yml`                                                                                             |

## Design

### 1. `make mutants` mutates a scratch copy

`init`, the optional shard step, `exec` and the two `cr-report` calls run in a scratch copy of the project directory. The source tree is never mutated.

- At the start of the recipe:
  - `work="$$(mktemp -d "$${TMPDIR:-/tmp}/mutants-@CRATE@.XXXXXX")" || exit 1`
  - `trap 'rm -rf -- "$$work"' EXIT`
  - `cp -R . "$$work/@CRATE@"`
  - `ln -s "$$(cd .. && pwd)/scripts" "$$work/scripts"`, so `../scripts/...` keeps resolving inside the copy
  - `cd "$$work/@CRATE@"`
- After `cr-report`, the recipe copies `cosmic-ray-session.sqlite` and `mutants-report.txt` back to the project directory. CI's artifact upload and `make mutants-report` read them there.
- It then returns to the project directory and runs `cosmic_ray_cell_status.py` exactly as today: the same relative session path and the same `STATUS_OUT`/`SURVIVORS_OUT` arguments. The existing argument-forwarding tests keep passing unchanged.
- Any failure inside the copy leaves the source untouched. `|| exit 1` stays on every step, and a failure before the copy-back leaves no new session file in the project directory.
- On SIGKILL the trap does not run, so the copy stays in `TMPDIR`. The source is still clean, and the stray copy is the accepted cost.
- `mutants-baseline` stays in place: `cosmic-ray baseline` runs the unmutated tests and edits nothing.

### 2. Sub-project `lint` guards ruff

- The template gains `RUFF := $(shell ruff --version >/dev/null 2>&1 && command -v ruff)`, the same line as the root `Makefile`.
- `lint:` runs both ruff commands under `ifdef RUFF`. Otherwise it prints `ruff not found, skipping (install: pip install ruff==0.16.4)` and exits 0, the same text as root.
- `test: lint` keeps its order, so a machine without runnable ruff still runs pytest and the CLI contract.
- CI installs ruff in every `*-py.yml` (Measurements), so lint stays enforced there.

### Tests

All tests go in `tests/scripts/makefile.bats`, using its `_py_stub_setup` harness (a copied `fib/Makefile` with stub `cosmic-ray`, `python3` and `cr-report`). The harness is extended with an opt-in stub behaviour and needs no new file.

- **Source untouched on failure.** A stub `exec` appends `MUTATED` to `fib.py` in its working directory and exits 1. After `make mutants` exits non-zero, `fib.py` in the project directory is byte-identical to its pre-run copy, and no `cosmic-ray-session.sqlite` was copied back.
- **Outputs copied back.** A stub `exec` writes `cosmic-ray-session.sqlite` (content `S`), and a stub `cr-report` writes its report. After a successful run, both files are in the project directory with the stub's content.
- **The copy is cleaned up.** With `TMPDIR` set to an empty `${BATS_TEST_TMPDIR}/t`, that directory is empty after a successful run and after a failed one.
- **Mutation control.** In a scratch copy of the template rendered in place, the "source untouched" case fails.
- **Lint, both directions**, against a rendered project Makefile with no `RUFF=` override, under `env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS`:
  - A `ruff` stub that exits 127, first on `PATH`, gives `ruff not found, skipping` and rc 0 from real `make lint`.
  - A `ruff` stub whose `--version` exits 0 makes `make -n lint` show `ruff check`.

### Docs

- `CLAUDE.md` is 29,995 bytes against a 30,000-byte ceiling, so it gets no edit.
- The mutation detail goes to `ai-config/docs/knowledge/math-testing-policy.md`, which the ai-config session owns, so I'll send it a message.
- Backlog: remove both rows.

## Requirements

- **R1.** The rendered Python `make mutants` runs `cosmic-ray init`, the shard step, `cosmic-ray exec` and `cr-report` inside a `mktemp -d` copy of the project directory, removed by an `EXIT` trap, and copies `cosmic-ray-session.sqlite` and `mutants-report.txt` back before running `cosmic_ray_cell_status.py` in the project directory.
- **R2.** A `makefile.bats` case with a stub `exec` that edits the module and exits 1 asserts that the project's module is byte-identical afterwards and that the hook rc is non-zero.
- **R3.** A `makefile.bats` case asserts that a successful run leaves the stub's session file and report in the project directory and leaves `TMPDIR` empty.
- **R4.** The Python template sets `RUFF` only when `ruff --version` succeeds, and `lint` prints `ruff not found, skipping` and exits 0 when it is unset. Two `makefile.bats` cases assert both directions with no `RUFF=` override.
- **R5.** The change goes through `scripts/crate_templates/python/Makefile` and `render_crate_files.py --write`; `tests/test_crate_uniformity.py` passes.
- **V1.** In a scratch copy of the repo, `cd fib && timeout -s TERM 25 make mutants` and `timeout -s KILL 25 make mutants` leave `fib/fib.py` unchanged (`git diff --stat` empty).
- **V2.** This PR's CI is green on every `*-py.yml`.
- **V3.** The next `mutation-testing-python.yml` run uploads non-empty `cosmic-ray-session.sqlite` artifacts.
- **N1.** No change to `mutants-baseline`, `cosmic-ray.toml`, `scripts/mutation-python-cell.sh` or any workflow.
- **N2.** No change to the Rust template or any Rust crate.
- **N3.** No change to `CLAUDE.md`.
