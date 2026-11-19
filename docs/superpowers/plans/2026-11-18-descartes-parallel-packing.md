# descartes parallel packing Implementation Plan

spec: docs/superpowers/specs/2026-11-18-descartes-parallel-packing-design.md

> **Status: DONE** — merged via math#234 (6fa6ae8, 2026-11-19). Rust K=8 196.95 s to 11.62 s, Python K=6 30.82 s to 2.76 s on 48 CPUs; output byte-identical to master.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Walk the descartes packing in parallel (rayon in Rust, a `fork`/`spawn` `ProcessPoolExecutor` in Python) with results byte-identical to the serial walk.

**Architecture:** One children helper holds the growth guard. A breadth-first frontier of `SEED_TARGET = 4096` seeds is followed by independent depth-first subtree walks, run serially below `PARALLEL_MIN_N = 100_000` and in parallel above it. `pack_with_workers` returns `(count, bitmap, workers)`; `pack` wraps it.

**Tech Stack:** Python 3.14 stdlib (`concurrent.futures`, `multiprocessing`), unittest; Rust `rayon = "1"`, `std::sync::atomic`, nextest.

## Global Constraints

- Exact equality with the serial reference walk is the contract; stdout, the `.txt`, the SVG and the count lines never change (N2).
- `PARALLEL_MIN_N = 100_000`, `SEED_TARGET = 4096` in both languages; `pack(root, n)` signatures unchanged; `pack_with_workers(root, n) -> (count, bitmap, workers)`.
- Python: `W = os.process_cpu_count() or 1`; `_mp_context()` fork on Linux, spawn otherwise; `_tasks(seeds, W)` makes `4 x W` strided tasks; `map`; commit pool results only after all return; fallback on `OSError`, `NotImplementedError`, `BrokenProcessPool` with pi's two lines on stderr. No entry guard, no `PermissionError` member.
- Rust: rayon current pool, `workers = rayon::current_num_threads()`, one shared `Vec<AtomicU64>` (relaxed load, `fetch_or` only when unset), `unsafe_code = "forbid"` kept.
- `Workers: <w>` on stderr immediately before `Elapsed:` only when `workers > 1`.
- Unit tests at n <= 10^5, never skipped on core count: Python patches `os.process_cpu_count`; Rust uses `rayon::ThreadPoolBuilder::new().num_threads(k).build().unwrap().install(..)`. Pool-reaching non-exactness tests use root `(-11, 21, 24, 28)`; small frontier `(-300, 301, 90300, 90301)`; 4097 pin `(-5, 10, 10, 15)`.
- Tests are unittest `TestCase` methods (cosmic-ray runs `python3 -m unittest`); every changed-line mutant is killed or a run-confirmed equivalent with its mechanism.
- Mutation repro runs only after committing (`scripts/mutation-pr-diff.sh` reads committed state).
- Tasks run sequentially: `descartes-rs/tests/parity.rs` runs `../descartes.py` inside `cargo test`.

## Verification (session level)

1. `make -C descartes test`, `make -C descartes/descartes-rs test`, root `make test` exit 0.
2. V1: build `origin/master`'s Rust binary in a `git archive` scratch copy and copy master's `descartes.py`; run old vs new with `--yes --no-draw` in scratch dirs: stdout and `.txt` byte-identical for Rust K=1-8, Python K=1-6 (default root) and K=1-5 on `-11 21 24 28` and `-2 3 6 7`.
3. V2: `/usr/bin/time -f '%e %M'` Rust K=7, 8 and Python K=5, 6; Rust K=8 <= 40.3 s, Python K=6 <= 10.3 s.
4. V3: `cd descartes && /usr/bin/time -f %e taskset -c 0-3 python3 -m unittest test_descartes` < 15 s; PR CI green including `mutation-pr`.

---

### Task 1: Python split, serial path and pack_with_workers

```yaml-task
id: 1
description: Restructure descartes.py pack into a shared children helper, BFS frontier and subtree walks with pack_with_workers (serial only, workers=1), plus split pins and reference-walk tests
role: executor
model: sonnet
tdd: required
requirements: [R1, R2]
acceptance:
  - cmd: 'cd descartes && python3 -m unittest test_descartes.TestPackSplit'
    exit_code: 0
  - cmd: make -C descartes test
    exit_code: 0
  - cmd: 'cd descartes && pyright'
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_equivalent
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py, descartes/mutants-equivalent.toml]
depends_on: []
```

**Interfaces:** Produces `SEED_TARGET = 4096`, `PARALLEL_MIN_N = 100_000`, `_children(quad, j, n)` (yields `(child_quad, i)`; holds `quad[i] < k <= n` and `i != j`), `_frontier(root, n) -> tuple[int, bytearray, list[tuple[list[int], int]]]` (coordinator count, bitmap, seeds), `_walk_subtrees(seeds, n, bitmap) -> int`, `pack_with_workers(root, n) -> tuple[int, bytearray, int]`; `pack` returns its first two.

- [ ] Write `TestPackSplit`: a module-level reference walk copied from today's `pack` loop; `pack_with_workers` equals it at n = 10^5 for `(-1, 2, 2, 3)`, `(-11, 21, 24, 28)`, `(-2, 3, 6, 7)` with `workers == 1`; pins `SEED_TARGET == 4096`, `PARALLEL_MIN_N == 100_000`; `len(_frontier((-1,2,2,3), 10**5)[2]) == 4096` with the coordinator count measured on your implementation (expected 2049 + the root's 3; record what you measure); `(-5, 10, 10, 15)` at 10^5 gives 4097 seeds (record its count); `(-300, 301, 90300, 90301)` at 10^5 gives 0 seeds and the reference result. Run: fails.
- [ ] Implement; `pack` becomes `return pack_with_workers(root, n)[:2]` with `_check_n`/`_check_reduced_root` still first. `test_dfs_terminates_when_root_invariant_is_broken` (~line 570) must still pass unchanged and still exercise `_children`.
- [ ] Re-confirm `mutants-equivalent.toml` entries whose anchors moved; commit; then `d=$(mktemp) && scripts/mutation-pr-diff.sh origin/master descartes "$d" && make -C descartes mutants-diff DIFF="$d"` (from the worktree root): 0 surviving.

### Task 2: Python parallel executor and fallback

```yaml-task
id: 2
description: Add _mp_context, _tasks, the ProcessPoolExecutor path above PARALLEL_MIN_N with commit-after-all merge, worker-count rules and the serial fallback in descartes.py
role: executor
model: sonnet
tdd: required
requirements: [R3, R5, R6]
acceptance:
  - cmd: 'cd descartes && python3 -m unittest test_descartes.TestPackParallel'
    exit_code: 0
  - cmd: make -C descartes test
    exit_code: 0
  - cmd: 'cd descartes && pyright'
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_equivalent
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py, descartes/mutants-equivalent.toml]
depends_on: [1]
```

**Interfaces:** Consumes Task 1. Produces `_mp_context()`, `_tasks(seeds, workers) -> list[list[...]]` (`T = 4 * workers`, seed `i` in task `i % T`), a module-level `_walk_task(task, n) -> tuple[int, bytes]`.

- [ ] Write `TestPackParallel` (all with `os.process_cpu_count` patched): 2 workers → exact reference for the three roots at 10^5 and `workers == 2`; `None` and `1` → `workers == 1` and `ProcessPoolExecutor` patched to fail if called; threshold `PARALLEL_MIN_N - 1` → 1, `PARALLEL_MIN_N` → 2 (root `(-11, 21, 24, 28)`); small frontier with 2 workers → 1; `_tasks(list(range(10)), 2)` → 8 tasks, seed `i` in task `i % 8`; `_mp_context()` → `fork` with `sys.platform` patched `"linux"`, `spawn` with `"darwin"`; fallback on `(-11, 21, 24, 28)` at 10^5: a fake pool whose `map` yields one real task result then raises `BrokenProcessPool`, and constructors raising `OSError("no sem")` and `NotImplementedError("x")` — each returns the reference count and bitmap, `workers == 1`, and stderr exactly `Parallel mode unavailable (<err>); falling back to serial.\nInstall project requirements and ensure OS multiprocessing semaphore support is available to re-enable parallel mode.\n`. Run: fails.
- [ ] Implement per R5/R6 (OR via `int.from_bytes(..., "little")` so bit order matches `_mark`); commit; run the mutation repro; 0 surviving.

### Task 3: Python CLI wiring, Workers line and existing tests

```yaml-task
id: 3
description: Make descartes.py main use pack_with_workers, print Workers line when workers > 1, migrate the four tests that patch pack, and meet the V3 suite-time bound
role: executor
model: sonnet
tdd: required
requirements: [R1, R7, R8]
acceptance:
  - cmd: 'cd descartes && python3 -m unittest test_descartes.TestWorkersLine'
    exit_code: 0
  - cmd: make -C descartes test
    exit_code: 0
  - cmd: 'cd descartes && pyright'
    exit_code: 0
  - cmd: 'cd descartes && python3 -c "import subprocess as s,time,sys; t=time.time(); r=s.run(''taskset -c 0-3 python3 -m unittest test_descartes''.split(),capture_output=True); d=time.time()-t; print(round(d,2)); sys.exit(0 if r.returncode==0 and d<15 else 1)"'
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py, descartes/mutants-equivalent.toml]
depends_on: [2]
```

- [ ] Write `TestWorkersLine`: CLI K=5 with 2 workers patched → stderr ends `Workers: 2\nElapsed: <d>.<dd>s\n` (the `Workers:` line immediately before `Elapsed:`) and stdout equals the serial run's; K=4 → no `Workers:`; fallback path → no `Workers:`. Run: fails.
- [ ] Implement in `_run_packing`. Move the patches in `test_k_boundaries_reach_pack_with_ten_to_the_k` (~2530), `test_unwritable_target_exits_1_before_pack_runs` (~2584), `test_file_is_opened_before_pack` (~2605) and `test_huge_terminal_limit_is_4000_for_a_large_n` (~2778) from `pack` to `pack_with_workers`, returning `(count, bitmap, 1)`, keeping their assertions; confirm the K=6 legs no longer run a real 10^6 packing.
- [ ] Commit; mutation repro; 0 surviving.

### Task 4: Rust split, serial path and pack_with_workers

```yaml-task
id: 4
description: Restructure descartes-rs walk into a shared children helper, BFS frontier and subtree walks with pack_with_workers (serial, workers=1), keeping the on_mark budget hook, plus pins and frontier tests
role: executor
model: sonnet
tdd: required
requirements: [R1, R2]
acceptance:
  - cmd: 'cd descartes/descartes-rs && cargo test --lib split_'
    exit_code: 0
    stdout_match: 'split_'
  - cmd: make -C descartes/descartes-rs test
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_exclusions
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/src/lib.rs, descartes/descartes-rs/.cargo/mutants.toml]
depends_on: [3]
```

**Interfaces:** Produces `pub const SEED_TARGET: usize = 4096`, `pub const PARALLEL_MIN_N: i64 = 100_000`, `pub fn pack_with_workers(root: [i64; 4], n: i64) -> Result<(i64, Vec<u64>, usize), DescartesError>`; `pack` returns the first two; `walk` keeps `on_mark` for every popped circle.

- [ ] Write lib tests `split_*`: equality with the existing independent walk (see `pack_agrees_with_an_independent_walk`, ~line 1171) at n = 10^5 for the three roots with `workers == 1`; the const pins; frontier seeds 4096 with the recorded coordinator count for the default root, 4097 for `[-5, 10, 10, 15]`, 0 for `[-300, 301, 90300, 90301]`. Run: fails.
- [ ] Implement; `walk_terminates_when_the_root_invariant_is_broken` (~1354) and `walk_on_a_valid_root_counts_every_circle_once` (~1367) pass unchanged. Update the `mutants.toml` `svg_solve` anchor if lines shift; commit; `scripts/mutation-pr-diff.sh origin/master descartes/descartes-rs /tmp/claude-1000/t4.diff && make -C descartes/descartes-rs mutants-diff DIFF=/tmp/claude-1000/t4.diff`: 0 missed.

### Task 5: Rust rayon executor and atomic bitmap

```yaml-task
id: 5
description: Add rayon, the shared AtomicU64 bitmap and the parallel subtree walk above PARALLEL_MIN_N with workers = current_num_threads in descartes-rs, with fixed-pool tests
role: executor
model: sonnet
tdd: required
requirements: [R3, R4]
acceptance:
  - cmd: 'cd descartes/descartes-rs && cargo test --lib parallel_'
    exit_code: 0
    stdout_match: 'parallel_'
  - cmd: make -C descartes/descartes-rs test
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_exclusions
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/src/lib.rs, descartes/descartes-rs/Cargo.toml, descartes/descartes-rs/Cargo.lock, descartes/descartes-rs/.cargo/mutants.toml]
depends_on: [4]
```

- [ ] Write `parallel_*` tests inside `ThreadPoolBuilder` pools: 2 threads → exact for the three roots at 10^5, `workers == 2`; 1 thread → `workers == 1`; threshold `PARALLEL_MIN_N - 1` → 1 and `PARALLEL_MIN_N` → 2 (root `[-11, 21, 24, 28]`); small frontier with 2 threads → 1; concurrent marks of the same and adjacent bits from many tasks give the exact union. Run: fails.
- [ ] Add `rayon = "1"` to `[dependencies]`; implement per R4; commit; Rust mutation repro; 0 missed (a timeout beside a catch is green).

### Task 6: Rust CLI Workers line

```yaml-task
id: 6
description: Make descartes-rs run_packing use pack_with_workers and print Workers line to stderr before Elapsed only when workers > 1
role: executor
model: sonnet
tdd: required
requirements: [R1, R7]
acceptance:
  - cmd: 'cd descartes/descartes-rs && cargo test --bins workers_line'
    exit_code: 0
    stdout_match: 'workers_line'
  - cmd: make -C descartes/descartes-rs test
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/src/main.rs, descartes/descartes-rs/tests/cli.rs]
depends_on: [5]
```

- [ ] Write `workers_line_*` tests in `main.rs` (run `run`/`piped` inside a 2-thread `ThreadPoolBuilder` pool via `install`): K=5 → stderr has `Workers: 2` immediately before `Elapsed:` and stdout equals the serial output; K=4 → no `Workers:`. Run: fails.
- [ ] Implement at `run_packing` (~line 424); commit; Rust mutation repro; 0 missed.

### Task 7: Docs and spec amendments

```yaml-task
id: 7
description: Docs-only (no behaviour change) — document the parallel model in the four descartes docs, amend the 2026-11-15 spec N2/R13, remove the backlog row
role: executor
model: sonnet
tdd: not-applicable
requirements: [R9, R10]
acceptance:
  - cmd: 'for f in descartes/README.md descartes/descartes-rs/README.md descartes/CLAUDE.md descartes/descartes-rs/CLAUDE.md; do command grep -qF "PARALLEL_MIN_N" "$f" && command grep -qF "Workers:" "$f" && command grep -qF "RAYON_NUM_THREADS" "$f" && command grep -qF "PYTHON_CPU_COUNT" "$f" || exit 1; done; command grep -qF "falling back to serial" descartes/CLAUDE.md'
    exit_code: 0
  - cmd: 'command grep -qE "^- N2 withdrawn — .*2026-11-18-descartes-parallel-packing" docs/superpowers/specs/2026-11-15-descartes-design.md && command grep -qE "^- R13 -> .*— .*2026-11-18-descartes-parallel-packing" docs/superpowers/specs/2026-11-15-descartes-design.md && python3 ~/.claude/scripts/spec_contract.py docs/superpowers/specs/2026-11-15-descartes-design.md >/dev/null && ! command grep -qF "| Parallel Descartes packing (Rust and Python) |" docs/superpowers/README.md'
    exit_code: 0
max_retries: 2
files_touched: [descartes/README.md, descartes/descartes-rs/README.md, descartes/CLAUDE.md, descartes/descartes-rs/CLAUDE.md, docs/superpowers/specs/2026-11-15-descartes-design.md, docs/superpowers/README.md]
depends_on: [6]
```

State in each doc: subtree split, `PARALLEL_MIN_N` (serial at K <= 4 on the default root), `Workers: <w>` on stderr before `Elapsed:` when more than one worker ran, `RAYON_NUM_THREADS` / `PYTHON_CPU_COUNT` bound the count; in `descartes/CLAUDE.md` the two-line fallback message on stderr (unlike pi's stdout) and the new functions in Code Layout; in `descartes-rs/CLAUDE.md` `pack_with_workers`, the atomic bitmap and the rayon dependency (replace the "no `rayon`" sentence). In the 2026-11-15 spec append under `## Amendments`: `- N2 withdrawn — superseded by 2026-11-18-descartes-parallel-packing-design.md` and `- R13 -> <R13's text with ", Cargo.toml with no rug and no rayon dependency" changed to ", Cargo.toml with no rug dependency"> — rayon allowed by 2026-11-18-descartes-parallel-packing-design.md`. Remove the Backlog row. These files are read by no suite; the orchestrator runs root `make test` after this task.

## Non-goal check

Fresh reviewer (Opus), 2026-11-18, against N1-N5 of the spec:

- N1 CLEAR — `RAYON_NUM_THREADS` / `PYTHON_CPU_COUNT` are existing runtime variables only documented in Task 7; no code reads them. Resolution: none needed.
- N2 CLEAR — `Workers:` and the fallback message go to stderr; stdout and the `.txt` stay byte-identical. Resolution: none needed.
- N3 CLEAR — no task touches `visible()`, the renderer, the SVG or `--solve`. Resolution: none needed.
- N4 CLEAR — only `rayon = "1"` is added and `unsafe_code = "forbid"` is kept; Python uses the stdlib. Resolution: none needed.
- N5 CLEAR — Task 4 moves only the `svg_solve` mutants anchor; no constant changes. Resolution: none needed.
