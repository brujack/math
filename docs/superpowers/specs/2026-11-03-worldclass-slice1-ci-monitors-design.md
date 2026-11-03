# Worldclass slice 1: mutation monitor correctness and an actionlint gate

- **Status:** Draft
- **Date:** 2026-11-03
- **Issues:** #195, #100, #95, #90

## Context

A worldclass audit of the repo on 2026-11-03 found coverage at 91-100% for every
sub-project, so coverage is not the gap. The first slice targets the CI monitors that
currently misreport, plus the one cheap lint gate the Backlog already records as missing.

Premises verified on master `622ba81` before design:

1. **#195 is a discovery bug, not a crate failure.** `.github/workflows/mutation-testing.yml:48`
   derives crates with `find . -name Cargo.toml -not -path '*/target/*' -not -path '*/.cache/*'`.
   `git ls-files '*/Cargo.toml' | grep fixtures` lists six fixture crates under
   `tests/fixtures/cargo-deny/` (added with the cargo-deny gate). The 2026-11-01 run filed #195
   naming exactly those six. The 11 real crates all evaluated mutants in that run (11
   `mutants tested` summary lines, every one with a non-zero caught count).
   `scripts/cargo-deny-all.sh:23` already uses the correct derivation,
   `git ls-files '*/*-rs/Cargo.toml'`.
2. **#100 is still live.** `scripts/mutation-notify.sh:189-193` comments "Closing." and closes the
   open tracking issue whenever `RESULT == success`, with no knowledge of whether the run was a
   full sweep or a single-unit dispatch (`crate` input in the Rust workflow, `subproject` in the
   Python one). A single-crate dispatch today would close #195 over 10 crates it never ran.
3. **actionlint is run nowhere and reports 41 findings.** actionlint 1.7.12 (release tarball,
   sha256 verified against the release checksums file) with shellcheck on PATH, run at the repo
   root on master `622ba81`: exit 1, 41 findings. 40 are in the `Publish coverage badge` step of
   the 20 rendered `*-rs.yml`/`*-py.yml` workflows (per file: one SC2015 for
   `git fetch ... && git worktree add ... || git worktree add -b ... --orphan ...`, one SC2034 for
   the unused retry variable `i`). 1 is SC2086 on the unquoted `${crate_dirs}` in
   `mutation-testing.yml`. All 20 files are rendered from two templates,
   `scripts/crate_templates/ci.yml` and `scripts/crate_templates/python/py.yml`.
4. **The badge retry loop hides a failed push.** In the same step,
   `for i in 1 2 3; do ...; git push origin coverage-data && break; sleep ...; done` ends on
   `sleep` after three failed pushes, so the step exits 0 and the badge silently goes stale.
5. **#95 and #90 are fixed in code but still open.** #95 (pi-rs and e-rs evaluate zero mutants):
   the 2026-11-01 run tested 148 and 170 mutants in the two largest crates. #90 (unpinned ruff,
   repo-wide lint drift): every install site pins `ruff==0.16.4` and `tests/test_tool_pins.py`
   enforces one version.

Population note for premise 3: the 41 count is one machine (`claude`, shellcheck
`/usr/local/bin/shellcheck`) against one tree (`622ba81`); CI will run its own pinned shellcheck,
so the CI count corroborates rather than reproduces it.

## Design

### A. Rust crate discovery (#195)

Split discovery out of `Run mutants` into its own step, `List crates` (`id: crates`), that writes
one line `crate_dirs=<dir> <dir> ...` (space-joined, single line) to `GITHUB_OUTPUT`:

- `CRATE` input set: use it unchanged (existing behaviour).
- Otherwise: `git ls-files '*/*-rs/Cargo.toml'`, take each path's directory.
- Empty list: print the existing "no crates found to test — refusing to report green" message
  and exit 1 (guard moves with the derivation).

`Run mutants` reads `steps.crates.outputs.crate_dirs` through `env:` and iterates it. Status-file
slugs keep their current form (`<crate>-<crate>-rs`); `git ls-files` emits no `./` prefix, and the
existing `${crate_dir#./}` strip is a no-op on such paths, so slugs for the real crates are
unchanged.

Test, in `tests/test_mutation_workflows.py`, following the existing pattern of executing a step's
`run` block in the repo, but with `bash -e` (as the runner does) and parsing `GITHUB_OUTPUT` the
way the runner does: every line must be `key=value` (a bare multi-line value fails the test).

- With `CRATE` empty, `crate_dirs` lists exactly the directories of
  `git ls-files '*/*-rs/Cargo.toml'` (11 today), and none starts with `tests/`.
- Positive control: `git ls-files 'tests/fixtures/**/Cargo.toml'` is non-empty, so a
  `find`-based derivation would fail the first assertion.
- With `CRATE=sq/sq-rs`, `crate_dirs` is exactly `sq/sq-rs`.
- The `run` block contains no `${{` (input passes through `env:`).

### B. Notify closes only after a full sweep (#100)

Both mutation workflows' notify steps pass `FULL_SWEEP`: `"true"` when the dispatch input is
empty (schedule, or dispatch without a unit), else `"false"`.

`scripts/mutation-notify.sh` requires `FULL_SWEEP` (`:?` guard with a message naming the
workflow wiring) and accepts only `true` or `false` (anything else exits 1 naming the value).
On `RESULT == success`:

- `FULL_SWEEP=true`: unchanged — comment and close the open issue.
- `FULL_SWEEP=false`: if an issue is open, comment
  `Single-unit run green as of <RUN_URL>; left open (only a full sweep closes this issue).` and do
  not close it; return 0.

The failure path is unchanged for both values: a red single-unit run still files or comments.
`check_expected_units` still runs before the success branch, as today.

Tests in `tests/scripts/mutation_notify.bats` with the existing `gh` mock: success + full sweep
closes; success + single unit with an open issue records one `issue comment` carrying the
single-unit text and no `issue close`; success + single unit with no open issue makes neither
call; missing and invalid `FULL_SWEEP` each exit 1 with their message; failure + single unit still
comments.

### C. actionlint gate (CI-enforced)

- **Make:** new root target `lint-workflows`, added to `lint`. It runs `actionlint` over
  `WORKFLOWS` (default: the tracked `.github/workflows/*.yml`; overridable so a test can point it
  at a fixture). When `actionlint` is not on PATH: with `CI=true` it exits 1 naming the missing
  tool; otherwise it prints a message naming the install remedy and exits 0, so a development
  machine without it can still commit.
- **CI:** `scripts.yml` gains an install step for actionlint 1.7.12 from the release tarball with
  a `sha256sum -c` line before extraction (core.md ci-002), placed after the pinned shellcheck
  step. Its `paths:` filter gains `.github/workflows/**` (replacing the per-file workflow entries
  it subsumes), so any workflow edit runs the gate. This also covers `mutation-testing*.yml`,
  whose tests `scripts.yml` never triggered on before.
- **Positive control:** fixture `tests/fixtures/actionlint/sc2086.yml`, a minimal workflow whose
  `run:` block expands an unquoted variable. A bats case runs `make lint-workflows
  WORKFLOWS=<fixture>` and asserts a non-zero exit with `SC2086` in the output, proving both
  actionlint and its shellcheck integration ran. The case skips with a message when actionlint or
  shellcheck is absent and `CI` is not `true`, and fails when either is absent under `CI=true`.
  Further bats cases cover the missing-tool guard: absent + `CI=true` exits 1; absent + `CI`
  unset exits 0 with the remedy text.
- **No pre-push change.** actionlint is not installed on the development machines, so a local
  branch would only print a skip line; CI is the gate.
- **Findings:** fix the badge step in both templates, then
  `python3 scripts/render_crate_files.py --write`:
  - Replace `git fetch ... && git worktree add ... || git worktree add -b ... --orphan ...` with an
    `if git fetch ...; then ...; else ...; fi` whose two `git worktree add` calls each end
    `|| { echo "coverage-data worktree unavailable; badge not published"; exit 0; }`, so the badge
    stays advisory under `bash -e` (N3).
  - Retry variable `_`.
  The SC2086 is removed by A. Target after the change: actionlint exit 0, 0 findings.

### D. Issue hygiene

After merge: comment on #95 and #90 with the evidence above (run URL, pin and test name) and close
them. #195 closes on the next green full sweep through B's unchanged full-sweep path; #100 is
closed by the PR (`Closes #100`).

## Out of scope (Backlog rows added in the same change)

- Branch protection. The audit claimed nothing server-side protects `master`; that was wrong. Classic
  branch protection requires `secret-scan` and `mutation-pr`, enforces linear history and blocks
  force-push and deletion, with `enforce_admins: false` so the operator can push docs direct
  (operator decision 2026-11-03: that path must keep working). Ruleset 14955025 is dead config
  beside it; the existing P2 row now records this.
- Coverage badges are published from `pull_request` runs, so each badge shows the most recent
  PR branch's coverage, not master's; the same step's retry loop exits 0 after three failed
  pushes. Both fixed together in one P3 row (a warning on the PR run was dropped in Step 8: it
  changes no verdict and nobody reads annotations on an auto-merged run).
- Mutation kill rates (Python pi 62%, e 55%; three Rust crates 68-78%): slices 2 and 3.

## Requirements

- **R1.** `[PR1]` `mutation-testing.yml` derives its crate list with `git ls-files '*/*-rs/Cargo.toml'` in a dedicated `List crates` step, and contains no `find` for `Cargo.toml`.
- **R2.** `[PR1]` A test executes the `List crates` step under `bash -e`, parses `GITHUB_OUTPUT` as `key=value` lines, and asserts `crate_dirs` is exactly the 11 `*/*-rs` crate directories with none under `tests/`, plus a positive control that fixture `Cargo.toml` files exist under `tests/fixtures/`.
- **R3.** `[PR1]` With a `crate` dispatch input, `List crates` yields exactly that input, and the step reads the input only through `env:`.
- **R4.** `[PR1]` An empty derived crate list exits 1 with the "no crates found to test" message.
- **R5.** `[PR1]` On success, `mutation-notify.sh` closes an open tracking issue only when `FULL_SWEEP=true`; with `FULL_SWEEP=false` it posts one non-closing single-unit comment when an issue is open and makes no `gh issue close` call.
- **R6.** `[PR1]` `mutation-notify.sh` exits 1 with a message when `FULL_SWEEP` is unset or is not `true`/`false`.
- **R7.** `[PR1]` Both mutation workflows pass `FULL_SWEEP` as `"true"` exactly when their unit dispatch input is empty.
- **R8.** `[PR1]` Root `make lint` runs a `lint-workflows` target that runs actionlint over `WORKFLOWS`; with actionlint absent it exits 1 when `CI=true` and exits 0 with a remedy message otherwise.
- **R9.** `[PR1]` `scripts.yml` installs actionlint 1.7.12 with a `sha256sum -c` check before extraction, after the pinned shellcheck step, and its `paths:` filter matches every file under `.github/workflows/`.
- **R10.** `[PR1]` A bats case runs `lint-workflows` on `tests/fixtures/actionlint/sc2086.yml` and asserts a non-zero exit with `SC2086` in the output, failing rather than skipping under `CI=true`.
- **R11.** `[PR1]` actionlint 1.7.12 reports 0 findings over the repo's workflows.
- **R12.** `[PR1]` In both badge templates a failed `git worktree add` for `coverage-data` prints a message and exits 0.
- **R13.** `[PR1]` The 20 rendered workflows match their templates (`tests/test_crate_uniformity.py` green).
- **V1.** The PR's `scripts` CI job log shows actionlint 1.7.12 running, exiting 0 on the repo, and the R10 case passing (not skipped).
- **V2.** After merge, a `workflow_dispatch` full sweep of `mutation-testing.yml` lists 11 crates and no `tests-fixtures-*` status entry.
- **V3.** #95 and #90 are closed with evidence comments; #100 is closed by the PR.
- **N1.** No change to which mutants run per crate or to any crate `Makefile`'s `mutants` recipe.
- **N2.** No branch-protection or ruleset change.
- **N3.** A coverage-data failure (worktree or push) never fails a CI job.
- **N4.** No edit to a rendered workflow that is not produced by `render_crate_files.py --write` from a template.
- **N5.** No change to `scripts/pre-push`.

## Multi-Lens Review

Reviewed at commit: `3f42636` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: A, B and C pass the reads-it test; D does not. D changes no verdict (N3 keeps the job green) and its `::warning::` lands on a `pull_request` run that auto-merge has already landed, so nobody reads it; the badge value is also already wrong (PR-branch source, Out of scope row 2). Drop D (R12, the `pushed` flag) and fix the retry loop with the badge source, or give it a durable consumer (stale marker in the `coverage-data` JSON, or an issue). The SC2015 rewrite is a real bug fix and should stay.
Assumption: someone reads `::warning::` annotations on auto-merged PR runs; refuted if no script or person consumes run annotations (`git grep -n annotations`). No uncertain assumption for A, B or C; their premises were re-verified (11 real crates, 6 fixtures, notify closes on any success, `EXPECTED_STATUS_UNITS` does not guard single-unit runs).
Disposition: Addressed — D dropped (operator, 2026-11-03); the retry-loop defect moves into the badge-source Backlog row; SC2015 rewrite kept.

### Ergonomics

Finding: the actionlint gate fails open where it is enforced. `lint-workflows` copies `lint-python`'s exit-0-when-missing guard, CI reaches it through `make lint`, and the only durable check asserts actionlint is installed, not that it ran. A PATH slip turns CI into a green "skipping". Locally actionlint is absent on `claude`, so R10's pre-push branch only prints a skip line. Fix: a missing actionlint exits 1 when `CI=true`; add a seeded-defect case `lint-workflows` must reject; either get actionlint into `make install-deps` or drop R10 and call the gate CI-only. Minor: under R5 a green single-unit re-dispatch leaves no trace on the issue; a non-closing "unit X green as of <run>" comment would cost nothing.
Assumption: no uncertain assumption found.
Disposition: Addressed — missing actionlint exits 1 under `CI=true`, SC2086 positive-control fixture added (R8, R10); R10's pre-push branch dropped, CI-only (N5); non-closing single-unit comment adopted (R5) (operator, 2026-11-03).

### Risk

Finding: no case fails when actionlint's shellcheck integration produces nothing. 40 of 41 findings are shellcheck findings, and actionlint silently disables that rule when `shellcheck` is not on PATH, so a reordered `scripts.yml` or a machine without shellcheck passes clean. Fix: a positive-control fixture with a known SC2086 that `lint-workflows` must report. Secondary: (1) A's test reads `GITHUB_OUTPUT` as raw text; a multi-line `crate_dirs=` write passes it but the runner rejects it, so pin the format (space-joined or heredoc delimiter) and parse as the runner does. (2) The SC2015 `if/else` turns a post-fetch `git worktree add` failure into a red coverage job under `bash -e`, against N3; give non-push `coverage-data` failures the same warn-and-exit-0 treatment or scope N3 to push.
Assumption: actionlint in the `scripts` job finds the pinned shellcheck; confirm with `actionlint -verbose` in the CI log or a seeded defect failing CI.
Disposition: Addressed — positive-control fixture (R10); `GITHUB_OUTPUT` pinned to one space-joined `key=value` line, tested under `bash -e` (R2); worktree failure exits 0 (R12, N3) (operator, 2026-11-03).

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
