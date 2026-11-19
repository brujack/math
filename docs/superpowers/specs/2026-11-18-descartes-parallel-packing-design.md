# descartes: parallel packing in Rust and Python

- **Status:** Approved
- **Approved:** 2026-11-18
- **Date:** 2026-11-18
- **Scope:** `descartes/descartes.py`, `descartes/descartes-rs/` (both halves; identical results)

## Context

The packing search is a single-threaded depth-first walk in both languages, and at the top K values it is
now the bottleneck. Measured 2026-11-18 on `claude` (Threadripper 3960X, 48 threads, default root,
`--no-draw`, `/usr/bin/time`, release build for Rust):

| program | K | wall | peak RSS |
|---|---|---|---|
| `descartes-rs` | 6 | 0.33 s | 5.6 MB |
| `descartes-rs` | 7 | 7.66 s | 30 MB |
| `descartes-rs` | 8 | 201.5 s | 276 MB |
| `descartes.py` | 5 | 1.66 s | 20 MB |
| `descartes.py` | 6 | 30.8 s | 33 MB |

The 276 MB at K=8 is the distinct-curvature list built for the `.txt` file, not the walk. The 2026-11-15
descartes spec deferred parallelism with N2 ("No parallel packing: no `rayon` and no threads in the packing
search"), backed by the Backlog row "Build only if V1 shows serial is too slow"; the figures above meet that
condition.

The other parallel sub-projects set the pattern: Rust `pi`, `e`, `factorial` and `prime` use `rayon`
(`rayon = "1"`) across every core with no flag; Python `pi`, `e` and `factorial` use
`concurrent.futures.ProcessPoolExecutor` (`fork` on Linux, `spawn` elsewhere) and fall back to serial with
an explicit message when the pool fails (root `CLAUDE.md` multiprocessing rule).

The walk is a pure function of a stack item `(quad, j)`: each item's subtree is independent of every other
item's, and the outputs are order-independent (`count` is a sum, the bitmap a union), so a split walk can
reproduce the serial result exactly. Exact equality is the correctness contract.

Step 8 prototyped the design on `claude` (probes under `/tmp/claude-1000/lensp*`, session-local):

- A breadth-first frontier stops at exactly 4096 seeds after 2049 coordinator pops for the default root and
  `-2 3 6 7` and 2619 for `-11 21 24 28` at n = 10^5 (round 1 also measured 10^6), and the split reproduces
  `pack`'s count and bitmap exactly. Root `-5 10 10 15` at n = 10^5 overshoots to 4097 seeds after 2060
  pops; root `-300 301 90300 90301` at n = 10^5 has only 198 circles and empties the frontier.
- Rust with `rayon` and the shared atomic bitmap below: K=7 0.42 s, K=8 10.62 s (19x, 16.6 MB peak RSS),
  counts equal to the shipped CLI. Python with a 48-worker `fork` pool and 192 strided tasks: K=6 2.08 s
  (15x). The largest seed subtree is 2.4% of the work (5.7% for `-2 3 6 7`).
- Serial `pack` at n = 10^5 under `taskset -c 0-3`: 1.53 s (default root), 0.60 s (`-2 3 6 7`), 0.067 s
  (`-11 21 24 28`); today's Python suite takes 3.6 s there.

Pool cost (Python 3.14.8): a 48-worker `fork` pool starts and stops in 0.085 s, against a serial `pack` of
0.078 s at n = 10^4 and 1.52 s at n = 10^5. The threshold is on `n`, so for a root with a large outer
curvature it can start a pool for little work (root `-11 21 24 28` at n = 10^5: 59,337 circles in 0.07 s);
that costs time, never correctness, and is accepted.

## Design

### One split, two executors

Both languages add `pack_with_workers(root, n)`, returning `(count, bitmap, workers)`; `pack(root, n)`
keeps its signature and returns the first two (Rust
`pack(root, n) -> Result<(i64, Vec<u64>), DescartesError>`, Python `pack(root, n) -> tuple[int, bytearray]`).
`main` calls `pack_with_workers`. Internally:

1. **Children.** One helper yields a quad's admissible children: today's rule, reflect each circle `i != j`
   and keep it only when `old < k <= n` (Rust keeps its existing form, which rejects the parent through the
   same guard). It holds the R21 growth guard and is the only copy of it; both stages below call it.
2. **Frontier.** Count and mark the root's positive circles, seed the root's reflections as today, then
   expand breadth-first: pop the oldest item, count and mark it, append its children. Stop when the frontier
   holds at least `SEED_TARGET = 4096` items or is empty. Every circle the coordinator pops is counted once.
3. **Subtrees.** Each remaining frontier item roots an independent subtree, walked depth-first through the
   same children helper. The serial path walks them one after another on the calling thread; the parallel
   path hands them to the executor.

The partition depends only on the root and `n`, never on the core count. Because the guard lives in one
helper, the existing broken-root termination and R21 budget tests (whose small trees finish inside the
frontier) still exercise it.

### When it runs in parallel

`PARALLEL_MIN_N = 100_000` in both languages. `n < PARALLEL_MIN_N`, a frontier that empties before
`SEED_TARGET`, or a single available worker runs serially without creating a pool or rayon tasks, and
reports `workers = 1`. With the default root that is K <= 4 serial and K >= 5 parallel; `--smoke` (K=2) and
the CLI contract stay serial. The value is set by Python's pool cost; Rust's rayon overhead is microseconds,
and it uses the same value so the two halves behave alike.

### Rust

Subtree walks run on the current rayon pool (`par_iter` over the frontier); `workers` is
`rayon::current_num_threads()`. Marks go to one shared `Vec<AtomicU64>` the length of today's bitmap: a mark
loads the word with `Ordering::Relaxed` and calls `fetch_or` only when the bit is unset. Counts are summed.
After the parallel section the atomics become the existing `Vec<u64>` (rayon's join gives the
happens-before; a racing double `fetch_or` is idempotent). No `unsafe`. Peak memory stays one bitmap
(12.5 MB at n = 10^8). The dependency is `rayon = "1"` (rayon 1.12.0 is already in `Cargo.lock` through
`criterion`). `walk`'s `on_mark` budget hook keeps counting every popped circle, coordinator pops included,
on the serial path.

### Python

Subtree walks run in `concurrent.futures.ProcessPoolExecutor(max_workers=W, mp_context=_mp_context())`,
where `_mp_context()` returns the `fork` context on Linux and `spawn` elsewhere and
`W = os.process_cpu_count() or 1`. A helper `_tasks(seeds, W)` deals the seeds into `T = 4 x W` tasks by
stride (task `t` takes seeds `t, t + T, t + 2T, ...`), which balanced better than contiguous chunks (25x
against 18x on 48 workers, simulated). The pool runs the tasks with `map`; each returns `(count, bytes)`. The
coordinator holds pool results apart from its own count and bitmap and commits them (sum the counts, OR the
bitmaps through `int.from_bytes`, measured 0.016 s against 4.9 s for a per-byte loop) only after every task
has returned. The worker function is module-level so it pickles under `spawn`.

**Fallback.** If creating or using the pool raises `OSError`, `NotImplementedError` or
`concurrent.futures.process.BrokenProcessPool` (`PermissionError` is an `OSError` and needs no entry),
uncommitted pool results are dropped, every subtree is walked serially from the frontier, `workers` is 1,
and stderr gets `Parallel mode unavailable (<error>); falling back to serial.` then
`Install project requirements and ensure OS multiprocessing semaphore support is available to re-enable parallel mode.`
This is pi's wording, on stderr rather than pi's stdout so stdout stays byte-identical. Exit codes do not
change.

No entry-point guard is added: under `fork` it is irrelevant, and under `spawn` the worker imports the
module as `__mp_main__`, so `__name__ == "__main__"` is already false.

### Status line

When a packing run used more than one worker, it prints `Workers: <w>` to stderr once, immediately before
`Elapsed: <s>s`. Serial runs (small K, small frontier, one worker, the fallback) print nothing new; the
fallback has its own message. The four existing exact-stderr assertions run at K=1 or K=3 and are
unaffected. Stdout, the `.txt` file, the SVG and the count lines do not change. The existing
`RAYON_NUM_THREADS` and `PYTHON_CPU_COUNT` variables still bound the worker count; the docs say so.

### Unchanged

`visible()`, the braille renderer, the SVG and `--solve` stay serial: the drawing caps bound them.

### Spec bookkeeping

The 2026-11-15 spec's N2 is withdrawn and its R13 amended, through its `## Amendments`. The Backlog row
"Parallel Descartes packing (Rust and Python)" is removed on merge. The fallback rule is recorded in
`descartes/CLAUDE.md`; the root `CLAUDE.md` (29,975 of its 30,000-byte cap) is not edited.

## Testing

TDD in both languages. Exactness tests compare against a reference serial walk kept in the test module
(today's loop, copied), computed once per root per test class, so a defect shared by the new serial and
parallel paths still fails. Unit tests stay at n <= 10^5: the debug-build serial walk measured 69-94 s at
10^7 (nextest kills a test at 45 s) and the Python walk 31 s at 10^6 (cosmic-ray times a mutant out at
60 s and scores it killed). Scale is covered by V1's release-binary comparison. Tests that need the pool but
not the default root's size use `-11 21 24 28` at 10^5 (0.07 s serial). Tests never skip on core count:
they set it (Python `os.process_cpu_count` patched; Rust `rayon::ThreadPoolBuilder` with a fixed thread
count and `install`).

- **Exactness:** with 2 workers forced, `pack_with_workers` equals the reference count and bitmap at
  n = 10^5 for the default root and roots `-11 21 24 28` and `-2 3 6 7`, and returns `workers == 2`.
- **Worker count:** Python with `os.process_cpu_count` patched to `None` and to `1`, and Rust inside a
  1-thread pool, return `workers == 1` and (Python) never construct `ProcessPoolExecutor` (patched to fail
  the test if called), at n = 10^5.
- **Threshold:** `workers == 1` at `n = PARALLEL_MIN_N - 1` and `workers == 2` at `PARALLEL_MIN_N` with 2
  workers forced, both languages.
- **Split pins:** literal pins `SEED_TARGET == 4096` and `PARALLEL_MIN_N == 100_000`; the frontier for the
  default root at n = 10^5 holds exactly 4096 seeds after exactly 2049 coordinator pops, and for root
  `-5 10 10 15` at n = 10^5 exactly 4097 seeds after 2060 pops (values to be re-measured on the
  implementation and recorded in the test).
- **Tasks (Python):** `_tasks(range(10), 2)` returns 8 tasks with seed `i` in task `i mod 8`; `_mp_context()`
  returns a `fork` context with `sys.platform` patched to `linux` and `spawn` with it patched to `darwin`.
- **Small frontier:** root `-300 301 90300 90301` at n = 10^5 returns the reference result and
  `workers == 1` with 2 workers forced.
- **Fallback (Python):** with 2 workers forced on root `-11 21 24 28` at n = 10^5, a patched pool whose
  `map` yields one task's result and then raises `BrokenProcessPool` returns the reference count and bitmap,
  `workers == 1` and the two-line stderr message; a constructor raising `OSError` and one raising
  `NotImplementedError` do the same.
- **Status line:** a CLI run at K=5 with 2 workers forced prints `Workers: 2` immediately before `Elapsed:`;
  runs at K <= 4 and the fallback print no `Workers:` line; stdout equals today's.
- **Rust atomics:** marks of the same and adjacent bits from many rayon tasks give the exact union.
- **Existing tests:** the four Python tests that patch `descartes.pack` (around `test_descartes.py` lines
  2530, 2584, 2605 and 2778) patch `pack_with_workers` instead, returning `(count, bitmap, 1)`, and keep
  their assertions.
- **Mutation:** an equivalent is declared only when `cargo mutants --list` (or cosmic-ray) generates the
  mutant and a run shows it surviving, with its mechanism. The Rust guard-to-timeout case follows the repo
  rule (a timeout beside a catch is green).

What the tests cannot see: a Rust `par_iter` written as `iter` still reports `current_num_threads()` and
passes every test; only V2's timing catches it. cargo-mutants does not generate that substitution.

## Requirements

- **R1.** Both languages add `pack_with_workers(root, n)` returning `(count, bitmap, workers)`; `pack(root, n)` keeps its signature (Rust `pack(root: [i64; 4], n: i64) -> Result<(i64, Vec<u64>), DescartesError>`, Python `pack(root, n) -> tuple[int, bytearray]`) and returns the first two; count and bitmap equal the serial reference walk for every valid root and `n`; `main` uses `pack_with_workers`.
- **R2.** One children helper holds the growth guard (`old < k <= n`) and is called by both stages: a breadth-first frontier from the root's reflections that counts and marks each popped circle once until it holds at least `SEED_TARGET = 4096` items or is empty, then a depth-first walk of each frontier item's subtree; the serial and parallel paths share both stages.
- **R3.** `PARALLEL_MIN_N = 100_000` in both languages: when `n < PARALLEL_MIN_N`, the frontier empties before `SEED_TARGET`, or one worker is available, no process pool and no rayon task is created and `workers` is 1; otherwise the subtrees are walked in parallel.
- **R4.** In `descartes-rs` the subtree walks run on the current rayon pool with `workers = rayon::current_num_threads()`, marks go to one shared `Vec<AtomicU64>` (relaxed load, `fetch_or` only when the bit is unset), counts are summed, the crate adds `rayon = "1"` and keeps `unsafe_code = "forbid"`.
- **R5.** In `descartes.py` the subtree walks run in `concurrent.futures.ProcessPoolExecutor(max_workers=W, mp_context=_mp_context())` with `W = os.process_cpu_count() or 1` and `_mp_context()` giving `fork` on Linux and `spawn` otherwise; `_tasks(seeds, W)` deals seeds into `4 x W` tasks by stride; `map` runs them; each returns `(count, bytes)`; the coordinator commits the sum and the `int.from_bytes` OR only after every task returned.
- **R6.** In `descartes.py`, when creating or using the pool raises `OSError`, `NotImplementedError` or `BrokenProcessPool`, uncommitted pool results are dropped, the subtrees are walked serially from the frontier, `workers` is 1, the result equals the reference, and stderr gets `Parallel mode unavailable (<error>); falling back to serial.` then `Install project requirements and ensure OS multiprocessing semaphore support is available to re-enable parallel mode.`; exit codes are unchanged.
- **R7.** A packing run whose `workers` is greater than 1 prints `Workers: <workers>` to stderr once, immediately before `Elapsed: <s>s`; a run with `workers == 1` prints no `Workers:` line; stdout, the `.txt` file, the SVG and the count lines are unchanged for every input.
- **R8.** Tests in both languages, all at n <= 10^5 and never skipped on core count (worker count set by patching or a fixed rayon pool), assert: equality with an in-module reference walk for the default root, `-11 21 24 28` and `-2 3 6 7` at n = 10^5 with 2 workers giving `workers == 2`; `workers == 1` and no pool for 1 worker and (Python) a `None` CPU count; `workers == 1` at `PARALLEL_MIN_N - 1` and 2 at `PARALLEL_MIN_N`; literal pins `SEED_TARGET == 4096` and `PARALLEL_MIN_N == 100_000`; the default root's frontier at n = 10^5 at 4096 seeds after its recorded coordinator count and root `-5 10 10 15`'s at 4097 seeds after its recorded count; (Python) `_tasks` stride and count and `_mp_context` per platform; root `-300 301 90300 90301` at n = 10^5 giving the reference and `workers == 1`; (Python) the fallback on `-11 21 24 28` for a `map` that yields one result then raises `BrokenProcessPool` and for constructors raising `OSError` and `NotImplementedError`, each giving the reference, `workers == 1` and the two-line message; `Workers: 2` before `Elapsed:` at K=5 with 2 workers and no `Workers:` line at K <= 4 or after the fallback; (Rust) exact unions under concurrent marks of shared and adjacent bits; and the four existing Python tests that patch `descartes.pack` patch `pack_with_workers` instead with their assertions kept.
- **R9.** `docs/superpowers/specs/2026-11-15-descartes-design.md`'s `## Amendments` withdraws N2 and amends R13 to drop "no `rayon` dependency", each with a reason naming this spec.
- **R10.** `descartes/README.md`, `descartes/descartes-rs/README.md`, `descartes/CLAUDE.md` and `descartes/descartes-rs/CLAUDE.md` state the parallel model, `PARALLEL_MIN_N`, the `Workers:` stderr line and `RAYON_NUM_THREADS` / `PYTHON_CPU_COUNT`; `descartes/CLAUDE.md` states the fallback message and that it goes to stderr, unlike pi's; the Backlog row "Parallel Descartes packing (Rust and Python)" is removed from `docs/superpowers/README.md`.
- **V1.** Build master's Rust binary and take master's `descartes.py` (from `origin/master` before this change) and run both against the new ones with `--yes --no-draw`: stdout and the `.txt` file are byte-identical for Rust K=1-8 and Python K=1-6 on the default root, and for K=1-5 on roots `-11 21 24 28` and `-2 3 6 7`.
- **V2.** Wall time and peak RSS on `claude` for Rust K=7 and 8 and Python K=5 and 6 are recorded in the PR body against the serial baseline above (7.66 s / 201.5 s; 1.66 s / 30.8 s); Rust K=8 is at least 5x faster and Python K=6 at least 3x faster.
- **V3.** `python3 -m unittest test_descartes` completes in under 15 s under `taskset -c 0-3` on `claude`, and CI is green on the PR, including `mutation-pr` with 0 survivors on changed lines in both languages and 0 Python timeouts on changed lines.
- **N1.** No new command-line flag and no new environment variable is added by this change.
- **N2.** Stdout, the `.txt` file, the SVG and their order do not change for any input.
- **N3.** `visible()`, the renderer, the SVG and `--solve` stay serial.
- **N4.** No `unsafe` code, and no new dependency other than `rayon` in `descartes-rs`.
- **N5.** `N_MAX`, `ROOT_MAX`, the K ranges and the drawing caps do not change.

## Multi-Lens Review

Reviewed at commit: `f1ffe85` (round 1), `d8a77f5` (round 2)

### Round 1

### Goal-Fit

Finding: Worth building; premise confirmed by prototype (Rust K=8 201.5 s -> 10.62 s, Python K=6 30.8 s -> 2.08 s, both exact). (1) The Rust 10^7 exactness test cannot pass: debug serial walk 73.8 s vs nextest's 45 s cap. (2) The Python 10^6 test costs ~10x the 3.65 s suite and covers nothing 10^5 does not. (3) Split constants and BFS order are equivalent mutants under V3. (4) The fallback can double-count when `BrokenProcessPool` surfaces mid-`map`. (5) Most tests pass if the parallel path is never taken (`w >= 1`). (6) `Workers:` is decoration and breaks exact-stderr assertions; Python's task split and OR method are unspecified (strided 25x vs contiguous 18x; use `int.from_bytes`). (7) Rust-only captures the headline value; Python scope is the operator's call.
Assumption: the Python suite plus new tests stays well under cosmic-ray's 60 s timeout on a 4-vCPU runner; settled by timing under `taskset -c 0-3` and the `mutation-pr` log.
Disposition: Addressed — operator chose `Workers:` only when parallel ran and both languages (2026-11-18); the remaining fixes were applied by the author and approved by the operator with the round-2 revision: both languages kept; `Workers:` only when workers > 1; unit tests at n <= 10^5, scale in V1; split pins, strided tasks, `int.from_bytes`, fallback discards partial results, `workers > 1` assertions; V3 adds a suite-time bound.

### Ergonomics

Finding: (1) Rust 10^7 test exceeds the 45 s cap (debug 68.65 s). (2) Python 10^6 test makes `make test`/pre-push ~45 s and the mutation gate vacuous or over the 30-minute job. (3) Most tests pass if parallel never runs; a crashing worker would fall back silently. (4) R1 vs R7: `main` cannot learn `workers` from a frozen `pack`; name the channel (`pack_with_workers`). (5) `Workers:` breaks four existing stderr assertions and adds `Workers: 1` noise to every small run. Ctrl-C, spawn cost, memory and existing knobs checked clean.
Assumption: per-mutant wall time with forking tests stays well under 60 s on a 4-vCPU runner; settled by a dispatched shard's timeout count.
Disposition: Addressed — operator chose `Workers:` only when parallel ran and both languages (2026-11-18); the remaining fixes were applied by the author and approved by the operator with the round-2 revision: `pack_with_workers` added (R1); `Workers:` only when workers > 1, so the four K <= 3 stderr assertions are unaffected; spy and `workers > 1` tests; 10^5 ceiling; V3 timing and 0-timeout bound.

### Risk

Finding: (1) Rust 10^7 (debug 93.85 s) and Python 10^6 (30.98 s) tests break their gates; timeouts score as killed. (2) Split logic is mutation-equivalent by construction (SEED_TARGET +-1, `>=`/`>`, BFS->DFS, `4 x W`, `or 1`, the threshold literal); needs pins, a seam, or declared equivalents. (3) Tests pass if parallel never runs. (4) `on_mark` hook unaddressed. (5) Unlisted stderr assertions. (6) Context premise "other roots have comparable counts" false at fixed n (root `-11 21 24 28`: 59,337 circles at 10^5). (7) Byte-loop OR costs 4.92 s; contiguous chunks balance worse than strided. Exactness, atomics ordering, cargo-deny, uniformity, amendment form and memory checked clean.
Assumption: the shared atomic bitmap does not stall on cache-coherence traffic at K=8; refuted by goal-fit's prototype (10.62 s, 19x).
Disposition: Addressed — operator chose `Workers:` only when parallel ran and both languages (2026-11-18); the remaining fixes were applied by the author and approved by the operator with the round-2 revision: literal and frontier pins, recorded coordinator count, stride test, declared Rust pre-check equivalent; `on_mark` stays serial-only (R4); Context premise corrected; strided tasks and `int.from_bytes` (R5).

### Round 2

Reviewed at commit: `d8a77f5`. All three lenses re-ran; the round-1 section above is history.

#### Goal-Fit (round 2)

Finding: Worth building (premise re-measured under `taskset -c 0-3`: exact, 0.52 s vs 1.53 s at 10^5). (1) The split would leave the subtree walk's copy of the growth guard with no killing test: every guard/budget test tree finishes inside the frontier, so its mutants survive; share one children helper. (2) `PermissionError` is an `OSError` subclass, so its tuple member is an unkillable ExceptionReplacer mutant. (3) The mandated Rust pre-check equivalent is a mutant cargo-mutants never generates (the declaration would be stale). (4) V3's 15 s depends on roots the spec never named (~17 s default root vs ~8 s with `-11 21 24 28`). (5) The Python spy duplicates exactness and `workers == 1`. (6) The entry guard is dead under `fork` and redundant under `spawn` (`__mp_main__`). (7) A Rust `par_iter` written as `iter` passes every test.
Assumption: Rust walk-guard mutants on changed lines may time out rather than be caught; V3's "0 timeouts" should follow the repo's green-timeout rule for Rust.
Disposition: Addressed (operator approved the round-2 revision, 2026-11-18) — see the revised Design, Testing and Requirements at 3cde75b.

#### Ergonomics (round 2)

Finding: (1) Four existing Python tests patch `descartes.pack` (lines ~2530, 2584, 2605, 2778); once `main` calls `pack_with_workers` two fail, one goes vacuous and one silently runs a real 10^6 packing. (2) V3's bound needs the pool-reaching tests on `-11 21 24 28`. (3) Rust `workers` is the runtime constant, so a serial `iter` passes. (4) The status-line test asserts `w > 1` with no core-count condition. (5) Pin the spy and fallback to `map`. (6) Root `CLAUDE.md` is at 29,975 / 30,000 bytes; R10's root edit barely fits and "high-precision calculators" does not describe descartes. Stderr assertions, cosmic-ray's sequential distributor, 4-vCPU public runners and `process_cpu_count` under `taskset` checked clean.
Assumption: the new Python tests fit V3's 15 s once the four tests migrate; settled by timing the implementation.
Disposition: Addressed (operator approved the round-2 revision, 2026-11-18) — see the revised Design, Testing and Requirements at 3cde75b.

#### Risk (round 2)

Finding: (1) The Rust pre-check equivalent cannot be declared (no such mutant in `cargo mutants --list`). (2) `PermissionError` member is an unkillable survivor. (3) Frontier pins miss `<` -> `!=` because all named roots land on exactly 4096; root `-5 10 10 15` lands on 4097. (4) The one-worker and `or 1` branches are never exercised (`or 0`/`or 2`, `W == 1` -> `W < 1`, Rust `||` -> `&&` survive); patch the CPU count and use a 1-thread rayon pool. (5) The small-frontier test must run at n >= `PARALLEL_MIN_N`; root `-300 301 90300 90301` at 10^5 has 198 circles. (6) `4 x W` and fork-on-Linux mutants survive unless the task helper and the context choice are testable units. (7) Force the parallel path (2 workers) instead of skipping on 1 CPU. (8) "Discard partial results already merged" cannot be literal for an OR: hold pool results apart and commit after all tasks return. (9) V3 root choice as above. (10) No Rust "pool used" test.
Assumption: the Python suite fits 15 s under `taskset -c 0-3` (~15.6 s default root, ~8 s on `-11 21 24 28`); settled by naming the root, done.
Disposition: Addressed (operator approved the round-2 revision, 2026-11-18) — see the revised Design, Testing and Requirements at 3cde75b.

#### Stop decision

Round 2's one design finding (the guard copy) is fixed by removing a duplicate rather than adding mechanism; the revision also removes the spy, the entry guard, the `PermissionError` member, the mandated equivalent and the root `CLAUDE.md` edit. The remaining findings sit in the test apparatus (which mutant each test kills, which root, which seam), where Phase 2's first red tests are the cheaper instrument. Both stop signals agree: no round 3.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

## Amendments

- R4 -> In `descartes-rs` the subtree walks run on a rayon pool with `workers` equal to that pool's thread count: the current pool when `pack_with_workers` is called from inside one (`rayon::current_thread_index()` is `Some`), otherwise a pool built with `rayon::ThreadPoolBuilder::new().build()` and entered with `install`; marks go to one shared `Vec<AtomicU64>` (relaxed load, `fetch_or` only when the bit is unset), counts are summed, the crate adds `rayon = "1"` and keeps `unsafe_code = "forbid"`. — bug-scan found that building rayon's global pool lazily panics when the OS refuses a thread, so the pool is built where its error can be handled.
- adds R11: When `descartes-rs` cannot build its rayon pool (`ThreadPoolBuilder::build` returns an error), `pack_with_workers` walks the remaining subtrees serially with `workers = 1` and reports the error, and the CLI prints `Parallel mode unavailable (<error>); falling back to serial.` then `Raise the process or thread limit (ulimit -u, a container pids limit) to re-enable parallel mode.` to stderr before `Elapsed:`, exits 0 and writes the same stdout and `.txt` as a serial run. — bug-scan found a K >= 5 run under `ulimit -u 5` panicked with exit 101 after truncating the `.txt`, a regression from master's thread-free crate; the operator chose a descartes-rs fallback on 2026-11-18 and a Backlog row for pi-rs, e-rs, factorial-rs and prime-rs.
