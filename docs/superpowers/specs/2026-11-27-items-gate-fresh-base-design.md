# Items gate runs master's current script and holds open PRs across a gate change

- **Date:** 2026-11-27
- **Backlog row:** P1 "mutation gate: items job runs the gate script from the PR's stale `base.sha`"
- **Approved:** 2026-11-27
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
2. **Hold open PRs across an items-gate change, then re-judge them.**
   - A change to the items gate reaches master only through a PR whose items check is red, so
     only the operator merges one, by admin override. The items gate is
     `scripts/mutation_gate_items.py`, `scripts/mutation-gate-items.sh`,
     `.github/workflows/mutation-gate-items.yml` and every module the script loads with
     `_load_sibling`, today only `scripts/cosmic_ray_prune.py`. It is used in item computation
     (`prune.load_entries`, `prune.resolve_entry`) and re-synced from ai-config one PR per
     change.
   - **Before** the admin merge, the operator takes every other open non-draft PR and runs
     `gh pr ready --undo <n>`, then `gh pr edit <n> --add-label gate-hold`. Drafting first
     means the `labeled` auto-merge run always finds a draft and holds:
     - The label fires a `labeled` auto-merge run, whose `cancel-in-progress` cancels any
       auto-merge job already polling (up to 90 minutes); the new run finds a draft and holds.
     - As a backup, `gh pr merge` refuses a draft, so a job that escapes the cancel still
       cannot merge on its old items result. A bot PR labelled `automerge-ok` is held the same
       way.
     - The label records exactly which PRs were converted, so the restore step never touches a
       PR that was a draft all along, such as an agent's unfinished work.
   - **After** the merge, the operator runs `gh pr ready <n>` and
     `gh pr edit <n> --remove-label gate-hold` for each PR in `gh pr list --label gate-hold`.
     - `ready_for_review` re-runs only the items check and auto-merge, not `mutation-pr` or the
       crate workflows, which use the default trigger types.
     - With item 1, the items check uses the new gate, and auto-merge's `ci-gate.sh` keeps the
       newest run per check name, so the new result governs.
   - **Agents never mark a PR ready while any open PR carries `gate-hold`.** Before
     `gh pr ready`, they check that `gh pr list --label gate-hold --json number --jq length`
     prints `0`. This stops an agent that finishes Phase 3 mid-hold from re-running the old gate
     on its own PR. A draft marked ready after the hold runs the new gate.
   - **The reminder.** `run()` in `scripts/mutation_gate_items.py` prints the procedure, addressed
     to the operator, whenever an item's path is one of the four items-gate files. It therefore
     appears in the red items log of exactly the PRs that need it. The pre-push advisory also
     shows it to the authoring agent, which the `operator:` prefix tells to leave it alone.
3. **Tests.**
   - `tests/test_mutation_gate_items_workflow.py` pins the checkout ref and the new run line,
     and asserts `base.sha` appears nowhere in the workflow text.
   - `tests/test_mutation_gate_items.py` pins the reminder line: present for each items-gate
     file, absent for any other gate file and for non-gate items. It also checks that the
     items-gate path set matches the script's `_load_sibling` calls, so a new import cannot
     drift out of it.

Both changed files are gate files, so this PR's own items check is red by design and the
operator merges it by admin override. The reminder line comes from master's script, so it
first appears on the gate-file PR after this one.

## Known limits

- An operator direct push to master (`enforce_admins` is false) or a `rollback-cycle` revert can
  change a gate file with no PR, so no items run prints the reminder. Agents cannot push gate
  files directly: the branch guard's safe-list admits none of them.
- The procedure is followed, not enforced. A skipped hold leaves the in-flight merge of window 2
  open, which needs an items-gate merge and a polling non-draft PR at the same moment.
- A tightening of any other gate file, such as `mutation-pr.yml`, is not re-judged: a green
  `mutation-pr` result on an open PR stays green. Marking ready re-runs only the items check,
  and fixing this would cost the full CI rerun rejected below.
- Marking a PR ready cancels its old auto-merge run through `cancel-in-progress`. An old job
  already past `ci-gate.sh` could still call `gh pr merge` in the seconds before the cancel
  lands.
- A `uses:` pin bump to `mutation-gate-items.yml` is not an item (`only_uses_bumps`), so it
  changes the items gate's runtime with no red check, no reminder and no hold. The workflow
  also installs a floating `stable` Rust toolchain, so `cargo mutants --list` output can change
  with no repository change at all.
- A non-draft PR opened during the hold, such as a new Renovate PR, is judged by the old gate,
  is never labelled, and can auto-merge before the admin merge lands.
- How Renovate treats a PR the operator drafted is unmeasured: if it marks the PR ready again
  during the hold, that PR is judged by the old gate.

## Rejected alternatives

- **Branch protection `strict: true`.** This closes window 2 mechanically. Measured over the last
  40 merged PRs:
  - 29 had at least one master commit land while they were open, 180 commits in all, mostly
    direct docs commits.
  - Under strict, each of those PRs would need `gh pr update-branch` and a full CI rerun, and
    `mutation-pr` alone can take 60 minutes.
  - Renovate does not rebase a PR that falls behind: #238's base fell 53 commits behind master
    (`git rev-list --count 19cdee3..33e09a2`) with no Renovate push before the operator's
    reopen.
  - All of that pays to close a window that opens only when a gate-file PR merges.
- **Close and reopen every open PR.**
  - After the merge, it is too late: an in-flight auto-merge job can merge first.
  - Before the merge, it works but re-fires every workflow on reopen (16 runs on #238) and
    restarts in-flight `mutation-pr` runs. Draft-first re-runs only items and auto-merge.
- **A `gate-hold` guard in the auto-merge job.** Its hold step could refuse to merge any PR
  while `gh pr list --label gate-hold` is non-empty, and go red if that query fails. That one
  check would also cover the agent rule, a PR opened mid-hold and Renovate un-drafting a PR,
  and it fails closed. It is not taken because it edits `auto-merge.yml` (N3), flips the
  restore order (labels off first, then ready), and leaves any PR readied mid-hold needing a
  manual re-ready. It is the next step if the procedure is ever skipped in practice.
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
- **R4.** When any item has target `gate` and a path among `scripts/mutation_gate_items.py`, `scripts/mutation-gate-items.sh`, `.github/workflows/mutation-gate-items.yml` and `scripts/cosmic_ray_prune.py`, `run()` in `scripts/mutation_gate_items.py` returns exit 1 with the line `operator: this PR changes the items gate; before the admin merge, run gh pr ready --undo <n> and then gh pr edit <n> --add-label gate-hold for every other open non-draft PR; after it, run gh pr ready <n> and gh pr edit <n> --remove-label gate-hold for each PR in gh pr list --label gate-hold.` exactly once, after the last `uncleared item:` line and before the existing operator line; for any other set of items that line is absent; item computation is unchanged.
- **R5.** `tests/test_mutation_gate_items.py` asserts R4: for each of the four items-gate paths, a change to that path alone yields exit 1 and the line once, between the last `uncleared item:` line and the operator line; the items-gate path set equals `scripts/mutation_gate_items.py`, `scripts/mutation-gate-items.sh` and `.github/workflows/mutation-gate-items.yml` plus `scripts/<name>.py` for every `_load_sibling("<name>")` call in `scripts/mutation_gate_items.py`, found with `ast`, and every `_load_sibling` call takes a single string literal; a changed `.github/workflows/mutation-pr.yml` alone yields exit 1, an `uncleared item: gate` line and no such line; a change yielding only a non-`gate` item yields exit 1, an `uncleared item:` line and no such line; a change yielding no items returns exit 0 and `mutation-gate-items: no uncleared items`.
- **R6.** Root `CLAUDE.md`'s `mutation-gate-items.yml` line states that the script runs from `base.ref` (master's tip) and that an agent never marks a PR ready while `gh pr list --label gate-hold` lists any PR, and points to ADR-0048 for the hold procedure; its `repro scripts/mutation-gate-items.sh <base> <head>` clause moves to ADR-0048 to make room; the file stays at or under 30,000 bytes.
- **R7.** `docs/adr/0048-pr-mutation-gates-see-test-weakening.md` gains a line dated 2026-11-27 recording that the items job runs the script from `base.ref`, the reason (math#238's `reopened` payload carried a base 53 commits behind master while an `edited` payload on the same head carried master's tip), the `gate-hold` procedure (draft then label before the admin merge; ready then unlabel after it), the repro `scripts/mutation-gate-items.sh <base> <head>`, and that a tightening of other gate files is not re-judged; `docs/superpowers/README.md` drops the P1 Backlog row "mutation gate: items job runs the gate script from the PR's stale `base.sha`".
- **V1.** After merge, open a throwaway docs-only PR as a draft and record its API `base.sha`. Land a direct docs commit on master, then confirm `gh api repos/brujack/math/pulls/<n> --jq .base.sha` still equals the recorded value (otherwise record V1 as inconclusive and say so). Close and reopen the PR; it stays a draft, so auto-merge holds it. In the `reopened` items run's log, the line after `git log -1 --format=%H` equals master's tip at run time, not the recorded `base.sha`, and the run passes. The run log does not show the `reopened` payload's base, so if GitHub refreshed it on reopen, V1 shows only that the checkout is master's tip, not that `base.ref` was needed; record V1 as a smoke test in that case. Then close the PR and delete its branch.
- **V2.** After merge, `gh label list --search gate-hold` shows the `gate-hold` label (create it with `gh label create gate-hold` if absent).
- **N1.** `scripts/mutation-gate-items.sh` is unchanged, and `scripts/mutation_gate_items.py` changes only in the text `run()` returns.
- **N2.** Branch protection is unchanged: `strict` stays `false`, and the required contexts, their app ids and `enforce_admins` are as before.
- **N3.** No new workflow file is added, and `auto-merge.yml` and `scripts/ci-gate.sh` are unchanged.

## Multi-Lens Review

Reviewed at commit: `cca4296` (round 1); re-run at `1f94d62` (round 2), `09f5e03` (round 3) and
`57d965d` (round 4, risk lens scoped to Design item 2, Known limits and R4-R7, V1, V2).

### Round 1 (`cca4296`, design: strict protection plus a `ci-gate.sh` behind check)

- **Goal-fit.** Finding: the `base.sha` rule was wrong (an `edited` run on the same head, 46055972031, carried master's tip), V2 could not tell the new design from the old, and the `ci-gate.sh` behind read changed no verdict while adding a fail-closed path. Assumption: a behind PR reports `mergeable_state` `behind`, not `blocked`.
- **Ergonomics.** Finding: under strict, 29 of the last 40 merged PRs had a master commit land while open (180 commits, mostly direct docs commits), so most PRs would need `gh pr update-branch` and a full CI rerun; Renovate does not rebase behind PRs (#238). Assumption: behind PRs are rare or refreshed by someone other than the operator.
- **Risk.** Finding: same `base.sha` correction; any operator-made event re-judges with `base.ref`, so strict is one option, not the only cheap one; strict binds only non-admin merges. Assumption: Renovate rebases held PRs under strict.
- **Adversarial Spec Review.** N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
- Disposition: operator chose "Re-judge step, drop strict (Recommended)".

### Round 2 (`1f94d62`, design: close and reopen every open PR after the gate merge)

- **Goal-fit.** Finding: no case fails if nobody performs the step, and the instruction lives where the merging operator does not look. Assumption: the authoring session is still running when the operator admin-merges.
- **Ergonomics.** Finding: a reopen re-fires every workflow (16 runs on #238) and restarts in-flight `mutation-pr`; `edited` is cheaper; no actor named; V1's PR would self-merge unless a draft. Assumption: no in-flight auto-merge merges during the gap.
- **Risk.** Finding: the step runs after the merge, so an auto-merge job already polling (up to 90 minutes) or a `labeled` bot PR merges on the old result first. Assumption: nothing merges between the gate merge and the re-judge.
- Disposition: operator chose "Draft-first (Recommended)".

### Round 3 (`09f5e03`, design: draft-first with a reminder line on any `gate` item)

- **Goal-fit.** Finding: the reminder would fire on about 18% of gate-file PRs but helps only when the items script changes; a `mutation-pr` tightening is never re-judged; V1 and R5 case 2 could pass vacuously. Assumption: the merging operator opens the items log first.
- **Ergonomics.** Finding: nothing records which PRs were drafted, and an agent marking its own draft ready mid-hold re-runs the old gate. Assumption: Renovate leaves an operator-drafted PR as a draft.
- **Risk.** Finding: V1 waited for `HEAD is now at`, which a `ref: master` checkout never prints (verified on run 45877030669); the restore set was unrecorded; pre-push shows the reminder to agents. Assumption: the `reopened` payload of a fresh PR stays stale after a master commit.
- Disposition: operator chose "Keep draft-first, add gate-hold label".

### Round 4 (`57d965d`, scoped risk lens)

- **Risk.** Finding: the items gate omitted `scripts/cosmic_ray_prune.py`, which the script loads with `_load_sibling` and uses in item computation; R5 had a positive case for one path only; a non-draft PR opened during the hold is uncovered. Fixed in `44e4923` (four paths, a `_load_sibling` drift check, a case per path, draft before label, new known limit). Assumption: Renovate does not mark an operator-drafted PR ready during the hold (unmeasured; listed in Known limits).
- Disposition: operator approved 2026-11-27 ("spec approved").

## External Review

### Round 1 (reviewed at `83a0147`)

Report: [round1.md](2026-11-27-items-gate-fresh-base-design.external-review/round1.md)

#### Author response

| finding | disposition | evidence | reviewer verdict | operator (Step 9) |
| ------- | ----------- | -------- | ---------------- | ----------------- |
| F1.1 | Fixed | R6 now keeps only `base.ref` and the agent rule inline, points to ADR-0048 for the hold procedure, and moves the repro clause there; R7 records the repro and the procedure. `wc -c < CLAUDE.md` prints `29996`. | unjudged | approved 2026-11-27 ("spec approved") |
| F1.2 | Fixed | Rejected alternatives gains the auto-merge `gate-hold` guard and why N3 wins; Design item 2 now names the `labeled` run's `cancel-in-progress` as the main hold and draft refusal as the backup (`auto-merge.yml:17`). | unjudged | approved 2026-11-27 ("spec approved") |
| F1.3 | Fixed | Known limits gains the `uses:` pin-bump exemption (`only_uses_bumps`, `scripts/mutation_gate_items.py:1376`, used at 1403) and the floating `stable` toolchain (`mutation-gate-items.yml:49`). | unjudged | approved 2026-11-27 ("spec approved") |
| F1.4 | Fixed | V1 now says that if the reopen refreshed the payload, V1 is recorded as a smoke test. | unjudged | approved 2026-11-27 ("spec approved") |
| F1.5 | Fixed | R5 now derives the set with `ast` and asserts every `_load_sibling` call takes a single string literal. | unjudged | approved 2026-11-27 ("spec approved") |
| F1.6 | Fixed | Rejected alternatives now says 53, with `git rev-list --count 19cdee3..33e09a2`. | unjudged | approved 2026-11-27 ("spec approved") |
| F1.7 | Rebutted | The Round 4 disposition is the operator's to record at Step 9; the assistant never authors a disposition. | unjudged | approved 2026-11-27 ("spec approved") |

Stopped: reviewer recommended stopping in round 1
