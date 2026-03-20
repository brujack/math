
#!/usr/bin/env python3
"""
Calculate π to a user-specified number of decimal places using the mpmath library.

Uses multiprocessing for string conversion (bypasses the GIL) and parallel
I/O workers for file writing, optimised for multi-core systems including
Apple Silicon and Linux x64.
"""

import argparse
import concurrent.futures
import multiprocessing
import mpmath
import os
import sys
import time

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Number of I/O worker threads used for parallel pwrite(2) file writes.
# Capped at 8: single-disk bandwidth saturates beyond that.
_CPU_COUNT = os.cpu_count() or 1
_IO_WORKERS = max(2, min(8, _CPU_COUNT))

# Minimum chunk size per I/O worker (4 MiB balances dispatch overhead vs. granularity).
_PWRITE_CHUNK = 4 * 1024 * 1024


# ---------------------------------------------------------------------------
# Module-level worker functions (must be at module level for multiprocessing)
# ---------------------------------------------------------------------------

def _convert_pi_worker(pi_value, digits):
    """
    Subprocess worker: convert mpmath π value to a decimal string.

    Running conversion here bypasses the GIL in the calling process,
    allowing the main thread to update the progress display without
    any starvation from the CPU-bound mpmath.nstr() call.

    Must be at module level so that spawn-mode multiprocessing (macOS default)
    can locate the function by name when unpickling the submitted call.
    """
    import mpmath as _mpmath
    return _mpmath.nstr(pi_value, digits + 1, strip_zeros=False)


def _pwrite_all(fd, data, offset):
    """
    Write all bytes in *data* to file descriptor *fd* at absolute *offset*.

    Uses os.pwrite(2) in a loop to handle short writes (rare but required
    for correctness).  Thread-safe: pwrite does not move the file pointer,
    so multiple threads can call this concurrently on the same fd with
    non-overlapping offsets.
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

    Args:
        digits (int): Number of decimal places to calculate

    Returns:
        mpmath.mpf: High-precision value of π
    """
    mpmath.mp.dps = digits + 50

    print(f"Calculating π to {digits} decimal places...")
    print(f"Running on {_CPU_COUNT} CPU core{'s' if _CPU_COUNT != 1 else ''}...")

    start_time = time.time()
    pi_value = mpmath.pi
    elapsed = time.time() - start_time

    print(f"\nCalculation completed in {elapsed:.2f} seconds")
    return pi_value


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def show_pi_preview(pi_value, preview_digits=100):
    """
    Show a preview of π with specified number of digits.

    Args:
        pi_value: The calculated π value
        preview_digits (int): Number of decimal places to show
    """
    actual_preview = min(preview_digits, 200)
    print(f"Generating preview of π ({actual_preview} digits)...")

    pi_str = mpmath.nstr(pi_value, actual_preview + 1, strip_zeros=False)

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

    Phase B — The resulting string is written to disk by _IO_WORKERS threads
    using os.pwrite(2), which allows non-overlapping chunks to be written
    concurrently without moving the shared file pointer.

    Args:
        pi_value: The calculated π value
        digits (int): Number of decimal places
        filename (str): Output filename
    """

    def estimate_conversion_time(d):
        """Estimate conversion time based on digit count."""
        if d <= 100_000:
            return max(1.0, 0.1 + d * 0.000005)
        elif d <= 1_000_000:
            return max(2.0, 0.5 + d * 0.000002)
        elif d <= 10_000_000:
            return max(30.0, d * 0.00005)
        else:
            return max(60.0, d * 0.0001)

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
            """Print one progress update; call from the main polling loop."""
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
    print(f"Estimated conversion time: {estimated_time:.1f} seconds")
    print(
        f"Using {_CPU_COUNT} CPU core{'s' if _CPU_COUNT != 1 else ''} "
        f"({_IO_WORKERS} I/O workers for file write)"
    )

    # Use 'fork' on Linux (fast, inherits mpmath state) and 'spawn' on macOS
    # (required — macOS deprecated fork in Python 3.12+ due to safety issues).
    mp_context = multiprocessing.get_context(
        'fork' if sys.platform == 'linux' else 'spawn'
    )

    conversion_start = time.time()
    progress = ProgressIndicator(estimated_time)
    progress.start()

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=1, mp_context=mp_context
    ) as pool:
        future = pool.submit(_convert_pi_worker, pi_value, digits)

        # Main thread drives progress while the subprocess converts.
        while not future.done():
            progress.show_one_tick()
            time.sleep(0.25)

        pi_str = future.result()  # re-raises any subprocess exception

    progress.stop()
    conversion_time = time.time() - conversion_start
    print(f"\rString conversion completed in {conversion_time:.2f} seconds" + " " * 50)

    # ── Phase B: parallel pwrite ─────────────────────────────────────────────

    print(f"Writing to {filename} using {_IO_WORKERS} parallel I/O worker"
          f"{'s' if _IO_WORKERS != 1 else ''}...")
    write_start = time.time()

    header = (
        f"π calculated to {digits:,} decimal places using mpmath\n"
        + "=" * 60 + "\n\n"
    ).encode("utf-8")
    pi_bytes = pi_str.encode("ascii")   # π digits are pure ASCII → 1 byte/char
    footer = f"\n\nTotal decimal places: {digits:,}".encode("utf-8")

    total_file_size = len(header) + len(pi_bytes) + len(footer)
    pi_offset = len(header)

    # Slice pi_bytes into chunks of at most _PWRITE_CHUNK bytes.
    chunk_starts = list(range(0, len(pi_bytes), _PWRITE_CHUNK))
    total_chunks = len(chunk_starts)
    completed_chunks = 0

    fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        # Pre-allocate the full file size.  pwrite will not extend a file
        # beyond its current size on most POSIX systems, so this is required.
        os.ftruncate(fd, total_file_size)

        # Header and footer are small — write sequentially.
        _pwrite_all(fd, header, 0)
        _pwrite_all(fd, footer, pi_offset + len(pi_bytes))

        def write_chunk(start):
            nonlocal completed_chunks
            end = min(start + _PWRITE_CHUNK, len(pi_bytes))
            _pwrite_all(fd, pi_bytes[start:end], pi_offset + start)

            completed_chunks += 1
            elapsed = time.time() - write_start
            pct = completed_chunks / total_chunks * 100
            bytes_done = min(completed_chunks * _PWRITE_CHUNK, len(pi_bytes))
            rate = bytes_done / elapsed / 1024 / 1024 if elapsed > 0 else 0
            remaining_chunks = total_chunks - completed_chunks
            eta = (remaining_chunks / completed_chunks * elapsed) if completed_chunks > 0 else 0
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
                pi_str = mpmath.nstr(pi_result, target_digits + 1, strip_zeros=False)
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
    # re-executes this script in each worker process to import __main__.
    # Checking the process name ensures main() runs only in the original
    # process; worker processes are named "SpawnProcess-N" / "ForkProcess-N".
    if multiprocessing.current_process().name == "MainProcess":
        try:
            import mpmath
        except ImportError:
            print("Error: mpmath library is required but not installed.")
            print("Please install it using: pip install mpmath")
            sys.exit(1)

        main()
