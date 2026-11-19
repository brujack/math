# ADR-0045: descartes-rs builds its rayon pool explicitly and falls back to serial

**Date:** 2026-11-19
**Status:** Accepted

## Context

descartes-rs gained parallel packing in math#234 (spec `2026-11-18-descartes-parallel-packing-design.md`). The first implementation followed the other rayon crates (pi-rs, e-rs, factorial-rs, prime-rs; ADR-0005): it called `rayon::current_num_threads()` and `par_iter` on rayon's global pool, which is built lazily on first use.

Phase 3's bug-scan found that the lazy build panics when the operating system refuses a thread, for example under `ulimit -u` or a container pids limit below the CPU count: `The global thread pool has not been initialized.: ThreadPoolBuildError { kind: IOError(... WouldBlock) }`, exit 101. By then the CLI had already created the `.txt` output, so an earlier good result was truncated. `RAYON_NUM_THREADS=1` did not avoid it, because a one-thread pool still spawns a thread. master's descartes-rs had no threads, so this was a regression for descartes, and the Python twin already falls back to serial under the same limit (ADR-0021).

Alternatives considered: ship as is, matching the other four rayon crates, with one Backlog row to fix all five together; or fix all five crates in the same PR. The operator chose to fix descartes-rs now and backlog the other four (2026-11-18).

## Decision

descartes-rs never touches rayon's global pool from production code. Above `PARALLEL_MIN_N`, with frontier seeds left, `pack_with_builder` builds a pool with `default_pool()` (`rayon::ThreadPoolBuilder::new().build()`) and runs the subtree walks inside `pool.install`; when it is already running inside a rayon pool (`rayon::current_thread_index()` is `Some`), it uses that pool. If the build returns an error, the walk runs serially with `workers = 1` and the error text is returned in `Packing::fallback`; the CLI prints `Parallel mode unavailable (<error>); falling back to serial.` and `Raise the process or thread limit (ulimit -u, a container pids limit) to re-enable parallel mode.` to stderr before `Elapsed:`, exits 0 and writes the same output as a serial run. Below the threshold no pool is built, so small runs start no threads.

## Consequences

- A thread limit degrades descartes-rs to serial instead of crashing it, matching the Python fallback; spec R11 pins the behaviour, and tests inject a refusing builder (`spawn_handler` returning an error) so CI covers it without a real `ulimit`.
- One pool is built per run; rayon stops any threads already started when a later spawn fails, so a partial build leaks nothing.
- `RAYON_NUM_THREADS` still bounds the worker count, because `ThreadPoolBuilder::new()` reads it; `tests/cli.rs` pins that through a subprocess.
- descartes-rs now differs from pi-rs, e-rs, factorial-rs and prime-rs, which keep the global pool and its panic. The Backlog row "Serial fallback when the rayon pool cannot be built" tracks giving them the same treatment.
- The fallback lines print after the `Saved` lines rather than during the computation as in Python, so a run that falls back and then fails its SVG write exits 1 without them; tracked as a Backlog row.

## Related

- [ADR-0005](0005-rayon-for-shared-memory-parallelism.md): rayon for shared-memory parallelism
- [ADR-0021](0021-processpool-serial-fallback.md): ProcessPoolExecutor serial fallback for Python
- [Spec](../superpowers/specs/2026-11-18-descartes-parallel-packing-design.md): R4 amended and R11 added 2026-11-18
- math#234
