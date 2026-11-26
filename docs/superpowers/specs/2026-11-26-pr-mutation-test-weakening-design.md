# PR mutation gates see test weakening

- **Date:** 2026-11-26 (revised after Multi-Lens Review round 1)
- **Backlog row closed:** "PR mutation gates miss test-only weakening (Rust and Python)" (P2)
- **Related:** ADR-0042 (Rust sweep holds zero missed), ADR-0044 (per-PR Python gate), ADR-0046
  (shard the Rust runs), `specs/2026-11-05-worldclass-slice5-rust-pr-mutation-ratchet-design.md`,
  `specs/2026-11-07-worldclass-slice8-python-pr-mutation-gate-design.md` ("Known gap, not closed here")

## Summary

Both per-PR mutation gates judge only mutants on lines a PR changes. A PR that deletes or weakens
tests changes no production line, so it is never judged, and the surviving mutants it creates sit
on unchanged lines. A PR can also exempt the mutant it exposes. This spec closes both holes:

- **Rust:** any change under a crate's `src/`, `tests/` or `.cargo/` runs every mutant in that crate,
  held to the sweep's rule (0 missed, timeouts green). It replaces the changed-line run for those crates.
- **Python:** a change to `test_<module>.py` mutates the whole head module and runs the head tests on
  every mutant; each shard then runs the base tests on its own head survivors in a throwaway copy. A
  mutant the base tests kill and the head tests do not is a weakening, and the gate is red. A base
  suite that cannot be judged (import or collection failure, hang, or more than 20% of its tests
  failing on the unmutated head) is red, never green.
- **Exemptions:** a new Python equivalent, a new or changed Rust exclusion, or an added
  `#[mutants::skip]` is red unless the operator adds a `Mutation-Gate-Reviewed:` trailer.

## Why

Measured 2026-11-26 on master `0bc607f`:

- `scripts/mutation-pr-detect.sh` puts a Python dir in `py_src_dirs` only when
  `git diff --numstat` shows added lines in `<dir>/<module>.py` (lines 15-18, 37). A PR touching only
  `test_<module>.py` runs no Python mutant.
- A Rust crate is selected only when a changed path matches `<crate>/src/**/*.rs` (line 66), and its
  mutants are filtered by `--in-diff`. A hunk inside a `#[test]` yields `INFO No mutants to filter`,
  exit 0 (orchestrator probe recorded in the slice 5 spec, 2026-11-05). A change under `<crate>/tests/`
  (13 crates have one) selects no crate.
- The 90% coverage floors (`--cov-fail-under=90` in the Python template, `tarpaulin --fail-under 90`
  in every `*-rs.yml`) catch a large test deletion but not a weakened assertion: coverage is unchanged
  when `assertEqual(x, 5)` becomes `assertIsNotNone(x)`.
- The Rust monthly sweep holds 0 missed (ADR-0042; run 45479226540 green), so a Rust weakening is
  reported within a month, after merge. The Python sweep carries about 1,250 open survivors (issue
  #184: pi 712, e 736), so a new Python survivor is indistinguishable from the backlog and is never
  reported at all.
- The exemption files are looser than the gate. Python prunes `mutants-equivalent.toml` entries before
  the session runs (template `Makefile` lines 101-103), and `tests/test_mutants_equivalent.py` checks
  only stale or ambiguous entries. Rust honours `.cargo/mutants.toml` (`exclude_re`, and zeta's
  `additional_cargo_test_args` skips the `e2e_` tests) and `#[mutants::skip]`;
  `tests/test_mutants_exclusions.py` checks only that each regex still matches a mutant.

Agents write most of the tests here, and weakening a test to make a gate pass is a known agent failure
(it is on the executor FORBIDDEN list). Nothing mechanical catches it before merge today, and
auto-merge lands a green PR without review.

## Facts this design rests on (measured 2026-11-26)

- **Rust whole-crate cost.** The monthly sweep run 45479226540 (2026-11-24, all 13 crates, 2,221
  mutants, 37 shards at B = 75) took 9 minutes of wall time; its longest shard was 7.4 min (descartes-rs,
  ADR-0046 V1). zeta-rs has 748 whole-crate mutants at about 29.6 s each on CI, so its 10 shards run about
  37 min each (ADR-0046 V2 measured a 68-mutant zeta shard at 33.8 min); `mutation-rs` has
  `timeout-minutes: 60`. Over the last 100 merged PRs the Rust trigger fires on the same 17 PRs as
  today's `src/*.rs` trigger; a one-line zeta edit goes from about 1 min to about 37 min of wall time.
- **Planner.** `scripts/mutation-rs-plan.sh --whole <crate-dir>...` already plans every mutant of the
  named crates and emits a fault unit `{"slug":"<name>-plan",...,"fault":"<cause>"}` instead of failing.
- **Python whole-module size.** `cosmic-ray init` on HEAD gives 1,828 mutants for pi; issue #184's sweep
  counted 1,859 jobs (pi) and 1,648 (e). Run 42157892557's pi shards took 15.3-20.2 min for about 183
  mutants each, about 5.9 s per mutant. (The earlier "613" was slice 8's diff-pruned count.)
- **Python trigger rate.** Over the last 100 merged PRs, `test_<module>.py` changed in 18, and 16 of
  those also changed `<module>.py`; pi and e are the most touched (7 PRs each). Renovate and docs-only
  PRs touch neither.
- **Python per-mutant replay.** `cosmic-ray mutate-and-test MODULE_PATH OPERATOR OCCURRENCE TEST_COMMAND`
  (cosmic-ray 8.7.0, the pinned version) mutates one occurrence and runs the given command: on a copy of
  `sq/`, `core/NumberReplacer` occurrence 0 was `killed` under `python3 -m unittest -q test_sq` and
  `survived` under `python3 -c pass`, and `sq.py` was restored afterwards. It passes `timeout=None`
  (`cli.py:298-311`), and wrapping it in `timeout` leaves the module mutated (probe: rc=124, `sq.py` left
  as `limit = 11**max_digits`), so the replay must run in a throwaway copy with its own limit. cosmic-ray
  maps a non-zero test exit, including a timeout, to `killed` (`testing.py:74-76`).
- **Obsolete base tests in real PRs.** For the 36 commits since 2026-09-26 that changed both
  `<dir>/<module>.py` and `test_<module>.py`, the parent's test file was run against the commit's module
  (scratch copy, pinned gmpy2/mpmath/hypothesis/pytest):
  - 2 had no base test file (new projects);
  - 16 had no base test failing;
  - 9 had failures or errors in at most 5% of base tests;
  - 7, all from one commit (68a2f8a, the uniform Python CLI refactor, math#171), had 13-65%;
  - 2 (amicable and descartes at 949fd22, a re-prompt change) hung past 900 s;
  - 0 collapsed to a single `unittest.loader._FailedTest`.
    A synthetic probe on a copy of `sq/` (renaming one imported name) did collapse all 53 base tests into
    one `_FailedTest`.
- **Hypothesis.** 8 of 10 Python test files import hypothesis and nothing derandomizes it. A
  `sitecustomize.py` on `PYTHONPATH` that registers and loads a profile with `derandomize=True,
database=None` gave the same examples on two runs (`[0, 2179, 4761, -107, 2925]`), with no test edit.
- **Exemption churn.** 10 commits since 2026-09-26 touched a `.cargo/mutants.toml` or a
  `mutants-equivalent.toml`. Rust `exclude_re` patterns embed line and column numbers and must be
  updated when code shifts; Python equivalents are keyed by operator, function, line text, column and
  the line above.
- **Python test layout.** Each of the 10 Python sub-projects has exactly one test file,
  `<dir>/test_<module>.py`, and no `conftest.py`; every `cosmic-ray.toml` sets `timeout = 60.0` and a
  `test-command` naming its own test module.

## Design

### Rust: whole crate on any crate change

1. `mutation-pr-detect.sh` selects a crate dir for `rs_dirs` when any changed path is under
   `<crate>/src/`, `<crate>/tests/` or `<crate>/.cargo/` (any file type).
2. `mutation-rs-plan` plans the selected crates with `mutation-rs-plan.sh --whole`, not the `--in-diff`
   mode. A fault unit is a red unit in `mutation-pr`. The 256-unit plan limit stays.
3. Each shard is classified with the sweep's rule: red on any missed mutant, on
   `caught + missed + timeout == 0`, on a missing `outcomes.json` or `mutants.out/exit-code`, or on a
   failed baseline; timeouts are green beside a catch (`scripts/mutation-classify.sh`, ADR-0042).
4. The amicable-rs canary is unchanged.
5. Accepted by the operator: drift from a newer rustc or cargo-mutants surfaces on the next PR that
   touches the crate, not only in the monthly sweep.

### Python: same code, two test suites

Triggered for a dir when `test_<module>.py` changes (any added or deleted line, or the file's
deletion), in addition to the existing module-change trigger. Both suites run against the **head**
module, so mutant identities match:

1. **Shards.** The whole head module is planned with `n = max(1, ceil(K/60))` shards (no 10-shard cap),
   so a pi shard holds about 31 mutants: about 3 min of head runs plus about 1.5 min of replay at the
   #184 survival rate. The whole PR plan is red above 256 units, as the Rust planner rule.
2. **Derandomized hypothesis.** Every head run, base run and replay sets `PYTHONPATH` to a directory
   holding a generated `sitecustomize.py` that registers and loads the profile
   `settings.register_profile("mutation-gate", derandomize=True, database=None)`.
3. **Head run.** Each shard mutates its slice of the head module and runs the head tests on every
   mutant (the existing `MUTANTS_BODY` path, which works in `.mutants-tmp`). The existing changed-line
   rule still applies: any survivor on a line the PR added to `<module>.py` is red.
4. **Base suite.** The shard writes `git show <merge-base>:<dir>/test_<module>.py` as
   `test_<module>_base.py` inside a throwaway copy of the dir (never the tracked tree). If the merge
   base has no such file, the comparison is skipped and says so. If head has no `test_<module>.py` and
   base has one, the dir is red with `test_<module>.py deleted`.
5. **Judgeable base suite.** The shard runs the base suite once against the unmutated head module, with a
   300-second limit. It is unjudgeable, and the dir red, when the run hits the limit, when any result is
   a `unittest.loader._FailedTest` (import or collection failure) or a class- or module-level setup
   error, or when more than 20% of the base tests fail or error. Otherwise every failing or erroring
   base test is excluded from step 6, and its id is printed under `obsolete base tests:` in the verdict,
   red or green.
6. **Replay.** For each of the shard's own head survivors, the shard runs
   `cosmic-ray mutate-and-test <module>.py <operator> <occurrence> "<base command>"` in a fresh
   throwaway copy, under `timeout 60` (the `cosmic-ray.toml` limit), with the base suite restricted to
   the tests not excluded in step 5. A timeout exit counts as `killed`.
7. **Verdict.** A mutant with base outcome `killed` and head outcome `survived` is a weakening: the dir
   is red and the summary prints `weakened: <count> mutants killed by base tests survive head tests`,
   then for each mutant its operator, occurrence, diff and the one-mutant repro command.

### Exemptions need the operator

For every dir or crate the PR touches, the gate compares exemptions at head with the merge base:

- **Python:** an `[[equivalent]]` entry in `<dir>/mutants-equivalent.toml` whose
  (`operator`, `function`, `line`, `col`, `above`) tuple is not in the base file.
- **Rust exclusions:** an `exclude_re` pattern in `<crate>/.cargo/mutants.toml` that is new once each
  `:<line>:<col>:` is normalized to `:N:N:`, or any change to another key of that file.
- **Rust skips:** a line added under `<crate>/src/` that contains `mutants::skip`.

Each is red, naming the entry, unless a commit in the PR's range carries a trailer
`Mutation-Gate-Reviewed: <reason>` of at least 10 characters. The same trailer also clears an
unjudgeable base suite (Python step 5). Agents never write this trailer; the operator does. This is
enforced by instruction, as `Plugin-Reviewed:` is, not by a mechanism.

### Known limits

- A weakening on a mutant that another head test still kills is invisible to any mutation-based gate.
- A base test that legitimately fails on the new behaviour is excluded, so a PR could pair a behaviour
  change with weakening that same test. The exclusion list is printed in every verdict and capped at
  20% of the base suite.

### Workflow and local repro

- `mutation-pr.yml` gains `concurrency: { group: mutation-pr-${{ github.event.pull_request.number }},
cancel-in-progress: true }`, so a superseded push stops its shards.
- CI runs the Python steps through one make target, so local and CI share one code path:
  `make -C <dir> mutants-weakening BASE=<ref> [MUTANT_SHARD=<k>/<n>]`.
- Rust: `scripts/mutation-pr-run.sh --whole [--shard <k>/<n> --expect <count>] <crate>`.

## Requirements

- **R1.** `scripts/mutation-pr-detect.sh` prints a crate dir in `rs_dirs` when a changed path starts with `<crate>/src/`, `<crate>/tests/` or `<crate>/.cargo/`, whatever the file extension.
- **R2.** In `mutation-pr.yml`, `mutation-rs-plan` plans every selected crate with `scripts/mutation-rs-plan.sh --whole <crate-dir>...` and never passes `--in-diff` for a selected crate.
- **R3.** A `--whole` fault unit (`"fault": "<cause>"`) makes `mutation-pr` red and its summary names the crate and the cause.
- **R4.** A Rust PR shard is red on any missed mutant, on `caught + missed + timeout == 0`, on a missing `mutants.out/outcomes.json` or `mutants.out/exit-code`, or on a failed baseline, and green on timeouts beside at least one caught mutant, using `scripts/mutation-classify.sh`.
- **R5.** `mutation-pr-detect.sh` prints a Python dir in a new output `py_test_dirs=<sorted dirs>` when `git diff --numstat --no-renames` shows any added or deleted line in `<dir>/test_<module>.py` (module = dir with `-` as `_`), including a deletion of the file.
- **R6.** For each dir in `py_test_dirs`, the gate mutates the whole head `<dir>/<module>.py`, runs the head `test_<module>.py` on every mutant, and plans `n = max(1, ceil(K/60))` shards with no 10-shard cap; a PR plan of more than 256 units in total is red.
- **R7.** Every head run, base run and replay for a dir in `py_test_dirs` runs with `PYTHONPATH` holding a generated `sitecustomize.py` that calls `settings.register_profile("mutation-gate", derandomize=True, database=None)` and `settings.load_profile("mutation-gate")`.
- **R8.** Each shard writes the merge base's `<dir>/test_<module>.py` as `test_<module>_base.py` only inside a throwaway copy of the dir, never in the tracked tree.
- **R9.** Each shard runs the base suite once against the unmutated head module with a 300-second limit, and the dir is red with `base suite unjudgeable: <cause>` when the run hits the limit, when any result is `unittest.loader._FailedTest`, when a class- or module-level setup errors, or when more than 20% of the base tests fail or error.
- **R10.** When R9 does not make the dir red, every base test that failed or errored on the unmutated head is excluded from replay, and the verdict lists their ids under `obsolete base tests:` whether the dir ends red or green.
- **R11.** For each of its own head survivors, a shard runs `cosmic-ray mutate-and-test <module>.py <operator> <occurrence> "<base command>"` in a fresh throwaway copy under a 60-second `timeout`, with the base suite restricted to the tests not excluded by R10, and counts a timeout exit as `killed`.
- **R12.** A dir in `py_test_dirs` is red when any mutant's base outcome is `killed` and head outcome is `survived`, and its summary reads `weakened: <count> mutants killed by base tests survive head tests`, then each mutant's operator, occurrence, diff and the line `repro: cosmic-ray mutate-and-test <module>.py <operator> <occurrence> "<base command>"`.
- **R13.** A dir in `py_test_dirs` whose `test_<module>.py` exists at the merge base and not at head is red with `test_<module>.py deleted`; one whose merge base has no `test_<module>.py` skips R8-R12 and prints `no base test file: weakening check skipped`.
- **R14.** A dir in `py_test_dirs` keeps the existing rule that any head survivor on a line the PR added to `<module>.py` is red.
- **R15.** The gate is red, naming the entry, for each `[[equivalent]]` entry in a touched dir's `mutants-equivalent.toml` whose (`operator`, `function`, `line`, `col`, `above`) tuple is absent at the merge base, unless a commit in the PR range has a `Mutation-Gate-Reviewed: <reason>` trailer of at least 10 characters.
- **R16.** The gate is red, naming the entry, for each `exclude_re` pattern in a touched crate's `.cargo/mutants.toml` that is absent at the merge base after every `:<digits>:<digits>:` is replaced by `:N:N:`, for any change to another key of that file, and for each line added under `<crate>/src/` containing `mutants::skip`, unless a commit in the PR range has a `Mutation-Gate-Reviewed: <reason>` trailer of at least 10 characters.
- **R17.** A `Mutation-Gate-Reviewed: <reason>` trailer of at least 10 characters on a commit in the PR range also clears a red from R9, and the summary then says `cleared by Mutation-Gate-Reviewed`.
- **R18.** `mutation-pr.yml` sets `concurrency: { group: mutation-pr-${{ github.event.pull_request.number }}, cancel-in-progress: true }`.
- **R19.** CI runs the Python weakening steps by calling `make -C <dir> mutants-weakening BASE=<sha> MUTANT_SHARD=<k>/<n>`, a target every Python `Makefile` gains from `scripts/crate_templates/python/Makefile`, which prints the same verdict lines locally and in CI and writes nothing in the tracked tree.
- **R20.** `scripts/mutation-pr-run.sh --whole [--shard <k>/<n> --expect <count>] <crate-dir>` runs one crate's whole mutant set locally and exits non-zero on the R4 red conditions.
- **R21.** `tests/scripts/mutation_pr_detect.bats` covers R1 (a `tests/` fixture, a non-`.rs` `src/` file and a `.cargo/mutants.toml` change each select the crate) and R5 (an added-only, a deleted-only and a file-deletion change to `test_<module>.py` each put the dir in `py_test_dirs`; a change to `<module>.py` alone does not).
- **R22.** A test on a copy of `sq/` requires: head dropping one assertion that kills a known mutant reports that exact mutant under `weakened: 1`; head only adding a test reports `weakened: 0`; one base test failing on the unmutated head is listed under `obsolete base tests:` and not counted; renaming an imported name so the base suite collapses to `_FailedTest` is red with `base suite unjudgeable`; a base test that sleeps past the limit is red with `base suite unjudgeable`; and after every case the tracked `sq/sq.py` and `sq/test_sq.py` are byte-identical to before.
- **R23.** Tests cover R15 and R16: a new equivalents tuple is red, an unchanged tuple is green, an `exclude_re` change that only shifts `:<line>:<col>:` is green, a new pattern is red, a changed `additional_cargo_test_args` is red, an added `mutants::skip` is red, and each red turns green with a valid trailer and stays red with a 9-character one.
- **R24.** Root `CLAUDE.md` (Mutation testing sections) and an ADR describe the whole-crate PR rule, the Python weakening check, the exemption rule and the `Mutation-Gate-Reviewed:` trailer with their repro commands; `docs/superpowers/README.md` removes the Backlog row "PR mutation gates miss test-only weakening (Rust and Python)"; root `CLAUDE.md` stays at or under 30,000 bytes.

- **V1.** Positive control before the PR is marked ready: a throwaway draft PR built on the branch that deletes one assertion from a crate's `#[cfg(test)]` module, where the deletion leaves a mutant uncaught, shows `mutation-pr` red naming that mutant; closed and its branch deleted.
- **V2.** Positive control: a throwaway draft PR that weakens one assertion in `sq/test_sq.py` shows `mutation-pr` red with `weakened: 1` naming the mutant; closed and deleted afterwards.
- **V3.** Negative control: a throwaway draft PR that only adds a test to `sq/test_sq.py` shows `mutation-pr` green.
- **V4.** Positive control: a throwaway draft PR that adds one `[[equivalent]]` entry to `sq/mutants-equivalent.toml` shows `mutation-pr` red naming it; closed and deleted afterwards.
- **V5.** Timing: a throwaway draft PR that adds one test to `pi/test_pi.py` records every pi shard's wall time against `mutation-py`'s `timeout-minutes`; a shard past about 20 minutes lowers the Python whole-module batch below 60 before merge.
- **V6.** Record the wall time of the PR's own `mutation-pr` run and of V1-V5; a zeta-rs whole-crate run is measured or projected from shard times, and any Rust shard past about 50 minutes lowers B per ADR-0046.

- **N1.** The monthly `mutation-testing.yml` and `mutation-testing-python.yml` sweeps do not change.
- **N2.** No committed survivor, missed or baseline list is added for any crate or Python dir.
- **N3.** The local pre-push hook runs no mutants.
- **N4.** The required check stays `mutation-pr`; no new required check is added to branch protection.
- **N5.** Nothing in the gate or the local target writes to a tracked file in the working tree; the base test file and every mutation exist only in throwaway copies.
- **N6.** The Python changed-line gate's behaviour for dirs not in `py_test_dirs` does not change.
- **N7.** No agent, script or workflow writes a `Mutation-Gate-Reviewed:` trailer; only the operator does.

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
