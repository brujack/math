# Worldclass slice 4: Rust mutation survivors in five crates

- **Date:** 2026-11-04
- **Status:** Draft
- **Scope:** `pi/pi-rs`, `e/e-rs`, `prime/prime-rs`, `twin-primes/twin-primes-rs` and `collatz/collatz-rs`: their `src/`, a new `.cargo/mutants.toml` in each, and each crate's `CLAUDE.md`

## Problem

The first per-crate matrix sweep (`mutation-testing.yml`, run 41769558239, attempt 2,
master `4a76cb4`, artifact `mutants-output`) left 136 missed mutants in five of the 11
Rust crates. The other six crates show 0 missed.

| Crate          | Caught | Missed | Timeout | Unviable |
| -------------- | ------ | ------ | ------- | -------- |
| pi-rs          | 118    | 43     | 6       | 3        |
| e-rs           | 89     | 45     | 11      | 3        |
| prime-rs       | 111    | 32     | 8       | 0        |
| twin-primes-rs | 108    | 12     | 4       | 2        |
| collatz-rs     | 33     | 4      | 3       | 1        |

Population: the five `mutants.out/missed.txt` files in that artifact, 136 lines in total.
No crate source has changed since (`git log -1 -- '*/*-rs/src'` is `c398814`, older than
`4a76cb4`), so the line numbers below hold on today's master.

The operator rule is that all crates get the same treatment
(`math-all-crates-treated-identically`), so all five are in scope, not only the three
weakest. The six clean crates got to 0 with tests plus a `.cargo/mutants.toml`
`exclude_re` list for true equivalents (for example `factorial/factorial-rs`). None of
the five crates here has a `.cargo/mutants.toml`.

### Why they survive

Every missed line was read in source. The survivors fall into five causes.

1. **The input never crosses a hard-coded size.** pi-rs and e-rs write the digit string
   in chunks of at least 4 MiB (`chunk_size = (4 * 1024 * 1024).max(len / threads)`).
   prime-rs sieves phase 2 in `BLOCK_SIZE` (100,000,000) blocks, and twin-primes-rs in
   `SEG_SIZE` (2^19) segments. Every test fits in one chunk, block or segment, so a
   wrong chunk offset (`pi_offset + i * chunk_size`), the step to the next block
   (`block_lo = block_hi + 1`, then `+= 1` when even) or the segment step
   (`lo += SEG_SIZE`) never runs a second time. The file test asserts only
   `contents.contains(PI_REF)`. A mutated header offset therefore still passes, because
   the digit string is still somewhere in the file.
2. **A threshold sits past an input too expensive to test.** The pi-rs and e-rs `run`
   functions warn above 1,000,000 digits, show a preview at or below 1,000,000 and
   auto-save above 10,000. `prompt_digits_with` asks for confirmation above 1,000,000.
   collatz-rs `run` warns above N=9, which means scanning 10^10 numbers. Testing a
   boundary through `run` means computing at that size.
3. **A value is printed only to the process's stderr.** The final "Writing: 100% ...
   MB/s" line (pi-rs, e-rs), the final "Phase 2: 100% ... M/s" line (prime-rs), and the
   values only the 200 ms progress thread reads (prime-rs `phase2_total` and
   `processed`) go to `eprint!`/`eprintln!` directly, and no test captures them.
4. **A pure formatter is under-asserted.** The `format_write_progress` (pi-rs, e-rs) and
   `format_phase2_progress` (prime-rs) tests check the percentage and the presence of
   "MB/s". They never pin a megabyte figure, a speed, or the `elapsed > 0.001` floor.
5. **The mutant is equivalent.** It changes no observable behaviour (list below).

Smaller real gaps: pi-rs/e-rs `run` with `digits = 1` (`d < 1` read as `d <= 1`).
collatz-rs `generate_records` at a limit of 19 or more: 19 and 18 both have chain
length 20, so `>` read as `>=` adds a record. twin-primes-rs `idx < n` read as
`idx <= n` sets a padding bit, or panics when `n % 8 == 0`. The phase-2 start formula
`sqrt_limit + 1 + (sqrt_limit & 1)` (prime-rs, twin-primes-rs) is never tested at a
limit whose square root makes the parity term matter.

### Equivalents

These change nothing a test can observe, and go into `exclude_re` with a reason:

- **`bs` serial/parallel threshold** (pi-rs `lib.rs:45`, e-rs `lib.rs:42`, 2 each).
  Moving `b - a <= BS_PAR_THRESHOLD` changes only whether `rayon::join` runs. Binary
  splitting is exact, so both paths give the same `Pqt`/`Pq`.
- **`digits + 5` precision margin** (pi-rs `lib.rs:106`, e-rs `lib.rs:112`).
  `digits * 5` is at least `digits + 5` for every `digits >= 2`. At `digits = 1` it is
  5 against 6 extra digits, and the mutant survived the existing single-decimal-place
  tests (`test_pi_to_string_single_decimal_place` and its e-rs twin), so the extra digit
  is never needed there.
- **Partition arithmetic.** The chunk-size expression and the block bound
  (`block_lo + BLOCK_SIZE - 1`) choose where pieces split. Any positive partition writes
  the same bytes and finds the same primes, provided the mutant keeps the pieces
  non-overlapping and gap-free. That proviso is checked per mutant against the
  size-parameter tests before an exclusion is written.
- **e-rs term count** (`lib.rs:139`, 141, 143, 144; 7 mutants). Each mutated formula
  still gives at least as many Taylor terms as `digits` needs, and more terms cannot
  change correct digits. Measured with the formula reproduced in Python against the
  smallest `n` with `log10(n!) >= digits + 2`, at digits 2, 3, 5, 10, 50, 100, 10^3 to
  10^9: no mutant falls short at any of them. At 10^6 the original gives 205,414 terms
  against 205,023 needed, and the mutants give 326,301 to 1,221,918.
- **`small_sieve` start** (prime-rs `lib.rs:35`, 37; twin-primes-rs `lib.rs:16`, 18).
  Starting the crossing-off at `i + i` instead of `i * i` marks the same composites, the
  same equivalence `factorial-rs` already excludes.
- **twin-primes-rs `limit < 5`** (`lib.rs:84`, 2 mutants). No pair `(p, p + 2)` with
  `p + 2 < limit` exists below 5 or at 5, so the early return and the full path agree.

The equivalence list is a hypothesis for each entry until a test run confirms it: the
plan writes the tests first, then a fresh `make mutants` per crate shows which survivors
remain, and only those that match an entry above may be excluded.

## Design

### 1. Size parameters

Each worker that splits work by a fixed size takes the size as an argument. The public
entry point keeps its signature and passes the constant.

- pi-rs: `write_pi_file(dir, pi_str, digits)` calls `write_pi_file_sized(dir, pi_str,
digits, min_chunk)` with `4 * 1024 * 1024`. e-rs: `write_e_file` the same.
- prime-rs: `find_primes(limit, out)` calls `find_primes_sized(limit, out, block,
seg)` with `BLOCK_SIZE` and `SEG_SIZE`, and `sieve_segment` takes `seg`.
- twin-primes-rs: `find_twin_primes(limit, out)` calls `find_twin_primes_sized(limit,
out, seg)`, and `sieve_segment` takes `seg`.

`seg` and `block` must stay even (the odd-`lo` invariant depends on it); the `_sized`
functions `debug_assert!` that. Tests call the `_sized` functions with a 7-byte chunk,
or 64-number blocks and segments, so a 1,000-number limit crosses many of them.

### 2. Pure functions

Each value in causes 2 and 3 moves into a small pure function, and the caller uses it:

- Thresholds: `warn_large_digits(d)`, `shows_preview(d)`, `auto_saves(d)` (pi-rs,
  e-rs), shared by `run` and `prompt_digits_with` where both test the same bound;
  `warns_large_n(v)` (collatz-rs).
- Final summary lines: `format_write_done(total_bytes, elapsed)` (pi-rs, e-rs) and
  `format_phase2_done(total, elapsed)` (prime-rs).
- Progress values: `phase2_range(sqrt_limit, limit) -> (start, total)` (prime-rs),
  also used by twin-primes-rs for its start. The block loop's processed count moves
  into the value the loop returns, so a test can assert it equals the range size.

Names are the plan's to finalise; the requirement is that each value is computed by a
function a test can call.

### 3. Exact-value tests

- File tests compare the whole file to `header + digits + footer`, byte for byte, at a
  chunk size that splits the digits into more than three pieces and leaves a remainder.
- Sieve tests compare `find_primes_sized` and `find_twin_primes_sized` output to a
  plain reference sieve (`small_sieve`, or a naive trial-division list in the test) at
  odd and even limits, across more than three blocks or segments, including a limit
  that lands exactly on a block or segment boundary.
- Formatter tests pin exact strings: megabyte and speed figures, the 0.001 s floor
  either side, and zero totals.
- Boundary tests: `digits = 1` in `run`; collatz records up to 19; a twin-primes
  segment whose odd count is a multiple of 8.

### 4. Exclusions

Each crate gets `.cargo/mutants.toml` with an `exclude_re` list in the `factorial-rs`
format: one comment line per entry stating why the mutant is equivalent, and a regex on
`src/<file>.rs:<line>:<col>: <description>`. The list is written last, against the line
numbers of the finished code, and holds only survivors that match a class in
§Equivalents.

### 5. Edits go to source directly

These crates' `src/` files are not rendered from `scripts/crate_templates/`, so the
uniformity test is unaffected; `.cargo/mutants.toml` is per-crate data, as in the six
clean crates.

## Testing

`make test` in each crate, unchanged gates. The new tests run in milliseconds: the
largest input is a few thousand digits or a limit of a few thousand. The nextest
45 s cap and the 90% coverage floor apply as today. A local `make mutants` per crate
(full, not sharded; each crate took 3 to 7 minutes in CI) before the PR shows the
remaining survivors match §Equivalents.

## Requirements

- **R1.** pi-rs and e-rs each have a write function taking the minimum chunk size, and a test writes a digit string split into more than three chunks with a remainder and asserts the file bytes equal header + digits + footer.
- **R2.** prime-rs and twin-primes-rs each have a sieve entry taking the segment size (and, for prime-rs, the block size), and tests compare its output to a reference prime list at odd and even limits spanning more than three segments or blocks, including one limit on a boundary.
- **R3.** The large-digit warning, preview and auto-save thresholds in pi-rs and e-rs, and the N>9 warning in collatz-rs, are pure functions used by `run` (and `prompt_digits_with`), each tested at its bound and one either side.
- **R4.** The final write-speed line (pi-rs, e-rs), the final phase-2 line and the phase-2 start and total (prime-rs) are produced by pure functions with exact-string or exact-value tests.
- **R5.** `format_write_progress` and `format_phase2_progress` tests pin the megabyte figures, the speed, and output at `elapsed` of 0.001 and just above.
- **R6.** Tests cover `run` with `digits = 1` (pi-rs, e-rs), `generate_records` at a limit of at least 19 asserting the exact record list (collatz-rs), and a twin-primes segment whose odd count is a multiple of 8.
- **R7.** Each of the five crates has `.cargo/mutants.toml` whose `exclude_re` entries each carry a comment naming the equivalence, and every entry belongs to a class in §Equivalents.
- **R8.** Each crate's `CLAUDE.md` lists the new functions and its test table counts.
- **V1.** After merge, dispatch `mutation-testing.yml` for each of the five crates and record caught, missed, timeout and unviable per crate beside the run-41769558239 figures; missed is 0 in all five.
- **V2.** Before the PR, `make mutants` in each of the five crates leaves only survivors that the crate's `exclude_re` covers, and the run's missed count is 0.
- **N1.** No change to any algorithm, output file format, printed text, or default chunk, block or segment size.
- **N2.** No change to the six crates already at 0 missed.
- **N3.** No new dependencies.
- **N4.** No change to `mutation-testing.yml`, the crate `Makefile` `mutants` recipe or `scripts/crate_templates/`.
- **N5.** No `exclude_re` entry for a mutant that a test with input under 10,000 digits, numbers or bytes could kill.

## Assumptions

- A twin-primes segment with `n % 8 == 0` makes `idx <= n` index past the bitset and
  panic, which a test catches; at other sizes it sets a padding bit that is never read
  and is equivalent. The test must use the panicking size.
