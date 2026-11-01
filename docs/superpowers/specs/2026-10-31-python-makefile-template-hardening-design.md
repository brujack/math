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

`init`, the optional shard step, `exec` and the two `cr-report` calls run in a scratch directory that holds only what cosmic-ray reads. The source tree is never mutated.

- The project directory first drops the previous run's outputs: `rm -f cosmic-ray-session.sqlite mutants-report.txt || exit 1`. A failed run then cannot leave stale results that `make mutants-report` or CI would present as current.
- The scratch directory is set up like this:
  - `work="$$(mktemp -d "$${TMPDIR:-/tmp}/mutants-@CRATE@.XXXXXX")" || exit 1`
  - `mkdir "$$work/@CRATE@"`
  - `cp -- @MODULE@.py test_@MODULE@.py cosmic-ray.toml "$$work/@CRATE@/"`
  - `ln -s "$$(cd .. && pwd)/scripts" "$$work/scripts"`, so `../scripts/...` still resolves
  - `cd "$$work/@CRATE@"`
- Only those three files are copied, never `.`, because every Python project directory also holds its Rust crate. Measured 2026-10-31 on `claude` with `du -sh`: `fib` is 668M and `pi` 1.8G, almost all of it `<p>-rs/target/`, and `/tmp` is tmpfs with `TMPDIR` unset. The three files total about 116K for fib.
  - Each `test_*.py` imports only its sibling module and resolves files through `Path(__file__).parent`, as two lenses grepped.
  - `typings/` is read by pyright only.
- An `EXIT` trap does two things:
  - It copies `cosmic-ray-session.sqlite`, and `mutants-report.txt` if present, from the scratch directory back to the project directory.
  - It then runs `rm -rf -- "$$work"`.
- So a normal exit, an error and a TERM or INT all leave the session where CI's `if: always()` upload and `make mutants-report` read it today. A partial session after an interrupt is kept, as it is today.
- A KILL skips the trap. The source is still untouched, and only about 116K is left in `TMPDIR`.
- `cosmic_ray_cell_status.py` runs after the copy-back, in the project directory, with the same relative session path and the same `STATUS_OUT`/`SURVIVORS_OUT` arguments as today. It does **not** use `exec`: `exec` replaces the shell and skips the `EXIT` trap. The status script's exit code becomes the recipe's.
- `mutants-baseline` stays in place: `cosmic-ray baseline` runs the unmutated tests and edits nothing.
- `module_path` in the session is the relative `@MODULE@.py`; `select distinct module_path from mutation_specs` returned `('sq.py',)`. `cr-report --show-diff` reads the diff stored in the db, so the copied-back session reads the same as today.

### 2. Sub-project `lint` guards ruff

- The template gains `RUFF := $(shell ruff --version >/dev/null 2>&1 && command -v ruff)`, the same line as the root `Makefile`.
- `lint:` runs both ruff commands under `ifdef RUFF`. Otherwise it prints `ruff not found, skipping (install: pip install ruff==0.16.4)` and exits 0, the same text as root.
- `test: lint` keeps its order, so a machine without runnable ruff still runs pytest and the CLI contract.
- CI installs ruff in every `*-py.yml` (Measurements), so lint stays enforced there.

### Tests

All tests go in `tests/scripts/makefile.bats` and use the `_py_stub_setup` harness. It is extended with an opt-in stub behaviour; no new file is needed. The stub `cosmic-ray exec` appends its `$$PWD` to the calls file, so every test can check where the work happened.

- **Source untouched on failure.**
  - Set-up: the stub `exec` appends `MUTATED` to `fib.py` in its working directory and exits 1. The harness puts a `fib.py`, `test_fib.py` and `cosmic-ray.toml` in the project directory.
  - Assertions:
    - `make mutants` exits non-zero;
    - the stub's recorded `pwd` is under `${BATS_TEST_TMPDIR}/t`, the `TMPDIR` the test sets;
    - the project's `fib.py` is byte-identical to its pre-run copy.
- **Outputs copied back.** The stub `exec` writes `cosmic-ray-session.sqlite` with the content `S`, and the stub `cr-report` writes its report. After a successful run:
  - both files are in the project directory with the stub's content;
  - `${BATS_TEST_TMPDIR}/t` is empty;
  - the recorded `pwd` was under it.
- **Partial session kept on failure.** The stub `exec` writes the session and exits 1. The session is in the project directory afterwards, and `${BATS_TEST_TMPDIR}/t` is empty.
- **Stale outputs removed.** A pre-existing `mutants-report.txt` with the content `OLD`, plus a failing `init`, leaves no `mutants-report.txt` in the project directory.
- **Only the three files are copied.** A decoy `fib-rs/target/big` in the project directory is absent from the scratch directory. The stub `exec` records `ls -A` of its working directory, which is exactly `cosmic-ray.toml fib.py test_fib.py`.
- **Mutation control.** In a scratch copy of the template where `init`/`exec` run in place, the "source untouched" case fails.
- **Lint, both directions.** These run against a rendered project Makefile with no `RUFF=` override, under `env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS`:
  - a `ruff` stub that exits 127, first on `PATH`, gives `ruff not found, skipping` and rc 0 from the real `make lint`;
  - a `ruff` stub whose `--version` exits 0 makes `make -n lint` show `ruff check`.
- The existing python mutants tests must keep passing, including "forwards CELL_LABEL, STATUS_OUT and SURVIVORS_OUT intact".

### Docs

- `CLAUDE.md` is 29,995 bytes against a 30,000-byte ceiling, so it gets no edit.
- The mutation detail goes to `ai-config/docs/knowledge/math-testing-policy.md`, which the ai-config session owns, so I'll send it a message.
- Backlog: remove both rows.

## Requirements

- **R1.** The rendered Python `make mutants` removes the project's `cosmic-ray-session.sqlite` and `mutants-report.txt`, copies only `@MODULE@.py`, `test_@MODULE@.py` and `cosmic-ray.toml` (plus a `scripts` symlink) into a `mktemp -d` under `TMPDIR`, runs `init`, the shard step, `exec` and `cr-report` there, and has an `EXIT` trap that copies the session (and report if present) back and removes the scratch directory; it runs `cosmic_ray_cell_status.py` in the project directory without `exec`.
- **R2.** `makefile.bats` cases with a recording stub `exec` assert: on a failing `exec` that edits the module, rc non-zero, the stub ran under the test's `TMPDIR`, and the project's module is byte-identical; on a failing `exec` that writes a session, the session is in the project directory and `TMPDIR` is empty.
- **R3.** `makefile.bats` cases assert that a successful run leaves the stub's session and report in the project directory with `TMPDIR` empty, that a stale report is removed when `init` fails, and that the scratch directory holds exactly `cosmic-ray.toml`, `@MODULE@.py` and `test_@MODULE@.py` while a decoy `<crate>-rs/target` file is not copied.
- **R4.** The Python template sets `RUFF` only when `ruff --version` succeeds, and `lint` prints `ruff not found, skipping` and exits 0 when it is unset. Two `makefile.bats` cases assert both directions with no `RUFF=` override.
- **R5.** The change goes through `scripts/crate_templates/python/Makefile` and `render_crate_files.py --write`; `tests/test_crate_uniformity.py` passes.
- **V1.** In a scratch copy of the repo, `cd fib && timeout -s TERM 25 make mutants` and `timeout -s KILL 25 make mutants` leave `fib/fib.py` unchanged (`git diff --stat` empty).
- **V2.** This PR's CI is green on every `*-py.yml`.
- **V3.** The next `mutation-testing-python.yml` run uploads non-empty `cosmic-ray-session.sqlite` artifacts.
- **N1.** No change to `mutants-baseline`, `cosmic-ray.toml`, `scripts/mutation-python-cell.sh` or any workflow.
- **N2.** No change to the Rust template or any Rust crate.
- **N3.** No change to `CLAUDE.md`.

## Multi-Lens Review

Reviewed at commit: `7e69755` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: `cp -R .` copies the sibling Rust crate. `<p>-rs/target` is 0.4–1.7 GB per project (pi 1.7G, e 1.5G, factorial 1.1G, fib 667M), and `/tmp` is tmpfs with `TMPDIR` unset, so every local run copies up to 1.8 GB into RAM and a SIGKILL strands it. CI cannot see this, because its checkout has no `target/`. The tests need only `@MODULE@.py`, `test_@MODULE@.py` and `cosmic-ray.toml`, which the lens confirmed by grepping all 8 tests. `module_path` is relative (`('sq.py',)`), and the EXIT trap does fire on TERM (probed).
Assumption: none left uncertain once the copy is scoped. Confirm with `du -sh "$work"` during a real pi run: it should be kilobytes.
Disposition: Addressed — operator chose "revise; trap copies partial back": allow-list copy, stale outputs removed first, no `exec`, recording stubs, and the trap copies the partial session back.

### Ergonomics

Finding: the same `target/` copy, measured on all 8 projects at about 7 GB total; pi's `target/` alone is 8,359 inodes, and `.hypothesis`, `.pytest_cache` and old outputs would be copied too. Three secondary defects:
- `exec python3` skips the EXIT trap (probed), so every success leaks its copy.
- The partial session that CI's `if: always()` upload and a later `mutants-report` used is lost on interrupt.
- A failed run leaves the previous run's results looking current.

R2 and "TMPDIR empty" could pass vacuously.
Assumption: cosmic-ray resolves `module-path` against cwd; settled by the relative `module_path` query.
Disposition: Addressed — as Goal-Fit.

### Risk

Finding: the same `target/` copy. "TMPDIR empty" passes on today's recipe, which never writes there, so it needs a positive `pwd` check. Also verified:
- `exec` skips the trap;
- TERM fires it;
- the shard script works only on the db;
- `cr-report --show-diff` reads diffs stored in the db;
- no project directory contains a symlink;
- the lint guard is fine in CI.
Assumption: `init` records a relative `module_path`; confirmed.
Disposition: Addressed — as Goal-Fit.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
