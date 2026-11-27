Tools: Read, Bash, SubagentHandback

The core of the design is right, and I would not change it. Checking out `base.ref` and passing `git rev-parse HEAD` as BASE makes the script and BASE the same commit, which removes window 1 outright. I checked the premise in the code: `run()` diffs from `merge_base(base, head)` at scripts/mutation_gate_items.py:1551, so BASE only selects which script runs. Draft-first is also the right hold. GitHub's merge path refuses drafts, so it stops every merge actor at once: the auto-merge job, Renovate's own `automerge: true` / `automergeType: pr`, and the operator's own `gh pr merge`. Leave both alone. What is left is one problem that will block the plan, one alternative that should be recorded, and some cleanup.

### F1.1 R6 cannot be met as written: root CLAUDE.md has 4 bytes of headroom

- **Defect.** R6 adds three facts to the `mutation-gate-items.yml` line: it runs from `base.ref`, the `gate-hold` procedure, and the agent never-ready rule. It also requires the file to stay at or under 30,000 bytes. The file is already almost full.
- **Failure.** Those three facts need roughly 250 bytes. The pre-push hook and the `claude-md-budget` CI job both refuse the result. The plan will find this on its first green-to-red run and then have to choose what to cut in the middle of implementation.
- **Measurement.** `wc -c < CLAUDE.md` at 83a0147 prints `29996`. Ubuntu 26.04 clone, coreutils wc.
- **Fix.** Add to R6 the text that moves out to make room. A candidate is the line's `repro scripts/mutation-gate-items.sh <base> <head>` clause, or the procedure detail, which can go behind the ADR-0048 pointer. Keep only the agent rule inline, because it is the one fact an agent needs before it reads any file.

### F1.2 Record one guard in the auto-merge job as the rejected mechanical alternative

- **Defect.** Three things in the spec depend on no one making a mistake:
  - the agent rule (check `gh pr list --label gate-hold` before running `gh pr ready`);
  - Known limit 5 (a non-draft PR opened during the hold);
  - Known limit 6 (Renovate un-drafting a PR).

  The `gh pr ready` an agent runs comes from the cross-repo `finishing-a-development-branch` skill, so the rule sits in a different file from the action it governs.
- **Simpler route the spec never weighs.** The auto-merge job's existing `hold` step could set `merge=false` whenever `gh pr list --label gate-hold` is non-empty, and go red if that query fails. That one check covers all three cases. It does not replace drafting, which is still needed to re-trigger the re-judge.
- **Trade-offs.**
  - It touches `auto-merge.yml`, which N3 forbids.
  - The restore order would flip: remove every label first, then ready each PR.
  - An agent's PR readied mid-hold would be held green and need a manual re-ready afterwards. It fails closed, not open.
- **Fix.** I am not asking for a switch. Add a Rejected-alternatives bullet that names this guard and why N3 wins.
- **Related point.** Adding `gate-hold` fires a `labeled` auto-merge run. That run cancels an in-flight polling job through `cancel-in-progress` (auto-merge.yml lines 15-17). So the hold is stronger than the spec says: the claim that `gh pr merge` refuses a draft is the backup, not the main mechanism. That sentence should say so.

### Smaller items

- **F1.3 Pin bumps escape the procedure.** Design item 2 says an items-gate change "reaches master only through a PR whose items check is red". That is false for `uses:` pin bumps to `mutation-gate-items.yml`. `_workflow_item` returns `None` when `only_uses_bumps` holds (scripts/mutation_gate_items.py:1392-1404). So a Renovate bump of `taiki-e/install-action`, `actions/setup-python` or `dtolnay/rust-toolchain` changes the items gate's runtime with no red check, no reminder and no hold. Separately, `dtolnay/rust-toolchain` installs floating `stable`, so `cargo mutants --list` can change with no repo change at all. Add a Known-limits line for both.
- **F1.4 V1 may not prove what it is meant to.** V1 records the API `base.sha`. The thing that matters is the `reopened` payload's base, and the run log never prints it. If a reopen refreshes the payload, V1 passes without showing that `base.ref` was needed; the checkout equals master's tip either way. The spec already accepts "inconclusive" for the API case. Extend that to this case, or accept V1 as a smoke test and say so.
- **F1.5 The drift test can miss a call.** The R5 drift test derives the items-gate set from `_load_sibling("<name>")` call text. A call with a non-literal argument would slip past. Assert with `ast` that every `_load_sibling` call takes a string literal.
- **F1.6 Commit count disagrees.** Rejected alternatives says "#238 saw 56 master commits". The Problem table and R7 say 53. Measured: `git rev-list --count 19cdee3..33e09a2` prints `53`, and 33e09a2 was master's tip before the 19:03:22Z reopen. Use 53, or say what population 56 counts.
- **F1.7 Round 4 Disposition is blank.** The `Disposition:` line under Multi-Lens Review Round 4 is empty.

Process note: one grep in my run expanded `~/.claude` against the real home directory instead of the scratch HOME. I used nothing from that output in these findings.

There is no previous Author response table, so there are no accepted or not-accepted lines.

F1.1 must be fixed before the plan, and F1.2 should be recorded. The rest can be fixed in the same edit or left for the first red test. Rounds 1-4 moved the design; this round found nothing against it, only budget, wording and test apparatus. Another round would cost more than it finds.

Recommend: stop
