# One CLI contract and uniform project files for the 8 Python sub-projects

**Status:** Approved, revision 4, 2026-10-25.
- **Approved:** 2026-10-25 by the operator ("Approve, write plan"), after three Multi-Lens Review rounds.

Design sections approved in conversation by the operator; revision 2 applies the operator's dispositions on the round-1 Multi-Lens Review
(below): Rust CLIs deferred, per-project contract test with an open pipe, a vendored gmpy2
stub, and five smaller corrections. Revision 3 applies the round-2 dispositions: shared inputs
trigger the project workflows, a declared `LARGE_RUN_THRESHOLD`, "proceeds with `--yes`" checked
by mocked pytests, and the benchmark recipe and its CI steps deleted. Revision 4 applies the
round-3 disposition: pre-push runs the harness alone on a harness change.

## Problem

Operator rule (2026-10-24): all 11 math projects are treated the same, all of the time; a
per-project difference is a defect unless it is a declared, justified parameter.

The Rust side was made uniform in math#166-#170: every per-crate file is rendered from
`scripts/crate_templates/` by `scripts/render_crate_files.py`, and `tests/test_crate_uniformity.py`
fails on drift. The 8 Python sub-projects (amicable, collatz, e, factorial, fib, perfect-numbers,
pi, sq) were not. Measured 2026-10-25 on master `f7658ed`, comparing each project's file after
replacing its own name and module name with placeholders, against fib's:

| File                           | Projects | Distinct variants |
| ------------------------------ | -------- | ----------------- |
| `<p>/Makefile`                 | 8        | 8                 |
| `<p>/install_deps.sh`          | 8        | 8                 |
| `.github/workflows/<p>-py.yml` | 8        | 7                 |
| `<p>/cosmic-ray.toml`          | 8        | 6                 |
| `<p>/pyrightconfig.json`       | 8        | 3                 |

Two differences are not drift but behaviour, and they block identical files:

1. **The CLIs behave differently.** Each Python CLI takes one positional argument, but they
   prompt at different points: e and pi ask "Continue with N digits?" above 1,000,000 digits
   (only interactively; with an argument they warn and continue) and "Display all?", and their
   bare `input()` raises `EOFError` at "Display all?" (caught, exit 1); fib confirms at X >= 4
   even with an argument; sq asks whether to display (and already reads end of input as no). So
   e, pi and sq's benchmark recipes pipe `printf "n\n" |`, each recipe passes a different size
   (amicable 5, collatz 5, e 10000, factorial 1000, fib 3, perfect-numbers 6, pi 10000, sq 1),
   and the timeouts differ (60 s for amicable and perfect-numbers, 30 s elsewhere). Measured in
   a scratch copy, every one of those recipes finishes in 0.09-0.50 s: they are smoke runs.
2. **Type checking differs.** e and pi run pyright `basic` with `reportAttributeAccessIssue`
   and `reportOptionalMemberAccess` off, because gmpy2 2.3.1 ships no `.pyi` and no `py.typed`.
   pyright 1.1.411 in `standard` mode on copies of master reports 41 errors for e and 78 for pi.

Also: only pi, e and factorial install gmpy2 and mpmath; only factorial publishes Python test
metrics; and the only real per-project setting in `cosmic-ray.toml` is `timeout` (60 for e and
pi, 30 elsewhere; `excluded-modules = []` everywhere).

## Design

### 1. One CLI contract for the 8 Python CLIs

```
python3 <module>.py SIZE [--show] [--yes]   # never reads stdin
python3 <module>.py --smoke                 # never reads stdin; runs at SMOKE_SIZE
python3 <module>.py                         # interactive only when stdin is a TTY, else exit 2
```

- `SIZE` is the single positional argument. Its meaning stays per program (exponent N for
  amicable, collatz, fib, perfect-numbers and sq; digit count for e and pi; n for factorial) and
  is stated in `--help`.
- With any argument a program never reads stdin. Results always go to the output file; `--show`
  also prints them to stdout, replacing every "Display all?" prompt.
- Large-run thresholds stay as they are, declared as a module-level `LARGE_RUN_THRESHOLD`: the
  smallest size that needs `--yes` (pi and e `1_000_001` digits, fib `4`), or `None` for the
  other 5. At or above it without `--yes`, the program exits 1 and names `--yes`, before doing
  any work; with `--yes` it proceeds. A program whose threshold is `None` accepts `--yes` and
  ignores it.
  For pi and e this is a behaviour change: a size above 1,000,000 with no `--yes` used to warn
  and continue (accepted by the operator).
- `--smoke` runs at a module-level `SMOKE_SIZE`, today's benchmark size for each program. It
  never needs `--yes` (every `SMOKE_SIZE` is below its threshold) and never shows.
- No arguments and stdin a TTY: the interactive prompt as today; at end of input a y/n prompt
  reads as no and a number prompt exits 1 naming the argument (math#161). No arguments and stdin
  not a TTY: exit 2 with usage.
- Exit codes: 0 success (including a run declined interactively), 1 invalid input, I/O failure
  or a refused large run, 2 usage error.
- Output file names are unchanged.

The `benchmark:` recipe and the 8 "Benchmark (timeout gate)" CI steps are deleted, with
`TestBenchmarkGatesCanFail` in `tests/test_workflow_continue_on_error.py`: the harness's `--smoke`
case (Design 2) runs inside every `make test` with the same 60 s timeout and also checks the
output file, so a second run in CI could change no decision.

### 2. Contract test, run by each project

- One shared harness, `scripts/cli_contract.py <module.py>`, reads the program's `SMOKE_SIZE`
  and `LARGE_RUN_THRESHOLD` by importing the module, runs the program as a subprocess against
  one matrix, and exits non-zero naming every failing case. Each run uses a fresh temp
  working directory, and stdin is an open pipe that is never written to, with a 60 s timeout:
  a program that reads stdin blocks and fails on the timeout instead of reading end of input
  as no.
- Cases: `SIZE` (the program's `SMOKE_SIZE`) writes a non-empty output file, prints nothing
  that looks like a prompt (`?`, `(y/n)`), and exits 0; `SIZE --show` prints at least one
  result line from the output file to stdout; `--smoke` behaves like `SIZE` at `SMOKE_SIZE`;
  when `LARGE_RUN_THRESHOLD` is set, `LARGE_RUN_THRESHOLD` without `--yes` exits 1 naming
  `--yes` within 5 s and writes no output file; when it is `None`, `SIZE --yes` exits 0 like
  `SIZE`; `y` written to stdin with `SIZE` still shows nothing; no arguments with stdin not a
  TTY exits 2. "Proceeds with `--yes`" is not run by the harness, because fib's smallest
  refused size takes about 15.5 s and writes 239 MB: pi, e and fib each test it in pytest with
  the computation mocked.
- Each project's `make test` runs pytest and then the harness against its own program, so the
  PR that changes `pi/pi.py` runs pi's contract in `pi-py.yml` (paths `pi/*.py`) with pi's
  dependencies installed, and pre-push runs it on any `.py` change in that project. The shared
  inputs `scripts/cli_contract.py` and `typings/**` are in every `py.yml`'s `paths:`, so a PR
  that changes only the harness or the stub still runs every real program against it in CI.
  Locally, a push touching `scripts/cli_contract.py` runs the harness alone against the 8
  programs (no pytest, about 2 s), which leaves pre-push's more-than-6-projects bail-out (the
  macOS resource_tracker guard) untouched. `typings/**` stays CI-only, like sub-project pyright.
- The harness holds stdin open with `os.pipe()`, keeping the write end open for the whole run:
  `subprocess.run(..., stdin=subprocess.PIPE)` closes stdin at once, so a reader sees end of
  input and the check is silently defeated (measured: rc 0 in 0.01 s against an `input()` stub).
- A test pins each program's `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD` to the values in R3 and R4,
  because the harness learns both from the module and would follow a deleted gate. The mocked
  "proceeds with `--yes`" pytests assert the mocked computation was called with the threshold
  size, not only that the exit code was 0 (fib's decline path today is a bare `return`).
  `tests/test_cli_contract_harness.py` unit-tests the harness itself against stub programs
  (one that prompts, one that writes nothing, one that ignores `--yes`, one that conforms).

### 3. Per-project Python files rendered from templates

- Five new template kinds in `scripts/crate_templates/python/`, rendered for the 8 projects:
  `Makefile` -> `<p>/Makefile`, `install_deps.sh` -> `<p>/install_deps.sh`, `py.yml` ->
  `.github/workflows/<p>-py.yml`, `pyrightconfig.json` -> `<p>/pyrightconfig.json`,
  `cosmic-ray.toml` -> `<p>/cosmic-ray.toml`.
- `render_crate_files.py` gains a second project list (`PYTHON_PROJECTS`, the 8) and a second
  placeholder, `@MODULE@`, derived from the directory name with `-` replaced by `_`. Any other
  `@NAME@` stays an error. `test_crate_uniformity.py` covers the new kinds, and `scripts.yml`
  triggers on every rendered path.
- **Libraries:** all 8 install the same set (GMP and MPFR system libraries; gmpy2 and mpmath),
  following the operator's Rust choice (math#168). Every pip-installed package in the Python
  workflows and installers carries one exact version repo-wide, chosen as the newest stable
  (non-pre-release) version at least two weeks old; `tests/test_tool_pins.py` is extended to require it.
- **pyright `standard` for all 8.** A repo-root `typings/gmpy2/__init__.pyi` types exactly the
  names, classes and methods the code and tests use (including `mpfr.digits`, the context's
  `precision`, and the arithmetic operators on `mpz` and `mpfr`) without `Any`, and e and pi
  narrow their optional import with `_gmpy2 is not None` in each function that uses it (pyright
  does not carry a caller's check into a callee). Every `pyrightconfig.json` points
  `stubPath` at `../typings`. A test fails if the stub contains `Any`.
- **Test metrics** for all 8 Python workflows, extending factorial's pilot (as math#169 did for
  Rust).
- **cosmic-ray:** `timeout = 60` in every project, so the file is identical after substitution.

### 4. Delivery

- **P1** CLI contract for the 8 Python CLIs, the shared harness and its tests, each project's
  `make test` running it.
- **P2** the gmpy2 stub and pyright `standard` for e and pi.
- **P3** Python templates, pinned libraries and test metrics, with the benchmark recipe and its
  CI steps deleted (depends on P1 and P2).

Deferred to a Backlog row (operator, round 1): the same contract for the 11 Rust binaries.
Measured `read_line` counts on master: pi 12, e 12, fib 14, sq 13, prime 12, factorial 10,
perfect-numbers 3, goldbach 1, collatz 1, twin-primes 0, amicable 0. It needs a consumer
first, such as a contract-smoke step in the Rust CI template.

### 5. Testing

Each changed function gets boundary, error-path and state-transition tests, written RED first.
The harness's own tests prove each contract case can fail. Coverage stays at or above 90% per
sub-project.

## Requirements

- **R1.** `[P1]` Each of the 8 Python CLIs accepts `SIZE`, `--show`, `--yes` and `--smoke`, and with any argument never reads stdin.
- **R2.** `[P1]` A Python CLI given `SIZE` writes its output file, prints the results to stdout only with `--show`, and exits 0.
- **R3.** `[P1]` Each Python CLI defines a module-level `LARGE_RUN_THRESHOLD` (pi and e `1_000_001`, fib `4`, the other 5 `None`); at or above it without `--yes` the CLI exits 1 naming `--yes` before any computation, and with `--yes` it proceeds, the latter shown by a pytest with the computation mocked in pi, e and fib.
- **R4.** `[P1]` Each Python CLI defines a module-level `SMOKE_SIZE` equal to its benchmark size on master `f7658ed` (amicable 5, collatz 5, e 10000, factorial 1000, fib 3, perfect-numbers 6, pi 10000, sq 1), and `--smoke` runs at that size.
- **R5.** `[P1]` A Python CLI run with no arguments and stdin not a TTY exits 2 with usage.
- **R6.** `[P1]` `scripts/cli_contract.py` reads `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD` from the module, runs the Design 2 matrix with stdin an open, never-written pipe and a 60 s timeout (5 s for the refusal case), and exits non-zero naming each failing case.
- **R7.** `[P1]` `tests/test_cli_contract_harness.py` shows the harness failing a stub that prompts, one that writes no output, one that reads stdin without printing a prompt (must fail by timeout), one that does not refuse at its threshold, and one that rejects `--yes` when its threshold is `None`, and passing a conforming stub.
- **R8.** `[P1]` Each Python project's `make test` runs the harness against its own program after pytest.
- **R9.** `[P2]` A repo-root `typings/gmpy2/__init__.pyi` contains no `Any`, every Python `pyrightconfig.json` sets `stubPath` to `../typings`, and e and pi, including `test_e.py` and `test_pi.py`, pass pyright `standard` with 0 errors and no `reportAttributeAccessIssue` or `reportOptionalMemberAccess` override.
- **R10.** `[P3]` `<p>/Makefile`, `<p>/install_deps.sh`, `.github/workflows/<p>-py.yml`, `<p>/pyrightconfig.json` and `<p>/cosmic-ray.toml` for the 8 projects are rendered from `scripts/crate_templates/python/` with only `@CRATE@` and `@MODULE@` substituted, and `tests/test_crate_uniformity.py` fails on any drift.
- **R11.** `[P3]` No Python Makefile has a `benchmark:` target, no `*-py.yml` has a "Benchmark (timeout gate)" step, and `TestBenchmarkGatesCanFail` is removed.
- **R12.** `[P3]` All 8 Python installers and workflows install GMP, MPFR, gmpy2 and mpmath, and every pip-installed package in them carries an exact `==` version of a stable release, one version per package repo-wide, enforced by `tests/test_tool_pins.py`.
- **R13.** `[P3]` All 8 Python workflows publish `test-metrics-<p>-py`.
- **R14.** `[P3]` Every `cosmic-ray.toml` sets `timeout = 60`.
- **R15.** `[P3]` `.github/workflows/scripts.yml` triggers on every path the renderer writes.
- **R16.** `[P1]` Every `*-py.yml` `paths:` includes `scripts/cli_contract.py` and `typings/**`, and `scripts/pre-push` runs `scripts/cli_contract.py` alone against all 8 Python programs when a push touches `scripts/cli_contract.py`, without changing its more-than-6-projects bail-out.
- **R17.** `[P1]` A test pins each Python CLI's `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD` to the R3 and R4 values, and the mocked "proceeds with `--yes`" pytests in pi, e and fib assert the mocked computation was called with the threshold size.
- **R18.** `[P3]` The root `CLAUDE.md` no longer says output files are "written by `make benchmark` too".
- **V1.** Each PR's CI is green with every affected project's workflow run; the PR body lists them.
- **V2.** Every Python sub-project's coverage stays at or above 90% on CI after each PR.
- **V3.** After P3, `make test` passes for all 8 Python projects in a clean copy of master on `claude`.
- **N1.** No output file is renamed.
- **N2.** No program changes what `SIZE` means.
- **N3.** No pyright suppression is added to any `pyrightconfig.json`, and no `# type: ignore` or `# pyright: ignore` is added to any source file.
- **N4.** No per-project template parameter beyond `@CRATE@` and `@MODULE@`.
- **N5.** No coverage floor is lowered.
- **N6.** No Rust source file changes in this spec's PRs.

## Multi-Lens Review

### Round 1

Reviewed at commit: `c6ef152` (spec commit, after Step 7 self-review)

#### Goal-Fit

Finding: The Rust half (series R1/R2, requirements R14-R16) does not serve the stated problem. The Rust per-crate files are already uniform (math#166-#170), the Rust CI template runs no benchmark step, and Rust benchmarking is Criterion (`benches/`, monthly `benchmarks.yml`). Reads-it test: R16's `benchmark:` target is consumed only by V3, a one-shot run; R14/R15's only consumer is the contract test R15 itself adds. The rewrite is also larger than stated (read_line counts pi 12, e 12, fib 14, sq 13, prime 12, factorial 10, perfect-numbers 3, goldbach 1, collatz 1, twin-primes and amicable 0). Simpler path: P1-P3, deferring the Rust CLIs. Also: R9 raises the benchmark timeout from 30 s to 60 s for six projects, the sq pipe is vestigial, and P2's "small typed helpers" do not reach pyright standard (a helper still reports 1 error); a local stub `typings/gmpy2/__init__.pyi` reaches 0.
Assumption: The operator's rule covers runtime CLI behaviour across languages, not only per-project files.
Disposition: Addressed — operator: "Defer to Backlog". Revision 2 drops the Rust series (now a Backlog row with the measured counts, and N6), replaces helpers with a vendored stub, and makes the 60 s timeout uniform deliberately.

#### Ergonomics

Finding: The contract test in `tests/` runs on the wrong triggers (root `test-python` and `scripts.yml`, neither of which fires on `*/*.py`) and `scripts.yml` lacks the projects' dependencies. `make bench` (Criterion) and a new `make benchmark` collide by name, and the Python recipes are smoke runs (0.09-0.50 s). Stress sizes for prime, twin-primes and goldbach would be a per-project difference. pi and e above 1,000,000 digits change from warning to exiting 1. Gaps: "never reads stdin" untested, "proceeds with `--yes`" untested, `--show` unasserted.
Assumption: Building 11 GMP-linked release binaries per contract run is cheap enough for its trigger.
Disposition: Addressed — operator: "Per-project, open-pipe" and "Accept all five". Revision 2 runs the harness from each project's `make test`, renames `benchmark` to `smoke` (`--smoke`, `SMOKE_SIZE`), keeps sub-second sizes only, records the pi/e behaviour change as accepted, and adds the three missing cases. The build-cost assumption no longer applies (no Rust in scope).

#### Risk

Finding: With stdin closed, the math#161 EOF rule lets a still-prompting CLI pass the SIZE case; detection needs an open, never-written pipe with a timeout or a no-prompt-text assertion. Placement leaves the contract unenforced on the PRs that change it. pyright standard on master copies: e 41 errors, pi 78; helpers only move the access; a 7-name hand-written stub plus `_gmpy2 is not None` narrowing would work. cosmic-ray honours `# pragma: no mutate` only through a `cr-filter-pragma` step this repo does not run, and no `cosmic-ray.toml` has exclusions; the real difference is `timeout` (60 vs 30).
Assumption: A hand-written gmpy2 stub without `Any`, plus narrowing, gets e and pi to 0 pyright standard errors.
Disposition: Addressed — operator: "Per-project, open-pipe", "Vendored stub" and "Accept all five". Revision 2 uses an open pipe plus a no-prompt-text assertion, a vendored stub with a no-`Any` test, and `timeout = 60` instead of pragmas.

#### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

### Round 2

Reviewed at commit: `18510fc` (revision 2). All three lenses re-run on the whole body.

#### Goal-Fit

Finding: Revision 2 created shared inputs (`scripts/cli_contract.py`, `typings/gmpy2/__init__.pyi`) that no project workflow triggers on (`pi-py.yml` paths are `pi/*.py`, `pi/install_deps.sh`, `pi/Makefile`, `pi/pyrightconfig.json` and the workflow), so a harness- or stub-only PR goes green with no real program checked; pre-push has the same gap. Second: the `smoke` recipe and the 8 "Benchmark (timeout gate)" CI steps add nothing once the harness runs `--smoke` inside `make test`; delete rather than rename. A no-`Any` stub with `stubPath: "../typings"` left pi 1 and e 2 attribute errors (all `mpfr.digits`, missing from the probe stub) plus the Optional errors the narrowing removes.
Assumption: fib's "proceeds with `--yes`" case finishes inside 60 s on CI's runner.
Disposition: Addressed — operator: "Add to triggers", "pytest, mocked, all 3", "Accept all, scoped re-review". Revision 3 adds R16, deletes the benchmark recipe and steps (R11), widens the stub wording (R9).

#### Ergonomics

Finding: "Proceeds with `--yes`" for fib means a full X=4 run: measured 15.75 s and a 239,321,457-byte `fib_1e4.txt` on `claude`, on every fib `make test`, pre-push and CI run (pi and e at 1,000,001 digits: 0.51 s and 0.16 s). Also: `scripts/cli_contract.py` is in no `py.yml` `paths:`.
Assumption: fib X=4 with `--yes` finishes well inside 60 s on the 2-vCPU runner and on macOS.
Disposition: Addressed — operator: "pytest, mocked, all 3". The harness checks only the refusal (before any work); pi, e and fib test "proceeds" in pytest with the computation mocked; the assumption no longer applies.

#### Risk

Finding: Same shared-input trigger gap (pre-push regex has nothing for `typings/`). Smaller: fib's `--yes` case (15.5 s, 239 MB); the pin rule picks mpmath `1.5.0a1`, an alpha (newest stable is 1.4.1); the harness has no declared way to learn thresholds, which would force a hidden per-program table; no case checks `SIZE --yes` exits 0 where there is no threshold. Premises held: pyright standard on master copies gives e 41 and pi 78 errors; `stubPath: "../typings"` is honoured; a no-`Any` stub covering the used classes and methods (`context.precision`, arithmetic, `mpfr.digits`) plus 6 per-function `_gmpy2 is not None` guards in each of e and pi reaches 0 standard errors including the tests. No R/N contradiction.
Assumption: fib's `--yes`-proceeds case finishes inside 60 s on every machine that runs fib's `make test`.
Disposition: Addressed — operator: "pytest, mocked, all 3" and "Accept all, scoped re-review". Revision 3 declares `LARGE_RUN_THRESHOLD` (read by the harness), adds the no-threshold `--yes` case, and requires stable pins.

#### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

### Round 3

Reviewed at commit: `8c1b173` (revision 3). Risk lens only (operator: "Accept all, scoped re-review"), briefed to focus on the revision-3 diff while reading the whole body.

#### Risk

Finding: R16's pre-push half is vacuous: adding all 8 projects to `DIRS_TO_TEST` trips `scripts/pre-push`'s `"${#UNIQUE_DIRS[@]}" -gt 6` bail-out, which prints "skipping" and exits 0, and the `typings/**` half buys nothing locally because sub-project pyright is CI-only. Second: the open-pipe mechanism has no failing proof; `subprocess.run(..., stdin=subprocess.PIPE, timeout=5)` returned rc 0 in 0.01 s against an `input()` stub (stdin closed by `communicate()`), while `os.pipe()` with the write end held blocked to the timeout, and R7 has no silent-reader stub, so a harness delivering EOF passes R7. Third: the large-run gate is self-declared; with fib's threshold set to `None` and its gate deleted the harness skips the refusal case, nothing pins the R3/R4 values, and a mocked pytest asserting only exit 0 passes a gate that silently returns. Checked and held: no import side effects (top level is imports and constants, pools in functions, `__main__` guarded); every refusal precedes `open()`; the only other `make benchmark` consumer is a root CLAUDE.md line; all 8 smoke runs take 0.05-0.45 s; no R/N contradiction.
Assumption: Running 8 Python `make test` targets in one pre-push still hangs macOS on resource_tracker; settled by a sequential run on the Mac Studio.
Disposition: Addressed — operator: "Pre-push runs harness only". Revision 4 runs the harness alone on a harness change (bail-out untouched, assumption no longer load-bearing), requires `os.pipe()` and a silent-reader stub (R7), pins the constants and the mocked-call assertion (R17), and removes the stale CLAUDE.md line (R18).

#### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

## Amendments

- finding R1 (2026-10-25, reviewer both): DIFFERS — All 8 parse_args add size/--show/--yes/--smoke, but the non-TTY guard is `elif args.size is None and not sys.stdin.isatty()`, so a run with flag-only arguments (e.g. `pi.py --show` or `fib.py --yes`) at a terminal still falls through to the interactive input() prompt; the contract holds for SIZE or --smoke, not for 'any argument'.
- R1 -> Each of the 8 Python CLIs accepts `SIZE`, `--show`, `--yes` and `--smoke`; given `SIZE` or `--smoke` it never reads stdin, and with neither it prompts only when stdin is a terminal (else exits 2). — flag-only runs at a terminal (`pi.py --show`) prompting for SIZE is the intended interactive mode and is what the READMEs document; the never-reads-stdin guarantee is for runs that name a size.
- finding R2 (2026-10-25, reviewer A): DIFFERS — The file is always written and the full result goes to stdout only under `if args.show:`, but pi and e keep their unchanged digit-preview branch (show_pi_preview/show_e_preview, which the tests have to mock), so a truncated result still reaches stdout without --show; the other 6 programs gate result lines on args.show.
- R2 -> A Python CLI given `SIZE` writes its output file, prints its result lines to stdout only with `--show`, and exits 0; pi and e keep their 100-digit preview, which is not a result line. — the preview predates the contract and the harness confirms the full result line never reaches stdout without `--show`.
- finding R6 (2026-10-25, reviewer A): DIFFERS — It imports the module for SMOKE_SIZE/LARGE_RUN_THRESHOLD, uses an open never-closed pipe, CASE_TIMEOUT 60 / REFUSAL_TIMEOUT 5, and exits 1 printing 'case N (label): problem' per failure; but case 4 ('y on stdin') writes "y\n" into the pipe, so stdin is not 'never-written' for every case (the Design 2 matrix itself was not available to check the case list).
- R6 -> `scripts/cli_contract.py` reads `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD` from the module, runs the Design 2 matrix with stdin an `os.pipe()` whose write end stays open for the whole run and is written to only in the `y`-on-stdin case, a 60 s timeout (5 s for the refusal case), and exits non-zero naming each failing case. — Design 2's own matrix includes the `y`-on-stdin case; "never-written" described every other case.
- finding R9 (2026-10-25, reviewer both): NOT-BUILT — The diff contains no typings/gmpy2/__init__.pyi, no pyrightconfig.json change (no stubPath, no mode change for e/pi), and no pyright-related edit at all.
- R9 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R10 (2026-10-25, reviewer both): NOT-BUILT — No scripts/crate_templates/python/ files, no renderer change, no install_deps.sh or cosmic-ray.toml change, and no tests/test_crate_uniformity.py change appear in the diff; the Makefiles and workflows are hand-edited.
- R10 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R11 (2026-10-25, reviewer both): NOT-BUILT — The benchmark: targets remain (amicable, e, pi, sq Makefiles edit them, e.g. amicable's to `timeout 30 python3 amicable.py 5`), no *-py.yml step is removed, and TestBenchmarkGatesCanFail is not touched.
- R11 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R12 (2026-10-25, reviewer both): NOT-BUILT — No installer, workflow install step, or tests/test_tool_pins.py change appears in the diff.
- R12 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R13 (2026-10-25, reviewer both): NOT-BUILT — The *-py.yml hunks add only two paths: entries; no test-metrics-<p>-py publishing step is added.
- R13 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R14 (2026-10-25, reviewer both): NOT-BUILT — No cosmic-ray.toml file is in the diff.
- R14 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R15 (2026-10-25, reviewer both): NOT-BUILT — .github/workflows/scripts.yml is not in the diff.
- R15 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R17 (2026-10-25, reviewer A): DIFFERS — The mocked --yes tests in pi, e and fib assert calc called with _LARGE (fib: 10**_LARGE), and seven constant tests pin literals, but e's test_large_run_threshold is `assertEqual(LARGE_RUN_THRESHOLD, _LARGE)` where _LARGE is LARGE_RUN_THRESHOLD, a tautology; e's 1_000_001 is pinned only indirectly by the boundary tests at 1000000/1000001.
- R17 reviewed: fixed in 7117d87
- finding R18 (2026-10-25, reviewer both): NOT-BUILT — The root CLAUDE.md hunk changes only the pre-push line; the Notes bullet saying output files are 'written by `make benchmark` too' is not edited.
- R18 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R9 (2026-10-25, reviewer both): NOT-BUILT — Looked for typings/gmpy2/__init__.pyi, stubPath edits to any pyrightconfig.json and an e/pi mode change; none appear in the diff.
- R9 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R10 (2026-10-25, reviewer both): NOT-BUILT — No scripts/crate_templates/python/ files, renderer change, install_deps.sh or cosmic-ray.toml change, or tests/test_crate_uniformity.py change appear; the Makefiles and workflows are hand-edited.
- R10 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R11 (2026-10-25, reviewer both): NOT-BUILT — benchmark: targets remain and are edited in amicable, e, pi and sq Makefiles (e.g. `timeout 30 python3 amicable.py 5`), no *-py.yml Benchmark step is removed, and TestBenchmarkGatesCanFail is untouched.
- R11 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R12 (2026-10-25, reviewer both): NOT-BUILT — No installer, workflow install step or tests/test_tool_pins.py change appears in the diff.
- R12 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R13 (2026-10-25, reviewer both): NOT-BUILT — The *-py.yml hunks add only two paths: entries; no test-metrics-<p>-py publishing step is added.
- R13 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R14 (2026-10-25, reviewer both): NOT-BUILT — No cosmic-ray.toml file is in the diff.
- R14 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R15 (2026-10-25, reviewer both): NOT-BUILT — .github/workflows/scripts.yml is not in the diff.
- R15 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- finding R18 (2026-10-25, reviewer both): NOT-BUILT — The root CLAUDE.md hunk edits only the pre-push line; no edit removes the 'written by `make benchmark` too' Notes text.
- R18 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.

## Spec alignment (2026-10-25)

- spec: docs/superpowers/specs/2026-10-25-uniform-project-cli-and-python-files-design.md
- anchor: 95a4378893327f6f1b7143e2a5cc67767ceb5cfc
- in scope: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15, R16, R17, R18
- out of scope: none

### Findings

| ID | Reviewer | Verdict | Reason | Amendment |
| --- | --- | --- | --- | --- |
| R9 | both | NOT-BUILT | Looked for typings/gmpy2/__init__.pyi, stubPath edits to any pyrightconfig.json and an e/pi mode change; none appear in the diff. | - R9 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence. |
| R10 | both | NOT-BUILT | No scripts/crate_templates/python/ files, renderer change, install_deps.sh or cosmic-ray.toml change, or tests/test_crate_uniformity.py change appear; the Makefiles and workflows are hand-edited. | - R10 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence. |
| R11 | both | NOT-BUILT | benchmark: targets remain and are edited in amicable, e, pi and sq Makefiles (e.g. `timeout 30 python3 amicable.py 5`), no *-py.yml Benchmark step is removed, and TestBenchmarkGatesCanFail is untouched. | - R11 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence. |
| R12 | both | NOT-BUILT | No installer, workflow install step or tests/test_tool_pins.py change appears in the diff. | - R12 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence. |
| R13 | both | NOT-BUILT | The *-py.yml hunks add only two paths: entries; no test-metrics-<p>-py publishing step is added. | - R13 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence. |
| R14 | both | NOT-BUILT | No cosmic-ray.toml file is in the diff. | - R14 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence. |
| R15 | both | NOT-BUILT | .github/workflows/scripts.yml is not in the diff. | - R15 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence. |
| R18 | both | NOT-BUILT | The root CLAUDE.md hunk edits only the pre-push line; no edit removes the 'written by `make benchmark` too' Notes text. | - R18 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence. |

### Reviewed

- R9 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R10 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R11 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R12 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R13 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R14 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R15 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R17 reviewed: fixed in 7117d87
- R18 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R9 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R10 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R11 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R12 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R13 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R14 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R15 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.
- R18 reviewed: `[P2]`/`[P3]` requirement, delivered by PR 2 or PR 3 of the plan; this branch is PR 1 (P1) and the plan runs the three PRs in sequence.

### Verifications

- V1: no evidence recorded
- V2: no evidence recorded
- V3: no evidence recorded
