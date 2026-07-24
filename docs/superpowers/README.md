# Superpowers Specs and Plans

Master status index for all specs and implementation plans in this directory.

## Status Key

| Status      | Meaning                          |
| ----------- | -------------------------------- |
| Done        | Implemented and merged to master |
| In Progress | Currently being implemented      |
| Pending     | Not yet started                  |

---

## All Plans

| Date       | Plan                                                                               | Spec                                                                                                                              | Status |
| ---------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 2026-03-30 | [fibonacci](plans/2026-03-30-fibonacci.md)                                         | [spec](specs/2026-03-30-fibonacci-design.md)                                                                                      | Done   |
| 2026-04-10 | [perfect-squares](plans/2026-04-10-perfect-squares.md)                             | [spec](specs/2026-04-10-perfect-squares-design.md)                                                                                | Done   |
| 2026-04-11 | [twin-primes](plans/2026-04-11-twin-primes.md)                                     | [spec](specs/2026-04-11-twin-primes-design.md)                                                                                    | Done   |
| 2026-04-21 | [github-releases](plans/2026-04-21-github-releases.md)                             | [spec](specs/2026-04-21-github-releases-design.md)                                                                                | Done   |
| 2026-04-23 | [euler-number](plans/2026-04-23-euler-number.md)                                   | [spec](specs/2026-04-23-euler-number-design.md)                                                                                   | Done   |
| 2026-04-24 | [factorial](plans/2026-04-24-factorial.md)                                         | [spec](specs/2026-04-24-factorial-design.md)                                                                                      | Done   |
| 2026-05-05 | [parallel-fallback-consistency](plans/2026-05-05-parallel-fallback-consistency.md) | [spec](specs/2026-05-05-parallel-fallback-consistency-design.md)                                                                  | Done   |
| 2026-05-05 | [hook-worktree-hardening](plans/2026-05-05-hook-worktree-hardening.md)             | [spec](specs/2026-05-05-hook-worktree-hardening-design.md)                                                                        | Done   |
| 2026-05-06 | [auto-merge-gate-integrity](plans/2026-05-06-auto-merge-gate-integrity.md)         | [spec](specs/2026-05-06-auto-merge-gate-integrity-design.md)                                                                      | Done   |
| 2026-05-09 | [failure-mode-test-matrix](plans/2026-05-09-failure-mode-test-matrix.md)           | [spec](specs/2026-05-09-failure-mode-test-matrix-design.md)                                                                       | Done   |
| 2026-05-11 | [perfect-numbers](plans/2026-05-11-perfect-numbers.md)                             | [spec](specs/2026-05-11-perfect-numbers-design.md)                                                                                | Done   |
| 2026-05-12 | [collatz](plans/2026-05-12-collatz.md)                                             | [spec](specs/2026-05-12-collatz-design.md)                                                                                        | Done   |
| 2026-05-12 | [goldbach](plans/2026-05-12-goldbach.md)                                           | [spec](specs/2026-05-12-goldbach-design.md)                                                                                       | Done   |
| 2026-05-17 | [amicable-pairs](plans/2026-05-17-amicable-pairs.md)                               | [spec](specs/2026-05-17-amicable-pairs-design.md)                                                                                 | Done   |
| 2026-05-19 | [test-metrics](plans/2026-05-19-test-metrics.md)                                   | [spec](https://github.com/brujack/ai-config/blob/master/docs/superpowers/specs/2026-05-19-flaky-test-tracking-design.md)          | Done   |
| 2026-05-20 | [sbom-cosign](plans/2026-05-20-sbom-cosign.md)                                     | [spec](https://github.com/brujack/ai-config/blob/master/docs/superpowers/specs/2026-05-20-sbom-cosign-design.md)                  | Done   |
| 2026-05-23 | [pip-audit-ci](plans/2026-05-23-pip-audit-ci.md)                                   | [spec](specs/2026-05-23-pip-audit-ci-design.md)                                                                                   | Done   |
| 2026-05-23 | [cli-integration-tests](plans/2026-05-23-cli-integration-tests.md)                 | [spec](specs/2026-05-23-cli-integration-tests-design.md)                                                                          | Done   |
| 2026-05-23 | [criterion-benchmarks](plans/2026-05-23-criterion-benchmarks.md)                   | [spec](https://github.com/brujack/ai-config/blob/master/docs/superpowers/specs/2026-05-23-criterion-benchmarks-design.md)         | Done   |
| 2026-07-03 | [python-mutant-killing](plans/2026-07-03-python-mutant-killing.md)                 | [spec](specs/2026-07-03-python-mutant-killing-design.md)                                                                          | Done   |
| 2026-07-16 | [release-sbom-monitor](plans/2026-07-16-release-sbom-monitor.md)                   | [spec](https://github.com/brujack/ai-config/blob/master/docs/superpowers/specs/2026-07-16-release-sbom-vuln-monitoring-design.md) | Done   |

---

## Backlog

Ideas approved for future specs, in no particular order:

| Feature                            | Notes                                                                                                                                                                                                 |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pyright standard mode for pi and e | Currently basic mode with gmpy2 suppressions; upgrade requires either gmpy2 type stubs or tighter optional-import wrapping so reportAttributeAccessIssue/reportOptionalMemberAccess can be re-enabled |
| Euler's totient (φ)                | Compute φ(n) for all n up to 10^N via sieve; sum of totients grows as 3N²/π²                                                                                                                          |
| Highly composite numbers           | Numbers with more divisors than any smaller integer; same record-setter pattern as Collatz; only ~96 known                                                                                            |
| Abundant/deficient numbers         | For every n up to 10^N classify as abundant/perfect/deficient; output counts and examples                                                                                                             |
| Happy numbers                      | Iterate sum of squared digits; find all happy numbers up to 10^N; simple algorithm, rich structure                                                                                                    |
| Kani formal verification           | Prove correctness properties on pure math functions (Goldbach, primality, Collatz); exhaustive proof rather than sampling; AWS uses on crypto libs                                                    |
| Cargo workspace                    | Unify 11 standalone crates into a workspace; shared `Cargo.lock`, faster CI build cache (shared target dir), atomic cross-crate refactors                                                             |
| `cargo deny` license policy        | Add license allowlist (`MIT`, `Apache-2.0`, `BSD-2-Clause`) to catch GPL-contaminating transitive deps before they enter a release; advisory scanning already covers CVEs                             |
| Snapshot testing (`insta`)         | Lock Rust CLI stdout format with `insta`; any unexpected output change becomes a visible diff rather than a silent regression                                                                         |
| Mutation score threshold           | Move `cargo mutants` from monthly advisory to a CI gate with a minimum score; currently collects data without enforcing a floor                                                                       |
| Maintainability pass               | Once the ai-config maintainability gate (2026-07-24 spec) ships, run a worldclass pass in this repo against its thresholds — not scheduled yet.                                                       |

---

## Adding a new entry

When a new spec or plan is created, add a row to the All Plans table. Set status to **In Progress** when implementation starts, **Done** when the PR merges. Also add a `> **Status: DONE**` banner at the top of the plan file once complete. Move backlog items to the All Plans table when their spec is written (remove the strikethrough pattern — just delete the backlog row).
