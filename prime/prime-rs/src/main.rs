/*!
Find all prime numbers up to 10^N.

Algorithm: parallel segmented Sieve of Eratosthenes

  Phase 1 — simple sieve of [2, √(10^N)]
    * √(10^18) = 10^9 → sieve array is ≤ 500 MB for the largest supported N,
      but typically tiny (√(10^9) ≈ 31 623 → just 4 KB).

  Phase 2 — segmented sieve of (√(10^N), 10^N]
    * Divide range into SEG_SIZE-number segments, each represented as a
      packed bitset (1 bit per odd number → 32 KB per segment, fits in L2).
    * Group segments into BLOCK_SIZE-number blocks processed by rayon::par_iter.
    * Stream each block's primes to the output file before moving to the next,
      bounding peak RAM to ~50 MB regardless of N.
    * Progress thread reports % complete and sieve rate (M numbers/s).

Build:
    cargo build --release
    ./target/release/prime [N]
*/

use std::fs::File;
use std::io::{self, BufRead, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::time::Instant;

use clap::Parser;

use prime::{find_primes, fmt_int};

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

#[derive(Parser)]
#[command(
    name = "prime",
    about = "Find all primes up to 10^N",
    long_about = "Find all prime numbers up to 10^N using a parallel segmented\n\
                  Sieve of Eratosthenes with rayon-accelerated segment processing.\n\n\
                  Run without arguments for interactive prompts."
)]
struct Cli {
    /// N: finds every prime up to 10^N  (e.g. 9 → all primes ≤ 1,000,000,000)
    digits: Option<u32>,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn read_line_from<R: BufRead>(reader: &mut R) -> io::Result<String> {
    let mut line = String::new();
    reader.read_line(&mut line)?;
    Ok(line.trim().to_string())
}

fn confirm_large_n_with<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    n: u32,
) -> io::Result<bool> {
    let limit = 10u64.pow(n);
    writeln!(
        err,
        "Warning: N={} means sieving up to {} — this may take a long time",
        n,
        fmt_int(limit)
    )?;
    writeln!(err, "         and produce a very large output file.")?;
    write!(out, "Continue? (y/n): ")?;
    out.flush()?;
    let answer = read_line_from(reader)?;
    Ok(matches!(answer.as_str(), "y" | "yes"))
}

fn prompt_n_with<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    err: &mut E,
) -> io::Result<u32> {
    loop {
        write!(out, "Enter N (finds all primes up to 10^N, max 18): ")?;
        out.flush()?;
        match read_line_from(reader)?.parse::<u32>() {
            Ok(n) if (1..=18).contains(&n) => return Ok(n),
            Ok(_) => writeln!(err, "N must be between 1 and 18.")?,
            _ => writeln!(err, "Please enter a positive integer.")?,
        }
    }
}

// ---------------------------------------------------------------------------
// Orchestrator
// ---------------------------------------------------------------------------

fn run<R: BufRead, W: Write, E: Write>(
    cli: Cli,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    dir: &Path,
) -> io::Result<i32> {
    writeln!(out, "Prime Number Sieve (Rust/Rayon)")?;
    writeln!(out, "{}", "=".repeat(40))?;

    let digits = match cli.digits {
        Some(d) => {
            if !(1..=18).contains(&d) {
                writeln!(err, "Error: N must be between 1 and 18.")?;
                return Ok(1);
            }
            d
        }
        None => prompt_n_with(reader, out, err)?,
    };

    let limit: u64 = 10u64.pow(digits);

    if digits >= 11 && !confirm_large_n_with(reader, out, err, digits)? {
        return Ok(0);
    }

    writeln!(out, "Finding all primes up to 10^{} = {}", digits, fmt_int(limit))?;
    writeln!(
        out,
        "Backend: segmented sieve / packed bitset / rayon ({} threads)",
        rayon::current_num_threads()
    )?;

    let t_total = Instant::now();

    if digits <= 6 {
        // Small result: buffer in memory, let user choose to display or save.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_primes(limit, &mut buf)?;

        writeln!(out, "\nFound {} primes up to 10^{}", fmt_int(count), digits)?;
        write!(out, "Display all {} primes? (y/n): ", fmt_int(count))?;
        out.flush()?;
        if matches!(read_line_from(reader)?.as_str(), "y" | "yes") {
            out.write_all(&buf)?;
        } else {
            let path = dir.join(format!("primes_1e{}.txt", digits));
            std::fs::write(&path, &buf)?;
            writeln!(out, "Saved to {}", path.display())?;
        }
    } else {
        // Large result: stream directly to file.
        let path = dir.join(format!("primes_1e{}.txt", digits));
        writeln!(out, "\nSaving to {}…", path.display())?;
        let file = File::create(&path)?;
        let mut writer = BufWriter::with_capacity(8 * 1024 * 1024, file);
        let count = find_primes(limit, &mut writer)?;
        writer.flush()?;
        writeln!(out, "Found {} primes up to 10^{}", fmt_int(count), digits)?;
        writeln!(out, "Saved to {}", path.display())?;
    }

    writeln!(out, "Total time: {:.2}s", t_total.elapsed().as_secs_f64())?;
    Ok(0)
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

#[cfg(not(tarpaulin_include))]
fn main() {
    let cli = Cli::parse();
    let stdin = io::stdin();
    let mut reader = stdin.lock();
    let stdout = io::stdout();
    let mut out = stdout.lock();
    let stderr = io::stderr();
    let mut err = stderr.lock();
    let dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let code = run(cli, &mut reader, &mut out, &mut err, &dir).unwrap_or(1);
    std::process::exit(code);
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use prime::{find_primes, fmt_int, format_phase2_progress, sieve_segment, small_sieve};
    use proptest::prelude::*;
    use tempfile::tempdir;

    // --- FailWriter helper ---

    struct FailWriter;
    impl Write for FailWriter {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::other("write failed"))
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    // --- fmt_int ---

    #[test]
    fn test_fmt_int_zero() {
        assert_eq!(fmt_int(0), "0");
    }

    #[test]
    fn test_fmt_int_below_thousand() {
        assert_eq!(fmt_int(999), "999");
    }

    #[test]
    fn test_fmt_int_thousands() {
        assert_eq!(fmt_int(1_000), "1,000");
        assert_eq!(fmt_int(10_000), "10,000");
    }

    #[test]
    fn test_fmt_int_millions() {
        assert_eq!(fmt_int(1_234_567), "1,234,567");
    }

    #[test]
    fn test_fmt_int_large() {
        assert_eq!(fmt_int(50_847_534), "50,847,534");
    }

    // --- small_sieve ---

    #[test]
    fn test_small_sieve_empty() {
        assert!(small_sieve(0).is_empty());
        assert!(small_sieve(1).is_empty());
    }

    #[test]
    fn test_small_sieve_two() {
        assert_eq!(small_sieve(2), vec![2u64]);
    }

    #[test]
    fn test_small_sieve_ten() {
        assert_eq!(small_sieve(10), vec![2u64, 3, 5, 7]);
    }

    #[test]
    fn test_small_sieve_thirty() {
        assert_eq!(small_sieve(30), vec![2u64, 3, 5, 7, 11, 13, 17, 19, 23, 29]);
    }

    #[test]
    fn test_small_sieve_count_100() {
        // π(100) = 25
        assert_eq!(small_sieve(100).len(), 25);
    }

    #[test]
    fn test_small_sieve_count_1000() {
        // π(1000) = 168
        assert_eq!(small_sieve(1000).len(), 168);
    }

    // --- sieve_segment ---

    #[test]
    fn test_sieve_segment_small() {
        // Primes in [11, 30] given small primes up to 7.
        let sp = vec![2u64, 3, 5, 7];
        let result = sieve_segment(11, 30, &sp);
        assert_eq!(result, vec![11u64, 13, 17, 19, 23, 29]);
    }

    #[test]
    fn test_sieve_segment_known_range() {
        // Primes in [101, 200]; sqrt(200) < 15 so sieve with primes up to 14.
        let sp = small_sieve(14);
        let result = sieve_segment(101, 200, &sp);
        let expected = vec![
            101u64, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151, 157, 163, 167, 173, 179, 181,
            191, 193, 197, 199,
        ];
        assert_eq!(result, expected);
    }

    #[test]
    fn test_sieve_segment_no_even_numbers() {
        // All results must be odd (segment lo is odd, 2 is not included).
        let sp = small_sieve(32);
        let result = sieve_segment(101, 200, &sp);
        assert!(result.iter().all(|&p| p % 2 == 1));
    }

    #[test]
    fn test_sieve_segment_empty_when_lo_exceeds_limit() {
        // lo > limit → empty.
        let sp = vec![2u64, 3, 5];
        let result = sieve_segment(101, 100, &sp);
        assert!(result.is_empty());
    }

    #[test]
    fn test_sieve_segment_lo_equals_limit_prime() {
        // lo == limit == 31 (a prime): segment contains exactly [31].
        let sp = small_sieve(5); // [2, 3, 5]
        let result = sieve_segment(31, 31, &sp);
        assert_eq!(result, vec![31u64]);
    }

    // --- format_phase2_progress ---

    #[test]
    fn test_format_phase2_progress_zero() {
        let s = format_phase2_progress(0, 1_000, 1.0);
        assert!(s.contains("  0%"), "got: {}", s);
        assert!(s.contains("0 / 1,000"), "got: {}", s);
    }

    #[test]
    fn test_format_phase2_progress_partial() {
        let s = format_phase2_progress(500_000, 1_000_000, 1.0);
        assert!(s.contains(" 50%"), "got: {}", s);
        assert!(s.contains("500,000 / 1,000,000"), "got: {}", s);
    }

    #[test]
    fn test_format_phase2_progress_complete() {
        let s = format_phase2_progress(1_000, 1_000, 1.0);
        assert!(s.contains("100%"), "got: {}", s);
    }

    #[test]
    fn test_format_phase2_progress_zero_total() {
        // phase2_total=0 → uses .max(1) to avoid division by zero; pct=0
        let s = format_phase2_progress(0, 0, 1.0);
        assert!(s.contains("  0%"), "got: {}", s);
    }

    // --- read_line_from ---

    #[test]
    fn test_read_line_from_trims_newline() {
        let mut r = io::Cursor::new(b"hello\n");
        assert_eq!(read_line_from(&mut r).unwrap(), "hello");
    }

    #[test]
    fn test_read_line_from_empty() {
        let mut r = io::Cursor::new(b"");
        assert_eq!(read_line_from(&mut r).unwrap(), "");
    }

    #[test]
    fn test_read_line_from_trims_whitespace() {
        let mut r = io::Cursor::new(b"  hello  \n");
        assert_eq!(read_line_from(&mut r).unwrap(), "hello");
    }

    // --- confirm_large_n_with ---

    #[test]
    fn test_confirm_large_n_y() {
        let mut r = io::Cursor::new(b"y\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert!(confirm_large_n_with(&mut r, &mut out, &mut err, 11).unwrap());
    }

    #[test]
    fn test_confirm_large_n_yes() {
        let mut r = io::Cursor::new(b"yes\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert!(confirm_large_n_with(&mut r, &mut out, &mut err, 11).unwrap());
    }

    #[test]
    fn test_confirm_large_n_n() {
        let mut r = io::Cursor::new(b"n\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert!(!confirm_large_n_with(&mut r, &mut out, &mut err, 11).unwrap());
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("Warning:"), "stderr: {}", stderr);
    }

    #[test]
    fn test_confirm_large_n_other() {
        let mut r = io::Cursor::new(b"maybe\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert!(!confirm_large_n_with(&mut r, &mut out, &mut err, 12).unwrap());
    }

    // --- prompt_n_with ---

    #[test]
    fn test_prompt_n_valid() {
        let mut r = io::Cursor::new(b"9\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 9);
    }

    #[test]
    fn test_prompt_n_minimum() {
        let mut r = io::Cursor::new(b"1\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 1);
    }

    #[test]
    fn test_prompt_n_maximum() {
        let mut r = io::Cursor::new(b"18\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 18);
    }

    #[test]
    fn test_prompt_n_zero_retries() {
        // 0 is invalid; retries and accepts 5
        let mut r = io::Cursor::new(b"0\n5\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 5);
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("between 1 and 18"), "stderr: {}", stderr);
    }

    #[test]
    fn test_prompt_n_non_numeric_retries() {
        let mut r = io::Cursor::new(b"abc\n7\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 7);
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("positive integer"), "stderr: {}", stderr);
    }

    #[test]
    fn test_prompt_n_above_max_retries() {
        let mut r = io::Cursor::new(b"19\n6\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 6);
    }

    proptest! {
        #[test]
        fn prop_sieve_elements_are_primes(limit in 2u64..=1_000u64) {
            let primes = small_sieve(limit);
            for &p in &primes {
                prop_assert!(p >= 2, "prime {} should be >= 2", p);
            }
        }
    }

    // --- find_primes (end-to-end) ---

    #[test]
    fn test_find_primes_below_2() {
        let mut buf: Vec<u8> = Vec::new();
        let count = find_primes(1, &mut buf).unwrap();
        assert_eq!(count, 0);
        assert!(buf.is_empty());
    }

    #[test]
    fn test_find_primes_limit_2() {
        // limit=2: exactly one prime, output is "2\n"
        let mut buf: Vec<u8> = Vec::new();
        let count = find_primes(2, &mut buf).unwrap();
        assert_eq!(count, 1);
        assert_eq!(String::from_utf8(buf).unwrap(), "2\n");
    }

    #[test]
    fn test_find_primes_write_error_propagates() {
        // limit=2 tries to write "2\n"; FailWriter returns an error immediately.
        let result = find_primes(2, &mut FailWriter);
        assert!(result.is_err());
    }

    #[test]
    fn test_find_primes_up_to_10() {
        let mut buf: Vec<u8> = Vec::new();
        let count = find_primes(10, &mut buf).unwrap();
        assert_eq!(count, 4);
        assert_eq!(String::from_utf8(buf).unwrap(), "2\n3\n5\n7\n");
    }

    #[test]
    fn test_find_primes_count_100() {
        // π(100) = 25
        let mut buf: Vec<u8> = Vec::new();
        let count = find_primes(100, &mut buf).unwrap();
        assert_eq!(count, 25);
    }

    #[test]
    fn test_find_primes_count_1000() {
        // π(1000) = 168
        let mut buf: Vec<u8> = Vec::new();
        let count = find_primes(1_000, &mut buf).unwrap();
        assert_eq!(count, 168);
    }

    #[test]
    fn test_find_primes_count_1_million() {
        // π(10^6) = 78,498
        let mut buf: Vec<u8> = Vec::new();
        let count = find_primes(1_000_000, &mut buf).unwrap();
        assert_eq!(count, 78_498);
    }

    #[test]
    fn test_find_primes_last_prime_before_million() {
        let mut buf: Vec<u8> = Vec::new();
        find_primes(1_000_000, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert_eq!(output.lines().last().unwrap(), "999983");
    }

    #[test]
    fn test_find_primes_no_even_numbers_except_2() {
        let mut buf: Vec<u8> = Vec::new();
        find_primes(10_000, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        let bad: Vec<&str> = output
            .lines()
            .filter(|&l| l != "2" && l.parse::<u64>().map(|n| n % 2 == 0).unwrap_or(false))
            .collect();
        assert!(bad.is_empty(), "unexpected even primes: {:?}", bad);
    }

    // --- run ---

    #[test]
    fn test_run_invalid_n_exits_one() {
        let dir = tempdir().unwrap();
        let cli = Cli { digits: Some(0) };
        let mut r = io::Cursor::new(b"" as &[u8]);
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(cli, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 1);
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("between 1 and 18"), "stderr: {}", stderr);
    }

    #[test]
    fn test_run_n_1_display_y() {
        // N=1 → primes up to 10 = {2,3,5,7}; user chooses "y" to display
        let dir = tempdir().unwrap();
        let cli = Cli { digits: Some(1) };
        let mut r = io::Cursor::new(b"y\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(cli, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("2\n"), "stdout: {}", stdout);
        assert!(stdout.contains("7\n"), "stdout: {}", stdout);
    }

    #[test]
    fn test_run_n_1_save_n() {
        // N=1 → user chooses "n" → file saved to tempdir
        let dir = tempdir().unwrap();
        let cli = Cli { digits: Some(1) };
        let mut r = io::Cursor::new(b"n\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(cli, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("Saved to"), "stdout: {}", stdout);
        assert!(dir.path().join("primes_1e1.txt").exists());
    }

    #[test]
    fn test_run_n_7_streams_to_file() {
        // N=7 → large path → streams to file (π(10^7) = 664,579)
        let dir = tempdir().unwrap();
        let cli = Cli { digits: Some(7) };
        let mut r = io::Cursor::new(b"" as &[u8]);
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(cli, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("Saved to"), "stdout: {}", stdout);
        assert!(dir.path().join("primes_1e7.txt").exists());
    }

    #[test]
    fn test_run_large_n_decline() {
        // N=11 triggers the large-N confirm path; user declines
        let dir = tempdir().unwrap();
        let cli = Cli { digits: Some(11) };
        let mut r = io::Cursor::new(b"n\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(cli, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        assert!(!dir.path().join("primes_1e11.txt").exists());
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("Warning:"), "stderr: {}", stderr);
    }

    #[test]
    fn test_run_no_arg_prompts() {
        // No CLI arg → prompts for N; user enters 1 then chooses display
        let dir = tempdir().unwrap();
        let cli = Cli { digits: None };
        let mut r = io::Cursor::new(b"1\ny\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(cli, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("Enter N"), "stdout: {}", stdout);
        assert!(stdout.contains("2\n"), "stdout: {}", stdout);
    }

    #[test]
    fn run_returns_err_on_stdout_failure() {
        let dir = tempdir().unwrap();
        let mut err = Vec::new();
        let mut reader = io::Cursor::new(b"n\n");
        let cli = Cli { digits: Some(1) };
        let result = run(cli, &mut reader, &mut FailWriter, &mut err, dir.path());
        assert!(result.is_err());
    }

    #[test]
    fn run_returns_err_on_stderr_failure() {
        // digits=0 is invalid; run() writes error to stderr
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut reader = io::Cursor::new(b"");
        let cli = Cli { digits: Some(0) };
        let result = run(cli, &mut reader, &mut out, &mut FailWriter, dir.path());
        assert!(result.is_err());
    }
}
