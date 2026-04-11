# docs/superpowers

Design specs and implementation plans for features built with the superpowers workflow.

## Specs

| Date | Feature | File |
|------|---------|------|
| 2026-03-30 | Fibonacci calculator | [specs/2026-03-30-fibonacci-design.md](specs/2026-03-30-fibonacci-design.md) |
| 2026-04-10 | Perfect squares calculator | [specs/2026-04-10-perfect-squares-design.md](specs/2026-04-10-perfect-squares-design.md) |
| 2026-04-11 | Twin primes | [specs/2026-04-11-twin-primes-design.md](specs/2026-04-11-twin-primes-design.md) |

## Plans

| Date | Feature | Status | File |
|------|---------|--------|------|
| 2026-03-30 | Fibonacci calculator | Done | [plans/2026-03-30-fibonacci.md](plans/2026-03-30-fibonacci.md) |
| 2026-04-10 | Perfect squares calculator | Done | [plans/2026-04-10-perfect-squares.md](plans/2026-04-10-perfect-squares.md) |

## Backlog

Ideas approved for future specs, in no particular order:

| Feature | Notes |
|---------|-------|
| ~~Twin primes~~ | Spec written — see Specs table above |
| e (Euler's number) | Compute e to N decimal places; same arbitrary-precision approach as pi |
| Collatz sequences | For each number up to 10^N find chain length; identify longest chain |
| Perfect numbers | Find all perfect numbers up to 10^N; connected to Mersenne primes |
| Factorial | Compute N! to arbitrary precision; extends big-number arithmetic pattern |

## Adding a new entry

When a new spec or plan is created, add a row to the appropriate table above. Set status to **In Progress** when implementation starts, **Done** when the PR merges. Also add a `> **Status: DONE**` banner at the top of the plan file once complete.
