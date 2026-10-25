# One CLI contract for all 19 programs, and uniform Python project files

**Status:** Draft, 2026-10-25. Design sections approved in conversation by the operator
(scope "All 19, one spec, Python first"; contract "Yes"; files, delivery and testing "Yes").

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

1. **The CLIs behave differently.** Each Python CLI takes one positional argument, but they prompt
   at different points after the work: e and pi ask "Continue with N digits?" above 1,000,000
   digits (only interactively; with an argument they warn and continue) and "Display all?";
   fib confirms at X >= 4 even with an argument; sq asks whether to display. So three of the
   eight benchmark recipes must pipe `printf "n\n" |` into the program, and each passes a
   different size (amicable 5, collatz 5, e 10000, factorial 1000, fib 3, perfect-numbers 6,
   pi 10000, sq 1). The Rust binaries prompt the same way: `pi-rs`, `e-rs`, `fib-rs` and
   `sq-rs` call `read_line` 12-14 times each (`grep -c read_line <crate>/src/main.rs`).
2. **Type checking differs.** e and pi run pyright `basic` with `reportAttributeAccessIssue`
   and `reportOptionalMemberAccess` off, because gmpy2 has no type stubs; the other 6 run
   `standard`.

Installed libraries also differ (only pi, e and factorial install gmpy2 and mpmath), and only
factorial publishes Python test metrics.

## Design

### 1. One CLI contract for every program

Applies to all 19 programs: the 8 Python CLIs and the 11 Rust binaries.

```
<prog> SIZE [--show] [--yes]    # never prompts
<prog> --benchmark              # never prompts; runs the program's own BENCHMARK_SIZE
<prog>                          # interactive prompt only when stdin is a TTY, else exit 2
```

- `SIZE` is the single positional argument. Its meaning stays per program (exponent N for
  amicable, collatz, fib, goldbach, perfect-numbers, prime, sq and twin-primes; digit count for
  e and pi; n for factorial) and is stated in `--help`. Keeping the meaning avoids rewriting the
  mathematics and its tests.
- With arguments a program never reads stdin. Results always go to the output file. `--show`
  additionally prints them, replacing every "Display all?" prompt.
- Each program keeps its existing large-run threshold (pi and e: more than 1,000,000 digits;
  fib: X >= 4; Rust binaries: the same threshold as their Python twin, and for prime,
  twin-primes and goldbach the threshold their binary uses today, or none). Above it, without
  `--yes`, the program exits 1 and names `--yes`; with `--yes` it proceeds. A program with no
  threshold accepts `--yes` and ignores it.
- `--benchmark` runs at a module- or crate-level constant `BENCHMARK_SIZE`. For the 8 Python
  programs and their Rust twins it is today's benchmark size (above); for prime, twin-primes and
  goldbach it is chosen in the plan as the largest size that finishes in under 10 s on an
  ubuntu-latest runner. `--benchmark` never needs `--yes` (`BENCHMARK_SIZE` is below every
  threshold) and never shows.
- With no arguments and stdin a TTY, the program keeps its interactive prompt; at the end of
  input a y/n prompt reads as no and a number prompt exits 1 naming the argument to pass (the
  math#161 behaviour). With no arguments and stdin not a TTY, it exits 2 with usage.
- Exit codes everywhere: 0 success (including a run declined interactively), 1 invalid input,
  I/O failure or a refused large run, 2 usage error.
- Output file names are unchanged (`pi_*_digits.txt`, `e_*_digits.txt`, `factorial_*.txt`,
  `<name>_1e*.txt`).

Every project's Makefile then has the identical benchmark recipe:
`timeout 60 python3 @MODULE@.py --benchmark` (Python) and
`timeout 60 cargo run --release -- --benchmark` (Rust).

### 2. Per-project Python files rendered from templates

- Five new template kinds in `scripts/crate_templates/python/`, rendered for the 8 Python
  projects: `Makefile` -> `<p>/Makefile`, `install_deps.sh` -> `<p>/install_deps.sh`,
  `py.yml` -> `.github/workflows/<p>-py.yml`, `pyrightconfig.json` -> `<p>/pyrightconfig.json`,
  `cosmic-ray.toml` -> `<p>/cosmic-ray.toml`.
- `render_crate_files.py` gains a second project list (`PYTHON_PROJECTS`, the 8) and a second
  placeholder, `@MODULE@`, derived from the directory name with `-` replaced by `_`
  (`perfect-numbers` -> `perfect_numbers`). Any other `@NAME@` stays an error.
  `test_crate_uniformity.py` covers the new kinds, and `scripts.yml` triggers on every rendered
  path.
- **Libraries:** all 8 install the same set: GMP and MPFR system libraries, and gmpy2 and mpmath
  in Python, following the operator's Rust choice (math#168). Every pip-installed package in the
  Python workflows and installers is pinned to one version repo-wide (ruff and pyright already
  are; pytest, pytest-cov, coverage, hypothesis, pip-audit, cosmic-ray, gmpy2 and mpmath join
  them), chosen as the newest release at least two weeks old, and `tests/test_tool_pins.py` is
  extended to require it.
- **pyright `standard` for all 8.** e and pi stop using `basic`: their gmpy2 uses go through
  small typed helpers in the module (for example a function returning `int` or `str` around the
  gmpy2 call), so pyright sees typed values. No suppression is added to any config.
- **Test metrics** for all 8 Python workflows, extending factorial's `time_tests.py` pilot as
  the Rust side did (math#169).
- **cosmic-ray:** the per-project parts of `cosmic-ray.toml` that are mutation exclusions move
  into the source as `# pragma: no mutate` on the lines they cover, so the config is identical.
  Any per-project setting that cannot move is a defect to resolve in the plan, not a template
  parameter.

### 3. Delivery

Two PR series, Python first. Each PR keeps master green on its own.

- **P1** CLI contract for the 8 Python CLIs, with the shared contract test.
- **P2** pyright `standard` for e and pi.
- **P3** Python templates, pinned libraries and test metrics (depends on P1 for the identical
  benchmark line, and on P2 for the identical pyright config).
- **R1** CLI contract for the 11 Rust binaries; the shared contract test covers them.
- **R2** a `benchmark:` target in the Rust Makefile template running `--benchmark`.

### 4. Testing

- `tests/test_cli_contract.py` runs every program as a subprocess with stdin closed, against one
  matrix: `SIZE` writes the output file, prompts nothing and exits 0; `--show` also prints the
  result; a size above the threshold without `--yes` exits 1 naming `--yes` (programs with a
  threshold); `--benchmark` exits 0 within its 60 s timeout and writes its output file; no
  arguments exits 2. Each case asserts a concrete artifact (the output file exists and is
  non-empty), not only an exit code. It covers the 8 Python programs from P1 and the 11 Rust
  binaries from R1, built once per test run.
- Each project keeps its own unit tests; changed functions get boundary, error-path and
  state-transition tests per the repo's TDD rule, written RED first.
- Coverage stays at or above 90% per sub-project.

## Requirements

- **R1.** `[P1]` Each of the 8 Python CLIs accepts `SIZE`, `--show`, `--yes` and `--benchmark` and, with any argument, never reads stdin.
- **R2.** `[P1]` A Python CLI given `SIZE` writes its output file, prints the results only with `--show`, and exits 0.
- **R3.** `[P1]` pi and e given more than 1,000,000 digits, and fib given X >= 4, exit 1 and name `--yes` when `--yes` is absent, and proceed when it is present.
- **R4.** `[P1]` Each Python CLI defines a module-level `BENCHMARK_SIZE` equal to its benchmark size on master `f7658ed` (amicable 5, collatz 5, e 10000, factorial 1000, fib 3, perfect-numbers 6, pi 10000, sq 1), and `--benchmark` runs at that size without prompting.
- **R5.** `[P1]` A Python CLI run with no arguments and stdin not a TTY exits 2 with usage; with no arguments and stdin a TTY it prompts as today.
- **R6.** `[P1]` `tests/test_cli_contract.py` runs the R1-R5 matrix as subprocesses for every Python CLI, asserting a non-empty output file for each `SIZE` and `--benchmark` case.
- **R7.** `[P2]` `e/pyrightconfig.json` and `pi/pyrightconfig.json` use `typeCheckingMode` `standard` with no `reportAttributeAccessIssue` or `reportOptionalMemberAccess` override, and pyright reports 0 errors in both.
- **R8.** `[P3]` `<p>/Makefile`, `<p>/install_deps.sh`, `.github/workflows/<p>-py.yml`, `<p>/pyrightconfig.json` and `<p>/cosmic-ray.toml` for the 8 Python projects are rendered from `scripts/crate_templates/python/` with only `@CRATE@` and `@MODULE@` substituted, and `tests/test_crate_uniformity.py` fails on any drift.
- **R9.** `[P3]` Every Python project's Makefile benchmark recipe is `timeout 60 python3 @MODULE@.py --benchmark`.
- **R10.** `[P3]` All 8 Python installers and workflows install GMP, MPFR, gmpy2 and mpmath, and every pip-installed package in them carries an exact `==` version, one version per package repo-wide, enforced by `tests/test_tool_pins.py`.
- **R11.** `[P3]` All 8 Python workflows publish `test-metrics-<p>-py`.
- **R12.** `[P3]` `cosmic-ray.toml` is identical across the 8 projects after substitution; per-project mutation exclusions are `# pragma: no mutate` comments in the source.
- **R13.** `[P3]` `.github/workflows/scripts.yml` triggers on every path the renderer writes.
- **R14.** `[R1]` Each of the 11 Rust binaries meets R1-R5 with a crate-level `BENCHMARK_SIZE`; the 8 with a Python twin use the twin's size, and prime, twin-primes and goldbach use the largest size that finishes in under 10 s on ubuntu-latest.
- **R15.** `[R1]` `tests/test_cli_contract.py` runs the same matrix against the 11 Rust binaries.
- **R16.** `[R2]` The Rust Makefile template has a `benchmark:` target running `timeout 60 cargo run --release -- --benchmark`.
- **V1.** Each PR's CI is green with every affected project's workflow run; the PR body lists them.
- **V2.** Every Python and Rust sub-project's coverage stays at or above 90% on CI after each PR.
- **V3.** After P3 and R2, `make benchmark` passes in a clean copy of master for all 19 programs on `claude`.
- **N1.** No output file is renamed.
- **N2.** No program changes what `SIZE` means.
- **N3.** No pyright suppression is added to any `pyrightconfig.json`.
- **N4.** No per-project template parameter beyond `@CRATE@` and `@MODULE@`.
- **N5.** No coverage floor is lowered.
