# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

This repository contains a small Python CLI for calculating π to high precision. It uses the Chudnovsky algorithm with `gmpy2`/GMP (fast path) and falls back to `mpmath` if `gmpy2` is not installed.

Current structure:

- `pi.py`: interactive calculator script (Python, gmpy2/GMP + mpmath fallback)
- `pi-rs/`: Rust implementation — Chudnovsky + Rayon + rug/GMP/MPFR (best for >50M digits)
- `install_deps.sh`: rendered from `scripts/crate_templates/python/install_deps.sh`: GMP + MPFR (Homebrew, apt or dnf/yum) and every pinned Python package
- `pi_1000000_digits.txt`: sample/generated output file
- `pi_10000000_digits.txt`: sample/generated output file

## Rust Implementation (`pi-rs/`)

The Rust binary targets >50M digit workloads where the Python subprocess IPC overhead becomes significant.

Key differences from Python:

- Uses `rayon::join()` for recursive parallel binary splitting — threads share memory, zero IPC/serialisation cost
- `rug` wraps GMP (`Integer`) and MPFR (`Float`) directly — same C libraries as Python's gmpy2
- Parallel file I/O via `FileExt::write_at` (POSIX pwrite equivalent) dispatched by rayon

Build (requires GMP + MPFR — run `install_deps.sh` first):

```bash
cd pi-rs
make pi          # cargo build --release (binary in target/release/pi)
make install     # build, then copy to ${XDG_BIN_HOME:-~/.local/bin}/pi
./target/release/pi [digits]
```

A `Makefile` is provided in `pi-rs/`:

- `make pi` — runs `cargo build --release`; the binary stays in `target/release/pi`
- `make install` — builds, then copies the binary to `${XDG_BIN_HOME:-~/.local/bin}/pi` (created if missing)
- `make lint` — runs `cargo clippy -- -D warnings`
- `make test` — runs lint then `cargo test`
- `make clean` — runs `cargo clean`

### Rust Code Layout (`pi-rs/src/main.rs`)

- `BS_PAR_THRESHOLD`: switch from `rayon::join()` to serial recursion below this range size (512 terms); rayon work-stealing handles load-balancing
- `BS_LEAF_COUNT` (`static AtomicU64`): counts completed leaf nodes during `bs()`; read every 200 ms by the series progress thread to display percentage
- `struct Pqt { p, q, t: Integer }`: accumulator for a Chudnovsky range `[a, b)`
- `fn bs(a, b)`: recursive binary splitting; uses `rayon::join()` above threshold, serial recursion below
- `fn bs_leaf(a)`: leaf computation with `rug::Integer`; increments `BS_LEAF_COUNT` on every call
- `fn bs_merge(l, r)`: combines two adjacent ranges
- `fn format_series_progress(completed, n)`: pure formatter for the compute progress line (testable in isolation)
- `fn compute_pi(digits)`: resets `BS_LEAF_COUNT`, spawns a progress thread that prints series completion % every 200 ms (a `recv_timeout(200 ms)` loop on an `mpsc` channel, so it exits the moment `bs` finishes), runs `bs(0, n)`, joins the thread, then builds `rug::Float` and calls `pi_to_string`
- `fn pi_to_string(pi, digits)`: uses `pi.to_string_radix(10, Some(digits+5))`, trims to exact decimal places
- `fn format_write_progress(written, pi_total, elapsed)`: pure formatter for the write progress line (testable in isolation)
- `fn write_pi_file(dir, pi_str, digits)`: `#[cfg(unix)]` — builds `dir/pi_<digits>_digits.txt`, pre-allocates with `file.set_len()`, spawns a progress thread reporting write % and MB/s every 200 ms, parallel pwrite via rayon `par_chunks` (each chunk updates an `Arc<AtomicU64>` byte counter), joins thread and prints final MB/s; returns the written `PathBuf`
- `fn save_pi(dir, pi_str, digits, out)`: `#[cfg(unix)]` — announces the filename then delegates to `write_pi_file`
- `fn fmt_int(n)`: formats with thousands separators
- `fn read_line_from<R: BufRead>(reader)`: reads one trimmed line from any `BufRead`
- `fn confirm_large_digits_with<R, W, E>(reader, out, err, n)`: y/n confirmation for large digit counts
- `fn prompt_digits_with<R, W, E>(reader, out, err)`: trait-injected interactive prompt (loops until valid; defers to `confirm_large_digits_with` for n > 1_000_000)
- `fn run<R, W, E>(cli, reader, out, err, dir)`: orchestration — returns process exit code; injects all I/O so tests can use pipes + temp dirs
- `fn main()`: thin wrapper — locks stdin/stdout, passes unlocked `io::stderr()` (a held `StderrLock` deadlocks the progress thread's `eprint!`), calls `run`, exits with the returned code

### rug Arithmetic Note

`rug::Integer` operator overloading uses lazy "incomplete" types: `&Integer * &Integer` returns `MulIncomplete<'_>`, not `Integer`. Always wrap with `Integer::from(...)` before using the result in further operations:

```rust
// Correct:
Integer::from(&l.p * &r.p)
Integer::from(&r.q * &l.t) + Integer::from(&l.p * &r.t)
// Wrong (will not compile):
&l.p * &r.p + &l.q * &r.q
```

## Environment

Each implementation has its own installer:

```bash
bash pi/install_deps.sh        # pi.py — GMP + MPFR and the pinned Python packages
bash pi/pi-rs/install_deps.sh  # pi-rs — GMP + MPFR, Rust toolchain, cargo-tarpaulin
```

Requirements summary:

| Dependency          | Required for                                |
| ------------------- | ------------------------------------------- |
| Python 3            | `pi.py`, tests                              |
| `mpmath`            | `pi.py` fallback path (required)            |
| `gmpy2`             | `pi.py` fast path (optional, 5–50× speedup) |
| `coverage`          | `make coverage`                             |
| GMP + MPFR (C libs) | `gmpy2`, `pi-rs` via rug                    |
| Rust 1.85+          | `pi-rs`                                     |
| `cargo-tarpaulin`   | `cargo tarpaulin` (Rust coverage)           |

## Running The Script

A `Makefile` is provided in `pi/`:

- `make run` — runs `python3 pi.py`
- `make lint` — runs `ruff check .`
- `make test` — runs lint then `pytest test_pi.py -v`
- `make coverage` — runs tests and prints a line coverage report
- `make clean` — removes `__pycache__` and `.coverage`

Run the calculator with:

```bash
make run
# or directly:
python3 pi.py
```

CLI contract: `python3 pi.py [DIGITS] [--show] [--yes] [--smoke]`.

- With `DIGITS` it never prompts. `DIGITS >= LARGE_RUN_THRESHOLD` (1,000,001) exits 1 naming `--yes` unless `--yes` is passed.
- With no `DIGITS` at a terminal it prompts for the digit count (and a `(y/n)` confirmation at or above the threshold, EOF reading as no with exit 0). On a non-TTY stdin with no `DIGITS` it exits 2; EOF at the number prompt exits 1.
- The result is always written to `pi_<digits>_digits.txt`; `--show` additionally prints the digit string (the file's digit line) on its own line.
- `--smoke` runs at `SMOKE_SIZE` (10000) and takes no `DIGITS`.
- `make test` also runs `python3 ../scripts/cli_contract.py pi.py`.

## Code Layout

The project is intentionally simple and centered in `pi.py`.

Chudnovsky / gmpy2 functions (used when gmpy2 is installed):

- `_chudnovsky_bs(a, b)`: recursive binary splitting; returns `(P, Q, T)` as `gmpy2.mpz`.
- `_bs_chunk_worker(a, b)`: module-level subprocess worker that computes `_chudnovsky_bs(a, b)` and returns plain Python ints for pickling safety.
- `_tree_combine(pqt_list)`: merges a list of `(P, Q, T)` results via pairwise tree reduction (more GMP-efficient than a linear fold for equal-sized chunks).
- `_calculate_pi_gmpy2(digits)`: splits `[0, N)` into `_CPU_COUNT` chunks, dispatches them to a `ProcessPoolExecutor`, tree-combines the results, then computes the final π as `gmpy2.mpfr`; returns `(pi_mpfr, Q_int, T_int)`.
- `_gmpy2_str_from_QT(Q_int, T_int, digits)`: recomputes π from integer accumulators and converts to decimal string (used in subprocess).
- `_gmpy2_mpfr_to_str(pi_mpfr, digits)`: fast in-process string conversion for preview.

Module-level worker functions (must stay at module level for multiprocessing pickling):

- `_convert_gmpy2_worker(Q_int, T_int, digits)`: subprocess worker for the gmpy2 path; receives plain Python ints (always picklable).
- `_convert_mpmath_worker(mpf_tuple, prec, digits)`: subprocess worker for the mpmath fallback path; takes the exact `_mpf_` tuple plus precision bits and converts under `mpmath.workprec` (a pickled mpf is rebuilt at 53 bits under `spawn`).
- `_pwrite_all(fd, data, offset)`: writes bytes to a file descriptor at an absolute offset using `os.pwrite(2)`; thread-safe.
- `_progress_lock` (inside `save_pi_to_file`): `threading.Lock` that serialises `completed_chunks` updates and the progress `print` across the I/O worker threads.

String conversion:

- `_pi_to_str(pi_value, digits)`: unified dispatch — uses `_gmpy2_mpfr_to_str` for `gmpy2.mpfr`, otherwise `mpmath.nstr`.

CLI:

- `SMOKE_SIZE` (10000), `LARGE_RUN_THRESHOLD` (1_000_001): contract constants, pinned by `TestCliContractConstants`.
- `parse_args(argv: list[str] | None = None) -> argparse.Namespace`: `argparse` namespace with optional `size` positional plus `--show`, `--yes`, `--smoke`.
- `refuse_large_run(size, yes)`: exits 1 naming `--yes` when `size >= LARGE_RUN_THRESHOLD` and not `yes`.
- `get_target_digits(args)`: returns `args.size` (after `refuse_large_run`) if provided, otherwise loops on interactive stdin input; validates that the value is a positive integer.

Main functions:

- `calculate_pi_high_precision(digits)`: tries gmpy2 Chudnovsky first, falls back to mpmath; caches `(Q_int, T_int)` in `_gmpy2_QT_cache` for the subprocess. Returns a `gmpy2.mpfr` (fast path) or `mpmath.mpf` (fallback path).
- `show_pi_preview(pi_value, preview_digits)`: prints a short preview of the computed digits.
- `save_pi_to_file(pi_value, digits, filename)`: two-phase save — subprocess conversion then parallel pwrite file write; returns the digit string it wrote.
- `main(argv: list[str] | None = None) -> None`: top-level entry point; calls `parse_args()`, `get_target_digits()`, `calculate_pi_high_precision()`, `show_pi_preview()`, always `save_pi_to_file()`, and with `--show` prints the digit string `save_pi_to_file` returned, before the "saved to" line.

Module-level constants / state:

- `_gmpy2`: the gmpy2 module, or `None` when the import failed. Code checks `_gmpy2 is not None` (pyright does not carry a caller's check into a callee); gmpy2-only functions call `_require_gmpy2()`, which raises `RuntimeError` when it is `None`. Tests simulate absence by patching `_gmpy2` to `None`.
- `_HAS_GMPY2`: `True` if gmpy2 imported successfully at startup; used only by tests for `skipUnless`, never by `pi.py` logic.
- `_gmpy2_QT_cache`: `(Q_int, T_int)` from the most recent gmpy2 calculation; used to pass picklable data to the subprocess worker.
- `_CPU_COUNT`: result of `os.cpu_count()`.
- `_IO_WORKERS`: number of I/O worker threads (scales with cores, capped at 8).
- `_PWRITE_CHUNK`: chunk size per I/O worker (4 MiB).
- `_CHU_A`, `_CHU_B`, `_CHU_C3_OVER_24`: Chudnovsky series constants.

## Important Behavior

- **gmpy2 path (fast)**: uses the Chudnovsky binary-splitting algorithm with GMP big-integer arithmetic (`gmpy2.mpz`), then MPFR for the final floating-point value. Each Chudnovsky term contributes ≈14.18 decimal digits; recursion depth is O(log N), well within Python's stack limit. The series computation is parallelised across all available CPU cores: `[0, N)` is split into `_CPU_COUNT` equal chunks (minimum 100 terms each), each chunk is computed in a subprocess, and the results are merged in the main process via `_tree_combine` (pairwise tree reduction keeps intermediate GMP multiply sizes balanced).
- **mpmath fallback**: sets precision to `digits + 50` and uses `mpmath.pi`. Large runs are dominated by converting the `mpmath` value to a string, not by the calculation itself.
- **gmpy2.mpfr is a C extension type** and does not support arbitrary attribute assignment. The `(Q_int, T_int)` accumulator ints are stored in `_gmpy2_QT_cache` (module-level) and passed as plain Python ints to the subprocess worker, avoiding any gmpy2 pickling uncertainty.
- String conversion runs in a `ProcessPoolExecutor` subprocess (1 worker) to bypass the GIL; the main thread polls `future.done()` to drive the progress display — no background thread is used.
- File writing uses `ThreadPoolExecutor` (`_IO_WORKERS` threads) with `os.pwrite(2)` so multiple threads can write non-overlapping chunks concurrently. The file is pre-allocated with `os.ftruncate()` before any writes. A `threading.Lock` (`_progress_lock`) guards `completed_chunks` increments and the progress print inside `write_chunk` to prevent data races on the shared counter and interleaved terminal output.
- On macOS the `spawn` multiprocessing context is used; on Linux `fork` is used.
- The `if __name__ == "__main__":` guard checks `multiprocessing.current_process().name == "MainProcess"` to prevent `main()` from running in worker subprocesses (required on macOS where `spawn` re-executes the script in each worker).
- Very large output files can be slow to generate and should not be casually regenerated during routine edits.

## Keeping This File Up To Date

**Update this file whenever you change the code.** Future Claude sessions rely on it — stale docs are worse than none. Specifically:

- New or renamed function / constant → update Code Layout
- Makefile target added or removed → update the Makefile bullet list here and in `README.md`
- Dependency added → update Environment section and `scripts/crate_templates/python/install_deps.sh`, then `python3 scripts/render_crate_files.py --write`
- Test class added or coverage % changes → update the Testing coverage table here and in `README.md`
- Behaviour or algorithm change → update Important Behavior

Also update the top-level `CLAUDE.md` if the change affects the repository overview or quick-reference targets.

## Editing Guidance

- **Write the failing test first** for all new or changed functions, then add the minimum implementation. Tests go in `test_pi.py`.
- Keep changes minimal and preserve the single-file CLI structure unless a refactor is clearly necessary.
- Preserve the current interactive behavior (number prompt, large-run `(y/n)` confirmation) unless the task explicitly changes UX.
- Ensure every script in the repository supports `-h` and `--help` with accurate command-line usage text.
- Be careful with performance changes inside `save_pi_to_file`, since that function handles the main large-number bottleneck.
- `_convert_gmpy2_worker`, `_convert_mpmath_worker`, `_bs_chunk_worker`, and `_pwrite_all` must remain at module level — moving them inside a function or class will break multiprocessing pickling.
- Do not remove the `current_process().name == "MainProcess"` check from the `if __name__ == "__main__":` block — it is required to prevent infinite subprocess spawning on macOS (where `spawn` re-executes the script in each worker).
- Do not attempt to set arbitrary attributes on `gmpy2.mpfr` objects — they are C extension types with fixed slots. Use `_gmpy2_QT_cache` to pass data between the calculation and the subprocess worker.
- Avoid committing regenerated large output files unless the task explicitly requires updating them.

## Testing

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass. Never write implementation before the test. Tests must be added in the same commit as the code they cover — both Python and Rust.

Every test must cover more than the happy path. Three categories are required for every function:

- **Boundary value tests** — empty/zero/null input, single vs multiple elements, min/max valid values, one above/below valid range
- **Error path tests** — what happens on failure, dependency failure, partial failure
- **State transition tests** — before/after assertions, no unintended side effects, idempotency

### Python (`test_pi.py`)

Run the full suite:

```bash
make test      # pytest test_pi.py -v
make coverage  # run tests + print coverage report
```

Or directly:

```bash
pytest test_pi.py -v
python3 -m pytest test_pi.py -v   # if pytest is installed
```

gmpy2-dependent tests are automatically skipped when gmpy2 is not installed.

#### Test coverage (94% line coverage, 113 tests)

| Class                                | Tests | Notes                                                                   |
| ------------------------------------ | ----- | ----------------------------------------------------------------------- |
| `TestTreeCombine`                    | 7     | Pure Python — always runs; includes empty-list boundary                 |
| `TestPwriteAll`                      | 4     | POSIX pwrite — always runs                                              |
| `TestPwriteAllStall`                 | 1     | Error path — always runs                                                |
| `TestChudnovskyBS`                   | 7     | Skipped without gmpy2                                                   |
| `TestBsChunkWorker`                  | 3     | Skipped without gmpy2                                                   |
| `TestGmpy2Conversions`               | 5     | Skipped without gmpy2                                                   |
| `TestConvertGmpy2Worker`             | 2     | Skipped without gmpy2                                                   |
| `TestConvertMpmathWorker`            | 3     | Always runs                                                             |
| `TestMpmathFallback`                 | 2     | Always runs                                                             |
| `TestPiToStr`                        | 6     | Format + known-digit checks                                             |
| `TestPiAccuracy`                     | 4     | End-to-end vs reference π                                               |
| `TestShowPiPreview`                  | 4     | stdout capture                                                          |
| `TestSavePiToFile`                   | 5     | File write + content checks                                             |
| `TestCalculatePiParallel`            | 1     | Skipped without gmpy2                                                   |
| `TestCalculatePiGmpy2PhaseAFallback` | 1     | OSError triggers serial fallback in `_calculate_pi_gmpy2`               |
| `TestGetTargetDigits`                | 7     | Argument path; boundaries 999_999 / 1_000_000 / 1_000_001, `--yes`      |
| `TestCliContractConstants`           | 2     | Pins `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD`                             |
| `TestRefuseLargeRun`                 | 1     | Threshold boundaries                                                    |
| `TestParseArgs`                      | 7     | Flags, `--smoke`, non-TTY exit 2                                        |
| `TestPiToStrNegativeSign`            | 1     | Negative-mpfr sign-strip branch in `_gmpy2_mpfr_to_str`                 |
| `TestShowPiPreviewNoDecimal`         | 1     | Else branch when preview string lacks `.`                               |
| `TestGetTargetDigitsInteractive`     | 5     | Interactive prompt: valid, retries, large-N decline + accept            |
| `TestSavePiEstimateAndProgress`      | 1     | Exercises `estimate_conversion_time` tiers via patched ProcessPool      |
| `TestSavePiToFilePhaseAFallback`     | 1     | OSError triggers serial fallback in `save_pi_to_file`                   |
| `TestMain`                           | 13    | Always-write, `--show` (returned string, ordering), overwrite, refusal before any write, `--yes` proceed, error handlers |
| `TestEntryPointGuard`                | 1     | Module runs via subprocess (`if __name__ == "__main__"` block)          |
| `TestProcessPoolPermissionError`     | 1     | PermissionError triggers serial fallback in `save_pi_to_file`           |
| `TestProcessPoolSemaphoreExhaustion` | 2     | OSError and errno.ENOSPC trigger serial fallback in `save_pi_to_file`   |
| `TestMissingGmpy2`                   | 1     | mpmath path used when `_gmpy2` is patched to None                       |
| `TestRequireGmpy2`                   | 3     | `_require_gmpy2` raises without gmpy2, returns the module with it       |
| `TestSavePiToFileWithoutGmpy2`       | 2     | `save_pi_to_file` takes the mpmath path when `_gmpy2` is None (incl. spawn-context precision)|
| `TestFileWritePermissionError`       | 1     | `main()` exits 1 on `PermissionError` when creating output file         |

#### Type checking

`pyrightconfig.json` runs pyright at `standard` with `stubPath` `../typings`: gmpy2 ships no stubs, so the vendored `typings/gmpy2/__init__.pyi` (exact, never claiming more than gmpy2 does at runtime; no `Any`, and `object` only for `__eq__`/`__ne__` `other`, both guarded by `tests/test_gmpy2_stub.py`, including string annotations) types the names e and pi use. Add a name to the stub before using a new gmpy2 attribute. Pyright at `standard` over e/ and pi/ is the primary gate for attribute use; the stub guard's alias scan (direct, `import ... as` and simple-assignment aliases) is only a cheap backstop. Run `cd pi && pyright`.

#### Adding new tests

- Add tests to `test_pi.py` alongside any new or changed function.
- Use `@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")` on classes that require gmpy2.
- Accuracy tests should verify against the `PI_REF` constant (first 50 known decimal places of π).
- Use `_quiet_pi(digits)` (defined in the test file) to suppress stdout when calling `calculate_pi_high_precision` inside tests.

### Rust (`pi-rs/`)

Tests live in a `#[cfg(test)] mod tests` block at the bottom of `src/main.rs`.

Run the full suite:

```bash
cd pi-rs
cargo test
```

Check coverage (requires `cargo-tarpaulin`):

```bash
cargo install cargo-tarpaulin   # one-time install
cargo tarpaulin --out Stdout
```

#### Test coverage (92.39% line coverage, 62 tests: 56 unit + 6 integration)

| Area                                    | Tests | Notes                                                                                                 |
| --------------------------------------- | ----- | ----------------------------------------------------------------------------------------------------- |
| `fmt_int`                               | 5     | zero, sub-thousand, thousands, millions, billions                                                     |
| `bs_leaf`                               | 4     | base case, index-1 formulas, even/odd sign, counter delta                                             |
| `bs_merge`                              | 1     | result matches manual merge of two leaves                                                             |
| `bs` split consistency                  | 3     | n=4, n=8, and n=600 (exercises rayon::join branch above 512 threshold)                                |
| `pi_to_string`                          | 7     | format, exact length, no exponent, known digits, single decimal place, exponent strip, no-dot path    |
| `compute_pi`                            | 2     | end-to-end accuracy at 10 and 50 decimal places                                                       |
| `format_series_progress`                | 4     | zero/partial/complete/zero-total                                                                      |
| `format_write_progress`                 | 4     | normal speed, zero-elapsed, zero-total, complete                                                      |
| `read_line_from`                        | 3     | trims newline, empty input, trims whitespace                                                          |
| `confirm_large_digits_with`             | 4     | "y", "yes", "n", other input                                                                          |
| `prompt_digits_with`                    | 6     | valid, minimum=1, zero retry, non-numeric retry, large decline + accept                               |
| `write_pi_file`                         | 4     | contents, filename format, idempotency, missing-dir error                                             |
| `save_pi`                               | 1     | writes file + announces                                                                               |
| `run`                                   | 5     | digits=0 → exit 1, display=y, save=n, no-arg prompts, digits>10000 auto-saves                         |
| `run_returns_err_on_stdout_failure`     | 1     | `run()` propagates Err when stdout write fails (FailWriter injection)                                 |
| `run_returns_err_on_stderr_failure`     | 1     | `run()` propagates Err when stderr write fails (FailWriter injection)                                 |
| `tests/cli.rs` (subprocess integration) | 6     | arg=0 exit 1, arg=10 + "y" displays, arg=10 + "n" saves, no-arg + "10\\ny\\n" prompts, unwritable dir, 5,000,000 digits exits within 60 s with a progress tick (stderr-lock deadlock regression) |

Uncovered lines (~17/224):

- Compute and write progress-thread loop bodies (timing-dependent — only fire after a 200 ms tick)
- `pi_to_string` pad branch when raw is shorter than wanted (defensive; unreachable for normal MPFR floats)
- Write speed `else 0.0` branch when `elapsed <= 0.001` (writes always take >1 ms)
- `#[cfg(not(unix))]` fallback stubs in `run` (macOS/Linux tests only hit the unix path)

#### Adding new tests

- Add tests to the `#[cfg(test)] mod tests` block in `src/main.rs`.
- Use `const PI_REF: &str = "3.14159265358979323846264338327950288419716939937510"` for accuracy assertions.
- `BS_LEAF_COUNT` is a global atomic — check deltas, not absolute values, since tests run in parallel threads.

## Notes

- Existing `.txt` files are generated artifacts and may be large.
