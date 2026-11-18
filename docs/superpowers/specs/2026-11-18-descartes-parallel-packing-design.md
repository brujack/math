# descartes: parallel packing in Rust and Python

- **Status:** Draft (revised after Step 8 round 1)
- **Date:** 2026-11-18
- **Scope:** `descartes/descartes.py`, `descartes/descartes-rs/` (both halves; identical results)

## Context

The packing search is a single-threaded depth-first walk in both languages, and at the top K values it is
now the bottleneck. Measured 2026-11-18 on `claude` (Threadripper 3960X, 48 threads, default root,
`--no-draw`, `/usr/bin/time`, release build for Rust):

| program        | K   | wall    | peak RSS |
| -------------- | --- | ------- | -------- |
| `descartes-rs` | 6   | 0.33 s  | 5.6 MB   |
| `descartes-rs` | 7   | 7.66 s  | 30 MB    |
| `descartes-rs` | 8   | 201.5 s | 276 MB   |
| `descartes.py` | 5   | 1.66 s  | 20 MB    |
| `descartes.py` | 6   | 30.8 s  | 33 MB    |

The 276 MB at K=8 is the distinct-curvature list built for the `.txt` file, not the walk. The 2026-11-15
descartes spec deferred parallelism with N2 ("No parallel packing: no `rayon` and no threads in the packing
search"), backed by the Backlog row "Build only if V1 shows serial is too slow"; the figures above meet that
condition.

The four other parallel sub-projects set the pattern: Rust `pi`, `e`, `factorial` and `prime` use `rayon`
(`rayon = "1"`) across every core with no flag; Python `pi`, `e` and `factorial` use
`concurrent.futures.ProcessPoolExecutor` (`fork` on Linux, `spawn` elsewhere) and fall back to serial with
an explicit message when the pool fails (root `CLAUDE.md` multiprocessing rule).

The walk is a pure function of a stack item `(quad, j)`: each item's subtree is independent of every other
item's, and the outputs are order-independent (`count` is a sum, the bitmap a union), so a split walk can
reproduce the serial result exactly. Exact equality is the correctness contract.

Step 8 round 1 prototyped the design on `claude` (probes `/tmp/claude-1000/lensp-*`, session-local):
a breadth-first frontier of 4096 seeds is reached after 2046-2616 coordinator pops for the default root
and roots `-11 21 24 28` and `-2 3 6 7` at n = 10^5 and 10^6, and the split reproduces `pack`'s count and
bitmap exactly in every case. Rust with `rayon` and the shared atomic bitmap below ran K=7 in 0.42 s and
K=8 in 10.62 s (19x, 16.6 MB peak RSS) with counts equal to the shipped CLI; Python with a 48-worker `fork`
pool and 192 strided tasks ran K=6 in 2.08 s (15x). The largest seed subtree is 2.4% of the work (5.7% for
`-2 3 6 7`).

Pool cost (Python 3.14.8): a 48-worker `fork` `ProcessPoolExecutor` starts and stops in 0.085 s, against
a serial `pack` of 0.078 s at n = 10^4 and 1.52 s at n = 10^5 (default root). The threshold is on `n`, so
for a root with a large outer curvature it can start a pool for less work than that (root `-11 21 24 28`
at n = 10^5 packs 59,337 circles in 0.07 s); that costs time, never correctness, and is accepted.

## Design

### One split, two executors

Both languages add `pack_with_workers(root, n)`, returning `(count, bitmap, workers)`; `pack(root, n)`
keeps its signature and returns the first two (Rust
`pack(root, n) -> Result<(i64, Vec<u64>), DescartesError>`, Python `pack(root, n) -> tuple[int, bytearray]`).
`main` calls `pack_with_workers`. Internally:

1. **Frontier.** Count and mark the root's positive circles, seed the root's reflections as today, then
   expand breadth-first: pop the oldest item, count and mark it, append its admissible children (today's
   growth guard, unchanged). Stop when the frontier holds at least `SEED_TARGET = 4096` items or is empty.
   Every circle the coordinator pops is counted once, as in the serial walk.
2. **Subtrees.** Each remaining frontier item roots an independent subtree, walked depth-first exactly as
   today's loop walks its stack. The serial path walks them one after another on the calling thread; the
   parallel path hands them to the executor.

The serial and parallel paths share the frontier and subtree code. The partition depends only on the root
and `n`, never on the core count.

### When it runs in parallel

`PARALLEL_MIN_N = 100_000` in both languages. `n < PARALLEL_MIN_N`, a frontier that empties before
`SEED_TARGET`, or a machine with one worker runs serially without creating a pool or rayon tasks, and
reports `workers = 1`. With the default root that is K <= 4 serial and K >= 5 parallel; `--smoke` (K=2) and
the CLI contract stay serial. The value is set by Python's pool cost; Rust's rayon overhead is microseconds,
and it uses the same value so the two halves behave alike.

### Rust

Subtree walks run on rayon's global pool (`par_iter` over the frontier); `workers` is
`rayon::current_num_threads()`. Marks go to one shared `Vec<AtomicU64>` the length of today's bitmap: a mark
loads the word with `Ordering::Relaxed` and calls `fetch_or` only when the bit is unset. Counts are summed.
After the parallel section the atomics are converted to the existing `Vec<u64>` (rayon's join gives the
happens-before; a racing double `fetch_or` is idempotent). No `unsafe`. Peak memory stays one bitmap
(12.5 MB at n = 10^8). The dependency is `rayon = "1"` (rayon 1.12.0 is already in `Cargo.lock` through
`criterion`).

`walk`'s `on_mark` budget hook stays on the serial path only: the subtree function is generic over the mark
callback, the serial path passes the budget closure, and the parallel path passes the atomic mark. The R21
budget tests run at n = 30 and 100, below the threshold, so they keep exercising the guard.

### Python

Subtree walks run in `concurrent.futures.ProcessPoolExecutor(max_workers=W, mp_context=...)`, `fork` on
Linux and `spawn` elsewhere, `W = os.process_cpu_count() or 1`. The seeds are dealt into `T = 4 x W` tasks
by stride (task `t` takes seeds `t, t + T, t + 2T, ...`), which balances better than contiguous chunks
(round-1 simulation: 25x against 18x on 48 workers). Each task returns `(count, bytes)`; the coordinator sums
the counts and ORs the bitmaps through `int.from_bytes` (a per-byte loop over 192 x 125 KB measured 4.9 s
against 0.016 s). The worker function is module-level so it pickles under `spawn`.

**Fallback.** If creating or using the pool raises (`OSError`, `PermissionError`, `NotImplementedError`,
`concurrent.futures.process.BrokenProcessPool`), `pack_with_workers` discards every partial result already
merged from the pool, walks all subtrees serially from the frontier state, returns `workers = 1`, and
prints to stderr `Parallel mode unavailable (<error>); falling back to serial.` then
`Install project requirements and ensure OS multiprocessing semaphore support is available to re-enable parallel mode.`
(pi's wording, on stderr rather than pi's stdout so stdout stays byte-identical). Exit codes do not change.

**Entry-point guard.** As in `pi.py`, the `if __name__ == "__main__":` block also checks
`multiprocessing.current_process().name == "MainProcess"`, so a `spawn` worker never re-runs `main()`.

### Status line

When a packing run used more than one worker, it prints `Workers: <w>` to stderr once, immediately before
`Elapsed: <s>s`. Serial runs (small K, small frontier, one core, the fallback) print nothing new; the
fallback has its own message. The four existing exact-stderr assertions (`test_descartes.py` around lines
2382 and 2404, `descartes-rs/src/main.rs` `elapsed_goes_to_stderr_only_with_two_decimals`,
`tests/cli.rs` around line 141) run at K=1 or K=3 and are therefore unaffected. Stdout, the `.txt` file, the
SVG and the count lines do not change. The existing `RAYON_NUM_THREADS` and `PYTHON_CPU_COUNT` variables
still bound the worker count; the docs say so.

### Unchanged

`visible()`, the braille renderer, the SVG and `--solve` stay serial: the drawing caps bound them.

### Spec bookkeeping

The 2026-11-15 spec's N2 is withdrawn and its R13 amended, through its `## Amendments`. The Backlog row
"Parallel Descartes packing (Rust and Python)" is removed on merge.

## Testing

TDD in both languages. Exactness tests compare against a reference serial walk kept in the test module
(today's loop, copied), so a defect shared by the new serial and parallel paths still fails. Unit tests stay
at n <= 10^5: the debug-build serial walk measured 69-94 s at 10^7 (nextest kills a test at 45 s) and the
Python walk 31 s at 10^6 (cosmic-ray times a mutant out at 60 s and counts that as killed). Scale is
covered by V1's byte-identical release-binary comparison.

- **Exactness:** `pack_with_workers` equals the reference count and bitmap at n = 10^5 for the default root
  and roots `-11 21 24 28` and `-2 3 6 7`, and returns `workers` equal to `os.process_cpu_count()` /
  `rayon::current_num_threads()` (asserted `> 1` when the machine has two or more cores, so a never-taken
  parallel path fails).
- **Pool actually used (Python):** a spy wrapping `ProcessPoolExecutor` records that it was constructed and
  that `map` (or the submit path used) returned every task's result at n = 10^5, and that it was not
  constructed at `n = PARALLEL_MIN_N - 1`.
- **Threshold (Rust):** `workers == 1` at `n = PARALLEL_MIN_N - 1` and `> 1` at `PARALLEL_MIN_N` (two or more
  cores).
- **Split pins:** literal pins `SEED_TARGET == 4096` and `PARALLEL_MIN_N == 100_000`; the frontier for the
  default root at n = 10^5 holds exactly 4096 seeds and its coordinator pass counted exactly the circles
  measured on the implementation (recorded in the test), which a depth-first frontier would not reproduce;
  the strided task split for a given `W` assigns seed `i` to task `i mod T`.
- **Small frontier:** a root and `n` whose tree empties before `SEED_TARGET` return the reference result and
  `workers == 1`.
- **Fallback (Python):** a patched pool whose `map` yields one task's result and then raises
  `BrokenProcessPool` returns the reference result (no double count), `workers == 1` and the two-line stderr
  message; one case each for `OSError`, `PermissionError` and `NotImplementedError` raised by the
  constructor.
- **Entry guard (Python):** with `current_process().name` patched to a worker name, running the module's
  `__main__` block does not call `main()`.
- **Status line:** a run at K=5 prints `Workers: <w>` with `w > 1` immediately before `Elapsed:`; runs at
  K <= 4 and the fallback print no `Workers:` line; stdout of both equals today's.
- **Rust atomics:** marks of the same and adjacent bits from many rayon tasks give the exact union.
- **Mutation equivalents:** the Rust relaxed-load pre-check before `fetch_or` is a true equivalent (removing
  it leaves results identical; only cache traffic changes) and is declared in `.cargo/mutants.toml`
  `exclude_re` with that mechanism; any other surviving split mutant gets a killing test or an equivalent
  entry with its mechanism, never a bare exclusion.

## Requirements

- **R1.** Both languages add `pack_with_workers(root, n)` returning `(count, bitmap, workers)`; `pack(root, n)` keeps its signature (Rust `pack(root: [i64; 4], n: i64) -> Result<(i64, Vec<u64>), DescartesError>`, Python `pack(root, n) -> tuple[int, bytearray]`) and returns the first two; count and bitmap equal the serial reference walk for every valid root and `n`; `main` uses `pack_with_workers`.
- **R2.** The walk first expands the frontier breadth-first from the root's reflections, counting and marking each popped circle once, until it holds at least `SEED_TARGET = 4096` items or is empty, then walks each frontier item's subtree depth-first; the serial and parallel paths share this split.
- **R3.** `PARALLEL_MIN_N = 100_000` in both languages: when `n < PARALLEL_MIN_N`, the frontier empties before `SEED_TARGET`, or only one worker is available, no process pool and no rayon task is created and `workers` is 1; otherwise the subtrees are walked in parallel.
- **R4.** In `descartes-rs` the subtree walks run on rayon's global pool with `workers = rayon::current_num_threads()`, marks go to one shared `Vec<AtomicU64>` (relaxed load, `fetch_or` only when the bit is unset), counts are summed, the crate adds `rayon = "1"`, keeps `unsafe_code = "forbid"`, and `walk`'s `on_mark` hook stays on the serial path.
- **R5.** In `descartes.py` the subtree walks run in `concurrent.futures.ProcessPoolExecutor` with `max_workers = os.process_cpu_count() or 1` and the `fork` context on Linux (`spawn` otherwise); seeds are dealt into `4 x workers` tasks by stride (seed `i` to task `i mod T`); each task returns `(count, bytes)`, which the coordinator sums and ORs via `int.from_bytes`.
- **R6.** In `descartes.py`, when creating or using the pool raises `OSError`, `PermissionError`, `NotImplementedError` or `BrokenProcessPool`, `pack_with_workers` discards all partial pool results, computes serially from the frontier, returns `workers = 1` and the reference result, and prints `Parallel mode unavailable (<error>); falling back to serial.` then `Install project requirements and ensure OS multiprocessing semaphore support is available to re-enable parallel mode.` to stderr; exit codes are unchanged; the `if __name__ == "__main__":` block runs `main()` only when `multiprocessing.current_process().name == "MainProcess"`.
- **R7.** A packing run whose `workers` is greater than 1 prints `Workers: <workers>` to stderr once, immediately before `Elapsed: <s>s`; a run with `workers == 1` prints no `Workers:` line; stdout, the `.txt` file, the SVG and the count lines are unchanged for every input.
- **R8.** Tests in both languages, all at n <= 10^5, assert: equality with an in-module reference serial walk for the default root and roots `-11 21 24 28` and `-2 3 6 7` at n = 10^5 with `workers` equal to the runtime's count and greater than 1 on two or more cores; (Python) a spy showing the pool constructed and every task's result returned at n = 10^5 and not constructed at `PARALLEL_MIN_N - 1`; (Rust) `workers == 1` at `PARALLEL_MIN_N - 1`; literal pins of `SEED_TARGET == 4096` and `PARALLEL_MIN_N == 100_000`; the default-root frontier at n = 10^5 holding exactly 4096 seeds after a recorded coordinator count; the stride assignment; the small-frontier case; (Python) the fallback with a `map` that yields one result then raises `BrokenProcessPool` returning the reference result and the two-line message, plus constructor-raised `OSError`, `PermissionError` and `NotImplementedError` cases; the entry guard; the `Workers:` line at K=5 and its absence at K <= 4 and after the fallback; and (Rust) exact unions under concurrent marks of shared and adjacent bits.
- **R9.** `docs/superpowers/specs/2026-11-15-descartes-design.md`'s `## Amendments` withdraws N2 and amends R13 to drop "no `rayon` dependency", each with a reason naming this spec.
- **R10.** `descartes/README.md`, `descartes/descartes-rs/README.md`, `descartes/CLAUDE.md` and `descartes/descartes-rs/CLAUDE.md` state the parallel model, `PARALLEL_MIN_N`, the `Workers:` stderr line, `RAYON_NUM_THREADS` / `PYTHON_CPU_COUNT` and (Python) the fallback message; the root `CLAUDE.md` multiprocessing-fallback rule names `descartes` beside `pi`, `e` and `factorial`; the Backlog row "Parallel Descartes packing (Rust and Python)" is removed from `docs/superpowers/README.md`.
- **V1.** Build master's Rust binary and take master's `descartes.py` (from `origin/master` before this change) and run both against the new ones with `--yes --no-draw`: stdout and the `.txt` file are byte-identical for Rust K=1-8 and Python K=1-6 on the default root, and for K=1-5 on roots `-11 21 24 28` and `-2 3 6 7`.
- **V2.** Wall time and peak RSS on `claude` for Rust K=7 and 8 and Python K=5 and 6 are recorded in the PR body against the serial baseline above (7.66 s / 201.5 s; 1.66 s / 30.8 s); Rust K=8 is at least 5x faster and Python K=6 at least 3x faster.
- **V3.** `python3 -m unittest test_descartes` completes in under 15 s under `taskset -c 0-3` on `claude` (well inside cosmic-ray's 60 s per-mutant timeout), and CI is green on the PR, including `mutation-pr` with 0 survivors and 0 timeouts on changed lines in both languages.
- **N1.** No new command-line flag and no new environment variable is added by this change.
- **N2.** Stdout, the `.txt` file, the SVG and their order do not change for any input.
- **N3.** `visible()`, the renderer, the SVG and `--solve` stay serial.
- **N4.** No `unsafe` code, and no new dependency other than `rayon` in `descartes-rs`.
- **N5.** `N_MAX`, `ROOT_MAX`, the K ranges and the drawing caps do not change.

## Multi-Lens Review

Reviewed at commit: `f1ffe85`

### Goal-Fit

Finding: Worth building; premise confirmed by prototype (Rust K=8 201.5 s -> 10.62 s, Python K=6 30.8 s -> 2.08 s, both exact). (1) The Rust 10^7 exactness test cannot pass: debug serial walk 73.8 s vs nextest's 45 s cap. (2) The Python 10^6 test costs ~10x the 3.65 s suite and covers nothing 10^5 does not. (3) Split constants and BFS order are equivalent mutants under V3. (4) The fallback can double-count when `BrokenProcessPool` surfaces mid-`map`. (5) Most tests pass if the parallel path is never taken (`w >= 1`). (6) `Workers:` is decoration and breaks exact-stderr assertions; Python's task split and OR method are unspecified (strided 25x vs contiguous 18x; use `int.from_bytes`). (7) Rust-only captures the headline value; Python scope is the operator's call.
Assumption: the Python suite plus new tests stays well under cosmic-ray's 60 s timeout on a 4-vCPU runner; settled by timing under `taskset -c 0-3` and the `mutation-pr` log.
Disposition: Addressed — operator chose `Workers:` only when parallel ran and both languages (2026-11-18); the remaining fixes were applied by the author and await the operator's approval of this revision: both languages kept; `Workers:` only when workers > 1; unit tests at n <= 10^5, scale in V1; split pins, strided tasks, `int.from_bytes`, fallback discards partial results, `workers > 1` assertions; V3 adds a suite-time bound.

### Ergonomics

Finding: (1) Rust 10^7 test exceeds the 45 s cap (debug 68.65 s). (2) Python 10^6 test makes `make test`/pre-push ~45 s and the mutation gate vacuous or over the 30-minute job. (3) Most tests pass if parallel never runs; a crashing worker would fall back silently. (4) R1 vs R7: `main` cannot learn `workers` from a frozen `pack`; name the channel (`pack_with_workers`). (5) `Workers:` breaks four existing stderr assertions and adds `Workers: 1` noise to every small run. Ctrl-C, spawn cost, memory and existing knobs checked clean.
Assumption: per-mutant wall time with forking tests stays well under 60 s on a 4-vCPU runner; settled by a dispatched shard's timeout count.
Disposition: Addressed — operator chose `Workers:` only when parallel ran and both languages (2026-11-18); the remaining fixes were applied by the author and await the operator's approval of this revision: `pack_with_workers` added (R1); `Workers:` only when workers > 1, so the four K <= 3 stderr assertions are unaffected; spy and `workers > 1` tests; 10^5 ceiling; V3 timing and 0-timeout bound.

### Risk

Finding: (1) Rust 10^7 (debug 93.85 s) and Python 10^6 (30.98 s) tests break their gates; timeouts score as killed. (2) Split logic is mutation-equivalent by construction (SEED_TARGET +-1, `>=`/`>`, BFS->DFS, `4 x W`, `or 1`, the threshold literal); needs pins, a seam, or declared equivalents. (3) Tests pass if parallel never runs. (4) `on_mark` hook unaddressed. (5) Unlisted stderr assertions. (6) Context premise "other roots have comparable counts" false at fixed n (root `-11 21 24 28`: 59,337 circles at 10^5). (7) Byte-loop OR costs 4.92 s; contiguous chunks balance worse than strided. Exactness, atomics ordering, cargo-deny, uniformity, amendment form and memory checked clean.
Assumption: the shared atomic bitmap does not stall on cache-coherence traffic at K=8; refuted by goal-fit's prototype (10.62 s, 19x).
Disposition: Addressed — operator chose `Workers:` only when parallel ran and both languages (2026-11-18); the remaining fixes were applied by the author and await the operator's approval of this revision: literal and frontier pins, recorded coordinator count, stride test, declared Rust pre-check equivalent; `on_mark` stays serial-only (R4); Context premise corrected; strided tasks and `int.from_bytes` (R5).

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
