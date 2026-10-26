# Uniform Rust CLI Contract and Cargo.toml Shape for the 11 Crates

- **Date:** 2026-10-25
- **Status:** Draft
- **Related:**
  - ADR-0030 (one CLI contract for the Python programs);
  - ADR-0032 (per-project files rendered from templates);
  - spec `2026-10-25-uniform-project-cli-and-python-files-design.md`, which deferred the Rust half;
  - Backlog row "Uniform CLI contract for the 11 Rust binaries".

## Problem

The operator rule (2026-10-24) is that all 11 projects are treated the same, all of the time.
The 8 Python programs now share one CLI contract, checked by `scripts/cli_contract.py`
(math#171). The 11 Rust binaries do not, and their `Cargo.toml` files are hand-maintained.

Measured on master `d79192c` by reading every `src/main.rs`, `src/lib.rs` and `Cargo.toml`:

- **Interactive prompts remain.** 9 of the 11 binaries still have `read_line` calls:
  pi 12, e 12, fib 14, sq 13, prime 12, factorial 10, perfect-numbers 3, goldbach 1, collatz 1;
  twin-primes and amicable have 0. A run with no argument waits on stdin, the defect ADR-0030
  removed from the Python programs.
- **Argument handling differs.** factorial parses its arguments by hand. The other 10 use
  clap, but their positional argument has four different names (`n`, `exponent`, `digits`, `N`)
  and differing optionality: amicable and twin-primes require it, the other 8 take an `Option`.
- **`Cargo.toml` differs where it should not.**
  - sq has no `[profile.release]`, so its release build lacks the `lto = "thin"` and
    `codegen-units = 1` the other 10 use.
  - factorial has no `clap` dependency.
  - The profile lines are formatted three ways.

  The `[dependencies]` tables differ legitimately (`rug`, `rayon`, `clap` features).
- **Local tests run one crate at a time, or not at all.**
  - `scripts/pre-push` runs `make -C <dir> test` for each changed sub-project in turn.
  - With more than 6 changed sub-projects it skips every local suite ("too many for macOS
    process isolation") and leaves the push to CI. P2, which changes all 11 crates, would push
    with no local test run.
  - No root target tests all 11 crates. Within a crate, cargo and nextest already use every core.
- **Two binaries deadlocked; fixed separately.** pi-rs, prime-rs and e-rs held `stderr.lock()` in
  `main()` while a progress thread called `eprint!`, so any run whose compute outlasted the first
  200 ms tick hung (`pi 5000000`, `prime 9`). math#175 fixed it before this spec's work began. The
  other 8 crates still lock stderr in `main()` but spawn no printing thread.
- **Fixed separately while this spec was in review.**
  - math#176: progress threads slept 200 ms before checking whether work was done, so pi's and
    e's 256-case property test took 51 s.
  - math#177: CI compiled nextest, tarpaulin and machete from source in every job, about 490 s
    of an 884 s test job. Tools are now prebuilt, coverage runs as a parallel job, and bats runs
    in parallel.
- **No test is bounded in time.** `.config/nextest.toml` (rendered from
  `scripts/crate_templates/nextest.toml`) sets no `slow-timeout`. The 51 s test passed for five
  months, and a mutation that deleted a progress thread's shutdown signal hung every affected
  test until it was killed. In CI that would wait for GitHub's 360-minute job timeout.
- **Two crates have no crate `CLAUDE.md`.** pi-rs and prime-rs are documented in
  `pi/CLAUDE.md` and `prime/CLAUDE.md`; the other 9 crates have `<crate>-rs/CLAUDE.md`.

The deferred Backlog row said the contract "needs a consumer first, such as a contract-smoke step
in CI". This spec supplies that consumer: the rendered Rust Makefile's `test` target, which every
`<crate>-rs.yml` CI job runs.

## Design

### Contract

The contract is ADR-0030's, applied unchanged to every Rust binary.

- `<bin> SIZE [--show] [--yes]` runs at SIZE and never reads stdin.
- `<bin> --smoke` runs at `SMOKE_SIZE`.
- With `LARGE_RUN_THRESHOLD` set, a SIZE at or above it without `--yes` exits 1 with a message
  naming `--yes`, before writing any file. With `--yes`, or below the threshold, the run proceeds.
- With no arguments and a stdin that is not a terminal (`std::io::IsTerminal`), the binary prints
  clap's usage and exits 2.
- With no arguments and a terminal stdin, it asks once for SIZE.
  - On EOF it prints an empty line, then
    `Error: no input; pass SIZE as an argument (e.g. <bin> <SMOKE_SIZE>).`, and exits 1.
  - An answer that fails validation exits 1 with the same validation message as the argument path.
- `--show` prints the result lines before the summary. Without it, no result line reaches stdout.
- SIZE keeps its current meaning in every crate:
  - digits for pi and e;
  - n for factorial;
  - the exponent N of 10^N for the other 8.

  Existing range checks stay.

Each crate's `src/lib.rs` declares two constants, and a test in that crate pins both:

```rust
pub const SMOKE_SIZE: u64 = 10_000;
pub const LARGE_RUN_THRESHOLD: Option<u64> = Some(100_000_001);
```

The type is `u64` in every crate; each `main.rs` converts it to its own SIZE type.

**In-process shape.** Each crate's CLI logic lives in one function, called by a thin `main()`:

```rust
pub fn run(
    cli: Cli,
    stdin_is_tty: bool,
    input: impl BufRead,
    out: impl Write,
    err: impl Write,
    dir: &Path,
) -> i32
```

All 11 crates' current `run` already takes `err` and an output directory (amicable takes the output
path), so tests stay hermetic: files go to a temp dir and stderr is a buffer.

`main()` parses `Cli` and passes:
- `std::io::stdin().is_terminal()` and the locked stdin;
- unlocked `std::io::stdout()` and `std::io::stderr()`, which lock per write;
- the current directory.

It then exits with the returned code. Holding a lock across `run` is the math#175 deadlock wherever
a thread prints. It stays excluded from coverage (`tarpaulin_include`), as `main()`
is in all 11 crates today. Unit tests call `run` directly for every contract path, including the
terminal prompt and its EOF, which the subprocess harness cannot reach.

This keeps coverage measurable. CI runs `cargo tarpaulin` without `--follow-exec`, so tests that
spawn the binary add no coverage. Today the 9 prompting crates get their `main.rs` coverage from
in-process `io::Cursor` tests, which R14 removes.

**SMOKE_SIZE values:**

| Crates | SMOKE_SIZE |
| ------ | ---------- |
| amicable, collatz | 5 |
| e, pi | 10000 |
| factorial | 1000 |
| fib | 3 |
| perfect-numbers | 6 |
| sq | 1 |
| prime, goldbach, twin-primes | 3 |

The first 8 equal their Python twins (ADR-0030). The Rust-only crates have no benchmark recipe to
borrow from, and 3 is valid in all three ranges.

**LARGE_RUN_THRESHOLD** is set per binary from a measurement on `claude`, taken after that binary's
rewrite in its own P2 task, so the measured code is the code that ships.
- **Definition:** the smallest SIZE whose release-build run takes more than 60 s wall-clock or
  8 GiB maximum resident memory, or `None` when the crate's own range check rejects every SIZE
  that large.
- **Probe:** each run uses `timeout 61` and `/usr/bin/time -v`, which reports wall-clock, maximum
  resident set size and CPU time. There is no `ulimit -v`: it caps virtual size, and the rayon crates
  reserve several GiB of address space at small sizes (`pi 100000` measured at 3.38 GB virtual on
  48 threads).
- **Evidence for a timed-out probe:** the probe must show CPU time near 61 s × the thread count it
  used, so a hang cannot pass as a slow run.

The task records SIZE, wall-clock, max RSS and CPU time as an amendment and pins the value in R4's
test.

### One harness

`scripts/cli_contract.py` gains a Rust mode, `cli_contract.py --rust <crate-dir>`:

- **Constants.** It reads `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD` from `<crate-dir>/src/lib.rs`
  with a strict pattern for the two declarations above. A missing, duplicated or unparsable
  declaration raises `ContractConfigError`, which exits 2.
- **Program.** It runs `<target-dir>/debug/<crate>`, with `<target-dir>` taken from
  `cargo metadata --format-version 1 --no-deps` so an exported `CARGO_TARGET_DIR` is honoured.
  The rendered `test` target runs `cargo build` immediately before the harness, so the binary is
  always built from the tree under test. Freshness must not depend on cargo building binaries only
  for integration tests. A missing binary exits 2 and names `cargo build`.
- **Cases.** The six-case matrix, its checks, the open-stdin pipe, the process-group kill and the
  concurrency are unchanged. Only the argv prefix differs between the two modes.

The Python mode's interface (`cli_contract.py <module.py>`) is unchanged.

**The consumer.** `scripts/crate_templates/Makefile`'s `test` target runs `../../scripts/rust-check.sh
test`, then `cargo build`, then `python3 ../../scripts/cli_contract.py --rust .`. It is
rendered into all 11 crate Makefiles, so every `<crate>-rs.yml` CI job runs it. 

The pre-push hook's `RUN_CLI_CONTRACT` arm runs on pushes that touch `scripts/cli_contract.py`.
It adds `tests/test_cli_contract_harness.py`, which covers both modes with fixture programs, and
still runs the harness over the 8 Python CLIs. It does not run the 11 binaries:
- a push that touches only the harness has built nothing;
- in a fresh worktree there is no binary to run;
- in an old worktree the binary is stale.

The 11 binaries are checked where they are built fresh: each crate's `make test` in CI.

### `Cargo.toml` shape

`tests/test_crate_uniformity.py` parses all 11 `Cargo.toml` files with `tomllib` and requires:

- the same `[package]` keys and values in all 11, apart from `name` and `description`;
- `name` equal to the crate directory without `-rs`;
- identical `[profile.release]`, `[lints.rust]`, `[lints.clippy]` and `[dev-dependencies]` tables;
- exactly one `[[bin]]`, named after the directory;
- a `clap` entry in `[dependencies]` with the same version and `features` in all 11.

Other `[dependencies]` entries may differ.

The fixes:

- sq gains the shared `[profile.release]`;
- factorial gains clap (its CLI rewrite is in P2);
- the profile formatting converges.

### Parallel local tests

**Pre-push.** `scripts/pre-push` runs the changed sub-projects' `make test` concurrently:
- `xargs -P "${PRE_PUSH_JOBS:-8}"`, each run with `< /dev/null`;
- each sub-project's output goes to its own log file in a temp directory;
- each job writes its own exit status to a status file, and the hook reads those files rather than
  xargs's exit code. xargs reports 123, 124 or 125 for different child failures, and stops
  starting new jobs on 255.
- a sub-project with no status file counts as `FAIL` (a killed or crashed job);
- the hook prints one `ok`/`FAIL` line per sub-project and each failing log in full, then exits 1
  if any failed.

The hook's `set -e` must not abort before the logs print.

The job count is fixed rather than `$(nproc)`, because the suites already fan out inside
themselves through `ProcessPoolExecutor` and rayon. The default is 8: every development machine is
workstation-class (`claude` has 48 threads, the Studio 20).

**The "more than 6 changed: skip" rule is removed, on a measurement.** It existed for a macOS
`resource_tracker` hang (`aba0ac2`). On the Mac Studio (macOS 27.0.1, Python 3.14.8), on a clean
clone of master `7ebf29b`, the 8 Python suites ran 4 at a time:
- no suite hung (exit 124 never occurred), and the whole run took 9 s;
- 0 `resource_tracker` processes remained afterwards;
- the only failures were pi and e. They failed run alone too, and were a separate spawn-precision
  bug, fixed in math#174.

On `claude`, all 11 crates' `make test` ran 4 at a time from a cold `CARGO_HOME` in 99 s.

Concurrent cargo runs share the per-checkout `CARGO_HOME`; cargo's own package-cache lock
serialises the downloads, which is the intended behaviour, not a deadlock.

**Root target.** A root `make test-rust` runs all 11 crates' `make test` the same way, with
`JOBS` defaulting to 8.

The CI layout is unchanged: each crate already runs as its own concurrent workflow.

### System GMP and MPFR

The 5 `rug` crates (e, factorial, fib, perfect-numbers, pi) build GMP and MPFR from C source
through `gmp-mpfr-sys` on every cold build: each new worktree, each cleared `.cache`, each CI cache
miss. The C libraries are already present everywhere this code builds:
- every crate's `install_deps.sh` installs them (Homebrew, apt or dnf/yum);
- every `<crate>-rs.yml` installs `libgmp-dev` and `libmpfr-dev`.

P1 enables `gmp-mpfr-sys`'s `use-system-libs` feature in those 5 crates, so the build links the
installed libraries instead of compiling them. It ships only if cold-build time and `make test` are
measured before and after on `claude` and on the Mac Studio, and both platforms build and pass. If
either platform cannot link the system libraries (a version mismatch, or a Homebrew path cargo does
not find), P1 records the failure in an amendment and drops this change rather than adding
platform-specific configuration.

### Bounded tests

The rendered `.config/nextest.toml` sets a `slow-timeout` with `terminate-after` on the default
profile, so the `ci` profile inherits it. A test that hangs, or runs far past the slowest test
today, then fails by name instead of passing slowly or hanging the job.

P1 sets the bound from measurements of the slowest test in each crate:
- on `claude` and on the Mac Studio, with nextest's slow-test reporting;
- on CI, from the `test-metrics-<crate>-rs` JUnit artifacts.

The bound must exceed the slowest measured test by at least 3×, and the measurements are recorded
as an amendment. `retries = 2` in the `ci` profile does not soften the bound: a hung test hangs on
every retry.

### Crate CLAUDE.md

pi-rs and prime-rs get `<crate>-rs/CLAUDE.md`, matching the other 9 crates:

- pi's Rust sections move out of `pi/CLAUDE.md`;
- `prime/CLAUDE.md` moves to `prime/prime-rs/CLAUDE.md`, leaving a pointer.

A test requires `<crate>-rs/CLAUDE.md` in all 11 crates.

## Delivery

| PR | Contents |
| -- | -------- |
| **P1** | The `Cargo.toml` shape test and the fixes it requires: sq's profile, factorial's clap entry, formatting. The crate `CLAUDE.md` test and the two moves. Concurrent pre-push sub-project tests and the root `make test-rust` target. System GMP and MPFR for the 5 `rug` crates. The nextest `slow-timeout` bound. |
| **P2** | Threshold measurements; harness Rust mode and its tests; the 11 CLI rewrites, each with its constants test; the Makefile template line rendered to 11; the pre-push arm; ADR-0033. |

P2 lands all 11 crates in one PR, so no window has some binaries on the contract and others off.
Its CLI rewrites are independent per-crate tasks that can run in parallel.

## Non-goal rationale

- **No Cargo workspace.** A root workspace would put the shared profile and lints in one place,
  but it replaces 11 `Cargo.lock` files with one and changes every Rust workflow, release
  workflow, `cargo-mutants` run and the Renovate config. The test-enforced shape gets uniformity
  without that churn.
- **`.cargo/mutants.toml` stays per-crate.** It exists in 4 crates and holds per-crate
  equivalent-mutant exclusions: data, not configuration.

### Mutation exclusions

Each `exclude_re` in the 4 `.cargo/mutants.toml` files pins a `src/<file>.rs:<line>:<col>`
position, and R4 and R14 move those lines. A stale pattern fails silently:
- the excluded mutant comes back as "missed";
- survivors are green in `mutation-classify.sh`, so no issue is filed.

P2 re-anchors every pattern after the rewrites and checks them with `cargo mutants --list`.

The rendered `mutants` recipe (`scripts/crate_templates/Makefile`) then checks the patterns before
every mutation run. It lists the mutants, verifies each `exclude_re` matches at least one, and
fails naming any stale pattern. Every mutation run therefore fails loudly instead of silently
re-admitting equivalents: the monthly workflow, `mutation-pr` and local `make mutants`.

A root test only placed on the push path would run where the drift does not happen. A `lib.rs`
edit runs only the crate suite, and `scripts.yml` does not install cargo-mutants.

## Requirements

- **R1.** `[P1]` `tests/test_crate_uniformity.py` fails when any of the 11 `Cargo.toml` files differs from the others in `[package]` keys and values (other than `name` and `description`), `[profile.release]`, `[lints.rust]`, `[lints.clippy]`, `[dev-dependencies]` or the `clap` dependency entry, or lacks exactly one `[[bin]]` named after its directory.
- **R2.** `[P1]` All 11 `Cargo.toml` files pass R1's test, including sq (gains the shared `[profile.release]`) and factorial (gains the shared `clap` entry).
- **R3.** `[P1]` Every crate has `<crate>-rs/CLAUDE.md`, a test requires it for all 11, and the Rust sections of `pi/CLAUDE.md` and the content of `prime/CLAUDE.md` move into `pi/pi-rs/CLAUDE.md` and `prime/prime-rs/CLAUDE.md`.
- **R4.** `[P2]` Every crate's `src/lib.rs` declares `pub const SMOKE_SIZE: u64` and `pub const LARGE_RUN_THRESHOLD: Option<u64>`, with the SMOKE_SIZE values in the Design table and the LARGE_RUN_THRESHOLD values recorded by R5, and a test in each crate pins both.
- **R5.** `[P2]` After each binary's rewrite, its LARGE_RUN_THRESHOLD is measured on `claude` as the smallest SIZE whose release run exceeds 60 s wall-clock or 8 GiB maximum resident memory, each probe under `timeout 61` and `/usr/bin/time -v` with no `ulimit -v`, a timed-out probe counting only when its CPU time shows it was computing, or `None` when the crate's range check rejects every such SIZE; each value is recorded as an amendment to this spec with SIZE, wall-clock, max RSS and CPU time.
- **R6.** `[P2]` Every binary accepts `SIZE [--show] [--yes]` and `--smoke`, never reads stdin when SIZE or `--smoke` is given, and refuses a SIZE at or above a non-`None` LARGE_RUN_THRESHOLD without `--yes` by exiting 1 before writing any file, with a message naming `--yes`.
- **R7.** `[P2]` With no arguments, every binary exits 2 with clap's usage when stdin is not a terminal; when it is a terminal, an EOF at the single prompt prints an empty line, then `Error: no input; pass SIZE as an argument (e.g. <bin> <SMOKE_SIZE>).`, and exits 1.
- **R8.** `[P2]` Without `--show` no result line reaches stdout; with `--show` the result lines print before the summary.
- **R9.** `[P2]` factorial parses its arguments with clap.
- **R10.** `[P2]` `scripts/cli_contract.py --rust <crate-dir>` reads both constants from `<crate-dir>/src/lib.rs`, resolves the target directory with `cargo metadata`, exits 2 on a missing, duplicated or unparsable declaration or a missing `<target-dir>/debug/<crate>`, and runs the same six-case matrix as the Python mode against that binary; the Python mode's interface is unchanged.
- **R11.** `[P2]` `tests/test_cli_contract_harness.py` covers the Rust mode with fixture binaries or scripts for a conforming program and for each failing case, plus each `ContractConfigError` path.
- **R12.** `[P2]` `scripts/crate_templates/Makefile`'s `test` target runs `rust-check.sh test`, then `cargo build`, then `python3 ../../scripts/cli_contract.py --rust .`, rendered to all 11 crate Makefiles, and a test requires `tests/cli.rs` in all 11 crates.
- **R13.** `[P2]` The pre-push `RUN_CLI_CONTRACT` arm also runs `tests/test_cli_contract_harness.py`, runs no Rust binary, and `tests/scripts/pre_push.bats` covers both facts.
- **R14.** `[P2]` The `read_line`-based prompt paths other than R7's single prompt are removed from all 11 binaries, together with the tests that drove them through `io::Cursor`; their behaviour is covered by tests of the new paths.
- **R15.** `[P2]` ADR-0033 records the Rust contract as an extension of ADR-0030, and root `CLAUDE.md`, each crate's `CLAUDE.md` and the root `README.md` CLI table describe the new usage.
- **R16.** `[P2]` Every crate's CLI logic is a `pub fn run(cli, stdin_is_tty: bool, input: impl BufRead, out: impl Write, err: impl Write, dir: &Path) -> i32` called by a coverage-excluded `main()` that passes unlocked stdout and stderr, with in-process unit tests of every R6-R8 path, including the terminal prompt and its EOF, writing only into a temp dir.
- **R17.** `[P2]` After the rewrites, every `exclude_re` in the 4 `.cargo/mutants.toml` files is re-anchored, and the rendered `mutants` recipe first verifies that each pattern matches at least one mutant listed by `cargo mutants --list`, failing with the stale pattern named; `tests/scripts/makefile.bats` covers a stale and a matching pattern.
- **R18.** `[P1]` `scripts/pre-push` runs the changed sub-projects' `make test` concurrently with `xargs -P "${PRE_PUSH_JOBS:-8}"`, stdin from `/dev/null`, one log and one status file per sub-project; a missing status file counts as FAIL; it prints one `ok`/`FAIL` line per sub-project and each failing log before exiting 1 if any failed, and no longer skips when more than 6 sub-projects changed; `tests/scripts/pre_push.bats` covers a pass, a single failure among several, a job killed before writing its status, and the 7-or-more case asserting all 7 `make` calls ran.
- **R19.** `[P1]` A root `make test-rust` target runs all 11 crates' `make test` concurrently with `JOBS` defaulting to 8, exits non-zero if any fails, and `tests/scripts/makefile.bats` covers it.
- **R20.** `[P1]` The 5 `rug` crates enable `gmp-mpfr-sys`'s `use-system-libs` feature through a `gmp-mpfr-sys` dependency entry identical in all 5 (R1's shape test covers it), so no build compiles GMP or MPFR from source; if `claude` or the Mac Studio cannot build with it, an amendment records why and the entry is not added.
- **R21.** `[P1]` `scripts/crate_templates/nextest.toml` sets `slow-timeout` with `terminate-after` on the default profile, rendered to all 11 crates, with a bound at least 3× the slowest test measured on `claude`, the Mac Studio and CI (recorded as an amendment), and `tests/test_crate_uniformity.py` or a new test fails if the bound is removed.
- **V1.** `[P2]` Every `<crate>-rs.yml` CI run on P2 is green with the harness step present in its log.
- **V2.** `[P1]` `cargo tarpaulin` coverage stays at or above 90% for every crate on Linux CI after P1.
- **V3.** `[P2]` `cargo tarpaulin` coverage stays at or above 90% for every crate on Linux CI after P2.
- **V4.** `[P2]` After P2, `make test` passes for all 11 crates in a clean clone of master on `claude`.
- **V5.** `[P1]` After P1, `make test` passes for all 8 Python projects and all 11 crates on the Mac Studio (login shell, clean copy of the merged tree).
- **V6.** `[P2]` After P2, `make test` passes for all 8 Python projects and all 11 crates on the Mac Studio (login shell, clean copy of the merged tree).
- **V7.** `[P1]` Cold `cargo build` and `make test` times for the 5 `rug` crates are recorded before and after R20 on `claude` and on the Mac Studio.
- **N1.** No output file is renamed.
- **N2.** No binary changes what SIZE means.
- **N3.** No Cargo workspace is introduced.
- **N4.** No `.cargo/mutants.toml` file or `exclude_re` exclusion is added or removed.
- **N5.** No coverage floor is lowered.
- **N6.** No Python program file (`<project>/<module>.py`) changes.
- **N7.** No CI workflow job, step order or runner changes; the rendered Makefile's `test` and `mutants` recipes (R12, R17) are the only CI-visible changes.

## Multi-Lens Review

Reviewed at commit: `218a2e4` (round 1, before the revisions below)

### Goal-Fit

Finding: Worth building. The premise was reproduced: a debug collatz with no argument and an open stdin printed `Enter N (...)` and hung until killed; twin-primes exits 2. The `read_line` counts match. The harness changes a verdict through CI and ci-gate. Defect: the pre-push arm (old R13) runs the Rust mode on pushes that touch only `cli_contract.py`, which build nothing, so a fresh worktree is refused (exit 2) and an old one checks stale binaries.
Assumption: the debug binaries finish the six smoke cases inside the 60 s case timeout on a 2-vCPU runner. Refuted as a risk by the Risk lens's measurement: all 11 run at SMOKE_SIZE in at most 0.41 s.
Disposition: Addressed. R13 now runs the harness's fixture tests and no Rust binary; the 11 binaries are checked by each crate's CI `make test`.

### Ergonomics

Finding: the same pre-push defect, found independently. The obvious fix (build first) costs minutes per push, because 5 crates compile GMP/MPFR in a cold per-checkout `CARGO_HOME`.
Assumption: tarpaulin, run without `--follow-exec`, counts `main.rs` lines exercised only by subprocess tests. If not, deleting the in-process `io::Cursor` tests (R14) drops coverage below 90%.
Disposition: Addressed. R16 requires an injectable `run(cli, stdin_is_tty, input, out)` with in-process tests of every contract path, including the terminal prompt. Operator also added concurrent local tests (R18, R19) after asking whether the build is parallel.

### Risk

Finding: N4 froze the 4 `.cargo/mutants.toml` files while R4 and R14 move the `file:line:col` positions their `exclude_re` patterns pin. About 25 equivalent mutants would silently return as "missed", and survivors are green. Minor:
- R5's probes had no time or memory cap;
- the harness assumed `./target`;
- twin-primes has no `tests/cli.rs`, although nextest still builds its binary.
Assumption: the rewritten `main.rs` logic, including R7's terminal branch, can be covered in-process.
Disposition: Addressed. R17 re-anchors the patterns and adds a test that each matches a listed mutant; N4 now forbids adding or removing exclusions. R5 runs each probe under `timeout 61` and `ulimit -v 8388608`. R10 resolves the target directory with `cargo metadata`. The twin-primes wording is corrected. R16 covers the assumption.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
