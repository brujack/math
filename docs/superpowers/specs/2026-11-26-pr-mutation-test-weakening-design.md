# PR mutation gates see test weakening

- **Date:** 2026-11-26 (revised after Multi-Lens Review rounds 1-3)
- **Backlog row closed:** "PR mutation gates miss test-only weakening (Rust and Python)" (P2)
- **Related:** ADR-0042 (Rust sweep holds zero missed), ADR-0044 (per-PR Python gate), ADR-0046
  (shard the Rust runs), `specs/2026-11-05-worldclass-slice5-rust-pr-mutation-ratchet-design.md`,
  `specs/2026-11-07-worldclass-slice8-python-pr-mutation-gate-design.md` ("Known gap, not closed here")

## Summary

Both per-PR mutation gates judge only mutants on lines a PR changes. A PR that deletes or weakens
tests changes no production line, so it is never judged, and a PR can exempt the mutant it exposes
or change the gate itself. This spec closes those holes:

- **Rust:** any change to a crate's `src/`, `tests/`, `.cargo/` or the test-shaping parts of its
  `Cargo.toml` runs every mutant in that crate, held to the sweep's rule (0 missed, timeouts green).
- **Python:** a change to `test_<module>.py`, `cosmic-ray.toml` or `mutants-equivalent.toml` mutates
  the whole head module and runs the head tests on every mutant; each shard then replays its own head
  survivors under the base tests. Base tests that fail on the new code are not dropped: each is judged
  by whether its recorded failure signature changes under the mutant. A mutant the base tests kill and
  the head tests do not is a weakening. A base suite that cannot be judged is red.
- **Exemptions and the gate itself:** what a PR newly exempts is computed from ground truth with
  content-keyed mutant identity, and a change to any gate-shaping file is itself an item. Every item is
  red unless the operator clears its target with a trailer on a commit signed by a touch-required FIDO
  key, verified in CI.

## Why

Measured 2026-11-26 on master `0bc607f`:

- `scripts/mutation-pr-detect.sh` puts a Python dir in `py_src_dirs` only when `git diff --numstat`
  shows added lines in `<dir>/<module>.py` (lines 15-18, 37). A PR touching only `test_<module>.py`
  runs no Python mutant.
- A Rust crate is selected only when a changed path matches `<crate>/src/**/*.rs` (line 66), and its
  mutants are filtered by `--in-diff`. A hunk inside a `#[test]` yields `INFO No mutants to filter`,
  exit 0 (slice 5 spec, 2026-11-05). A change under `<crate>/tests/` (13 crates have one) or to
  `Cargo.toml` (`autotests`, `[[test]]`) selects no crate.
- The 90% coverage floors catch a large test deletion but not a weakened assertion.
- The Rust monthly sweep holds 0 missed (ADR-0042; run 45479226540 green), so a Rust weakening is
  reported within a month, after merge. The Python sweep carries about 1,250 open survivors (issue #184;
  latest per-dir figures pi 368, e 396), so a new Python survivor is never reported at all.
- The exemption and gate channels are looser than the gate: `mutants-equivalent.toml` entries are pruned
  before the session runs, `cosmic-ray.toml`'s `test-command` chooses which tests run, Rust
  `.cargo/mutants.toml` holds `exclude_re` and zeta's `additional_cargo_test_args`, `#[mutants::skip]`
  and macro-wrapped code remove mutants, and the gate's own scripts, templates and crate `Makefile`
  arguments run from the PR head.

Agents write most of the tests here, weakening a test to make a gate pass is on the executor FORBIDDEN
list, and auto-merge lands a green PR without review. No weakening incident in this repo has been
measured; the operator chose this semantic design over a static assertion-line rule and asked for a
fourth review round (2026-11-26).

## Facts this design rests on (measured 2026-11-26)

- **Rust whole-crate cost.** Sweep run 45479226540 (all 13 crates, 2,221 mutants, 37 shards at B = 75)
  took 9 minutes of wall time; longest shard 7.4 min. zeta-rs: 748 mutants, 10 shards of about 37 min
  against `mutation-rs`'s `timeout-minutes: 60`. The Rust trigger fires on the same 17 of the last 100
  PRs as today's.
- **Planner.** `scripts/mutation-rs-plan.sh --whole <crate-dir>...` plans every mutant and emits a fault
  unit instead of failing.
- **cargo-mutants listing.** `cargo mutants --list --json` gives, per mutant, `file`,
  `function.function_name`, `genre`, `replacement`, `name` (`<file>:<line>:<col>: <description>`) and a
  `span`; `--config <FILE>` and `--no-config` choose the configuration. So a mutant can be identified by
  content (file, function, genre, description, the source text under its span, and its ordinal among
  equal keys) rather than by line number. Patterns in every `exclude_re` embed `:<line>:<col>:`; 3 of
  the 8 recent commits to a `mutants.toml` only shifted those numbers.
- **Skip evasions.** Under cargo-mutants 27.1.0, `#[mutants::skip]`, `#[mutants :: skip]`, a line-split
  `#[mutants::` / `skip]`, `#[mutants:: /* c */ skip]`, and wrapping a function in a no-op
  `macro_rules!` invocation each removed that function's mutants from `--list`.
- **Python whole-module size** (`cosmic-ray init`): descartes 3663, triangle 3113, pi 1828, e 1621,
  perfect-numbers 679, factorial 500, collatz 420, amicable 252, fib 232, sq 164. Local suite times:
  descartes 7.0 s, e 5.5 s, pi 4.5 s, sq 1.0 s, triangle 0.8 s, amicable 0.6 s, collatz 0.5 s, fib
  0.5 s, factorial 0.4 s, perfect-numbers 0.4 s.
- **Timeouts dominate small suites.** Sweep run 41279088956 (10 cells per dir): collatz 82.2 min summed
  with 62 timed-out mutants, perfect-numbers 36.1 min (24), factorial 30.3 min (18), sq 28.0 min (19);
  the slowest collatz cell took 759 s.
- **Replay identity and timeout.** `cosmic_ray.mutating.mutate_and_test(mutations, test_command,
  timeout)` applies stored `MutationSpec`s and runs `cosmic_ray.testing.run_tests`, which starts the
  tests in a new session and kills the whole process group on timeout, returning `KILLED`. Replaying all
  164 of sq's session jobs with their stored specs gave diffs identical to the session's (164 of 164).
  Out-of-range occurrences return `no-test`; an unlaunchable command returns `incompetent`, both exit 0.
- **Obsolete base tests in real PRs.** Of 36 commits since 2026-09-26 that changed both a module and its
  test file: 2 had no base file, 16 no failing base test, 9 at most 5%, 7 (68a2f8a, math#171) 13-65%, 2
  (949fd22) hung past 900 s, 0 collapsed to `_FailedTest`. A synthetic rename of one imported name in a
  copy of `sq/` collapsed all 53 base tests into one `_FailedTest`.
- **Hypothesis.** 8 of 10 Python test files import hypothesis; 9 set no `deadline`. `derandomize=True`
  seeds from a digest of the test's source, so an edited `@given` body drew different examples. A
  `sitecustomize.py` that replaces `hypothesis.core.function_digest` (called at `core.py:720` in 6.168.5)
  with a digest of the test's `__qualname__`, and loads a profile with `derandomize=True, database=None,
  deadline=None, suppress_health_check=list(HealthCheck)`, drew identical examples for two bodies. A
  failing `sitecustomize.py` prints `Error in sitecustomize` and the interpreter continues.
- **Terminal confirmation is not a boundary.** From an agent shell, `printf 'yes\n' | script -qec
  "git commit -F msg" /dev/null` satisfied a `/dev/tty` prompt (rc=0); `git cherry-pick` runs no
  commit-msg hook.
- **Hardware signing.** `ssh-keygen -Y verify` (used by `git verify-commit` with `gpg.format=ssh`)
  rejects an `sk-` key signature without user presence unless the allowed-signers entry says
  `no-touch-required`. git 2.53.0 here. The repo squash-merges with `COMMIT_MESSAGES`, so trailer lines
  survive into master's history even though signatures do not.
- **Exemption churn.** 13 of 107 PRs since 2026-09-26 touched an exemption file; one `cosmic-ray.toml`
  template edit touches 10 dirs.

## Design

### Rust: whole crate on any crate change

1. `mutation-pr-detect.sh` selects a crate for `rs_dirs` when a changed path is under `<crate>/src/`,
   `<crate>/tests/` or `<crate>/.cargo/`, or when `<crate>/Cargo.toml` changes outside its
   `[dependencies]`, `[dev-dependencies]` and `[build-dependencies]` tables.
2. `mutation-rs-plan` plans the selected crates with `--whole`. A fault unit is red. The 256-unit limit
   applies to the Rust matrix.
3. Each shard uses the sweep's rule through `scripts/mutation-classify.sh`: red on a missed mutant, on
   `caught + missed + timeout == 0`, on a missing `outcomes.json` or `mutants.out/exit-code`, or on a
   failed baseline; timeouts green beside a catch.
4. The amicable-rs canary is unchanged. Toolchain drift surfaces on the next PR touching the crate.

### Python: same code, two test suites

Triggered for a dir when its `test_<module>.py`, `cosmic-ray.toml` or `mutants-equivalent.toml`
changes, in addition to the existing module-change trigger.

1. **Planning.** The planner times the head suite once on the unmutated head module (`s` seconds) and
   plans `n = min(40, max(10, ceil(K * s / 600)))` shards for each dir; the floor of 10 matches the
   sweep, whose slowest collatz cell took 759 s. `mutation-py` has `timeout-minutes: 60`.
2. **Sandbox and order.** Both arms run in the `MUTANTS_BODY` sandbox (its file set, `MUTANTS_CAP` and
   `TMPDIR` under `.mutants-tmp`). The head session runs first. Only after it finishes is the base test
   file written, as `<sandbox>/.base/test_<module>_base.py` from the merge base, and `.base` is on the
   base arm's `PYTHONPATH` only. Both the head and the base `test-command` must name exactly one test
   module (`python3 -m unittest test_<module>`); otherwise the dir is unjudgeable.
3. **Deterministic hypothesis.** Every run in both arms has `PYTHONPATH` holding a generated
   `sitecustomize.py` that replaces `hypothesis.core.function_digest` with a SHA-384 of the test's
   `__qualname__` and loads the profile `mutation-gate` (`derandomize=True, database=None,
   deadline=None, suppress_health_check=list(HealthCheck)`). A behavioural preflight, under the same
   `PYTHONPATH`, defines two `@given` functions with the same `__qualname__` and different bodies and
   requires them to draw the same first 10 examples; it fails red with the installed hypothesis version.
4. **Head arm.** Each shard runs the head tests on every mutant in its slice (the existing session path).
   Any survivor on a line the PR added to `<module>.py` is red, as today.
5. **Base runner and signatures.** The base command runs `scripts/mutation_base_runner.py`, which runs
   the base test module under unittest and compares each test with a signature file. Before replay, the
   shard runs the base runner twice on the unmutated head module, recording each test's signature:
   `pass`, or (`fail` or `error`, exception type, the line of the innermost frame in the base test file,
   the exception message). The base suite is unjudgeable, and the dir red with the failing ids, when
   either run times out, any result is `unittest.loader._FailedTest`, a class- or module-level setup
   errors, or the two runs' signatures differ.
6. **Replay.** For each of its own head survivors, the shard calls
   `cosmic_ray.mutating.mutate_and_test([<the session's stored MutationSpec>], <base runner command>,
   <toml timeout>)`. The runner exits non-zero, so the mutant counts as killed by the base suite, when
   any recorded `pass` fails or errors, or any recorded failure's signature differs. `killed` and
   `survived` are the only accepted outcomes; any other outcome or an exception is red with
   `replay failed: <outcome>` and the job id.
7. **Near-timeout check.** When the base kill was a timeout, the shard re-runs that mutant under both the
   head tests and the base runner with twice the toml timeout, and counts a weakening only if the base
   runner kills it and the head tests do not.
8. **Verdict.** A mutant killed by the base arm and surviving the head arm is a weakening; the summary
   prints `weakened: <count> mutants killed by base tests survive head tests`, then each mutant's job id,
   operator, occurrence, diff and `repro: make -C <dir> mutants-weakening BASE=<sha> JOB=<job id>`.
9. **Missing files.** A `test_<module>.py` present at the merge base and absent at head is red with
   `test_<module>.py deleted`. A merge base with no test file skips steps 5-8 and says so.
10. **Standing canary.** `py_canary` runs the weakening path on committed fixtures
    `tests/fixtures/mutation_weakening/test_sq_base.py` and `test_sq_head.py`, where head drops one
    assertion, and requires `weakened: 1` naming the expected mutant.

### Items the operator must clear

The planners compute every item before any shard runs, so an item red arrives within minutes. Each item
has a content key that survives line shifts.

- **Python equivalents.** The head module's job list is pruned twice with the merge base's copy of
  `scripts/cosmic_ray_prune.py`: by the merge base's `mutants-equivalent.toml` and by the head's. Each job
  pruned only by the head file is an item, keyed by (operator, function, mutated line text, line above,
  ordinal among equal keys).
- **Python config.** Each changed key of `<dir>/cosmic-ray.toml` is an item, keyed by (dir, key).
- **Rust exclusions.** For base source with the base config and head source with the head config, the
  excluded set is the `--no-config` listing minus the configured listing. Each mutant is keyed by (file,
  function, genre, description without `<line>:<col>:`, source text under its span, ordinal). Each head
  excluded key absent from the base excluded keys is an item. Each changed key of `.cargo/mutants.toml`
  other than `exclude_re` is an item.
- **Rust disappearance.** Each (file, function) that has mutants in the base `--no-config` listing, none
  in the head `--no-config` listing, and whose `fn <name>` still appears in the head file is an item. In
  each hunk under `<crate>/src/`, the added lines with comments and whitespace removed are searched for
  `mutants::skip`; each hit is an item.
- **Gate-shaping files.** Each changed file among `.github/workflows/mutation-pr.yml`, the scripts it
  runs (`scripts/mutation-*.sh`, `scripts/mutation_*.py`, `scripts/cosmic_ray_*.py`), the crate and
  Python `Makefile` templates under `scripts/crate_templates/`, every rendered crate or Python `Makefile`,
  and the canary fixtures is an item with target `gate`.

An item is cleared only by a commit in the PR range that carries the line
`Mutation-Gate-Reviewed: <target>: <reason>` (target a dir, a crate dir or `gate`; reason at least 10
characters) and whose signature `git verify-commit` accepts with `gpg.format=ssh` and
`gpg.ssh.allowedSignersFile` set to the merge base's copy of `.github/mutation-gate-allowed-signers`,
which lists only `sk-ssh-ed25519` keys without `no-touch-required`. Per target, the latest such commit
clears every item whose content key is present at that commit; an item first present after it is red
again. The same commit clears, for its dir, an unjudgeable base suite and a `weakened` red when
`<module>.py` and `test_<module>.py` are unchanged between it and head. A trailer on an unsigned or
unaccepted commit is ignored with `trailer ignored: <commit>: <reason>`. Every item red names the item,
its target and the remedy: "a `Mutation-Gate-Reviewed: <target>: <reason>` commit signed with the
operator's FIDO key".

### Known limits

- A weakening on a mutant another head test still kills is invisible to any mutation-based gate.
- New code written inside a macro invocation is never mutated by cargo-mutants (pre-existing).
- A failing base test whose failure message does not change under a mutant gives no kill for that
  mutant; the signature compares type, line and message only.
- A uniform refactor of many test files plans up to 40 shards per dir and runs in several waves on the
  shared runner pool.
- The signing key's custody is the trust root; a key left unlocked without a touch policy would defeat
  it, which the allowed-signers rule forbids.

### Workflow and local repro

- `mutation-pr.yml` sets `concurrency: { group: mutation-pr-${{ github.event.pull_request.number }},
  cancel-in-progress: true }`.
- CI runs the Python steps through `make -C <dir> mutants-weakening BASE=<sha> MUTANT_SHARD=<k>/<n>`
  (also `JOB=<job id>` for one mutant); the same target runs locally.
- Rust: `scripts/mutation-pr-run.sh --whole [--shard <k>/<n> --expect <count>] <crate>`.
- Items: `scripts/mutation-gate-items.sh <base-sha>` prints every item and its clearance state locally.

## Requirements

- **R1.** `scripts/mutation-pr-detect.sh` prints a crate dir in `rs_dirs` when a changed path starts with `<crate>/src/`, `<crate>/tests/` or `<crate>/.cargo/`, whatever the file extension, or when `<crate>/Cargo.toml` has a changed line outside its `[dependencies]`, `[dev-dependencies]` and `[build-dependencies]` tables.
- **R2.** In `mutation-pr.yml`, `mutation-rs-plan` plans every selected crate with `scripts/mutation-rs-plan.sh --whole <crate-dir>...` and never passes `--in-diff` for a selected crate.
- **R3.** A `--whole` fault unit (`"fault": "<cause>"`) makes `mutation-pr` red and its summary names the crate and the cause.
- **R4.** A Rust PR shard is red on any missed mutant, on `caught + missed + timeout == 0`, on a missing `mutants.out/outcomes.json` or `mutants.out/exit-code`, or on a failed baseline, and green on timeouts beside at least one caught mutant, using `scripts/mutation-classify.sh`.
- **R5.** `mutation-pr-detect.sh` prints a Python dir in a new output `py_test_dirs=<sorted dirs>` when `git diff --numstat --no-renames` shows any added or deleted line in `<dir>/test_<module>.py`, `<dir>/cosmic-ray.toml` or `<dir>/mutants-equivalent.toml` (module = dir with `-` as `_`), including a file deletion.
- **R6.** The Python planner times each `py_test_dirs` dir's head suite once on the unmutated head module (`s` seconds), plans `n = min(40, max(10, ceil(K * s / 600)))` whole-module shards, and `mutation-py` has `timeout-minutes: 60`.
- **R7.** Both arms of every `py_test_dirs` shard run in the `MUTANTS_BODY` sandbox under `.mutants-tmp` with `MUTANTS_CAP` and `TMPDIR`; the base test file is written as `<sandbox>/.base/test_<module>_base.py` only after the head session finishes, and `.base` is on the base arm's `PYTHONPATH` only.
- **R8.** The dir is red with `base suite unjudgeable: test-command must name one test module` unless both the head and the merge base `cosmic-ray.toml` `test-command` are `python3 -m unittest test_<module>`.
- **R9.** Every run in both arms has `PYTHONPATH` holding a generated `sitecustomize.py` that sets `hypothesis.core.function_digest` to a SHA-384 of the test's `__qualname__` and calls `settings.register_profile("mutation-gate", derandomize=True, database=None, deadline=None, suppress_health_check=list(HealthCheck))` and `settings.load_profile("mutation-gate")`.
- **R10.** Each shard runs a preflight under that `PYTHONPATH` in which two `@given` functions with the same `__qualname__` and different bodies must draw the same first 10 examples, and is red with `hypothesis profile not active (hypothesis <version>)` when they differ or the preflight errors.
- **R11.** `scripts/mutation_base_runner.py` runs the base test module and, given a signature file, exits non-zero when any test recorded as `pass` fails or errors, or any test recorded as failing has a different signature, a signature being (`fail` or `error`, exception type, line of the innermost frame in the base test file, exception message); in record mode it writes that file.
- **R12.** Each shard records signatures twice on the unmutated head module, and the dir is red with `base suite unjudgeable: <cause>` followed by the failing test ids when either run times out, any result is `unittest.loader._FailedTest`, a class- or module-level setup errors, or the two recordings differ.
- **R13.** For each of its own head survivors, a shard calls `cosmic_ray.mutating.mutate_and_test` with that job's stored `MutationSpec`, the base runner command and the toml `timeout`; `killed` and `survived` are accepted, and any other outcome or an exception makes the dir red with `replay failed: <outcome>` and the job id.
- **R14.** When a base kill in R13 was a timeout, the shard re-runs that mutant under the head tests and the base runner with twice the toml `timeout`, and counts a weakening only when the base runner kills it and the head tests do not.
- **R15.** A dir is red when any mutant is killed by the base arm and survives the head arm, and its summary reads `weakened: <count> mutants killed by base tests survive head tests`, then for each mutant its job id, operator, occurrence, diff and `repro: make -C <dir> mutants-weakening BASE=<sha> JOB=<job id>`.
- **R16.** A dir in `py_test_dirs` keeps the existing rule that any head survivor on a line the PR added to `<module>.py` is red.
- **R17.** A dir whose `test_<module>.py` exists at the merge base and not at head is red with `test_<module>.py deleted`; one whose merge base has no `test_<module>.py` skips R11-R15 and prints `no base test file: weakening check skipped`.
- **R18.** `py_canary` runs the weakening path on committed fixtures `tests/fixtures/mutation_weakening/test_sq_base.py` and `test_sq_head.py` (head drops one assertion) and is red unless it reports `weakened: 1` naming the expected mutant.
- **R19.** The planners compute all items before any shard runs: each head job that the merge base's copy of `scripts/cosmic_ray_prune.py` prunes under the head `mutants-equivalent.toml` but not under the merge base's, keyed by (operator, function, mutated line text, line above, ordinal); and each changed key of `<dir>/cosmic-ray.toml`, keyed by (dir, key).
- **R20.** For each planned crate, each mutant excluded by config in the head (its `--no-config` listing minus its configured listing) whose key (file, function, genre, description without `<line>:<col>:`, source text under its span, ordinal) is not excluded at the merge base is an item, and each changed `.cargo/mutants.toml` key other than `exclude_re` is an item.
- **R21.** For each planned crate, each (file, function) with mutants in the merge base `--no-config` listing, none in the head `--no-config` listing, and `fn <name>` still present in the head file is an item, and each hunk under `<crate>/src/` whose added lines, with comments and whitespace removed, contain `mutants::skip` is an item.
- **R22.** Each changed file among `.github/workflows/mutation-pr.yml`, `scripts/mutation-*.sh`, `scripts/mutation_*.py`, `scripts/cosmic_ray_*.py`, the `Makefile` templates under `scripts/crate_templates/`, every rendered crate or Python `Makefile`, and the `tests/fixtures/mutation_weakening/` files is an item with target `gate`.
- **R23.** Each item makes `mutation-pr` red, naming the item, its target and the remedy, unless the latest commit in the range that carries `Mutation-Gate-Reviewed: <target>: <reason>` for its target (reason at least 10 characters) and that `git verify-commit` accepts with `gpg.format=ssh` and `gpg.ssh.allowedSignersFile` set to the merge base's `.github/mutation-gate-allowed-signers` contains the item's content key.
- **R24.** `.github/mutation-gate-allowed-signers` lists only `sk-ssh-ed25519` keys, none with `no-touch-required`, and a test fails on any other key type or that option.
- **R25.** A verified trailer commit for a dir also clears that dir's R12 and R15 reds when `<dir>/<module>.py` and `<dir>/test_<module>.py` are unchanged between it and head, and the summary then says `cleared by Mutation-Gate-Reviewed <commit>`; a trailer on an unsigned or unaccepted commit is reported as `trailer ignored: <commit>: <reason>`.
- **R26.** `mutation-pr.yml` sets `concurrency: { group: mutation-pr-${{ github.event.pull_request.number }}, cancel-in-progress: true }`.
- **R27.** CI runs the Python steps by calling `make -C <dir> mutants-weakening BASE=<sha> MUTANT_SHARD=<k>/<n>`, a target every Python `Makefile` gains from `scripts/crate_templates/python/Makefile`, which also accepts `JOB=<job id>` and writes nothing in the tracked tree; `scripts/mutation-gate-items.sh <base-sha>` prints every item and its clearance state locally.
- **R28.** `scripts/mutation-pr-run.sh --whole [--shard <k>/<n> --expect <count>] <crate-dir>` runs one crate's whole mutant set locally and exits non-zero on the R4 red conditions.
- **R29.** `tests/scripts/mutation_pr_detect.bats` covers R1 (a `tests/` fixture, a non-`.rs` `src/` file, a `.cargo/mutants.toml` change and a `Cargo.toml` `[[test]]` change each select the crate; a `[dependencies]` version change alone does not) and R5 (added-only, deleted-only and file-deletion changes to `test_<module>.py`, and changes to `cosmic-ray.toml` or `mutants-equivalent.toml`, each select the dir; a change to `<module>.py` alone does not).
- **R30.** A test on a copy of `sq/` requires: dropping one assertion that alone kills a known mutant reports it under `weakened: 1`; only adding a test reports `weakened: 0`; a cosmetic edit to every `@given` body reports `weakened: 0`; weakening a base test that fails on the unmutated head (its expected value changed) still reports the mutant it alone killed; an import-breaking rename and a base test whose failure message varies between runs are each red with `base suite unjudgeable`; a base test sleeping past the timeout is red and leaves no process running; an untested line added to `sq.py` with a test-file change is red under R16; a replay forced to `no-test` is red with `replay failed`; a broken `sitecustomize` is red with `hypothesis profile not active`; and the tracked `sq/` files are byte-identical after every case.
- **R31.** Tests cover R19-R25: a new equivalents entry, a `variant` change and a duplicated entry are items; a pure line shift of `exclude_re` and of an equivalents entry is not; a new or retargeted pattern, an `additional_cargo_test_args` change, `#[mutants::skip]`, `#[mutants :: skip]`, a line-split or comment-split `mutants::skip`, and a function wrapped in a no-op macro are each items; an edit to `scripts/mutation-pr-detect.sh` is a `gate` item; each item clears only with a verified trailer for its target, not with an unsigned one, a non-`sk` signature, a trailer for another target or a 9-character reason, and an item first added after the trailer commit is red.
- **R32.** Root `CLAUDE.md` (Mutation testing sections) and an ADR describe the whole-crate PR rule, the Python weakening check, the items and the signed trailer, with repro commands; `docs/superpowers/README.md` removes the Backlog row "PR mutation gates miss test-only weakening (Rust and Python)"; root `CLAUDE.md` stays at or under 30,000 bytes.

- **V1.** Positive control before the PR is marked ready: a throwaway draft PR that deletes one assertion from a crate's `#[cfg(test)]` module, leaving a mutant uncaught, shows `mutation-pr` red naming that mutant; closed and its branch deleted.
- **V2.** Positive control: a throwaway draft PR that weakens one assertion in `sq/test_sq.py` shows `mutation-pr` red with `weakened: 1` naming the mutant; closed and deleted afterwards.
- **V3.** Negative control: a throwaway draft PR that only adds a test to `sq/test_sq.py` shows `mutation-pr` green.
- **V4.** Positive control: a throwaway draft PR that adds one `[[equivalent]]` entry to `sq/mutants-equivalent.toml` shows `mutation-pr` red naming it, then green after the operator pushes a FIDO-signed `Mutation-Gate-Reviewed: sq: <reason>` commit; an unsigned commit with the same line stays red.
- **V5.** Timing: throwaway draft PRs that add one test to `collatz/test_collatz.py`, `descartes/test_descartes.py` and `pi/test_pi.py` record every shard's wall time and concurrent jobs; a shard past about 45 minutes changes the R6 constants before merge.
- **V6.** False-positive replay: before merge, run the weakening path locally on the 25 real commits since 2026-09-26 that changed a module and its test file with at most 5% failing base tests; every `weakened` result is inspected and any that is not a real weakening is fixed or recorded before merge.
- **V7.** Record the wall time of the PR's own `mutation-pr` run and of V1-V5; a zeta-rs whole-crate run is measured or projected, and any Rust shard past about 50 minutes lowers B per ADR-0046.

- **N1.** The monthly `mutation-testing.yml` and `mutation-testing-python.yml` sweeps do not change.
- **N2.** No committed survivor, missed or baseline list is added; the only committed fixtures are the R18 canary files.
- **N3.** The local pre-push hook runs no mutants.
- **N4.** The required check stays `mutation-pr`; no new required check is added to branch protection.
- **N5.** Nothing in the gate or the local targets writes to a tracked file in the working tree.
- **N6.** The Python changed-line gate's behaviour for dirs not in `py_test_dirs` does not change.
- **N7.** No agent, script or workflow creates a signature for a `Mutation-Gate-Reviewed:` commit; only the operator's FIDO key does.

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

### Round 3 (all four reviews, reviewed at `d823b60`, the round-2 revision)

#### Goal-Fit

Finding: Rust and exemption halves are the right shape; the listing and prune comparisons are ground truth; the trailer is durable because squash merges keep commit messages (`squash_merge_commit_message: COMMIT_MESSAGES`). Load-bearing flaw: R6's time-based sizing ignores mutants that hang to the 60 s timeout. collatz's suite runs in about 0.5 s, so it gets 1 shard, but sweep run 41279088956 timed out 63 of its 420 mutants and its 10 cells summed about 75 minutes of head work: one shard exceeds `timeout-minutes: 60`, so every PR touching `test_collatz.py` goes red on the job kill. sq, factorial, perfect-numbers and fib also collapse to one shard (22-33 min). V5 cannot see it. `obsolete base tests:` on a possibly green run is still a log. The spec's per-dir survivor figures are stale (pi 368, e 396 in the latest report).
Assumption: Single-assertion weakenings expose at least one mutant no other head test kills; settle by deleting each assertion of `test_sq.py` and `test_collatz.py` in turn and counting `weakened >= 1`.
Disposition: Addressed (operator, 2026-11-26: "Round 4 on full design"): shard floor of 10, collatz in V5, obsolete tests judged by failure signature.

#### Ergonomics

Finding: Load-bearing: the trailer hook does not stop an agent: `printf 'yes\n' | script -qec "git commit -F ../msg" /dev/null` committed the trailer from an agent shell, rc=0; `pty.spawn`, `unbuffer` and `expect` do the same, and `git cherry-pick` writes a trailer without running commit-msg. collatz (62 timeouts, 82.2 min sweep sum) runs in one shard and times out; descartes hits the 20-shard cap at about 40-45 min per shard, so V5's lever is inert. 13 of 107 PRs since 2026-09-26 touched an exemption file; one template edit is 10 items; any fix-up after the trailer re-reds; the iPad and Claude Code's `!` prompt have no `/dev/tty`. The hook's own tests hang in a real terminal, and the commit-msg early exit for `Revert ` subjects precedes any new check. Exemption reds should be computed in the planner, not after a 45-minute run. Several reds lack a job id or remedy.
Assumption: Agents cannot give the hook a terminal; refuted by the `script` probe.
Disposition: Addressed (operator, 2026-11-26: "Round 4 on full design"; "Yes, FIDO key signing"): the hook is dropped in favour of a touch-required hardware-key signature verified in CI; shard floor and cap revised; exemption items computed in the planners; every red names its job id and remedy.

#### Risk

Finding: Load-bearing: R18's listing comparison goes red on a pure line shift (the base config's `:line:col:` patterns match nothing on head source), contradicting R27, and the same line-bound identity breaks R19's containment; round 2's normalization was dropped. The R9 preflight is a tautology (it checks the attribute it just assigned); a hypothesis bump could make the patch dead while it passes. The `/dev/tty` hook blocks the operator's own test runs and is bypassed by pty allocation. Sizing ignores timeouts (2% timeouts doubles a triangle shard). A mutant near the 60 s timeout can survive the head arm and time out in the base replay, a false `weakened`. The exemption machinery's complexity outgrows the threat.
Assumption: No mutant runs close to the 60 s timeout; settle from the last sweep's per-job durations and TIMEOUT counts.
Disposition: Addressed (operator, 2026-11-26: "Round 4 on full design"): content-keyed mutant identity, behavioural preflight, signing instead of the hook, shard floor, near-timeout re-run at twice the timeout.

#### Adversarial Spec Review

Finding: A (main recall hole): excluding base tests that fail on the unmutated head drops exactly the tests a PR had to edit, which is where an agent weakens; mutants they alone killed sit on unchanged lines (9 of 36 real commits hit this path). B: listing comparison reds on line shifts (3 of 8 recent `mutants.toml` commits were pure shifts); normalizing reopens retargeting; item identity is undefined. C: `#[mutants:: /* c */ skip]`, a comment inside a split attribute, and wrapping a function in a no-op `macro_rules!` invocation each removed mutants unseen by the scan. D: crate `Makefile` mutants arguments, the head copy of `cosmic_ray_prune.py`, and a cleared `unittest discover` test-command (which would also discover `test_<module>_base.py` and blind the check permanently) are outside the exemption check. E: the `/dev/tty` hook is not a boundary (`script` gave a `read </dev/tty` the answer `yes`); a touch-required FIDO signature verified with `git verify-commit` is. F: a false `weakened` red (for example after renaming a `@given` test) has no clearance path. Preflight checks the attribute, not behaviour.
Assumption: Excluded base tests remove few weakening-relevant kills; settle on the 9 low-obsolete real commits by comparing kills with and without the excluded tests.
Disposition: Addressed (operator, 2026-11-26: "Round 4 on full design"; "Yes, FIDO key signing"): failure-signature judging of failing base tests instead of exclusion, content-keyed identity, function-disappearance check plus comment-stripped scan, gate-shaping files as items, the base file outside the head arm's path and written after the head session, signed trailer, which may also clear a `weakened` red.
