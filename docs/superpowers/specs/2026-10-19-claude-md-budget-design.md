# CLAUDE.md budget: one line per rule, and a byte ceiling that stops regrowth

**Status:** Draft, 2026-10-19. Method (terraform_ansible#229 / dotfiles#347) chosen by the
operator; spec review pending.

## Problem

Measured 2026-10-19 with `claude -p "/context"` in the math main checkout on `claude` at
`4fe381a`: session start 65.7k tokens, of which the root `CLAUDE.md` (60,297 bytes) is 21.9k.
Its bulk is reference text: `## CI` 14,718 bytes, `### Bash Coverage` 7,132, `### Mutation
testing (Rust)` 4,797, `## Dependency Installation` 3,445, `## Keeping CLAUDE.md Up To Date`
3,375. 16 commits touched it in 60 days.

**Dry run (V1, done):** a whole-file one-line-per-rule draft came to **20,735 bytes** (161
lines, 90 rule lines, 61 pointers). CI 24,885 to 6,742 (release, atomic-publication, hook,
bash-coverage and Renovate rules stay); Testing Policy 11,436 to 4,484; Quick Reference 8,163
to 2,661. Population: one draft, written before the math session's keep-list (Design 6), about
2 KB more. The draft templated the per-sub-project command blocks (`<project>`, `<name>`); that
is lossless only if every sub-project follows the pattern, so Design 7 forbids it unless
verified.

Sub-project `CLAUDE.md` files (`fib/`, `e/` and so on) load only under their directory; out of
scope.

## Design

1. **One line per rule**, detail moved byte-identical under a unique `###` heading in
   `ai-config/docs/knowledge/math-*.md` on ai-config master, kept line ending with
   `→ ai-config/docs/knowledge/math-<topic>.md § <heading>`. ai-config `validate_knowledge.py`
   rules apply.
2. **Live-state lines keep their variable, override or command** (ai-config ADR-0077 rule 5).
3. **Blocks the PR does not change stay byte-identical.**
4. **A byte ceiling: `scripts/claude_md_budget.py <rev>`, 30,000 bytes**, about 30% above the
   dry run plus the Design 6 additions. Python, because math's root suite is
   `python3 -m unittest discover -s tests` and a new `scripts/*.sh` would join the
   bash-coverage floor's denominator (math session). Same contract as terraform_ansible's
   checker: reads only `git show <rev>:CLAUDE.md`, absence via `git ls-tree --full-tree`, exit 1
   naming size, ceiling and remedy (pointer, or amend ADR-0028), 0 within or absent, 2 on git
   failure; no flag, environment variable or trailer changes it.
5. **Enforcement where `CLAUDE.md` changes.**
   - `scripts/pre-push`: inside its existing `while read` ref loop, for each ref with a
     non-zero local SHA, decide whether the push changes `CLAUDE.md` against
     `merge-base(local_sha, origin/master)` (refuse when that cannot be determined); if it does,
     run the checker from the pushed commit (skip with a message when that commit has no
     checker; refuse when reading it fails; subshell `pipefail`). Exit 1 after the loop if any
     check failed, before the `RUN_HOOK_TESTS` and sub-project test dispatch and before any
     early `exit 0`.
   - `scripts.yml` (`paths:`-filtered; `CLAUDE.md` is not added): a step with `shell: bash` and
     the PR base fetched fails when the PR changes `CLAUDE.md` and the checker exits 1, warns
     (`::warning::`) when it does not and master is over, fails on exit 2. A `CLAUDE.md`-only PR
     runs no `scripts.yml` and is checked by pre-push only.
   - `CLAUDE.md` is not eligible for `--no-verify` (if any text grants that).
   - Hooks are installed by copy: after merge, `make install-hooks` from the main checkout on
     `claude`, `workstation` and `studio`, with a `cmp` check.
   - Changing `scripts/` makes pre-push run root `make test` (lint-hooks, bats, test-python);
     expected cost.
6. **Session-start rules named by the math session stay as full one-line rules**, never
   pointer-only:
   - Release: the "Create and push tag" step stays after sbom-sign (a tag before a signing
     failure leaves an unshippable version and a re-run fails "tag already exists"); never a
     separate signing job; every `softprops/action-gh-release` has `fail_on_unmatched_files:
true`; release builds use `cargo auditable build --release`; `tests/test_release_workflows.py`
     pins all three.
   - Release workflow shape (core.md ci-020): `workflow_dispatch` with `version` (no `v`), tag
     `{subproject}-v{version}`, Node 24, `actions/checkout@v7`, Rust builds `needs: [test]`,
     `actions/upload-artifact@v7` 7 days.
   - Auto-merge lands a PR when checks pass, so Phase 3 runs before ready-for-review; own
     changes use a draft PR.
   - Never commit generated output (`pi_*_digits.txt`, `primes_1e*.txt` and similar); remove
     `.cache/` (rust-check.sh `CARGO_HOME`) before commits.
   - Mutation testing: never put a fixed `--timeout` back (it caps the baseline, #95); keep
     `ulimit -v` 8 GiB and `MUTANTS_UNCAPPED=1` on macOS; timeout flags live in each crate's
     Makefile.
   - The two `# noqa: C901` in `e/e.py` and `pi/pi.py` are load-bearing.
   - One root `ruff.toml` only; deleting a sub-project `pyrightconfig.json` falls through to
     the root config.
   - `renovate.json` `packageRules` begin with the 5 canonical preset rules
     (`renovate_preset_sync.py:87` prefix equality).
   - A Rust workflow calling `test_metrics.py` needs `pip install defusedxml`.
   - pre-push runs tests on `.py`/`.rs` source changes only (macOS resource_tracker hang fix);
     run `make test < /dev/null`; resolve the repo root with `rev-parse --show-toplevel`, never
     git-common-dir; math's hooks bypass root `test:` (core.md code-standards-003).
   - Read `python.md` / `rust.md` before `.py` / `.rs` / their config edits.
   - Worktrees go in `.worktrees/`; run `make validate-plan` before dispatch.
   - The DoD additions (Rust coverage ≥90% from the CI log; BATS failure-mode tests; plan
     index; README CLI table) and the coverage floors (90 Python and Rust per sub-project).
7. **No lossy templating:** per-sub-project command blocks may become one templated block only
   where every sub-project's target and test-file names follow the template (verified
   per sub-project in the plan); otherwise the per-project facts move behind a pointer.
8. **Stale references retargeted:** `tests/scripts/makefile.bats:96`,
   `tests/test_root_pyright_scope.py:10` and `scripts/run-bash-coverage.sh:85` cite `CLAUDE.md`
   sections in comments; they point at the knowledge headings instead.
9. **Relocation checked mechanically** (one-off script): every removed block appears
   byte-identical in the knowledge files on ai-config `origin/master`; every pointer resolves to
   exactly one `###` heading.
10. **The convention is stated in `CLAUDE.md`** (one line, naming the ceiling and ADR-0028).
11. **ADR-0028** records the ceiling, amendment rule, review-held trust model and convention.
12. **The PR opens as a draft** and is marked ready after V2 and V5.

## Alternatives rejected

- **A bash checker.** It would enter the bash-coverage floor denominator; Python matches the
  root unittest suite.
- **Adding `CLAUDE.md` to `scripts.yml` paths.** A `CLAUDE.md`-only PR would then auto-merge
  on green, removing human review of rule edits (terraform_ansible spec, round 1).
- **Whole-tree enforcement.** An over-ceiling master would block every push.

## Requirements

- **R1.** `[PR1]` math root `CLAUDE.md` is at most 30,000 bytes.
- **R2.** `[PR1]` Every block of `CLAUDE.md` at the PR's base that the PR changes has its full text, byte-identical, under a unique `###` heading in an `ai-config/docs/knowledge/math-*.md` file on ai-config master, and each replacing line that dropped detail ends with a pointer to that heading.
- **R3.** `[PR1]` A block the PR does not change is byte-identical to the base.
- **R4.** `[PR1]` Every kept line for a command or action whose failing path touches live state contains the variable, override or command from the original text.
- **R5.** `[PR1]` `scripts/claude_md_budget.py <rev>` exits 1 and prints the size, the 30,000-byte ceiling and a remedy naming ADR-0028 when `CLAUDE.md` at `<rev>` exceeds it, exits 0 when within, exits 0 when `<rev>`'s tree has no `CLAUDE.md`, exits 2 when git cannot resolve `<rev>` or read its tree, and gives the same result from a subdirectory.
- **R6.** `[PR1]` `scripts/pre-push`, inside its existing ref loop, decides for each ref with a non-zero local SHA whether the push changes `CLAUDE.md` against `merge-base(local_sha, origin/master)`, refusing when that cannot be determined; for a changing ref, skips with a message when the pushed commit has no checker, refuses when reading it fails, runs it under subshell `pipefail`; and exits 1 after the loop, before any test dispatch or early `exit 0`, when any check failed.
- **R7.** `[PR1]` `.github/workflows/scripts.yml` runs the checker with `shell: bash` against the fetched PR base, fails when the PR changes `CLAUDE.md` and the checker exits 1, emits a `::warning::` when it does not and master is over, fails when the diff or checker exits 2, and `paths:` does not list `CLAUDE.md`.
- **R8.** `[PR1]` `tests/test_claude_md_budget.py` covers 30,001 bytes refused, 30,000 allowed, absent allowed, unresolvable revision exit 2, size, ceiling and remedy in output, run from a subdirectory; `tests/scripts/pre_push.bats` covers, with real git fixtures (`GIT_*` unset): a `CLAUDE.md`-only push over refused, a compliant one allowed with evidence the checker ran, a push not changing `CLAUDE.md` onto an over-ceiling base allowed without running it, a rebased branch without its own change allowed, a commit without the checker skipped with the message, a read failure refused, an undeterminable change test refused, a two-ref push with the second over refused, and the existing suite unchanged.
- **R9.** `[PR1]` ADR-0028 records the 30,000-byte ceiling, that raising it needs an ADR amendment, that the ceiling is held by review because the checker runs from the pushed commit, and the convention; `docs/adr/README.md` lists it.
- **R10.** `[PR1]` `CLAUDE.md` has one line stating the convention and the ceiling with ADR-0028.
- **R11.** `[PR1]` Each Design 6 rule is a full one-line rule in `CLAUDE.md`, not pointer-only.
- **R12.** `[PR1]` The three comment references in Design 8 point at the knowledge headings, not `CLAUDE.md` sections.
- **V1.** Done: whole-file dry run 20,735 bytes.
- **V2.** An independent reviewer records kept, pointer-only, weakened, missing or wrong for every rule of every changed block; none missing or wrong at merge; the pointer-only list goes in the PR body.
- **V3.** `claude -p "/context"` in the math main checkout on `claude` after merge shows `CLAUDE.md` at 13k tokens or less, recorded with the 21.9k before figure.
- **V4.** The Design 9 relocation check passes on the final diff; output in the PR body.
- **V5.** The operator reads the compressed `CLAUDE.md` and the pointer-only list and approves before the PR is marked ready.
- **V6.** After merge, `make install-hooks` from the main checkout on `claude`, `workstation` and `studio`, with `cmp` of the installed pre-push against `scripts/pre-push`.
- **V7.** The PR's CI log shows the checker step ran.
- **N1.** No rule removed: every rule of every changed block is a kept line or pointer-only with its text in the knowledge file.
- **N2.** The checker has no trailer, environment variable or flag that skips or raises its ceiling.
- **N3.** No edit to any sub-project directory, release workflow, or file other than `CLAUDE.md`, `scripts/pre-push`, `scripts/claude_md_budget.py`, `tests/test_claude_md_budget.py`, `tests/scripts/pre_push.bats`, `.github/workflows/scripts.yml`, the three Design 8 comment lines, the new ADR, `docs/adr/README.md` and `docs/superpowers/`.
- **N4.** No change to ai-config scripts or `core.md`.
