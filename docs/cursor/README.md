# Cursor Specs and Plans

Master status index for Cursor-oriented specs and plans in this repository.

The Claude + Superpowers workflow remains primary; `docs/superpowers/README.md` is the full historical index.
This file mirrors the active plan/spec history for Cursor sessions.

## Status Key

| Status      | Meaning                          |
| ----------- | -------------------------------- |
| Done        | Implemented and merged to master |
| In Progress | Currently being implemented      |
| Pending     | Not yet started                  |

---

## All Plans

| Date       | Plan                                                                                              | Spec                                                                                                     | Status  |
| ---------- | ------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------- |
| 2026-03-30 | [fibonacci](../superpowers/plans/2026-03-30-fibonacci.md)                                         | [spec](../superpowers/specs/2026-03-30-fibonacci-design.md)                                              | Done    |
| 2026-04-10 | [perfect-squares](../superpowers/plans/2026-04-10-perfect-squares.md)                             | [spec](../superpowers/specs/2026-04-10-perfect-squares-design.md)                                        | Done    |
| 2026-04-11 | [twin-primes](../superpowers/plans/2026-04-11-twin-primes.md)                                     | [spec](../superpowers/specs/2026-04-11-twin-primes-design.md)                                            | Done    |
| 2026-04-21 | [github-releases](../superpowers/plans/2026-04-21-github-releases.md)                             | [spec](../superpowers/specs/2026-04-21-github-releases-design.md)                                        | Done    |
| 2026-04-23 | [euler-number](../superpowers/plans/2026-04-23-euler-number.md)                                   | [spec](../superpowers/specs/2026-04-23-euler-number-design.md)                                           | Done    |
| 2026-04-24 | [factorial](../superpowers/plans/2026-04-24-factorial.md)                                         | [spec](../superpowers/specs/2026-04-24-factorial-design.md)                                              | Done    |
| 2026-04-29 | [rust-offline-dependency-robustness](plans/2026-04-29-rust-offline-dependency-robustness.md)      | [rust-offline-dependency-robustness](specs/2026-04-29-rust-offline-dependency-robustness-design.md)      | Done    |
| 2026-05-05 | [parallel-fallback-consistency](../superpowers/plans/2026-05-05-parallel-fallback-consistency.md) | [parallel-fallback-consistency](../superpowers/specs/2026-05-05-parallel-fallback-consistency-design.md) | Done    |
| 2026-05-05 | [hook-worktree-hardening](../superpowers/plans/2026-05-05-hook-worktree-hardening.md)             | [hook-worktree-hardening](../superpowers/specs/2026-05-05-hook-worktree-hardening-design.md)             | Pending |

---

## Backlog

Ideas approved for future specs, in no particular order:

| Feature                                   | Notes                                                                                                     |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Collatz sequences                         | For each number up to 10^N find chain length; identify longest chain                                      |
| Perfect numbers                           | Find all perfect numbers up to 10^N; connected to Mersenne primes                                         |
| Failure-mode test matrix for compute CLIs | Add explicit environment-failure tests (semaphores, permissions, missing deps) and expected degradations. |
| Auto-merge gate integrity                 | Define must-pass vs advisory checks so bugfix PRs cannot merge on partial green.                          |

---

## Adding a new entry

When a new Cursor spec or plan is created, add a row to the All Plans table.
Set status to **In Progress** when implementation starts and **Done** when the work merges.
Keep backlog entries at the bottom of this file.
