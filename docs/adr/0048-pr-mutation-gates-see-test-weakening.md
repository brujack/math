# ADR-0048: PR mutation gates see test weakening

**Date:** 2026-11-26
**Status:** Accepted

## Context

The per-PR mutation gates judged only mutants on lines the PR changed (ADR-0044 for Python, ADR-0046 for Rust). A PR that deletes or weakens tests, or hides code from the mutator, leaves survivors on unchanged lines, and no changed-line gate sees them; only the monthly sweeps reported it. A goal-seeking agent has three documented levers: weaken a test, widen an equivalence or exclusion list, and edit the gate itself.

Spec: `docs/superpowers/specs/2026-11-26-pr-mutation-test-weakening-design.md`. Plan: `docs/superpowers/plans/2026-11-26-pr-mutation-test-weakening.md`.

## Decision

1. **Rust: whole crate on any crate change.** `mutation-pr-detect.sh` selects a crate when a changed path is under `<crate>/src/`, `<crate>/tests/` or `<crate>/.cargo/`, is `<crate>/build.rs`, or is `<crate>/Cargo.toml` with a changed line other than the `[package]` `version` line and outside the dependency tables. `mutation-rs-plan` plans selected crates with `--whole` (never `--in-diff`), each shard classifies with the sweep's rule through `scripts/mutation-classify.sh`, and a fault unit is red. The amicable-rs canary is unchanged.
2. **Python: the same code under two test suites.** A dir enters the check when its `test_<module>.py`, `cosmic-ray.toml` or `mutants-equivalent.toml` changes, in addition to the module-change trigger. Both arms run in the `MUTANTS_BODY` sandbox with `PYTHONHASHSEED=0`, `PYTHONDONTWRITEBYTECODE=1` and a generated `PYTHONPATH`.
   - **Planning.** The head suite is timed once; shards per dir are `min(40, max(10, ceil(K * s / 600)))`, and `mutation-py` has `timeout-minutes: 60`. A dir both module-changed and test-changed is planned as weakening shards only, but the planner still runs the diff-mode prune over the real PR diff for it: the whole-module diff adds every `mutants-equivalent.toml` entry, so only the real diff can show an entry left unconfirmed on a changed line, and any red line from that plan (a refusal, or `lines 0`) is the dir's red plan line with no weakening row, which the `Python verdict` step reports and fails on.
   - **Head arm.** The head session runs over the whole-module mutant set. Under R16, any survivor on a line the PR added to `<module>.py` is red. R16 applies to PR-added lines inside the target.
   - **Base arm.** The merge base's test file is written beside the module as `test_<module>_base.py` only after the head session. `scripts/mutation_base_runner.py` rewrites `self.assert*` statements, `assert` statements and `with self.assert*` blocks so a failure is recorded and execution continues, and produces a per-test signature (final outcome, failure sites, error type and line; no messages). An obsolete early assertion therefore cannot mask a later one.
   - **Judge and replay.** The shard records signatures twice on the unmutated head; a dir is unjudgeable and red when the recordings differ, a result is a `_FailedTest`, a `setUp` errors or a run times out. For each head survivor it replays the stored `MutationSpec` through `cosmic_ray.mutating.mutate_and_test` with the base runner. A mutant killed by the base arm and surviving the head arm is a weakening. A timeout kill is re-run at twice the timeout. Each shard is red with `shard incomplete` unless it ran its planned slice and replayed every survivor.
   - **Hypothesis.** A generated `sitecustomize.py` keys `hypothesis.core.function_digest` on the test's `__qualname__` and loads the `mutation-gate` profile (`derandomize=True`, `database=None`, `deadline=None`, all health checks suppressed). A preflight must draw identical examples for two same-name `@given` tests or the dir is red with `hypothesis profile not active`.
   - **Interface (amended R8).** A dir whose merge base has `test_<module>.py` is red with `base suite unjudgeable: test-command must be python3 -m unittest test_<module>` unless the head and merge-base `cosmic-ray.toml` `test-command` both equal that. A dir with no base test file skips the weakening check. A deleted `test_<module>.py` is red.
   - **Verdict (amended R15).** The summary prints `weakened: <count> mutants killed by base tests survive head tests`, then each mutant's operator, occurrence, diff and `repro: make -C <dir> mutants-weakening BASE=<sha> JOB=<operator>@<occurrence>`. Cosmic-ray job ids are random per `cosmic-ray init`, so the operator and module-wide occurrence select the mutant.
   - **Affirmative verdict file.** The judge writes a verdict file that the gate step reads. The absence of a verdict is red, never green.
   - **Canary.** `py_canary` runs the path on `tests/fixtures/mutation_weakening/` and requires `weakened: 1` in each case.
3. **`mutation-gate-items`, a new required check on `pull_request_target`.** `.github/workflows/mutation-gate-items.yml` has `permissions: contents: read`, no secrets and no `paths:` filter. It runs the base branch's `scripts/mutation-gate-items.sh` against the PR head's objects. It lists what the changed-line gates cannot judge, and is red while any item exists. Invocation rules, so no PR content executes:
   - PR files are written to a scratch tree only with `git show <sha>:<path>`, never `git archive` or `git checkout`, which honour PR `.gitattributes` and filters.
   - Every tool runs with its working directory outside the scratch tree.
   - No cargo config or toolchain file is materialised, so a PR `.cargo/config.toml` alias, `rust-toolchain.toml` or `rustc-wrapper` cannot run.
   - `RUSTUP_TOOLCHAIN` is the pinned toolchain; `CARGO_HOME` is a fresh empty directory; `cargo metadata` is never called without `--no-deps`.
   - `cosmic-ray init` runs through its installed console script, never `python -m`, with a generated config (absolute `module-path`; the PR's `test-command` is never used).
   - Item kinds, each keyed by the content it approves: Python equivalents (head-only prune entries), Python config keys, Rust exclusions (`exclude_re` matches and other `.cargo/mutants.toml` keys), Rust hidden code (`mutants::skip`, `macro_rules!`, `include!`, `#[path]`, opaque macro arguments, a new function with no mutant; excludes `tests/`, `benches/` and `examples/`, amended R24), and gate-shaping files (target `gate`).
4. **Red items merge only by admin override.** Any item makes `mutation-gate-items` red, and the red lists every item as `uncleared item: <target> <kind> <key>`. A `weakened:` or `base suite unjudgeable` red in `mutation-pr` is handled the same way. A reviewed PR merges only by the operator's admin override (`enforce_admins` is false); `auto-merge` never merges a red PR. Keys still carry the content they flag, so an edited item is a new line in the list. A reviewer-supplied exemption inside the PR would let the PR author clear its own gate, so none exists.
5. **Tracked required-check list (amended R36).** `scripts/ci-gate.sh` reads `.github/required-status-checks` (blank lines and `#` comments ignored; a missing, unreadable or empty file fails closed before any poll) and waits for a completed check run on the PR head SHA for each listed context, other than the self-checks `secret-scan` and `auto-merge` and the advisory `snyk-scan`. `GITHUB_TOKEN` cannot read branch protection, so the list mirrors it and V4 checks the two against each other. The file ships listing `secret-scan` and `mutation-pr`.
6. **Bootstrap order.** The PR that adds `mutation-gate-items.yml` is not judged by it, because `pull_request_target` runs the base branch's workflow, which lacks it. So: (1) merge; (2) the operator adds `mutation-gate-items` to branch protection with expected source GitHub Actions, and sets the same expected source on `mutation-pr` and `secret-scan`, so a status posted with a personal token cannot satisfy them; (3) a follow-up PR adds `mutation-gate-items` to `.github/required-status-checks`, after confirming that the `pull_request_target` check run lands on the PR head SHA.
7. **Workflow.** `mutation-pr.yml` sets `concurrency: { group: mutation-pr-${{ github.event.pull_request.number }}, cancel-in-progress: true }`. `scripts/pre-push` prints, advisory, without running a mutant and without looking up a PR, the items the branch's merge-base range would raise.

## Repro commands

Each was checked against the real usage text or Makefile guard.

- Python weakening for one shard, or for one mutant: `make -C <dir> mutants-weakening BASE=<merge-base sha> MUTANT_SHARD=<k>/<n>` or `make -C <dir> mutants-weakening BASE=<merge-base sha> JOB=<operator>@<occurrence>`. `BASE` must be a lowercase hex sha, and exactly one of `MUTANT_SHARD` and `JOB` is given. The target writes nothing in the tracked tree.
- Rust whole crate: `scripts/mutation-pr-run.sh --whole [--shard <k>/<n> [--expect <count>]] <crate-dir>...`.
- Items: `scripts/mutation-gate-items.sh <base-sha> <head-sha>` prints every `uncleared item: ...` line.

## Consequences

- Deleting or weakening a test now surfaces in the PR, not a month later in the sweep. A Rust PR touching a crate runs its whole mutant set (ADR-0046 measured 2,221 mutants over 37 shards for all 13 crates at its branch base; one crate is a fraction of that), so per-PR CI minutes rise.
- Whenever a PR changes an equivalence list, an exclusion, hidden code or a gate file, `mutation-gate-items` is red and only the operator can merge it, by admin override. Pre-push shows the items beforehand. The same holds for a `weakened:` or `base suite unjudgeable` red.
- A uniform refactor of many test files plans up to 40 shards per dir and runs in waves.
- The gate is tamper-resistant only once the operator completes the bootstrap order; until the check is required in branch protection and listed in `.github/required-status-checks`, it is absent.

### Known limits

- A hostile test that asserts nothing real (a hash of the module, for example) kills every mutant and defeats any mutation-based gate; the design targets a goal-seeking agent using the documented levers.
- A weakening on a mutant another head test still kills is invisible to any mutation-based gate.
- A base assertion that runs once and already fails on the unmutated head gives the base arm no information about a mutant; its head replacement is judged only by the head arm.
- An assertion made by a module-level function, `self.fail(...)` or `raise AssertionError` is not a rewritten statement and still stops its test at the first failure; `self.assert*` statements in helper methods are rewritten.
- `enforce_admins` is false, so only the local branch guard and the agent instructions keep a session holding the operator's credentials from pushing to master or merging a red PR.
- Code in `#[cfg(test)]` modules is not examined for hidden code.
- N7 (no agent, script or workflow merges a PR whose `mutation-gate-items` or `mutation-pr` check is red) is instruction-only: nothing mechanical stops a session holding the operator's credentials from merging.
- A new crate outside the `*/*-rs/` layout is neither an item nor mutated: `mutation-pr-detect.sh` lists only `*/*-rs/Cargo.toml`, so a plain path-dependency library escapes the gate. This was already true on master.
- A crates.io proc-macro or derive dependency, which the PR author can publish, produces no item: dependency-table changes are not items, so `dependency-review` is the gate for new crates.

## Related

- ADR-0042: Rust sweep holds zero missed
- ADR-0044: per-PR Python mutation gate on changed lines
- ADR-0046: shard the Rust mutation runs (shard size, planner, `--expect`)
- Spec `docs/superpowers/specs/2026-11-26-pr-mutation-test-weakening-design.md`; plan `docs/superpowers/plans/2026-11-26-pr-mutation-test-weakening.md`
