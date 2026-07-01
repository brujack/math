# 2026-06 Retrospective — math

**Period:** 2026-06-01 → 2026-06-30
**PRs merged:** 12 (#71–#82)
**Commits:** 47

---

## PRs Merged

| PR | Title | Area |
|----|-------|------|
| #71 | fix(factorial-rs): use mutants.toml exclusions for equivalent mutations | Rust/testing |
| #72 | ci: align math release workflows with etch-cli strategy | CI |
| #73 | fix(ci): strip directory prefix from sha256sum in release workflows | CI |
| #74 | fix(ci): install cargo-machete in factorial-rs workflow | CI |
| #75 | fix(ci): install cargo-machete in all Rust test workflows | CI |
| #76 | feat: adopt 10-80-10 execution cycle (ai-config ADR-0009/0010) | Process |
| #77 | feat(ci): swap mutmut → cosmic-ray for 8 Python sub-projects | Python/testing |
| #78 | refactor(memory): adopt canonical .claude/memory + .claude/retrospectives layout | Docs |
| #79 | chore: remove per-repo memory/retrospective plumbing | Docs |
| #80 | docs(knowledge): pointer stub per ADR-0020 | Docs |
| #81 | ci: add mutation-pr per-PR gate workflow | CI |
| #82 | fix(ci): make cosmic-ray Python mutation check advisory, not a required gate | CI |

Outside PRs (direct commits):
- All 8 Python sub-projects migrated from `unittest` to **pytest** + ruff format check (ADR-0023)
- `cargo-machete` and `ruff C901` added to lint gates
- `ci(benchmarks)`: fail workflow on regression alert
- Language standards (`python.md`, `rust.md`) added to CLAUDE.md

---

## Recurring Patterns and Gotchas

### 1. CI tool additions without install steps (2 PRs to fix)
`cargo-machete` was added to `scripts/rust-check.sh` lint mode but the install step was omitted from CI. PR #74 fixed `factorial-rs.yml` (the one workflow calling `make lint` directly), and #75 fixed the 9 others (which call `make test → make lint` transitively). Root cause: the initial fix assumed only direct `make lint` callers were affected, missing the transitive dependency.

**Lesson:** When adding a tool to `rust-check.sh`, update every Rust workflow in the same commit — not just the ones that obviously call lint.

### 2. New feature introduced with untested behavior (1 PR to fix)
PR #72 added SHA256 checksum generation across all 11 release workflows, but the `sha256sum` invocation embedded the full build-tree path into the `.sha256` file. PR #73 fixed it with a subshell `cd`. The feature was broken on day 1 with no end-to-end test.

**Lesson:** New release workflow steps should be smoke-tested against a test tag before merge, not left to the "next actual release."

### 3. Mutation gate design assumption mismatch (2 PRs to fix)
PR #81 added `mutation-pr.yml` as a required CI gate and assumed `cosmic-ray` could scope mutations to PR diff (like `cargo mutants --in-diff`). It can't — cosmic-ray runs all mutations for a sub-project. Pre-existing surviving mutants immediately blocked every Python PR from auto-merging. PR #82 demoted Python mutation to advisory within 3 days.

**Lesson:** Verify tool capability (diff-scoped vs full-suite) before making a gate required. The `--in-diff` affordance is specific to cargo-mutants. Cosmic-ray is advisory-only until a diff-scoped equivalent exists.

---

## What Went Well

- **Pytest migration landed cleanly.** All 8 Python sub-projects moved from `unittest` to pytest via a consistent pattern of direct commits; ruff format pass applied everywhere. ADR-0023 documents the rationale.
- **Quick fix cycle.** The cargo-machete gap and sha256sum bug were found and fixed within 1–8 days. Auto-merge kept the feedback loop tight.
- **Memory/knowledge consolidation.** The multi-PR sequence (#78 → #79 → #80) completed cleanly — git mv with canonical frontmatter, then removal of now-redundant per-repo plumbing.
- **mutmut → cosmic-ray migration.** Correct call: mutmut fails on Python 3.14; cosmic-ray works. The decision was made proactively (ADR-0022) rather than blocking on a broken CI.
- **10-80-10 cycle adopted** (ADR-0009/0010) — plan validator wired into `make validate-plan`.

## What to Improve

- **Atomic tool-install PRs.** When a new lint/test tool is added to a shared script, the CI install step should be part of the same PR, not a follow-up. Two follow-up PRs for one tool (cargo-machete) was avoidable.
- **Release workflow smoke testing.** The sha256sum path bug would have been caught by a manual dry-run dispatch. No post-merge release has been cut yet — the next release will exercise the new path for the first time.
- **Mutation gate design review before merge.** PR #81's test plan only validated the "no source changes → skip" path. A Python test path would have revealed the full-suite problem before the PR merged.

---

## Action Items for Next Period

1. **Release smoke test:** Trigger at least one release workflow with a test tag to verify git-cliff notes, CHANGELOG commit, and sha256sum end-to-end.
2. **Cosmic-ray kill rate baseline:** Document the per-sub-project surviving-mutant count from the first monthly run so regressions can be detected.
3. **Pytest migration completeness:** Confirm `TestEntryPointGuard` (CLI subprocess tests) exists in all 8 migrated Python sub-projects; add any missing.
4. **cargo-machete false-positive audit:** First month with machete active — check CI logs for false positives (machete can flag deps used only in macros or build scripts).
