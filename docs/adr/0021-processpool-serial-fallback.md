# ADR-0021: ProcessPoolExecutor Serial Fallback for Python Availability

**Date:** 2026-04-29
**Status:** Accepted

## Context

Several Python sub-projects use `concurrent.futures.ProcessPoolExecutor` to parallelize computation — chunked swing factorial and parallel digit computation are the primary cases. Two distinct failure modes were discovered:

**Restricted environments**: On sandboxed CI runners or Docker containers without semaphore access, `ProcessPoolExecutor` raises `PermissionError` or `OSError` when attempting to acquire POSIX semaphores. The computation fails entirely rather than degrading to serial mode.

**macOS spawn context hang**: On macOS with Python 3.14+ using the `spawn` multiprocessing start method, `ProcessPoolExecutor` leaks `resource_tracker` daemons for small inputs — worker processes and tracker daemons accumulate as zombies, Python never exits after tests complete, and the pre-push hook deadlocks indefinitely. This does not appear on Linux (which defaults to `fork`) and does not appear in CI (which runs on Ubuntu). It surfaces only during local development on macOS.

A second related problem: the overhead of spawning workers (~100–200ms per worker on macOS) exceeds the computation time for small inputs. For `factorial(4)` the swing computation over 2 primes takes ~1μs serially but ~200ms via `ProcessPoolExecutor` — 200,000× slower in parallel. This inflated local test runtime from <1s to 53s and masked the orphan-leak hang.

## Decision

Every use of `ProcessPoolExecutor` must follow three rules:

1. **Minimum-threshold guard**: Parallel dispatch is gated behind a named constant (`_MIN_PARALLEL_PRIMES`, `_MIN_PARALLEL_CHUNKS`, etc.). Below the threshold, serial mode is used without attempting to spawn workers. Compute the crossover before adding parallel dispatch: if serial time < spawn cost, parallel dispatch is net-negative.

2. **Try/except fallback**: The `ProcessPoolExecutor` block is wrapped in `try/except (PermissionError, OSError)`. On failure, execution falls back to serial mode immediately and prints a warning to stdout (flushed):

   ```
   Warning: parallel execution unavailable, falling back to serial mode.
   ```

3. **Patchable threshold**: The threshold constant must be patchable in tests using `unittest.mock.patch("module._MIN_PARALLEL_PRIMES", 0)` to force the parallel branch. Without patching the threshold, the mock never fires and fallback tests pass vacuously.

The fallback path is tested by patching both the threshold constant and `ProcessPoolExecutor` at the module import site (`"module.concurrent.futures.ProcessPoolExecutor"`), not at the canonical path — following the "patch where used" rule.

## Consequences

- Python sub-projects work in restricted CI environments that cannot spawn processes.
- Pre-push hook does not hang on macOS from orphaned `resource_tracker` daemons.
- Parallel computation is only attempted when the input is large enough for parallel to beat serial plus spawn overhead.
- Tests of the fallback path require patching both the threshold and the class; a test that patches only the class and does not patch the threshold passes vacuously when the threshold guards the parallel branch.
- The `< /dev/null` pre-push hook fix (for git-pipe inheritance) does NOT prevent the macOS spawn hang — that fix addresses a different problem (git pipe blocking EOF). The threshold guard is the correct fix for the macOS hang.

## Related

- [ADR-0007: Prime swing algorithm for factorial](0007-prime-swing-factorial.md)
- [ADR-0020: Dual-mode CI — permanent pre-push hook + PR-only GitHub Actions](0020-dual-mode-ci-prepush-github-actions.md)
- [ADR-0013: Hypothesis and proptest for property-based testing](0013-hypothesis-proptest-property-based-tests.md)
