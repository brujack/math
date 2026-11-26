# PR mutation gates see test weakening

- **Date:** 2026-11-26 (revised after Multi-Lens Review rounds 1-4)
- **Backlog row closed:** "PR mutation gates miss test-only weakening (Rust and Python)" (P2)
- **Related:** ADR-0042 (Rust sweep holds zero missed), ADR-0044 (per-PR Python gate), ADR-0046
  (shard the Rust runs), `specs/2026-11-05-worldclass-slice5-rust-pr-mutation-ratchet-design.md`,
  `specs/2026-11-07-worldclass-slice8-python-pr-mutation-gate-design.md` ("Known gap, not closed here")

## Summary

Both per-PR mutation gates judge only mutants on lines a PR changes. A PR that deletes or weakens
tests changes no production line, so it is never judged; a PR can also exempt the mutant it exposes,
or change the gate that judges it. This spec closes those holes with three parts:

- **Rust (in `mutation-pr`):** any change to a crate's `src/`, `tests/`, `.cargo/`, `build.rs` or the
  test-shaping parts of its `Cargo.toml` runs every mutant in that crate, held to the sweep's rule.
- **Python (in `mutation-pr`):** a change to `test_<module>.py`, `cosmic-ray.toml` or
  `mutants-equivalent.toml` mutates the whole head module and runs the head tests on every mutant;
  each shard then replays its own head survivors under the base tests through an assertion-continuing
  runner, so a failure early in a base test does not hide its later assertions. A mutant the base
  tests kill and the head tests do not is a weakening.
- **Items (new required check `mutation-gate-items`):** a `pull_request_target` job that runs only
  master's code computes what the PR newly exempts and which gate-shaping content it changes, keyed by
  content and value. Every item is red unless a FIDO-signed `Mutation-Gate-Reviewed:` commit, verified
  against master's allowed-signers file, approved that exact content.

## Why

Measured 2026-11-26 on master `0bc607f`:

- `scripts/mutation-pr-detect.sh` puts a Python dir in `py_src_dirs` only when `git diff --numstat`
  shows added lines in `<dir>/<module>.py` (lines 15-18, 37). A PR touching only `test_<module>.py`
  runs no Python mutant.
- A Rust crate is selected only when a changed path matches `<crate>/src/**/*.rs` (line 66), and its
  mutants are filtered by `--in-diff`. A hunk inside a `#[test]` yields `INFO No mutants to filter`,
  exit 0. A change under `<crate>/tests/` (13 crates have one) or to `Cargo.toml` selects no crate.
- The 90% coverage floors catch a large test deletion but not a weakened assertion.
- The Rust sweep holds 0 missed (ADR-0042; run 45479226540 green), so a Rust weakening is reported
  within a month, after merge. The Python sweep carries about 1,250 open survivors (issue #184; latest
  per-dir pi 368, e 396), so a new Python survivor is never reported.
- Exemption channels are looser than the gate: `mutants-equivalent.toml`, `cosmic-ray.toml`'s
  `test-command`, `.cargo/mutants.toml` (`exclude_re`, zeta's `additional_cargo_test_args`),
  `#[mutants::skip]`, and macro-wrapped code all remove mutants or tests.
- The gate judges itself: `mutation-pr.yml` runs on `pull_request`, so the PR head's workflow and
  scripts run, and branch protection requires only checks named `secret-scan` and `mutation-pr`
  (`enforce_admins: false`).

Agents write most of the tests here, weakening a test to make a gate pass is on the executor FORBIDDEN
list, and auto-merge lands a green PR without review. No weakening incident in this repo has been
measured. The operator chose this semantic design over a static assertion-line rule, a fifth review
round, a new required check and signing with a forwarded FIDO key (2026-11-26).

## Facts this design rests on (measured 2026-11-26)

- **Rust whole-crate cost.** Sweep run 45479226540 (13 crates, 2,221 mutants, 37 shards at B = 75) took
  9 minutes of wall time; zeta-rs (748 mutants) shards run about 37 min against `timeout-minutes: 60`.
  The Rust trigger fires on the same 17 of the last 100 PRs as today's.
- **cargo-mutants listing.** `cargo mutants --list --json` gives, per mutant, `file`,
  `function.function_name`, `genre`, `replacement`, `name` (`<file>:<line>:<col>: <description>`) and a
  `span`; `--config <FILE>` and `--no-config` choose the configuration. 11 of the 12 mutants excluded by
  today's configs are `BinaryOperator`, whose span text is a single operator token, so a key must carry
  the whole source line. A line-shift-only commit (02390d7, 6fa6ae8) produced 0 changed keys.
- **Code hidden from cargo-mutants.** Under 27.1.0, `#[mutants::skip]` in any spelling (spaced, split
  across lines, with a comment inside), a function wrapped in a no-op `macro_rules!` invocation, and a
  single expression wrapped in a local macro or `dbg!(...)` each removed mutants from `--list`.
- **Python whole-module size** (`cosmic-ray init`): descartes 3663, triangle 3113, pi 1828, e 1621,
  perfect-numbers 679, factorial 500, collatz 420, amicable 252, fib 232, sq 164. Local suite times:
  descartes 7.0 s, e 5.5 s, pi 4.5 s, sq 1.0 s, triangle 0.8 s, the rest 0.4-0.6 s. Sweep run
  41279088956: collatz cells summed 82.2 min with 62 timeouts, slowest cell 759 s.
- **`cosmic-ray init` parses, it does not import.** `commands/init.py` builds jobs with
  `get_ast_from_path` (parso); nothing in `cosmic_ray` calls `import_module`, `exec` or `runpy` on the
  target, so listing a PR's Python mutants executes no PR code.
- **Replay identity and timeout.** `cosmic_ray.mutating.mutate_and_test(mutations, test_command,
  timeout)` applies stored `MutationSpec`s and runs `cosmic_ray.testing.run_tests`, which sets
  `PYTHONDONTWRITEBYTECODE=1`, starts the tests in a new session, kills the whole group on timeout and
  returns `KILLED` with output `"timeout"`. Replaying all 164 of sq's session jobs with their stored
  specs gave identical diffs (164 of 164). Out-of-range occurrences return `no-test`; an unlaunchable
  command returns `incompetent`. Without `PYTHONDONTWRITEBYTECODE`, a module edited in the same second
  was shadowed by a stale `.pyc`.
- **Masking and the continuing runner.** A base test stops at its first failing assertion: with an
  obsolete `label(3) == "sq 3"` assertion first, plain unittest never reached `sq(3) == 9`, so the
  `n*n -> n+n` mutant left the signature unchanged. A runner that rewrites each `self.assert*(...)`
  statement into a record-and-continue block recorded, under that mutant, `(6, AssertionError,
  '6 != 9')` and, inside a `subTest`, `(9, AssertionError, '8 != 16')`, beside the unchanged line-5
  failure.
- **Obsolete base tests in real PRs.** Of 36 commits since 2026-09-26 that changed both a module and its
  test file: 2 had no base file, 16 no failing base test, 9 at most 5%, 7 (68a2f8a, math#171) 13-65%,
  2 (949fd22) hung past 900 s, 0 collapsed to `_FailedTest`. A synthetic import-breaking rename collapsed
  all 53 base tests into one `_FailedTest`.
- **Message stability.** `repr` of a set changed order in 7 of 8 processes without a fixed
  `PYTHONHASHSEED`, and object reprs carry addresses that change every run.
- **Subprocess tests.** `amicable/test_amicable.py:451` and `collatz/test_collatz.py:357` run
  `Path(__file__).parent / "<module>.py"`, so the base test file must sit beside the module.
- **Hypothesis.** 8 of 10 Python test files import hypothesis; 9 set no `deadline`. A `sitecustomize.py`
  that replaces `hypothesis.core.function_digest` (called at `core.py:720` in 6.168.5) with a digest of
  the test's `__qualname__` and loads a profile with `derandomize=True, database=None, deadline=None,
  suppress_health_check=list(HealthCheck)` drew identical examples for two different bodies. A
  `sitecustomize.py` placed earlier on `sys.path` preempts it, and a failing one only prints a warning.
- **Prune strictness.** `scripts/cosmic_ray_prune.py` exits 1 (`entry N: matches no spec`) when any
  entry matches no job, which happens on a legitimate edit of an entry's line (probe on a copy of `e/`).
- **Signing.** `ssh-keygen -Y verify` (used by `git verify-commit` with `gpg.format=ssh`) rejects an
  `sk-` signature without the user-presence flag unless the allowed-signers entry says
  `no-touch-required`; a software `SSH_SK_PROVIDER` can set that flag, so the trust root is key
  enrolment, not key type. Today `claude`'s forwarded agent holds no `sk-` key and `gpg.format` is
  unset. A terminal prompt is not a boundary (`script -qec` satisfied a `/dev/tty` read from an agent
  shell). The repo squash-merges with `COMMIT_MESSAGES`.
- **Item frequency.** Over the last 100 PRs, 35 touched a gate-shaping or exemption file as round 4
  defined them; most gate hits were rendered `Makefile`s changed outside their mutation recipes, and 8
  Renovate PRs since 2026-08-24 changed only action digests in `mutation-pr.yml`.

## Design

### Rust: whole crate on any crate change (in `mutation-pr`)

1. `mutation-pr-detect.sh` selects a crate for `rs_dirs` when a changed path is under `<crate>/src/`,
   `<crate>/tests/` or `<crate>/.cargo/`, is `<crate>/build.rs`, or is `<crate>/Cargo.toml` with a
   changed line outside its `[dependencies]`, `[dev-dependencies]` and `[build-dependencies]` tables.
2. `mutation-rs-plan` plans the selected crates with `--whole`; a fault unit is red.
3. Each shard uses the sweep's rule through `scripts/mutation-classify.sh`.
4. The amicable-rs canary is unchanged; toolchain drift surfaces on the next PR touching the crate.

### Python: same code, two test suites (in `mutation-pr`)

Triggered for a dir when its `test_<module>.py`, `cosmic-ray.toml` or `mutants-equivalent.toml`
changes, in addition to the existing module-change trigger.

1. **Planning.** The planner times the head suite once on the unmutated head (`s` seconds) and plans
   `n = min(40, max(10, ceil(K * s / 600)))` shards per dir; `mutation-py` has `timeout-minutes: 60`.
2. **Environment.** Both arms run in the `MUTANTS_BODY` sandbox (its file set, `MUTANTS_CAP`, `TMPDIR`
   under `.mutants-tmp`) with `PYTHONHASHSEED=0`, `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH` holding
   only a generated directory with the `sitecustomize.py` of step 3. The head session runs first; only
   then is the merge base's test file written beside the module as `test_<module>_base.py`. Both the
   head and the merge base `test-command` must be exactly `python3 -m unittest test_<module>`; otherwise
   the dir is unjudgeable.
3. **Deterministic hypothesis.** The generated `sitecustomize.py` replaces
   `hypothesis.core.function_digest` with a SHA-384 of the test's `__qualname__` and loads the profile
   `mutation-gate` (`derandomize=True, database=None, deadline=None,
   suppress_health_check=list(HealthCheck)`). A behavioural preflight requires two `@given` functions
   with the same `__qualname__` and different bodies to draw the same first 10 examples, and is red with
   the installed hypothesis version otherwise.
4. **Head arm.** Each shard runs the head tests on every mutant in its slice (the existing session
   path). Any survivor on a line the PR added to `<module>.py` is red, as today.
5. **Base runner.** `scripts/mutation_base_runner.py`, started with the sandbox as working directory,
   inserts the sandbox at `sys.path[0]` after interpreter start-up, parses `test_<module>_base.py`, and
   rewrites every expression statement that calls `self.assert*` and every `assert` statement into a block
   that records `(line, exception type, message)` on `AssertionError` and continues. It runs every test
   and produces, per test id, a signature: its final outcome (`pass`, `fail`, `error`, `skip`,
   `expected-failure` or `unexpected-success`), the recorded assertion failures in order, and for an
   error the exception type and the innermost line in the base file; messages have every `0x[0-9a-f]+`
   replaced by `0x?`.
6. **Judgeable base suite.** The shard records signatures twice on the unmutated head module. The dir is
   unjudgeable, red with the affected test ids, when either run times out, any result is
   `unittest.loader._FailedTest`, any class-, module- or per-test `setUp` errors, or the two recordings
   differ.
7. **Replay.** For each of its own head survivors, the shard calls
   `cosmic_ray.mutating.mutate_and_test([<the session's stored MutationSpec>], <base runner command>,
   <the merge base's toml timeout>)`. The runner exits non-zero, and the mutant counts as killed by the
   base arm, when any test's signature differs from the recording. `killed` and `survived` are the only
   accepted outcomes; any other outcome or an exception is red with `replay failed: <outcome>` and the
   job id. When the base kill was a timeout, the shard re-runs the mutant under both arms with twice the
   timeout and counts a weakening only if the base runner kills it and the head tests do not.
8. **Verdict.** A mutant killed by the base arm and surviving the head arm is a weakening: the summary
   prints `weakened: <count> mutants killed by base tests survive head tests`, then each mutant's job id,
   operator, occurrence, diff and `repro: make -C <dir> mutants-weakening BASE=<sha> JOB=<job id>`.
9. **Missing files.** A `test_<module>.py` present at the merge base and absent at head is red with
   `test_<module>.py deleted`; a merge base without one skips steps 5-8 and says so.
10. **Standing canary.** `py_canary` runs the weakening path on committed fixtures
    `tests/fixtures/mutation_weakening/test_sq_base.py` and `test_sq_head.py` (head drops one assertion)
    and on a masking pair (an obsolete first assertion hides a later one) and requires `weakened: 1`
    naming the expected mutant in each.

### Items (new required check `mutation-gate-items`)

A new workflow `.github/workflows/mutation-gate-items.yml` runs on `pull_request_target` with
`permissions: contents: read` and no secrets. It checks out master's code, fetches the PR head's objects
into a separate directory without executing anything from them, and runs master's
`scripts/mutation-gate-items.sh`. It only reads PR files and runs listings (`cosmic-ray init`, which
parses, and `cargo mutants --list`). It is red when any item is uncleared, within minutes of a push.

Items and their keys (every key carries the content it approves):

- **Python equivalents.** The head module's jobs are pruned with a tolerant copy of master's prune
  matching (entries that match no job are skipped and listed), once with the merge base's
  `mutants-equivalent.toml` and once with the head's. Each job pruned only by the head file is an item,
  keyed by (dir, operator, function, mutated line text, line above, ordinal).
- **Python config.** Each changed key of `<dir>/cosmic-ray.toml`, keyed by (dir, key, new value).
- **Rust exclusions.** For base source with the base config and head source with the head config, the
  excluded set is the `--no-config` listing minus the configured listing, matched by `name` within one
  tree. Each mutant is keyed by (crate, file, function, genre, description without `<line>:<col>:`, the
  whitespace-normalized source line, the line above, ordinal from the `--no-config` listing). Each head
  excluded key absent at the merge base is an item. Each changed `.cargo/mutants.toml` key other than
  `exclude_re` is an item keyed by (crate, key, new value).
- **Rust hidden code.** In each hunk under `<crate>/src/`, the added lines with comments and whitespace
  removed are searched for `mutants::skip`, for `macro_rules!`, and for any macro invocation other than
  `println!`, `eprintln!`, `print!`, `eprint!`, `format!`, `write!`, `writeln!`, `vec!`, `panic!`,
  `matches!`, `unreachable!`, `todo!`, `assert!`, `assert_eq!`, `assert_ne!`, `debug_assert!`,
  `debug_assert_eq!` and `debug_assert_ne!`; each hit is an item keyed by (crate, file, normalized added
  text).
- **Gate-shaping content.** For each changed file among `.github/workflows/mutation-pr.yml`,
  `.github/workflows/mutation-gate-items.yml`, `scripts/mutation-*.sh`, `scripts/mutation_*.py`,
  `scripts/cosmic_ray_*.py`, `.github/mutation-gate-allowed-signers` and its test, and the
  `tests/fixtures/mutation_weakening/` files, an item keyed by (path, new blob hash); for `Makefile`
  templates and rendered crate or Python `Makefile`s, an item only when the text of their `mutants*`
  targets or `MUTANTS_*` variables changes, keyed by (path, hash of that text). A change to
  `mutation-pr.yml` that only replaces the 40-hex SHA of a `uses: actions/<name>@<sha>` line is not an
  item.

Clearance: a commit in the PR range that is an ancestor of head, carries the line
`Mutation-Gate-Reviewed: <target>: <reason>` (target a dir, a crate dir or `gate`; reason at least 10
characters), and whose signature `git verify-commit` accepts with `gpg.format=ssh` and
`gpg.ssh.allowedSignersFile` set to master's `.github/mutation-gate-allowed-signers` clears every item of
its target whose key is present in that commit's tree. Because keys carry content and value, a later
change produces a new key and is red again. Every item red names the item, its target and the remedy:
"commit `git commit --allow-empty -S -m 'chore: mutation gate review' -m 'Mutation-Gate-Reviewed:
<target>: <reason>'` in the PR worktree with the operator's forwarded FIDO key, touching only for a
prompt you started". A trailer on an unsigned or unaccepted commit is reported as
`trailer ignored: <commit>: <reason>`.

The same verified commit, for its dir, also clears an unjudgeable base suite or a `weakened` red in
`mutation-pr` when `<module>.py` and `test_<module>.py` are unchanged between it and head.

Bootstrap: the PR that adds `mutation-gate-items.yml` is not judged by it (`pull_request_target` runs
master's workflow, which does not have it yet). That PR adds `.github/mutation-gate-allowed-signers`
with the operator's key. After it merges, the operator adds `mutation-gate-items` to branch protection.

### Known limits

- A weakening on a mutant another head test still kills is invisible to any mutation-based gate.
- An assertion written as a bare expression other than `self.assert*` or `assert` (for example a helper
  that asserts) still stops its test at the first failure.
- New code inside an allowed macro (such as `vec![...]`) is not mutated by cargo-mutants.
- A forwarded key means an agent can raise a touch prompt; the touch proves presence, so the operator
  must only touch for a signing they started. Enrolment in the allowed-signers file is the trust root.
- A uniform refactor of many test files plans up to 40 shards per dir and runs in waves.

### Workflow and local repro

- `mutation-pr.yml` sets `concurrency: { group: mutation-pr-${{ github.event.pull_request.number }},
  cancel-in-progress: true }`.
- Python: `make -C <dir> mutants-weakening BASE=<sha> MUTANT_SHARD=<k>/<n>` (or `JOB=<job id>`), used by
  CI and locally.
- Rust: `scripts/mutation-pr-run.sh --whole [--shard <k>/<n> --expect <count>] <crate>`.
- Items: `scripts/mutation-gate-items.sh <base-sha> <head-sha>` prints every item and its clearance.

## Requirements

- **R1.** `scripts/mutation-pr-detect.sh` prints a crate dir in `rs_dirs` when a changed path starts with `<crate>/src/`, `<crate>/tests/` or `<crate>/.cargo/`, whatever the extension, equals `<crate>/build.rs`, or is `<crate>/Cargo.toml` with a changed line outside its `[dependencies]`, `[dev-dependencies]` and `[build-dependencies]` tables.
- **R2.** In `mutation-pr.yml`, `mutation-rs-plan` plans every selected crate with `scripts/mutation-rs-plan.sh --whole <crate-dir>...` and never passes `--in-diff` for a selected crate.
- **R3.** A `--whole` fault unit (`"fault": "<cause>"`) makes `mutation-pr` red and its summary names the crate and the cause.
- **R4.** A Rust PR shard is red on any missed mutant, on `caught + missed + timeout == 0`, on a missing `mutants.out/outcomes.json` or `mutants.out/exit-code`, or on a failed baseline, and green on timeouts beside at least one caught mutant, using `scripts/mutation-classify.sh`.
- **R5.** `mutation-pr-detect.sh` prints a Python dir in a new output `py_test_dirs=<sorted dirs>` when `git diff --numstat --no-renames` shows any added or deleted line in `<dir>/test_<module>.py`, `<dir>/cosmic-ray.toml` or `<dir>/mutants-equivalent.toml`, including a file deletion.
- **R6.** The Python planner times each `py_test_dirs` dir's head suite once on the unmutated head module (`s` seconds), plans `n = min(40, max(10, ceil(K * s / 600)))` whole-module shards, and `mutation-py` has `timeout-minutes: 60`.
- **R7.** Both arms of every `py_test_dirs` shard run in the `MUTANTS_BODY` sandbox under `.mutants-tmp` with `MUTANTS_CAP`, `TMPDIR`, `PYTHONHASHSEED=0`, `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH` holding only the generated `sitecustomize.py` directory; `test_<module>_base.py` is written beside the module only after the head session finishes.
- **R8.** The dir is red with `base suite unjudgeable: test-command must be python3 -m unittest test_<module>` unless both the head and the merge base `cosmic-ray.toml` `test-command` are exactly that.
- **R9.** The generated `sitecustomize.py` sets `hypothesis.core.function_digest` to a SHA-384 of the test's `__qualname__` and calls `settings.register_profile("mutation-gate", derandomize=True, database=None, deadline=None, suppress_health_check=list(HealthCheck))` and `settings.load_profile("mutation-gate")`.
- **R10.** Each shard runs a preflight in which two `@given` functions with the same `__qualname__` and different bodies must draw the same first 10 examples, and is red with `hypothesis profile not active (hypothesis <version>)` when they differ or the preflight errors.
- **R11.** `scripts/mutation_base_runner.py` inserts its working directory at `sys.path[0]` after start-up, rewrites every expression statement calling `self.assert*` and every `assert` statement in `test_<module>_base.py` to record `(line, exception type, message)` on `AssertionError` and continue, and writes or compares per-test signatures made of the final outcome (`pass`, `fail`, `error`, `skip`, `expected-failure`, `unexpected-success`), the recorded assertion failures in order, and for an error its exception type and innermost line in the base file, with every `0x[0-9a-f]+` in a message replaced by `0x?`; in compare mode it exits non-zero when any test's signature differs.
- **R12.** Each shard records signatures twice on the unmutated head module, and the dir is red with `base suite unjudgeable: <cause>` and the affected test ids when either run times out, any result is `unittest.loader._FailedTest`, any class-, module- or per-test `setUp` errors, or the two recordings differ.
- **R13.** For each of its own head survivors, a shard calls `cosmic_ray.mutating.mutate_and_test` with that job's stored `MutationSpec`, the base runner command and the merge base's toml `timeout`; `killed` and `survived` are accepted, and any other outcome or an exception is red with `replay failed: <outcome>` and the job id.
- **R14.** When a base kill in R13 was a timeout, the shard re-runs that mutant under the head tests and the base runner with twice that timeout, and counts a weakening only when the base runner kills it and the head tests do not.
- **R15.** A dir is red when any mutant is killed by the base arm and survives the head arm, and its summary reads `weakened: <count> mutants killed by base tests survive head tests`, then for each mutant its job id, operator, occurrence, diff and `repro: make -C <dir> mutants-weakening BASE=<sha> JOB=<job id>`.
- **R16.** A dir in `py_test_dirs` keeps the existing rule that any head survivor on a line the PR added to `<module>.py` is red.
- **R17.** A dir whose `test_<module>.py` exists at the merge base and not at head is red with `test_<module>.py deleted`; one whose merge base has no `test_<module>.py` skips R11-R15 and prints `no base test file: weakening check skipped`.
- **R18.** `py_canary` runs the weakening path on committed fixture pairs under `tests/fixtures/mutation_weakening/` (one where head drops an assertion, one where an obsolete first assertion masks a later one) and is red unless each reports `weakened: 1` naming its expected mutant.
- **R19.** `.github/workflows/mutation-gate-items.yml` runs on `pull_request_target` with `permissions: contents: read`, checks out the base branch, fetches the PR head into a separate directory, never executes a file from it, and runs the base branch's `scripts/mutation-gate-items.sh <base-sha> <head-sha>`, whose only tools on PR content are `git`, `cosmic-ray init` and `cargo mutants --list`; its job is named `mutation-gate-items`.
- **R20.** Python items: each head job pruned under the head `mutants-equivalent.toml` but not under the merge base's, using a tolerant prune that skips and lists entries matching no job, keyed by (dir, operator, function, mutated line text, line above, ordinal); and each changed `<dir>/cosmic-ray.toml` key, keyed by (dir, key, new value).
- **R21.** Rust items: each mutant excluded by config at head (the `--no-config` listing minus the configured listing, matched by `name`) whose key (crate, file, function, genre, description without `<line>:<col>:`, whitespace-normalized source line, line above, ordinal in the `--no-config` listing) is not excluded at the merge base; and each changed `.cargo/mutants.toml` key other than `exclude_re`, keyed by (crate, key, new value).
- **R22.** Hidden-code items: each hunk under `<crate>/src/` whose added lines, with comments and whitespace removed, contain `mutants::skip`, `macro_rules!`, or a macro invocation not in the list `println! eprintln! print! eprint! format! write! writeln! vec! panic! matches! unreachable! todo! assert! assert_eq! assert_ne! debug_assert! debug_assert_eq! debug_assert_ne!`, keyed by (crate, file, normalized added text).
- **R23.** Gate items, target `gate`: each changed file among `.github/workflows/mutation-pr.yml`, `.github/workflows/mutation-gate-items.yml`, `scripts/mutation-*.sh`, `scripts/mutation_*.py`, `scripts/cosmic_ray_*.py`, `.github/mutation-gate-allowed-signers`, its test, and `tests/fixtures/mutation_weakening/`, keyed by (path, new blob hash); and each `Makefile` template or rendered `Makefile` whose `mutants*` targets or `MUTANTS_*` variables change, keyed by (path, hash of that text); a `mutation-pr.yml` change that only replaces the 40-hex SHA in a `uses: actions/<name>@<sha>` line is not an item.
- **R24.** An item is cleared by a commit in the PR range that is an ancestor of head, carries `Mutation-Gate-Reviewed: <target>: <reason>` for the item's target (reason at least 10 characters), is accepted by `git verify-commit` with `gpg.format=ssh` and `gpg.ssh.allowedSignersFile` set to the base branch's `.github/mutation-gate-allowed-signers`, and whose tree contains the item's key; any uncleared item makes `mutation-gate-items` red, naming the item, its target and the remedy command; a trailer on an unsigned or unaccepted commit is reported as `trailer ignored: <commit>: <reason>`.
- **R25.** A commit that clears target `<dir>` under R24 also clears that dir's R12 and R15 reds in `mutation-pr` when `<dir>/<module>.py` and `<dir>/test_<module>.py` are unchanged between it and head, and the summary then says `cleared by Mutation-Gate-Reviewed <commit>`.
- **R26.** `.github/mutation-gate-allowed-signers` lists only `sk-ssh-ed25519` keys, none with `no-touch-required`, and a test fails on any other key type or that option.
- **R27.** `mutation-pr.yml` sets `concurrency: { group: mutation-pr-${{ github.event.pull_request.number }}, cancel-in-progress: true }`.
- **R28.** CI runs the Python steps through `make -C <dir> mutants-weakening BASE=<sha> MUTANT_SHARD=<k>/<n>`, a target every Python `Makefile` gains from `scripts/crate_templates/python/Makefile`, which also accepts `JOB=<job id>` and writes nothing in the tracked tree; `scripts/mutation-pr-run.sh --whole [--shard <k>/<n> --expect <count>] <crate-dir>` runs one crate's whole set and exits non-zero on the R4 red conditions.
- **R29.** `tests/scripts/mutation_pr_detect.bats` covers R1 (a `tests/` fixture, a non-`.rs` `src/` file, a `.cargo/mutants.toml` change, `build.rs` and a `Cargo.toml` `[[test]]` change each select the crate; a `[dependencies]` version change alone does not) and R5 (added-only, deleted-only and file-deletion changes to `test_<module>.py`, and changes to `cosmic-ray.toml` or `mutants-equivalent.toml`, each select the dir; a change to `<module>.py` alone does not).
- **R30.** A test on a copy of `sq/` requires: dropping an assertion that alone kills a known mutant reports it under `weakened: 1`; only adding a test reports `weakened: 0`; a cosmetic edit to every `@given` body reports `weakened: 0`; an obsolete first assertion followed by a deleted later assertion reports the later assertion's mutant; a `subTest` failure under a mutant counts as a kill; a message containing a set repr or an address is stable across recordings; an import-breaking rename, a per-test `setUp` error, and a base test sleeping past the timeout are each red with `base suite unjudgeable` and leave no process running; an untested line added to `sq.py` with a test-file change is red under R16; a replay forced to `no-test` is red with `replay failed`; a `sitecustomize.py` placed in the sandbox does not replace the generated one; a broken generated profile is red with `hypothesis profile not active`; and the tracked `sq/` files are byte-identical after every case.
- **R31.** Tests cover R20-R26: a new equivalents entry, a `variant` change and a duplicated entry are items; pure line shifts of `exclude_re` and of an equivalents entry are not; an equivalents entry whose line was legitimately edited does not crash the item computation; a retargeted pattern onto an equal operator elsewhere in the function is an item; an `additional_cargo_test_args` change and a `timeout` change are items keyed by their new value; `#[mutants::skip]` in spaced, split and commented spellings, `macro_rules!`, a local macro wrapping an expression and `dbg!(...)` are items; a changed `mutation-pr-detect.sh`, allowed-signers file, or `mutants` recipe is a `gate` item and a non-recipe `Makefile` change and an `actions/checkout` digest bump are not; each item clears only with a verified trailer commit for its target whose tree holds its key, not with an unsigned or non-`sk` signature, a trailer for another target, a 9-character reason, or a commit whose tree holds an earlier value.
- **R32.** Root `CLAUDE.md` (Mutation testing sections) and an ADR describe the whole-crate PR rule, the Python weakening check, the items job, the signed trailer and the bootstrap order, with repro commands; `docs/superpowers/README.md` removes the Backlog row "PR mutation gates miss test-only weakening (Rust and Python)"; root `CLAUDE.md` stays at or under 30,000 bytes.

- **V1.** Positive control before the PR is marked ready: a throwaway draft PR that deletes one assertion from a crate's `#[cfg(test)]` module, leaving a mutant uncaught, shows `mutation-pr` red naming that mutant; closed and its branch deleted.
- **V2.** Positive control: a throwaway draft PR that weakens one assertion in `sq/test_sq.py` shows `mutation-pr` red with `weakened: 1` naming the mutant; closed and deleted afterwards.
- **V3.** Negative control: a throwaway draft PR that only adds a test to `sq/test_sq.py` shows `mutation-pr` green.
- **V4.** After the items job is on master and required: a throwaway draft PR that adds one `[[equivalent]]` entry to `sq/mutants-equivalent.toml` shows `mutation-gate-items` red naming it, green after the operator pushes a FIDO-signed `Mutation-Gate-Reviewed: sq: <reason>` commit, and red again after a further edit of that entry; an unsigned commit with the same line stays red; a throwaway PR that deletes the items step from `mutation-pr.yml` is still red in `mutation-gate-items`.
- **V5.** Timing: throwaway draft PRs that add one test to `collatz/test_collatz.py`, `descartes/test_descartes.py` and `pi/test_pi.py` record every shard's wall time and concurrent jobs; a shard past about 45 minutes changes the R6 constants before merge.
- **V6.** False-positive replay before merge: run the weakening path locally on the 32 real commits since 2026-09-26 that changed a module and its test file and have a base file and no hang; print per commit the head survivors replayed, the base-arm kills, the kills that come only from a changed failure signature, and every `weakened` result, and inspect each `weakened` result.
- **V7.** Signing setup before merge: the operator's `sk-ssh-ed25519` public key is in `.github/mutation-gate-allowed-signers`, the key is forwarded to a session on `claude`, a trailer commit made there prompts for a touch on the physical key, and `git verify-commit` accepts it against that file.
- **V8.** Item frequency: run `scripts/mutation-gate-items.sh` over the last 100 merged PRs and report how many would need a signature, by item kind, to the operator before merge.
- **V9.** Record the wall time of the PR's own `mutation-pr` and `mutation-gate-items` runs and of V1-V5; a zeta-rs whole-crate run is measured or projected, and any Rust shard past about 50 minutes lowers B per ADR-0046.

- **N1.** The monthly `mutation-testing.yml` and `mutation-testing-python.yml` sweeps do not change.
- **N2.** No committed survivor, missed or baseline list is added; the only committed fixtures are the R18 canary pairs.
- **N3.** The local pre-push hook runs no mutants.
- **N4.** `mutation-gate-items` never checks out, builds, imports or runs a file from the PR head, and has no secrets.
- **N5.** Nothing in the gates or the local targets writes to a tracked file in the working tree.
- **N6.** The Python changed-line gate's behaviour for dirs not in `py_test_dirs` does not change.
- **N7.** No agent, script or workflow signs a `Mutation-Gate-Reviewed:` commit; only the operator does, touching the key only for a signing they started.

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

### Round 4 (all four reviews, reviewed at `1b53e6b`, the round-3 revision)

#### Goal-Fit

Finding: Load-bearing: the gate-items class is checked by the code it guards. `mutation-pr.yml` runs on `pull_request`, so the PR head's workflow and scripts run, and branch protection requires only a check named `mutation-pr` (contexts `secret-scan`, `mutation-pr`); a PR can drop the item step or replace the job and go green without a signature. The implementing PR also cannot clear itself (master has no allowed-signers file). Cost: 38 of 108 PRs since 2026-09-26 touched a gate-shaping or exemption file, including Renovate digest bumps to `mutation-pr.yml` and every new-crate PR. Not converging: each round's load-bearing defect came from the previous round's fix; suggested a three-way split (Rust now, Python with exemptions simply red, clearance in its own spec).
Assumption: The operator can make a touch-required `sk-ssh-ed25519` signature where commits are made; `claude` holds only `id_ed25519` and `gpg.format` is unset.
Disposition: Addressed (operator, 2026-11-26: "Round 5 on full design"; "Yes, add required check"; "Forward key to claude"): a `pull_request_target` items job running master code only, as a second required check; bootstrap order stated; narrowed gate files; signing setup is a verification.

#### Ergonomics

Finding: R22 fires on 28 of the last 100 PRs, mostly rendered `Makefile`s changed for unrelated reasons; with exemption files, 35 of 100. 8 Renovate PRs since 2026-08-24 bumped action digests in `mutation-pr.yml` and would no longer auto-merge. No signing flow exists on `claude` (forwarded agent holds `ssh-rsa` and two `ssh-ed25519` keys, no `sk-`; `gpg.format` unset; recent commits unsigned); a forwarded FIDO key can also be used by an agent's own `git commit -S`, so a touch proves presence, not content. Bootstrap and the ungated allowed-signers file. "Item reds arrive early" depends on an unspecified job layout. At the new floor, descartes is 40 shards and a uniform refactor about 140-170 units, saturating the shared pool for 1.5-2 h.
Assumption: A touch-required sk key can sign where the operator actually works.
Disposition: Addressed (operator, 2026-11-26: "Round 5 on full design"; "Forward key to claude"): gate items keyed on the mutation recipe text and content hashes, `actions/` digest-only `uses:` changes exempt, a separate items job, signing setup verified before merge, cost re-projected in a V.

#### Risk

Finding: F1 (load-bearing) the same self-verification. F2 the trust root `.github/mutation-gate-allowed-signers` is not a gate item, and the key-type rule cannot tell hardware from a software `SSH_SK_PROVIDER` (sk-dummy, unprobed). F3 config and gate items keyed without value: one signed change clears later edits of the same key. F4 the Rust content key is mostly an operator token (11 of 12 excluded mutants are `BinaryOperator`; descartes-rs has 327 mutants sharing keys): retargets pass, insertions raise false items; pure shifts measured 0 items on 02390d7 and 6fa6ae8. F5 two recordings can agree by chance: `repr` of a set changed order in 7 of 8 processes, and object addresses differ every run. F6 bootstrap.
Assumption: Messages of base tests failing on the head do not change under backlog survivors (pi 368, e 396); settle by counting signature-only kills on real commits.
Disposition: Addressed (operator, 2026-11-26: "Round 5 on full design"): allowed-signers and its test gated, enrolment stated as the trust root, value- and hash-keyed items, line-text Rust keys, `PYTHONHASHSEED=0` and address stripping, V6 counts signature-only kills.

#### Adversarial Spec Review

Finding: F1 (load-bearing) masking: a base test stops at its first failing assertion, so later assertions never run under head or any mutant and their kills vanish (probe: obsolete `label(3)` assertion hid `sq(3) == 9`); per-test `setUp` errors mask whole classes; this is the ordinary refactor PR. F2 base arm disadvantaged: `Path(__file__).parent / "<module>.py"` subprocess tests (amicable, collatz) break from `.base/`; the runner script's `sys.path[0]` lacks the sandbox; cwd-first `PYTHONPATH` lets a PR-supplied `sitecustomize.py` preempt the generated one. F3 `subTest` (about 40 in descartes), skip and expected-failure outcomes are outside the signature model. F4 `cosmic_ray_prune.py` exits 1 on any entry matching no spec (probe on `e/`: `matches no spec`, rc=1), so any legitimate edit of an entry's line breaks the item computation. F5 config items keyed without value let a signed timeout change clear a later `timeout = 1.0`; which side's toml sets the replay timeout is undefined. F6 trust root ungated; an old signed gate commit can be merged back to clear later changes; "latest" is undefined in a non-linear range. F7 wrapping one expression in a local macro or `dbg!()` removes its mutants while the function keeps others, so function-level disappearance misses it; `build.rs` is not a trigger. F8 hash-seed false kills.
Assumption: Masking loses few sole kills on real commits; settle on the 7 high-failure commits by isolating the assertions after each recorded failure.
Disposition: Addressed (operator, 2026-11-26: "Round 5 on full design"): an assertion-continuing base runner (probe: it recorded the masked `6 != 9` and a `subTest` failure `8 != 16` that plain unittest never reached), per-test `setUp` errors unjudgeable, base file at the sandbox root after the head session with the runner inserting the sandbox on `sys.path` after start-up, outcomes extended to skip and expected-failure, a tolerant prune, value keys, ancestor-based clearance, an added-macro scan, `build.rs` trigger, `PYTHONHASHSEED=0`.
