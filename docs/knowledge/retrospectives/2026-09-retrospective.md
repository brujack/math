# 2026-09 Retrospective — math

**Period:** 2026-09-01 → 2026-09-30
**PRs merged:** 9 (#125–#133)
**Commits:** 50

---

## PRs Merged

| PR | Title | Area | Author |
|----|-------|------|--------|
| #125 | feat(ci): attest mutation-run progress with a breadcrumb | CI/mutation | brujack |
| #126 | chore(deps): update orhun/git-cliff-action digest to 3d96a18 | Deps | renovate[bot] |
| #127 | fix(mutants): scale the mutant timeout, stop capping the baseline | CI/mutation | brujack |
| #128 | fix(notify): per-workflow issue labels and per-call mock isolation | CI/notify | brujack |
| #129 | chore(deps): update dtolnay/rust-toolchain digest to 6bed076 | Deps | renovate[bot] |
| #130 | feat(ci): sign releases before publishing them | CI/security | brujack |
| #131 | feat(types): declare and type-check root-scope Python | Python/types | brujack |
| #132 | chore(deps): update rust crate clap to v4.6.7 | Deps | renovate[bot] |
| #133 | chore(deps): update orhun/git-cliff-action digest to a9a9552 | Deps | renovate[bot] |

Direct commits (not PRs):
- `docs(backlog)`: model-generation-audit findings (two rounds), 19 shell files unreachable from push path, SBOM-monitor backlog correction, stale cargo install pinning re-measurement
- `docs`: CLAUDE.md double-tilde standards includes fix, `make install-deps` README documentation
- `docs(specs/plans)`: multi-commit series for root-scope Python gate holes spec (#131 implementation), atomic release publication spec (#130 implementation)
- `chore(changelog)`: 2× weekly updates (2026-09-04, 2026-09-11)

---

## Recurring Patterns and Gotchas

### 1. Mutation testing stabilization fully converged (after 5 months)

The mutation CI work that started in June (wrong baseline-timeout diagnosis) and dominated August (#91–#97) closed out in September with two final PRs:
- **#125** added a `marker/job-began` breadcrumb so the notify job can distinguish runner death (SIGTERM/OOM) from a baseline failure — without reading the Actions API (which would require extra permissions).
- **#127** replaced the fixed `--timeout 30` with `--timeout-multiplier 5 --minimum-test-timeout 30`. The key finding: `cargo mutants --timeout` caps **all** cargo commands including the unmutated baseline — pi-rs and e-rs have baselines of 54s+, so a 30s cap aborted before testing a single mutant for 6 months. The 30s floor is load-bearing because the multiplier alone would drop fast crates below their budget.

Root-cause discipline paid off: the first diagnosis was wrong (blamed job timeout + infinite-loop mutations rather than the OOM), but persistence to a second diagnosis found the real cause.

### 2. Release publication window eliminated — sign-before-publish pattern

**#130** moved signing inside the release job (composite action `.github/actions/sbom-sign`) rather than a downstream reusable workflow job. The prior design required `gh release download` in a separate signing job, which meant a window where the release existed but had no SBOM. Three invariants now tested in `tests/test_release_workflows.py`:
1. Build with `cargo auditable build --release` (otherwise `syft` reports only 1 package — the binary — vs. 13 linked crates)
2. Sign via `.github/actions/sbom-sign` **before** the release tag is created (signing failure leaves repo unchanged)
3. `fail_on_unmatched_files: true` on `softprops/action-gh-release` (default is false; missing SBOM/checksum would silently publish)

### 3. Root-scope Python type-check gap: 6 of 8 files were invisible

**#131** found that `scripts.yml` ran pyright in `working-directory: scripts` against a config whose `include` named only `time_tests.py` and `test_metrics.py`. The remaining 6 root-scope tracked `.py` files (including `tests/test_release_workflows.py`) were never type-checked. Fix: a root `pyrightconfig.json` in `standard` mode with `include: ["scripts", "tests", ".claude/scripts"]` and `exclude` without `**/.*` (load-bearing — pyright's default exclude drops `.claude/scripts` entirely). Measured denominator: 10 files after fix vs. 2 before.

### 4. Spec-to-code ratio highest of any month

September had 30+ `docs` commits against ~6 `feat`/`fix` code commits. Three specs each went through multiple review rounds before a PR landed:
- SBOM/dead-ruleset spec: 10 commits, 3 review rounds
- Root-scope Python gate spec: 7 commits, redesign after multi-lens review
- Mutation notify mock/label spec: 5 commits

The multi-lens spec review process produces more accurate specs before implementation starts, but the overhead is significant when all three active specs are in flight simultaneously.

### 5. Renovate auto-merge policy working as designed

Four Renovate PRs auto-merged in September without intervention (#126, #129, #132, #133), all carrying the `automerge-ok` label from the digest-update rule established in #123. This is the first month the policy ran fully. The `test_renovate_automerge_policy.py` assertion remains green across both auto-merged and held PRs.

---

## Test Health

- **Root test count:** 93 tests (as of 2026-09-05, per CLAUDE.md) — unchanged from August; no new test files
- **New gate:** `tests/test_release_workflows.py` (added by #130) asserts atomic release invariants across all `release-*-rs.yml` workflows using `yaml.safe_load` — structure-aware, not raw text
- **Type coverage:** Root-scope pyright now covers 10/10 tracked `.py` files (was 2/8 before #131)
- **No flaky tests surfaced** this period; mutation-testing monthly run scheduled for 2026-10-01

---

## What Went Well

- **Mutation stabilization fully closed**: a 5-month investigation (June diagnosis → August OOM fix → September timeout-multiplier fix) converged, with the breadcrumb/notify improvements landing in the same week
- **Fast first-week cadence**: #125, #126, #127, #128, #129, #130, #131 all merged within the first 5 days of September
- **Release security hardened**: sign-before-publish eliminates a class of race condition that existed since the SBOM feature was added; tests prevent regression
- **Renovate automation running cleanly**: digest updates flowing through without manual intervention

## What to Improve

- **Backlog growing faster than it's being resolved**: September added 4 new backlog items (model-generation-audit findings ×2, 19 unreachable shell files, stale cargo install pinning re-measurement) and closed none. The cumulative backlog is now the largest it has been.
- **Multi-round spec overhead**: three specs in simultaneous review created high document churn. Consider serializing active specs when each requires multiple rounds, to reduce context-switching overhead and duplicate-wording corrections.
- **19 shell files unreachable from push path**: `docs(backlog)` commit recorded this; the pre-push hook only covers `.py`/`.rs` source changes — changes to the 19 `install_deps.sh` and hook scripts escape local testing. Backlogged but not scheduled.
- **Pyright pinned only in `scripts.yml`**: 8 `*-py.yml` workflows still install pyright unpinned (backlog row from August). No regression yet but a future upstream break would hit CI before local.

---

## Action Items for October

- [ ] Schedule and resolve at least one backlog item (suggested: 19 unreachable shell files — adds push-path coverage for install scripts)
- [ ] Verify the October monthly mutation run passes (first run with the corrected timeout-multiplier config for all 11 crates)
- [ ] Consider serializing the active spec queue to reduce multi-round spec overhead
- [ ] Track pyright pin backlog row — add a timeline or acceptance criterion to `docs/superpowers/README.md`
