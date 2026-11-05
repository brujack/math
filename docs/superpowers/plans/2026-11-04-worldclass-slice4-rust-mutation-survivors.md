# Worldclass Slice 4: Rust Mutation Survivors Implementation Plan

> **Status: DONE** (math#203, 821acb1)

spec: docs/superpowers/specs/2026-11-04-worldclass-slice4-rust-mutation-survivors-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring pi-rs, e-rs, prime-rs, twin-primes-rs and collatz-rs to 0 missed mutants with tests for real gaps, line-anchored `exclude_re` for proven equivalents, and a drift test that runs on the edit that moves an excluded line.

**Architecture:** Each crate task adds size parameters, pure functions and exact-value tests in that crate only (tests live in each crate's `src/main.rs` `mod tests`). One task then runs `make mutants` per crate and writes `.cargo/mutants.toml` from what survives. A last task adds `tests/test_mutants_exclusions.py`, its CI install and triggers, and a targeted pre-push run.

**Tech Stack:** Rust 2024 (rug/GMP for pi and e, rayon), cargo-mutants 27.1.0, Python `unittest`, bats.

## Global Constraints

- No change to any algorithm, output file format, printed text, or default chunk, block or segment size (N1).
- No change to factorial, amicable, goldbach, perfect-numbers, fib or sq (N2). No new dependencies (N3).
- No change to `mutation-testing.yml`, `scripts/mutation-classify.sh`, the crate `Makefile` `mutants` recipe or `scripts/crate_templates/` (N4).
- No `exclude_re` entry for a mutant a test with input under 10,000 digits, numbers or bytes could kill (N5).
- Equivalence classes allowed in `exclude_re`: `bs` serial/parallel threshold; `digits + 5` margin; partition arithmetic (incl. default size constants); e-rs term count; `small_sieve` start; preallocation and short-write retry (comment: "unreachable without fault injection"); twin-primes `limit < 5`.
- Root `CLAUDE.md` stays at or under 30,000 bytes (currently 29,998).
- Mutation runs: `CARGO_MUTANTS_JOBS=8 make mutants` inside the crate directory; output lands in the gitignored `<crate>/mutants.out/`.

## Verification

- Session-level: after Task 6, for each crate, `mutants.out/missed.txt` is empty and `mutants.out/caught.txt` is non-empty (V2). After Task 7, root `make test` passes and `python3 -m unittest tests.test_mutants_exclusions -v` reports every crate in its expected set checked.
- Edge cases: a twin-primes segment where `idx <= n` panics (Task 4 mutation control); the perfect-numbers double match (Task 7 must pass on it unchanged).
- Post-merge (V1): dispatch `mutation-testing.yml` per crate; record caught/missed/timeout/unviable beside run 41769558239.

Known survivors to kill or classify are in run 41769558239's `mutants-output` artifact (`gh run download 41769558239 -n mutants-output -D <dir>`), `<crate>/<crate>-rs/mutants.out/missed.txt`.

---

### Task 1: pi-rs size parameter, pure functions, exact tests

```yaml-task
id: 1
description: pi-rs gets write_pi_file_sized, threshold and summary-line pure functions, and exact-value tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C pi/pi-rs test
    exit_code: 0
max_retries: 3
files_touched: [pi/pi-rs/src/main.rs, pi/pi-rs/src/lib.rs, pi/pi-rs/CLAUDE.md]
depends_on: []
parallel_group: crates
requirements: [R1, R3, R4, R5, R6, R8]
```

**Files:** `pi/pi-rs/src/main.rs` (code and `mod tests`), `pi/pi-rs/src/lib.rs` (only if a moved helper lives there), `pi/pi-rs/CLAUDE.md`.

- [ ] `write_pi_file(dir, pi_str, digits)` delegates to `write_pi_file_sized(dir, pi_str, digits, min_chunk: usize)` with `4 * 1024 * 1024`. Test: `min_chunk = 7`, a digit string of at least 40 bytes whose length is not a multiple of 7, and assert the whole file equals `header + digits + footer` byte for byte (build the expected header/footer in the test the same way the code does).
- [ ] Pure thresholds, used by `run` and `prompt_digits_with`: `warn_large_digits(d) -> bool` (`d > 1_000_000`), `shows_preview(d) -> bool` (`d <= 1_000_000`), `auto_saves(d) -> bool` (`d > 10_000`). Test each at the bound and one either side.
- [ ] `format_write_done(total_bytes: u64, elapsed: f64) -> String` returns exactly the text the final `eprintln!` prints today (the caller keeps the leading `\r`); test exact strings at elapsed 0.001, 0.002 and 1.0.
- [ ] `format_write_progress` tests pin exact output strings (MB figures, speed) at elapsed 0.001 and 0.002.
- [ ] `run` with `digits = Some(1)` returns 0 and prints `π = 3.1…`.
- [ ] Any survivor from the known list on a line you touch that falls in no Global-Constraints class gets a test. CLAUDE.md: new functions, test table counts.

**Interfaces:** Produces `write_pi_file_sized`, `warn_large_digits`, `shows_preview`, `auto_saves`, `format_write_done` (private to the binary crate is fine).

### Task 2: e-rs size parameter, pure functions, exact tests

```yaml-task
id: 2
description: e-rs gets write_e_file_sized, threshold and summary-line pure functions, and exact-value tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C e/e-rs test
    exit_code: 0
max_retries: 3
files_touched: [e/e-rs/src/main.rs, e/e-rs/src/lib.rs, e/e-rs/CLAUDE.md]
depends_on: []
parallel_group: crates
requirements: [R1, R3, R4, R5, R6, R8]
```

Same as Task 1 with e names: `write_e_file` delegates to `write_e_file_sized(..., min_chunk)`; `warn_large_digits`, `shows_preview`, `auto_saves` used by `run` and `prompt_digits_with`; `format_write_done`; `format_write_progress` lives in `src/lib.rs` here, so its exact-string tests go in `src/main.rs` `mod tests` calling it. `run` with `digits = Some(1)` returns 0 and prints `e = 2.7…`. Do not touch `compute_e`'s term-count block (lines 139-144): its mutants are proven equivalent and Task 6 excludes them. CLAUDE.md updated.

### Task 3: prime-rs block and segment sizes, phase-2 pure functions

```yaml-task
id: 3
description: prime-rs gets find_primes_sized and sieve_segment seg parameter, phase2_range and format_phase2_done, with reference-sieve tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C prime/prime-rs test
    exit_code: 0
max_retries: 3
files_touched: [prime/prime-rs/src/lib.rs, prime/prime-rs/src/main.rs, prime/prime-rs/CLAUDE.md]
depends_on: []
parallel_group: crates
requirements: [R2, R4, R5, R8]
```

- [ ] `find_primes(limit, out)` delegates to `find_primes_sized(limit, out, block: u64, seg: u64) -> io::Result<(u64, u64)>` returning (prime count, processed count); `find_primes` passes `BLOCK_SIZE`, `SEG_SIZE` and returns the count. `sieve_segment` takes `seg`. `debug_assert!` that `block` and `seg` are even.
- [ ] `phase2_range(sqrt_limit: u64, limit: u64) -> (u64, u64)` returns (start, total) as computed today; the progress thread and final line use it. Test start/total for odd and even `sqrt_limit`.
- [ ] `format_phase2_done(total: u64, elapsed: f64) -> String` returns the final line's text; exact-string tests at elapsed 0.001, 0.002, 1.0. `format_phase2_progress` exact-string tests at elapsed 0.001 and 0.002.
- [ ] Reference test: with `block = 64`, `seg = 16`, compare `find_primes_sized` output to a naive trial-division list at limits 1000, 1001, and one limit landing exactly on a block boundary; assert the processed count's exact value for one 3+-block run (derive it by hand in the test).
- [ ] CLAUDE.md updated.

### Task 4: twin-primes-rs segment size and panic witness

```yaml-task
id: 4
description: twin-primes-rs gets find_twin_primes_sized and sieve_segment seg parameter, segment_start, reference tests and an idx-panic witness
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C twin-primes/twin-primes-rs test
    exit_code: 0
  - cmd: 'bash -c ''d=$(mktemp -d /tmp/claude-1000/s4ctl.XXXX); git archive HEAD twin-primes/twin-primes-rs | tar -x -C "$d"; f="$d/twin-primes/twin-primes-rs/src/lib.rs"; sed -i "s/while idx < n {/while idx <= n {/" "$f"; grep -q "while idx <= n {" "$f" || { rm -rf -- "$d"; exit 9; }; (cd "$d/twin-primes/twin-primes-rs" && cargo test --quiet >/dev/null 2>&1); rc=$?; rm -rf -- "$d"; [ "$rc" -ne 0 ]'''
    exit_code: 0
max_retries: 3
files_touched: [twin-primes/twin-primes-rs/src/lib.rs, twin-primes/twin-primes-rs/src/main.rs, twin-primes/twin-primes-rs/CLAUDE.md]
depends_on: []
parallel_group: crates
requirements: [R2, R6, R8]
```

- [ ] `find_twin_primes(limit, out)` delegates to `find_twin_primes_sized(limit, out, seg: u64)` with `SEG_SIZE`; `sieve_segment(lo, limit, small_primes, seg)`; `debug_assert!` even `seg`. `segment_start(sqrt_limit) -> u64` computes the first odd above `sqrt_limit` and is tested for odd and even input.
- [ ] Reference test with `seg = 64`: pairs from `find_twin_primes_sized` equal pairs from a naive list at limits 1000, 1001 and one on a segment boundary, including a pair spanning two segments.
- [ ] Witness test: a direct `sieve_segment` call on a full segment with `n % 8 == 0` where a sieving prime's progression lands on `idx == n`; the second acceptance command (commit first) proves the suite fails under `idx <= n`.
- [ ] CLAUDE.md updated.

### Task 5: collatz-rs warning predicate and record boundary

```yaml-task
id: 5
description: collatz-rs gets a warns_large_n predicate used by run, and an exact generate_records test up to 19
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C collatz/collatz-rs test
    exit_code: 0
max_retries: 3
files_touched: [collatz/collatz-rs/src/lib.rs, collatz/collatz-rs/src/main.rs, collatz/collatz-rs/CLAUDE.md]
depends_on: []
parallel_group: crates
requirements: [R3, R6, R8]
```

- [ ] `warns_large_n(v: u64) -> bool` (`v > 9`), used by `run`; tested at 8, 9, 10.
- [ ] `generate_records(19, ...)` returns exactly `[(1,0),(2,1),(3,7),(6,8),(7,16),(9,19),(18,20)]` (verify each length in the test by hand from the chain-length definition; 19 also has length 20 and must not appear).
- [ ] CLAUDE.md updated.

### Task 6: mutation runs and exclusion lists

```yaml-task
id: 6
description: run make mutants in the five crates and write each .cargo/mutants.toml from survivors that match an allowed equivalence class
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'bash -c ''for c in pi/pi-rs e/e-rs prime/prime-rs twin-primes/twin-primes-rs collatz/collatz-rs; do test -s "$c/mutants.out/caught.txt" && ! test -s "$c/mutants.out/missed.txt" || { echo "FAIL $c"; exit 1; }; done'''
    exit_code: 0
  - cmd: 'bash -c ''for c in pi/pi-rs e/e-rs prime/prime-rs twin-primes/twin-primes-rs; do test -f "$c/.cargo/mutants.toml" || { echo "MISSING $c"; exit 1; }; done'''
    exit_code: 0
max_retries: 2
files_touched: [pi/pi-rs/.cargo/mutants.toml, e/e-rs/.cargo/mutants.toml, prime/prime-rs/.cargo/mutants.toml, twin-primes/twin-primes-rs/.cargo/mutants.toml, collatz/collatz-rs/.cargo/mutants.toml]
depends_on: [1, 2, 3, 4, 5]
requirements: [R7]
```

TDD waived: data files only, verified by the mutation run itself. For each crate, one at a time, with the Bash timeout at 600000: `cd <crate> && CARGO_MUTANTS_JOBS=8 make mutants`. Read `mutants.out/missed.txt`. Every survivor must fit a Global-Constraints class, and its comment must say why no test with input under 10,000 (the `_sized` entry points included) can kill it (N5). A partition-arithmetic survivor qualifies only on a default-constant line reached solely by the unsized wrapper, or where the comment shows every mutated value keeps the pieces positive, non-overlapping and gap-free; otherwise it is a blocker. Write it into `.cargo/mutants.toml` in the `factorial/factorial-rs/.cargo/mutants.toml` format (a comment naming the class and why, then the line-anchored regex), re-run, and repeat until `missed.txt` is empty. A survivor that fits no class is a blocker: report it with its line and source; do not exclude it and do not edit `src/`. A crate whose survivors are all killed gets no `.cargo/mutants.toml` (spec R7 amendment; collatz-rs is expected to be one). pi, e, prime and twin-primes each have known equivalents, so each gets a file. Report which crates got a file: Task 7's expected set is built from that list.

### Task 7: exclusion drift test, CI trigger, pre-push run

```yaml-task
id: 7
description: tests/test_mutants_exclusions.py over nine crates, scripts.yml install and paths, targeted pre-push run with bats coverage, root CLAUDE.md line
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: python3 -m unittest tests.test_mutants_exclusions -v
    exit_code: 0
  - cmd: make test
    exit_code: 0
  - cmd: 'test "$(wc -c < CLAUDE.md)" -le 30000'
    exit_code: 0
max_retries: 3
files_touched: [tests/test_mutants_exclusions.py, .github/workflows/scripts.yml, scripts/pre-push, tests/scripts/pre_push.bats, CLAUDE.md]
depends_on: [6]
requirements: [R9]
```

- [ ] Test (unittest, root `tests/`): glob `*/*-rs/.cargo/mutants.toml`, assert the set of crate directories equals a literal `EXPECTED` set (amicable, factorial, goldbach, perfect-numbers plus each slice-4 crate Task 6 reported); parse with `tomllib`, assert non-empty `exclude_re`; per crate run `cargo mutants --list --no-config -d <crate>` (assert rc 0, non-empty); each entry `re.search`es at least one listed line; no listed line matched by two entries. Absent `cargo-mutants`: `skipTest` naming `cargo install cargo-mutants --locked --version 27.1.0`, unless `CI=true`, then fail. Include a negative case on a fixture list (a stale entry fails; a shared match fails).
- [ ] `scripts.yml`: `paths:` add `"*/*-rs/src/**"` and `"*/*-rs/.cargo/mutants.toml"`; in the `taiki-e/install-action` step with `tool: cargo-deny@0.20.2`, make it `tool: cargo-deny@0.20.2,cargo-mutants@27.1.0` (keeps the SHA pin and `fallback: none`).
- [ ] `scripts/pre-push`: when the pushed range touches `^[^/]+/[^/]+-rs/src/` or `^[^/]+/[^/]+-rs/\.cargo/mutants\.toml$`, run `python3 -m unittest tests.test_mutants_exclusions < /dev/null` from the repo root (before the early exits, like `RUN_CLI_CONTRACT`), failing the push on error. Bats: one test per branch (triggered, not triggered), using the existing `MOCK_GIT_DIFF_NAMES` pattern.
- [ ] Root `CLAUDE.md`: edit the existing `exclude_re` line in place to name `tests/test_mutants_exclusions.py`; stay at or under 30,000 bytes.

## Non-goal check

Reviewer verdicts (fresh Opus subagent, `nongoal-check.md`, 2026-11-04): N1 CLEAR, N2 CLEAR, N4 CLEAR, N3 UNCLEAR, N5 UNCLEAR.

- **N3 UNCLEAR.** Quote: Task 7 "in the `taiki-e/install-action` step with `tool: cargo-deny@0.20.2`, make it `tool: cargo-deny@0.20.2,cargo-mutants@27.1.0`". Resolution: no plan change. Spec R9 (as amended) requires `scripts.yml` to install `cargo-mutants@27.1.0` through the pinned `taiki-e/install-action`, and N3 means crate and Python package dependencies; the tool is the version `mutation-testing.yml` already installs.
- **N5 UNCLEAR.** Quote: Task 6 "Every survivor must fit a Global-Constraints class; write it into `.cargo/mutants.toml` ..." with the class "partition arithmetic (incl. default size constants)". Resolution: plan revised. Before: "Every survivor must fit a Global-Constraints class; write it into". After: "Every survivor must fit a Global-Constraints class, and its comment must say why no test with input under 10,000 (the `_sized` entry points included) can kill it (N5). A partition-arithmetic survivor qualifies only on a default-constant line reached solely by the unsized wrapper, or where the comment shows every mutated value keeps the pieces positive, non-overlapping and gap-free; otherwise it is a blocker. Write it into".
