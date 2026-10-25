# One CLI contract and uniform project files for the 8 Python sub-projects

**Status:** Draft, revision 2, 2026-10-25. Design sections approved in conversation by the
operator; revision 2 applies the operator's dispositions on the round-1 Multi-Lens Review
(below): Rust CLIs deferred, per-project contract test with an open pipe, a vendored gmpy2
stub, and five smaller corrections.

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
- Large-run thresholds stay as they are (pi and e: more than 1,000,000 digits; fib: X >= 4; the
  other 5 have none). Above the threshold without `--yes`, the program exits 1 and names
  `--yes`; with `--yes` it proceeds. A program with no threshold accepts `--yes` and ignores it.
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

Every Python project's Makefile then has the identical recipe
`smoke:` -> `timeout 60 python3 @MODULE@.py --smoke`, replacing `benchmark:` (the name `bench`
stays the Rust Criterion target).

### 2. Contract test, run by each project

- One shared harness, `scripts/cli_contract.py <module.py>`, runs a program as a subprocess
  against one matrix and exits non-zero naming every failing case. Each run uses a fresh temp
  working directory, and stdin is an open pipe that is never written to, with a 60 s timeout:
  a program that reads stdin blocks and fails on the timeout instead of reading end of input
  as no.
- Cases: `SIZE` (the program's `SMOKE_SIZE`) writes a non-empty output file, prints nothing
  that looks like a prompt (`?`, `(y/n)`), and exits 0; `SIZE --show` prints at least one
  result line from the output file to stdout; `--smoke` behaves like `SIZE` at `SMOKE_SIZE`;
  for pi, e and fib, a size above the threshold without `--yes` exits 1 naming `--yes`, and
  with `--yes` proceeds (exit 0 and a non-empty file); `y` written to stdin with `SIZE` still
  shows nothing; no arguments with stdin not a TTY exits 2.
- Each project's `make test` runs pytest and then the harness against its own program, so the
  PR that changes `pi/pi.py` runs pi's contract in `pi-py.yml` (paths `pi/*.py`) with pi's
  dependencies installed, and pre-push runs it on any `.py` change in that project.
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
  workflows and installers carries one exact version repo-wide, chosen as the newest release at
  least two weeks old; `tests/test_tool_pins.py` is extended to require it.
- **pyright `standard` for all 8.** A repo-root `typings/gmpy2/__init__.pyi` types exactly the
  names the code and tests use (`mpfr`, `mpz`, `get_context`, `sqrt`, `version`, `mp_version`,
  `mpfr_version`) without `Any`, and e and pi narrow their optional import with
  `_gmpy2 is not None` rather than a separate flag. Every `pyrightconfig.json` points
  `stubPath` at `../typings`. A test fails if the stub contains `Any`.
- **Test metrics** for all 8 Python workflows, extending factorial's pilot (as math#169 did for
  Rust).
- **cosmic-ray:** `timeout = 60` in every project, so the file is identical after substitution.

### 4. Delivery

- **P1** CLI contract for the 8 Python CLIs, the shared harness and its tests, each project's
  `make test` running it.
- **P2** the gmpy2 stub and pyright `standard` for e and pi.
- **P3** Python templates, pinned libraries, test metrics and the `smoke` recipe (depends on P1
  and P2).

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
- **R3.** `[P1]` pi and e given more than 1,000,000 digits, and fib given X >= 4, exit 1 naming `--yes` when `--yes` is absent, and proceed when it is present.
- **R4.** `[P1]` Each Python CLI defines a module-level `SMOKE_SIZE` equal to its benchmark size on master `f7658ed` (amicable 5, collatz 5, e 10000, factorial 1000, fib 3, perfect-numbers 6, pi 10000, sq 1), and `--smoke` runs at that size.
- **R5.** `[P1]` A Python CLI run with no arguments and stdin not a TTY exits 2 with usage.
- **R6.** `[P1]` `scripts/cli_contract.py` runs the Design 2 matrix with stdin an open, never-written pipe and a 60 s timeout, and exits non-zero naming each failing case.
- **R7.** `[P1]` `tests/test_cli_contract_harness.py` shows the harness failing a stub that prompts, one that writes no output, and one that ignores `--yes`, and passing a conforming stub.
- **R8.** `[P1]` Each Python project's `make test` runs the harness against its own program after pytest.
- **R9.** `[P2]` A repo-root `typings/gmpy2/__init__.pyi` contains no `Any`, every Python `pyrightconfig.json` sets `stubPath` to `../typings`, and e and pi pass pyright `standard` with 0 errors and no `reportAttributeAccessIssue` or `reportOptionalMemberAccess` override.
- **R10.** `[P3]` `<p>/Makefile`, `<p>/install_deps.sh`, `.github/workflows/<p>-py.yml`, `<p>/pyrightconfig.json` and `<p>/cosmic-ray.toml` for the 8 projects are rendered from `scripts/crate_templates/python/` with only `@CRATE@` and `@MODULE@` substituted, and `tests/test_crate_uniformity.py` fails on any drift.
- **R11.** `[P3]` Every Python Makefile has `smoke:` running `timeout 60 python3 @MODULE@.py --smoke` and no `benchmark:` target.
- **R12.** `[P3]` All 8 Python installers and workflows install GMP, MPFR, gmpy2 and mpmath, and every pip-installed package in them carries an exact `==` version, one version per package repo-wide, enforced by `tests/test_tool_pins.py`.
- **R13.** `[P3]` All 8 Python workflows publish `test-metrics-<p>-py`.
- **R14.** `[P3]` Every `cosmic-ray.toml` sets `timeout = 60`.
- **R15.** `[P3]` `.github/workflows/scripts.yml` triggers on every path the renderer writes.
- **V1.** Each PR's CI is green with every affected project's workflow run; the PR body lists them.
- **V2.** Every Python sub-project's coverage stays at or above 90% on CI after each PR.
- **V3.** After P3, `make smoke` and `make test` pass for all 8 Python projects in a clean copy of master on `claude`.
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
