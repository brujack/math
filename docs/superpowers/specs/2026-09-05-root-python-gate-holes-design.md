# Root-scope Python gate holes: dependency declaration and type checking

**Date:** 2026-09-05
**Status:** Spec

## Problem

Two backlog rows in `docs/superpowers/README.md`, both about root-scope Python
(`tests/`, `scripts/`, `.claude/scripts/`) — the part of this repo that sits outside every
sub-project's own gate chain.

### Row 1 — `pyyaml` is a hard import for the root suite with no local installer

`tests/test_release_workflows.py:39` carries an unguarded `import yaml`, and
`scripts/pre-push:52` triggers the root `make test` (which runs `test-python`) whenever a
push touches `^scripts/`, `^tests/`, `^Makefile$`, or the release/mutation workflows.
`pyyaml==6.0.3` is declared in exactly one place: `.github/workflows/scripts.yml`. No
repo-root installer, manifest, or doc names it, so a fresh checkout fails the pre-push hook
with an `ImportError`.

Measured on the Mac Studio, 2026-09-05, by blocking each module with a `PYTHONPATH` shim
that raises `ImportError` on import. Exit codes captured immediately after the command, not
through a pipe:

```
baseline                       rc=0   Ran 82 tests   OK
yaml blocked                   rc=1   Ran 52 tests   FAILED (errors=1)
defusedxml blocked             rc=1   Ran 80 tests   FAILED (errors=1)
make test-python (no pyyaml)   rc=2
```

Note the 30 tests that vanish from the run when `yaml` is blocked, and the 2 that vanish
when `defusedxml` is. `unittest discover` reports an unimportable module as a single error
and continues, so the headline is one error while a whole file's worth of coverage is
absent. The suite still exits non-zero, so the push is blocked rather than silently passed
— this is an ergonomics gap, not a safety hole.

The population is the root-scope tracked Python set, derived by AST over
`git ls-files 'tests/*.py' 'scripts/*.py' '.claude/scripts/*.py'` (8 files). Exactly two
files carry an unguarded third-party import:

```
scripts/test_metrics.py:          hard=['defusedxml']  guarded=[]
tests/test_release_workflows.py:  hard=['yaml']        guarded=[]
```

A related structural gap: `tests/scripts/install_deps.bats` checks installer/Makefile parity
by iterating `git ls-files '*/Makefile' '*/*/Makefile'`. Neither pathspec matches the root
`Makefile`, so the root target's dependencies are outside that parity check — the same
denominator hole one level up.

### Row 2 — root `tests/*.py` is type-checked by nothing

`.github/workflows/scripts.yml` runs `pyright` with `working-directory: scripts`, against
`scripts/pyrightconfig.json`, whose `include` is `["time_tests.py", "test_metrics.py"]`. So
2 of the 8 tracked root-scope Python files are type-checked and 6 are not, including all 5
under `tests/`.

**The row's evidence half does not reproduce and is retracted.** It stated that a new
`tests/` file "shipped two `reportArgumentType` errors that every gate passed." Measured
2026-09-05 with pyright 1.1.411 on the Mac Studio:

```
pyright tests/                                              5 files, 0 err, 0 warn
each tests/*.py individually                                1 file each, 0 err
root config {scripts,tests,.claude/scripts}, standard mode  7 files, 0 err, 0 warn
```

Positive control, because a clean result and a broken instrument produce the same output —
appending `def _seeded_control(x: int) -> str: return x` to `tests/test_triage_log.py`:

```
1 errors
    reportReturnType  Type "int" is not assignable to return type "str"
```

The instrument fires. The claimed errors are either stale or were specific to an environment
this session cannot reconstruct. **The gate hole is real; there is nothing behind it to
fix.** That makes this a clean ratchet rather than a repair, which is a better starting
position, and it is recorded here rather than quietly corrected because a stale measurement
carried in a backlog row is exactly the artifact a later reader would trust.

## Measurements that decided the design

All on the Mac Studio, pyright 1.1.411, PyYAML 6.0.3, defusedxml 0.7.1, 2026-09-05. Each is
a claim about this repo at commit `c95f521`, not about the fleet.

### pyright's `exclude` beats `include`, and that is what hides `.claude/scripts`

```
include [scripts,tests,.claude/scripts], default exclude       7 files, 0 err
same + exclude ["**/node_modules","**/__pycache__"]            8 files, 0 err
```

pyright's default `exclude` list contains `**/.*`. An explicit `include` entry naming a
dot-directory does not override it. The 7-vs-8 delta is `.claude/scripts/triage_log.py`.

### A root config does not leak into a sub-project run

Measured across all 8 sub-projects carrying a `pyrightconfig.json`, derived from
`git ls-files '*/pyrightconfig.json'` rather than enumerated, with and without a root config
present:

```
                   WITHOUT root config      WITH root config
amicable           2 files 0 err            2 files 0 err
collatz            2 files 0 err            2 files 0 err
e                  2 files 0 err            2 files 0 err
factorial          2 files 0 err            2 files 0 err
fib                2 files 0 err            2 files 0 err
perfect-numbers    2 files 0 err            2 files 0 err
pi                 2 files 0 err            2 files 0 err
sq                 2 files 0 err            2 files 0 err
```

pyright resolves `pyrightconfig.json` from the current working directory and does not walk
up the tree — unlike `ruff.toml`, which this repo relies on for ancestor discovery across
those same 8 sub-projects. Adding a root config is therefore inert for all 8 sub-project
pyright gates.

This was measured rather than assumed because a wrong answer would have silently changed all
8. It was also measured across all 8 rather than one: the first pass ran `pi` alone and the
sentence written from it claimed the property for all 8 — a claim wider than its evidence,
caught in this spec's own self-review.

### `pyright` is unpinned at 9 sites

All 8 `*-py.yml` workflows plus `scripts.yml` install a bare `pyright`. No incident has been
observed. The risk class is the one `shell.md` already pins `shellcheck` for: a pre-1.0 tool
whose default rule set moves between releases, so a gate can turn red on a commit that
changed nothing.

### An existing test constrains the workflow edit

`tests/scripts/makefile.bats`:

```bash
@test "the workflow running root lint installs ruff" {
    run grep -E '^[[:space:]]*run: pip install .*ruff==' \
        "${REPO_ROOT}/.github/workflows/scripts.yml"
    [ "${status}" -eq 0 ]
}
```

Any move of `scripts.yml` to a bare `pip install -r <file>` breaks this assertion. The
design keeps `ruff==` literal on that line so the test passes unchanged.

## Design

### 1. `requirements-dev.txt` at the repo root

```
defusedxml==0.7.1
pyyaml==6.0.3
```

**Definition — derived from purpose, not from who needs it today:** this file declares the
third-party modules that root-scope Python *imports*. It does not declare tools.

That boundary is a real category line, not a convenience. `pyyaml` and `defusedxml` are
imports: the code raises `ImportError` without them, and `make test-python` exits non-zero.
`ruff`, `pyright` and `pip-audit` are tools the gate invokes, and the root `Makefile`'s
`lint-python` already guards a missing `ruff` with `ifndef RUFF` and exits 0 by design.
Different failure semantics justify a different declaration site.

Rejected alternatives:

- **A root `install_deps.sh`**, matching the 19 sub-project installers. It would be
  invisible to `dependency-review`, whose manifest regex is
  `[-_a-zA-Z0-9]*requirements[-_a-zA-Z0-9]*\.(txt|in)`. The installer convention exists for
  sub-projects that each have a Makefile; the root already diverges from it, since
  `install_deps.bats`'s pathspecs cannot see the root Makefile.
- **Everything in the manifest**, including `ruff`/`pyright`/`pip-audit`, with `scripts.yml`
  reduced to a bare `-r`. This moves one of CLAUDE.md's 17 documented `ruff==0.16.4` pin
  sites behind an indirection and forces the `makefile.bats` assertion above to follow it.

`defusedxml` is pinned here at its installed version, 0.7.1. It is currently bare in
`scripts.yml`. A manifest that pins one entry and floats the other would be worse than
either consistent choice.

### 2. `scripts.yml`

Install step becomes:

```yaml
run: pip install -r requirements-dev.txt ruff==0.16.4 pyright==1.1.411 pip-audit
```

The pyright pin is scoped to this workflow only. This PR creates the root type-check
ratchet, so it owns that gate's instrument stability. Pinning the other 8 sites is the same
decision applied 8 more times, each needing its own green check at the pinned version — a
backlog row, not a rider here.

The pyright step drops `working-directory: scripts`.

The `paths:` filter gains `pyrightconfig.json`, `requirements-dev.txt`, and
`.claude/scripts/**`. Without these, a change to the manifest or the type-check config
triggers no CI at all — the same class of gap as the two rows this spec closes.

### 3. Root `pyrightconfig.json`

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

`scripts/pyrightconfig.json` is deleted. Two configs over overlapping sets is displacement:
`cd scripts && pyright` and a root `pyright` would answer differently about the same files,
and nothing would force them equal.

The `exclude` list is pyright's default minus `**/.*`. That omission is the whole reason
`.claude/scripts` is reachable, so it carries a comment saying so — a future reader
restoring the "missing" default would silently drop a file from the denominator without any
number moving, which is the failure `tdd.md`'s Coverage Denominators section describes.

Its one cost, stated rather than discovered later: pyright will descend into any
dot-directory beneath `scripts`, `tests`, or `.claude/scripts`. None exist today.

The denominator is every tracked root-scope `.py` file (8). Excluding
`.claude/scripts/triage_log.py` because its directory begins with a dot would *raise* the
reported figure by dropping a tracked file — the direction that needs evidence, not the
conservative one. It is real code with a paired suite (`tests/test_triage_log.py`), and
CLAUDE.md documents why it is vendored here rather than reached through the
`~/.claude/scripts/` symlink.

### 4. `scripts/pre-push`

The root-scope trigger regex at line 52 gains `^pyrightconfig\.json$` and
`^requirements-dev\.txt$`. A change to either alters what the root suite can import or what
gets type-checked, so it must run the root suite locally.

### 5. Two new gates, each with a positive control

**`tests/test_root_python_deps.py`** — AST-derives every unguarded third-party import
across `git ls-files 'tests/*.py' 'scripts/*.py' '.claude/scripts/*.py'` and asserts each
appears in `requirements-dev.txt`. It uses `ast` and stdlib only, so it cannot depend on the
thing it checks.

An import is "guarded" when it appears inside a `try` whose handler catches `ImportError` or
`ModuleNotFoundError`; guarded imports are excluded because the code has an explicit
fallback path.

Vacuity guards, because an AST bug returning an empty set would pass silently:

- the derived file count must be non-zero
- `yaml` and `defusedxml` must both be found

This is a derived denominator: a third unguarded import added later fails the suite rather
than the next fresh checkout.

**Two `tests/scripts/pre_push.bats` cases** for the widened trigger regex, following that
file's existing pattern of setting `MOCK_GIT_DIFF_NAMES` to one path and asserting the root
test target is reached — one for `pyrightconfig.json`, one for `requirements-dev.txt`. A
regex alternative with no test is an untested branch, and the file's existing negative cases
(`rust-only change does not drag in the python sibling suite`) already cover the other
direction.

**`tests/test_root_pyright_scope.py`** asserts `filesAnalyzed` from `pyright --outputjson`
equals the tracked root-scope `.py` count from `git ls-files`, both sides derived rather than
hardcoded. It skips when `pyright` is absent —
**except when the `CI` environment variable is set, where a missing `pyright` fails the
test.** CLAUDE.md already records that pyright runs in CI only and not in `make lint`; this
preserves that while removing CI's ability to skip the check silently.

## Verification

Runnable now, against `c95f521`, and recorded above rather than predicted:

```
pyright, root config, exclude override    files 8, err 0
cd pi && pyright                          2 files, 0 err
python3 -m unittest discover -s tests     Ran 82, OK
```

After implementation:

| command | expected |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_*.py'` | `Ran` count above the current 82, `OK` |
| `make lint` | exit 0 |
| `make test` | exit 0 |
| `bats --recursive tests/` | all pass, including the unchanged `ruff==` assertion |
| `pyright` from repo root | `8 files, 0 errors` |
| `cd pi && pyright` | `2 files, 0 errors` — unchanged |

Two mutations, because a gate that has never gone red is not yet a gate:

1. Seed a return-type error into `.claude/scripts/triage_log.py`; root `pyright` must report
   it. This proves the dot-directory reach is live, rather than inferred from reading the
   config.
2. Add an unguarded `import requests` to a root test file; `tests/test_root_python_deps.py`
   must go red, and must name `requests`.

Both mutations are reverted before commit, and `git status --porcelain` must be empty
afterwards.

## Documentation

- `CLAUDE.md` "Type checking (Python — pyright)" — replace the `scripts` row with the root
  config, its 8-file denominator, the `exclude`-beats-`include` finding, and the 1.1.411 pin
  scoped to `scripts.yml`.
- `CLAUDE.md` — a note naming `requirements-dev.txt`, its definition, and the fact that root
  `install_deps.sh` deliberately does not exist.
- `CLAUDE.md` "Repo-level Python tests" — updated test count.
- `docs/superpowers/README.md` — delete both backlog rows; add the row for pinning pyright
  at the other 8 sites.

## Scope

Out of scope, stated so the omissions read as decisions:

- **Pinning `pyright` at the other 8 `*-py.yml` sites.** Backlog row.
- **The `dependency-review` blind-spot row.** The manifest partly relieves it — math gains
  its first tracked Python manifest, which that gate's regex can see — but hand-typed
  `cargo install` and `pip install` lines in workflows stay invisible. Not solved.
- **The root `install_deps.bats` parity hole.** Noted in Problem above; closing it means
  teaching that test about a root Makefile with no sibling installer, which is its own
  change.
- **Guarding the imports.** Wrapping `import yaml` in a `try` would make the suite pass with
  30 tests silently absent. The current fail-closed behavior is correct; only the
  declaration is missing.
