# Amicable Pairs — Design Spec

**Date:** 2026-05-17
**Status:** Approved

---

## Overview

Two distinct positive integers (a, b) are an amicable pair when each equals the sum
of the other's proper divisors: s(a) = b and s(b) = a, where s(n) = σ(n) − n
(sum of all divisors of n except n itself).

Find and print all amicable pairs (a, b) with a < b and b ≤ 10^N, one pair per line,
ascending by a. Write output to stdout and to `amicable_1eN.txt`.

The smallest pair is (220, 284): s(220) = 1+2+4+5+10+11+20+22+44+55+110 = 284,
and s(284) = 1+2+4+71+142 = 220.

---

## Project Structure

```
amicable/
  amicable.py
  test_amicable.py
  Makefile
  install_deps.sh
  README.md
  CLAUDE.md
  amicable-rs/
    src/main.rs
    Cargo.toml
    Cargo.lock
    rustfmt.toml
    Makefile
    install_deps.sh
    CLAUDE.md
```

---

## Algorithm

**Proper-divisor sum sieve** — O(N log N) time, O(N) space.

Build an array `s[0..=limit]` where `s[n]` = sum of proper divisors of n:

1. Initialise `s` to all zeros.
2. For each `d` from 1 to `limit / 2`: add `d` to `s[2d], s[3d], s[4d], …` up to `limit`.

After the sieve, scan for pairs:

- For each `n` from 2 to `limit`:
  - Let `m = s[n]`.
  - If `m > n` and `m <= limit` and `s[m] == n`: output pair `(n, m)`.
  - The `m > n` guard emits each pair exactly once and excludes perfect numbers (where s(n) = n).

This is the same divisor-sieve pattern as in the prime sieve — well-understood,
cache-friendly, and correct by construction. No ADR needed.

Note: the perfect-numbers implementation uses a specialised multiplicative sigma formula
for Mersenne numbers only. This sieve is entirely independent code.

---

## N Range and Limits

| N   | Limit | s[] size (u32) | Python feasible? | Rust feasible? |
| --- | ----- | -------------- | ---------------- | -------------- |
| 1–6 | ≤1M   | ≤4MB           | Yes              | Yes            |
| 7   | 10M   | 40MB           | Yes              | Yes            |
| 8   | 100M  | 400MB          | Marginal (slow)  | Yes            |
| 9   | 1B    | 4GB            | No               | Yes (slow)     |

Valid range: 1–8. Python warns and exits for N > 7. Rust warns but proceeds for N ≤ 9.

u32 is sufficient for the sieve values: the maximum proper-divisor sum for any n ≤ 10^8
is well within 2^32.

---

## CLI Interface

```
python3 amicable.py [N]
./amicable-rs/target/release/amicable N
```

- N is a positive integer specifying the exponent (limit = 10^N).
- If N is omitted (Python only), prompt interactively.
- Output: one `a b` pair per line, a < b, sorted ascending by a, to stdout and file.
- File name: `amicable_1eN.txt` in the current directory.

Example invocations:

```
$ python3 amicable.py 3
220 284

$ python3 amicable.py 4
220 284
1184 1210
2620 2924
5020 5564
6232 6368
```

---

## Test Cases

| Input (N) | Expected output (a b pairs, a < b ≤ 10^N)               |
| --------- | ------------------------------------------------------- |
| 1         | (none — smallest pair has b=284 > 10)                   |
| 2         | (none — smallest pair has b=284 > 100)                  |
| 3         | 220 284                                                 |
| 4         | 220 284 / 1184 1210 / 2620 2924 / 5020 5564 / 6232 6368 |

Boundary / algorithm checks:

- s(220) = 284, s(284) = 220 — confirm pair detection
- s(6) = 6 — perfect number, must NOT appear (excluded by m > n guard)
- s(1) = 0 — must not crash or emit false pair
- N=0 → error (invalid exponent, limit would be 1)
- Non-integer argument → error

---

## Output File

`amicable_1eN.txt` — same convention as other CLIs in this repo.
Written to the current working directory. Each line: `a b` separated by a single space.
