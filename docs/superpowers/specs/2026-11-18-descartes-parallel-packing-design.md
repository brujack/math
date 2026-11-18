# descartes: parallel packing in Rust and Python

- **Status:** Draft
- **Date:** 2026-11-18
- **Scope:** `descartes/descartes.py`, `descartes/descartes-rs/` (both halves; identical results)

## Context

The packing search is a single-threaded depth-first walk in both languages, and at the top K values it is
now the bottleneck. Measured 2026-11-18 on `claude` (Threadripper 3960X, 48 threads, default root,
`--no-draw`, `/usr/bin/time`):

| program                  | K   | wall    | peak RSS |
| ------------------------ | --- | ------- | -------- |
| `descartes-rs` (release) | 6   | 0.33 s  | 5.6 MB   |
| `descartes-rs`           | 7   | 7.66 s  | 30 MB    |
| `descartes-rs`           | 8   | 201.5 s | 276 MB   |
| `descartes.py`           | 5   | 1.66 s  | 20 MB    |
| `descartes.py`           | 6   | 30.8 s  | 33 MB    |

The 2026-11-15 descartes spec deferred this with N2 ("No parallel packing: no `rayon` and no threads in
the packing search"), backed by the Backlog row "Build only if V1 shows serial is too slow". The figures
above meet that condition. Population: one machine, default root only; other roots have comparable counts
(the 2026-11-17 SVG spec measured 3,116-3,339 circles at the 1000 cap for every root tried).

The four other parallel sub-projects set the pattern: Rust `pi`, `e`, `factorial` and `prime` use `rayon`
(`rayon = "1"`) across every core with no flag; Python `pi`, `e` and `factorial` use
`concurrent.futures.ProcessPoolExecutor` (`fork` on Linux, `spawn` elsewhere) and, per the root
`CLAUDE.md`, fall back to serial with an explicit message when the pool fails.

The walk is a pure function of a stack item `(quad, j)`: each item's subtree is independent of every other
item's, and the outputs are order-independent (`count` is a sum, the curvature bitmap a union). A parallel
walk can therefore reproduce the serial result exactly; exact equality is the correctness contract.

Pool cost, measured 2026-11-18 (Python 3.14.8): a 48-worker `fork` `ProcessPoolExecutor` starts and stops
in 0.085 s, against a serial `pack` of 0.078 s at n = 10^4 and 1.52 s at n = 10^5. Parallel work below
10^5 cannot win, so both languages keep it serial there.

## Design

### One split, two executors

`pack(root, n)` keeps its signature and result in both languages (Rust
`pack(root, n) -> Result<(i64, Vec<u64>), DescartesError>`, Python `pack(root, n) -> tuple[int, bytearray]`).
Internally it now has two stages:

1. **Frontier.** Count and mark the root's positive circles, seed the root's reflections as today, then
   expand the stack breadth-first: pop the oldest item, count and mark it, push its admissible children
   (the same growth guard as today). Stop when the frontier holds at least `SEED_TARGET = 4096` items or is
   empty. Every circle the coordinator pops is counted exactly once, as in the serial walk.
2. **Subtrees.** Each remaining frontier item is the root of an independent subtree, walked depth-first
   exactly as today's loop walks its stack. The serial path walks them one after another on the calling
   thread; the parallel path hands them to the executor.

Both paths share the frontier and subtree code, so the serial path exercises the same split it is compared
against. The partition depends only on the root and `n`, never on the core count.

### When it runs in parallel

`PARALLEL_MIN_N = 100_000` in both languages. `n < PARALLEL_MIN_N`, or a frontier that empties before
reaching `SEED_TARGET`, runs serially without creating a pool or threads. With the default root that is
K <= 4 serial and K >= 5 parallel. `--smoke` (K=2) and the CLI contract therefore stay serial.

### Rust

Subtree walks run on rayon's global pool (`par_iter` over the frontier). Marks go to one shared
`Vec<AtomicU64>` of the same length as today's bitmap: a mark loads the word with `Ordering::Relaxed` and
calls `fetch_or` only when the bit is unset, so the heavily repeated low curvatures are read, not written,
after their first mark. Each task returns its count and the counts are summed. The atomic bitmap is
converted to the existing `Vec<u64>` before returning. No `unsafe` (the crate forbids it). Peak memory stays
at one bitmap (12.5 MB at n = 10^8) rather than one per thread. Workers are `rayon::current_num_threads()`.
The dependency is `rayon = "1"`, as in the other four crates.

### Python

Subtree walks run in `concurrent.futures.ProcessPoolExecutor(max_workers=W, mp_context=...)` with the
`fork` context on Linux and `spawn` elsewhere, `W = os.process_cpu_count() or 1`. The frontier is split
into `4 x W` tasks; each task walks its seeds and returns `(count, bytearray)`; the coordinator sums the
counts and ORs the bitmaps into its own. The worker function is module-level so it pickles under `spawn`.

**Fallback.** If creating or using the pool raises (`OSError`, `NotImplementedError`,
`concurrent.futures.process.BrokenProcessPool`, `PermissionError`), `pack` prints
`Parallel mode unavailable (<error>); falling back to serial.` and, on the next line,
`Install project requirements and ensure OS multiprocessing semaphore support is available to re-enable parallel mode.`
to stderr (pi's wording, as the root `CLAUDE.md` multiprocessing rule requires), walks the subtrees serially
and returns the same result. Exit codes do not change.

**Entry-point guard.** As in `pi.py`, the `if __name__ == "__main__":` block also checks
`multiprocessing.current_process().name == "MainProcess"`, so a `spawn` worker (macOS) re-importing the
script never re-runs `main()`.

### Status line

Each packing run prints `Workers: <w>` to stderr once, immediately before `Elapsed: <s>s`: the thread or
process count used, `1` when the run was serial (below the threshold, a small frontier, or after the
fallback). Stdout, the `.txt` file, the SVG, the count lines and their order do not change.

### Unchanged

`visible()`, the braille renderer, the SVG and `--solve` stay serial: the drawing caps bound them
(at most 4000 for braille, `min(10^K, 1000 x |outer curvature|)` for the SVG).

### Spec bookkeeping

The 2026-11-15 spec's N2 is withdrawn and its R13 (which requires "no `rayon` dependency") is amended,
through that spec's `## Amendments`. The Backlog row "Parallel Descartes packing (Rust and Python)" is
removed on merge.

## Testing

TDD in both languages. Every exactness test compares against a reference serial walk kept in the test
module (today's loop, copied), so a defect shared by the new serial and parallel paths still fails.

- Exactness: parallel `pack` equals the reference `(count, bitmap)` for the default root at n = 10^5 and
  10^6 (Rust also 10^7), and for roots `-11 21 24 28` and `-2 3 6 7` at n = 10^5.
- Threshold: at `n = PARALLEL_MIN_N - 1` no pool or rayon task is created (Python: `ProcessPoolExecutor`
  patched to fail the test if constructed; Rust: a counting seam on the parallel entry); at
  `n = PARALLEL_MIN_N` the parallel path runs.
- Small frontier: a root and `n` whose tree empties before `SEED_TARGET` give the reference result.
- Fallback (Python): `ProcessPoolExecutor` patched to raise `OSError("no sem")` gives the reference result,
  stderr `Parallel mode unavailable (no sem); falling back to serial.` followed by the semaphore-support line,
  and `Workers: 1`; one case each for `OSError`, `PermissionError`, `NotImplementedError` and
  `BrokenProcessPool` (raised from the pool's `map`, not its constructor).
- Entry guard (Python): running `descartes.py` as a module from a non-main process name does not call `main()`.
- Status line: a parallel run prints `Workers: <w>` with `w >= 1` immediately before `Elapsed:`; a serial
  run prints `Workers: 1`; stdout of both equals today's.
- Rust atomics: concurrent marks of the same and adjacent bits from many tasks give the exact union.

## Requirements

- **R1.** In both languages `pack(root, n)` keeps its signature (Rust `pack(root: [i64; 4], n: i64) -> Result<(i64, Vec<u64>), DescartesError>`, Python `pack(root, n) -> tuple[int, bytearray]`) and returns a count and bitmap equal to the serial reference walk for every valid root and `n`.
- **R2.** `pack` first expands the DFS frontier breadth-first from the root's reflections, counting and marking each popped circle once, until the frontier holds at least `SEED_TARGET = 4096` items or is empty, then walks each frontier item's subtree depth-first; the serial and parallel paths share this split.
- **R3.** `PARALLEL_MIN_N = 100_000` in both languages: when `n < PARALLEL_MIN_N` or the frontier empties before `SEED_TARGET`, `pack` creates no process pool and no rayon task; otherwise it walks the subtrees in parallel.
- **R4.** In `descartes-rs` the subtree walks run on rayon's global pool, marks go to one shared `Vec<AtomicU64>` bitmap (relaxed load, `fetch_or` only when the bit is unset), counts are summed, the crate adds `rayon = "1"` and still sets `unsafe_code = "forbid"`.
- **R5.** In `descartes.py` the subtree walks run in `concurrent.futures.ProcessPoolExecutor` with `max_workers = os.process_cpu_count() or 1` and the `fork` context on Linux (`spawn` otherwise), split into `4 x workers` tasks that each return `(count, bytearray)`, which the coordinator sums and ORs.
- **R6.** In `descartes.py`, when creating or using the pool raises `OSError`, `NotImplementedError`, `PermissionError` or `BrokenProcessPool`, `pack` prints `Parallel mode unavailable (<error>); falling back to serial.` then `Install project requirements and ensure OS multiprocessing semaphore support is available to re-enable parallel mode.` to stderr, computes serially and returns the reference result; the exit code is unchanged; and the `if __name__ == "__main__":` block runs `main()` only when `multiprocessing.current_process().name == "MainProcess"`.
- **R7.** Each packing run in both languages prints `Workers: <w>` to stderr once, immediately before `Elapsed: <s>s`, where `w` is the thread or process count used and `1` for a serial run; stdout, the `.txt` file, the SVG and the count lines are unchanged for every input.
- **R8.** Tests in both languages assert: equality with a reference serial walk kept in the test module for the default root at n = 10^5 and 10^6 (Rust also 10^7) and for roots `-11 21 24 28` and `-2 3 6 7` at n = 10^5; no pool or rayon task at `n = PARALLEL_MIN_N - 1` and the parallel path at `n = PARALLEL_MIN_N`; the small-frontier case; the Python fallback message, `Workers: 1` and result; the `Workers:` line placement; and (Rust) exact unions under concurrent marks of shared and adjacent bits.
- **R9.** `docs/superpowers/specs/2026-11-15-descartes-design.md`'s `## Amendments` withdraws N2 and amends R13 to drop "no `rayon` dependency", each with a reason naming this spec.
- **R10.** `descartes/README.md`, `descartes/descartes-rs/README.md`, `descartes/CLAUDE.md` and `descartes/descartes-rs/CLAUDE.md` state the parallel model, `PARALLEL_MIN_N`, the `Workers:` stderr line and (Python) the fallback message; the root `CLAUDE.md` multiprocessing-fallback rule names `descartes` beside `pi`, `e` and `factorial`; the Backlog row "Parallel Descartes packing (Rust and Python)" is removed from `docs/superpowers/README.md`.
- **V1.** Build master's Rust binary and take master's `descartes.py` (from `origin/master` before this change) and run both against the new ones with `--yes --no-draw`: stdout and the `.txt` file are byte-identical for Rust K=1-8 and Python K=1-6 on the default root, and for K=1-5 on roots `-11 21 24 28` and `-2 3 6 7`.
- **V2.** Wall time and peak RSS on `claude` for Rust K=7 and 8 and Python K=5 and 6 are recorded in the PR body against the serial baseline above (7.66 s / 201.5 s; 1.66 s / 30.8 s); Rust K=8 is at least 5x faster and Python K=6 at least 3x faster.
- **V3.** CI is green on the PR, including `mutation-pr` with 0 survivors on changed lines in both languages.
- **N1.** No new command-line flag and no new environment variable is added by this change.
- **N2.** Stdout, the `.txt` file, the SVG and their order do not change for any input.
- **N3.** `visible()`, the renderer, the SVG and `--solve` stay serial.
- **N4.** No `unsafe` code, and no new dependency other than `rayon` in `descartes-rs`.
- **N5.** `N_MAX`, `ROOT_MAX`, the K ranges and the drawing caps do not change.
