# Items gate runs master's current script and holds open PRs across a gate change

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
2. **Hold open PRs across a gate change, then re-judge them.**
   - A gate tightening reaches master only through a gate-file PR. The items check is red on
     every such PR, so only the operator merges one, by admin override.
   - **Before** the admin merge, every other open non-draft PR is converted to draft with
     `gh pr ready --undo <n>`.
     - Auto-merge holds drafts.
     - `gh pr merge` refuses a draft, so an auto-merge job already polling (up to 90 minutes)
       cannot merge one on its old items result.
     - A bot PR labelled `automerge-ok` is held the same way.
   - **After** the merge, those PRs are marked ready with `gh pr ready <n>`.
     - `ready_for_review` re-runs only the items check and auto-merge, not `mutation-pr` or
       the crate workflows, which use the default trigger types.
     - With item 1, the items check uses the new gate, and auto-merge's `ci-gate.sh` keeps the
       newest run per check name, so the new result governs.
   - PRs that were already drafts need nothing: marking them ready later fires
     `ready_for_review`, which runs the current gate.
   - The step must happen before the merge, because the person merging is the one who needs
     reminding. `run()` in `scripts/mutation_gate_items.py` prints the procedure whenever it
     reports a `gate` item. It therefore appears in the red items log of exactly the PRs that
     need it, where the operator decides to override.
3. **Tests.**
   - `tests/test_mutation_gate_items_workflow.py` pins the checkout ref and the new run line,
     and asserts `base.sha` appears nowhere in the workflow text.
   - `tests/test_mutation_gate_items.py` pins the reminder line: present for a gate item,
     absent otherwise.

Both changed files are gate files, so this PR's own items check is red by design and the
operator merges it by admin override. The reminder line comes from master's script, so it
first appears on the gate-file PR after this one.

## Known limits

- An operator direct push to master (`enforce_admins` is false) or a `rollback-cycle` revert can
  change a gate file with no PR, so no items run prints the reminder. Agents cannot push gate
  files directly: the branch guard's safe-list admits none of them.
- The procedure is followed, not enforced. Its only failure is the in-flight merge described in
  window 2, which needs a gate-file merge and a polling non-draft PR at the same moment.

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
- **Close and reopen every open PR.**
  - After the merge, it is too late: an in-flight auto-merge job can merge first.
  - Before the merge, it works but re-fires every workflow on reopen (16 runs on #238) and
    restarts in-flight `mutation-pr` runs. Draft-first re-runs only items and auto-merge.
- **Re-judge with a body edit (`edited`).** It re-runs only the items check, but nothing holds
  a polling auto-merge job in the meantime.
- **Run master's items script inside the auto-merge job before `gh pr merge`.** This closes
  window 2 with no operator step. But it puts cosmic-ray and cargo-mutants into the auto-merge
  job, and adds a second, PR-controlled place where the gate runs.
- **`ref: ${{ github.sha }}`.** For `pull_request_target`, GitHub documents `GITHUB_SHA` as the
  last commit on the base branch, but this could not be confirmed from a past run without a new
  probe. `base.ref` plus `rev-parse` needs no such assumption.

## Requirements

- **R1.** `.github/workflows/mutation-gate-items.yml`'s single `actions/checkout` step has `ref: ${{ github.event.pull_request.base.ref }}`, keeps `fetch-depth: 0` and `persist-credentials: false`, and the workflow text contains no `base.sha`.
- **R2.** The gate step's `run` is exactly `scripts/mutation-gate-items.sh "$(git rev-parse HEAD)" "${HEAD_SHA}"`, its `env` holds `HEAD_SHA: ${{ github.event.pull_request.head.sha }}` and no `BASE_SHA`, and the workflow's set of `run` commands is otherwise unchanged.
- **R3.** `tests/test_mutation_gate_items_workflow.py` asserts R1 and R2: the checkout ref equals `${{ github.event.pull_request.base.ref }}`, the allow-listed run set contains the R2 line in place of `scripts/mutation-gate-items.sh "${BASE_SHA}" "${HEAD_SHA}"`, the gate step's env has no `BASE_SHA`, and `base.sha` does not occur in the workflow text.
- **R4.** When any item has target `gate`, `run()` in `scripts/mutation_gate_items.py` returns exit 1 with the line `gate files changed: before the admin merge, mark every other open non-draft PR as draft (gh pr ready --undo <n>); after it, mark those PRs ready (gh pr ready <n>) so their mutation-gate-items check re-runs on the new gate.` exactly once, after the last `uncleared item:` line and before the existing operator line; when no item has target `gate`, that line is absent; item computation is unchanged.
- **R5.** `tests/test_mutation_gate_items.py` asserts R4 with three cases: a changed gate file yields the line once, between the last `uncleared item:` line and the operator line; a change yielding only a non-`gate` item (for example a new Python equivalent) yields no such line; a change yielding no items returns exit 0 and `mutation-gate-items: no uncleared items`.
- **R6.** Root `CLAUDE.md`'s `mutation-gate-items.yml` line states that the script runs from `base.ref` (master's tip) and that around a gate-file admin merge every other open non-draft PR is marked draft before the merge and ready after it; the file stays at or under 30,000 bytes.
- **R7.** `docs/adr/0048-pr-mutation-gates-see-test-weakening.md` gains a line dated 2026-11-27 recording that the items job runs the script from `base.ref`, the reason (math#238's `reopened` payload carried a base 53 commits behind master while an `edited` payload on the same head carried master's tip), and the draft-before, ready-after procedure; `docs/superpowers/README.md` drops the P1 Backlog row "mutation gate: items job runs the gate script from the PR's stale `base.sha`".
- **V1.** After merge, open a throwaway docs-only PR as a draft and record its API `base.sha`, land a direct docs commit on master, then close and reopen the PR (it stays a draft, so auto-merge holds it). The `reopened` items run's checkout step resolves to master's tip at run time (`HEAD is now at <new commit>`), not the recorded `base.sha`, and the run passes. Then close the PR and delete its branch.
- **N1.** `scripts/mutation-gate-items.sh` is unchanged, and `scripts/mutation_gate_items.py` changes only in the text `run()` returns.
- **N2.** Branch protection is unchanged: `strict` stays `false`, and the required contexts, their app ids and `enforce_admins` are as before.
- **N3.** No new workflow file is added, and `auto-merge.yml` and `scripts/ci-gate.sh` are unchanged.
