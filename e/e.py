#!/usr/bin/env python3
"""
Calculate e (Euler's number) to a user-specified number of decimal places.

Uses the Taylor series e = sum(1/n! for n=0..N) computed via binary splitting
with gmpy2/GMP (if available) for fast arbitrary-precision arithmetic.
Falls back to mpmath if gmpy2 is not installed.

Install fast backend (recommended):
    bash install_deps.sh
or manually:
    brew install gmp mpfr && pip install gmpy2   # macOS
    sudo apt install libgmp-dev libmpfr-dev && pip install gmpy2  # Debian/Ubuntu
"""

import argparse
import concurrent.futures
import math
import multiprocessing
import os
import sys
import threading
import time

import mpmath

# ---------------------------------------------------------------------------
# Optional fast backend: gmpy2 (GMP + MPFR)
# ---------------------------------------------------------------------------

try:
    import gmpy2 as _gmpy2

    _HAS_GMPY2 = True
except ImportError:
    _gmpy2 = None
    _HAS_GMPY2 = False

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_CPU_COUNT = os.cpu_count() or 1
_IO_WORKERS = max(2, min(8, _CPU_COUNT))
_PWRITE_CHUNK = 4 * 1024 * 1024  # 4 MiB per I/O worker chunk

# Cached (P_int, Q_int) from the most recent gmpy2 computation.
# Plain Python ints — always picklable for the subprocess worker.
_gmpy2_PQ_cache: tuple = ()


# ---------------------------------------------------------------------------
# Taylor series binary splitting (gmpy2 path)
# ---------------------------------------------------------------------------


def _taylor_bs(a, b):
    """
    Binary splitting for the Taylor series of e, range [a, b).

    Returns (P, Q) as gmpy2.mpz such that the partial sum
    sum_{k=a}^{b-1} 1/k! can be recovered from Q(a,b) / P(a,b).

    Leaf values:
        a=0: P=1, Q=1   (represents 1/0! = 1)
        a>0: P=a+1, Q=a+1

    Merge rule for adjacent ranges [a,m) and [m,b):
        P(a,b) = P(a,m) * P(m,b)
        Q(a,b) = Q(a,m) * P(m,b) + Q(m,b)

    Final result: e = Q(0,N) / P(0,N)
    """
    if b - a == 1:
        if a == 0:
            return _gmpy2.mpz(1), _gmpy2.mpz(1)
        val = _gmpy2.mpz(a + 1)
        return val, val
    m = (a + b) >> 1
    Pl, Ql = _taylor_bs(a, m)
    Pr, Qr = _taylor_bs(m, b)
    return Pl * Pr, Ql * Pr + Qr


def _bs_chunk_worker(a, b):
    """
    Subprocess worker: compute Taylor binary splitting for range [a, b).

    Returns (P, Q) as plain Python ints so they are always picklable,
    regardless of the gmpy2 version or platform.
    """
    P, Q = _taylor_bs(a, b)
    return int(P), int(Q)


def _tree_combine(pq_list):
    """
    Reduce a list of (P, Q) tuples using pairwise tree combination.

    Tree reduction keeps intermediate sizes balanced — each merge combines
    two chunks of similar magnitude, which is better for GMP's asymptotically
    fast multiplication algorithms than a sequential left fold.

    Combination rule for adjacent ranges [a,m) and [m,b):
        P(a,b) = P(a,m) * P(m,b)
        Q(a,b) = Q(a,m) * P(m,b) + Q(m,b)
    """
    while len(pq_list) > 1:
        next_level = []
        for i in range(0, len(pq_list), 2):
            if i + 1 < len(pq_list):
                Pl, Ql = pq_list[i]
                Pr, Qr = pq_list[i + 1]
                next_level.append((Pl * Pr, Ql * Pr + Qr))
            else:
                next_level.append(pq_list[i])
        pq_list = next_level
    return pq_list[0]


def _calculate_e_gmpy2(digits):
    """
    Compute e using Taylor series binary splitting + gmpy2/GMP.

    When _CPU_COUNT > 1 and N is large enough to justify subprocess overhead,
    splits [0, N) into _CPU_COUNT equal chunks and computes them in parallel
    using ProcessPoolExecutor.  Results are merged via tree reduction in the
    main process using gmpy2.mpz arithmetic.

    Returns (e_mpfr, P_int, Q_int) where:
    - e_mpfr  is a gmpy2.mpfr value
    - P_int, Q_int are plain Python ints (picklable)
    """
    if digits > 1:
        # Need N such that log10(N!) > digits (truncation error < 10^-digits).
        # Stirling: log10(N!) ≈ N*(log10(N) - log10(e)).  The naive estimate
        # N = digits/log10(digits) ignores the -N*log10(e) term and undershoots
        # for digits > ~340.  One Newton step corrects for it.
        d = float(digits)
        n0 = d / math.log10(d + 1)
        log_n0 = max(math.log10(n0), 1.0)
        deficit = max(0.0, d - n0 * (log_n0 - math.log10(math.e)))
        N = int(n0 + deficit / log_n0) + 50
    else:
        N = 20

    # Divide [0, N) into at most _CPU_COUNT chunks.
    # Minimum 100 terms per chunk so each worker does meaningful work.
    chunk_size = max(100, (N + _CPU_COUNT - 1) // _CPU_COUNT)
    ranges = []
    start = 0
    while start < N:
        ranges.append((start, min(start + chunk_size, N)))
        start += chunk_size
    n_workers = len(ranges)

    if n_workers > 1:
        mp_context = multiprocessing.get_context(
            "fork" if sys.platform == "linux" else "spawn"
        )
        print(f"  Parallel series: {n_workers} workers x ~{chunk_size:,} terms each")
        bar_width = 30
        try:
            with concurrent.futures.ProcessPoolExecutor(
                max_workers=n_workers, mp_context=mp_context
            ) as pool:
                futures = [pool.submit(_bs_chunk_worker, a, b) for a, b in ranges]
                completed = 0
                for _ in concurrent.futures.as_completed(futures):
                    completed += 1
                    filled = completed * bar_width // n_workers
                    bar = "#" * filled + "." * (bar_width - filled)
                    print(
                        f"\r  [{bar}] {completed}/{n_workers} chunks",
                        end="",
                        flush=True,
                    )
            print()

            # Collect results in submission order (all done; .result() is instant).
            int_results = [f.result() for f in futures]

            # Convert to gmpy2.mpz and merge via tree reduction.
            print("  Combining chunks...", end="", flush=True)
            pq_list = [(_gmpy2.mpz(P), _gmpy2.mpz(Q)) for P, Q in int_results]
            P, Q = _tree_combine(pq_list)
            print("\r  Combination complete.   ")
        except (PermissionError, OSError) as err:
            print(
                f"\nParallel mode unavailable ({err}); falling back to serial.\n"
                "Install project requirements and ensure OS multiprocessing "
                "semaphore support is available to re-enable parallel mode."
            )
            P, Q = _taylor_bs(0, N)
    else:
        P, Q = _taylor_bs(0, N)

    # Compute e = Q / P in MPFR with enough binary precision.
    prec = int(digits * 3.3219280948873626) + 100  # bits ~ digits * log2(10) + margin

    ctx = _gmpy2.get_context()
    saved_prec = ctx.precision
    ctx.precision = prec
    try:
        e_mpfr = _gmpy2.mpfr(Q) / _gmpy2.mpfr(P)
    finally:
        ctx.precision = saved_prec

    return e_mpfr, int(P), int(Q)


# ---------------------------------------------------------------------------
# String conversion helpers
# ---------------------------------------------------------------------------


def _e_to_str(e_value, digits):
    """
    Convert an e value to a decimal string with *digits* decimal places.

    Dispatches to the fast gmpy2/MPFR path for gmpy2.mpfr values, otherwise
    falls back to mpmath.nstr (pure Python).
    """
    if _HAS_GMPY2 and isinstance(e_value, _gmpy2.mpfr):
        mantissa, exp, _ = e_value.digits(10, digits + 5)
        sign = ""
        if mantissa.startswith("-"):
            sign, mantissa = "-", mantissa[1:]
        int_part = mantissa[:exp] if exp > 0 else "0"
        dec_part = mantissa[exp : digits + exp]
        return f"{sign}{int_part}.{dec_part}"
    return mpmath.nstr(e_value, digits + 1, strip_zeros=False)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def show_e_preview(e_value, preview_digits=100):
    """
    Show a preview of e with specified number of digits.

    Args:
        e_value: gmpy2.mpfr or mpmath.mpf
        preview_digits (int): number of decimal places to show
    """
    actual_preview = min(preview_digits, 200)
    print(f"Generating preview of e ({actual_preview} digits)...")
    e_str = _e_to_str(e_value, actual_preview)
    if "." in e_str:
        integer_part, decimal_part = e_str.split(".", 1)
    else:
        integer_part, decimal_part = e_str, ""
    print(f"\ne = {integer_part}.{decimal_part}...")
    print(f"(Showing first {len(decimal_part)} decimal places)")


# ---------------------------------------------------------------------------
# Module-level subprocess worker functions
# (must be at module level so spawn-mode multiprocessing can pickle them)
# ---------------------------------------------------------------------------


def _gmpy2_str_from_PQ(P_int, Q_int, digits):
    """
    Recompute e = Q / P in a subprocess and return the decimal string.
    Accepts plain Python ints (always picklable).
    """
    prec = int(digits * 3.3219280948873626) + 100

    ctx = _gmpy2.get_context()
    saved_prec = ctx.precision
    ctx.precision = prec
    try:
        P = _gmpy2.mpz(P_int)
        Q = _gmpy2.mpz(Q_int)
        e_mpfr = _gmpy2.mpfr(Q) / _gmpy2.mpfr(P)
        mantissa, exp, _ = e_mpfr.digits(10, digits + 5)
    finally:
        ctx.precision = saved_prec

    sign = ""
    if mantissa.startswith("-"):
        sign, mantissa = "-", mantissa[1:]
    int_part = mantissa[:exp] if exp > 0 else "0"
    dec_part = mantissa[exp : digits + exp]
    return f"{sign}{int_part}.{dec_part}"


def _convert_gmpy2_worker(P_int, Q_int, digits):
    """
    Subprocess worker (gmpy2 path): recompute e from integer series
    accumulators and convert to a decimal string.  Plain-int arguments
    are always picklable regardless of gmpy2 version.
    """
    return _gmpy2_str_from_PQ(P_int, Q_int, digits)


def _convert_mpmath_worker(e_value, digits):
    """
    Subprocess worker (mpmath path): convert mpmath.mpf to decimal string.
    Running in a subprocess bypasses the GIL so the main-thread progress
    display is not starved by the pure-Python mpmath.nstr call.
    """
    return mpmath.nstr(e_value, digits + 1, strip_zeros=False)


def _pwrite_all(fd, data, offset):
    """
    Write all bytes in *data* to open fd at absolute *offset* (POSIX pwrite).

    Thread-safe: pwrite does not move the file pointer, so concurrent threads
    can write non-overlapping chunks to the same fd simultaneously.
    Uses a memoryview to avoid copying large byte strings in the retry loop.
    """
    view = memoryview(data)
    written = 0
    while written < len(view):
        n = os.pwrite(fd, view[written:], offset + written)
        if n == 0:
            raise OSError("os.pwrite returned 0 — file write stalled")
        written += n
    return written


# ---------------------------------------------------------------------------
# File save — multithreaded
# ---------------------------------------------------------------------------


def save_e_to_file(e_value, digits, filename):  # noqa: C901 — multi-backend parallel I/O; TODO: split into gmpy2/mpmath helpers
    """
    Save e to file using subprocess string conversion and parallel I/O.

    Phase A — String conversion runs in a dedicated subprocess (bypasses
    the GIL).  The main thread drives a progress display by polling the
    Future, so progress remains smooth without a background thread.

      gmpy2 path: subprocess receives plain-int P, Q and recomputes the
                  final mpfr value — avoids any gmpy2 pickling uncertainty.
      mpmath path: subprocess receives the mpmath.mpf directly.

    Phase B — The resulting string is written to disk by _IO_WORKERS
    threads using os.pwrite(2), allowing non-overlapping chunks to be
    written concurrently without moving the shared file pointer.

    Args:
        e_value: gmpy2.mpfr or mpmath.mpf
        digits (int): number of decimal places
        filename (str): output filename
    """
    using_gmpy2 = _HAS_GMPY2 and isinstance(e_value, _gmpy2.mpfr)
    backend_label = "gmpy2/MPFR" if using_gmpy2 else "mpmath"

    def estimate_conversion_time(d):
        if using_gmpy2:
            if d <= 100_000:
                return max(0.05, d * 5e-8)
            if d <= 1_000_000:
                return max(0.1, d * 2e-7)
            if d <= 10_000_000:
                return max(1.0, d * 5e-6)
            return max(10.0, d * 1e-5)
        else:
            if d <= 100_000:
                return max(1.0, 0.1 + d * 5e-6)
            if d <= 1_000_000:
                return max(2.0, 0.5 + d * 2e-6)
            if d <= 10_000_000:
                return max(30.0, d * 5e-5)
            return max(60.0, d * 1e-4)

    class ProgressIndicator:
        def __init__(self, estimated_duration):
            self.running = False
            self.start_time = None
            self.estimated_duration = estimated_duration

        def start(self):
            self.running = True
            self.start_time = time.time()

        def stop(self):
            self.running = False

        def show_one_tick(self):
            if self.start_time is None:
                return
            elapsed = time.time() - self.start_time
            if elapsed <= self.estimated_duration:
                remaining = max(0, self.estimated_duration - elapsed)
                pct = (elapsed / self.estimated_duration) * 100
                bar_length = 30
                filled = int(bar_length * pct / 100)
                bar = "#" * filled + "." * (bar_length - filled)
                dots = "." * (int(elapsed * 2) % 4)
                print(
                    f"\rConverting {digits:,} digits{dots:<3} "
                    f"[{bar}] {pct:.1f}% "
                    f"Elapsed: {elapsed:.1f}s | ETA: {remaining:.1f}s",
                    end="",
                    flush=True,
                )
            else:
                dots = "." * (int(elapsed * 2) % 4)
                print(
                    f"\rConverting {digits:,} digits{dots:<3} "
                    f"[Still converting...] "
                    f"Elapsed: {elapsed:.1f}s (longer than estimated)",
                    end="",
                    flush=True,
                )

    # -- Phase A: subprocess conversion + main-thread progress ----------------

    print(f"Starting conversion of {digits:,} digits...")
    estimated_time = estimate_conversion_time(digits)
    print(f"Estimated conversion time: {estimated_time:.1f} seconds ({backend_label})")
    print(
        f"Using {_CPU_COUNT} CPU core{'s' if _CPU_COUNT != 1 else ''} "
        f"({_IO_WORKERS} I/O workers for file write)"
    )

    mp_context = multiprocessing.get_context(
        "fork" if sys.platform == "linux" else "spawn"
    )

    conversion_start = time.time()
    progress = ProgressIndicator(estimated_time)
    progress.start()

    try:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=1, mp_context=mp_context
        ) as pool:
            if using_gmpy2:
                P_int, Q_int = _gmpy2_PQ_cache
                future = pool.submit(_convert_gmpy2_worker, P_int, Q_int, digits)
            else:
                future = pool.submit(_convert_mpmath_worker, e_value, digits)

            while not future.done():
                progress.show_one_tick()
                time.sleep(0.25)

            e_str = future.result()  # re-raises any subprocess exception
    except (PermissionError, OSError) as err:
        print(
            f"\nParallel mode unavailable ({err}); falling back to serial.\n"
            "Install project requirements and ensure OS multiprocessing "
            "semaphore support is available to re-enable parallel mode."
        )
        if using_gmpy2:
            P_int, Q_int = _gmpy2_PQ_cache
            e_str = _gmpy2_str_from_PQ(P_int, Q_int, digits)
        else:
            e_str = _e_to_str(e_value, digits)
    finally:
        progress.stop()
    conversion_time = time.time() - conversion_start
    print(f"\rString conversion completed in {conversion_time:.2f} seconds" + " " * 50)

    # -- Phase B: parallel pwrite ---------------------------------------------

    print(
        f"Writing to {filename} using {_IO_WORKERS} parallel I/O worker"
        f"{'s' if _IO_WORKERS != 1 else ''}..."
    )
    write_start = time.time()

    header = (
        f"e calculated to {digits:,} decimal places using {backend_label}\n"
        + "=" * 60
        + "\n\n"
    ).encode("utf-8")
    e_bytes = e_str.encode("ascii")
    footer = f"\n\nTotal decimal places: {digits:,}".encode()

    total_file_size = len(header) + len(e_bytes) + len(footer)
    e_offset = len(header)

    chunk_starts = list(range(0, len(e_bytes), _PWRITE_CHUNK))
    total_chunks = len(chunk_starts)
    completed_chunks = 0
    _progress_lock = threading.Lock()

    fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.ftruncate(fd, total_file_size)
        _pwrite_all(fd, header, 0)
        _pwrite_all(fd, footer, e_offset + len(e_bytes))

        def write_chunk(start):
            nonlocal completed_chunks
            end = min(start + _PWRITE_CHUNK, len(e_bytes))
            _pwrite_all(fd, e_bytes[start:end], e_offset + start)
            with _progress_lock:
                completed_chunks += 1
                elapsed = time.time() - write_start
                pct = completed_chunks / total_chunks * 100
                bytes_done = min(completed_chunks * _PWRITE_CHUNK, len(e_bytes))
                rate = bytes_done / elapsed / 1024 / 1024 if elapsed > 0 else 0
                remaining = total_chunks - completed_chunks
                eta = (
                    (remaining / completed_chunks * elapsed)
                    if completed_chunks > 0
                    else 0
                )
                print(
                    f"\rFile write progress: {pct:.1f}% | "
                    f"Written: {bytes_done:,}/{len(e_bytes):,} chars | "
                    f"ETA: {eta:.1f}s | "
                    f"Rate: {rate:.1f} MB/s",
                    end="",
                    flush=True,
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=_IO_WORKERS) as io_pool:
            futures_list = [io_pool.submit(write_chunk, cs) for cs in chunk_starts]
            for f in concurrent.futures.as_completed(futures_list):
                f.result()  # re-raises any thread exception

    finally:
        os.close(fd)

    print()
    write_time = time.time() - write_start
    print(f"File write completed in {write_time:.2f} seconds")
    print(f"Total file operation time: {(conversion_time + write_time):.2f} seconds")


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Calculate e (Euler's number) to a specified number of decimal places.",
        epilog=(
            "Run without arguments to use the interactive prompts, or provide "
            "the number of digits directly."
        ),
    )
    parser.add_argument(
        "digits",
        nargs="?",
        type=int,
        help="number of decimal places to calculate",
    )
    return parser.parse_args(argv)


def get_target_digits(args):
    """Get the requested digit count from CLI args or interactive input."""
    if args.digits is not None:
        if args.digits < 1:
            raise ValueError("Please enter a positive number of decimal places.")
        if args.digits > 1000000:
            print("Warning: Very large numbers may take a long time to calculate.")
        return args.digits

    while True:
        try:
            user_input = input(
                "Enter the number of decimal places to calculate e (1-1000000): "
            )
            target_digits = int(user_input)
            if target_digits < 1:
                print("Please enter a positive number.")
                continue
            if target_digits > 1000000:
                print("Warning: Very large numbers may take a long time to calculate.")
                confirm = (
                    input(f"Continue with {target_digits} digits? (y/n): ")
                    .lower()
                    .strip()
                )
                if confirm not in ["y", "yes"]:
                    continue
            return target_digits
        except ValueError:
            print("Please enter a valid integer.")


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------


def calculate_e(digits=1000):
    """
    Calculate e to the specified number of decimal places.

    Tries the fast Taylor/gmpy2 path first; falls back to mpmath if
    gmpy2 is not installed.

    Returns:
        gmpy2.mpfr | mpmath.mpf: high-precision value of e.
    """
    print(f"Calculating e to {digits:,} decimal places...")
    print(f"Running on {_CPU_COUNT} CPU core{'s' if _CPU_COUNT != 1 else ''}...")

    if _HAS_GMPY2:
        print(
            f"Backend: Taylor series / gmpy2 {_gmpy2.version()} "
            f"(GMP {_gmpy2.mp_version()}, MPFR {_gmpy2.mpfr_version()})"
        )
        start = time.time()
        e_mpfr, P_int, Q_int = _calculate_e_gmpy2(digits)
        elapsed = time.time() - start
        print(f"\nCalculation completed in {elapsed:.2f} seconds")
        # Cache P and Q as plain Python ints for the subprocess worker.
        global _gmpy2_PQ_cache
        _gmpy2_PQ_cache = (P_int, Q_int)
        return e_mpfr

    print(
        f"Backend: mpmath {mpmath.__version__} "
        f"(install gmpy2 for faster computation - see install_deps.sh)"
    )
    print("This may take a while for high precision calculations...")
    mpmath.mp.dps = digits + 50
    start = time.time()
    e_value = +mpmath.e  # unary + forces evaluation to mpf at current dps
    elapsed = time.time() - start
    print(f"\nCalculation completed in {elapsed:.2f} seconds")
    return e_value


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Main function to execute e calculation."""
    try:
        args = parse_args()

        print("High-Precision e Calculator")
        print("=" * 40)

        target_digits = get_target_digits(args)
        e_result = calculate_e(target_digits)

        if target_digits <= 1_000_000:
            preview_digits = min(100, target_digits)
            show_e_preview(e_result, preview_digits)
        else:
            print(
                f"\nSkipping preview for {target_digits:,} digits (too large for quick preview)"
            )

        if target_digits > 10000:
            filename = f"e_{target_digits}_digits.txt"
            print(
                f"\nFor {target_digits:,} digits, saving to file for better performance..."
            )
            save_e_to_file(e_result, target_digits, filename)
            print(f"\nFull precision e saved to {filename}")
        else:
            print(
                f"\nWould you like to display all {target_digits:,} digits? (y/n): ",
                end="",
            )
            response = input().lower().strip()
            if response in ["y", "yes"]:
                e_str = _e_to_str(e_result, target_digits)
                print(f"\ne = {e_str}")
                print(f"\nTotal digits: {target_digits:,}")
            else:
                filename = f"e_{target_digits}_digits.txt"
                save_e_to_file(e_result, target_digits, filename)
                print(f"\nFull precision e saved to {filename}")

    except KeyboardInterrupt:
        print("\n\nCalculation interrupted by user.")
        sys.exit(1)
    except ValueError as error:
        print(f"\nError: {error}")
        sys.exit(1)
    except (RuntimeError, OSError, ArithmeticError, EOFError, MemoryError) as ex:
        print(f"\nError occurred during calculation: {ex}")
        sys.exit(1)


if __name__ == "__main__":
    # Guard against re-execution in multiprocessing worker subprocesses.
    if multiprocessing.current_process().name == "MainProcess":
        try:
            import mpmath
        except ImportError:
            print("Error: mpmath is required.  Run: pip install mpmath")
            sys.exit(1)

        main()
