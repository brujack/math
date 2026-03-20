
#!/usr/bin/env python3
"""
Calculate π to a user-specified number of decimal places using the mpmath library.
"""

import argparse
import mpmath
import sys
import threading
import time


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

def calculate_pi_high_precision(digits=1000):
    """
    Calculate π to the specified number of decimal places.

    Args:
        digits (int): Number of decimal places to calculate

    Returns:
        mpmath.mpf: High-precision value of π
    """
    # Set precision to handle the requested number of digits
    # We need extra precision for intermediate calculations
    mpmath.mp.dps = digits + 50

    print(f"Calculating π to {digits} decimal places...")
    print("This may take a while for high precision calculations...")

    start_time = time.time()

    # Calculate π using mpmath's built-in high-precision pi
    pi_value = mpmath.pi

    end_time = time.time()
    calculation_time = end_time - start_time

    print(f"\nCalculation completed in {calculation_time:.2f} seconds")

    return pi_value

def show_pi_preview(pi_value, preview_digits=100):
    """
    Show a preview of π with specified number of digits.

    Args:
        pi_value: The calculated π value
        preview_digits (int): Number of decimal places to show
    """
    # Limit preview for very large numbers to avoid slowdown
    actual_preview = min(preview_digits, 200)  # Maximum 200 digits in preview

    print(f"Generating preview of π ({actual_preview} digits)...")

    # Convert only the preview portion to string
    pi_str = mpmath.nstr(pi_value, actual_preview + 1, strip_zeros=False)

    # Split into integer and decimal parts
    if '.' in pi_str:
        integer_part, decimal_part = pi_str.split('.', 1)
    else:
        integer_part = pi_str
        decimal_part = ""

    print(f"\nπ = {integer_part}.{decimal_part}...")
    print(f"(Showing first {len(decimal_part)} decimal places)")

def save_pi_to_file(pi_value, digits, filename):
    """
    Efficiently save π to file with progress indication and countdown timer.

    Args:
        pi_value: The calculated π value
        digits (int): Number of decimal places
        filename (str): Output filename
    """
    def estimate_conversion_time(digits):
        """Estimate conversion time based on number of digits."""
        # More accurate empirical formula - actual conversion time grows non-linearly
        if digits <= 100000:
            return max(1.0, 0.1 + digits * 0.000005)
        elif digits <= 1000000:
            return max(2.0, 0.5 + digits * 0.000002)
        elif digits <= 10000000:
            # 10M digits takes ~300-600 seconds based on testing
            return max(30.0, digits * 0.00005)  # Much more realistic
        else:
            # Over 10M gets increasingly slow
            return max(60.0, digits * 0.0001)

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

        def show_progress(self):
            while self.running:
                elapsed = time.time() - self.start_time

                if elapsed <= self.estimated_duration:
                    # Show progress bar based on estimate
                    remaining = max(0, self.estimated_duration - elapsed)
                    progress_percent = (elapsed / self.estimated_duration) * 100

                    # Create a simple progress bar
                    bar_length = 30
                    filled_length = int(bar_length * progress_percent / 100)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)

                    dots = "." * (int(elapsed * 2) % 4)
                    print(f"\rConverting {digits:,} digits{dots:<3} "
                          f"[{bar}] {progress_percent:.1f}% "
                          f"Elapsed: {elapsed:.1f}s | ETA: {remaining:.1f}s",
                          end="", flush=True)
                else:
                    # Estimate was too low - show spinner with elapsed time
                    dots = "." * (int(elapsed * 2) % 4)
                    print(f"\rConverting {digits:,} digits{dots:<3} "
                          f"[Still converting...] "
                          f"Elapsed: {elapsed:.1f}s (longer than estimated)",
                          end="", flush=True)

                time.sleep(0.25)

    print(f"Starting conversion of {digits:,} digits...")
    estimated_time = estimate_conversion_time(digits)
    print(f"Estimated conversion time: {estimated_time:.1f} seconds")

    conversion_start = time.time()

    # Create and start progress indicator
    progress = ProgressIndicator(estimated_time)
    progress.start()
    progress_thread = threading.Thread(target=progress.show_progress, daemon=True)
    progress_thread.start()

    # Give the progress thread a moment to start
    time.sleep(0.1)

    try:
        # Convert to string - this is the slow operation
        pi_str = mpmath.nstr(pi_value, digits + 1, strip_zeros=False)
    finally:
        # Stop progress indicator
        progress.stop()
        progress_thread.join(timeout=1.0)

    conversion_time = time.time() - conversion_start
    print(f"\rString conversion completed in {conversion_time:.2f} seconds" + " " * 50)

    print(f"Writing to {filename}...")
    write_start = time.time()

    # Calculate chunk size for progress tracking (write in chunks)
    total_length = len(pi_str)
    chunk_size = max(1024 * 1024, total_length // 100)  # 1MB chunks or 1% of total

    with open(filename, 'w', buffering=8192*16) as f:  # Larger buffer for better performance
        f.write(f"π calculated to {digits:,} decimal places using mpmath\n")
        f.write("=" * 60 + "\n\n")

        # Write the main content in chunks with progress
        written = 0
        total_data = len(pi_str)

        for i in range(0, total_data, chunk_size):
            chunk = pi_str[i:i + chunk_size]
            f.write(chunk)
            written += len(chunk)

            # Calculate and display progress
            progress = (written / total_data) * 100
            elapsed = time.time() - write_start

            if elapsed > 0:
                rate = written / elapsed  # bytes per second
                remaining_bytes = total_data - written
                eta = remaining_bytes / rate if rate > 0 else 0

                # Display progress with countdown
                print(f"\rFile write progress: {progress:.1f}% | "
                      f"Written: {written:,}/{total_data:,} chars | "
                      f"ETA: {eta:.1f}s | "
                      f"Rate: {rate/1024/1024:.1f} MB/s", end="", flush=True)

        f.write(f"\n\nTotal decimal places: {digits:,}")

    print()  # New line after progress
    write_time = time.time() - write_start
    print(f"File write completed in {write_time:.2f} seconds")
    print(f"Total file operation time: {(conversion_time + write_time):.2f} seconds")

def main():
    """Main function to execute π calculation."""
    try:
        args = parse_args()

        print("High-Precision π Calculator")
        print("=" * 40)

        target_digits = get_target_digits(args)

        # Calculate π
        pi_result = calculate_pi_high_precision(target_digits)

        # Show preview for calculations <= 1 million digits
        if target_digits <= 1000000:
            preview_digits = min(100, target_digits)
            show_pi_preview(pi_result, preview_digits)
        else:
            print(f"\nSkipping preview for {target_digits:,} digits (too large for quick preview)")

        # For large numbers (>10000 digits), always save to file
        if target_digits > 10000:
            filename = f"pi_{target_digits}_digits.txt"
            print(f"\nFor {target_digits:,} digits, saving to file for better performance...")
            save_pi_to_file(pi_result, target_digits, filename)
            print(f"\nFull precision π saved to {filename}")
        else:
            # For smaller numbers, ask if user wants full display
            print(f"\nWould you like to display all {target_digits:,} digits? (y/n): ", end="")
            response = input().lower().strip()

            if response in ['y', 'yes']:
                # Convert to string and display
                pi_str = mpmath.nstr(pi_result, target_digits + 1, strip_zeros=False)
                print(f"\nπ = {pi_str}")
                print(f"\nTotal digits: {target_digits:,}")
            else:
                # Save to file
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
    # Check if mpmath is installed
    try:
        import mpmath
    except ImportError:
        print("Error: mpmath library is required but not installed.")
        print("Please install it using: pip install mpmath")
        sys.exit(1)

    main()
