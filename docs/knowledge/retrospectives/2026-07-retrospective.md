# 2026-07 Retrospective — math

**Period:** 2026-07-01 → 2026-07-31
**PRs merged:** 7 (#83–#89)
**Commits:** 22

---

## PRs Merged

| PR | Title | Area |
|----|-------|------|
| #83 | test(mutation): kill surviving mutants in goldbach/perfect-numbers/amicable/collatz | Rust/testing |
| #84 | test(mutation): kill surviving mutants in sq, fib, perfect-numbers | Python/testing |
| #85 | chore: scope enabledPlugins per ADR-0046 | Config |
| #86 | fix(amicable-rs): flush BufWriter before returning Ok(()) | Rust/correctness |
| #87 | fix: bump crossbeam-epoch to 0.9.20 (RUSTSEC-2026-0204) | Security |
| #88 | feat(ci): add release SBOM vulnerability monitor | CI/security |
| #89 | fix(ci): use exact-phrase title search in SBOM issue dedup check | CI |

Direct commits (not PRs):
- `docs(mutation)`: add two new equivalent-mutation patterns to CLAUDE.md (Jul 1)
- `docs`: update test count tables for goldbach-rs and perfect-numbers-rs (Jul 1)
- `docs(claude)`: remove content promoted to global standards (Jul 2)
- `docs(backlog)`: add July 2026 retro action items (Jul 3)
- `chore`: gitignore shared cargo target dir for rust checker (Jul 25)
- `docs`: add maintainability-pass backlog row (Jul 24)
- 4× `chore(changelog)`: weekly updates

---

## Recurring Patterns and Gotchas

### 1. New CI feature needs immediate follow-up fix (third consecutive month)

SBOM monitor (#88, Jul 16) had a false-positive dedup bug fixed 3 days later by #89. The `in:title "CVE-ID" "binary"` search found binary names (`e`, `pi`, `sq`, `fib`) as substrings inside every CVE ID string (e.g., "CVE-…E…"), so the dedup check always returned a match — suppressing all future issue creation for those binaries. Fix: require the exact phrase the monitor writes (`"[SBOM Monitor] CVE-ID in binary" in:title`).

This is the same pattern seen in June: sha256sum path bug (#72→#73) and mutation gate full-suite problem (#81→#82). Three months running.

**Lesson:** Any new CI logic that matches on binary names must be tested against `e`, `pi`, `sq`, and `fib` before merge — these are substrings of common English words and identifier segments. Add this to the CI-feature review checklist.

### 2. Mutation testing is an ongoing maintenance burden

Both #83 (4 Rust crates) and #84 (3 Python modules) landed in the first three days of July, directly addressing the June action item. The work involved a mix of:
- Real behavioral gap tests (boundary values, prompt-guard file-name assertions, singular-form output checks)
- Equivalent mutation exclusions documented in `.cargo/mutants.toml` and `cosmic-ray.toml`
- Two new equivalent-mutation patterns added to CLAUDE.md (algebraic-identity dead-code and dead-branch via positive-modulus math)

The mutation backlog is now substantially smaller but not empty — remaining open items for next period.

**Lesson:** Mutation kills require careful triage between genuine gaps (write a test) and mathematical equivalences (document in exclusion files with reasoning). Conflating the two leads to either phantom test coverage or incorrect exclusions.

### 3. Automated bug scan finding correctness gaps

PR #86 (BufWriter flush in amicable-rs) was found by an automated deep-bug-scan routine, not manual review. The omission was present since amicable-rs was first written — `writer.flush()?` before `Ok(())` was in every other Rust CLI (goldbach, fib, prime, twin-primes) but missing here. No data loss risk in practice (BufWriter::drop flushes on success), but flush errors on write were swallowed.

**Lesson:** Automated periodic bug scans are catching cross-crate consistency gaps that human review misses. The pattern check "does every Rust CLI do X that all other Rust CLIs do?" is hard to hold in head but easy to automate.

### 4. Security advisory response remains fast

RUSTSEC-2026-0204 (crossbeam-epoch 0.9.18, invalid pointer dereference in `fmt::Pointer`) was a transitive dep via rayon in all 11 Rust crates. A single PR (#87) bumped all 11 Cargo.locks to 0.9.20 and passed `cargo audit` and `make test` in all 11 crates. One pre-existing allowed advisory (RUSTSEC-2026-0190, anyhow) was left in place with explicit allowance.

---

## Test Health

| Crate / Module | Tests | Notes |
|----------------|-------|-------|
| goldbach-rs | 27 | Up from ~18; prompt-guard file assertion added (#83) |
| perfect-numbers-rs | 27 | Up; boundary + singular-form tests added (#83) |
| collatz-rs | 24 | Prompt-guard file assertion added (#83) |
| amicable-rs | 16 | No new tests; equivalent mutations excluded (#83) |
| sq (Python) | 35 | New boundary + comparison tests (#84) |
| fib (Python) | 39 | New while-bound boundary tests (#84) |
| perfect-numbers (Python) | 45 | New guard variant tests (#84) |

Coverage: no regressions reported; all Rust crates remain above the ≥90% line coverage gate. Cosmic-ray monthly baseline collection is still pending (June action item #2 — see Action Items below).

---

## What Went Well

- **June action items addressed on day 3.** Both Rust (#83) and Python (#84) mutant-killing PRs merged in the first three days of July, directly closing the mutation backlog.
- **Security posture is proactive.** RUSTSEC-2026-0204 patched across all 11 crates in one PR; SBOM vulnerability monitor (#88) now provides monthly re-scanning of published release SBOMs.
- **Automated tooling caught a real bug.** The BufWriter flush omission (#86) was found by automated scan, not manual code review — the scan is earning its keep.
- **Equivalent-mutation documentation is maturing.** CLAUDE.md now documents five named patterns (sieve equivalences, algebraic-identity dead-code, dead-branch via positive modulus, prompt-guard output-filename assertion, per-mutant timeout rationale). New sessions can apply these patterns without re-deriving them.

## What to Improve

- **CI feature smoke-testing for short binary names.** The SBOM dedup bug would have been caught by a manual test with `binary_name=e` before merge. The pre-merge test plan listed "manual reasoning" only — not an actual dispatch run. Short names that are common substrings (`e`, `pi`, `sq`, `fib`) need explicit test coverage in any new CI logic that matches on names.
- **Post-merge workflow_dispatch verification still pending.** PR #88 noted that SBOM monitor can't be fully tested pre-merge (requires a real CVE against a published SBOM). The post-merge dispatch verification was listed as a TODO and has not been done — it's now a July carry-over.
- **Small chore commits going direct to master.** The gitignore and docs commits in the Jul 24–25 window went direct without a PR. This is fine for doc-only changes but worth batching when multiple chores accumulate in one week.

---

## Action Items for Next Period

1. **SBOM monitor end-to-end test:** Trigger `workflow_dispatch` on `release-sbom-monitor-schedule.yml` to verify SBOM download, CVE scan, issue creation, and dedup path all work against at least one published release.
2. **Short-binary-name checklist:** Add "test with `e`, `pi`, `sq`, `fib` binary names" to the CI-feature PR review checklist in CLAUDE.md before the next CI logic PR.
3. **Cosmic-ray baseline:** Run the monthly `mutation-testing-python` workflow and document per-sub-project surviving-mutant counts (was June action item #2 — still open).
4. **Cargo-mutants monthly run:** After #83, confirm via the `mutation-testing` workflow that surviving count in goldbach/perfect-numbers/amicable/collatz dropped to expected level. Document the baseline.
5. **Criterion benchmark evaluation:** Backlog item — evaluate Criterion for Rust sub-projects to enable a perf-regression gate (currently only advisory).
