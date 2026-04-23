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
import mpmath
import os
import sys
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
        N = int(digits / math.log10(digits + 1)) + 50
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
            'fork' if sys.platform == 'linux' else 'spawn'
        )
        print(
            f"  Parallel series: {n_workers} workers "
            f"x ~{chunk_size:,} terms each"
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
                bar = '#' * filled + '.' * (bar_width - filled)
                print(
                    f"\r  [{bar}] {completed}/{n_workers} chunks",
                    end="", flush=True,
                )
        print()

        # Collect results in submission order (all done; .result() is instant).
        int_results = [f.result() for f in futures]

        # Convert to gmpy2.mpz and merge via tree reduction.
        print("  Combining chunks...", end="", flush=True)
        pq_list = [
            (_gmpy2.mpz(P), _gmpy2.mpz(Q))
            for P, Q in int_results
        ]
        P, Q = _tree_combine(pq_list)
        print("\r  Combination complete.   ")
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
        sign = ''
        if mantissa.startswith('-'):
            sign, mantissa = '-', mantissa[1:]
        int_part = mantissa[:exp] if exp > 0 else '0'
        dec_part = mantissa[exp:digits + exp]
        return f"{sign}{int_part}.{dec_part}"
    return mpmath.nstr(e_value, digits + 1, strip_zeros=False)


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
            user_input = input("Enter the number of decimal places to calculate e (1-1000000): ")
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

        e_str = _e_to_str(e_result, min(100, target_digits))
        print(f"\ne = {e_str}...")
        print(f"(Showing first {min(100, target_digits)} decimal places)")

    except KeyboardInterrupt:
        print("\n\nCalculation interrupted by user.")
        sys.exit(1)
    except ValueError as error:
        print(f"\nError: {error}")
        sys.exit(1)
    except Exception as ex:
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
