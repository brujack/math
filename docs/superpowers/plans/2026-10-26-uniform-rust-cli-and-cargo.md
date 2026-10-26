# Uniform Rust CLI Contract and Cargo.toml Shape Implementation Plan

spec: docs/superpowers/specs/2026-10-25-uniform-rust-cli-and-cargo-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the 11 Rust binaries the ADR-0030 CLI contract checked by the shared harness in every crate's `make test`, make the 11 `Cargo.toml` files test-enforced uniform, run local suites concurrently, and bound every test in time.

**Architecture:** Two PRs. P1 (Tasks 1-5) adds the `Cargo.toml` shape test and fixes, the two missing crate `CLAUDE.md` files, one concurrent runner (`scripts/parallel-make-test.sh`) used by the pre-push hook and a root `make test-rust`, and the nextest/coverage time bounds. P2 (Tasks 6-23) adds the harness Rust mode, wires it into the rendered crate `Makefile`, rewrites the 11 CLIs in one parallel wave, measures the thresholds serially, adds the mutants anchor pre-flight, ADR-0033 and the `math-new-cli` update.

**Tech Stack:** Rust (clap 4 derive, `std::io::IsTerminal`), cargo-nextest 0.9.149, cargo-tarpaulin 0.37.5, cargo-mutants 27.1.0, cargo-machete 0.9.2, Python 3.14 stdlib (`tomllib`, `subprocess`), bats 1.13.0, GNU make 4.4.1, GNU xargs 4.10.0.

## Global Constraints

- Crates (dir: lib name, SIZE meaning, current range): amicable (10^N, 1-8), collatz (10^N, 1-12), e (digits), factorial (n), fib (10^X digits, 1-5), goldbach (10^N, 1-8), perfect-numbers / `perfect_numbers` (10^N, 1-54), pi (digits), prime (10^N, max 18), sq (10^N digits, 1 only), twin-primes / `twin_primes` (10^N, 1-15). Existing range checks and their messages stay (N2).
- `SMOKE_SIZE`: amicable 5, collatz 5, e 10000, pi 10000, factorial 1000, fib 3, perfect-numbers 6, sq 1, prime 3, goldbach 3, twin-primes 3.
- `LARGE_RUN_THRESHOLD`: written `None` by the wave (Tasks 9-19); Task 20 sets each measured value (R5 definition: smallest SIZE whose release run exceeds 60 s wall-clock or 8 GiB max RSS; `timeout 61`, `/usr/bin/time -v`, no `ulimit -v`; or `None` when the range check rejects every such SIZE).
- nextest bound: `slow-timeout = { period = "15s", terminate-after = 3 }` on `[profile.default]`. Coverage job: `timeout-minutes: 30`.
- `PRE_PUSH_JOBS` default 8; root `JOBS` default 8 (the existing `JOBS ?= 8`).
- `pub fn run(cli: Cli, stdin_is_tty: bool, input: impl BufRead, out: impl Write, err: impl Write, dir: &Path) -> i32`.
- EOF message (stderr, after an empty line on stdout): `Error: no input; pass SIZE as an argument (e.g. <bin> <SMOKE_SIZE>).` Refusal: `Error: <size> is a large run; pass --yes to proceed.`
- N1 No output file is renamed. N2 No binary changes what SIZE means. N3 No Cargo workspace is introduced. N4 No `.cargo/mutants.toml` file or `exclude_re` exclusion is added or removed. N5 No coverage floor is lowered. N6 No Python program file (`<project>/<module>.py`) changes. N7 No CI workflow job, step order or runner changes other than the rendered Makefile's `test` and `mutants` recipes (R12, R17), the rendered `.config/nextest.toml` bound and the coverage job's `timeout-minutes` (R20).
- Root `CLAUDE.md` ceiling 30,000 bytes (27,762 at `a280493`); P1 and P2 together may add at most 2,238.
- Read `~/.claude/standards/rust.md` before any `.rs`, `Cargo.toml`, `rustfmt.toml`, `rust-check.sh` or `*-rs.yml` change; `~/.claude/standards/python.md` before any `.py` change.
- Mutants anchors at `a280493` (`cargo mutants --list --no-config`): all 24 `exclude_re` patterns (amicable 1, factorial 3, goldbach 9, perfect-numbers 11) match one listed mutant, `src/lib\.rs:44:5: replace verify_perfect` two; the unconfigured lists hold 21/65/95/98 mutants against 20/62/86/87 configured.
- Measured durations on `claude`, clone of `a280493` (2026-10-26): root `make test` 36.9 s (305 Python tests, 252 bats); crate `make test` amicable 12.5, collatz 10.4, e 17.8, factorial 11.0, fib 10.9, goldbach 10.5, perfect-numbers 10.7, pi 15.0, prime 11.6, sq 17.2, twin-primes 11.4 s; `cargo tarpaulin` collatz 14 s (98.33%), pi 32 s (92.27%), e 34 s (93.01%). Slowest nextest totals: e 6.03 s, pi 4.18 s, prime 0.74 s.

### Rust contract shape (every wave task implements exactly this)

```rust
// src/lib.rs: appended after the last existing item, before any #[cfg(test)] module,
// so no exclude_re line in .cargo/mutants.toml moves (N4).
pub const SMOKE_SIZE: u64 = <table value>;
pub const LARGE_RUN_THRESHOLD: Option<u64> = None;

// src/main.rs
#[derive(Parser, Debug)]
#[command(version, about = "<existing about>")]
pub struct Cli {
    /// <existing help text, meaning unchanged>
    #[arg(value_name = "SIZE")]
    size: Option<u64>,
    /// also print each result line to stdout
    #[arg(long)]
    show: bool,
    /// confirm a run at or above LARGE_RUN_THRESHOLD
    #[arg(long)]
    yes: bool,
    /// quick check at SMOKE_SIZE
    #[arg(long, conflicts_with = "size")]
    smoke: bool,
}

/// Prints the refusal and returns true when size needs --yes and it is absent.
fn refuse_large_run(size: u64, yes: bool, threshold: Option<u64>, err: &mut impl Write) -> bool;

pub fn run(cli: Cli, stdin_is_tty: bool, input: impl BufRead, out: impl Write, err: impl Write, dir: &Path) -> i32;

#[cfg(not(tarpaulin_include))]
fn main() {
    let cli = Cli::parse();
    let dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let code = run(cli, io::stdin().is_terminal(), io::stdin().lock(), io::stdout(), io::stderr(), &dir);
    std::process::exit(code);
}
```

`run` order: `--smoke` sets SIZE to `SMOKE_SIZE` and show to false; a given SIZE is used as is; no SIZE with `!stdin_is_tty` writes `Cli::command().render_usage()` to err and returns 2; no SIZE at a terminal writes one prompt `Enter SIZE (<meaning>): ` to out and reads one line (EOF: empty line on out, the EOF message on err, return 1; an unparsable or invalid answer returns 1 with the argument path's message). Then the crate's existing range check (message unchanged, return 1), then `refuse_large_run(size, yes, LARGE_RUN_THRESHOLD, ..)` (return 1) before any file is created. The output file is always written under `dir` with its current name (N1); with `--show` each result line goes to out before the summary, without it no result line reaches out. An `io::Error` prints `Error: <e>` to err and returns 1. No `.lock()` on stdout or stderr anywhere in `main.rs`. Unit tests in `main.rs` call `run` with `Cli::try_parse_from`, `io::Cursor`, `Vec<u8>` writers and a `tempfile::tempdir()`, covering: SIZE quiet, SIZE `--show`, `--smoke`, `--smoke` with SIZE (clap error), invalid SIZE, `refuse_large_run` with `Some(t)` at t-1/t/t+1 with and without `--yes`, no-arg non-TTY (2, usage), TTY with a valid answer, TTY EOF (1, both lines), TTY invalid answer (1), an unwritable `dir` (1). The pin test `assert_eq!(SMOKE_SIZE, ..); assert_eq!(LARGE_RUN_THRESHOLD, ..)` lives in `lib.rs`'s test module.

## Verification Planning

- After P1: `make test` exits 0; `make test-rust` prints 11 `ok` lines and exits 0; `python3 scripts/render_crate_files.py --check` exits 0; `bats tests/scripts/pre_push.bats` covers pass, one failure among several, a killed job and 7 suites.
- After P2: `make test-rust` exits 0 with every crate log containing `cli_contract: <crate>: all cases pass`; `for c in amicable factorial goldbach perfect-numbers; do python3 scripts/mutants_anchor_check.py "$c/$c-rs" || exit 1; done` exits 0; `git grep -c read_line -- '*/*-rs/src/main.rs'` shows at most 1 per crate.
- Proof the harness fails: after Task 8 and before the wave, `make -C collatz/collatz-rs test` exits 2 naming `SMOKE_SIZE`; Task 6's tests run every bad fixture through `--rust`.
- Edge cases: SIZE at threshold-1/threshold/threshold+1; `--smoke SIZE` (2); non-TTY bare run (2); TTY EOF (1); xargs killed job (GNU xargs exits 125 at once and starts no further job: measured with 4 inputs at `-P 2`, the killed second job left 1 status file); macOS BSD xargs (status files make the result independent of xargs's exit code; V5/V6 run it).
- V1-V6 are orchestrator steps below.

---

## PR 1 (P1): Cargo.toml shape, crate CLAUDE.md, concurrent local tests, time bounds

Orchestrator before Task 1:

- [ ] `git worktree add .worktrees/uniform-rust-p1 -b feat/uniform-rust-cargo-and-parallel-tests` from `origin/master`; every dispatch prompt starts with the worktree line (git-workflow-045). P1 tasks are sequential (each edits root `CLAUDE.md` or a shared test file).
- [ ] R20 Mac Studio figure (master suffices; P1 changes no test). Write the probe locally, copy it, run it in a login shell:

  ```bash
  # <scratchpad>/r20-probe.sh, then: scp it studio:/tmp/r20-probe.sh
  d=$(mktemp -d) && git clone -q "$(git -C ~/git-repos/personal/math remote get-url origin)" "$d" || exit 1
  for c in e pi prime; do
    (cd "$d/$c/$c-rs" && NEXTEST_PROFILE=ci make test </dev/null >/dev/null 2>&1) || echo "$c: make test failed"
    python3 -c 'import sys,xml.etree.ElementTree as E; print(sys.argv[1], max(float(t.get("time")) for t in E.parse(sys.argv[2]).iter("testcase")))' "$c" "$d/$c/$c-rs/target/nextest/ci/junit.xml"
  done
  rm -rf -- "$d"
  ```

  `ssh studio 'zsh -l -i -c "bash /tmp/r20-probe.sh"'`. Record the three maxima as an amendment in the spec's `## Amendments` (create the section; forms in `~/.claude/scripts/spec_contract.py`'s docstring). If any exceeds 15 s, Task 5's period becomes the slowest test measured on any of the three machines, rounded up to a whole second (kill time 3 × period keeps R20's 3× headroom), and the amendment says so.

### Task 1: Cargo.toml shape test and the fixes it requires

```yaml-task
id: 1
description: Add TestCargoTomlShape (tomllib) to test_crate_uniformity.py, converge all 11 Cargo.toml files, and give factorial a used clap parse
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R9]
acceptance:
  - cmd: python3 -m unittest tests.test_crate_uniformity -v
    exit_code: 0   # base with the new test only: 1, naming sq and factorial
  - cmd: make -C factorial/factorial-rs test
    exit_code: 0   # clap added but unused: 2 (cargo machete "unused dependencies: clap")
  - cmd: make -C sq/sq-rs test
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [tests/test_crate_uniformity.py, sq/sq-rs/Cargo.toml, factorial/factorial-rs/Cargo.toml, factorial/factorial-rs/Cargo.lock, factorial/factorial-rs/src/main.rs, factorial/factorial-rs/CLAUDE.md, e/e-rs/Cargo.toml, pi/pi-rs/Cargo.toml, prime/prime-rs/Cargo.toml, .github/workflows/scripts.yml]
depends_on: []
```

Measured at `a280493` (tomllib): everything R1 names already agrees except `[profile.release]` (`{opt-level 3, lto "thin", codegen-units 1}` in 9, `{opt-level 3}` alone in factorial, absent in sq) and clap (absent in factorial). `TestCargoTomlShape` asserts R1 per crate (`subTest`, crates from `rcf.CRATES`) plus byte-identical `[profile.release]` text, canonical form amicable's (`opt-level     = 3` aligned); e, pi (drop its comments), prime, factorial and sq converge. `cargo machete` (in `make lint`) fails on an unused clap, so factorial's `main()` parses `#[derive(Parser, Debug)] struct Cli { n: Option<String> }` and passes `cli.n.as_deref()` to the unchanged `run` (only `--help` is new). Add `"*/*-rs/Cargo.toml"` to `scripts.yml` `paths:`, asserted by the new test.

- [ ] Failing test, fix, run acceptance, commit (`test(rust): enforce one Cargo.toml shape`).

### Task 2: A CLAUDE.md in every crate

```yaml-task
id: 2
description: Move pi's Rust sections and prime/CLAUDE.md into pi/pi-rs and prime/prime-rs CLAUDE.md files, and require <crate>-rs/CLAUDE.md for all 11 (docs plus one test)
role: executor
model: sonnet
tdd: required
requirements: [R3]
acceptance:
  - cmd: python3 -m unittest tests.test_crate_uniformity -v
    exit_code: 0   # base with the new test only: 1, naming pi and prime
  - cmd: '! command grep -q "^## Rust Implementation" pi/CLAUDE.md'
    exit_code: 0   # base: 1 (heading at line 17)
  - cmd: 'command grep -q "prime-rs/CLAUDE.md" prime/CLAUDE.md'
    exit_code: 0   # base: 1
  - cmd: 'test "$(wc -c < CLAUDE.md)" -le 30000'
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 2
files_touched: [tests/test_crate_uniformity.py, pi/CLAUDE.md, pi/pi-rs/CLAUDE.md, prime/CLAUDE.md, prime/prime-rs/CLAUDE.md, AGENTS.md, CLAUDE.md, .github/workflows/scripts.yml]
depends_on: [1]
```

`TestCrateClaudeMd`: `<crate>/<crate>-rs/CLAUDE.md` exists for every `rcf.CRATES` entry (base: missing for pi and prime). Move `pi/CLAUDE.md` lines 17-76 (`## Rust Implementation`, `### Rust Code Layout`, `### rug Arithmetic Note`) and 283-335 (`### Rust (pi-rs/)` testing) into `pi/pi-rs/CLAUDE.md`, leaving one pointer line. Move all of `prime/CLAUDE.md` (191 lines) to `prime/prime-rs/CLAUDE.md`, leaving a 3-line file that points there. `AGENTS.md` lists every sub-project and crate `CLAUDE.md` (today it lists 7, including the two moved ones). Root `CLAUDE.md` line 13's parenthesis becomes "every crate's is `<crate>/<crate>-rs/CLAUDE.md`". Add `"*/*-rs/CLAUDE.md"` to `scripts.yml` `paths:`.

- [ ] Failing test, move text verbatim, run acceptance, commit (`docs(rust): give every crate its own CLAUDE.md`).

### Task 3: Concurrent pre-push suites with per-job status files

```yaml-task
id: 3
description: Add scripts/parallel-make-test.sh (xargs -P, one log and status file per dir) and use it from pre-push, removing the >6 skip
role: executor
model: sonnet
tdd: required
requirements: [R18]
acceptance:
  - cmd: bats tests/scripts/pre_push.bats
    exit_code: 0   # new cases fail against the unmodified hook (7 dirs print "skipping", 0 make calls)
  - cmd: '! command grep -q -- "-gt 6" scripts/pre-push'
    exit_code: 0   # base: 1
  - cmd: make lint-hooks
    exit_code: 0
  - cmd: 'test "$(wc -c < CLAUDE.md)" -le 30000'
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/parallel-make-test.sh, scripts/pre-push, tests/scripts/pre_push.bats, tests/mocks/make, CLAUDE.md]
depends_on: [2]
```

`parallel-make-test.sh <jobs> <root> <dir>...` (shell standard; exit 2 on a bad `<jobs>` or no dirs): temp dir with an `EXIT` trap; `xargs -0 -P "${jobs}" -I{} bash -c 'make -C "$1/$2" test </dev/null >"$3" 2>&1; printf "%s\n" "$?" >"$4"'` per dir (log/status names: dir with `/` → `_`); ignore xargs's exit code; per dir in input order print `ok <dir>` or `FAIL <dir>` (no status file = FAIL), then each failing log in full; exit 1 if any failed. The hook locates it beside itself (`readlink -f "${BASH_SOURCE[0]}"`; the installed hook is a symlink into the main checkout) and replaces the `-gt 6` block and serial loop with `"${HOOK_DIR}/parallel-make-test.sh" "${PRE_PUSH_JOBS:-8}" "${REPO_ROOT}" "${UNIQUE_DIRS[@]}" || exit 1`. `tests/mocks/make` gains `MOCK_MAKE_FAIL_DIR` (exit 1) and `MOCK_MAKE_KILL_DIR` (`kill -KILL "${PPID}"`). bats: pass; fib failing among pi/fib/e prints `FAIL fib` and its log, exit 1; killed e prints `FAIL e`, exit 1; 7 Python dirs give 7 `make` calls. Rewrite the two `skipping local tests` cases. Root `CLAUDE.md` pre-push and `resource_tracker` lines: concurrent, no skip.

- [ ] Failing bats, implement, run acceptance, commit (`ci(pre-push): run changed suites concurrently`).

**Interfaces (Produces):** `scripts/parallel-make-test.sh <jobs> <root> <dir>...` → 0 all ok, 1 any FAIL, 2 usage. Task 4 calls it.

### Task 4: Root make test-rust

```yaml-task
id: 4
description: Add a root test-rust target running all crates' make test through parallel-make-test.sh with JOBS, covered by makefile.bats
role: executor
model: sonnet
tdd: required
requirements: [R19]
acceptance:
  - cmd: make -n test-rust
    exit_code: 0   # base: 2, "No rule to make target 'test-rust'"
  - cmd: bats tests/scripts/makefile.bats
    exit_code: 0
  - cmd: make test-rust
    exit_code: 0
    stdout_match: 'ok twin-primes/twin-primes-rs'
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [Makefile, tests/scripts/makefile.bats, CLAUDE.md, README.md]
depends_on: [3]
```

`RUST_CRATE_DIRS := $(patsubst %/Makefile,%,$(shell env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git ls-files '*/*-rs/Makefile'))` (derived, never hand-listed; ci-016); recipe guards an empty list (exit 1, message), then `scripts/parallel-make-test.sh $(JOBS) $(CURDIR) $(RUST_CRATE_DIRS)`; add to `.PHONY`. makefile.bats: capture the real make (`command -v make`) before `load_mocks`, run it on `test-rust JOBS=3` so sub-makes hit the mock: 11 `make -C <root>/<dir> test` calls, one per `git ls-files '*/*-rs/Makefile'` entry; with `MOCK_MAKE_FAIL_DIR=fib/fib-rs` the target exits non-zero and prints `FAIL fib/fib-rs`. Docs: one Quick Reference line in root `CLAUDE.md` and README.

- [ ] Failing bats, implement, run acceptance, commit (`build: add make test-rust`).

### Task 5: Bounded tests and bounded coverage job

```yaml-task
id: 5
description: Set the nextest slow-timeout bound and the coverage job timeout-minutes in the templates, render 22 files, and test both bounds
role: executor
model: sonnet
tdd: required
requirements: [R20]
acceptance:
  - cmd: python3 -m unittest tests.test_rust_ci_jobs -v
    exit_code: 0   # base with the new tests only: 1 (no slow-timeout, no timeout-minutes)
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: make -C e/e-rs test
    exit_code: 0
  - cmd: make -C pi/pi-rs test
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 2
files_touched: [scripts/crate_templates/nextest.toml, scripts/crate_templates/ci.yml, tests/test_rust_ci_jobs.py, CLAUDE.md, amicable/amicable-rs/.config/nextest.toml, collatz/collatz-rs/.config/nextest.toml, e/e-rs/.config/nextest.toml, factorial/factorial-rs/.config/nextest.toml, fib/fib-rs/.config/nextest.toml, goldbach/goldbach-rs/.config/nextest.toml, perfect-numbers/perfect-numbers-rs/.config/nextest.toml, pi/pi-rs/.config/nextest.toml, prime/prime-rs/.config/nextest.toml, sq/sq-rs/.config/nextest.toml, twin-primes/twin-primes-rs/.config/nextest.toml, .github/workflows/amicable-rs.yml, .github/workflows/collatz-rs.yml, .github/workflows/e-rs.yml, .github/workflows/factorial-rs.yml, .github/workflows/fib-rs.yml, .github/workflows/goldbach-rs.yml, .github/workflows/perfect-numbers-rs.yml, .github/workflows/pi-rs.yml, .github/workflows/prime-rs.yml, .github/workflows/sq-rs.yml, .github/workflows/twin-primes-rs.yml]
depends_on: [4]
```

Template `nextest.toml` gains `[profile.default]` with the bound (or the Studio amendment's period) above `[profile.ci]`; `ci.yml`'s `coverage` job gains `timeout-minutes: 30`; `--write` renders 22 files. Tests over every rendered file: default-profile `slow-timeout` equals the bound; `jobs.coverage["timeout-minutes"] == 30`. One root `CLAUDE.md` line names both bounds.

- [ ] Failing tests, implement, render, run acceptance, commit (`ci(rust): bound test and coverage time`).

Orchestrator after Task 5:

- [ ] Uncontended: `make test`, `make test-rust`, `python3 scripts/render_crate_files.py --check`.
- [ ] `gh pr create --draft`; Phase 3 (`finishing-a-development-branch`); `gh pr ready`; `gh pr checks <n> --watch` until green.
- [ ] V2: for each of the 11 `<crate>-rs` runs, `gh run view <id> --log | command grep -E '[0-9.]+% coverage'` is at least 90.
- [ ] Merge, clean up (git-workflow-006/009). V5 on the merged tree: copy this script to `studio:/tmp/v-studio.sh` and run `ssh studio 'zsh -l -i -c "bash /tmp/v-studio.sh"'`; it must exit 0.

  ```bash
  d=$(mktemp -d) && git clone -q "$(git -C ~/git-repos/personal/math remote get-url origin)" "$d" || exit 1
  rc=0
  for p in amicable collatz e factorial fib perfect-numbers pi sq; do make -C "$d/$p" test </dev/null || rc=1; done
  make -C "$d" test-rust </dev/null || rc=1
  rm -rf -- "$d"; exit "${rc}"
  ```

---

## PR 2 (P2): the Rust CLI contract

Orchestrator before Task 6: `git worktree add .worktrees/uniform-rust-p2 -b feat/uniform-rust-cli-contract` from `origin/master` after PR 1 merges.

### Task 6: Harness Rust mode

```yaml-task
id: 6
description: Add cli_contract.py --rust <crate-dir> (constants from lib.rs, target dir from cargo metadata) sharing the six-case matrix, with fake-crate tests for every case and config error
role: executor
model: sonnet
tdd: required
requirements: [R10, R11]
acceptance:
  - cmd: python3 -m unittest tests.test_cli_contract_harness -v
    exit_code: 0
  - cmd: python3 scripts/cli_contract.py --rust collatz/collatz-rs
    exit_code: 2
    stderr_match: 'SMOKE_SIZE'   # base: exit 2 with "usage: cli_contract.py <module.py>"
  - cmd: python3 scripts/cli_contract.py fib/fib.py
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/cli_contract.py, tests/test_cli_contract_harness.py]
depends_on: [5]
```

New: `load_rust_constants(lib_rs: Path) -> tuple[int, int | None]`, patterns `^pub const SMOKE_SIZE: u64 = ([0-9_]+);$` and `^pub const LARGE_RUN_THRESHOLD: Option<u64> = (None|Some\(([0-9_]+)\));$` (multiline, exactly one match each, else `ContractConfigError`); `rust_binary(crate_dir: Path) -> Path` from `cargo metadata --format-version 1 --no-deps` (module-level `CARGO = "cargo"`) as `<target_directory>/debug/<dir without -rs>`, `ContractConfigError` on a metadata failure or a missing file (naming `cargo build`); `run_case` takes an argv prefix; `run_matrix(path)` unchanged; `run_rust_matrix(crate_dir) -> list[str]`; `main` takes `<module.py>` or `--rust <crate-dir>`. Tests build a fake crate in a temp dir (Cargo.toml with `[[bin]]`, `src/main.rs`, a written `src/lib.rs`) and install an existing stub (conforming, prompts, silent_reader, writes_nothing, no_refusal, rejects_yes) as `target/debug/<name>` with a `#!<sys.executable>` line, mode 0o755: conforming passes, each bad stub fails its case; config errors: missing, duplicated, unparsable (`= 1e4;`) SMOKE_SIZE, missing threshold, missing binary, failing metadata; `CARGO_TARGET_DIR` honoured; `main` exits 0/1/2. (`cargo metadata` there: 0.07 s, no `Cargo.lock`.)

- [ ] Failing tests, implement, run acceptance, commit (`feat(cli): add the harness Rust mode`).

### Task 7: Pre-push harness arm runs the harness tests, never a binary

```yaml-task
id: 7
description: The RUN_CLI_CONTRACT arm also runs tests/test_cli_contract_harness.py and no Rust binary; pre_push.bats covers both
role: executor
model: sonnet
tdd: required
requirements: [R13]
acceptance:
  - cmd: bats tests/scripts/pre_push.bats
    exit_code: 0   # the new case fails against the unmodified arm (no unittest call recorded)
  - cmd: make lint-hooks
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 2
files_touched: [scripts/pre-push, tests/scripts/pre_push.bats]
depends_on: [6]
```

In the arm, before the 8-project loop: `(cd "${REPO_ROOT}" && python3 -m unittest tests.test_cli_contract_harness) </dev/null || { printf "pre-push: CLI contract harness tests failed\n" >&2; exit 1; }`. bats with `setup_harness_stub`: a harness-only push records `python3 cwd=fake-worktree args=-m unittest tests.test_cli_contract_harness`; no `python3` call carries `--rust` and no `make -C .*-rs test` occurs; `MOCK_PYTHON_FAIL_DIR=fake-worktree` fails the push.

- [ ] Failing bats, implement, run acceptance, commit (`ci(pre-push): run harness tests on harness changes`).

### Task 8: Harness in every crate's make test

```yaml-task
id: 8
description: Template test target runs rust-check test, rust-check build, then the harness --rust; render 11; require tests/cli.rs in all 11; harness changes trigger crate CI
role: executor
model: sonnet
tdd: required
requirements: [R12]
acceptance:
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: make -C collatz/collatz-rs test
    exit_code: 2
    stderr_match: 'SMOKE_SIZE'   # base: 0 (no harness line)
  - cmd: bats tests/scripts/rust_check.bats
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/Makefile, scripts/crate_templates/ci.yml, scripts/rust-check.sh, tests/scripts/rust_check.bats, tests/test_crate_uniformity.py, tests/test_rust_ci_jobs.py, CLAUDE.md, amicable/amicable-rs/Makefile, collatz/collatz-rs/Makefile, e/e-rs/Makefile, factorial/factorial-rs/Makefile, fib/fib-rs/Makefile, goldbach/goldbach-rs/Makefile, perfect-numbers/perfect-numbers-rs/Makefile, pi/pi-rs/Makefile, prime/prime-rs/Makefile, sq/sq-rs/Makefile, twin-primes/twin-primes-rs/Makefile, .github/workflows/amicable-rs.yml, .github/workflows/collatz-rs.yml, .github/workflows/e-rs.yml, .github/workflows/factorial-rs.yml, .github/workflows/fib-rs.yml, .github/workflows/goldbach-rs.yml, .github/workflows/perfect-numbers-rs.yml, .github/workflows/pi-rs.yml, .github/workflows/prime-rs.yml, .github/workflows/sq-rs.yml, .github/workflows/twin-primes-rs.yml]
depends_on: [7]
```

`test: lint` recipe: `../../scripts/rust-check.sh test`, `../../scripts/rust-check.sh build`, `python3 ../../scripts/cli_contract.py --rust .`. The new `build` mode (`cargo build` plus the offline args) keeps `rust-check.sh`'s `CARGO_HOME`; alternating CARGO_HOME rebuilt pi-rs every call (4.7-8.0 s, measured). rust_check.bats: `build` runs `cargo build`, honours `RUST_CHECK_OFFLINE`, propagates failure. `ci.yml` `paths:` gains `"scripts/cli_contract.py"` (asserted in `test_rust_ci_jobs.py`). `TestCrateCliTests`: `tests/cli.rs` in all 11. Every crate's `make test` stays red until its wave task. Root `CLAUDE.md`: one line.

- [ ] Failing tests, implement, render, run acceptance, commit (`feat(rust): run the CLI harness in every crate test`).

### Wave: Tasks 9-19, one crate each (`parallel_group: cli-rust`)

Each wave task implements the Global Constraints shape in its own crate only and depends on Tasks 6 and 8 (harness Rust mode and the rendered harness line). Its gates are crate-scoped and valid under the wave rule: `make -C <crate>-rs test` reads only that crate's directory plus `scripts/rust-check.sh` and `scripts/cli_contract.py`, which no wave member touches, and each crate has its own `target/` (the shared `.cache/cargo-home` is serialised by cargo's package-cache lock). The orchestrator runs root `make test` and `make test-rust` once at wave close. Each gate is its own Bash call with `timeout: 600000`; uncontended figures are in Global Constraints. Before the wave each crate's `make test` exits 2 naming `SMOKE_SIZE` (Task 8). Every member deletes the old prompt functions (`prompt_*`, `read_line_from`, confirm prompts) and their `io::Cursor` tests (R14), rewrites `tests/cli.rs` cases that piped answers into prompts (now: no-arg with piped stdin exits 2; SIZE runs), updates its crate `CLAUDE.md` usage, and leaves `LARGE_RUN_THRESHOLD = None` for Task 20.

### Task 9: amicable on the contract

```yaml-task
id: 9
description: amicable-rs adopts the Rust contract shape; pairs echo only with --show; amicable.bats rust cases updated
role: executor
model: sonnet
tdd: required
requirements: [R4, R6, R7, R8, R14, R16]
acceptance:
  - cmd: make -C amicable/amicable-rs test
    exit_code: 0
  - cmd: 'cd amicable/amicable-rs && cargo tarpaulin --out Stdout --fail-under 90'
    exit_code: 0
  - cmd: '! command grep -qE "(stdout|stderr)(\(\))?\.lock\(\)" amicable/amicable-rs/src/main.rs'
    exit_code: 0   # base: 1
  - cmd: bats tests/scripts/amicable.bats
    exit_code: 0
max_retries: 3
files_touched: [amicable/amicable-rs/src/main.rs, amicable/amicable-rs/src/lib.rs, amicable/amicable-rs/tests/cli.rs, amicable/amicable-rs/CLAUDE.md, tests/scripts/amicable.bats]
depends_on: [6, 8]
parallel_group: cli-rust
```

Today `n: u32` is required with a clap `range(1..=8)` and `run` prints every `a b` pair to stdout and takes an output path. Move the range check into `run` (`Error: N must be between 1 and 8.`, exit 1), pass `dir`, print `Found <k> amicable pairs up to 10^<n>` and `Saved to amicable_1e<n>.txt`, echo pairs only with `--show`. `lib.rs` lines 1-11 stay byte-identical (mutants anchor `src/lib.rs:3:25`). `amicable.bats` "rust: N=3 produces exactly one pair" becomes `3 --show` asserting a line equal to `220 284`, plus a no-`--show` case asserting none.

- [ ] Failing tests, implement, run acceptance, commit (`feat(amicable-rs): adopt the CLI contract`).

### Task 10: collatz on the contract

```yaml-task
id: 10
description: collatz-rs adopts the Rust contract shape; record lines echo only with --show; prompt_n loop removed
role: executor
model: sonnet
tdd: required
requirements: [R4, R6, R7, R8, R14, R16]
acceptance:
  - cmd: make -C collatz/collatz-rs test
    exit_code: 0
  - cmd: 'cd collatz/collatz-rs && cargo tarpaulin --out Stdout --fail-under 90'
    exit_code: 0
  - cmd: '! command grep -qE "(stdout|stderr)(\(\))?\.lock\(\)" collatz/collatz-rs/src/main.rs'
    exit_code: 0   # base: 1
  - cmd: 'test "$(command grep -c read_line collatz/collatz-rs/src/main.rs)" -le 1'
    exit_code: 0
max_retries: 3
files_touched: [collatz/collatz-rs/src/main.rs, collatz/collatz-rs/src/lib.rs, collatz/collatz-rs/tests/cli.rs, collatz/collatz-rs/CLAUDE.md]
depends_on: [6, 8]
parallel_group: cli-rust
```

`exponent: Option<u32>` becomes `size`; keep the 1-12 check and the `Warning: N=<v> may require significant time and memory.` line on stderr; `prompt_n` (1 `read_line`, 8 `Cursor` uses) is replaced by the single prompt. Record lines go to the file always and to stdout only with `--show`; print a `Saved <k> records to collatz_1e<n>.txt` summary.

- [ ] Failing tests, implement, run acceptance, commit (`feat(collatz-rs): adopt the CLI contract`).

### Task 11: e on the contract

```yaml-task
id: 11
description: e-rs adopts the Rust contract shape; 12 read_line prompt paths removed; the math#175 progress-thread regression test kept
role: executor
model: sonnet
tdd: required
requirements: [R4, R6, R7, R8, R14, R16]
acceptance:
  - cmd: make -C e/e-rs test
    exit_code: 0
  - cmd: 'cd e/e-rs && cargo tarpaulin --out Stdout --fail-under 90'
    exit_code: 0
  - cmd: '! command grep -qE "(stdout|stderr)(\(\))?\.lock\(\)" e/e-rs/src/main.rs'
    exit_code: 0   # base: 1
  - cmd: 'test "$(command grep -c read_line e/e-rs/src/main.rs)" -le 1'
    exit_code: 0   # base: 12
max_retries: 3
files_touched: [e/e-rs/src/main.rs, e/e-rs/src/lib.rs, e/e-rs/tests/cli.rs, e/e-rs/CLAUDE.md]
depends_on: [6, 8]
parallel_group: cli-rust
```

`digits: Option<usize>` becomes `size: u64` converted with `usize::try_from` (error → exit 1). Delete `read_line_from`, `prompt_digits_with` and the display prompts; the `e_<digits>_digits.txt` file is always written; `--show` prints its digit line (the file's longest line) before the summary. Keep the progress thread, its shutdown signal and the deadlock regression test; progress stays on stderr via `eprint!`, which is safe because `main` holds no lock.

- [ ] Failing tests, implement, run acceptance, commit (`feat(e-rs): adopt the CLI contract`).

### Task 12: factorial on the contract

```yaml-task
id: 12
description: factorial-rs adopts the Rust contract shape on clap (SIZE u64); prompt_n_with loop removed; --show prints the digits
role: executor
model: sonnet
tdd: required
requirements: [R4, R6, R7, R8, R9, R14, R16]
acceptance:
  - cmd: make -C factorial/factorial-rs test
    exit_code: 0
  - cmd: 'cd factorial/factorial-rs && cargo tarpaulin --out Stdout --fail-under 90'
    exit_code: 0
  - cmd: '! command grep -qE "(stdout|stderr)(\(\))?\.lock\(\)" factorial/factorial-rs/src/main.rs'
    exit_code: 0   # base: 1
  - cmd: 'test "$(command grep -c read_line factorial/factorial-rs/src/main.rs)" -le 1'
    exit_code: 0   # base: 10
max_retries: 3
files_touched: [factorial/factorial-rs/src/main.rs, factorial/factorial-rs/src/lib.rs, factorial/factorial-rs/tests/cli.rs, factorial/factorial-rs/CLAUDE.md]
depends_on: [6, 8]
parallel_group: cli-rust
```

Task 1's `n: Option<String>` becomes the contract's `size: Option<u64>`; a non-numeric SIZE is now clap's exit 2 (`cli_invalid_arg_exits_one` asserts only non-zero). `factorial_<n>.txt` always written; `--show` prints the decimal string. `lib.rs` lines 1-41 stay byte-identical (anchors 13:13, 15:27, 41:16).

- [ ] Failing tests, implement, run acceptance, commit (`feat(factorial-rs): adopt the CLI contract`).

### Task 13: fib on the contract

```yaml-task
id: 13
description: fib-rs adopts the Rust contract shape; 14 read_line prompt paths and the display prompt removed
role: executor
model: sonnet
tdd: required
requirements: [R4, R6, R7, R8, R14, R16]
acceptance:
  - cmd: make -C fib/fib-rs test
    exit_code: 0
  - cmd: 'cd fib/fib-rs && cargo tarpaulin --out Stdout --fail-under 90'
    exit_code: 0
  - cmd: '! command grep -qE "(stdout|stderr)(\(\))?\.lock\(\)" fib/fib-rs/src/main.rs'
    exit_code: 0   # base: 1
  - cmd: 'test "$(command grep -c read_line fib/fib-rs/src/main.rs)" -le 1'
    exit_code: 0   # base: 14
max_retries: 3
files_touched: [fib/fib-rs/src/main.rs, fib/fib-rs/src/lib.rs, fib/fib-rs/tests/cli.rs, fib/fib-rs/CLAUDE.md]
depends_on: [6, 8]
parallel_group: cli-rust
```

`exponent: Option<u32>` becomes `size`; keep the 1-5 check and the large-X `Warning:` on stderr; delete `read_line_from`, `prompt_exponent_with` and every display/confirm prompt. `fib_1e<X>.txt` always written; `--show` prints each number line before the summary.

- [ ] Failing tests, implement, run acceptance, commit (`feat(fib-rs): adopt the CLI contract`).

### Task 14: goldbach on the contract

```yaml-task
id: 14
description: goldbach-rs adopts the Rust contract shape; prompt_n loop removed; pair lines echo only with --show
role: executor
model: sonnet
tdd: required
requirements: [R4, R6, R7, R8, R14, R16]
acceptance:
  - cmd: make -C goldbach/goldbach-rs test
    exit_code: 0
  - cmd: 'cd goldbach/goldbach-rs && cargo tarpaulin --out Stdout --fail-under 90'
    exit_code: 0
  - cmd: '! command grep -qE "(stdout|stderr)(\(\))?\.lock\(\)" goldbach/goldbach-rs/src/main.rs'
    exit_code: 0   # base: 1
  - cmd: 'test "$(command grep -c read_line goldbach/goldbach-rs/src/main.rs)" -le 1'
    exit_code: 0
max_retries: 3
files_touched: [goldbach/goldbach-rs/src/main.rs, goldbach/goldbach-rs/src/lib.rs, goldbach/goldbach-rs/tests/cli.rs, goldbach/goldbach-rs/CLAUDE.md]
depends_on: [6, 8]
parallel_group: cli-rust
```

`exponent` becomes `size`; keep the 1-8 check and the `Warning: N=<v> output may exceed 20 GB` line on stderr. Keep the prompt-guard artifact assertion style (root CLAUDE.md "Prompt-guard assertions") for the new TTY test: assert `goldbach_1e2.txt` exists. `lib.rs` lines 1-20 stay byte-identical (9 anchors on lines 14-20).

- [ ] Failing tests, implement, run acceptance, commit (`feat(goldbach-rs): adopt the CLI contract`).

### Task 15: perfect-numbers on the contract

```yaml-task
id: 15
description: perfect-numbers-rs adopts the Rust contract shape, keeping run's max_p formula and pn > limit break so their two mutants anchors still exist
role: executor
model: sonnet
tdd: required
requirements: [R4, R6, R7, R8, R14, R16]
acceptance:
  - cmd: make -C perfect-numbers/perfect-numbers-rs test
    exit_code: 0
  - cmd: 'cd perfect-numbers/perfect-numbers-rs && cargo tarpaulin --out Stdout --fail-under 90'
    exit_code: 0
  - cmd: '! command grep -qE "(stdout|stderr)(\(\))?\.lock\(\)" perfect-numbers/perfect-numbers-rs/src/main.rs'
    exit_code: 0   # base: 1
  - cmd: 'test "$(command grep -c read_line perfect-numbers/perfect-numbers-rs/src/main.rs)" -le 1'
    exit_code: 0   # base: 3
max_retries: 3
files_touched: [perfect-numbers/perfect-numbers-rs/src/main.rs, perfect-numbers/perfect-numbers-rs/src/lib.rs, perfect-numbers/perfect-numbers-rs/tests/cli.rs, perfect-numbers/perfect-numbers-rs/CLAUDE.md]
depends_on: [6, 8]
parallel_group: cli-rust
```

N4 forbids removing an exclusion, so `run` must keep `max_p = (limit.significant_bits() as u64 / 2) + 3` and `if pn > limit { ... break }` as expressions (their lines may move; Task 21 re-anchors `src/main.rs:92:*` and `:112:15`). `lib.rs` lines 1-62 stay byte-identical. `exponent` becomes `size` (1-54 check kept); `perfect-numbers_1e<n>.txt` always written; `--show` prints each perfect number line before the summary.

- [ ] Failing tests, implement, run acceptance, commit (`feat(perfect-numbers-rs): adopt the CLI contract`).

### Task 16: pi on the contract

```yaml-task
id: 16
description: pi-rs adopts the Rust contract shape; 12 read_line prompt paths removed; the math#175 progress-thread regression test kept
role: executor
model: sonnet
tdd: required
requirements: [R4, R6, R7, R8, R14, R16]
acceptance:
  - cmd: make -C pi/pi-rs test
    exit_code: 0
  - cmd: 'cd pi/pi-rs && cargo tarpaulin --out Stdout --fail-under 90'
    exit_code: 0
  - cmd: '! command grep -qE "(stdout|stderr)(\(\))?\.lock\(\)" pi/pi-rs/src/main.rs'
    exit_code: 0   # base: 1
  - cmd: 'test "$(command grep -c read_line pi/pi-rs/src/main.rs)" -le 1'
    exit_code: 0   # base: 12
max_retries: 3
files_touched: [pi/pi-rs/src/main.rs, pi/pi-rs/src/lib.rs, pi/pi-rs/tests/cli.rs, pi/pi-rs/CLAUDE.md]
depends_on: [6, 8]
parallel_group: cli-rust
```

Same as Task 11 for pi: `digits: Option<usize>` becomes `size: u64` with `usize::try_from`; today's `run` returns `io::Result<i32>` and takes `&mut` readers/writers, which the contract signature replaces. Delete `read_line_from`, `prompt_digits_with` and the display prompts; `pi_<digits>_digits.txt` always written via `write_pi_file`; `--show` prints the digit line. Keep the progress thread and the `TICK_BUDGET` deadlock test. Docs go in `pi/pi-rs/CLAUDE.md` (Task 2).

- [ ] Failing tests, implement, run acceptance, commit (`feat(pi-rs): adopt the CLI contract`).

### Task 17: prime on the contract

```yaml-task
id: 17
description: prime-rs adopts the Rust contract shape; the Continue? (y/n) confirmation becomes the --yes refusal; 12 read_line paths removed
role: executor
model: sonnet
tdd: required
requirements: [R4, R6, R7, R8, R14, R16]
acceptance:
  - cmd: make -C prime/prime-rs test
    exit_code: 0
  - cmd: 'cd prime/prime-rs && cargo tarpaulin --out Stdout --fail-under 90'
    exit_code: 0
  - cmd: '! command grep -qE "(stdout|stderr)(\(\))?\.lock\(\)" prime/prime-rs/src/main.rs'
    exit_code: 0   # base: 1
  - cmd: 'test "$(command grep -c read_line prime/prime-rs/src/main.rs)" -le 1'
    exit_code: 0   # base: 12
max_retries: 3
files_touched: [prime/prime-rs/src/main.rs, prime/prime-rs/src/lib.rs, prime/prime-rs/tests/cli.rs, prime/prime-rs/CLAUDE.md]
depends_on: [6, 8]
parallel_group: cli-rust
```

`digits: Option<u32>` becomes `size`; keep the max-18 check. The large-N `Warning:` plus `Continue? (y/n)` prompt is deleted: `refuse_large_run` is the only gate (Task 20 sets the threshold). `primes_1e<n>.txt` always written; `--show` prints each prime line. Keep the progress thread and its deadlock test. Docs go in `prime/prime-rs/CLAUDE.md` (Task 2).

- [ ] Failing tests, implement, run acceptance, commit (`feat(prime-rs): adopt the CLI contract`).

### Task 18: sq on the contract

```yaml-task
id: 18
description: sq-rs adopts the Rust contract shape; 13 read_line prompt paths and the display prompt removed
role: executor
model: sonnet
tdd: required
requirements: [R4, R6, R7, R8, R14, R16]
acceptance:
  - cmd: make -C sq/sq-rs test
    exit_code: 0
  - cmd: 'cd sq/sq-rs && cargo tarpaulin --out Stdout --fail-under 90'
    exit_code: 0
  - cmd: '! command grep -qE "(stdout|stderr)(\(\))?\.lock\(\)" sq/sq-rs/src/main.rs'
    exit_code: 0   # base: 1
  - cmd: 'test "$(command grep -c read_line sq/sq-rs/src/main.rs)" -le 1'
    exit_code: 0   # base: 13
max_retries: 3
files_touched: [sq/sq-rs/src/main.rs, sq/sq-rs/src/lib.rs, sq/sq-rs/tests/cli.rs, sq/sq-rs/CLAUDE.md]
depends_on: [6, 8]
parallel_group: cli-rust
```

`exponent` becomes `size`; keep the `N must be 1.` check (SMOKE_SIZE 1 is the only valid SIZE). Delete `read_line_from`, `prompt_exponent_with` and the display prompt; `sq_1e1.txt` always written (the file-idempotency test stays); `--show` prints each square line.

- [ ] Failing tests, implement, run acceptance, commit (`feat(sq-rs): adopt the CLI contract`).

### Task 19: twin-primes on the contract

```yaml-task
id: 19
description: twin-primes-rs adopts the Rust contract shape; SIZE becomes optional with the single terminal prompt; pair lines echo only with --show
role: executor
model: sonnet
tdd: required
requirements: [R4, R6, R7, R8, R14, R16]
acceptance:
  - cmd: make -C twin-primes/twin-primes-rs test
    exit_code: 0
  - cmd: 'cd twin-primes/twin-primes-rs && cargo tarpaulin --out Stdout --fail-under 90'
    exit_code: 0
  - cmd: '! command grep -qE "(stdout|stderr)(\(\))?\.lock\(\)" twin-primes/twin-primes-rs/src/main.rs'
    exit_code: 0   # base: 1
max_retries: 3
files_touched: [twin-primes/twin-primes-rs/src/main.rs, twin-primes/twin-primes-rs/src/lib.rs, twin-primes/twin-primes-rs/tests/cli.rs, twin-primes/twin-primes-rs/CLAUDE.md]
depends_on: [6, 8]
parallel_group: cli-rust
```

Today `digits: u32` is required (clap exit 2 with no argument) and `run(digits, out, err, dir)` has no input. It gains the contract's optional `size`, the TTY prompt and the max-15 check inside `run` (`Error: N must be between 1 and 15.`). `twin-primes_1e<n>.txt` always written; `--show` prints each pair line before the `Found <k> twin prime pairs` summary.

- [ ] Failing tests, implement, run acceptance, commit (`feat(twin-primes-rs): adopt the CLI contract`).

Orchestrator at wave close: uncontended `make test`, `make test-rust` (every log shows `cli_contract: <crate>: all cases pass`), `python3 scripts/render_crate_files.py --check`. A red result is a wave defect: re-dispatch the owning task with the log.

### Task 20: Measure and pin LARGE_RUN_THRESHOLD (serial, uncontended)

```yaml-task
id: 20
description: Measure each rewritten binary's LARGE_RUN_THRESHOLD on claude one probe at a time, set the 11 constants and pin tests, and report the evidence table
role: executor
model: sonnet
tdd: required
requirements: [R4, R5]
acceptance:
  - cmd: make test-rust
    exit_code: 0
  - cmd: bats tests/scripts/amicable.bats
    exit_code: 0   # release binary now built, so the rust cases run instead of skipping
max_retries: 2
files_touched: [amicable/amicable-rs/src/lib.rs, collatz/collatz-rs/src/lib.rs, e/e-rs/src/lib.rs, factorial/factorial-rs/src/lib.rs, fib/fib-rs/src/lib.rs, goldbach/goldbach-rs/src/lib.rs, perfect-numbers/perfect-numbers-rs/src/lib.rs, pi/pi-rs/src/lib.rs, prime/prime-rs/src/lib.rs, sq/sq-rs/src/lib.rs, twin-primes/twin-primes-rs/src/lib.rs]
depends_on: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
```

Serial, not in the wave: the wave runs 11 builds at once and the rayon crates (e, factorial, pi, prime) use 48 threads each, so a wave probe measures the wave. Each probe needs `uptime` load below 4. Per crate `make -C <c>/<c>-rs <c>`, then one Bash call per probe: `t=$(mktemp -d) && cd "$t" && timeout 61 /usr/bin/time -v <repo>/<c>/<c>-rs/target/release/<c> <SIZE> --yes </dev/null >/dev/null 2>time.txt; echo rc=$?; command grep -E 'Elapsed|Maximum resident|User time|System time' time.txt; cd / && rm -rf -- "$t"`. Exponent crates: ascend from SMOKE_SIZE to the range maximum; the first SIZE over 60 s or 8 GiB is the threshold, else `None`. pi, e, factorial: double until a probe exceeds, then bisect to within 10%; the threshold is the smallest failing SIZE probed. A timeout (rc 124) counts only with user+system CPU of at least 61 s; record threads (48 rayon, else 1). Pin test first (RED), then the constant. Report crate, SIZE, wall, max RSS, CPU, threads, rc.

- [ ] Probe, pin, run acceptance, commit (`feat(rust): pin measured large-run thresholds`); report the table.

Orchestrator after Task 20: append one R5 amendment per crate to the spec's `## Amendments` (SIZE, wall-clock, max RSS, CPU time), committed on the branch with the code.

### Task 21: Re-anchor mutants exclusions and pre-flight them in the mutants recipe

```yaml-task
id: 21
description: Add scripts/mutants_anchor_check.py, call it first in the rendered mutants recipe, re-anchor the 4 mutants.toml files, and cover stale/matching patterns in makefile.bats
role: executor
model: sonnet
tdd: required
requirements: [R17]
acceptance:
  - cmd: 'for c in amicable factorial goldbach perfect-numbers; do python3 scripts/mutants_anchor_check.py "$c/$c-rs" || exit 1; done'
    exit_code: 0
  - cmd: 'command grep -q "mutants_anchor_check.py" scripts/crate_templates/Makefile'
    exit_code: 0   # base: 1
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: bats tests/scripts/makefile.bats
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutants_anchor_check.py, scripts/crate_templates/Makefile, tests/scripts/makefile.bats, CLAUDE.md, amicable/amicable-rs/.cargo/mutants.toml, factorial/factorial-rs/.cargo/mutants.toml, goldbach/goldbach-rs/.cargo/mutants.toml, perfect-numbers/perfect-numbers-rs/.cargo/mutants.toml, amicable/amicable-rs/Makefile, collatz/collatz-rs/Makefile, e/e-rs/Makefile, factorial/factorial-rs/Makefile, fib/fib-rs/Makefile, goldbach/goldbach-rs/Makefile, perfect-numbers/perfect-numbers-rs/Makefile, pi/pi-rs/Makefile, prime/prime-rs/Makefile, sq/sq-rs/Makefile, twin-primes/twin-primes-rs/Makefile]
depends_on: [20]
```

`mutants_anchor_check.py <crate-dir>`: no `.cargo/mutants.toml` → exit 0; else `cargo mutants --list --no-config` in the dir (`MUTANTS_ANCHOR_CARGO` overrides `cargo` for bats), `re.search` each `exclude_re` (tomllib) over the listed lines; exit 1 naming every unmatched pattern; exit 2 when listing fails. Baseline in Global Constraints. Re-anchor by editing only line:col (N4); expect perfect-numbers' `src/main\.rs:92:*` and `:112:15`. Recipe: `@python3 ../../scripts/mutants_anchor_check.py .` before the `ulimit` block. makefile.bats builds `${BATS_TEST_TMPDIR}/repo/{scripts,x/x-rs}` with the rendered recipe and a stub `cargo`: a stale pattern fails naming it and never reaches `cargo mutants --timeout-multiplier`; a matching one reaches it. Root `CLAUDE.md` exclude_re line names the pre-flight.

- [ ] Failing bats, implement, re-anchor, run acceptance, commit (`feat(mutants): fail on stale exclude_re anchors`).

### Task 22: ADR-0033 and docs

```yaml-task
id: 22
description: Write ADR-0033 (Rust contract extends ADR-0030), index it, and document the Rust usage in root CLAUDE.md and the README CLI section (docs-only, no behaviour)
role: executor
model: sonnet
tdd: not-applicable
requirements: [R15]
acceptance:
  - cmd: 'test -n "$(ls docs/adr/0033-*.md 2>/dev/null)"'
    exit_code: 0   # base: 1
  - cmd: 'command grep -q "0030" docs/adr/0033-*.md'
    exit_code: 0
  - cmd: 'command grep -q "0033" docs/adr/README.md'
    exit_code: 0   # base: 1
  - cmd: 'command grep -qE "^#+ .*Rust CLI contract" README.md'
    exit_code: 0   # base: 1
  - cmd: 'command grep -q -- "--rust" CLAUDE.md'
    exit_code: 0   # base: 1
  - cmd: 'test "$(wc -c < CLAUDE.md)" -le 30000'
    exit_code: 0
max_retries: 2
files_touched: [docs/adr/0033-one-cli-contract-for-the-rust-programs.md, docs/adr/README.md, CLAUDE.md, README.md]
depends_on: [21]
```

ADR-0033 (Context, Decision, Consequences, Related, as ADR-0030): the shape in Global Constraints, the harness `--rust` mode run by every crate `make test`, serial threshold measurement, the anchor pre-flight. README: a `### Rust CLI contract` section after the Python one with the three usage lines and the measured thresholds. Root `CLAUDE.md`: one line for the contract and `cli_contract.py --rust`. No suite reads these files, so no `make test` gate.

- [ ] Write, run acceptance, commit (`docs: ADR-0033 Rust CLI contract`).

### Task 23: math-new-cli skill (ai-config, own PR)

```yaml-task
id: 23
description: Update ai-config's math-new-cli skill for rendered crate templates, the run() shape, the two constants and every hardcoded project list (docs-only, in an ai-config worktree)
role: executor
model: sonnet
tdd: not-applicable
requirements: [R21]
acceptance:
  - cmd: 'for p in crate_templates render_crate_files stdin_is_tty SMOKE_SIZE LARGE_RUN_THRESHOLD "cli_contract.py --rust"; do command grep -q -- "$p" .claude/skills/math-new-cli/SKILL.md || exit 1; done'
    exit_code: 0   # base: 1 (each pattern 0 matches at ai-config 27a1a7e4)
  - cmd: make check-skill-catalog
    exit_code: 0
max_retries: 2
files_touched: [.claude/skills/math-new-cli/SKILL.md]
depends_on: [22]
```

Paths are relative to an ai-config worktree, not math. The orchestrator first messages the ai-config session (`ListAgents`, `SendMessage`, git-workflow-020) naming this one file, then `git -C ~/git-repos/personal/ai-config worktree add .worktrees/math-new-cli-rust-contract -b docs/math-new-cli-rust-contract`, and dispatches with that path. Step 5's `main.rs` template becomes the Global Constraints shape; Step 3 says crate files come from `scripts/crate_templates/` via `render_crate_files.py --write` (add the crate to `CRATES`); list every hardcoded project list, derived by `git -C <math> grep -lE 'twin-primes|\b11\b' -- scripts tests .github Makefile AGENTS.md README.md CLAUDE.md` (at `a280493`: `scripts/pre-commit`, `scripts/pre-push`, `scripts/render_crate_files.py`, `tests/test_crate_uniformity.py`, `tests/test_rust_ci_jobs.py`, `tests/test_release_workflows.py`, `tests/test_tool_pins.py`, `tests/scripts/makefile.bats`, `tests/scripts/crate_build_target.bats`, `tests/test_release_sbom_monitor.py`, `.github/workflows/benchmarks.yml`, `.github/workflows/release-sbom-monitor-schedule.yml`, `AGENTS.md`).

- [ ] Edit, run acceptance, commit; ai-config PR with its own Phase 3, after P2 merges.

Orchestrator after Task 22 (math):

- [ ] Uncontended `make test`, `make test-rust`; `gh pr create --draft`; Phase 3; `gh pr ready`; `gh pr checks <n> --watch` until green.
- [ ] V1: each of the 11 `<crate>-rs` test-job logs contains `cli_contract: <crate>: all cases pass` (`gh run view <id> --log | command grep -c 'all cases pass'`). V3: each coverage log at least 90%.
- [ ] R20 re-measure: `gh run download <id> -n test-metrics-<crate>-rs` for all 11; if any test's time exceeds 15 s, widen per R20 (3× headroom) with an amendment before merge.
- [ ] Merge; clean up. V4: `d=/tmp/claude-1000/v4 && rm -rf -- "$d" && git clone -q "$(git remote get-url origin)" "$d" && make -C "$d" test-rust </dev/null` exits 0; delete `$d`. V6: the V5 script again.
- [ ] On master: delete the Backlog row "Uniform CLI contract for the 11 Rust binaries"; add a Backlog row that `mutation-pr.yml` and the `mutation-pr` skill call `cargo mutants` directly and so skip the anchor pre-flight; mark this plan Done in `docs/superpowers/README.md`; then Task 23.

## Non-goal check

One fresh reviewer (`~/.claude/skills/writing-plans/nongoal-check.md`) checked this plan against
N1-N7 on 2026-10-26. Verdicts: 6 CLEAR, 1 UNCLEAR.

- **N7 — UNCLEAR.** Quote: "Task 1: Add `*/*-rs/Cargo.toml` to `scripts.yml` `paths:` ... Task 2:
  Add `*/*-rs/CLAUDE.md` to `scripts.yml` `paths:` ... Task 8: `ci.yml` `paths:` gains
  `scripts/cli_contract.py`." The reviewer's reason: N7's letter covers jobs, step order and
  runners, but its list claims to be "the spec's only CI-visible changes", and a trigger path is
  CI-visible.
  - Resolution: a spec amendment. N7 now lists the three trigger additions alongside R12, R17 and
    R20. The plan text is unchanged; the trigger additions are needed so the R1 and R3 tests and
    the harness run where their subjects change.
- **N4 — CLEAR.** Task 21 edits only the line:col part of `exclude_re`. Task 15 keeps the `max_p`
  and `pn > limit` expressions that two perfect-numbers patterns anchor on.
- **N2 — CLEAR.** The exit-code changes do not change what SIZE means:
  - factorial non-numeric input goes from 1 to 2;
  - amicable and twin-primes range errors go from 2 to 1;
  - e and pi change from `usize` to `u64` with `try_from`.
- **N1, N3, N5, N6 — CLEAR.** No output file is renamed, no workspace is added, no floor is
  lowered, and no Python program file is touched.

Also amended at plan time: R12's `cargo build` becomes `rust-check.sh build`, so the build keeps the
wrapper's `CARGO_HOME`. A bare `cargo build` alternating with the wrapper rebuilt pi-rs on every
call (4.7-8.0 s).
