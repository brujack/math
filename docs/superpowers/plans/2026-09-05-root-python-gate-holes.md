# Root-scope Python Gate Holes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Declare root-scope Python's two hard third-party dependencies in a tracked manifest with an installer, and put the 8 tracked root-scope `.py` files under a type-check gate.

**Architecture:** A root `requirements-dev.txt` declares what root-scope Python imports; a `make install-deps` target consumes it. A root `pyrightconfig.json` replaces `scripts/pyrightconfig.json` and widens the type-check denominator from 2 files to 8. Two new Python gates and four new bats cases keep both honest.

**Tech Stack:** GNU Make, pyright 1.1.411, bats-core, Python 3 `unittest` + `ast`.

**Spec:** [2026-09-05-root-python-gate-holes-design.md](../specs/2026-09-05-root-python-gate-holes-design.md) at `6e0ee85`, approved after three Multi-Lens Review rounds.

## Global Constraints

- Pins, exact: `defusedxml==0.7.1`, `pyyaml==6.0.3`, `pyright==1.1.411`, `ruff==0.16.4`.
- `scripts.yml`'s install line MUST keep a literal `ruff==` on it — `tests/scripts/makefile.bats:133` greps `^[[:space:]]*run: pip install .*ruff==`.
- Root `pyrightconfig.json` `exclude` is `["**/node_modules", "**/__pycache__"]` — pyright's default list **minus** `**/.*`. That omission is what makes `.claude/scripts/` reachable; it needs a comment saying so.
- `install-deps` uses `python3 -m pip`, never bare `pip`, and refuses when the `EXTERNALLY-MANAGED` marker is present.
- Baseline, measured at `6e0ee85`: `make test` rc=0, 145 bats assertions, 82 Python tests, 21s.
- Baseline: root-scope tracked `.py` count is 8; `pyright` under the new config reports `filesAnalyzed 8, errorCount 0`.
- Every task ends with `make test` green. It is 21s, well under the 120s Bash auto-background threshold.

---

## Gate falsifiability

Every acceptance gate was run against `6e0ee85` before this plan was committed. Base-tree
exit codes:

- **Exit 1 — real progress gates:** both `Makefile` greps (T1); both `pre-push` greps (T2);
  `test -f pyrightconfig.json`, `test ! -f scripts/pyrightconfig.json`,
  `unittest tests.test_root_pyright_scope`, `pyright --outputjson` (T3);
  `unittest tests.test_root_python_deps` (T4); both `scripts.yml` greps (T5); all four
  documentation gates (T6).
- **Exit 0 — regression guards, labelled as such in their tasks:** `make test` (every task),
  the `ruff==` grep and `yaml.safe_load` parse (T5).
- **Exit 0 — falsifiable by TDD ordering, not by the base tree:** `bats
  tests/scripts/makefile.bats` (T1) and `bats tests/scripts/pre_push.bats` (T2). Both suites
  pass today because their new cases do not exist. Each task writes its cases first and must
  observe them fail before implementing; that observation is the falsifiability evidence, and
  the task report must state it.

Two gates were rejected during authoring rather than shipped:

- `make -n install-deps` — an absent target exits **2**, a usage error indistinguishable from
  a real failure. Replaced with `grep -qE "^install-deps:" Makefile`.
- `grep -q "Status: DONE" <this plan>` — exits **0** on the unmodified tree, because this
  plan's own prose contains the literal string. Replaced with a `head -5` anchored form.

---

## Verification Planning (session level)

**The command that proves the whole change works:**

```bash
make test && pyright && make install-deps
```

**Expected:** `make test` rc=0 with the Python count above 82 and bats above 145; `pyright` reports `8 files, 0 errors`; `install-deps` installs on the Mac Studio and refuses with the venv remedy over `ssh workstation`.

**Edge cases that must be exercised** — these are the spec's five mutations, each owned by the task that owns the gate it tests. A gate that has never gone red is not a gate:

1. Seed a return-type error in `.claude/scripts/triage_log.py` → root `pyright` reports it. (T3)
2. Add an unguarded `import requests` to a root test file → `test_root_python_deps` goes red naming `requests`. (T4)
3. Set `typeCheckingMode: off` → `test_root_pyright_scope` assertion 1 goes red. (T3)
4. Restore `**/.*` to `exclude` → assertion 2 goes red, **run both on a clean tree and with an untracked `.py` present**. (T3)
5. Widen `scripts/pre-push:52` to `.` → the new negative bats case goes red. (T2)

All five are reverted before commit; `git status --porcelain` must be empty afterwards.

---

## Task 1: Manifest and installer

```yaml-task
id: 1
description: Add requirements-dev.txt and a make install-deps target guarded on the PEP 668 EXTERNALLY-MANAGED marker
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: 'grep -qE "^install-deps:" Makefile'
    exit_code: 0
  - cmd: 'grep -q "python3 -m pip install -r requirements-dev.txt" Makefile'
    exit_code: 0
  - cmd: 'bats tests/scripts/makefile.bats'
    exit_code: 0
  - cmd: 'make test'
    exit_code: 0
max_retries: 3
files_touched:
  - requirements-dev.txt
  - Makefile
  - tests/scripts/makefile.bats
depends_on: []
```

**Base-tree state (proves each gate can fail):** `grep -qE "^install-deps:" Makefile` → exit 1. `test -f requirements-dev.txt` → exit 1. Do **not** gate on `make -n install-deps`; an absent target exits **2**, a usage error indistinguishable from a real failure.

**Files:**

`requirements-dev.txt` (new), exactly:

```
defusedxml==0.7.1
pyyaml==6.0.3
```

`Makefile` — add `install-deps` to the `.PHONY` line (line 1) and the target:

```make
install-deps:
	@python3 -c 'import os, sysconfig; raise SystemExit(1 if os.path.exists(os.path.join(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED")) else 0)' \
	  || { printf 'python3 is externally managed (PEP 668). Create a venv first:\n  python3 -m venv .venv && . .venv/bin/activate\nthen re-run: make install-deps\n' >&2; exit 1; }
	python3 -m pip install -r requirements-dev.txt
```

The marker check is the exact discriminator pip itself uses. Measured: the Linux 7950X is Python 3.12.3 with `EXTERNALLY-MANAGED: True` and fails `python3 -m pip install`; the Mac Studio's pyenv interpreter has no marker and installs normally.

**Tests** — write these in `tests/scripts/makefile.bats` BEFORE the Makefile edit, confirm they fail, then implement:

1. `make -n install-deps` output contains `python3 -m pip install -r requirements-dev.txt`.
2. `make -n install-deps` output does NOT contain a bare `pip install` unprefixed by `python3 -m` — use the existing `assert_no_match`-style negative form in that file, not a bare `! grep`.
3. `requirements-dev.txt` parses as one pinned requirement per line, both entries carrying `==`.

**Interfaces:**
- Produces: `requirements-dev.txt` at repo root (Task 4 reads it); `install-deps` target (Task 6 documents it).

---

## Task 2: Pre-push trigger regex

```yaml-task
id: 2
description: Widen the pre-push root-scope trigger regex by four alternatives and add four bats cases including the missing over-match negative
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: 'bats tests/scripts/pre_push.bats'
    exit_code: 0
  - cmd: 'grep -qE "pyrightconfig" scripts/pre-push'
    exit_code: 0
  - cmd: 'grep -qE "requirements-dev" scripts/pre-push'
    exit_code: 0
  - cmd: 'make test'
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/pre-push
  - tests/scripts/pre_push.bats
depends_on: []
```

**Base-tree state:** both `grep` gates exit 1; `bats tests/scripts/pre_push.bats` exits 0 (the new cases do not exist yet, which is why they must be written first and seen to fail).

**Files:**

`scripts/pre-push` line 52 — the current regex is:

```
'^scripts/|^tests/|^Makefile$|^\.github/workflows/mutation-testing.*\.yml$|^\.github/workflows/release-.*\.yml$|^\.github/actions/'
```

Add four alternatives: `^pyrightconfig\.json$`, `^requirements-dev\.txt$`, `^\.claude/scripts/`, `^\.github/workflows/scripts\.yml$`.

The fourth is not about imports: `tests/scripts/makefile.bats:133` greps `.github/workflows/scripts.yml`, so editing that workflow can turn the root suite red while the hook stays silent.

**Tests** — four new cases in `tests/scripts/pre_push.bats`, following the file's existing `MOCK_GIT_DIFF_NAMES` pattern:

- Three positive: `pyrightconfig.json`, `requirements-dev.txt`, `.claude/scripts/triage_log.py` — each asserts the root `make ... test` target is reached.
- One negative: `MOCK_GIT_DIFF_NAMES="pi/pi.py"`, asserting the **root** target is NOT reached. Use the file's `assert_no_match` helper; a bare `! grep -q` only fails as the last command in a bats body.

This negative case is the one the spec originally claimed already existed and does not. All four current `assert_no_match` calls are at `:35`, `:42` (empty diff), `:115`, `:124` (specific sub-project targets) — none fails if line 52 is widened to match everything.

**Mutation 5 (required):** widen line 52 to `.`, run `bats tests/scripts/pre_push.bats`, confirm the new negative case fails, revert. Report the observed failure line.

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks read.

---

## Task 3: Root pyright config and scope gate

```yaml-task
id: 3
description: Add a root pyrightconfig.json covering all 8 tracked root-scope .py files, delete scripts/pyrightconfig.json, and gate the config's mode and coverage
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: 'test -f pyrightconfig.json'
    exit_code: 0
  - cmd: 'test ! -f scripts/pyrightconfig.json'
    exit_code: 0
  - cmd: 'python3 -m unittest tests.test_root_pyright_scope -v'
    exit_code: 0
  - cmd: 'pyright --outputjson'
    exit_code: 0
  - cmd: 'make test'
    exit_code: 0
max_retries: 3
files_touched:
  - pyrightconfig.json
  - scripts/pyrightconfig.json
  - tests/test_root_pyright_scope.py
depends_on: []
```

**Base-tree state:** `test -f pyrightconfig.json` → 1. `test ! -f scripts/pyrightconfig.json` → 1. `python3 -m unittest tests.test_root_pyright_scope` → 1 (missing module; verified this is exit 1, not 2/4/127).

**Files:**

`pyrightconfig.json` (new):

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

`exclude` is pyright's default minus `**/.*`. **Exclude beats include** — naming `.claude/scripts` in `include` is not enough on its own; measured 7 files with the default exclude, 8 without `**/.*`. JSON takes no comments, so record this in the CLAUDE.md entry (Task 6), not in the file.

Delete `scripts/pyrightconfig.json`. Verified safe: pyright resolves config from cwd and does not walk up, so all 8 sub-project gates are unaffected — measured `2 files 0 err` for every one of them with and without a root config present.

**Tests** — `tests/test_root_pyright_scope.py`, written first and seen to fail:

1. **Mode.** Parse `pyrightconfig.json`; assert `typeCheckingMode == "standard"` and `reportMissingImports` is true.
2. **Coverage.** Assert:

   ```
   filesAnalyzed == |git ls-files    'tests/*.py' 'scripts/*.py' '.claude/scripts/*.py'|
                  + |git ls-files -o 'tests/*.py' 'scripts/*.py' '.claude/scripts/*.py'|
   ```

   `-o` **without** `--exclude-standard`: pyright does not read `.gitignore`, so ignored files are analysed and must be counted. Verified `git ls-files -o` recurses into ignored directories and lists files individually.

   Vacuity floor: the tracked count must be non-zero.

Skip when `pyright` is absent, **except** when `CI` is set, where a missing `pyright` fails.

Do **not** implement this as `==` against the tracked count alone, nor as `>=`, nor by reimplementing pyright's include/exclude matching in Python. All three were tried in review and refuted; the spec's three-draft table records the mechanism for each.

**Mutations 1, 3, 4 (required):**

1. Append `def _seed(x: int) -> str:\n    return x` to `.claude/scripts/triage_log.py`; `pyright` must report `reportReturnType`. Revert.
3. Set `typeCheckingMode` to `off`; assertion 1 must go red. Revert.
4. Restore `**/.*` to `exclude`; assertion 2 must go red. **Run this twice — on a clean tree and with an untracked `.py` under an include root.** The dirty run is the one that matters: a previous draft passed it. Revert.

Report the observed failure for each. `git status --porcelain` must be empty afterwards.

**Interfaces:**
- Produces: `pyrightconfig.json` at repo root (Task 5 adds it to the CI `paths:` filter, Task 6 documents it).

---

## Task 4: Root dependency-declaration gate

```yaml-task
id: 4
description: Add tests/test_root_python_deps.py asserting every unguarded third-party import in root-scope Python is declared in requirements-dev.txt
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: 'python3 -m unittest tests.test_root_python_deps -v'
    exit_code: 0
  - cmd: 'make test'
    exit_code: 0
max_retries: 3
files_touched:
  - tests/test_root_python_deps.py
depends_on: [1]
```

**Base-tree state:** `python3 -m unittest tests.test_root_python_deps` → exit 1 (missing module).

**Files:**

`tests/test_root_python_deps.py`. Population: `git ls-files 'tests/*.py' 'scripts/*.py' '.claude/scripts/*.py'` — 8 files today. Git pathspec `*` crosses `/`, so this already covers nested paths; do not "fix" it to `tests/**/*.py`, which would narrow it.

**Definitions, both load-bearing:**

- **Guarded** — the import sits inside a `try` whose handler catches `ImportError` or `ModuleNotFoundError`. Guarded imports are excluded.
- **Third-party** — the top-level module name is neither in `sys.stdlib_module_names` **nor a first-party root**, where first-party means a top-level directory or module of this repo.

The first-party half is not optional. `tests/test_test_metrics.py:22` and `tests/test_time_tests.py:10` both do `from scripts.… import …`; `'scripts' in sys.stdlib_module_names` is False, so a stdlib-only classifier demands `scripts` in the manifest.

**Vacuity guards** — an AST bug returning an empty set must fail, not pass:

1. The derived file count must be non-zero.
2. `yaml` and `defusedxml` must both be found.

Note these guard **under**-detection only; nothing catches an over-broad classifier, which is why the first-party clause is specified rather than left to the implementer.

Uses `ast` and stdlib only, so it cannot depend on what it checks.

**Mutation 2 (required):** add `import requests` unguarded to a root test file; this suite must go red and name `requests`. Revert.

**Interfaces:**
- Consumes: `requirements-dev.txt` from Task 1.

---

## Task 5: CI workflow

```yaml-task
id: 5
description: Point scripts.yml at the manifest, pin pyright, drop working-directory from the pyright step, and widen the paths filter
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'grep -qE "^[[:space:]]*run: pip install .*ruff==" .github/workflows/scripts.yml'
    exit_code: 0
  - cmd: 'grep -q "requirements-dev.txt" .github/workflows/scripts.yml'
    exit_code: 0
  - cmd: 'grep -q "pyright==1.1.411" .github/workflows/scripts.yml'
    exit_code: 0
  - cmd: 'python3 -c "import yaml,sys; yaml.safe_load(open(\".github/workflows/scripts.yml\"))"'
    exit_code: 0
  - cmd: 'bats tests/scripts/makefile.bats'
    exit_code: 0
  - cmd: 'make test'
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/scripts.yml
depends_on: [1, 3]
```

`tdd: not-applicable` — a CI workflow file has no unit-testable behaviour of its own; its assertions live in `tests/scripts/makefile.bats` (unchanged here) and `tests/test_release_workflows.py`. The acceptance gates above are the check.

**Base-tree state:** the `requirements-dev.txt` and `pyright==1.1.411` greps exit 1. Two gates here exit 0 **now and after** and are regression guards, not progress gates: the `ruff==` grep (pins the `makefile.bats:133` contract) and the `yaml.safe_load` parse (catches a YAML syntax break introduced by this edit).

**Files:**

`.github/workflows/scripts.yml`:

- Install step becomes `run: pip install -r requirements-dev.txt ruff==0.16.4 pyright==1.1.411 pip-audit`. Keep `ruff==` literal on this line.
- Remove `working-directory: scripts` from the `Run pyright` step.
- `paths:` gains `pyrightconfig.json`, `requirements-dev.txt`, `.claude/scripts/**`.

The pyright pin is scoped to this workflow only. The other 8 `*-py.yml` sites stay unpinned — that is a backlog row, deliberately, since each needs its own green check.

**Interfaces:**
- Consumes: `requirements-dev.txt` (T1), `pyrightconfig.json` (T3).

---

## Task 6: Documentation

```yaml-task
id: 6
description: Update CLAUDE.md and the plan index for the manifest, installer, root type-check config and its corrected CI-only claim (docs-only, no behavior change)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'grep -q "requirements-dev.txt" CLAUDE.md'
    exit_code: 0
  - cmd: 'grep -q "install-deps" CLAUDE.md'
    exit_code: 0
  - cmd: 'grep -q "2026-09-05-root-python-gate-holes" docs/superpowers/README.md'
    exit_code: 0
  - cmd: 'head -5 docs/superpowers/plans/2026-09-05-root-python-gate-holes.md | grep -q "Status: DONE"'
    exit_code: 0
  - cmd: 'make test'
    exit_code: 0
max_retries: 3
files_touched:
  - CLAUDE.md
  - docs/superpowers/README.md
  - docs/superpowers/plans/2026-09-05-root-python-gate-holes.md
depends_on: [1, 2, 3, 4, 5]
```

`tdd: not-applicable` — prose only, no executable logic.

**Files:**

`CLAUDE.md`:

- Setup block: add `make install-deps` beside `make install-hooks`.
- Type-checking section: replace the `scripts` row with the root config; record the 8-file denominator, that **exclude beats include** (7 files with the default `**/.*`, 8 without), and the `pyright==1.1.411` pin scoped to `scripts.yml`.
- **Correct two stale claims in that same section.** It says pyright "runs in CI only — not in `make lint` (spawn overhead on macOS makes it slow locally)". After this change `tests/test_root_pyright_scope.py` runs under `make test-python`, which the pre-push hook invokes, so the CI-only half is false. The severity half is also stale — measured `real 0.90`, `0.89`, `0.91`.
- Note that `cd <sub-project> && pyright` no longer behaves uniformly across nine directories: `scripts/` has no config after this change and falls back to pyright defaults rather than erroring, so a green result there is indistinguishable from a configured pass.
- New note naming `requirements-dev.txt`, its definition (what root-scope Python imports, not tools), and that a root `install_deps.sh` deliberately does not exist.
- Repo-level Python tests: update the test count from 82.

`docs/superpowers/README.md`:

- Add this plan to the All Plans table, status `Done`.
- Delete the two backlog rows this closes: the `pyyaml` row and the root-`tests/*.py`-type-checked-by-nothing row.
- Add a row for pinning `pyright` at the other 8 `*-py.yml` sites.
- Add a row for the first-party-name collision, stating its **trigger, not its current state**: it becomes live when a new top-level directory is added whose name matches a distribution this repo imports. The safe-today enumeration is what justifies deferring and is the wrong thing to write in the row.

Add a `> **Status: DONE**` banner within the first 5 lines of this plan file. The acceptance
gate is `head -5 | grep`, deliberately: a bare `grep` over the whole file matches this very
sentence and passes on the unmodified tree — measured, exit 0. The banner's *position* is
what is being asserted, so the gate has to be anchored to it.

**Interfaces:**
- Consumes: every prior task's deliverable.
