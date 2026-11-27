# Items gate runs master's current script and cannot merge on a stale run

- **Date:** 2026-11-27
- **Backlog row:** P1 "mutation gate: items job runs the gate script from the PR's stale `base.sha`"
- **Related:** ADR-0048, `docs/superpowers/specs/2026-11-26-pr-mutation-test-weakening-design.md`

## Problem

`.github/workflows/mutation-gate-items.yml` checks out its gate script at
`${{ github.event.pull_request.base.sha }}` and passes the same value to
`scripts/mutation-gate-items.sh` as BASE.

GitHub sets `pull_request.base.sha` when the PR's head is pushed; it does not move when master
moves.

Measured 2026-11-27 on math#238:

- Renovate last pushed the head on 2026-11-20. The PR was closed and reopened on 2026-11-27,
  after math#252 and math#253 merged.
- The `reopened` run (46053939365) still carried base 19cdee3, 53 commits behind master.
- `scripts/mutation-gate-items.sh` did not exist there, so the run failed with exit 127.
- After a Renovate rebase (head 777bb40) the payload carried a fresh base, and the check
  passed.

Population: one PR, one event type (`reopened`); the claim that a head push refreshes
`base.sha` rests on that one rebase plus GitHub's payload semantics.

Two windows follow:

1. **Event time.** A PR last pushed before a gate tightening is judged by the older script, so
   it can pass an item the current gate flags. Example: a PR last pushed between math#252 and
   math#253 that edits `.github/required-status-checks`. A PR older than the gate fails
   closed, as #238 did.
2. **Merge time.** A PR whose items run went green, followed by a gate-tightening merge to
   master, still merges on that green check.
   - Branch protection has `strict: false`, so nothing re-runs the check.
   - `gh run rerun` would not help: it replays the original event payload.

The script itself is not at fault: `mutation_gate_items.py` diffs from
`git merge-base <base> <head>`, so the item list does not depend on which master commit is
passed as BASE, only on which script runs.

## Design

1. **Workflow: check out the base branch tip.**
   - The checkout step uses `ref: ${{ github.event.pull_request.base.ref }}`. The
     `branches: [master]` trigger filter makes that always `master`, resolved when the step
     runs.
   - The gate step passes `"$(git rev-parse HEAD)"` as BASE, so the script and BASE are the
     same commit. `BASE_SHA` leaves the step's `env`.
   - Every event then runs master's current gate, and a stale PR gets the real item list
     instead of exit 127.
   - `pull_request_target` reads the workflow file from the base branch, so this takes effect
     only after the PR merges.
2. **Branch protection `strict: true`.**
   - A PR behind master cannot merge.
   - Bringing it up to date pushes its head, which fires `synchronize` and re-runs the items
     check on master's tip. That closes the merge-time window.
   - This is a repository setting, applied with `gh api` after the PR merges (V1).
3. **`scripts/ci-gate.sh` names the behind state.**
   - The auto-merge job cannot update the branch itself: a push made with `GITHUB_TOKEN` fires
     no workflows, so the checks would never re-run (N1).
   - With strict on, its `gh pr merge` on a behind branch fails with GitHub's generic error.
   - Only where `ci_gate` would otherwise return 0 (every required check passed, or none
     triggered), it reads `mergeable_state` from `repos/<repo>/pulls/<pr>`. On `behind` it
     fails with a message naming the remedy. A failing PR keeps its failure list, unmasked.
   - Any other value proceeds, including `unknown`, which GitHub reports while it computes
     the state; `gh pr merge` remains the final judge there.
   - Assumption, settled by V2: with the required checks green and strict on, GitHub reports
     a behind PR as `behind` rather than `blocked`. If it reports `blocked`, the message does
     not fire and the merge fails with GitHub's generic error: less clear, not less safe.
4. **Who updates a behind PR.**
   - Renovate rebases its own PRs when they fall behind and automerge is on.
   - Agent and operator PRs run `gh pr update-branch <n>` before marking ready, and again if
     the auto-merge job reports the behind message.
5. **Tests.**
   - `tests/test_mutation_gate_items_workflow.py` pins the checkout ref and the new run line,
     and asserts `base.sha` appears nowhere in the workflow text.
   - `tests/scripts/ci_gate.bats` covers `behind`, `clean`, `unknown` and a failed read.

Both changed files are gate files (`mutation_gate_items.py` `GATE_FILES`), so this PR's own
items check is red by design and the operator merges it by admin override.

## Rejected alternatives

- **`ref: ${{ github.sha }}`.** For `pull_request_target`, GitHub documents `GITHUB_SHA` as the
  last commit on the base branch, but the run API reports the PR head as the run's `head_sha`.
  This could not be confirmed from a past run without a new probe. `base.ref` plus
  `rev-parse` needs no such assumption.
- **Re-trigger items on every open PR after a gate change.** This needs a new push-to-master
  workflow and a token able to fire events, and the operator chose strict instead.
- **Strict only, no workflow change.** Strict alone closes both windows, but then the gate's
  freshness rests on a repository setting that nothing in the repository checks. The workflow
  change makes event-time freshness hold whatever the setting.

## Requirements

- **R1.** `.github/workflows/mutation-gate-items.yml`'s single `actions/checkout` step has `ref: ${{ github.event.pull_request.base.ref }}`, keeps `fetch-depth: 0` and `persist-credentials: false`, and the workflow text contains no `base.sha`.
- **R2.** The gate step's `run` is exactly `scripts/mutation-gate-items.sh "$(git rev-parse HEAD)" "${HEAD_SHA}"`, its `env` holds `HEAD_SHA: ${{ github.event.pull_request.head.sha }}` and no `BASE_SHA`, and the workflow's set of `run` commands is otherwise unchanged.
- **R3.** `tests/test_mutation_gate_items_workflow.py` asserts R1 and R2: the checkout ref equals `${{ github.event.pull_request.base.ref }}`, the allow-listed run set contains the R2 line in place of `scripts/mutation-gate-items.sh "${BASE_SHA}" "${HEAD_SHA}"`, the gate step's env has no `BASE_SHA`, and `base.sha` does not occur in the workflow text.
- **R4.** Where `ci_gate` in `scripts/ci-gate.sh` would otherwise return 0 (before printing `All required checks passed.` or `No required checks triggered. Proceeding.`), it reads `gh api repos/<repo>/pulls/<pr> --jq .mergeable_state`. On `behind` it prints `PR <pr> is behind master: run gh pr update-branch <pr>` to stderr and returns 1. If the read fails, it returns 1. Any other value returns 0 as before. A timeout or a failed required check returns 1 without reading `mergeable_state`.
- **R5.** `tests/scripts/ci_gate.bats` has cases where all required checks pass and `mergeable_state` is `behind` (exit 1, stderr contains `PR 42 is behind master: run gh pr update-branch 42`), `clean` (exit 0, `All required checks passed.`), `unknown` (exit 0) and where the `pulls/<pr>` read for `mergeable_state` fails (exit 1), plus a case where a required check failed and `mergeable_state` is `behind` (exit 1, stderr lists the failed check and does not contain `is behind master`).
- **R6.** Root `CLAUDE.md`'s `mutation-gate-items.yml` line states that the script runs from `base.ref` (master's tip) and that protection is strict. Its Branch Workflow section says to run `gh pr update-branch <n>` when a PR is behind master. The file stays at or under 30,000 bytes.
- **R7.** `docs/adr/0048-pr-mutation-gates-see-test-weakening.md` gains a dated line recording that the items job runs the script from `base.ref` and that protection is strict, with the reason (`pull_request.base.sha` is fixed at the PR's last head push), and `docs/superpowers/README.md` drops the P1 Backlog row "mutation gate: items job runs the gate script from the PR's stale `base.sha`".
- **V1.** After merge, `gh api repos/brujack/math/branches/master/protection/required_status_checks --jq .strict` prints `true`, and `.checks` still lists `secret-scan`, `mutation-pr` and `mutation-gate-items` with app_id 15368.
- **V2.** After merge and V1, open a throwaway docs-only PR from a branch based on 19cdee3. Its `mutation-gate-items` run checks out master's tip, finds the script (no exit 127) and passes, and its auto-merge job prints `PR <n> is behind master: run gh pr update-branch <n>` and does not merge. Then close the PR and delete the branch.
- **N1.** No workflow or script updates a PR branch (`gh pr update-branch`, a merge or a push) on the PR's behalf.
- **N2.** `scripts/mutation_gate_items.py` and `scripts/mutation-gate-items.sh` are unchanged.
- **N3.** Branch protection changes only `strict`; the required contexts, their app ids and `enforce_admins` are unchanged.
