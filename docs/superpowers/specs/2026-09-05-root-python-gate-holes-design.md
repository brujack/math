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

That file carries **two** `ruff==` assertions, not one: `:133` above, and `:128`
(`[[ "${output}" == *"pip install ruff=="* ]]`) on the Makefile's ruff-absent skip notice.
`:128` is unaffected by this change. Recorded because the round-1 enumeration meant to bound
this edit stopped at the first hit — find-first where the question needed
enumerate-until-exhausted.

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

**A root `make install-deps` target consumes it**, because a declaration is not a remedy.
Without it, a fresh checkout after this change still fails with
`ModuleNotFoundError: No module named 'yaml'` and nothing in the failure names the new file
— the same symptom Row 1 opens with, closed by a CLAUDE.md sentence rather than a command.
The repo already has this pattern: `Makefile:84` prints
`ruff not found, skipping (install: pip install ruff==0.16.4)`.

```make
install-deps:
	@python3 -c 'import os, sysconfig; raise SystemExit(1 if os.path.exists(os.path.join(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED")) else 0)' \
	  || { printf 'python3 is externally managed (PEP 668). Create a venv first:\n  python3 -m venv .venv && . .venv/bin/activate\nthen re-run: make install-deps\n' >&2; exit 1; }
	python3 -m pip install -r requirements-dev.txt
```

**The PEP 668 guard is not defensive boilerplate — the bare form fails on one of the two
development machines.** Measured over `ssh workstation` (Linux 7950X):

```
Python 3.12.3
EXTERNALLY-MANAGED: True
python3 -m pip install pyyaml==6.0.3  ->  error: externally-managed-environment
```

The Mac Studio's pyenv interpreter carries no marker and installs normally, so the marker is
the exact discriminator pip itself uses. Refusing with the venv command follows this repo's
remedy-in-the-message pattern (`Makefile:84`) and is preferable to
`--break-system-packages`, which does what its name says to a system interpreter.

Note the verification row for this target must **not** run only inside a venv: a venv is the
one environment where PEP 668 structurally cannot fire, so testing there certifies nothing
about the fresh-checkout path this target exists for.

**`python3 -m pip`, not bare `pip`, and this is not style.** Measured on the Mac Studio:
`pip --version` resolves to
`/Users/bruce/.pyenv/versions/ansible/lib/python3.14/site-packages/pip`, a pyenv environment
shared with unrelated work. A bare `pip install` can therefore succeed, print "Successfully
installed", and leave `make test-python` — which runs `python3` (`Makefile:39`) — still
raising `ModuleNotFoundError: No module named 'yaml'`. That is strictly worse than today's
honest failure, because the remedy now appears to work. `python3 -m pip` ties the install to
the interpreter that runs the suite and makes the question moot rather than answered.

This is the consumer the manifest otherwise lacks. `dependency-review`'s regex matching the
filename is real but fires only on future additions; `install-deps` changes what a human
runs today. Added to `.PHONY` and to CLAUDE.md's per-checkout Setup block beside
`make install-hooks`.

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

The root-scope trigger regex at line 52 gains `^pyrightconfig\.json$`,
`^requirements-dev\.txt$`, `^\.claude/scripts/`, and
`^\.github/workflows/scripts\.yml$`. The first two alter what the root suite
can import or what gets type-checked. The third closes an asymmetry this design would
otherwise introduce: `.claude/scripts/**` enters the CI `paths:` filter and
`.claude/scripts/triage_log.py` enters both new gates' denominators, while
`'.claude/scripts/triage_log.py'` does not match the existing
`^scripts/|^tests/|^Makefile$|...` — so the one file the design argues hardest to keep in
the denominator would be the one editable without the local suite running. Verified by
matching that path against the current regex: no match.

The fourth is not about imports at all: `tests/scripts/makefile.bats:133` greps
`.github/workflows/scripts.yml`, so editing that workflow — bumping the pyright pin, say —
can turn the root suite red while the pre-push hook stays silent, because the regex covers
the release and mutation workflows but not this one.

### 5. Two new gates, each with a positive control

**`tests/test_root_python_deps.py`** — AST-derives every unguarded third-party import
across `git ls-files 'tests/*.py' 'scripts/*.py' '.claude/scripts/*.py'` and asserts each
appears in `requirements-dev.txt`. It uses `ast` and stdlib only, so it cannot depend on the
thing it checks.

An import is **guarded** when it appears inside a `try` whose handler catches `ImportError`
or `ModuleNotFoundError`; guarded imports are excluded because the code has an explicit
fallback path.

An import is **third-party** when its top-level module name is neither in
`sys.stdlib_module_names` nor a first-party root — where first-party means a top-level
directory or module of this repo. **The first-party half is not optional**, and a naive
stdlib-only classifier gets it wrong:

```
tests/test_test_metrics.py:22   from scripts.test_metrics import fetch_historical
tests/test_time_tests.py:10     from scripts.time_tests import TimingResult, ...
'scripts' in sys.stdlib_module_names   ->  False
```

Both are unguarded, top-level, and not stdlib, so a `sys.stdlib_module_names`-only
implementation demands `scripts` in `requirements-dev.txt` — poisoning the manifest with a
package that does not exist. Note the direction: the two vacuity floors below guard
*under*-detection only, and both are satisfied by an over-broad classifier, so nothing else
in this design catches it.

Vacuity guards, because an AST bug returning an empty set would pass silently:

- the derived file count must be non-zero
- `yaml` and `defusedxml` must both be found

This is a derived denominator: a third unguarded import added later fails the suite rather
than the next fresh checkout.

**Four `tests/scripts/pre_push.bats` cases** for the widened trigger regex, following that
file's existing pattern of setting `MOCK_GIT_DIFF_NAMES` to one path. Three positive —
`pyrightconfig.json`, `requirements-dev.txt`, `.claude/scripts/triage_log.py` — each
asserting the root test target is reached.

**One negative, and it is the one this spec originally got wrong.** Round 1 claimed the
widened regex needed no over-match test because the file's existing negative cases covered
that direction. They do not. All four `assert_no_match` calls in that file:

```
35:  assert_no_match "^make"                     # empty diff
42:  assert_no_match "^make"                     # empty diff
115: assert_no_match "make -C .../pi test"
124: assert_no_match "make -C .../pi/pi-rs test"
```

The two `^make` cases run with an empty diff, which an over-broad regex passes too; the other
two name a specific sub-project target, never the root one. **No test in that file fails if
line 52 is widened to match everything** — and the failure would be silent, running the root
suite on every push, on a hook that gates every push in this repo. The fourth case sets
`MOCK_GIT_DIFF_NAMES="pi/pi.py"` and asserts the root target is *not* reached.

**`tests/test_root_pyright_scope.py`** — **redesigned in Multi-Lens Review round 1.** The
first version asserted `pyright --outputjson`'s `filesAnalyzed` equals a `git ls-files`
count. Three lenses converged on that being wrong, and measurement confirmed both defects:

```
                           filesAnalyzed   git ls-files
clean tree                       8              8
1 untracked .py                  9              8
+1 nested untracked              10             8
```

```
mode=standard                    filesAnalyzed 8  err 0
mode=off                         filesAnalyzed 8  err 0
mode=off + seeded type error     filesAnalyzed 8  err 0
```

The first table is a **disk-versus-index divergence**: pyright walks the filesystem,
`git ls-files` reads the index, so `touch tests/test_foo.py && make test` — the exact
sequence `tdd.md` mandates — goes red on a non-defect and teaches the operator to stage
before running the suite. The second is worse: the count-equality **pins the denominator and
never the measurement**, so the gate passes green with `typeCheckingMode: off` and a genuine
type error present.

The replacement asserts two things with distinct failure modes:

1. **Mode.** Parse `pyrightconfig.json`; assert `typeCheckingMode == "standard"` and
   `reportMissingImports` is true. This is the artifact under protection — the silent
   downgrade to `off` is precisely what a count-equality cannot see — so reading it is the
   right target rather than displacement onto a proxy.
2. **Coverage, as an equality against pyright's own output with slack modelled.** Assert

   ```
   filesAnalyzed == |git ls-files       'tests/*.py' 'scripts/*.py' '.claude/scripts/*.py'|
                  + |git ls-files -o    'tests/*.py' 'scripts/*.py' '.claude/scripts/*.py'|
   ```

   pyright analyses every `.py` under an `include` root regardless of git state; the two
   `git ls-files` invocations enumerate exactly that set, tracked and untracked. Note `-o`
   without `--exclude-standard`: pyright does not read `.gitignore`, so ignored files must be
   counted too.

**This is the third draft of this assertion, and the first two are recorded because each was
refuted by the fix for its predecessor.**

| draft | defeated by |
| --- | --- |
| `filesAnalyzed == tracked` | one untracked `.py` gives 9 vs 8 — false red inside the TDD loop `tdd.md` mandates |
| assert each tracked path clears `exclude` in Python | `fnmatch` and `PurePath.match` both return False for `('.claude/scripts/triage_log.py', '**/.*')` while pyright drops the file; pyright excludes by directory descent and no stdlib glob has that semantics |
| `filesAnalyzed >= tracked` | slack is one-directional in the *other* direction too: one untracked file buys back a dropped `include` root |

The third refutation, measured on the real tree:

```
baseline                        filesAnalyzed=8  tracked=8   pass
include root dropped            filesAnalyzed=7  tracked=8   FAIL
dropped + 1 untracked scratch   filesAnalyzed=8  tracked=8   PASS   <- triage_log.py unanalysed
```

`>=` would have gone green with the file unanalysed. Worse, the two requirements were not
independent: Verification row 8 requires the gate green on a dirty tree, and mutation 4
certifies it on a clean one — one mechanism read in opposite directions, with only the
flattering direction argued.

The equality above is verified against all four states, including the case the `**/.*`
removal opens:

```
baseline                            fa=8   expected 8 + 0 = 8    pass
+1 untracked                        fa=9   expected 8 + 1 = 9    pass
+1 untracked, include root dropped  fa=8   expected 8 + 1 = 9    RED
gitignored tests/.fakevenv/, 2 .py  fa=10  expected 8 + 2 = 10   pass
```

The third row is the one that matters: mutation 4 now fires **in a dirty tree**, which is the
state the operator is usually in. The fourth confirms `git ls-files -o` recurses into ignored
directories and lists files individually rather than collapsing the directory.

A set-based assertion would be stronger and is **unavailable**: `pyright --outputjson` emits
only `version`, `time`, `generalDiagnostics` and `summary` — no analysed-file list — and
`--dependencies` names none either (measured: 0 matches for two known analysed filenames).
So a cardinality check is the best available, and what it cannot express is *which* file was
reached. Mutation 4 covers that at implementation time.

Vacuity floor: the tracked count must be non-zero, so an empty `git ls-files` cannot make the
inequality trivially true.

The test skips when `pyright` is absent — **except when the `CI` environment variable is
set, where a missing `pyright` fails.** Assertion 2 invokes pyright, so this guard is live
rather than vestigial.

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
| `make install-deps` on the Mac Studio, neither package present | both install; `make test-python` then `OK` |
| `make install-deps` over `ssh workstation`, no venv | exits non-zero naming the venv command — **not** tested inside a venv, where PEP 668 cannot fire |
| `touch tests/_scratch.py && make test` | `OK` — the redesigned gate is index-only and must not go red on untracked state |

Five mutations, because a gate that has never gone red is not yet a gate:

1. Seed a return-type error into `.claude/scripts/triage_log.py`; root `pyright` must report
   it. This proves the dot-directory reach is live, rather than inferred from reading the
   config.
2. Add an unguarded `import requests` to a root test file; `tests/test_root_python_deps.py`
   must go red, and must name `requests`.
3. Set `typeCheckingMode` to `off` in `pyrightconfig.json`; `tests/test_root_pyright_scope.py`
   assertion 1 must go red. The old design passed this case at full green.
4. Restore `**/.*` to the config's `exclude`; assertion 2 must go red. Measured: this takes
   `filesAnalyzed` from 8 to 7 while the expected total stays 8. **Run this mutation with an
   untracked `.py` present as well as on a clean tree** — the `>=` draft passed the dirty
   case, which is how the false green was found.
5. Widen `scripts/pre-push:52` to `.` (match everything); the new negative `pre_push.bats`
   case must go red. No existing case does.

All five mutations are reverted before commit, and `git status --porcelain` must be empty
afterwards.

## Documentation

- `CLAUDE.md` "Type checking (Python — pyright)" — replace the `scripts` row with the root
  config, its 8-file denominator, the `exclude`-beats-`include` finding, and the 1.1.411 pin
  scoped to `scripts.yml`.
- `CLAUDE.md` — a note naming `requirements-dev.txt`, its definition, and the fact that root
  `install_deps.sh` deliberately does not exist.
- `CLAUDE.md` "Repo-level Python tests" — updated test count.
- `CLAUDE.md` Setup block — `make install-deps` beside `make install-hooks`.
- `CLAUDE.md` Type-checking section — **two corrections beyond the table row.** It currently
  says pyright "runs in CI only — not in `make lint` (spawn overhead on macOS makes it slow
  locally)". After this change `tests/test_root_pyright_scope.py` runs under `make
  test-python`, which the pre-push hook invokes, so the CI-only half becomes false. The
  severity half is already stale: three runs measured `real 0.90`, `0.89`, `0.91`.
- `CLAUDE.md` — the `cd <sub-project> && pyright` instruction now behaves differently for
  `scripts/`, whose config this change deletes; it falls back to pyright defaults rather than
  erroring. Say so rather than leaving the sentence to cover nine directories it no longer
  describes uniformly.
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

---

## Multi-Lens Review

Reviewed at commit: `dd573f6` (Step 7 self-review commit, before Step 8 dispatch)

Round 1. Three lenses, dispatched in parallel as fresh subagents with no conversation
history. Every finding below was re-measured by the session before being recorded; two lens
claims were refuted that way and are marked as such.

### Goal-Fit

Finding, four parts:

1. **`requirements-dev.txt` changes no verdict today.** Its consumer (a) is
   `scripts.yml:34`, which already installs both packages, so no CI verdict can differ. Its
   consumer (b) is `dependency-review`'s `MANIFEST_RE`, which does match the filename — real,
   but fires only on future additions. Row 1's stated symptom is closed by a CLAUDE.md
   sentence, not by the file. A `make install-deps` target consuming the manifest would turn
   the fix from prose into a command; the spec rejects a root `install_deps.sh` on
   `dependency-review`-visibility grounds, which is not an argument against a Makefile target.
2. **REFUTED — claimed recursion mismatch between `git ls-files 'tests/*.py'` and pyright's
   directory `include`.** The lens asserted the pathspec is single-level. Git pathspecs use
   wildmatch without pathname semantics, so `*` crosses `/`. Measured against untracked
   probes:

   ```
   git ls-files -o --exclude-standard 'tests/*.py'
     tests/_probe_flat.py
     tests/scripts/_probe_nested.py      <- nested, matched
   git ls-files -o --exclude-standard ':(glob)tests/*.py'
     tests/_probe_flat.py                <- :(glob) is what makes it single-level
   ```

   The ergonomics lens independently reached the correct answer. No mismatch exists, and the
   proposed `tests/**/*.py` "fix" would have narrowed the set rather than widening it.
3. **`.claude/scripts/` is in the CI `paths:` filter and not in the pre-push regex.**
   Confirmed: `'.claude/scripts/triage_log.py'` does not match
   `^scripts/|^tests/|^Makefile$|...`. The one file the design argues hardest to keep in the
   denominator is the one editable without the local suite running.
4. **The pyright gate has no vacuity floor** where its sibling has explicit ones. See Risk,
   which found the sharper instance.

Premise verification: picked Row 2's "2 of the 8 tracked root-scope Python files are
type-checked". `cat scripts/pyrightconfig.json` returns
`"include": ["time_tests.py", "test_metrics.py"]`; `git ls-files 'tests/*.py' 'scripts/*.py'
'.claude/scripts/*.py' | wc -l` returns 8. Confirmed. Row 1 verified independently in the
same pass: `pyyaml` appears in exactly one tracked non-doc file.

Assumption: that no root-scope Python file will ever live in a subdirectory. **Refuted** —
the pathspec is already recursive, so the assumption is not load-bearing.

Disposition: **Addressed.** Finding 1 added `make install-deps` (§1). Finding 3 added
`^\.claude/scripts/` to the pre-push regex (§4). Finding 4 drove the §5 gate redesign.
Finding 2 was refuted by measurement and no change was made; the refutation is recorded above
so a later reader does not re-derive the wrong conclusion.

### Ergonomics

Finding, four parts:

1. **No installer, no `make` target, no error path.** After this change a fresh checkout
   still fails with `ModuleNotFoundError: No module named 'yaml'`, with nothing in the
   failure naming the new file. The repo already has the remedy-in-the-message pattern at
   `Makefile:84`. Same finding as Goal-Fit 1, reached independently.
2. **The pyright gate is red-on-untracked, which breaks this repo's mandated TDD loop.**
   pyright walks the filesystem; `git ls-files` reads the index. Confirmed by measurement
   against the config this spec proposes:

   ```
   clean tree        pyright=8   git ls-files=8
   1 untracked .py   pyright=9   git ls-files=8
   +1 nested         pyright=10  git ls-files=8
   ```

   `touch tests/test_foo.py && make test` — the exact sequence `tdd.md` requires — turns the
   gate red on a non-defect, and teaches the operator to stage before running the suite.

   The session's first probe of this returned 8 vs 8 and read as a refutation. That probe
   used the default-`exclude` config, where 7 tracked files plus 1 untracked coincidentally
   equals the tracked count of 8 — a value compatible with both causes. Re-run with the
   proposed config, it discriminates.
3. **Putting pyright on the pre-push path contradicts CLAUDE.md**, which states pyright
   "runs in CI only — not in `make lint` (spawn overhead on macOS makes it slow locally)".
   The new test runs under `make test-python`, which the pre-push hook invokes. The severity
   half of that sentence is also stale: three runs measured `real 0.90`, `0.89`, `0.91`. The
   Documentation section does not list correcting it.
4. **`.claude/scripts/` pre-push gap.** Same as Goal-Fit 3, reached independently.

Premise verification: picked Row 1's single-declaration claim. A recursive grep over
`*.yml`, `*.sh`, `*.txt`, `*.md` and `Makefile`, excluding `docs/superpowers`, returned
exactly `.github/workflows/scripts.yml:34`. Confirmed.

Assumption: that the window between creating a root-scope `.py` and staging it is rare
enough for `filesAnalyzed == git ls-files` to behave as an identity. **Refuted by the
measurement in finding 2** — the divergence is one `touch` away.

Disposition: **Addressed.** Finding 2 removed the disk walk entirely; the redesigned gate is
index-only and a verification row now pins that `touch tests/_scratch.py && make test` stays
green. Findings 1 and 4 addressed as under Goal-Fit. Finding 3's documentation contradiction
is now listed in §Documentation, including the stale macOS-slowness claim.

### Risk

Finding, five parts:

1. **The spec cites a negative control that does not exist.** It claims the widened pre-push
   regex needs no over-match test because existing negative cases cover that direction.
   Measured — all four `assert_no_match` calls in `tests/scripts/pre_push.bats`:

   ```
   35:  assert_no_match "^make"                              # empty diff
   42:  assert_no_match "^make"                              # empty diff
   115: assert_no_match "make -C .../pi test"
   124: assert_no_match "make -C .../pi/pi-rs test"
   ```

   The two `^make` cases run with an empty diff, which an over-broad regex passes too; the
   other two name a specific sub-project target, not the root one. **No test in that file
   fails if line 52 is widened to match everything.** The failure would be silent — root
   `make test` on every push — and it gates every push in the repo.
2. **The pyright gate pins the denominator and never the measurement.** Nothing asserts
   `typeCheckingMode`. Measured on the real tree:

   ```
   mode=standard              filesAnalyzed 8  err 0
   mode=off                   filesAnalyzed 8  err 0
   mode=off + seeded error    filesAnalyzed 8  err 0
   ```

   The third row is worse than the lens reported: with checking disabled, a genuine seeded
   type error is invisible and both the gate and the `Run pyright` step exit 0. This is the
   every-gate-expects-PASS failure exactly.
3. **Two independent walks over one set.** Same finding as Ergonomics 2. The `**/.*` exclude
   removal compounds it: a developer `.venv` or `.pytest_cache` under any of the three
   include roots is now reachable and would inflate `filesAnalyzed`.
4. **Proportionality.** Row 1 has a reproducible failure. Row 2's evidence half is retracted
   by this spec itself — 0 errors across all 8 files. The pyright pin, the config, the third
   gate, the `working-directory` drop and the config deletion all sit on a hole with nothing
   behind it. The spec uses precisely this argument to defer the other 8 pin sites and does
   not apply it to itself.
5. **Minor.** Deleting `scripts/pyrightconfig.json` changes CLAUDE.md's documented
   `cd <sub-project> && pyright` for one of nine directories — it falls back to pyright
   defaults rather than erroring. The Documentation section updates the table row but not
   that sentence.

Premise verification: picked Row 1's declaration claim; a full-repo grep returned one CI
declaration, zero installers, one unguarded import. Confirmed. Collaterals also reproduced:
the `include` of 2, the tracked count of 8, and `pyright` returning 7 files when
`.claude/scripts` is named explicitly under the default exclude.

Assumption: that the filesystem set and the index set stay identical. **Refuted** — the
lens's own stated refutation command returns 9 against a tracked count of 8 once an
untracked file exists.

Disposition: **Addressed**, except finding 4. Finding 1 added a real over-match negative case
and recorded that the control this spec claimed does not exist. Finding 2 drove the mode
assertion; mutation 3 now pins it. Finding 3 is resolved by the gate becoming index-only.
Finding 5 is now in §Documentation.

Finding 4 — proportionality, split the PR — **Accepted, reason: the operator chose the
redesign over the split when both were put to them.** The lens is right that Row 2 has no
measured breakage behind it. The counter-argument is that the redesign is *smaller* than what
it replaces — a disk walk removed, no pyright invocation in the new assertions — so it
removes the four new failure points the lens objected to rather than deferring them.

### Adversarial Spec Review (comparison/judge designs only)

N/A — the spec has no comparison arms, no judge or evaluator component, and its acceptance
criteria are concrete derived counts rather than qualitative verdicts.

---

## Multi-Lens Review — Round 2

Reviewed at commit: `72a5c17`

All three lenses re-run after the round-1 revision replaced a gate wholesale, added a
Makefile target, and widened a git hook regex. Each was told the round-1 section is history,
not findings, and pointed at defects the revision itself introduced. Every finding below was
re-measured before being recorded.

### Goal-Fit

Finding, four parts:

1. **The revision left the design it replaced standing in the body**, stated last and
   unmarked — a duplicated `pre_push.bats` block plus the retracted count-equality gate. An
   implementer reading top-to-bottom would have implemented the refuted design. Confirmed:
   `grep -n test_root_pyright_scope` returned hits at 302 and 375 describing two incompatible
   tests. A pure revision artifact, and the highest-cost item in the document.
2. **The redesign over-corrected: the round-1 defect was the operator, not the measurement.**
   `filesAnalyzed >= len(tracked)` is immune to untracked files, goes red on a restored
   `**/.*`, keeps pyright in the standing suite, and needs no matcher reimplementation.
3. **Assertion 2 as drafted could not satisfy mutation 4.** `fnmatch` and `PurePath.match`
   both return False for `('.claude/scripts/triage_log.py', '**/.*')` while pyright drops the
   file — the mutation would have stayed green.
4. Row 1's half is right-sized and unarguable; the pre-push widening and its negative case
   are the only new standing test pinning something no existing test pins.

Premise verification: picked the revision's claim that the pyright invocation could be
dropped because the pin covers instrument stability. Ran `pyright --outputjson` and found
`filesAnalyzed` is a live integer already discriminating 7 vs 8. **Verdict: the premise that
the measurement had to be abandoned is false** — only the equality had to go.

Assumption: that `.claude/scripts/` keeps containing exactly `triage_log.py` and stays
repo-authored code worth type-checking. CLAUDE.md records the vendoring is contingent on
ai-config spec `2026-07-29-telemetry-home-anchoring-design.md`, still Status: Spec.
Genuinely open in both directions.

Disposition: **Addressed.** Finding 1 removed 28 lines. Findings 2 and 3 replaced assertion 2
with the inequality, with the measurement recorded. Finding 4 needed no action.

The assumption is **accepted as a known contingency, not resolved.** Assertion 2 is now a
count inequality rather than a per-filename check, so a deleted `triage_log.py` lowers both
sides and the gate stays green — the coupling the assumption warned about is gone as a side
effect of the round-2 fix rather than by design.

### Ergonomics

Finding, four parts plus one minor:

1. Same stale-duplicate finding as Goal-Fit 1, reached independently.
2. **§5 defined "guarded" precisely and never defined "third-party".** `from
   scripts.test_metrics import ...` is unguarded, top-level, and not in
   `sys.stdlib_module_names`, so the natural implementation demands `scripts` in the
   manifest. Both vacuity floors guard under-detection only, so nothing else catches it.
3. **The skip-guard was written for assertions that no longer existed** — the round-2 draft
   invoked no pyright, so a missing binary would fail a test that never used it.
4. **`make install-deps` declared no environment boundary.** Measured: `pip` resolves to
   `/Users/bruce/.pyenv/versions/ansible/…` on this machine.
5. Minor: `.github/workflows/scripts.yml` absent from the widened pre-push regex.

Premise verification: picked the revision's claim that `make install-deps` closes Row 1,
which requires `pip` and `python3` to be the same interpreter. Holds on this machine because
pyenv shims both; **asserted, not scoped**.

Assumption: that `pip` and `python3` resolve to the same interpreter on a fresh checkout. The
failure shape is the worst available — install exits 0, suite still raises
`ModuleNotFoundError`, reproducing Row 1's symptom behind a green install.

Disposition: **Addressed.** Finding 2 added an explicit first-party clause with the
counter-example. Finding 3 is resolved by assertion 2 invoking pyright again, making the
guard live. Finding 4 changed the recipe to `python3 -m pip`, which makes the assumption moot
rather than answered — the lens's own preferred resolution. Finding 5 added
`^\.github/workflows/scripts\.yml$` to the regex, justified by `makefile.bats:133` grepping
that file.

### Risk

Finding, seven parts. 1 through 4 duplicate Goal-Fit 1/2/3 and Ergonomics 4 and are
dispositioned there. New:

5. **One negative sample tests one point, not a boundary.** Mutation 5 (widen line 52 to `.`)
   goes red; widening to `^\.` or `^pyright` would not.
6. **The round-1 enumeration bounding the workflow edit stopped at find-first** —
   `makefile.bats` has two `ruff==` assertions, `:128` and `:133`, and only `:133` was cited.
   `:128` is unaffected, so no breakage.
7. `cd scripts && pyright` after the config deletion does not error; it falls back to defaults
   and checks the cwd, so a green result there is indistinguishable from a configured pass.

Premise verification: picked mutation 4's claim that a restored `**/.*` fails the coverage
assertion. Reproduced in a scratch mirror: pyright 3 files → 2 files; `fnmatch`,
`PurePath.match` and `PurePath.full_match` all False. **Verdict: false under the three most
likely implementations** — which is what retired the stdlib matcher.

Assumption: that pyright's include/exclude matching is a stable, reimplementable contract a
stdlib-only assertion can track. **Refuted by the measurement above**, and the redesign no
longer depends on it.

Disposition: **Addressed** for 6 and 7 — 6 is now recorded beside the `makefile.bats`
constraint, 7 was already in §Documentation and is unchanged.

Finding 5 — **Accepted by the operator, 2026-09-05.** Reason: one negative case is what the
existing file's pattern supports, and the boundary it fails to pin is narrower than the class
mutation 5 covers — a regex widened to `^\.` or `^pyright` is a deliberate edit rather than
the accidental over-broadening the case exists to catch. Recorded rather than fixed so a later
reader can disagree with the trade.

Provenance, because it matters for a disposition: this reason was drafted by the session and
put to the operator twice as needing confirmation or replacement; it was confirmed on the
second ask. It is not an inferred disposition.

### Adversarial Spec Review (comparison/judge designs only)

N/A — unchanged from round 1.

---

## Multi-Lens Review — Round 3 (scoped)

Reviewed at commit: `c0165ea`. **Scoped re-review**, one lens (Risk), pointed only at the
sections the round-2 revision changed: `make install-deps`, the four-alternative pre-push
regex, the "third-party" definition, the coverage inequality, and the five mutations. The
rest of the document is unchanged and reviewed twice already.

### Risk (scoped)

Finding, two parts:

1. **The coverage inequality had a false-green mode, and the spec's own verification row
   mandated the conditions for it.** `>=`'s tolerance of untracked files was argued only in
   the direction that flatters it. Slack also buys back a *dropped* tracked file. Reproduced
   on the real tree:

   ```
   baseline                        filesAnalyzed=8  tracked=8   pass
   include root dropped            filesAnalyzed=7  tracked=8   FAIL
   dropped + 1 untracked scratch   filesAnalyzed=8  tracked=8   PASS
   ```

   Mutation 4 was specified on a clean tree — the one state where slack is zero — while
   Verification row 8 requires the gate green on a dirty tree, which is the state `tdd.md`'s
   red-green loop keeps the operator in. Two requirements that are one mechanism read in
   opposite directions.

2. **`make install-deps` does not work on the Linux 7950X.** The round-2 justification for
   `python3 -m pip` was also wrong on its own terms: on the Mac Studio `pip` and
   `python3 -m pip` print the identical line, so the divergence the spec asserted does not
   exist there. The remedy is right for a different, measured reason — PEP 668.

Also raised and not disputed: two Verification rows (`make lint`, `make test` → exit 0) are
satisfied by both linters being absent, since `Makefile:83-84` skips a missing ruff and exits
0 by design; and deriving first-party names from every top-level entry means a future
top-level directory sharing a distribution's import name would silently drop it from the
required set — Row 1's defect reintroduced by the fix for it.

Checked and explicitly cleared: the four-alternative regex over-matches nothing across 16
probed paths; `git ls-files 'tests/*.py'` does match nested paths, so the denominator does not
undercount; no current top-level entry is a plausible root-scope import.

Premise verification: picked the round-2 claim that `>=`'s tolerance is a one-directional
safety property. Scratch-repo differential at baseline, with an include root removed, and with
that removal plus one untracked file: `3/3 pass`, `2/3 FAIL`, `3/3 PASS`. **Verdict: true as
stated, false as relied on.**

Assumption: that the working tree carries no untracked root-scope `.py` when the gate runs.
**Refuted** — Verification row 8 asserts the dirty tree is the normal case, which contradicts
it outright.

Disposition: **Addressed.** Finding 1 replaced the inequality with an equality that models
slack explicitly, verified against four states including the two that killed its predecessors
and the gitignored-directory case the `**/.*` removal opens. Mutation 4 now requires running
in a dirty tree as well as clean. Finding 2 added the PEP 668 guard, measured over
`ssh workstation`, and the verification row no longer tests only inside a venv.

The two null-passing `make lint` / `make test` rows are **Accepted** — they are pre-existing
properties of `Makefile:83-84`'s deliberate skip-on-missing-tool design, which `ci.md`
requires so a machine is never locked out of committing the change that installs the tool.
Not introduced here and not this spec's to fix.

The first-party-name collision is **carried to the backlog** rather than fixed, and the row
must state its **trigger, not its current state**: it becomes live the moment a new top-level
directory is added whose name matches a distribution this repo imports. The safe-today
measurement — no current top-level entry among `amicable collatz docs e factorial fib
goldbach perfect-numbers pi prime scripts sq tests twin-primes` is a plausible import name —
is what makes deferring it reasonable, and is exactly the wrong thing to write in the row,
because it is dated and this repo adds top-level directories. The failure mode is Row 1's
defect reintroduced by Row 1's fix: a shadowed name silently drops a genuine dependency from
the required set, and both vacuity floors guard under-detection only.

### Stopping

Three rounds, and each round found a defect created by the previous round's fix — the pattern
this skill names as the argument against budgeting rounds on decaying yield. Stopping anyway,
on both stated signals:

- **Artifact location.** Round 3's remaining items are in the test harness and the mutation
  procedure, not the mechanism. The one design finding was resolved by a form now verified
  against its own failure modes rather than reasoned about.
- ~~**Direction of the corrections.**~~ **Retracted — this signal was read on the wrong
  object and does not hold.** The claim was that every round removed surface. Measured over
  the document:

  ```
  dd573f6  327 lines
  72a5c17  628
  c0165ea  847
  7b65860  969
  ```

  It grew every round. The claim is true of the *component under review* — the gate mechanism
  shed a matcher reimplementation and a config-only read — and false of the artifact, because
  each round also added measurements, dispositions and review prose. Reading a
  whole-document signal off one component is the same error as measuring `pi` and claiming
  all 8 sub-projects, committed twice in one spec.

**The stop rests on artifact location alone, which does hold.** That is a weaker argument
than two agreeing signals and is recorded as such. The next round should be Phase 2's first
red test.

Found by external review, not by this session — and the finding it came with was that the
duplication removed in round 2 had been reintroduced by the round-3 edit, with the second
copy carrying the *refuted* round-2 gate. Same defect, same document, one round apart:

```
338 / 451  Four `tests/scripts/pre_push.bats` cases          duplicated
360 / 473  **tests/test_root_pyright_scope.py**              duplicated
448        "assertion 2 invokes pyright, so this guard is live"
521        "Assertions 1 and 2 need no pyright binary at all"
```

An implementer reading to the end would have built the design round 2 refuted. Removed, and
the lesson is mechanical rather than attitudinal: **`str.index` anchors find the first
occurrence, so a splice against a document that already contains a duplicate silently
preserves the copy after it.** Any future edit to this file must re-grep for its own anchors
afterwards, which is what the verification commands under §Verification do for code and
nothing was doing for prose.
