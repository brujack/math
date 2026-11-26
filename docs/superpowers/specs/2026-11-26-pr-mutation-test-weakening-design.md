# PR mutation gates see test weakening

- **Date:** 2026-11-26 (revised after Multi-Lens Review rounds 1 and 2)
- **Backlog row closed:** "PR mutation gates miss test-only weakening (Rust and Python)" (P2)
- **Related:** ADR-0042 (Rust sweep holds zero missed), ADR-0044 (per-PR Python gate), ADR-0046
  (shard the Rust runs), `specs/2026-11-05-worldclass-slice5-rust-pr-mutation-ratchet-design.md`,
  `specs/2026-11-07-worldclass-slice8-python-pr-mutation-gate-design.md` ("Known gap, not closed here")

## Summary

Both per-PR mutation gates judge only mutants on lines a PR changes. A PR that deletes or weakens
tests changes no production line, so it is never judged, and a PR can exempt the mutant it exposes.
This spec closes both holes:

- **Rust:** any change to a crate's `src/`, `tests/`, `.cargo/` or the test-shaping parts of its
  `Cargo.toml` runs every mutant in that crate, held to the sweep's rule (0 missed, timeouts green).
- **Python:** a change to `test_<module>.py`, `cosmic-ray.toml` or `mutants-equivalent.toml` mutates
  the whole head module and runs the head tests on every mutant; each shard then replays its own head
  survivors under the base tests, with the head arm's exact mutation specs, sandbox, timeout and
  deterministic hypothesis. A mutant the base tests kill and the head tests do not is a weakening.
  A base suite that cannot be judged is red, never green.
- **Exemptions:** what a PR newly exempts is computed from ground truth (the mutant listing or the
  prune result under the base versus the head configuration), and is red unless the operator clears
  that target with a terminal-confirmed `Mutation-Gate-Reviewed:` trailer.

## Why

Measured 2026-11-26 on master `0bc607f`:

- `scripts/mutation-pr-detect.sh` puts a Python dir in `py_src_dirs` only when `git diff --numstat`
  shows added lines in `<dir>/<module>.py` (lines 15-18, 37). A PR touching only `test_<module>.py`
  runs no Python mutant.
- A Rust crate is selected only when a changed path matches `<crate>/src/**/*.rs` (line 66), and its
  mutants are filtered by `--in-diff`. A hunk inside a `#[test]` yields `INFO No mutants to filter`,
  exit 0 (slice 5 spec, 2026-11-05). A change under `<crate>/tests/` (13 crates have one) or to
  `Cargo.toml` (`autotests`, `[[test]]`) selects no crate.
- The 90% coverage floors catch a large test deletion but not a weakened assertion: coverage is
  unchanged when `assertEqual(x, 5)` becomes `assertIsNotNone(x)`.
- The Rust monthly sweep holds 0 missed (ADR-0042; run 45479226540 green), so a Rust weakening is
  reported within a month, after merge. The Python sweep carries about 1,250 open survivors (issue
  #184: pi 712, e 736), so a new Python survivor is never reported at all.
- The exemption channels are looser than the gate: Python `mutants-equivalent.toml` entries are pruned
  before the session runs (template `Makefile` lines 101-103), `cosmic-ray.toml`'s `test-command`
  chooses which tests run, Rust `.cargo/mutants.toml` holds `exclude_re` and zeta's
  `additional_cargo_test_args = ["--", "--skip", "e2e_"]`, and `#[mutants::skip]` removes mutants. The
  existing drift tests check only stale or non-matching entries.

Agents write most of the tests here, weakening a test to make a gate pass is on the executor FORBIDDEN
list, and auto-merge lands a green PR without review. No weakening incident in this repo has been
measured; the operator chose the semantic design over a static assertion-line rule (2026-11-26).

## Facts this design rests on (measured 2026-11-26)

- **Rust whole-crate cost.** Sweep run 45479226540 (all 13 crates, 2,221 mutants, 37 shards at B = 75)
  took 9 minutes of wall time; longest shard 7.4 min (descartes-rs). zeta-rs: 748 mutants at about
  29.6 s each, 10 shards of about 37 min against `mutation-rs`'s `timeout-minutes: 60`. The Rust trigger
  fires on the same 17 of the last 100 PRs as today's; a one-line zeta edit goes from about 1 to about
  37 min.
- **Planner.** `scripts/mutation-rs-plan.sh --whole <crate-dir>...` plans every mutant and emits a fault
  unit `{"slug":"<name>-plan",...,"fault":"<cause>"}` instead of failing.
- **cargo-mutants listing.** `cargo mutants --list --json` lists the mutants a configuration admits,
  and `--config <FILE>` points it at another config file, so the mutants a head config newly excludes
  are the difference between two listings of the head source. `#[mutants :: skip]` and a line-split
  `#[mutants::` / `skip]` both suppressed every mutant of their functions under 27.1.0 while
  `grep -c 'mutants::skip'` returned 0.
- **Python whole-module size** (`cosmic-ray init` on master): descartes 3663, triangle 3113, pi 1828,
  e 1621, perfect-numbers 679, factorial 500, collatz 420, amicable 252, fib 232, sq 164. Local suite
  run times: descartes 7.0 s, e 5.5 s, pi 4.5 s, sq 1.0 s, triangle 0.8 s; pi on CI about 5.9 s per
  mutant (run 42157892557).
- **Python trigger rate.** Of the last 100 merged PRs, 18 changed a `test_<module>.py` and 16 of those
  also changed the module; descartes is in 5 of the last 9 such commits.
- **Replay identity and timeout.** `cosmic_ray.mutating.mutate_and_test(mutations, test_command,
  timeout)` applies stored `MutationSpec`s and runs `cosmic_ray.testing.run_tests`, which starts the
  tests in a new session and kills the whole process group on timeout, returning `KILLED`. Replaying
  every one of sq's 164 session jobs through it with each job's stored spec gave a diff identical to
  the session's in 164 of 164, and `sq.py` was restored. The CLI `cosmic-ray mutate-and-test` passes
  `timeout=None`, and an outer `timeout` leaves the test process running.
- **Replay outcomes.** An out-of-range occurrence returns `worker_outcome: "no-test"` and a command that
  cannot launch returns `test_outcome: "incompetent"`, both with exit 0.
- **Obsolete base tests in real PRs.** For the 36 commits since 2026-09-26 that changed both a module and
  its test file, the parent's test file was run against the commit's module: 2 had no base file, 16 no
  failures, 9 at most 5% failing, 7 (all from 68a2f8a, the uniform CLI refactor, math#171) 13-65%, 2
  (949fd22, a re-prompt change) hung past 900 s, 0 collapsed to `_FailedTest`. A synthetic rename of one
  imported name in a copy of `sq/` collapsed all 53 base tests into one `_FailedTest`.
- **Hypothesis.** 8 of 10 Python test files import hypothesis; 9 set no `deadline`. `derandomize=True`
  seeds from a digest of the test's source, so an edited `@given` body drew different examples
  (`[0, 2179, 4761, ...]` versus `[0, -18471347, ...]`). A `sitecustomize.py` that replaces
  `hypothesis.core.function_digest` with a digest of the test's `__qualname__` and loads a profile with
  `derandomize=True, database=None, deadline=None, suppress_health_check=list(HealthCheck)` drew the same
  examples for both bodies (`[0, -82, 7227, ...]`). A `sitecustomize.py` that raises only prints
  `Error in sitecustomize` and the interpreter continues.
- **Exemption churn.** 10 commits since 2026-09-26 touched an exemption file; 9 would need the operator
  under this design (one, 57271ec, only re-keyed `above` after a refactor).
- **Terminal confirmation.** Agent shells have no controlling terminal (a hook writing `/dev/tty` in
  this session failed with `No such device or address`), so a `commit-msg` hook that reads a typed
  confirmation from `/dev/tty` refuses an agent's commit.
- **Runner pool.** Sweep run 45479226540 ran 35 jobs at once.

## Design

### Rust: whole crate on any crate change

1. `mutation-pr-detect.sh` selects a crate for `rs_dirs` when a changed path is under `<crate>/src/`,
   `<crate>/tests/` or `<crate>/.cargo/`, or when `<crate>/Cargo.toml` changes outside its
   `[dependencies]`, `[dev-dependencies]` and `[build-dependencies]` tables (so Renovate version bumps
   do not select it).
2. `mutation-rs-plan` plans the selected crates with `--whole`. A fault unit is red. The 256-unit limit
   applies to the Rust matrix.
3. Each shard uses the sweep's rule through `scripts/mutation-classify.sh`: red on a missed mutant, on
   `caught + missed + timeout == 0`, on a missing `outcomes.json` or `mutants.out/exit-code`, or on a
   failed baseline; timeouts green beside a catch.
4. The amicable-rs canary is unchanged. Drift from a newer rustc or cargo-mutants surfaces on the next
   PR touching the crate (accepted by the operator).

### Python: same code, two test suites

Triggered for a dir when its `test_<module>.py`, `cosmic-ray.toml` or `mutants-equivalent.toml`
changes, in addition to the existing module-change trigger.

1. **Planning.** The planner job runs the head suite once on the unmutated head module and records its
   wall time `s`. It plans `n = min(20, max(1, ceil(K * s / 600)))` shards per dir (about 10 minutes of
   head work each), and `mutation-py`'s `timeout-minutes` rises to 60.
2. **One sandbox.** Both arms run in the existing `MUTANTS_BODY` sandbox: its file set, the
   `MUTANTS_CAP` limits and `TMPDIR` under `.mutants-tmp`. The base test file is written only there,
   as `test_<module>_base.py`, from `git show <merge-base>:<dir>/test_<module>.py`.
3. **Deterministic hypothesis.** Every run in both arms has `PYTHONPATH` holding a generated
   `sitecustomize.py` that replaces `hypothesis.core.function_digest` with a SHA-384 of the test's
   `__qualname__` and loads the profile `mutation-gate` (`derandomize=True, database=None,
   deadline=None, suppress_health_check=list(HealthCheck)`). Each shard first runs a preflight under the
   same `PYTHONPATH` that asserts the profile is loaded and the digest replaced; a failed preflight is red.
4. **Head arm.** Each shard runs the head tests on every mutant in its slice (the existing session path).
   The existing changed-line rule still applies: any survivor on a line the PR added to `<module>.py`
   is red.
5. **Judgeable base suite.** The base command is the merge base's `cosmic-ray.toml` `test-command`
   with its test module renamed to `test_<module>_base`. The shard runs it once on the unmutated head
   module through `cosmic_ray.testing.run_tests` with the toml `timeout`. The suite is unjudgeable, and
   the dir red, when that run times out, when any result is `unittest.loader._FailedTest`, when a class-
   or module-level setup errors, or when more than 5% of base tests fail or error. Otherwise each failing
   or erroring base test is excluded from replay.
6. **Replay.** For each of its own head survivors, the shard calls
   `cosmic_ray.mutating.mutate_and_test([<the session's stored MutationSpec>], <base command restricted
   to the kept tests>, <toml timeout>)`. `killed` (a timeout included) and `survived` are the only
   accepted outcomes; any other outcome or an exception is red with `replay failed: <outcome>`.
7. **Verdict.** A mutant killed by the base arm and surviving the head arm is a weakening; the summary
   prints `weakened: <count> mutants killed by base tests survive head tests`, then each mutant's
   operator, occurrence, diff and a one-mutant repro command.
8. **Missing files.** A `test_<module>.py` present at the merge base and absent at head is red with
   `test_<module>.py deleted`. A merge base with no test file skips steps 5-7 and says so.
9. **Standing canary.** `py_canary` gains a weakening case: committed fixture files
   `tests/fixtures/mutation_weakening/test_sq_base.py` and `test_sq_head.py`, where head drops one
   assertion, must report `weakened: 1` naming the expected mutant whenever a file that shapes the
   Python run changes.

### Exemptions need the operator

For every dir or crate in the PR's plan, the gate computes what the PR newly exempts:

- **Python equivalents.** The head module's job list is pruned twice, by the merge base's
  `mutants-equivalent.toml` and by the head's (with `scripts/cosmic_ray_prune.py`'s matching). Each job
  pruned only by the head file is newly exempted.
- **Python config.** Any change to `cosmic-ray.toml` is an exemption item.
- **Rust exclusions.** `cargo mutants --list --json` runs on the head crate with the head
  `.cargo/mutants.toml` and again with `--config <merge-base copy>`. Each mutant listed only under the
  base config is newly excluded. Any change to a key other than `exclude_re` is an exemption item.
- **Rust skips.** For each hunk under `<crate>/src/`, its added lines are joined with all whitespace
  removed; any occurrence of `mutants::skip` is an exemption item.

Each item is red, naming it, unless the target is cleared. A commit message line
`Mutation-Gate-Reviewed: <target>: <reason>`, where `<target>` is the dir or crate dir and `<reason>`
has at least 10 characters, clears that target's items present at that commit (the latest such commit
in the range per target wins); an item first present after it is red again. The same line clears an
unjudgeable base suite for that dir only if its `<module>.py` and `test_<module>.py` are unchanged
between that commit and head. Every red names the remedy: "operator-dictated
`Mutation-Gate-Reviewed: <target>: <reason>`, committed from a terminal".

`scripts/commit-msg` refuses a message containing `Mutation-Gate-Reviewed:` unless `yes` is typed at
`/dev/tty`; with no terminal it refuses. Agents have no terminal and cannot bypass hooks
(git-workflow-046). Honest ceiling: plumbing that runs no hooks (`git commit-tree`, a web edit) can
still write the line, so the agent instruction (N7) remains.

### Known limits

- A weakening on a mutant another head test still kills is invisible to any mutation-based gate.
- A base test that legitimately fails on the new behaviour is excluded (at most 5% of the suite), so
  pairing a behaviour change with weakening that test is not seen on unchanged lines; the changed-line
  rule still covers the changed lines.
- A uniform refactor of many test files can plan up to 20 shards per dir and run in several waves on the
  shared runner pool.

### Workflow and local repro

- `mutation-pr.yml` sets `concurrency: { group: mutation-pr-${{ github.event.pull_request.number }},
  cancel-in-progress: true }`.
- CI runs the Python steps through `make -C <dir> mutants-weakening BASE=<sha> MUTANT_SHARD=<k>/<n>`;
  the same target runs locally.
- Rust: `scripts/mutation-pr-run.sh --whole [--shard <k>/<n> --expect <count>] <crate>`.

## Requirements

- **R1.** `scripts/mutation-pr-detect.sh` prints a crate dir in `rs_dirs` when a changed path starts with `<crate>/src/`, `<crate>/tests/` or `<crate>/.cargo/`, whatever the file extension, or when `<crate>/Cargo.toml` has a changed line outside its `[dependencies]`, `[dev-dependencies]` and `[build-dependencies]` tables.
- **R2.** In `mutation-pr.yml`, `mutation-rs-plan` plans every selected crate with `scripts/mutation-rs-plan.sh --whole <crate-dir>...` and never passes `--in-diff` for a selected crate.
- **R3.** A `--whole` fault unit (`"fault": "<cause>"`) makes `mutation-pr` red and its summary names the crate and the cause.
- **R4.** A Rust PR shard is red on any missed mutant, on `caught + missed + timeout == 0`, on a missing `mutants.out/outcomes.json` or `mutants.out/exit-code`, or on a failed baseline, and green on timeouts beside at least one caught mutant, using `scripts/mutation-classify.sh`.
- **R5.** `mutation-pr-detect.sh` prints a Python dir in a new output `py_test_dirs=<sorted dirs>` when `git diff --numstat --no-renames` shows any added or deleted line in `<dir>/test_<module>.py`, `<dir>/cosmic-ray.toml` or `<dir>/mutants-equivalent.toml` (module = dir with `-` as `_`), including a file deletion.
- **R6.** The Python planner runs each `py_test_dirs` dir's head suite once on the unmutated head module, records its wall time `s` in seconds, plans `n = min(20, max(1, ceil(K * s / 600)))` whole-module shards, and `mutation-py` has `timeout-minutes: 60`.
- **R7.** Both arms of every `py_test_dirs` shard run in the `MUTANTS_BODY` sandbox under `.mutants-tmp` with `MUTANTS_CAP` and `TMPDIR`, and `test_<module>_base.py` (from `git show <merge-base>:<dir>/test_<module>.py`) is written only there.
- **R8.** Every run in both arms has `PYTHONPATH` holding a generated `sitecustomize.py` that sets `hypothesis.core.function_digest` to a SHA-384 of the test's `__qualname__` and calls `settings.register_profile("mutation-gate", derandomize=True, database=None, deadline=None, suppress_health_check=list(HealthCheck))` and `settings.load_profile("mutation-gate")`.
- **R9.** Each shard runs a preflight under that `PYTHONPATH` asserting `hypothesis.settings.default.derandomize` is true, `deadline` is `None` and `hypothesis.core.function_digest` is the replacement, and is red with `hypothesis profile not active` when it fails.
- **R10.** The base command is the merge base's `cosmic-ray.toml` `test-command` with its test module renamed to `test_<module>_base`; each shard runs it once on the unmutated head module through `cosmic_ray.testing.run_tests` with the toml `timeout`, and the dir is red with `base suite unjudgeable: <cause>` followed by the failing test ids when that run times out, when any result is `unittest.loader._FailedTest`, when a class- or module-level setup errors, or when more than 5% of base tests fail or error.
- **R11.** When R10 does not make the dir red, every base test that failed or errored on the unmutated head is excluded from replay, and the summary lists their ids under `obsolete base tests:`.
- **R12.** For each of its own head survivors, a shard calls `cosmic_ray.mutating.mutate_and_test` with that job's stored `MutationSpec`, the base command restricted to the tests not excluded by R11, and the toml `timeout`; the outcomes `killed` and `survived` are accepted, and any other outcome or an exception makes the dir red with `replay failed: <outcome>`.
- **R13.** A dir in `py_test_dirs` is red when any mutant is killed in the replay and survived in the head arm, and its summary reads `weakened: <count> mutants killed by base tests survive head tests`, then each mutant's operator, occurrence, diff and a line `repro: make -C <dir> mutants-weakening BASE=<sha> JOB=<job id>`.
- **R14.** A dir in `py_test_dirs` keeps the existing rule that any head survivor on a line the PR added to `<module>.py` is red.
- **R15.** A dir whose `test_<module>.py` exists at the merge base and not at head is red with `test_<module>.py deleted`; one whose merge base has no `test_<module>.py` skips R10-R13 and prints `no base test file: weakening check skipped`.
- **R16.** `py_canary` runs the weakening path on committed fixtures `tests/fixtures/mutation_weakening/test_sq_base.py` and `test_sq_head.py` (head drops one assertion) and is red unless it reports `weakened: 1` naming the expected mutant.
- **R17.** For each dir in the Python plan, each job of the head module that `scripts/cosmic_ray_prune.py`'s matching prunes under the head `mutants-equivalent.toml` but not under the merge base's is an exemption item, and any change to `<dir>/cosmic-ray.toml` is an exemption item.
- **R18.** For each crate in the Rust plan, each mutant listed by `cargo mutants --list --json` on the head source with `--config <merge-base .cargo/mutants.toml>` but not with the head config is an exemption item, any change to a `.cargo/mutants.toml` key other than `exclude_re` is an exemption item, and each hunk under `<crate>/src/` whose added lines, joined with all whitespace removed, contain `mutants::skip` is an exemption item.
- **R19.** Each exemption item makes `mutation-pr` red, naming it and the remedy `operator-dictated Mutation-Gate-Reviewed: <target>: <reason>, committed from a terminal`, unless the latest commit in the range with a line `Mutation-Gate-Reviewed: <target>: <reason>` for its dir or crate (reason at least 10 characters) already contains the item.
- **R20.** That trailer also clears an R10 red for its dir when `<dir>/<module>.py` and `<dir>/test_<module>.py` are unchanged between the trailer commit and head, and the summary then says `cleared by Mutation-Gate-Reviewed`.
- **R21.** `scripts/commit-msg` refuses a commit message containing `Mutation-Gate-Reviewed:` unless the line `yes` is read from `/dev/tty`, and refuses it when `/dev/tty` cannot be opened.
- **R22.** `mutation-pr.yml` sets `concurrency: { group: mutation-pr-${{ github.event.pull_request.number }}, cancel-in-progress: true }`.
- **R23.** CI runs the Python steps by calling `make -C <dir> mutants-weakening BASE=<sha> MUTANT_SHARD=<k>/<n>`, a target every Python `Makefile` gains from `scripts/crate_templates/python/Makefile`, which also accepts `JOB=<job id>` to replay one mutant and writes nothing in the tracked tree.
- **R24.** `scripts/mutation-pr-run.sh --whole [--shard <k>/<n> --expect <count>] <crate-dir>` runs one crate's whole mutant set locally and exits non-zero on the R4 red conditions.
- **R25.** `tests/scripts/mutation_pr_detect.bats` covers R1 (a `tests/` fixture, a non-`.rs` `src/` file, a `.cargo/mutants.toml` change and a `Cargo.toml` `[[test]]` change each select the crate; a `[dependencies]` version change alone does not) and R5 (an added-only, a deleted-only and a file-deletion change to `test_<module>.py`, and a change to `cosmic-ray.toml` or `mutants-equivalent.toml`, each put the dir in `py_test_dirs`; a change to `<module>.py` alone does not).
- **R26.** A test on a copy of `sq/` requires: head dropping one assertion that kills a known mutant reports that mutant under `weakened: 1`; head only adding a test reports `weakened: 0`; a cosmetic edit to every `@given` test body reports `weakened: 0`; one base test failing on the unmutated head is listed under `obsolete base tests:` and not counted; an import-breaking rename is red with `base suite unjudgeable`; a base test sleeping past the timeout is red with `base suite unjudgeable` and leaves no process running; an untested line added to `sq.py` together with a test-file change is red under R14; a replay forced to `no-test` is red with `replay failed`; a failing `sitecustomize` is red with `hypothesis profile not active`; and after every case the tracked `sq/` files are byte-identical to before.
- **R27.** Tests cover R17-R20: a new equivalents entry, a `variant` change and a duplicated entry are red; a re-keyed entry that prunes the same job is green only with the trailer; an `exclude_re` change that only shifts line numbers is green; a new or retargeted pattern is red; an `additional_cargo_test_args` change is red; `#[mutants::skip]`, `#[mutants :: skip]` and a line-split `#[mutants::` / `skip]` are each red; each red turns green with a valid trailer for its target, stays red with a trailer for another target or a 9-character reason, and an item added after the trailer commit is red; and tests for R21 show the hook refusing without a terminal.
- **R28.** Root `CLAUDE.md` (Mutation testing sections) and an ADR describe the whole-crate PR rule, the Python weakening check, the exemption rule, the trailer and its terminal hook, with repro commands; `docs/superpowers/README.md` removes the Backlog row "PR mutation gates miss test-only weakening (Rust and Python)"; root `CLAUDE.md` stays at or under 30,000 bytes.

- **V1.** Positive control before the PR is marked ready: a throwaway draft PR that deletes one assertion from a crate's `#[cfg(test)]` module, leaving a mutant uncaught, shows `mutation-pr` red naming that mutant; closed and its branch deleted.
- **V2.** Positive control: a throwaway draft PR that weakens one assertion in `sq/test_sq.py` shows `mutation-pr` red with `weakened: 1` naming the mutant; closed and deleted afterwards.
- **V3.** Negative control: a throwaway draft PR that only adds a test to `sq/test_sq.py` shows `mutation-pr` green.
- **V4.** Positive control: a throwaway draft PR that adds one `[[equivalent]]` entry to `sq/mutants-equivalent.toml` shows `mutation-pr` red naming it; closed and deleted afterwards.
- **V5.** Timing: throwaway draft PRs that add one test to `descartes/test_descartes.py` and to `pi/test_pi.py` record every shard's wall time and the number of concurrent jobs; a shard past about 30 minutes lowers the 600-second target before merge.
- **V6.** Record the wall time of the PR's own `mutation-pr` run and of V1-V5; a zeta-rs whole-crate run is measured or projected from shard times, and any Rust shard past about 50 minutes lowers B per ADR-0046.
- **V7.** The operator commits one `Mutation-Gate-Reviewed:` trailer from a terminal (answering `yes`) on a throwaway branch, and an agent's attempt to commit the same message is refused by the hook.

- **N1.** The monthly `mutation-testing.yml` and `mutation-testing-python.yml` sweeps do not change.
- **N2.** No committed survivor, missed or baseline list is added for any crate or Python dir; the only committed fixtures are the R16 canary files.
- **N3.** The local pre-push hook runs no mutants.
- **N4.** The required check stays `mutation-pr`; no new required check is added to branch protection.
- **N5.** Nothing in the gate or the local target writes to a tracked file in the working tree; the base test file and every mutation exist only in the sandbox.
- **N6.** The Python changed-line gate's behaviour for dirs not in `py_test_dirs` does not change.
- **N7.** No agent, script or workflow writes a `Mutation-Gate-Reviewed:` trailer; only the operator does, from a terminal.

## Multi-Lens Review

Reviewed at commit: `b79a1c9` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: Worth building; premise verified (`mutation-pr-detect.sh:66` selects a crate only on `<crate>/src/*.rs`, lines 15-18 a Python dir only on added `<module>.py` lines; 13 crates have `tests/`). Of 41 recent Python dir-changes touching `test_<m>.py`, 36 also changed `<m>.py`, so the any-test-change trigger (R5) is right. The Rust half is the simplest correct design (sweep at 0 missed, run 45479226540 green). Load-bearing flaw: the exemption files are an allow-path looser than the gate. A PR can weaken a test and add a `mutants-equivalent.toml` entry (Python, pruned before the session, so never replayed) or a `.cargo/mutants.toml` `exclude_re` (Rust) for the exposed mutant, and go green; auto-merge lands it unreviewed. Secondary: R12 has no mechanism on the base side (`cosmic-ray mutate-and-test` 8.7.0 passes `timeout=None`); the R7 obsolete list is printed only in a green run's summary, which nobody reads, and is where an evasion hides; R15 should be the code path CI calls, not a second implementation.
Assumption: Few base test methods fail on the unmutated head in PRs that change both `<m>.py` and `test_<m>.py`; if many do, R7 excludes them and the check goes quiet on the PRs it mainly exists for. Settle by running each such commit's parent test file against its module for the 36 commits since 2026-09-26.
Disposition: Addressed (operator, 2026-11-26: exemptions "Red unless operator trailer"; revisions "Yes, address all": fail closed on a collapsed or mostly obsolete base suite, replay in a throwaway copy with a per-mutant timeout, per-shard replay with more shards, derandomized hypothesis, corrected mutant counts plus a pi timing V, CI calls the make target, MUTANT_SHARD, one-mutant repro line, cancel-in-progress, inherent limit stated).

### Ergonomics

Finding: Premise verified (same lines). The Facts' "pi and e hold 613 mutants each" is the diff-pruned count from slice 8; whole modules are 1,828 (pi, `cosmic-ray init` on HEAD) and about 1,621 (e), and issue #184 shows 712 and 736 survivors. With R6's cap of 10 shards, a pi/e shard holds about 183 mutants (15-20 min on CI, run 42157892557) plus about 70 survivors to replay (about 7 min), so a shard lands at 26-28 min against `mutation-py`'s `timeout-minutes: 30`; a serial aggregate replay is about 70 min. Over the last 100 merged PRs the Python test trigger fires on 18 (16 also change the module), so it fires on every TDD Python PR, pi and e most; the Rust trigger fires on the same 17 PRs as today, with a one-line zeta edit going from about 1 to about 37 min. 8 of 10 Python test files import hypothesis with no derandomization, so base and head can disagree by chance and give a false `weakened` red. Smaller: no `concurrency: cancel-in-progress` on `mutation-pr.yml`; R15 takes no `MUTANT_SHARD`; R9 should print the one-mutant repro command. Renovate and docs-only PRs trigger neither path.
Assumption: A whole-module Python head shard plus its survivor replay fits `mutation-py`'s 30-minute timeout for pi and e (estimated 26-28 min per shard); settle by timing one pi shard plus `python3 -m unittest test_pi` locally, or a V5 draft PR adding one test to `pi/test_pi.py`.
Disposition: Addressed (operator, 2026-11-26: exemptions "Red unless operator trailer"; revisions "Yes, address all": fail closed on a collapsed or mostly obsolete base suite, replay in a throwaway copy with a per-mutant timeout, per-shard replay with more shards, derandomized hypothesis, corrected mutant counts plus a pi timing V, CI calls the make target, MUTANT_SHARD, one-mutant repro line, cancel-in-progress, inherent limit stated).

### Risk

Finding: Premise verified; the head run is not contaminated by the base file (`test-command` names the module). A: the replay is not small: head survivors include the backlog (e 396 at 5.6 s, pi 368 at 4.7 s in slice 8), so a serial unsharded replay is about 37 and 29 min and a PR touching `test_e.py` goes red on the job timeout, not a verdict; replay each cell's own survivors in that cell. B: base-side timeout cannot occur (`cli.py:309-311` passes `None`), so a loop mutant hangs the job until the 30-minute kill, red without a named mutant. C: when the head renames a symbol the base test file imports, the base file fails to import and unittest reports one `_FailedTest`; R7 then excludes the whole suite and R8 is undefined: discovery fallback or "no tests" exit 5 gives a false red, special-casing empty gives an exploitable false green. D: Rust risk acceptable (sweep green, zeta about 37 min against a 60-minute cap, public repo). Not over-engineered.
Assumption: The serial base replay of head survivors fits in the 30-minute job; above about 300 survivors in e it must be sharded per cell. Settle by counting SURVIVED jobs in a fresh whole-module `make -C e mutants` on master.
Disposition: Addressed (operator, 2026-11-26: exemptions "Red unless operator trailer"; revisions "Yes, address all": fail closed on a collapsed or mostly obsolete base suite, replay in a throwaway copy with a per-mutant timeout, per-shard replay with more shards, derandomized hypothesis, corrected mutant counts plus a pi timing V, CI calls the make target, MUTANT_SHARD, one-mutant repro line, cancel-in-progress, inherent limit stated).

### Adversarial Spec Review (comparison/judge designs only)

Trigger applies (base-vs-head judge). Premise verified; sweep green. Load-bearing flaw: R7's exclusion has no bound and can switch the check off: renaming one imported name in `sq.py` made the base copy collapse to one id, `unittest.loader._FailedTest.test_sq_base` (all 53 tests), which R7 excludes, so R8 replays an empty suite and R9 reports `weakened: 0`; a failing `setUpModule`/`setUpClass` collapses the same way. "Rename one function, then weaken the tests" passes; fail closed instead. Mechanism flaw: wrapping `mutate-and-test` in `timeout` leaves the module mutated (probe: rc=124, `sq.py` left as `limit = 11**max_digits`), so later replays stack mutations and shift occurrence indices, and the local target would mutate the developer's tracked module (N5); replay in a throwaway copy with an explicit per-mutant timeout equal to `cosmic-ray.toml`'s 60.0. Bias: hypothesis is random on both sides with different databases and directories, so a mutant only random inputs kill can survive head and die under base by luck (false red). Missed recall: exemption edits (equivalents entry, `exclude_re`, an added `#[mutants::skip]`, and `mutants.toml` is not an R1 trigger path); inherent limit: a weakening on a mutant another head test still kills is invisible to any mutation judge, which the spec should state. Rust half: absolute 0-missed rule favours neither suite; recall equals the sweep's minus the exemption holes.
Assumption: Base tests failing on the unmutated head are rare and confined to single methods in real PRs; a rename or removed import takes out the whole suite. Settle by running each recent both-files PR's merge-base test file against its head module and counting failures and `_FailedTest` results.
Disposition: Addressed (operator, 2026-11-26: exemptions "Red unless operator trailer"; revisions "Yes, address all": fail closed on a collapsed or mostly obsolete base suite, replay in a throwaway copy with a per-mutant timeout, per-shard replay with more shards, derandomized hypothesis, corrected mutant counts plus a pi timing V, CI calls the make target, MUTANT_SHARD, one-mutant repro line, cancel-in-progress, inherent limit stated).

### Round 2 (all four reviews, reviewed at `ad23640`, the round-1 revision)

#### Goal-Fit

Finding: Rust and exemption halves worth building as designed. Load-bearing flaw: hypothesis `derandomize` seeds from `function_digest(test)`, a hash of the test's source (hypothesis 6.168.5 `core.py:719-720`, `reflection.py:56-80`), so any edit to a `@given` test body gives base and head different examples, and a mutant killed only by some base examples reads as `weakened` with no clearance path; those edited tests are exactly what TDD PRs touch. No case pins R14 on the new whole-module path (16 of 18 triggering PRs also change the module). One trailer anywhere in the range clears every later exemption. Printing `obsolete base tests:` on a green, auto-merged run is decoration. Simpler path for the operator to weigh: a static rule (red on a deleted or changed assertion line or an added skip, unless trailer); 5 of the last 100 PRs deleted an assertion line; it misses weakening through inputs, helpers or strategies; the spec cites no weakening incident in this repo.
Assumption: Few mutants in the `@given` modules are killed only by generated examples; settle with a cosmetic body edit to each `@given` test in a copy of `sq/` and the R11 replay.
Disposition: Addressed (operator, 2026-11-26: "Round 3 on full design"): name-keyed hypothesis seeding, R14 case, trailer scoped per target and per commit.

#### Ergonomics

Finding: The Python cost is on the wrong dir and miscomputed: `cosmic-ray init` on master gives descartes 3663, triangle 3113, pi 1828, e 1621, perfect-numbers 679, factorial 500, collatz 420, amicable 252, fib 232, sq 164 mutants; under `ceil(K/60)` descartes is 62 shards (plus 12 whole-crate descartes-rs) and a uniform test refactor 213 Python units, about 6 waves on a pool of about 40 runners shared with 8 other repos; the count rule ignores suite time (triangle 0.8 s per run). Since 2026-09-26, 9 of 10 exemption-file commits would need the trailer (one, 57271ec, only re-keyed `above`), plus 2 unjudgeable-suite commits: about 1 PR in 9, each forcing a full re-run. One trailer clears everything after it. R9's red does not list the failing test ids, and reds do not name the remedy. Draft-held-green and auto-merge add no friction.
Assumption: Replay share of a descartes or triangle shard stays small; settle by counting SURVIVED in one local descartes shard or running V5 on descartes.
Disposition: Addressed (operator, 2026-11-26: "Round 3 on full design"): time-based shard sizing with a per-dir cap, V5 on descartes, ids and remedy in every red, trailer scoped to the commit.

#### Risk

Finding: Rust proportionate. Python: F1 false red from source-keyed seeds and hypothesis's 200 ms `deadline` (9 of 10 test files set none); F2 the trailer disables the whole check for a dir, any commit in range clears every dir, and git identity and `gh` token are the operator's, so nothing distinguishes operator from agent; a `commit-msg` hook requiring `/dev/tty` confirmation is tighter; F3 a failing `sitecustomize` prints an error and continues (probe rc=0), silently re-randomizing; F4 300 s judgeability limit versus 60 s replay limit makes a 61-300 s suite turn every survivor into `weakened`; F5 the per-shard estimate was off by 2x; F6 a descartes test edit queues 62 shards and a uniform refactor about 250 against a 20-job account limit; F7 `:N:N:` retargets within a function. Uncovered channels: a crate's `Cargo.toml` (`autotests`, `[[test]]`) and a Python `cosmic-ray.toml` `test-command`. Matrix: all Python dirs total 213 units under `ceil(K/60)`, plus 37 Rust is 250.
Assumption: Base and head draw the same hypothesis examples for tests the PR did not weaken; refuted for edited `@given` tests by the seeding mechanism.
Disposition: Addressed (operator, 2026-11-26: "Round 3 on full design"): name-keyed seed plus `deadline=None`, tty-confirmed trailer, preflight, one 60 s limit, time-based sizing, `Cargo.toml` and `cosmic-ray.toml` covered, listing-based exclusion check.

#### Adversarial Spec Review

Finding: F1 an outer `timeout` around `mutate-and-test` kills cosmic-ray but leaves the test process alive (`start_new_session=True`; probe showed `python3 slow.py` running after rc=124), and base and head time different things. F2 replay outcomes `no-test` (out-of-range occurrence) and `incompetent` (command cannot launch) both rc=0 and count as neither killed nor survived, so a broken replay reports `weakened: 0` forever; no standing canary covers the weakening path. F3 the arms run in different sandboxes (head: 4-file copy with caps, `TMPDIR` and `../scripts`; base: "the dir", which includes `<crate>-rs/target`). F4 the base command is unspecified, and `cosmic-ray.toml`'s `test-command` is an unguarded weakening channel. F5 `#[mutants :: skip]` and a line-split `#[mutants::` / `skip]` both suppress mutants under cargo-mutants 27.1.0 while `grep -c 'mutants::skip'` returns 0. F6 `:N:N:` set comparison admits an added duplicate pattern and retargeting of function-less patterns (pi `^src/main\.rs:105:34: replace \* with \+$`). F7 the R15 tuple omits `variant` and `row`, which `cosmic_ray_prune.py` uses as selectors. F8 one trailer clears every item in the range, including later agent commits. F9 the 20% cap admits the dominant real weakening (a test failing on new behaviour, then weakened); the author's data supports 5%. F10 hypothesis `deadline` and health checks, and a silently failing `sitecustomize`. F11 a crate `Cargo.toml` edit dropping test targets is not a trigger.
Assumption: The head session's (operator, occurrence) replays the same mutant under `mutate-and-test`; verified only for one job. Settle by replaying every job of a full session and comparing diffs.
Disposition: Addressed (operator, 2026-11-26: "Round 3 on full design"): replay through `cosmic_ray.mutating.mutate_and_test` with the session's stored specs and the toml timeout (same group-kill semantics as the head arm; 164 of 164 sq jobs replayed to identical diffs), any other outcome red, a standing weakening canary, one sandbox for both arms, base command from the merge base's toml, `cosmic-ray.toml` changes are exemption-class, whitespace-insensitive skip scan, listing-based exclusion and prune-based equivalents comparison, 5% cap, `Cargo.toml` trigger.
