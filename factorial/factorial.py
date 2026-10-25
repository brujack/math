#!/usr/bin/env python3
"""
Compute N! (N factorial) to arbitrary precision using the prime swing algorithm.

Algorithm: n! = swing(n) × (floor(n/2)!)²  (Luschny prime swing)
  swing(m) = ∏ p^e_p  where e_p = Σ_{j≥1} (floor(m/p^j) mod 2)

Uses gmpy2/GMP for fast arbitrary-precision arithmetic.
Falls back to mpmath.factorial if gmpy2 is not installed.

Install fast backend (recommended):
    bash install_deps.sh
"""

import argparse
import concurrent.futures
import multiprocessing
import os
import sys
import time

try:
    import gmpy2 as _gmpy2

    _HAS_GMPY2 = True
except ImportError:
    _gmpy2 = None
    _HAS_GMPY2 = False

SMOKE_SIZE = 1000
LARGE_RUN_THRESHOLD: int | None = None

_CPU_COUNT = os.cpu_count() or 1
# spawn overhead on macOS is ~100-200ms per worker; only parallel when worth it
_MIN_PARALLEL_PRIMES = 1000


# ---------------------------------------------------------------------------
# Sieve of Eratosthenes
# ---------------------------------------------------------------------------


def _sieve(n: int) -> list[int]:
    """Return sorted list of all primes <= n."""
    if n < 2:
        return []
    composite = bytearray(n + 1)  # 0 = prime, 1 = composite
    composite[0] = 1
    composite[1] = 1
    i = 2
    while i * i <= n:
        if not composite[i]:
            j = i * i
            while j <= n:
                composite[j] = 1
                j += i
        i += 1
    return [p for p in range(2, n + 1) if not composite[p]]


# ---------------------------------------------------------------------------
# Stubs — will be replaced in later tasks
# ---------------------------------------------------------------------------


def _compute_swing_chunk(m: int, prime_chunk: list[int]) -> int:
    """
    Compute product of p^e_p for each prime in prime_chunk, for swing(m).

    e_p = number of odd values in {floor(m/p), floor(m/p^2), ...}
    Returns a plain Python int (always picklable).
    """
    result = 1
    for p in prime_chunk:
        if p > m:
            break  # prime_chunk must be sorted ascending; primes beyond m have no contribution
        exp = 0
        q = m
        while q >= p:
            q //= p
            if q & 1:
                exp += 1
        if exp:
            result *= p**exp
    return result


def _tree_combine_int(values: list[int]) -> int:
    """
    Pairwise tree reduction of a list of integers (plain int or gmpy2.mpz).
    Returns 1 for an empty list.
    Balanced tree keeps GMP multiply sizes similar at each level.
    """
    if not values:
        return 1
    while len(values) > 1:
        next_level = []
        for i in range(0, len(values), 2):
            if i + 1 < len(values):
                next_level.append(values[i] * values[i + 1])
            else:
                next_level.append(values[i])
        values = next_level
    return values[0]


def _compute_swing(m: int, primes: list[int]) -> int:
    """Compute swing(m) = product of p^e_p for all primes p <= m.

    Splits the prime list into _CPU_COUNT chunks and dispatches each chunk
    to a subprocess via ProcessPoolExecutor, then tree-combines the results.
    Falls back to a single-process call when the prime list is small enough
    that subprocess overhead would dominate.
    """
    if not primes or primes[0] > m:
        return 1

    # Filter to primes <= m (the sieve may contain primes beyond m)
    relevant = [p for p in primes if p <= m]
    if not relevant:
        return 1

    chunk_size = max(1, (len(relevant) + _CPU_COUNT - 1) // _CPU_COUNT)
    chunks = [relevant[i : i + chunk_size] for i in range(0, len(relevant), chunk_size)]

    if len(chunks) == 1 or len(relevant) < _MIN_PARALLEL_PRIMES:
        # Serial: single chunk or too few primes to justify spawn overhead
        return _compute_swing_chunk(m, relevant)

    ctx = multiprocessing.get_context("spawn" if sys.platform == "darwin" else "fork")
    try:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=len(chunks), mp_context=ctx
        ) as pool:
            futures = [pool.submit(_compute_swing_chunk, m, chunk) for chunk in chunks]
            partial_results = [f.result() for f in futures]
    except (PermissionError, OSError) as err:
        print(
            f"\nParallel mode unavailable ({err}); falling back to serial.\n"
            "Install project requirements and ensure OS multiprocessing "
            "semaphore support is available to re-enable parallel mode."
        )
        partial_results = [_compute_swing_chunk(m, chunk) for chunk in chunks]

    return int(_tree_combine_int(partial_results))


def _write_factorial_file(
    result: object, n: int, show: bool = False
) -> tuple[str, str]:
    """Write factorial result to factorial_<n>.txt. Returns (filename, digits).

    With show, the digits are printed before the summary line.
    """
    filename = f"factorial_{n}.txt"
    digits_str = str(int(result))  # type: ignore[arg-type]
    if show:
        print(digits_str)
    start = time.time()
    with open(filename, "w") as f:
        f.write(digits_str)
    elapsed = time.time() - start
    digit_count = len(digits_str)
    print(f"{digit_count:,} digits written to {filename} in {elapsed:.2f}s")
    return filename, digits_str


def _factorial_rec(n: int, primes: list[int]) -> int:
    """Recursive prime swing factorial: n! = swing(n) * (n//2)!^2."""
    if n <= 1:
        return 1
    half_factorial = _factorial_rec(n // 2, primes)
    swing = _compute_swing(n, primes)
    return half_factorial * half_factorial * swing


def calculate_factorial(n: int) -> int:
    """Compute n! using the prime swing algorithm. Returns gmpy2.mpz if available, int otherwise."""
    if n < 0:
        raise ValueError(f"factorial not defined for negative integers: {n}")
    if n <= 1:
        result = 1
    else:
        primes = _sieve(n)
        result = _factorial_rec(n, primes)
    if _HAS_GMPY2:
        return _gmpy2.mpz(result)  # type: ignore[union-attr]
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute N! to arbitrary precision using the prime swing algorithm.",
        epilog="Run with no arguments at a terminal for interactive prompts.",
    )
    parser.add_argument(
        "size",
        nargs="?",
        type=int,
        metavar="n",
        help="Integer to compute factorial of",
    )
    parser.add_argument(
        "--show", action="store_true", help="also print each result line to stdout"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a large run (ignored when this program has none)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=f"quick check at SMOKE_SIZE ({SMOKE_SIZE})",
    )
    args = parser.parse_args(argv)
    if args.smoke:
        if args.size is not None:
            parser.error("--smoke takes no SIZE")
        args.size, args.show = SMOKE_SIZE, False
    elif args.size is None and not sys.stdin.isatty():
        parser.error("SIZE is required when stdin is not a terminal")
    return args


def refuse_large_run(size: int, yes: bool) -> None:
    """Exit 1 naming --yes when size needs confirmation and --yes is absent."""
    if LARGE_RUN_THRESHOLD is not None and size >= LARGE_RUN_THRESHOLD and not yes:
        print(f"Error: {size} is a large run; pass --yes to proceed.", file=sys.stderr)
        sys.exit(1)


def get_target_n(args: argparse.Namespace) -> int:
    """Return n from args or interactive prompt. Validates positive integer (0 allowed)."""
    if args.size is not None:
        if args.size < 0:
            raise ValueError(f"n must be a non-negative integer, got {args.size}")
        return args.size
    while True:
        try:
            raw = input("Enter N to compute N! : ").strip()
        except EOFError:
            print()
            print(
                "Error: no input; pass SIZE as an argument "
                f"(e.g. python3 factorial.py {SMOKE_SIZE}).",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            n = int(raw)
        except ValueError:
            print(f"Invalid input: '{raw}'. Please enter a non-negative integer.")
            continue
        if n < 0:
            print(f"N must be non-negative, got {n}.")
            continue
        return n


def main(argv: list[str] | None = None) -> None:
    """Entry point: parse args, compute factorial, write to file."""
    args = parse_args(argv)
    # N! routinely exceeds the default 4,300-digit int-to-str limit.
    sys.set_int_max_str_digits(0)
    try:
        n = get_target_n(args)
        refuse_large_run(n, args.yes)
        print(f"Computing {n:,}! ...")
        start = time.time()
        result = calculate_factorial(n)
        elapsed = time.time() - start
        _write_factorial_file(result, n, show=args.show)
        print(f"Computed in {elapsed:.2f}s")
    except ValueError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nComputation interrupted.")
        sys.exit(1)
    except PermissionError as err:
        print(f"Error: {err}")
        sys.exit(1)


if __name__ == "__main__":
    if multiprocessing.current_process().name == "MainProcess":
        main()
