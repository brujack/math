# Items gate runs master's current script

- **Date:** 2026-11-27
- **Backlog row:** P1 "mutation gate: items job runs the gate script from the PR's stale `base.sha`"
- **Related:** ADR-0048, `docs/superpowers/specs/2026-11-26-pr-mutation-test-weakening-design.md`

## Problem

`.github/workflows/mutation-gate-items.yml` checks out its gate script at
`${{ github.event.pull_request.base.sha }}` and passes the same value to
`scripts/mutation-gate-items.sh` as BASE. That value comes from the event payload, and the
payload's base is not always master's tip.

Measured 2026-11-27 on math#238. Renovate last pushed its head (8a7d662) on 2026-11-23T07:08Z;
base 19cdee3 is dated 2026-11-23T07:06:58Z.

| Run         | Event                                           | Head    | `BASE_SHA`                        | Result                                                                |
| ----------- | ----------------------------------------------- | ------- | --------------------------------- | --------------------------------------------------------------------- |
| 46053939365 | `reopened` (19:03Z)                             | 8a7d662 | 19cdee3, 53 commits behind master | exit 127: `scripts/mutation-gate-items.sh: No such file or directory` |
| 46055972031 | `edited`, a body edit (19:20Z)                  | 8a7d662 | 33e09a2, master's tip             | success                                                               |
| 46056218964 | `synchronize`, after a Renovate rebase (19:22Z) | 777bb40 | cd8c48b, master's tip             | success                                                               |

So the payload's base is refreshed by some events and not others: `reopened` carried a base four
days stale, while an `edited` event on the same head carried master's tip. Population: one PR,
three events, one of each type.

Two windows follow:

1. **Event time.** An event whose payload carries a stale base runs an older gate script. A PR
   last refreshed before a gate tightening can then pass an item the current gate flags, for
   example an edit to `.github/required-status-checks` judged by a script from before
   math#253. A PR older than the gate fails closed, as #238 did.
2. **Merge time.** A PR whose items run went green, followed by a gate-tightening merge to
   master, still merges on that green check. Nothing re-runs the check, and `gh run rerun`
   replays the original payload.

The script itself is not at fault: `mutation_gate_items.py` diffs from
`git merge-base <base> <head>`, so the item list depends only on which script runs, not on which
master commit is passed as BASE.

## Design

1. **Workflow: check out the base branch tip.**
   - The checkout step uses `ref: ${{ github.event.pull_request.base.ref }}`. The
     `branches: [master]` trigger filter makes that always `master`, resolved when the step
     runs, whatever base the payload carries.
   - The gate step passes `"$(git rev-parse HEAD)"` as BASE, so the script and BASE are the same
     commit. `BASE_SHA` leaves the step's `env`.
   - Every event then runs master's current gate, which closes window 1. A stale PR gets the
     real item list instead of exit 127.
   - `pull_request_target` reads the workflow file from the base branch, so this takes effect
     only after the PR merges.
2. **Re-judge open PRs after a gate change.**
   - A gate tightening reaches master only through a gate-file PR, and the items check is red on
     every such PR, so only the operator merges one, by admin override.
   - After merging one, every open PR is closed and reopened. Each `reopened` event re-runs the
     items check, which with item 1 uses the new gate. That closes window 2.
   - On 2026-11-27 this would have touched one PR (#238). There are 0 open PRs now.
   - This is a documented procedure, not a mechanism: ADR-0048 and the root `CLAUDE.md` items
     line state it.
3. **Tests.** `tests/test_mutation_gate_items_workflow.py` pins the checkout ref and the new run
   line, and asserts `base.sha` appears nowhere in the workflow text.

The workflow is a gate file, so this PR's own items check is red by design and the operator
merges it by admin override.

## Rejected alternatives

- **Branch protection `strict: true`.** This closes window 2 mechanically. Measured over the last
  40 merged PRs:
  - 29 had at least one master commit land while they were open, 180 commits in all, mostly
    direct docs commits.
  - Under strict, each of those PRs would need `gh pr update-branch` and a full CI rerun, and
    `mutation-pr` alone can take 60 minutes.
  - Renovate does not rebase a PR that falls behind: #238 saw 56 master commits with no
    Renovate push between its scheduled push and the operator's reopen.
  - All of that pays to close a window that opens only when a gate-file PR merges.
- **Run master's items script inside the auto-merge job before `gh pr merge`.** This closes
  window 2 with no operator step. But it puts cosmic-ray and cargo-mutants into the auto-merge
  job, and adds a second, PR-controlled place where the gate runs.
- **`ref: ${{ github.sha }}`.** For `pull_request_target`, GitHub documents `GITHUB_SHA` as the
  last commit on the base branch, but this could not be confirmed from a past run without a new
  probe. `base.ref` plus `rev-parse` needs no such assumption.
- **A push-to-master workflow that re-triggers items on open PRs.** This needs a token able to
  fire events, for a step the operator already performs at the only moment it matters.

## Requirements

- **R1.** `.github/workflows/mutation-gate-items.yml`'s single `actions/checkout` step has `ref: ${{ github.event.pull_request.base.ref }}`, keeps `fetch-depth: 0` and `persist-credentials: false`, and the workflow text contains no `base.sha`.
- **R2.** The gate step's `run` is exactly `scripts/mutation-gate-items.sh "$(git rev-parse HEAD)" "${HEAD_SHA}"`, its `env` holds `HEAD_SHA: ${{ github.event.pull_request.head.sha }}` and no `BASE_SHA`, and the workflow's set of `run` commands is otherwise unchanged.
- **R3.** `tests/test_mutation_gate_items_workflow.py` asserts R1 and R2: the checkout ref equals `${{ github.event.pull_request.base.ref }}`, the allow-listed run set contains the R2 line in place of `scripts/mutation-gate-items.sh "${BASE_SHA}" "${HEAD_SHA}"`, the gate step's env has no `BASE_SHA`, and `base.sha` does not occur in the workflow text.
- **R4.** Root `CLAUDE.md`'s `mutation-gate-items.yml` line states that the script runs from `base.ref` (master's tip) and that after merging a gate-file PR every open PR is closed and reopened so the items check re-runs; the file stays at or under 30,000 bytes.
- **R5.** `docs/adr/0048-pr-mutation-gates-see-test-weakening.md` gains a line dated 2026-11-27 recording that the items job runs the script from `base.ref`, the reason (math#238's `reopened` payload carried a base 53 commits behind master while an `edited` payload on the same head carried master's tip), and the close-and-reopen step after a gate-file merge; `docs/superpowers/README.md` drops the P1 Backlog row "mutation gate: items job runs the gate script from the PR's stale `base.sha`".
- **V1.** After merge, open a throwaway docs-only PR, then land a direct docs commit on master, then close and reopen the PR. The `reopened` items run's checkout step resolves to master's tip at run time, which is the new commit and not the PR's opening base, and the run passes. Then close the PR and delete its branch.
- **N1.** `scripts/mutation_gate_items.py` and `scripts/mutation-gate-items.sh` are unchanged.
- **N2.** Branch protection is unchanged: `strict` stays `false`, and the required contexts, their app ids and `enforce_admins` are as before.
- **N3.** No new workflow file is added, and `auto-merge.yml` and `scripts/ci-gate.sh` are unchanged.
