# Worldclass slice 4: Rust mutation survivors in five crates

- **Date:** 2026-11-04
- **Status:** Approved
- **Approved:** 2026-11-04
- **Revised:** 2026-11-04 after Step 8 round 1 (drift test, sixth equivalence class, V2 floor) and round 2 (drift-test triggers and match rule)
- **Scope:** `pi/pi-rs`, `e/e-rs`, `prime/prime-rs`, `twin-primes/twin-primes-rs` and `collatz/collatz-rs`: their `src/`, a new `.cargo/mutants.toml` in each, and each crate's `CLAUDE.md`, a new root test `tests/test_mutants_exclusions.py`, an install step and two `paths:` globs in `.github/workflows/scripts.yml`, and a targeted run in `scripts/pre-push` with its bats coverage

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
No crate source has changed since (`git log -1 --format=%h -- '*/*-rs/src/*'` is `c398814`,
an ancestor of `4a76cb4`), so the line numbers below hold on today's master.

The operator rule is that all crates get the same treatment
(`math-all-crates-treated-identically`), so all five are in scope, not only the three
weakest. Of the six clean crates, four reached 0 with tests plus a `.cargo/mutants.toml`
`exclude_re` list for true equivalents (factorial, amicable, goldbach, perfect-numbers;
written in `59c7736` and `f18f96f` and never re-anchored since), and fib and sq reached 0
with tests alone. None of the five crates here has a `.cargo/mutants.toml`.

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
  positive, non-overlapping and gap-free. For an expression the `_sized` tests run (the
  block bound, the `len / threads` term), the size-parameter tests check that proviso.
  The default constants (`4 * 1024 * 1024`, `BLOCK_SIZE`) move into the public wrappers,
  which those tests never call, so their literal mutants are excluded on the argument
  alone: every mutated value stays positive, and any positive size gives the same
  output.
- **e-rs term count** (`lib.rs:139`, 141, 143, 144; 7 mutants). Each mutated formula
  still gives at least as many Taylor terms as `digits` needs, and more terms cannot
  change correct digits. Measured with the formula reproduced in Python against the
  smallest `n` with `log10(n!) >= digits + 2`, at digits 2, 3, 5, 10, 50, 100, 10^3 to
  10^9: no mutant falls short at any of them. At 10^6 the original gives 205,414 terms
  against 205,023 needed, and the mutants give 326,301 to 1,221,918.
- **`small_sieve` start** (prime-rs `lib.rs:35`, 37; twin-primes-rs `lib.rs:16`, 18).
  Starting the crossing-off at `i + i` instead of `i * i` marks the same composites, the
  same equivalence `factorial-rs` already excludes.
- **Preallocation and short-write retry** (pi-rs `main.rs:95:39`, `129:62`; e-rs
  `main.rs:78:44`, `112:62`; `+` to `-`). `set_len(total)` only preallocates: the later
  `write_at` calls extend the file, so `hdr + digits - ftr` leaves the same bytes
  (checked in a scratch copy; the `*` sibling does change the bytes and the file test
  kills it). The retry offset `base + written` runs with `written = 0` on every first
  call, and `write_at` on a regular file writes the whole chunk, so the retry never
  runs on a fault-free file system. Unlike the other entries this one is not strictly
  equivalent: `base - written` would misplace bytes after a real partial write (ENOSPC,
  a signal). It is unreachable without fault injection, a seam for that is production
  abstraction with no other user, and N5 permits the exclusion; its comment in
  `mutants.toml` says "unreachable without fault injection", not "equivalent".
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

The entries must keep their line numbers: most equivalents share file, operator and
function with mutants that are killed today, so a regex without the line would hide
those. A line-anchored entry goes stale silently when an edit moves its line (11 commits
touched these five crates' `src/` between 2026-05-01 and today). A new root test,
`tests/test_mutants_exclusions.py`, guards that:

- It finds exactly nine `.cargo/mutants.toml` files (the four existing and the five
  new), so a deleted file fails rather than shrinking the set.
- Each file parses to a non-empty `exclude_re` list, so a misspelled key fails.
- `cargo mutants --list --no-config` exits 0 with non-empty output in each crate.
- Each entry, searched unanchored as cargo-mutants does, matches at least one listed
  mutant, and no listed mutant is matched by two entries. "Exactly one" would be wrong:
  `perfect-numbers`' `verify_perfect` entry deliberately matches both
  `-> bool with true` and `-> bool with false`.

Listing writes nothing and fetches nothing: with `CARGO_HOME` pointed at an empty
directory, pi-rs listed its 170 mutants (the table's 118 + 43 + 6 + 3) in 0.05 s and the
directory stayed empty. The test skips with a message naming the remedy when
`cargo-mutants` is absent, and fails instead when `CI=true`.

The test must run on the change that causes drift, which is a crate source edit:

- `scripts.yml` adds `*/*-rs/src/**` and `*/*-rs/.cargo/mutants.toml` to its `paths:`,
  and installs `cargo-mutants@27.1.0` through the pinned `taiki-e/install-action` with
  `fallback: none` (its manifest carries 27.1.0 at the pinned SHA), the version
  `mutation-testing.yml` uses, so `tests/test_tool_pins.py` still sees one version.
- `scripts/pre-push` runs `tests/test_mutants_exclusions.py` alone when a push touches
  either path, the way it already runs `scripts/cli_contract.py` alone, without
  widening the full root `make test` trigger. The pre-push bats suite covers both the
  trigger and its absence.

A per-crate missed-count ratchet (red when a crate's missed count rises above a committed
baseline) would make the 0 last, but it changes the mutation workflow, which N4 keeps out
of this slice. It goes to the Backlog.

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
- **R6.** Tests cover `run` with `digits = 1` (pi-rs, e-rs), `generate_records` at a limit of at least 19 asserting the exact record list (collatz-rs), and a twin-primes segment on which the `idx <= n` mutant indexes past the bitset, shown by a mutation control in which that test fails with the mutant applied.
- **R7.** Each of the five crates has `.cargo/mutants.toml` whose `exclude_re` entries each carry a comment naming the equivalence, and every entry belongs to a class in §Equivalents.
- **R8.** Each crate's `CLAUDE.md` lists the new functions and its test table counts.
- **R9.** `tests/test_mutants_exclusions.py` finds exactly nine `.cargo/mutants.toml` files, each with a non-empty `exclude_re`, requires `cargo mutants --list --no-config` to exit 0 with non-empty output per crate, and asserts each entry matches at least one listed mutant and no mutant is matched by two entries; it skips naming the remedy when `cargo-mutants` is absent outside CI and fails when absent under `CI=true`. `scripts.yml` installs `cargo-mutants@27.1.0` via the pinned `taiki-e/install-action` and triggers on `*/*-rs/src/**` and `*/*-rs/.cargo/mutants.toml`, and `scripts/pre-push` runs the test alone when a push touches either, with bats tests for both branches.
- **V1.** After merge, dispatch `mutation-testing.yml` for each of the five crates and record caught, missed, timeout and unviable per crate beside the run-41769558239 figures; missed is 0 in all five.
- **V2.** Before the PR, `make mutants` in each of the five crates leaves only survivors that the crate's `exclude_re` covers: the run's missed count is 0 and its caught count is above 0.
- **N1.** No change to any algorithm, output file format, printed text, or default chunk, block or segment size.
- **N2.** No change to the six crates already at 0 missed.
- **N3.** No new dependencies.
- **N4.** No change to `mutation-testing.yml`, `scripts/mutation-classify.sh`, the crate `Makefile` `mutants` recipe or `scripts/crate_templates/`.
- **N5.** No `exclude_re` entry for a mutant that a test with input under 10,000 digits, numbers or bytes could kill.

## Amendments

- R7 -> Each of the five crates whose final mutation run leaves a survivor in a §Equivalents class has `.cargo/mutants.toml` whose `exclude_re` entries each carry a comment naming the equivalence, and every entry belongs to a class in §Equivalents; a crate whose survivors are all killed has no `.cargo/mutants.toml`. — collatz-rs's four survivors are all killable, so a mandatory file there would be empty, which R9 forbids.
- R9 -> `tests/test_mutants_exclusions.py` asserts the set of crates with a `.cargo/mutants.toml` equals an expected set written as a literal in the test (the four existing crates plus each slice-4 crate that got one), each file with a non-empty `exclude_re`, requires `cargo mutants --list --no-config` to exit 0 with non-empty output per crate, and asserts each entry matches at least one listed mutant and no mutant is matched by two entries; it skips naming the remedy when `cargo-mutants` is absent outside CI and fails when absent under `CI=true`. `scripts.yml` installs `cargo-mutants@27.1.0` via the pinned `taiki-e/install-action` and triggers on `*/*-rs/src/**` and `*/*-rs/.cargo/mutants.toml`, and `scripts/pre-push` runs the test alone when a push touches either, with bats tests for both branches. — follows the R7 amendment: the expected set is eight or nine crates, and a literal set still fails on a deleted file.
- R7 -> Each of the five crates whose final mutation run leaves a survivor in a §Equivalents class has `.cargo/mutants.toml` whose `exclude_re` entries each carry a comment naming the equivalence, and every entry belongs to a class in §Equivalents, where the twin-primes sieving bound `sqrt(limit) as u64 + 1` counts under the margin class; a crate whose survivors are all killed has no `.cargo/mutants.toml`. — Phase 2 review found the `+ 1` on the sieving bound survives as `* 1` because primes up to floor(sqrt(limit)) already suffice; it is a margin like `digits + 5`, and the operator chose to classify it rather than delete it.
- N1 reviewed: Phase 2 deletes two pieces of dead code instead of excluding their mutants: the twin-primes small-prime pair guard `w[1] < limit` (always true, since small primes stop at sqrt(limit) + 1, below every limit of 5 or more) and the prime-rs post-block parity step `if block_lo.is_multiple_of(2) { block_lo += 1 }` (with an even block size it can fire only after the final block, where the loop ends either way). Neither changes output; tests pin the output at the affected limits. Operator's choice, 2026-11-04.
- finding R3 (2026-11-05, reviewer both): DIFFERS — pi-rs (999_999/1_000_000/1_000_001 and 9_999/10_000/10_001) and collatz-rs (8/9/10) test bound and bound+-1, but e-rs tests shows_preview at 1, 1_000_000 and 1_000_001 and auto_saves at 1, 10_000 and 10_001, so the value below each bound is 1, not bound-1 (999_999 / 9_999); all functions are pure and called from run / prompt_digits_with.
- R3 reviewed: fixed in 99d0b1c — e-rs `test_shows_preview_bounds` and `test_auto_saves_bounds` now also assert 999_999 and 9_999.
- finding N1 (2026-11-05, reviewer A): VIOLATED — Removing a guard from the twin-primes pair loop and the parity step from prime-rs's block loop changes algorithm code, even though the spec's own 'N1 reviewed' amendment line (spec diff line 157) calls both dead code and records it as the operator's choice; the effective N1 in requirements.md does not include that carve-out.
- N1 -> No change to any algorithm, output file format, printed text, or default chunk, block or segment size; deleting code proven unreachable (the twin-primes small-prime pair guard `w[1] < limit` and the prime-rs post-block parity step) is not an algorithm change. — the earlier `N1 reviewed` amendment records the operator's choice to delete both dead paths; this folds that carve-out into N1's text so later runs read it, and bug-scan's 87-case old-versus-new differential found 0 diverging outputs.

## Assumptions

- The twin-primes `idx <= n` mutant panics only on a full segment where `n % 8 == 0`
  and some sieving prime's progression lands on `idx == n`; `n % 8 == 0` alone is not
  enough (first counterexample: limit 21, lo 7, n 8). R6's mutation control is what
  shows the chosen test reaches it.

## Multi-Lens Review

Reviewed at commit: `4c44f34` (spec as first committed, after the Step 7 self-review)

### Goal-Fit

Finding: R1, R2, R6 and R7 change decisions: they put real untested paths under `make test` (the chunk offset runs only above 4 MiB, the prime block step only above 1e8) and keep monthly sweeps honest. R3 to R5 restructure production code to kill mutants in stderr progress text that N1 already freezes and nothing downstream reads. "Missed is 0" has no lasting reader: `scripts/mutation-classify.sh` scores survivors (exit 2) green and the Rust notify fires only on failure, so a crate drifting from 0 to 30 missed goes unnoticed. The 0 is a snapshot, not a ratchet. Kill rates from the table: twin-primes 90% and collatz 89% already pass the repo's 80% bar; prime 78%, pi 73%, e 66% do not. Simpler path: R1, R2, R6, R7 and the equivalents; drop R3 to R5, or add a per-crate missed baseline so the gain lasts. Second finding: the twin-primes Assumption is false as stated. A Python simulation over limits 5 to 2,999 found segments with `n % 8 == 0` where the `idx <= n` mutant does not panic (first: limit 21, lo 7, n 8), because the panic also needs a sieving prime's progression to land on `idx == n`.
Assumption: That the operator wants missed = 0 as a lasting standard rather than a one-time milestone. Settle by answering: should a Rust crate regressing from 0 missed turn the monthly leg red?
Disposition: Accepted, reason: operator keeps R3 to R5 as designed so every crate reaches a true 0; the per-crate missed-count ratchet goes to the Backlog because it changes the workflow N4 excludes. The twin-primes Assumption was rewritten and R6 now requires a mutation control.

### Ergonomics

Finding: Roughly 20 line-anchored `exclude_re` entries across five crates (seven in e-rs `compute_e`, lines 139 to 144) have no drift detection. The line number cannot be dropped: most equivalents share file, operator and function with mutants killed today (for example `replace - with + in bs` has 3 sites per crate, 1 equivalent). Any edit above an excluded line silently orphans the entry, and the equivalent returns as "missed" in the next monthly sweep, weeks later, with no context. Dead entries accumulate because nothing reports an entry that matches nothing. The four existing `mutants.toml` files share the gap at lower cost. Fix within N4: a root `tests/` check running `cargo mutants --list` per crate that asserts each `exclude_re` matches exactly one listed mutant, skipping with a message when cargo-mutants is absent outside CI; covers all nine crates with a `mutants.toml`. Premise correction: only four of the six clean crates have `.cargo/mutants.toml` (factorial, amicable, goldbach, perfect-numbers); fib and sq reached 0 with tests alone.
Assumption: That the five crates stay unedited between the local V2 run and later monthly sweeps. Measured by the orchestrator after the report: 11 commits touched the five crates' `src/` since 2026-05-01 (6 in May, 1 each in July and August, 3 in October), and the existing four `mutants.toml` files were each written once and never re-anchored (`59c7736`, `f18f96f`).
Disposition: Addressed — R9 adds `tests/test_mutants_exclusions.py` over all nine crates with a `mutants.toml`, plus the `scripts.yml` install; the premise sentence now names the four crates that use exclusions.

### Risk

Finding: Four equivalent survivors fit no class in §Equivalents, so V2 is unreachable without breaking R7. pi-rs `main.rs:95:39` and e-rs `main.rs:78:44` (`+` to `-` in the `set_len(total)` preallocation): later `write_at` calls extend the file, so the bytes are identical (probe in a scratch copy: `h+p+f` vs `h+p-f` equal; `h*p+f` differs, so the byte test kills the `*` sibling). pi-rs `main.rs:129:62` and e-rs `main.rs:112:62` (`base + written` to `-` in the short-write retry): `write_at` on a regular file writes the whole chunk, so `written` is 0 whenever the expression runs; only an injected short write reaches it, and a seam for that would be production abstraction whose only job is killing a mutant. Fix: add a sixth class, "preallocation and short-write retry, unobservable on a fault-free file system". Smaller: once §1 moves `4 * 1024 * 1024` into the public wrapper, the `_sized` tests never run that literal, so the partition proviso checks nothing for it (still equivalent); V2 passes on a run that evaluated nothing, so require caught > 0 per crate, as the CI classifier's `caught + missed == 0` red rule does. Cleared: `debug_assert!` on even sizes; default behaviour unchanged; `idx <= n` panics exactly when `n % 8 == 0` with a progression landing on `n` (a full 64-number segment has n = 32); `limit < 5` equivalent at 0, 3, 4, 5; prime block `- to /` stays gap-free and `+ to -` underflows and is caught.
Assumption: That the e-rs term-count mutants never fall short at an unsampled digit count. Settled by the orchestrator after the report: the original formula and all seven mutants (`139:28 > to >=`, `141` ×2, `143` ×3, `144`) swept against the smallest `n` with `log10(n!) >= digits + 2` at every `digits` from 1 to 100,000 plus 8,001 log-spaced points from 10^5 to 10^9 (108,001 points): zero shortfalls for any of them.
Disposition: Addressed — sixth class "Preallocation and short-write retry" added, the partition proviso reworded for the default constants, V2 requires caught > 0, R6 requires a mutation control.

### Round 2 (all three lenses, at `80eb7fd`)

Goal-Fit — Finding: R9 fails the reads-it test on the event it exists for. A crate `src/` edit is what moves an excluded line, and neither consumer fires on one: `scripts.yml` `paths:` lists no `*/*-rs/src/**` or `*/*-rs/.cargo/mutants.toml`, and `scripts/pre-push:180` runs the root suite only for `^scripts/|^tests/|...`. The orphan surfaces in the monthly sweep or as a red on a later unrelated PR, blamed on its author. "Exactly one match per entry" also passes on an empty list, and on a deleted `mutants.toml`. The spec's evidence command `git log -1 -- '*/*-rs/src'` prints nothing (the pathspec needs `src/*`; with it, `c398814`, still older than `4a76cb4`). Assumption: that `cargo mutants --list --no-config` on a cold runner needs no dependency fetch or GMP build. Settled by the orchestrator: with `CARGO_HOME` pointed at an empty directory it listed pi-rs's 170 mutants (118 + 43 + 6 + 3, the table's total) in 0.05 s, exit 0, and the directory stayed empty.
Ergonomics — Finding: the same trigger gap, with the fix scoped: add the two path globs to `scripts.yml`, and in pre-push run only `tests/test_mutants_exclusions.py` when they change, as `scripts/cli_contract.py` already runs alone, without widening the full root trigger. R9 also needs: exactly nine `mutants.toml` files found, each with a non-empty `exclude_re` (a misspelled `exclude-re` key reads as empty), `--list` exiting 0 with non-empty output, and an unanchored search as cargo-mutants does. `cargo install` in `scripts.yml` compiles on every run; the repo's pinned `taiki-e/install-action` with `fallback: none` keeps one version for `test_tool_pins.py` and takes seconds. Assumption: that only R9 can catch a stale entry, since the classifier scores survivors green; R9's trigger paths decide whether the design lasts.
Risk — Finding: R9 as written is red on day one without breaking N2. In a scratch copy of the four existing crates, `perfect-numbers` `src/lib\.rs:44:5: replace verify_perfect` matches 2 listed mutants (`-> bool with true` and `with false`), by design: it is the documented algebraic-identity exclusion. The other 35 existing entries match one each, so none has gone stale yet. Fix: at least one match per entry, plus no listed mutant matched by two entries; assert nine crates found. Also the trigger gap above. The short-write retry entry is unreachable without fault injection rather than equivalent (`base - written` is wrong on a real partial write); N5 permits it, but its comment should say "unreachable without fault injection". Assumption: the cold-runner listing question, settled as above.
Disposition: Addressed — R9 now runs on crate `src/` and `mutants.toml` changes (`scripts.yml` paths, a targeted pre-push run), uses at-least-one with no shared matches, pins nine non-empty files and non-empty listing output, installs through `taiki-e/install-action`; the retry entry's comment says "unreachable without fault injection"; the `git log` pathspec is fixed. Operator chose to stop review here: the round-2 findings sit in test plumbing that Phase 2's first runs exercise.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

## Spec alignment (2026-11-05)

- spec: docs/superpowers/specs/2026-11-04-worldclass-slice4-rust-mutation-survivors-design.md
- anchor: 45f032f6a9b9f651290e377e7023606cffe44a96
- in scope: R1, R2, R3, R4, R5, R6, R7, R8, R9
- out of scope: none

### Findings

| ID | Reviewer | Verdict | Reason | Amendment |
| --- | --- | --- | --- | --- |

### Reviewed

- N1 reviewed: Phase 2 deletes two pieces of dead code instead of excluding their mutants: the twin-primes small-prime pair guard `w[1] < limit` (always true, since small primes stop at sqrt(limit) + 1, below every limit of 5 or more) and the prime-rs post-block parity step `if block_lo.is_multiple_of(2) { block_lo += 1 }` (with an even block size it can fire only after the final block, where the loop ends either way). Neither changes output; tests pin the output at the affected limits. Operator's choice, 2026-11-04.
- R3 reviewed: fixed in 99d0b1c — e-rs `test_shows_preview_bounds` and `test_auto_saves_bounds` now also assert 999_999 and 9_999.

### Verifications

- V1: Met 2026-11-05. Full sweep run 41952665142 at 0d28038 (math#204; attempt 2 reran collatz and fib after a runner shutdown cancelled both): missed 0 in all five; caught/missed/timeout/unviable pi 159/0/4/3, e 122/0/12/3, prime 144/0/12/0, twin-primes 115/0/4/2, collatz 36/0/6/1 (baseline run 41769558239 missed pi 43, e 45, prime 32, twin-primes 12, collatz 4). The first post-merge sweep, run 41948343321 at 821acb1, left one host-dependent survivor each in pi-rs and e-rs on 2-vCPU runners; math#204 fixed both.
- V2: Local CARGO_MUTANTS_JOBS=8 make mutants at the branch: missed 0 in all five; caught pi 159, e 129, prime 149, twin-primes 115, collatz 42 (timeouts 4/6/7/4/0); every exclude_re entry matches exactly one listed mutant.
