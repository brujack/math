# CLAUDE.md budget: one line per rule, and a byte ceiling that stops regrowth

- **Approved:** 2026-10-19, operator: "approved for both" (revision 2)

**Status:** Draft, revision 2, 2026-10-19. Method (terraform_ansible#229 / dotfiles#347) chosen
by the operator; round-1 review findings recorded below.

## Problem

Measured 2026-10-19 with `claude -p "/context"` in the math main checkout on `claude` at
`4fe381a`: session start 65.7k tokens, of which the root `CLAUDE.md` (60,297 bytes) is 21.9k.
Its bulk is reference text: `## CI` 14,718 bytes, `### Bash Coverage` 7,132, `### Mutation
testing (Rust)` 4,797, `## Dependency Installation` 3,445, `## Keeping CLAUDE.md Up To Date`
3,375. 16 commits touched it in 60 days; 5 of them went direct to master, so CI never saw them
and pre-push is their only gate. The other PRs auto-merge: `auto-merge.yml` has no `paths:`
filter and merges human PRs on green (math#142 changed only `CLAUDE.md` and was merged by
`app/github-actions`).

**Dry run (V1, done):** a whole-file one-line-per-rule draft came to **20,735 bytes** (161
lines, 90 rule lines, 61 pointers). CI 24,885 to 6,742; Testing Policy 11,436 to 4,484; Quick
Reference 8,163 to 2,661. The math session's keep-list (Design 6) adds about 2 KB. The draft
templated the per-sub-project command blocks; round-1 review verified the template holds for
all 8 Python sub-projects (`<p>/<n>.py`, `test_<n>.py`, a `run:` target) and all 11 crates (a
`<p>:` Makefile target).

Sub-project `CLAUDE.md` files load only under their directory; out of scope.

## Design

1. **One line per rule**, detail moved byte-identical under a unique `###` heading in
   `ai-config/docs/knowledge/math-*.md` on ai-config master, kept line ending with
   `→ ai-config/docs/knowledge/math-<topic>.md § <heading>`. ai-config `validate_knowledge.py`
   rules apply.
2. **Live-state lines keep their variable, override or command** (ai-config ADR-0077 rule 5).
3. **Blocks the PR does not change stay byte-identical.**
4. **A byte ceiling: `scripts/claude_md_budget.py <rev>`, 30,000 bytes**, about 30% above the
   dry run plus Design 6 (about 22.7 KB). Python, because math's root suite is
   `python3 -m unittest discover -s tests` and a new `scripts/*.sh` would join the
   bash-coverage floor's denominator. Same contract as terraform_ansible's checker: reads only
   `git show <rev>:CLAUDE.md`, absence via `git ls-tree --full-tree`, exit 1 naming size,
   ceiling and remedy (pointer, or amend `docs/adr/0028-claude-md-size-ceiling.md`), 0 within
   or absent, 2 on git failure; no flag, environment variable or trailer changes it.
5. **Enforcement where `CLAUDE.md` changes, on every PR and every push.**
   - `scripts/pre-push`: inside its existing `while read` ref loop, for each ref with a
     non-zero local SHA, decide whether the push changes `CLAUDE.md` with
     `git diff --quiet <base> <local_sha> -- CLAUDE.md` (exit 1 = changed, ≥2 = failure;
     statuses read explicitly), where `<base>` is `merge-base(local_sha, origin/master)` with
     the hook's existing `rev-list --max-parents=0` fallback, so orphan pushes behave as today
     and a rebase onto master does not count as this branch's change. If the diff itself fails,
     refuse. If it changes, run the checker from the pushed commit (skip with a message when
     that commit has no checker; refuse when reading it fails; subshell `pipefail`). Exit 1
     after the loop, before `RUN_HOOK_TESTS` and sub-project dispatch and before any early
     `exit 0`, when any check failed.
   - `auto-merge.yml` (no `paths:` filter, runs on every PR): a new `claude-md-budget` job,
     added to the auto-merge job's `needs:`, checks out with `fetch-depth: 0`, runs the checker
     with `shell: bash` (statuses read explicitly), prints its output, fails when the PR changes
     `CLAUDE.md` and the checker exits 1, warns (`::warning::`) when it does not and master is
     over, fails on exit 2. `tests/test_automerge_bot_hold.py` (which extracts a step from this
     file) stays green.
   - Hooks are symlinks (`make install-hooks` runs `ln -sf ../../scripts/pre-push`), so the
     running hook is the main checkout's working tree: after merge, the main checkout on each
     machine that pushes math must be at or past the merge commit (V6).
   - Changing `scripts/` makes pre-push run root `make test`; expected cost.
6. **Session-start rules named by the math session stay as full one-line rules**, never
   pointer-only:
   - Release: the "Create and push tag" step stays after sbom-sign; never a separate signing
     job; every `softprops/action-gh-release` has `fail_on_unmatched_files: true`; release
     builds use `cargo auditable build --release`; `tests/test_release_workflows.py` pins all
     three.
   - Release workflow shape (core.md ci-020): `workflow_dispatch` with `version` (no `v`), tag
     `{subproject}-v{version}`, Node 24, `actions/checkout@v7`, Rust builds `needs: [test]`,
     `actions/upload-artifact@v7` 7 days.
   - Auto-merge lands a PR when checks pass, so Phase 3 runs before ready-for-review; own
     changes use a draft PR.
   - Never commit generated output (`pi_*_digits.txt`, `primes_1e*.txt` and similar); remove
     `.cache/` (rust-check.sh `CARGO_HOME`) before commits.
   - Mutation testing: never put a fixed `--timeout` back (#95); keep `ulimit -v` 8 GiB and
     `MUTANTS_UNCAPPED=1` on macOS; timeout flags live in each crate's Makefile.
   - The two `# noqa: C901` in `e/e.py` and `pi/pi.py` are load-bearing.
   - One root `ruff.toml` only; deleting a sub-project `pyrightconfig.json` falls through to
     the root config.
   - `renovate.json` `packageRules` begin with the 5 canonical preset rules.
   - A Rust workflow calling `test_metrics.py` needs `pip install defusedxml`.
   - pre-push runs tests on `.py`/`.rs` source changes only; run `make test < /dev/null`;
     resolve the repo root with `rev-parse --show-toplevel`; math's hooks bypass root `test:`.
   - Read `python.md` / `rust.md` before `.py` / `.rs` / their config edits.
   - Worktrees go in `.worktrees/`; run `make validate-plan` before dispatch.
   - The DoD additions and the coverage floors (90 Python and Rust per sub-project).
7. **Templating** of per-sub-project command blocks is allowed: verified to hold for every
   sub-project (Problem).
8. **Stale references retargeted:** `tests/scripts/makefile.bats:96`,
   `tests/test_root_pyright_scope.py:10` and `scripts/run-bash-coverage.sh:85` point at the
   knowledge headings instead of `CLAUDE.md` sections.
9. **`AGENTS.md` keeps parity** (its line 39 requires it): line 7's "Top-level `CLAUDE.md` is
   exhaustive and authoritative" is reworded to say `CLAUDE.md` holds one line per rule with
   detail behind pointers to ai-config knowledge files.
10. **Relocation checked mechanically** (one-off script): every removed block appears
    byte-identical in the knowledge files on ai-config `origin/master`; every pointer resolves
    to exactly one `###` heading; the counts are non-zero and equal the diff's removed blocks
    and pointer lines.
11. **The convention is stated in `CLAUDE.md`** (one line, naming the ceiling and ADR-0028).
12. **ADR-0028** records the ceiling, amendment rule, review-held trust model and convention.
13. **The PR opens as a draft** and is marked ready after V2 and V5.

## Alternatives rejected

- **A bash checker.** It would enter the bash-coverage floor denominator.
- **The checker in `scripts.yml` (revision 1).** That workflow is `paths:`-filtered, so a
  `CLAUDE.md`-only PR, which `auto-merge.yml` merges on green anyway, would go unchecked.
- **Real-git hook tests in `tests/scripts/pre_push.bats`.** Its `setup()` puts a `git` mock on
  `PATH` whose `diff` ignores pathspecs and always succeeds, so new cases would pass
  vacuously; they go in their own file (R8).
- **Whole-tree enforcement.** An over-ceiling master would block every push.

## Multi-Lens Review (round 1, combined goal-fit/ergonomics/risk, spec c4b505f)

| #   | Finding                                                                                                                     | Disposition                                                                                        |
| --- | --------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| 1   | High: `auto-merge.yml` already merges `CLAUDE.md`-only PRs on every PR, so the `scripts.yml` placement left them unchecked. | Addressed: checker job in `auto-merge.yml`'s `needs:` (Design 5, R7).                              |
| 2   | Medium: `AGENTS.md` requires parity and calls `CLAUDE.md` exhaustive.                                                       | Addressed: Design 9, R12, N3.                                                                      |
| 3   | Medium: hooks are symlinks; install and `cmp` were vacuous.                                                                 | Addressed: V6 checks the main checkout includes the merge.                                         |
| 4   | Medium: `pre_push.bats` mocks git; new cases would be vacuous; the existing merge-base test can no longer fail.             | Addressed: separate `pre_push_budget.bats`, `git diff --quiet` form, tightened existing test (R8). |
| 5   | Low: refusing on merge-base failure replaces the orphan fallback.                                                           | Addressed: the existing fallback is reused; only a failed diff refuses.                            |
| 6   | Low: V3 could not fail; V4 passes on empty counts; V7 passes on any PR.                                                     | Addressed: V3, V4, V7 tightened.                                                                   |

## Requirements

- **R1.** `[PR1]` math root `CLAUDE.md` is at most 30,000 bytes.
- **R2.** `[PR1]` Every block of `CLAUDE.md` at the PR's base that the PR changes has its full text, byte-identical, under a unique `###` heading in an `ai-config/docs/knowledge/math-*.md` file on ai-config master, and each replacing line that dropped detail ends with a pointer to that heading.
- **R3.** `[PR1]` A block the PR does not change is byte-identical to the base.
- **R4.** `[PR1]` Every kept line for a command or action whose failing path touches live state contains the variable, override or command from the original text.
- **R5.** `[PR1]` `scripts/claude_md_budget.py <rev>` exits 1 and prints the size, the 30,000-byte ceiling and a remedy naming `docs/adr/0028-claude-md-size-ceiling.md` when `CLAUDE.md` at `<rev>` exceeds it, exits 0 when within, exits 0 when `<rev>`'s tree has no `CLAUDE.md`, exits 2 when git cannot resolve `<rev>` or read its tree, and gives the same result from a subdirectory.
- **R6.** `[PR1]` `scripts/pre-push`, inside its existing ref loop, decides for each ref with a non-zero local SHA whether the push changes `CLAUDE.md` with `git diff --quiet` against `merge-base(local_sha, origin/master)` (falling back to the root commit as the hook already does), refusing when the diff fails; for a changing ref, skips with a message when the pushed commit has no checker, refuses when reading it fails, runs it under subshell `pipefail`; and exits 1 after the loop, before any test dispatch or early `exit 0`, when any check failed.
- **R7.** `[PR1]` `.github/workflows/auto-merge.yml` has a `claude-md-budget` job in the auto-merge job's `needs:` that runs the checker with `shell: bash` against the PR base, prints its output, fails when the PR changes `CLAUDE.md` and the checker exits 1, emits a `::warning::` when it does not and master is over, and fails when the diff or checker exits 2; `tests/test_automerge_bot_hold.py` passes.
- **R8.** `[PR1]` `tests/test_claude_md_budget.py` covers 30,001 bytes refused, 30,000 allowed, absent allowed, unresolvable revision exit 2, size, ceiling and remedy in output, run from a subdirectory; a new `tests/scripts/pre_push_budget.bats`, using real git (`GIT_*` unset) and a stub `make` only, covers a `CLAUDE.md`-only push over refused, a compliant one allowed with evidence the checker ran, a push not changing `CLAUDE.md` onto an over-ceiling base allowed without running it, a rebased branch without its own change allowed, a commit without the checker skipped with the message, a read failure refused, a failed diff refused, an orphan-branch push behaving as before, and a two-ref push with the second over refused; the existing `tests/scripts/pre_push.bats` passes, and its merge-base test asserts the existing range use specifically.
- **R9.** `[PR1]` ADR-0028 records the 30,000-byte ceiling, that raising it needs an ADR amendment, that the ceiling is held by review because the checker runs from the pushed commit, and the convention; `docs/adr/README.md` lists it.
- **R10.** `[PR1]` `CLAUDE.md` has one line stating the convention and the ceiling with ADR-0028.
- **R11.** `[PR1]` Each Design 6 rule is a full one-line rule in `CLAUDE.md`, not pointer-only.
- **R12.** `[PR1]` The three Design 8 comment references point at the knowledge headings, and `AGENTS.md` line 7 no longer calls `CLAUDE.md` exhaustive.
- **V1.** Done: whole-file dry run 20,735 bytes.
- **V2.** An independent reviewer records kept, pointer-only, weakened, missing or wrong for every rule of every changed block; none missing or wrong at merge; the pointer-only list goes in the PR body.
- **V3.** `claude -p "/context"` in the math main checkout on `claude` after merge shows `CLAUDE.md` loaded, at or under the R1 size, recorded with the 21.9k before figure.
- **V4.** The Design 10 relocation check passes with non-zero counts matching the diff; output in the PR body.
- **V5.** The operator reads the compressed `CLAUDE.md` and the pointer-only list and approves before the PR is marked ready.
- **V6.** After merge, on `claude`, `workstation` and `studio`, `git -C ~/git-repos/personal/math merge-base --is-ancestor <merge-sha> HEAD` succeeds in the main checkout, which is on master.
- **V7.** The PR's CI log for the `claude-md-budget` job shows the "PR changes `CLAUDE.md`" branch and the checker's size line.
- **N1.** No rule removed: every rule of every changed block is a kept line or pointer-only with its text in the knowledge file.
- **N2.** The checker has no trailer, environment variable or flag that skips or raises its ceiling.
- **N3.** No edit to any sub-project directory, release workflow, or file other than `CLAUDE.md`, `AGENTS.md`, `scripts/pre-push`, `scripts/claude_md_budget.py`, `tests/test_claude_md_budget.py`, `tests/scripts/pre_push.bats`, `tests/scripts/pre_push_budget.bats`, `.github/workflows/auto-merge.yml`, the three Design 8 comment lines, the new ADR, `docs/adr/README.md` and `docs/superpowers/`.
- **N4.** No change to ai-config scripts or `core.md`.
