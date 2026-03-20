
#!/usr/bin/env python3
"""
Calculate π to a user-specified number of decimal places.

Uses the Chudnovsky algorithm with gmpy2/GMP (if available) for a 5-50x
speedup over the mpmath fallback.  File writing uses parallel I/O workers
via os.pwrite(2), optimised for Apple Silicon and Linux x64.

Install fast backend (recommended):
    bash install_deps.sh
or manually:
    brew install gmp mpfr && pip install gmpy2   # macOS
    sudo apt install libgmp-dev libmpfr-dev && pip install gmpy2  # Debian/Ubuntu
"""

import argparse
import concurrent.futures
import multiprocessing
import mpmath
import os
import sys
import threading
import time

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

# Cached (Q, T) from the most recent gmpy2 Chudnovsky computation.
# Plain Python ints — always picklable for the subprocess worker.
_gmpy2_QT_cache: tuple = ()

# Chudnovsky series constants (plain Python ints; no gmpy2 dependency).
# Each term contributes ≈14.1816 decimal digits of π.
_CHU_A = 13591409
_CHU_B = 545140134
_CHU_C3_OVER_24 = 640320 ** 3 // 24  # 10939058860032000


# ---------------------------------------------------------------------------
# Chudnovsky binary splitting (gmpy2 path)
# ---------------------------------------------------------------------------

def _chudnovsky_bs(a, b):
    """
    Binary splitting for the Chudnovsky π series, range [a, b).

    Returns (P, Q, T) as gmpy2.mpz such that

        Σ_{k=a}^{b-1} term(k)  =  T(a,b) / Q(a,b)

    Full series (a=0, b=N) satisfies: π = 426880 √10005 · Q / T
    """
    if b - a == 1:
        if a == 0:
            return _gmpy2.mpz(1), _gmpy2.mpz(1), _gmpy2.mpz(_CHU_A)
        az = _gmpy2.mpz(a)
        P = _gmpy2.mpz(6 * a - 5) * _gmpy2.mpz(2 * a - 1) * _gmpy2.mpz(6 * a - 1)
        Q = az ** 3 * _gmpy2.mpz(_CHU_C3_OVER_24)
        T = P * (_gmpy2.mpz(_CHU_A) + _gmpy2.mpz(_CHU_B) * az)
        if a & 1:
            T = -T
        return P, Q, T
    m = (a + b) >> 1
    Pl, Ql, Tl = _chudnovsky_bs(a, m)
    Pr, Qr, Tr = _chudnovsky_bs(m, b)
    return Pl * Pr, Ql * Qr, Qr * Tl + Pl * Tr


def _bs_chunk_worker(a, b):
    """
    Subprocess worker: compute Chudnovsky binary splitting for range [a, b).

    Returns (P, Q, T) as plain Python ints so they are always picklable,
    regardless of the gmpy2 version or platform.
    """
    P, Q, T = _chudnovsky_bs(a, b)
    return int(P), int(Q), int(T)


def _tree_combine(pqt_list):
    """
    Reduce a list of (P, Q, T) tuples using pairwise tree combination.

    Tree reduction keeps intermediate sizes balanced — each merge combines
    two chunks of similar magnitude, which is better for GMP's asymptotically
    fast multiplication algorithms than a sequential left fold.

    Combination rule for adjacent ranges [a,m) and [m,b):
        P(a,b) = P(a,m) * P(m,b)
        Q(a,b) = Q(a,m) * Q(m,b)
        T(a,b) = Q(m,b) * T(a,m)  +  P(a,m) * T(m,b)
    """
    while len(pqt_list) > 1:
        next_level = []
        for i in range(0, len(pqt_list), 2):
            if i + 1 < len(pqt_list):
                Pl, Ql, Tl = pqt_list[i]
                Pr, Qr, Tr = pqt_list[i + 1]
                next_level.append((Pl * Pr, Ql * Qr, Qr * Tl + Pl * Tr))
            else:
                next_level.append(pqt_list[i])
        pqt_list = next_level
    return pqt_list[0]


def _calculate_pi_gmpy2(digits):
    """
    Compute π using Chudnovsky binary splitting + gmpy2/GMP.

    When _CPU_COUNT > 1 and N is large enough to justify subprocess overhead,
    splits [0, N) into _CPU_COUNT equal chunks and computes them in parallel
    using ProcessPoolExecutor.  Results are merged via tree reduction in the
    main process using gmpy2.mpz arithmetic.

    Returns (pi_mpfr, Q_int, T_int) where:
    - pi_mpfr  is a gmpy2.mpfr value (used for preview)
    - Q_int, T_int are plain Python ints (picklable; used in subprocess
      for full-precision string conversion)
    """
    N = digits // 14 + 10  # terms needed; each gives ≈14.18 decimal digits

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
            'fork' if sys.platform == 'linux' else 'spawn'
        )
        print(
            f"  Parallel series: {n_workers} workers "
            f"× ~{chunk_size:,} terms each"
        )
        bar_width = 30
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=n_workers, mp_context=mp_context
        ) as pool:
            futures = [pool.submit(_bs_chunk_worker, a, b) for a, b in ranges]
            completed = 0
            for _ in concurrent.futures.as_completed(futures):
                completed += 1
                filled = completed * bar_width // n_workers
                bar = '█' * filled + '░' * (bar_width - filled)
                print(
                    f"\r  [{bar}] {completed}/{n_workers} chunks",
                    end="", flush=True,
                )
        print()

        # Collect results in submission order (all done; .result() is instant).
        int_results = [f.result() for f in futures]

        # Convert to gmpy2.mpz and merge via tree reduction.
        print("  Combining chunks...", end="", flush=True)
        pqt_list = [
            (_gmpy2.mpz(P), _gmpy2.mpz(Q), _gmpy2.mpz(T))
            for P, Q, T in int_results
        ]
        _, Q, T = _tree_combine(pqt_list)
        print("\r  Combination complete.   ")
    else:
        _, Q, T = _chudnovsky_bs(0, N)

    # Compute π = 426880 √10005 · Q / T in MPFR with enough binary precision.
    prec = int(digits * 3.3219280948873626) + 100  # bits ≈ digits·log₂(10) + margin

    ctx = _gmpy2.get_context()
    saved_prec = ctx.precision
    ctx.precision = prec
    try:
        sqrt_10005 = _gmpy2.sqrt(_gmpy2.mpfr(10005))
        pi_mpfr = _gmpy2.mpfr(426880) * sqrt_10005 * _gmpy2.mpfr(Q) / _gmpy2.mpfr(T)
    finally:
        ctx.precision = saved_prec

    return pi_mpfr, int(Q), int(T)


# ---------------------------------------------------------------------------
# String conversion helpers
# ---------------------------------------------------------------------------

def _gmpy2_str_from_QT(Q_int, T_int, digits):
    """
    Recompute π = 426880 √10005 · Q / T in a subprocess and return the
    decimal string.  Accepts plain Python ints (always picklable).
    """
    prec = int(digits * 3.3219280948873626) + 100

    ctx = _gmpy2.get_context()
    saved_prec = ctx.precision
    ctx.precision = prec
    try:
        Q = _gmpy2.mpz(Q_int)
        T = _gmpy2.mpz(T_int)
        sqrt_10005 = _gmpy2.sqrt(_gmpy2.mpfr(10005))
        pi_mpfr = _gmpy2.mpfr(426880) * sqrt_10005 * _gmpy2.mpfr(Q) / _gmpy2.mpfr(T)
        mantissa, exp, _ = pi_mpfr.digits(10, digits + 5)
    finally:
        ctx.precision = saved_prec

    sign = ''
    if mantissa.startswith('-'):
        sign, mantissa = '-', mantissa[1:]
    int_part = mantissa[:exp] if exp > 0 else '0'
    dec_part = mantissa[exp:digits + 1]
    return f"{sign}{int_part}.{dec_part}"


def _gmpy2_mpfr_to_str(pi_mpfr, digits):
    """
    Convert a gmpy2.mpfr π value to a decimal string (preview / small counts).

    mpfr.digits(base, n) → (mantissa, exp, prec_bits)
    where  value == 0.mantissa × base^exp.
    For π ≈ 3.14159…: mantissa = '314159…', exp = 1.
    """
    mantissa, exp, _ = pi_mpfr.digits(10, digits + 5)
    sign = ''
    if mantissa.startswith('-'):
        sign, mantissa = '-', mantissa[1:]
    int_part = mantissa[:exp] if exp > 0 else '0'
    dec_part = mantissa[exp:digits + 1]
    return f"{sign}{int_part}.{dec_part}"


def _pi_to_str(pi_value, digits):
    """
    Convert a π value to a decimal string with *digits* decimal places.

    Dispatches to the fast gmpy2/MPFR path for gmpy2.mpfr values, otherwise
    falls back to mpmath.nstr (pure Python).
    """
    if _HAS_GMPY2 and isinstance(pi_value, _gmpy2.mpfr):
        return _gmpy2_mpfr_to_str(pi_value, digits)
    return mpmath.nstr(pi_value, digits + 1, strip_zeros=False)


# ---------------------------------------------------------------------------
# Module-level subprocess worker functions
# (must be at module level so spawn-mode multiprocessing can pickle them)
# ---------------------------------------------------------------------------

def _convert_gmpy2_worker(Q_int, T_int, digits):
    """
    Subprocess worker (gmpy2 path): recompute π from integer series
    accumulators and convert to a decimal string.  Plain-int arguments
    are always picklable regardless of gmpy2 version.
    """
    return _gmpy2_str_from_QT(Q_int, T_int, digits)


def _convert_mpmath_worker(pi_value, digits):
    """
    Subprocess worker (mpmath path): convert mpmath.mpf to decimal string.
    Running in a subprocess bypasses the GIL so the main-thread progress
    display is not starved by the pure-Python mpmath.nstr call.
    """
    return mpmath.nstr(pi_value, digits + 1, strip_zeros=False)


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
# CLI parsing
# ---------------------------------------------------------------------------

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Calculate pi to a specified number of decimal places.",
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
    return parser.parse_args()


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
            user_input = input("Enter the number of decimal places to calculate π (1-1000000): ")
            target_digits = int(user_input)
            if target_digits < 1:
                print("Please enter a positive number.")
                continue
            if target_digits > 1000000:
                print("Warning: Very large numbers may take a long time to calculate.")
                confirm = input(f"Continue with {target_digits} digits? (y/n): ").lower().strip()
                if confirm not in ['y', 'yes']:
                    continue
            return target_digits
        except ValueError:
            print("Please enter a valid integer.")


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def calculate_pi_high_precision(digits=1000):
    """
    Calculate π to the specified number of decimal places.

    Tries the fast Chudnovsky/gmpy2 path first; falls back to mpmath if
    gmpy2 is not installed.

    Returns:
        gmpy2.mpfr | mpmath.mpf: high-precision value of π.
        When the gmpy2 backend is used, the return value also carries
        _Q and _T attributes (Python ints) for efficient subprocess conversion.
    """
    print(f"Calculating π to {digits:,} decimal places...")
    print(f"Running on {_CPU_COUNT} CPU core{'s' if _CPU_COUNT != 1 else ''}...")

    if _HAS_GMPY2:
        print(
            f"Backend: Chudnovsky / gmpy2 {_gmpy2.version()} "
            f"(GMP {_gmpy2.mp_version()}, MPFR {_gmpy2.mpfr_version()})"
        )
        start = time.time()
        pi_mpfr, Q_int, T_int = _calculate_pi_gmpy2(digits)
        elapsed = time.time() - start
        print(f"\nCalculation completed in {elapsed:.2f} seconds")
        # Cache Q and T as plain Python ints for the subprocess worker.
        # gmpy2.mpfr is a C extension type and does not support arbitrary attrs.
        global _gmpy2_QT_cache
        _gmpy2_QT_cache = (Q_int, T_int)
        return pi_mpfr

    print(
        f"Backend: mpmath {mpmath.__version__} "
        f"(install gmpy2 for 5-50x faster computation — see install_deps.sh)"
    )
    print("This may take a while for high precision calculations...")
    mpmath.mp.dps = digits + 50
    start = time.time()
    pi_value = mpmath.pi
    elapsed = time.time() - start
    print(f"\nCalculation completed in {elapsed:.2f} seconds")
    return pi_value


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def show_pi_preview(pi_value, preview_digits=100):
    """
    Show a preview of π with specified number of digits.

    Args:
        pi_value: gmpy2.mpfr or mpmath.mpf
        preview_digits (int): number of decimal places to show
    """
    actual_preview = min(preview_digits, 200)
    print(f"Generating preview of π ({actual_preview} digits)...")
    pi_str = _pi_to_str(pi_value, actual_preview)
    if '.' in pi_str:
        integer_part, decimal_part = pi_str.split('.', 1)
    else:
        integer_part, decimal_part = pi_str, ""
    print(f"\nπ = {integer_part}.{decimal_part}...")
    print(f"(Showing first {len(decimal_part)} decimal places)")


# ---------------------------------------------------------------------------
# File save — multithreaded
# ---------------------------------------------------------------------------

def save_pi_to_file(pi_value, digits, filename):
    """
    Save π to file using subprocess string conversion and parallel I/O.

    Phase A — String conversion runs in a dedicated subprocess (bypasses
    the GIL).  The main thread drives a progress display by polling the
    Future, so progress remains smooth without a background thread.

      gmpy2 path: subprocess receives plain-int Q, T and recomputes the
                  final mpfr value — avoids any gmpy2 pickling uncertainty.
      mpmath path: subprocess receives the mpmath.mpf directly.

    Phase B — The resulting string is written to disk by _IO_WORKERS
    threads using os.pwrite(2), allowing non-overlapping chunks to be
    written concurrently without moving the shared file pointer.

    Args:
        pi_value: gmpy2.mpfr (with ._pi_Q / ._pi_T) or mpmath.mpf
        digits (int): number of decimal places
        filename (str): output filename
    """
    using_gmpy2 = _HAS_GMPY2 and isinstance(pi_value, _gmpy2.mpfr)
    backend_label = "gmpy2/MPFR" if using_gmpy2 else "mpmath"

    def estimate_conversion_time(d):
        if using_gmpy2:
            # MPFR string conversion is ~10x faster than mpmath
            if d <= 100_000:    return max(0.05, d * 5e-8)
            if d <= 1_000_000:  return max(0.1,  d * 2e-7)
            if d <= 10_000_000: return max(1.0,  d * 5e-6)
            return max(10.0, d * 1e-5)
        else:
            if d <= 100_000:    return max(1.0,  0.1 + d * 5e-6)
            if d <= 1_000_000:  return max(2.0,  0.5 + d * 2e-6)
            if d <= 10_000_000: return max(30.0, d * 5e-5)
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
            elapsed = time.time() - self.start_time
            if elapsed <= self.estimated_duration:
                remaining = max(0, self.estimated_duration - elapsed)
                pct = (elapsed / self.estimated_duration) * 100
                bar_length = 30
                filled = int(bar_length * pct / 100)
                bar = '█' * filled + '░' * (bar_length - filled)
                dots = "." * (int(elapsed * 2) % 4)
                print(
                    f"\rConverting {digits:,} digits{dots:<3} "
                    f"[{bar}] {pct:.1f}% "
                    f"Elapsed: {elapsed:.1f}s | ETA: {remaining:.1f}s",
                    end="", flush=True,
                )
            else:
                dots = "." * (int(elapsed * 2) % 4)
                print(
                    f"\rConverting {digits:,} digits{dots:<3} "
                    f"[Still converting...] "
                    f"Elapsed: {elapsed:.1f}s (longer than estimated)",
                    end="", flush=True,
                )

    # ── Phase A: subprocess conversion + main-thread progress ───────────────

    print(f"Starting conversion of {digits:,} digits...")
    estimated_time = estimate_conversion_time(digits)
    print(f"Estimated conversion time: {estimated_time:.1f} seconds ({backend_label})")
    print(
        f"Using {_CPU_COUNT} CPU core{'s' if _CPU_COUNT != 1 else ''} "
        f"({_IO_WORKERS} I/O workers for file write)"
    )

    # 'fork' on Linux (fast, safe); 'spawn' on macOS (required — Apple deprecated
    # fork in Python 3.12+ due to Objective-C runtime safety issues).
    mp_context = multiprocessing.get_context(
        'fork' if sys.platform == 'linux' else 'spawn'
    )

    conversion_start = time.time()
    progress = ProgressIndicator(estimated_time)
    progress.start()

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=1, mp_context=mp_context
    ) as pool:
        if using_gmpy2:
            # Pass plain Python ints from the module-level cache — always
            # picklable; the worker recomputes the final mpfr internally.
            Q_int, T_int = _gmpy2_QT_cache
            future = pool.submit(_convert_gmpy2_worker, Q_int, T_int, digits)
        else:
            future = pool.submit(_convert_mpmath_worker, pi_value, digits)

        while not future.done():
            progress.show_one_tick()
            time.sleep(0.25)

        pi_str = future.result()  # re-raises any subprocess exception

    progress.stop()
    conversion_time = time.time() - conversion_start
    print(f"\rString conversion completed in {conversion_time:.2f} seconds" + " " * 50)

    # ── Phase B: parallel pwrite ─────────────────────────────────────────────

    print(
        f"Writing to {filename} using {_IO_WORKERS} parallel I/O worker"
        f"{'s' if _IO_WORKERS != 1 else ''}..."
    )
    write_start = time.time()

    header = (
        f"π calculated to {digits:,} decimal places using {backend_label}\n"
        + "=" * 60 + "\n\n"
    ).encode("utf-8")
    pi_bytes = pi_str.encode("ascii")   # π digits are pure ASCII → 1 byte/char
    footer = f"\n\nTotal decimal places: {digits:,}".encode("utf-8")

    total_file_size = len(header) + len(pi_bytes) + len(footer)
    pi_offset = len(header)

    chunk_starts = list(range(0, len(pi_bytes), _PWRITE_CHUNK))
    total_chunks = len(chunk_starts)
    completed_chunks = 0
    _progress_lock = threading.Lock()

    fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        # Pre-allocate the full file size; pwrite will not extend a file
        # past its current end on most POSIX systems, so this is required.
        os.ftruncate(fd, total_file_size)
        _pwrite_all(fd, header, 0)
        _pwrite_all(fd, footer, pi_offset + len(pi_bytes))

        def write_chunk(start):
            nonlocal completed_chunks
            end = min(start + _PWRITE_CHUNK, len(pi_bytes))
            _pwrite_all(fd, pi_bytes[start:end], pi_offset + start)
            with _progress_lock:
                completed_chunks += 1
                elapsed = time.time() - write_start
                pct = completed_chunks / total_chunks * 100
                bytes_done = min(completed_chunks * _PWRITE_CHUNK, len(pi_bytes))
                rate = bytes_done / elapsed / 1024 / 1024 if elapsed > 0 else 0
                remaining = total_chunks - completed_chunks
                eta = (remaining / completed_chunks * elapsed) if completed_chunks > 0 else 0
                print(
                    f"\rFile write progress: {pct:.1f}% | "
                    f"Written: {bytes_done:,}/{len(pi_bytes):,} chars | "
                    f"ETA: {eta:.1f}s | "
                    f"Rate: {rate:.1f} MB/s",
                    end="", flush=True,
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
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Main function to execute π calculation."""
    try:
        args = parse_args()

        print("High-Precision π Calculator")
        print("=" * 40)

        target_digits = get_target_digits(args)
        pi_result = calculate_pi_high_precision(target_digits)

        if target_digits <= 1_000_000:
            preview_digits = min(100, target_digits)
            show_pi_preview(pi_result, preview_digits)
        else:
            print(f"\nSkipping preview for {target_digits:,} digits (too large for quick preview)")

        if target_digits > 10000:
            filename = f"pi_{target_digits}_digits.txt"
            print(f"\nFor {target_digits:,} digits, saving to file for better performance...")
            save_pi_to_file(pi_result, target_digits, filename)
            print(f"\nFull precision π saved to {filename}")
        else:
            print(f"\nWould you like to display all {target_digits:,} digits? (y/n): ", end="")
            response = input().lower().strip()
            if response in ['y', 'yes']:
                pi_str = _pi_to_str(pi_result, target_digits)
                print(f"\nπ = {pi_str}")
                print(f"\nTotal digits: {target_digits:,}")
            else:
                filename = f"pi_{target_digits}_digits.txt"
                save_pi_to_file(pi_result, target_digits, filename)
                print(f"\nFull precision π saved to {filename}")

    except KeyboardInterrupt:
        print("\n\nCalculation interrupted by user.")
        sys.exit(1)
    except ValueError as error:
        print(f"\nError: {error}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError occurred during calculation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Guard against re-execution in multiprocessing worker subprocesses.
    #
    # With the 'spawn' start method (macOS default), ProcessPoolExecutor
    # re-executes this script in each worker to import __main__.  Checking
    # the process name ensures main() runs only in the original process;
    # workers are named "SpawnProcess-N" / "ForkProcess-N".
    if multiprocessing.current_process().name == "MainProcess":
        try:
            import mpmath
        except ImportError:
            print("Error: mpmath is required.  Run: pip install mpmath")
            sys.exit(1)

        main()
