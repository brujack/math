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

| Date       | Plan                                                   | Spec                                                             | Status  |
| ---------- | ------------------------------------------------------ | ---------------------------------------------------------------- | ------- |
| 2026-03-30 | [fibonacci](plans/2026-03-30-fibonacci.md)             | [spec](specs/2026-03-30-fibonacci-design.md)                     | Done    |
| 2026-04-10 | [perfect-squares](plans/2026-04-10-perfect-squares.md) | [spec](specs/2026-04-10-perfect-squares-design.md)               | Done    |
| 2026-04-11 | [twin-primes](plans/2026-04-11-twin-primes.md)         | [spec](specs/2026-04-11-twin-primes-design.md)                   | Done    |
| 2026-04-21 | [github-releases](plans/2026-04-21-github-releases.md) | [spec](specs/2026-04-21-github-releases-design.md)               | Done    |
| 2026-04-23 | [euler-number](plans/2026-04-23-euler-number.md)       | [spec](specs/2026-04-23-euler-number-design.md)                  | Done    |
| 2026-04-24 | [factorial](plans/2026-04-24-factorial.md)             | [spec](specs/2026-04-24-factorial-design.md)                     | Done    |
| 2026-05-05 | —                                                      | [spec](specs/2026-05-05-parallel-fallback-consistency-design.md) | Pending |

---

## Backlog

Ideas approved for future specs, in no particular order:

| Feature           | Notes                                                                |
| ----------------- | -------------------------------------------------------------------- |
| Collatz sequences | For each number up to 10^N find chain length; identify longest chain |
| Perfect numbers   | Find all perfect numbers up to 10^N; connected to Mersenne primes    |

---

## Adding a new entry

When a new spec or plan is created, add a row to the All Plans table. Set status to **In Progress** when implementation starts, **Done** when the PR merges. Also add a `> **Status: DONE**` banner at the top of the plan file once complete. Move backlog items to the All Plans table when their spec is written (remove the strikethrough pattern — just delete the backlog row).
