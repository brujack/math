---
name: retrospective-2026-06-retrospective
description: Retrospective — 2026-06
metadata:
  type: retrospective
  period: 2026-06
---

# Retrospective — 2026-06

**Period:** 2026-05-17 to 2026-06-01 (15 days)
**Repo(s):** math
**PRs merged:** 19 (PRs #52–#70)
**Direct master commits:** ~31 (docs, CI housekeeping, post-merge cleanups)
**Total commits:** 50

## Summary

A focused 15-day quality/infrastructure sprint. No new CLIs shipped — instead the period was dominated by comprehensive upgrades to test infrastructure (cargo-nextest, Hypothesis, proptest, mutmut, CLI entry-point tests), supply-chain security hardening (SBOM + cosign, pip-audit, defusedxml), static analysis rollout (pyright across all 11 Python sub-projects), and Criterion benchmarks for all 11 Rust crates. All 5 plans that entered the spec phase this period were completed. Five PRs landed on May 23 alone. The repo's quality surface is now substantially wider than it was two weeks ago.

## PRs Merged This Period

| # | Title | Merged |
|---|-------|--------|
| #52 | feat: amicable pairs — Python + Rust CLI with proper-divisor sum sieve | 2026-05-17 |
| #53 | feat: adopt cargo-nextest as test runner | 2026-05-18 |
| #54 | feat: add Python mutation testing with mutmut | 2026-05-18 |
| #55 | test: add Hypothesis and proptest property-based tests | 2026-05-19 |
| #56 | ci: add per-sub-project coverage badges | 2026-05-19 |
| #57 | fix(amicable): correct Hypothesis test oracle in test_pairs_within_limit | 2026-05-19 |
| #58 | fix(perfect-numbers): correct Hypothesis test oracle in test_perfect_numbers_below_limit | 2026-05-20 |
| #59 | feat: flaky-test tracking via nextest CI profile and test-metrics artifacts | 2026-05-20 |
| #60 | feat: SBOM generation and cosign signing for releases | 2026-05-20 |
| #61 | test(cli): add CLI integration tests for collatz and goldbach | 2026-05-21 |
| #62 | feat(factorial): add pyright type checking and fix macOS spawn deadlock | 2026-05-23 |
| #63 | feat(ci): add pyright type checking to all Python sub-projects | 2026-05-23 |
| #64 | feat(ci): upgrade pyright to standard mode for 6 sub-projects | 2026-05-23 |
| #65 | feat(ci): add pip-audit advisory security step to all Python workflows | 2026-05-23 |
| #66 | feat(changelog): add git-cliff config and make target | 2026-05-23 |
| #67 | test: add CLI entry-point integration tests for amicable, collatz, perfect-numbers, factorial | 2026-05-23 |
| #68 | ci: add release workflows for collatz, goldbach, amicable, perfect-numbers | 2026-05-23 |
| #69 | fix(scripts): replace xml.etree with defusedxml in test_metrics.py | 2026-05-23 |
| #70 | feat: add Criterion benchmarks to all 11 Rust crates | 2026-05-24 |

## Themes

**Test infrastructure leap (week 1).** cargo-nextest (#53), Python mutmut mutation testing (#54), Hypothesis/proptest property-based tests (#55), CLI entry-point integration tests (#61, #67), and flaky-test tracking via nextest CI profiles (#59) all landed within 6 days. The test surface went from unit-only to multi-layer: unit → property-based → mutation → CLI integration → flaky-test tracking.

**Security hardening in one push (days 3–4).** SBOM generation + cosign signing for all releases (#60), pip-audit advisory CVE step in all Python workflows (#65), and defusedxml replacing xml.etree in test_metrics.py (#69) all landed within the same 5-day window. These were independent specs but executed as a coherent batch.

**Pyright rollout — all 11 Python sub-projects in a single day.** PRs #62, #63, #64 shipped on May 23 in sequence: factorial first (with a macOS spawn deadlock fix bundled), then all remaining sub-projects, then upgrade of 6 from basic to standard mode. Complete type-checking coverage in ~6 hours of elapsed time.

**Criterion benchmarks for all 11 Rust crates (#70).** Adds a performance regression baseline across the entire Rust surface. Threshold alerts at 130% set in a follow-up commit post-merge.

## Recurring Patterns and Gotchas

**1. Hypothesis oracle circularity (PRs #57, #58).**
Within 24 hours of landing property-based tests (#55), two test oracles needed corrections. The root cause: `test_pairs_within_limit` and `test_perfect_numbers_below_limit` were asserting that `f(N) == expected` where `expected` was computed by calling `f(N)` at a known-good input — a circular oracle that tests internal consistency, not correctness. The fix in both cases was to replace with hard-coded reference values from known mathematical sources. **Pattern to avoid:** never derive the expected value by calling the function under test; derive it from a published table or a reference implementation.

**2. defusedxml in Rust workflow (PR #69).**
`test_metrics.py` was updated to import `defusedxml` (XXE safety, added in #69), but Rust workflows have no Python dependency install step — Python workflows do. The result was `ModuleNotFoundError` in CI for any Rust workflow that calls `test_metrics.py`. Fix documented in CLAUDE.md: any Rust workflow that calls a Python utility script must include an explicit `pip install <deps>` step immediately before. **Pattern:** when adding a new import to a shared Python utility script, immediately audit all callers (not just Python CI workflows).

**3. CI action version drift (multiple commits).**
Two separate commits after PR #70 were needed to bump straggler `upload-artifact@v6→v7` and `checkout@v5→v6` instances. The bump pattern repeats: a new workflow is created, versions are set, then a subsequent audit finds older versions elsewhere. **Pattern:** after any batch of new workflow files, run a single grep across `.github/workflows/` for pinned action versions and normalize in one commit.

**4. Benchmark alerts set post-merge.**
The Criterion regression alert threshold (130%) was set in a follow-up master commit after #70 merged, rather than in the PR itself. Minor friction. **Pattern:** for configuration that should travel with the feature, keep it in the same PR.

**5. Mutation testing workflow required a separate fix.**
`ci(mutation-testing): fix rust-cache error and input injection` was committed to master after the monthly mutation run on 2026-06-01. Two issues: rust-cache configuration error and expression injection in the workflow. The mutation workflow was added to CI in a prior period; these fixes only surfaced on the first actual run.

## Test Health

- **Property-based tests added:** Hypothesis for all 7 Python CLIs; proptest for all 11 Rust crates.
- **CLI entry-point integration tests:** now covering collatz, goldbach, amicable, collatz, perfect-numbers, factorial. (pi, e, fib, sq, prime covered in prior periods.)
- **Mutation testing:** first full run on 2026-06-01. Surviving mutants documented in backlog:
  - amicable-rs: `replace * with + in sieve` (2 mutants) — tests don't assert on operator boundaries
  - factorial-rs: `replace > with >= in compute_swing_chunk` (1 mutant) — off-by-one in prime swing not caught
- **Coverage:** no regressions observed; all Rust crates remain ≥90% (CI gate enforcing).
- **Flaky test tracking:** nextest CI profile + XML artifact now in place for all Rust projects. No flaky tests detected yet — baseline established.

## What Went Well

- **Speed of pyright rollout.** Three PRs, all 11 sub-projects, one day. No regressions. The pattern of doing one project as a proof-of-concept then mass-applying is efficient.
- **Security batch.** SBOM, cosign, pip-audit, and defusedxml landed in a 5-day window as a coherent security posture upgrade, not a slow drip.
- **All 5 tracked plans completed.** test-metrics, sbom-cosign, pip-audit-ci, cli-integration-tests, criterion-benchmarks — all Done.
- **First mutation testing baseline.** Surviving mutants are documented and actionable. The monthly CI run is working.
- **Hypothesis oracle bugs found and fixed same-day.** Quick turnaround demonstrates the review + fix loop is tight.

## What to Improve

- **Hypothesis oracle discipline.** Two oracle fixes within 24 hours of introducing property-based tests is a sign the oracle pattern wasn't established before writing tests. Add a docs/knowledge entry on correct oracle patterns before the next round of property-based test expansion.
- **Shared utility script dependency tracking.** When `test_metrics.py` gained a new import, no checklist prompted a Rust workflow audit. The CLAUDE.md note was added after the break, not before.
- **Features shouldn't require config follow-ups.** The benchmark alert threshold commit and the mutation workflow fix are two examples of "almost complete" PRs. The goal is zero follow-up commits per PR. Pre-push review should check for obvious missing configuration.
- **Action version normalization.** The recurring action version drift is now documented; worth adding a one-liner grep check to the pre-push hook or a periodic make target.

## Actions for Next Period

- [ ] Kill surviving mutants: amicable-rs `*`→`+` in sieve (2 mutants), factorial-rs `>`→`>=` in compute_swing_chunk (1 mutant).
- [ ] Add `mutants` Makefile target to all remaining Rust crates (still outstanding from 2026-05-17 retro).
- [ ] Audit `rustfmt.toml` presence with `use_small_heuristics = "Max"` in all 11 Rust crates (still outstanding from 2026-05-17 retro).
- [ ] Add `docs/knowledge/hypothesis-oracle-patterns.md` capturing correct vs. circular oracle patterns to prevent recurrence.
- [ ] Pyright standard mode for `pi/` and `e/` (in backlog — gmpy2 stubs path or optional-import wrapping required).
- [ ] Consider a new CLI from the backlog (Euler's totient φ, highly composite numbers, or abundant/deficient numbers).

## Metrics

- **PRs merged:** 19 in 15 days (1.27/day — matches the prior period's pace)
- **New CLIs shipped:** 0 (infrastructure period)
- **Plans completed:** 5
- **Test categories added:** property-based (Hypothesis + proptest), mutation (mutmut + cargo-mutants), CLI entry-point integration, flaky-test tracking
- **Python sub-projects with full type checking:** 11/11 (was 0/11 at period start)
- **Rust crates with Criterion benchmarks:** 11/11 (was 0/11 at period start)
- **Releases with SBOM + cosign:** all 11 Rust crates going forward
- **Coverage:** stable at ≥90% all Rust crates, ≥90% all Python CLIs
- **Surviving mutants discovered:** 3 (amicable-rs ×2, factorial-rs ×1)

## Calibration Note

No new CLIs is intentional and correct for this period. The test infrastructure, security posture, and static analysis coverage were all in debt after the prior period's CLI velocity sprint. A 15-day infrastructure push that adds property-based testing, mutation testing, SBOM/cosign, pyright, pip-audit, Criterion benchmarks, and CLI entry-point tests in one coherent sweep is exactly the right counter-weight. The system is more correct and more auditable. Next period is ready for another CLI or two.
