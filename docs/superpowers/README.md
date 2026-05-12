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

| Date       | Plan                                                                               | Spec                                                             | Status  |
| ---------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------- |
| 2026-03-30 | [fibonacci](plans/2026-03-30-fibonacci.md)                                         | [spec](specs/2026-03-30-fibonacci-design.md)                     | Done    |
| 2026-04-10 | [perfect-squares](plans/2026-04-10-perfect-squares.md)                             | [spec](specs/2026-04-10-perfect-squares-design.md)               | Done    |
| 2026-04-11 | [twin-primes](plans/2026-04-11-twin-primes.md)                                     | [spec](specs/2026-04-11-twin-primes-design.md)                   | Done    |
| 2026-04-21 | [github-releases](plans/2026-04-21-github-releases.md)                             | [spec](specs/2026-04-21-github-releases-design.md)               | Done    |
| 2026-04-23 | [euler-number](plans/2026-04-23-euler-number.md)                                   | [spec](specs/2026-04-23-euler-number-design.md)                  | Done    |
| 2026-04-24 | [factorial](plans/2026-04-24-factorial.md)                                         | [spec](specs/2026-04-24-factorial-design.md)                     | Done    |
| 2026-05-05 | [parallel-fallback-consistency](plans/2026-05-05-parallel-fallback-consistency.md) | [spec](specs/2026-05-05-parallel-fallback-consistency-design.md) | Done    |
| 2026-05-05 | [hook-worktree-hardening](plans/2026-05-05-hook-worktree-hardening.md)             | [spec](specs/2026-05-05-hook-worktree-hardening-design.md)       | Done    |
| 2026-05-06 | [auto-merge-gate-integrity](plans/2026-05-06-auto-merge-gate-integrity.md)         | [spec](specs/2026-05-06-auto-merge-gate-integrity-design.md)     | Done    |
| 2026-05-09 | [failure-mode-test-matrix](plans/2026-05-09-failure-mode-test-matrix.md)           | [spec](specs/2026-05-09-failure-mode-test-matrix-design.md)      | Done    |
| 2026-05-11 | [perfect-numbers](plans/2026-05-11-perfect-numbers.md)                             | [spec](specs/2026-05-11-perfect-numbers-design.md)               | Done    |
| 2026-05-12 | [collatz](plans/2026-05-12-collatz.md)                                             | [spec](specs/2026-05-12-collatz-design.md)                       | Done    |
| 2026-05-12 | [goldbach](plans/2026-05-12-goldbach.md)                                           | [spec](specs/2026-05-12-goldbach-design.md)                      | Pending |

---

## Backlog

Ideas approved for future specs, in no particular order:

| Feature                    | Notes                                                                                                      |
| -------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Euler's totient (φ)        | Compute φ(n) for all n up to 10^N via sieve; sum of totients grows as 3N²/π²                               |
| Highly composite numbers   | Numbers with more divisors than any smaller integer; same record-setter pattern as Collatz; only ~96 known |
| Amicable pairs             | Pairs (a,b) where σ(a)=b and σ(b)=a; sigma function already implemented in perfect-numbers                 |
| Abundant/deficient numbers | For every n up to 10^N classify as abundant/perfect/deficient; output counts and examples                  |
| Happy numbers              | Iterate sum of squared digits; find all happy numbers up to 10^N; simple algorithm, rich structure         |

---

## Adding a new entry

When a new spec or plan is created, add a row to the All Plans table. Set status to **In Progress** when implementation starts, **Done** when the PR merges. Also add a `> **Status: DONE**` banner at the top of the plan file once complete. Move backlog items to the All Plans table when their spec is written (remove the strikethrough pattern — just delete the backlog row).
