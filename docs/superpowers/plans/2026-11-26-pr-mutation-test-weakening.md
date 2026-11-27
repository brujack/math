# PR Mutation Gates See Test Weakening Implementation Plan

> **Status: DONE** — Implemented 2026-11-27 in math#252 (3790f49); bootstrap of `mutation-gate-items` as a required check is a follow-up PR (ADR-0048 §6).

spec: docs/superpowers/specs/2026-11-26-pr-mutation-test-weakening-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the per-PR mutation gates go red when a PR weakens tests, and add a required check (`mutation-gate-items`) that holds the levers which hide mutants until the operator signs them off.

**Architecture:**

- **Rust:** `mutation-pr` runs the whole crate on any crate change.
- **Python:** each test-touching dir gets a two-arm comparison in `mutation-py`:
  - the head arm is the sharded cosmic-ray session;
  - the base arm replays each head survivor through `cosmic_ray.mutating.mutate_and_test`, against the merge base's tests rewritten by an assertion-continuing runner.
- **Items:** a new `pull_request_target` workflow runs master's `scripts/mutation-gate-items.sh`. It lists content-keyed items; any item is red, and only the operator merges, by admin override.

**Tech Stack:** bash, Python 3 (stdlib `ast`, `unittest`), cosmic-ray 8.7.0, hypothesis 6.168.5, cargo-mutants 27.1.0, GitHub Actions, bats, ssh signing (`git verify-commit`, `gpg.format=ssh`).

## Global Constraints

- Every requirement's exact strings live in the spec's `## Requirements` (R1-R36). The spec is authoritative. Read the cited R items in full before writing code, and copy their messages byte for byte.
- Shell follows shell-006:
  - `#!/usr/bin/env bash`, and no `set -e` outside git hooks;
  - a sourcing guard;
  - `[[ ]]`, `${VAR}` and `printf`;
  - functions use `|| return 1`.
- Python must pass ruff (root `ruff.toml`), `ruff format --check` and root pyright (`standard`). Keep every function under the maintainability thresholds: ruff C901 and PLR09xx, which `maintainability-review` enforces in Phase 3.
- Every `git` call that builds paths or decides scope uses `env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git ...` (shell-007).
- Every bats `setup()` that makes a fixture repo runs `unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE` and redirects `HOME` to `BATS_TEST_TMPDIR` (tdd-009).
- N5: no gate or target writes a tracked file. Tests that use `sq/` copy it to a temp dir first, then assert the tracked `sq/` is byte-identical afterwards.
- N2: the only committed fixtures are the R18 canary pairs. The R34 planted files (`.cargo/config.toml`, `rust-toolchain.toml`, `parso.py`, `.gitattributes`) are generated in temp dirs inside the tests.
- N4: `scripts/mutation-gate-items.sh` never builds, imports or runs a file from the PR head.
- N7: no agent, script or workflow merges a PR whose `mutation-gate-items` or `mutation-pr` check is red; only the operator does, by admin override.
- Pins: cosmic-ray 8.7.0, hypothesis 6.168.5, cargo-mutants 27.1.0. `tests/test_tool_pins.py` requires one version per tool, and every workflow `uses:` pins a 40-hex SHA (`tests/test_workflow_actions_pinned.py`).
- Python `Makefile`s are rendered. Edit `scripts/crate_templates/python/Makefile`, then run `python3 scripts/render_crate_files.py --write`. Never hand-edit a rendered copy; `tests/test_crate_uniformity.py` fails on drift.
- Root `CLAUDE.md` is at 29,997 of 30,000 bytes (measured 2026-11-26). Task 19 pays for every byte it adds by compressing existing lines.

## Environment set-up (orchestrator, before Task 1)

```bash
cd /home/bruce/git-repos/personal/math
git fetch origin master
git worktree add .worktrees/pr-mutation-test-weakening -b feat/pr-mutation-test-weakening origin/master
cd .worktrees/pr-mutation-test-weakening
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install -r requirements-dev.txt mpmath==1.4.1 gmpy2==2.3.2 coverage==7.16.2 cosmic-ray==8.7.0 hypothesis==6.168.5 pytest==9.1.1 ruff==0.17.4
make install-hooks
```

Every task runs in `/home/bruce/git-repos/personal/math/.worktrees/pr-mutation-test-weakening` with that `.venv` active. The root `make test` takes several minutes, more than the 120 s auto-background threshold. Task gates are therefore scoped (`make lint` plus the task's own bats or unittest module). The orchestrator runs `make test < /dev/null` once after each dependency level, and once after Task 19.

## Verification (session level)

- **Repo gates:** `make lint && make test < /dev/null` exits 0 in the worktree; `make validate-plan PLAN=<this file>` exits 0.
- **Python weakening path on a `sq/` copy:** `python3 -m unittest tests.test_mutation_weakening_e2e -v` passes every R33 case. The tracked `sq/` is unchanged afterwards (`git status --porcelain sq/` empty).
- **Canary:** `python3 -m unittest tests.test_mutation_weakening_canary -v` reports `weakened: 1` for each of the four R18 pairs.
- **Items:** `scripts/mutation-gate-items.sh <base> <head>` over a fixture range prints each item kind as `uncleared item: ...` and exits red on any item (`tests/test_mutation_gate_items*.py`).
- **Edge cases:**
  - a cleared dir still runs the head arm (R19);
  - `no PR yet` in pre-push (R29);
  - a late `pull_request_target` context in `ci-gate.sh` (R36);
  - planted PR config never executes (R34).
- **Outside the diff:** V1-V9 run against the real PR and throwaway PRs (see "Verification obligations" below).

---

### Task 1: Rust whole-crate trigger and `py_test_dirs` in detect

```yaml-task
id: 1
description: Widen mutation-pr-detect.sh Rust selection (R1) and add the py_test_dirs output (R5), with bats cases (R32)
role: executor
model: sonnet
tdd: required
requirements: [R1, R5, R32]
acceptance:
  - cmd: bats tests/scripts/mutation_pr_detect.bats
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-pr-detect.sh, tests/scripts/mutation_pr_detect.bats]
depends_on: []
```

**Files:** `scripts/mutation-pr-detect.sh`, `tests/scripts/mutation_pr_detect.bats`.

- [ ] Write the R32 bats cases first, in the file's existing fixture-repo style.
  - These select the crate: a `tests/` file; a non-`.rs` file under `src/`; `.cargo/mutants.toml`; `build.rs`; a `Cargo.toml` `[[test]]` change.
  - These do not: a `[dependencies]` version change alone; a `[package] version` change alone.
  - For `py_test_dirs`, each of these selects the dir: added-only, deleted-only and whole-file deletion of `test_<module>.py`; a change to `cosmic-ray.toml`; a change to `mutants-equivalent.toml`.
  - A change to `<module>.py` alone does not select the dir.
- [ ] Run the cases and watch them fail.
- [ ] Implement:
  - The Cargo.toml table scan tracks the current `[section]` header. A line counts when it is a changed line outside `dependencies`, `dev-dependencies`, `build-dependencies`, and it is not the `version =` line inside `[package]`.
  - `py_test_dirs` comes from `git diff --numstat --no-renames`. Print `py_test_dirs=<space-separated sorted dirs>` (empty when none), after the existing outputs.
- [ ] Run the cases and watch them pass. Commit.

**Interfaces:** Produces `py_test_dirs=<dirs>` on stdout, the same `key=value` form as `rs_dirs`. Tasks 8 and 15 read it.

### Task 2: `mutation-pr-run.sh --whole`

```yaml-task
id: 2
description: Add --whole mode to mutation-pr-run.sh that runs a crate's whole set and exits non-zero on the R4 red conditions
role: executor
model: sonnet
tdd: required
requirements: [R4, R31]
acceptance:
  - cmd: bats tests/scripts/mutation_pr_run.bats
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-pr-run.sh, tests/scripts/mutation_pr_run.bats]
depends_on: []
```

**Files:** `scripts/mutation-pr-run.sh`, `tests/scripts/mutation_pr_run.bats`.

- [ ] Add failing bats cases that use the file's existing mocked `cargo`/`make`:
  - `--whole [--shard k/n --expect c] <crate-dir>` runs without `--in-diff`;
  - it is red on a missed mutant;
  - it is red on `caught+missed+timeout == 0`;
  - it is red on a missing `mutants.out/outcomes.json`;
  - it is red on a missing `mutants.out/exit-code`;
  - it is red on a failed baseline;
  - it is green on timeouts with at least one caught mutant.

  Verdicts go through `scripts/mutation-classify.sh` exactly as the sweep does, with limits `0 1` (ADR-0042).

- [ ] Implement `--whole`. The existing diff mode stays byte-identical in behaviour, and its existing tests pass unchanged.
- [ ] Commit.

**Interfaces:** Produces `scripts/mutation-pr-run.sh --whole [--shard <k>/<n> --expect <count>] <crate-dir>`, which Task 15 calls.

### Task 3: Assertion-continuing base runner

```yaml-task
id: 3
description: Write scripts/mutation_base_runner.py, the AST-rewriting unittest runner with record and compare modes (R11)
role: executor
model: sonnet
tdd: required
requirements: [R11]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_base_runner -v
    exit_code: 0
  - cmd: pyright scripts/mutation_base_runner.py tests/test_mutation_base_runner.py
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation_base_runner.py, tests/test_mutation_base_runner.py]
depends_on: []
```

**Files:** `scripts/mutation_base_runner.py`, `tests/test_mutation_base_runner.py`.

CLI: `python3 <path>/mutation_base_runner.py record <sig.json> <test_file.py>` and `... compare <sig.json> <test_file.py>`. It runs with cwd = the module dir, and inserts cwd at `sys.path[0]` after start-up.

- [ ] Write tests that each build a tiny module and test file in a temp dir:
  - a failing `assertEqual` followed by a later one: both sites are recorded;
  - an `AttributeError` raised inside `self.assertEqual(...)`: recorded as a site with type `AttributeError`, and the test continues;
  - a failing `with self.assertRaises(X)` block: continues;
  - a failing `with self.assertRaises(X) as cm` block, then `cm.exception.args`: no `AttributeError`, and the later assert still runs (placeholder exception);
  - a bare `assert`;
  - a loop assertion failing on iteration 1 in the recording: compare goes non-zero when iteration 3 fails too (n-th execution key);
  - a `subTest` failure, keyed by its params;
  - an error outside any assertion: outcome `error` with type and innermost line, no message;
  - a message-only difference at an already-failing site: compare exits 0;
  - a new site: compare exits non-zero;
  - each outcome kind (`pass`, `fail`, `error`, `skip`, `expected-failure`, `unexpected-success`) is recorded.
- [ ] Implement with an `ast.NodeTransformer` over the test file. Execute the rewritten code under the original filename so line numbers match, and run it with `unittest`. Hook the result object to build the signatures. Keep each function small (C901).
- [ ] Commit.

**Interfaces:** Produces exit 0 or 1 from `compare`, and a signature JSON of `{test_id: {outcome, sites: [[line, params, nth, exc_type]], error: [type, line] | null}}`. Tasks 5 and 6 consume both.

### Task 4: Hypothesis profile and preflight

```yaml-task
id: 4
description: Write scripts/mutation_hypothesis_profile.py that generates sitecustomize.py (R9) and runs the profile preflight (R10)
role: executor
model: sonnet
tdd: required
requirements: [R9, R10]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_hypothesis_profile -v
    exit_code: 0
  - cmd: pyright scripts/mutation_hypothesis_profile.py tests/test_mutation_hypothesis_profile.py
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation_hypothesis_profile.py, tests/test_mutation_hypothesis_profile.py]
depends_on: []
```

**Files:** `scripts/mutation_hypothesis_profile.py`, `tests/test_mutation_hypothesis_profile.py`.

- [ ] Write the failing tests:
  - `write <dir>` creates `<dir>/sitecustomize.py` holding exactly the R9 calls;
  - `preflight <dir>` runs a subprocess with `PYTHONPATH=<dir>`, in which two `@given` functions with the same `__qualname__` and different bodies draw the same first 10 examples, and exits 0;
  - with a deliberately broken sitecustomize (profile not loaded), preflight exits 1 and prints `hypothesis profile not active (hypothesis <version>)`;
  - a preflight that raises gives the same message.
- [ ] Implement. `function_digest` replacement: `hashlib.sha384(f.__qualname__.encode()).digest()`, assigned to `hypothesis.core.function_digest`.
- [ ] Commit.

**Interfaces:** Produces `python3 scripts/mutation_hypothesis_profile.py write <dir>` and `... preflight <dir>` (exit 0, or 1 with the R10 message). Task 7 calls both.

### Task 5: Weakening driver: base suite judgement

```yaml-task
id: 5
description: Start scripts/mutation_weakening.py with the unjudgeable checks (R8, R12) and the deleted/absent base test file rules (R17)
role: executor
model: sonnet
tdd: required
requirements: [R8, R12, R17]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_weakening -v
    exit_code: 0
  - cmd: pyright scripts/mutation_weakening.py tests/test_mutation_weakening.py
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation_weakening.py, tests/test_mutation_weakening.py]
depends_on: [3, 4]
```

**Files:** `scripts/mutation_weakening.py`, `tests/test_mutation_weakening.py`.

Subcommand `judge --dir <dir> --base <sha> --work <dir>`:

- materializes `test_<module>.py` from the merge base with `git show` into `<dir>/test_<module>_base.py`;
- applies R8, then R17;
- records signatures twice with `mutation_base_runner.py record` (timeout = merge-base toml `timeout`);
- applies R12.

The function is pure over its inputs, so tests use temp git repos.

- [ ] Write the failing tests, one per R8, R12 and R17 message, with these cases:
  - a toml with a pytest `test-command`;
  - an import-breaking rename (`_FailedTest`);
  - a per-test `setUp` error;
  - a sleep past the timeout, after which no child process remains (`psutil` is not available, so check with `os.kill(pid, 0)` on the recorded pid);
  - two differing recordings;
  - a deleted test file;
  - no base file, which prints `no base test file: weakening check skipped` and exits 0 with nothing to replay.
- [ ] Implement. The base file is written only after the caller says the head session finished; the caller passes `--after-head`, and Task 7 orders this.
- [ ] Commit.

**Interfaces:** Produces `python3 scripts/mutation_weakening.py judge ...`, which exits 0 (judgeable; recording at `<work>/base-sig.json`), 1 (red, message on stdout) or 3 (skipped, no base file).

### Task 6: Weakening driver: replay, verdict, completeness

```yaml-task
id: 6
description: Add replay through mutate_and_test (R13), the timeout re-run (R14), the weakened verdict (R15) and shard completeness with cleared-dir handling (R19, R27)
role: executor
model: sonnet
tdd: required
requirements: [R13, R14, R15, R19, R27]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_weakening -v
    exit_code: 0
  - cmd: pyright scripts/mutation_weakening.py tests/test_mutation_weakening.py
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation_weakening.py, tests/test_mutation_weakening.py]
depends_on: [5, 10]
```

**Files:** as in Task 5.

Subcommand `replay --dir <dir> --session <head sqlite> --shard <k>/<n> --planned <a> --base <sha> --work <dir> [--pr <n>]`:

1. Read this shard's survivors and their `MutationSpec`s from the head session (cosmic-ray `WorkDB`).
2. Ask `mutation_gate_clearance.cleared_for_dir(...)` (Task 10). When the dir is cleared, print `cleared by Mutation-Gate-Reviewed <commit>` and skip only the replay.
3. Otherwise call `cosmic_ray.mutating.mutate_and_test` per survivor with the base runner `compare` command and the merge-base timeout, and apply R14.
4. Print R15 and R19 output.

- [ ] Write the failing tests. Mock `mutate_and_test` through an injectable seam, and use a real sqlite session built with cosmic-ray's `WorkDB` API:
  - `killed`, `survived` and `incompetent` → `replay failed: <outcome>`;
  - an exception;
  - a timeout re-run where base kills and head survives → counted;
  - a timeout re-run where both kill → not counted;
  - the exact `weakened:` block, with its repro and clearance-command lines;
  - `shard incomplete` when a job is skipped;
  - a cleared dir: no replay, exempt count, head-arm result still honoured.
- [ ] Implement, then commit.

**Interfaces:**

- Consumes `cleared_for_dir(repo, base_sha, head_sha, pr, dir) -> str | None` (the commit sha) from Task 10.
- Produces the `replay` subcommand: exit 0 green, 1 red.

### Task 7: `mutants-weakening` Makefile target

```yaml-task
id: 7
description: Add the mutants-weakening target to the Python Makefile template and render it to all ten Python dirs (R7, R31)
role: executor
model: sonnet
tdd: required
requirements: [R7, R31]
acceptance:
  - cmd: bats -f weakening tests/scripts/makefile.bats
    exit_code: 0
    stdout_match: 'ok [0-9]+ .*weakening'
  - cmd: python3 -m unittest tests.test_crate_uniformity -v
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/python/Makefile, amicable/Makefile, collatz/Makefile, descartes/Makefile, e/Makefile, factorial/Makefile, fib/Makefile, perfect-numbers/Makefile, pi/Makefile, sq/Makefile, triangle/Makefile, tests/scripts/makefile.bats]
depends_on: [4, 6]
```

**Files:** the template, the ten rendered `Makefile`s (via `render_crate_files.py --write`) and `tests/scripts/makefile.bats`.

Target: `mutants-weakening BASE=<sha> MUTANT_SHARD=<k>/<n>`, or `JOB=<job id>`.

- It first copies `<module>.py`, `test_<module>.py` and `cosmic-ray.toml` into a per-run work dir `.mutants-tmp/weakening-<pid>/`, and passes that copy as every `--dir`. So neither the head session, nor `judge` (which writes `test_<module>_base.py`), nor `mutate_and_test` ever writes the tracked dir (N5).
- It runs inside `MUTANTS_BODY`'s sandbox and `MUTANTS_CAP`.
- Environment: `TMPDIR=.mutants-tmp/...`, `PYTHONHASHSEED=0`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONPATH` set to only the generated sitecustomize dir.
- Order of steps:
  1. `write` the profile;
  2. `preflight`;
  3. the head session for the shard;
  4. `judge --after-head`;
  5. `replay`.
- Missing `BASE` errors like `DIFF_GUARD`.
- It writes nothing tracked, and `mutants-clean` removes its files.

- [ ] Write the failing bats cases, with a mocked cosmic-ray as the existing `mutants-diff` cases use:
  - missing `BASE` → exit non-zero with the message;
  - env values present (assert from a mock that dumps its env);
  - step order;
  - `JOB=` passes through;
  - `git status --porcelain <dir>` is empty after a run.
- [ ] Implement in the template, render with `python3 scripts/render_crate_files.py --write`, and commit.

**Interfaces:** Produces `make -C <dir> mutants-weakening BASE=<sha> MUTANT_SHARD=<k>/<n> [PR=<n>]`. Tasks 9, 15 and 16 call it.

### Task 8: Python planner for `py_test_dirs`

```yaml-task
id: 8
description: Plan py_test_dirs as whole-module shards sized by suite time and mutant count (R6)
role: executor
model: sonnet
tdd: required
requirements: [R6]
acceptance:
  - cmd: bats tests/scripts/mutation_pr_plan_python.bats
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-pr-plan-python.sh, tests/scripts/mutation_pr_plan_python.bats]
depends_on: [1]
```

- [ ] Write the failing bats cases for `n = min(40, max(10, ceil(K * s / 600)))`. `K` is the whole-module job count after the head prune, and `s` is the timed head suite (mock both):
  - K=100, s=1 → 10;
  - K=3000, s=5 → 25;
  - K=10000, s=10 → 40;
  - K=0 → 10.

  Dirs only in the changed-line set keep today's plan unchanged (N6).

- [ ] Implement, emitting matrix entries `{dir, shard, n, mode: weakening}` beside the existing ones. Commit.

**Interfaces:** Produces matrix rows with `mode` = `weakening` or `diff`. Task 15 routes each row by it.

### Task 9: End-to-end weakening test on a `sq/` copy

```yaml-task
id: 9
description: Write the R33 end-to-end cases over a temp copy of sq/ using the real cosmic-ray and base runner
role: executor
model: sonnet
tdd: required
requirements: [R33]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_weakening_e2e -v
    exit_code: 0
  - cmd: git status --porcelain sq/
    exit_code: 0
    stdout_match: '^$'
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [tests/test_mutation_weakening_e2e.py]
depends_on: [7]
```

Model the file on `tests/test_mutation_pr_python_e2e.py`. Each case copies `sq/` and a temp git history (base commit, head commit) into `tempfile.mkdtemp()`, then runs `make -C <copy> mutants-weakening BASE=<base> JOB=<job>` for the single relevant job, keeping runtime bounded. Skip with a printed reason when `cosmic_ray` is not importable outside CI.

- [ ] Write one test method per clause of R33, using its wording as the method docstring. Assert:
  - the exact `weakened: 1` / `weakened: 0` lines;
  - `base suite unjudgeable`;
  - `replay failed`;
  - `shard incomplete`;
  - `hypothesis profile not active`;
  - the R16 red;
  - no live process after the sleep case;
  - the tracked `sq/` files are byte-identical (sha256 before and after) in `tearDown`.
- [ ] Run them, and fix only test wiring. A real driver defect is a blocker that goes back to Task 5 or 6. Commit.

### Task 10: Clearance verification and allowed signers

```yaml-task
id: 10
description: Write scripts/mutation_gate_clearance.py (trailer parsing and git verify-commit, R26 clearance half) and the allowed-signers file with its type test (R28)
role: executor
model: sonnet
tdd: required
requirements: [R26, R28]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_gate_clearance tests.test_mutation_gate_allowed_signers -v
    exit_code: 0
  - cmd: pyright scripts/mutation_gate_clearance.py tests/test_mutation_gate_clearance.py tests/test_mutation_gate_allowed_signers.py
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation_gate_clearance.py, tests/test_mutation_gate_clearance.py, .github/mutation-gate-allowed-signers, tests/test_mutation_gate_allowed_signers.py]
depends_on: []
```

`.github/mutation-gate-allowed-signers` holds one line: the operator's key from the orchestrator, formatted as `bjackson-mutation-gate namespaces="git" sk-ssh-ed25519@openssh.com AAAA...`. The principal is a fixed label, not an email address.

- [ ] Write the failing tests.
  - R28: every non-comment line uses key type `sk-ssh-ed25519@openssh.com` and has no `no-touch-required`. Fixture lines with `ssh-ed25519` or `no-touch-required` fail the checker function.
  - Clearance, using temp repos with commits signed by a throwaway `ssh-keygen -t ed25519` key listed in a temp signers file:
    - a valid trailer clears its target;
    - an unsigned commit → `trailer ignored: <sha>: unsigned`;
    - a key absent from the signers file → `trailer ignored: <sha>: signature not accepted`;
    - another PR's number → `trailer ignored: <sha>: names #<n>`;
    - another target does not clear;
    - a 9-character reason does not clear;
    - two lines in one commit clear two targets;
    - `cleared_for_dir` returns None when `<module>.py` or `test_<module>.py` changed after the commit.
- [ ] Implement:
  - `verify(repo, sha, signers) -> bool` runs `git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=<signers> verify-commit <sha>`;
  - `trailers(repo, base, head, pr, signers) -> list[Clearance]`;
  - `cleared_for_dir(...)`;
  - the R26 remedy-command printer.
- [ ] Commit.

**Interfaces:** Produces `Clearance(sha: str, target: str, reason: str)`, `trailers(...)`, `cleared_for_dir(...) -> str | None` and `remedy_command(pr: int, targets: list[str], key: str) -> str`. Tasks 6, 11 and 18 consume them.

### Task 11: Items script: framework, Python items, gate items

```yaml-task
id: 11
description: Write scripts/mutation-gate-items.sh and scripts/mutation_gate_items.py with git-show materialization, Python items (R22), gate items (R25), clearance output (R26) and the cosmic-ray invocation rule (R21)
role: executor
model: sonnet
tdd: required
requirements: [R21, R22, R25, R26, R34]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_gate_items -v
    exit_code: 0
  - cmd: pyright scripts/mutation_gate_items.py tests/test_mutation_gate_items.py
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-gate-items.sh, scripts/mutation_gate_items.py, tests/test_mutation_gate_items.py]
depends_on: [10]
```

The `.sh` is a thin wrapper: `mutation-gate-items.sh <base-sha> <head-sha> [--pr <n>]`. The Python does the work.

- PR files are written only with `git show <sha>:<path>`, into a scratch tree outside the repo.
- Every subprocess runs with `cwd` set to a fresh empty temp dir.
- `cosmic-ray init` runs on a config the script generates, with an absolute `module-path` and the test-command never taken from the PR.
- The Python items use a tolerant copy of `cosmic_ray_prune.py`'s matcher (import it and wrap it; do not fork it).

- [ ] Write the failing tests over temp repos built from a `sq/` copy:
  - a new equivalents entry, a `variant` change and a duplicated entry are items;
  - a pure line shift of an entry is not;
  - a legitimately edited entry line does not crash;
  - a retarget onto an equal operator elsewhere in the function is an item;
  - a `cosmic-ray.toml` `timeout` change is keyed by its new value;
  - a changed `mutation-pr-detect.sh`, allowed-signers file, `mutants` recipe or a variable it references → `gate` items;
  - another workflow with job `mutation-pr` → a `gate` item;
  - a non-recipe `Makefile` change and a `taiki-e/install-action` SHA-and-comment bump are not items;
  - a planted `parso.py` in the PR dir leaves no marker file;
  - `.gitattributes` `export-ignore` does not hide an equivalents file;
  - the red output carries the R26 command;
  - a verified commit whose tree holds an earlier value does not clear.
- [ ] Implement, then commit.

**Interfaces:**

- Produces `Item(target: str, kind: str, key: tuple[str, ...])`, `collect(repo, base, head) -> list[Item]` with a registry that Tasks 12 and 13 extend via `register(kind, fn)`.
- The CLI exit codes are 0 (no uncleared items) and 1 (red).

### Task 12: Items: Rust exclusions and cargo invocation rules

```yaml-task
id: 12
description: Add Rust exclusion items (R23) using cargo mutants --list under the R21 invocation rules, with planted-config security tests (R34)
role: executor
model: sonnet
tdd: required
requirements: [R21, R23, R34]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_gate_items_rust -v
    exit_code: 0
  - cmd: pyright scripts/mutation_gate_items.py tests/test_mutation_gate_items_rust.py
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation_gate_items.py, tests/test_mutation_gate_items_rust.py]
depends_on: [11]
```

Invocation: `cargo mutants --list --json -d <scratch>/<crate>` and the same with `--no-config`, with:

- cwd outside the scratch tree;
- `RUSTUP_TOOLCHAIN` set to the toolchain the crate templates pin;
- `CARGO_HOME` set to a fresh empty dir;
- no `cargo metadata` without `--no-deps`.

The excluded set is the `--no-config` listing minus the configured one, matched by `name`. Keys follow R23.

- [ ] Write the failing tests on a copy of `amicable/amicable-rs`:
  - a new `exclude_re` → an item;
  - a pure line shift of `exclude_re` targets → not an item;
  - an `additional_cargo_test_args` change → an item keyed by its value.

  Planted in the PR tree, each of these leaves no marker file:
  - `.cargo/config.toml` `[alias] mutants = ["run", ...]` with a `build.rs` that writes a marker;
  - `rustc-wrapper`;
  - `rust-toolchain.toml` with an absolute `path`.

- [ ] Implement, then commit.

### Task 13: Items: hidden code

```yaml-task
id: 13
description: Add hidden-code items outside cfg(test) modules (R24) with the R34 spelling and macro cases
role: executor
model: sonnet
tdd: required
requirements: [R24, R34]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_gate_items_hidden -v
    exit_code: 0
  - cmd: pyright scripts/mutation_gate_items.py tests/test_mutation_gate_items_hidden.py
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation_gate_items.py, tests/test_mutation_gate_items_hidden.py]
depends_on: [12]
```

- [ ] Write the failing tests. These are items:
  - `#[mutants::skip]` spaced, split across lines, and with an inner comment;
  - `macro_rules!`;
  - `vec![a * b + 1][0]`;
  - `dbg!(a * b)`;
  - `vec![match a { 0 => 7, _ => 3 }][0]`;
  - `vec![S { a, ..Default::default() }][0]`;
  - a new function with no mutant in the head `--no-config` listing.

  These are not items:
  - `prop_assert!` inside `#[cfg(test)] mod tests`;
  - `println!("{}", x)`.

- [ ] Implement:
  - a token scanner that strips comments and strings and tracks `#[cfg(test)] mod` spans;
  - a macro-argument allow-set of literals, identifiers, paths, `.` field/method access, `&` and `,`.
- [ ] Commit.

### Task 14: `mutation-gate-items` workflow

```yaml-task
id: 14
description: Add .github/workflows/mutation-gate-items.yml on pull_request_target running base-branch code only (R20)
role: executor
model: sonnet
tdd: required
requirements: [R20]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_gate_items_workflow -v
    exit_code: 0
  - cmd: python3 -m unittest tests.test_workflow_actions_pinned tests.test_tool_pins -v
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/mutation-gate-items.yml, tests/test_mutation_gate_items_workflow.py]
depends_on: [11]
```

- [ ] Write failing `yaml.safe_load` tests:
  - trigger `pull_request_target` only, with no `paths`;
  - `permissions: {contents: read}`;
  - no `secrets.` reference anywhere;
  - job id and name `mutation-gate-items`;
  - checkout `ref` is the base sha, with `persist-credentials: false`;
  - a step fetches `refs/pull/<n>/head` objects without checking them out;
  - the run step invokes `scripts/mutation-gate-items.sh "${BASE_SHA}" "${HEAD_SHA}" --pr "${PR}"`, with values passed through `env:` and never interpolated into `run:`;
  - the cargo-mutants and cosmic-ray installs are pinned.
- [ ] Write the workflow, then commit.

### Task 15: `mutation-pr.yml` wiring

```yaml-task
id: 15
description: Wire whole-crate Rust planning (R2, R3), py_test_dirs weakening shards (R6 timeout, R16, R19, R31), the canary job (R18) and concurrency (R30) into mutation-pr.yml
role: executor
model: sonnet
tdd: required
requirements: [R2, R3, R16, R18, R30]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_workflows -v
    exit_code: 0
  - cmd: python3 -m unittest tests.test_workflow_actions_pinned tests.test_workflow_continue_on_error -v
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/mutation-pr.yml, tests/test_mutation_workflows.py]
depends_on: [1, 2, 7, 8, 16]
```

- [ ] Write the failing tests in `tests/test_mutation_workflows.py`:
  - `mutation-rs-plan` calls `mutation-rs-plan.sh --whole` and never `--in-diff` for a selected crate;
  - a fault unit fails the `mutation-pr` aggregator, which names the crate and cause;
  - `mutation-rs` calls `mutation-pr-run.sh --whole`;
  - `mutation-py` has `timeout-minutes: 60`, and routes `mode: weakening` rows to `make -C <dir> mutants-weakening BASE=... MUTANT_SHARD=... PR=...` while `diff` rows keep the existing path;
  - the R16 changed-line check still runs for weakening dirs;
  - the `mutation-py-canary` job runs the four fixture pairs;
  - top-level `concurrency` equals the R30 value.
- [ ] Edit the workflow, then commit.

### Task 16: Canary fixture pairs

```yaml-task
id: 16
description: Commit the four R18 canary fixture pairs and a local test that runs each through the weakening path expecting weakened 1
role: executor
model: sonnet
tdd: required
requirements: [R18]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_weakening_canary -v
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [tests/fixtures/mutation_weakening/, tests/test_mutation_weakening_canary.py]
depends_on: [7]
```

There are four pairs under `tests/fixtures/mutation_weakening/<case>/`, each holding `sq.py` (a small module), `test_sq_base.py`, `test_sq_head.py`, `cosmic-ray.toml` and `expected.txt` (the expected job's operator and occurrence). The cases:

- `drop`: head drops an assertion;
- `mask`: an obsolete first assertion masks a later one;
- `raises`: a failing `with self.assertRaises` block masks a later one;
- `raises_cm`: a failing `as cm` block is followed by `cm.exception` checks.

- [ ] Write the test first. It builds a temp repo per pair (base commit with `test_sq_base.py` as `test_sq.py`, head commit with `test_sq_head.py`), runs `mutants-weakening`, and requires `weakened: 1` naming the job in `expected.txt`. Then write the fixtures until it passes. Commit.

### Task 17: `ci-gate.sh` waits for required contexts

```yaml-task
id: 17
description: Make ci-gate.sh wait for every branch-protection required context on the head SHA, including pull_request_target runs (R36)
role: executor
model: sonnet
tdd: required
requirements: [R36]
acceptance:
  - cmd: bats tests/scripts/ci_gate.bats
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/ci-gate.sh, tests/scripts/ci_gate.bats]
depends_on: []
```

- [ ] Write the failing bats case with the `gh` mock. `repos/:o/:r/branches/master/protection/required_status_checks` returns `mutation-gate-items`. The first poll's check-runs lack it and every other run is complete. The second poll adds it as `success`. The gate must not report before the second poll. A variant that never registers it times out red.
- [ ] Implement, then commit.

### Task 18: Pre-push advisory listing

```yaml-task
id: 18
description: Make scripts/pre-push print gate items and their clearance for item-relevant pushes without failing or running mutants (R29)
role: executor
model: sonnet
tdd: required
requirements: [R29]
acceptance:
  - cmd: bats tests/scripts/pre_push.bats
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/pre-push, tests/scripts/pre_push.bats]
depends_on: [11]
```

- [ ] Write the failing bats cases:
  - a push touching `sq/mutants-equivalent.toml`, with mocked `gh pr view` returning a PR number, prints the items and a cleared/uncleared state, and exits 0;
  - with `gh pr view` failing, it prints `no PR yet: sign after opening it`;
  - with the items script exiting 1, the push still exits 0;
  - an unrelated push prints nothing;
  - no `cosmic-ray` or `cargo mutants` mock is ever called.
- [ ] Implement, then commit.

### Task 19: Docs, ADR, CLAUDE.md, Backlog row

```yaml-task
id: 19
description: Write ADR-0048, update root CLAUDE.md within the 30000-byte ceiling, and remove the Backlog row (R35); docs-only, tdd not applicable
role: executor
model: sonnet
tdd: not-applicable
requirements: [R35]
acceptance:
  - cmd: python3 scripts/claude_md_budget.py HEAD
    exit_code: 0
  - cmd: '[ "$(wc -c < CLAUDE.md)" -le 30000 ]'
    exit_code: 0
  - cmd: '! command grep -q "PR mutation gates miss test-only weakening" docs/superpowers/README.md'
    exit_code: 0
  - cmd: 'command grep -q "mutation-gate-items" CLAUDE.md'
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [docs/adr/0048-pr-mutation-gates-see-test-weakening.md, docs/adr/README.md, CLAUDE.md, docs/superpowers/README.md]
depends_on: [9, 13, 14, 15, 17, 18]
```

- ADR-0048 has Context, Decision, Consequences and Related. It covers:
  - the whole-crate rule;
  - the two-arm Python check;
  - the items job and its invocation rules;
  - the absence of in-band clearance (red items merge only by the operator's admin override; N7 is instruction-only);
  - the bootstrap order;
  - the repro commands.
- `docs/adr/README.md` gets its row.
- `CLAUDE.md` byte budget: 29,997 of 30,000 bytes before this task.
  - Replace the two lines starting "Per-PR Python gate" and "`mutation-pr.yml`: `mutation-rs-plan`" with shorter lines that state the whole-crate rule, `mutants-weakening`, `mutation-gate-items` and the admin-override-only rule.
  - Point detail at `→ ai-config/docs/knowledge/math-testing-policy.md § PR test-weakening gate`, which the orchestrator creates in ai-config before Phase 3 (below).
  - Measure with `wc -c` after each edit.
- Remove the Backlog row from `docs/superpowers/README.md`.

## Orchestrator steps after Task 19 (before Phase 3)

1. Run `make test < /dev/null` once in the worktree, and paste the summary line.
2. **ai-config knowledge heading.** Message the ai-config session first (`ListAgents`, `SendMessage`). Then add `## PR test-weakening gate` to `ai-config/docs/knowledge/math-testing-policy.md`, docs-only to ai-config master. It holds the detail moved out of `CLAUDE.md`. The pointer must resolve before branch code review.
3. **V6.** Run the weakening path locally over the 32 commits since 2026-09-26 that changed a module and its test file. Print the per-commit counts the spec names. Any false `weakened` result is a design fix before merge.
4. **V8.** Run `scripts/mutation-gate-items.sh` over the last 100 merged PRs, and report counts by item kind to the operator. It must show 1 Rust exclusion item for math#204, an `additional_cargo_test_args` item for math#246, and 0 items for math#229 and math#152.
5. **Open the PR as a draft** (`gh pr create --draft`), and watch `gh pr checks <n> --watch`.
6. **V1, V2, V3, V5.** Open throwaway draft PRs from separate branches, record the results and wall times, then close them and delete their branches.
7. **V9.** Record the PR's own run times, and the measured or projected zeta-rs whole-crate time.
8. Run Phase 3 (`finishing-a-development-branch`), then `gh pr ready`.

## Verification obligations after merge (bootstrap)

1. The operator adds `mutation-gate-items` to branch protection with expected source GitHub Actions, and sets the same expected source on `mutation-pr` and `secret-scan`.
   Before that, confirm on a live PR that the `pull_request_target` check run of `mutation-gate-items` is returned by `gh api repos/brujack/math/commits/<PR head sha>/check-runs` (not only on the base SHA); if it is not, `ci-gate.sh` would time out on every PR once the context is listed, so stop and re-plan.
   Then a small follow-up PR adds `mutation-gate-items` to `.github/required-status-checks` (R36 amendment), and V4 confirms the file equals `gh api repos/brujack/math/branches/master/protection/required_status_checks --jq .contexts`.
2. **V4.** Use throwaway draft PRs:
   - add one `[[equivalent]]` entry to `sq/mutants-equivalent.toml`: `mutation-gate-items` red naming it, not merged by `auto-merge`, mergeable only by the operator's admin override;
   - delete the items step from `mutation-pr.yml`: still red in `mutation-gate-items`;
   - a posted success status for `mutation-gate-items` does not make the PR mergeable.
3. Mark the plan Done in `docs/superpowers/README.md`.

## Non-goal check

Reviewer verdicts (2026-11-26): N1, N2, N3, N4 and N7 are CLEAR; N5 and N6 are UNCLEAR; nothing is in CONFLICT.

- **N5 UNCLEAR.**
  - Reviewer: in Task 6, `mutate_and_test` rewrites `<module>.py` in place, and in Task 5, `judge` writes `test_<module>_base.py` into `--dir`. When `make -C sq mutants-weakening` runs on a real checkout, both writes land in the tracked `sq/` unless the sandbox works on a copy. The plan claims the sandbox but never says it copies the dir.
  - Resolution: plan revision in Task 7.
    - Before: "It runs inside `MUTANTS_BODY`'s sandbox and `MUTANTS_CAP`."
    - After: a first bullet copies `<module>.py`, `test_<module>.py` and `cosmic-ray.toml` into `.mutants-tmp/weakening-<pid>/` and passes that copy as every `--dir`, and a bats case asserts `git status --porcelain <dir>` is empty after a run.
- **N6 UNCLEAR.**
  - Reviewer: Task 15 sets `timeout-minutes: 60` on the shared `mutation-py` job and adds a top-level R30 `concurrency`. Both also reach `diff` rows, the dirs that are not in `py_test_dirs`.
  - Measured: `mutation-py` is at `timeout-minutes: 30` today.
  - R6 and R30 are job-level and workflow-level settings, so neither can be scoped per matrix row.
  - Resolution: the spec's `## Amendments` now limits N6 to the changed-line gate's verdicts.
