use std::io::{self, BufRead, BufWriter, Write};
use std::path::Path;

use clap::Parser;

#[derive(Parser)]
#[command(name = "goldbach", about = "Find all Goldbach pairs for even numbers up to 10^N")]
struct Cli {
    /// N: finds all Goldbach pairs for even numbers up to 10^N (1-8)
    exponent: Option<u32>,
}

// ---------------------------------------------------------------------------
// Sieve
// ---------------------------------------------------------------------------

/// Build a packed bitset covering odd numbers 3..=limit.
/// Bit index i represents 2i+3. Bit set (1) = composite; clear (0) = prime.
/// Callers must only pass n ≤ limit to is_prime; no bounds check is performed.
fn build_sieve(limit: u64) -> Vec<u64> {
    if limit < 3 {
        return vec![];
    }
    let count = ((limit - 3) / 2 + 1) as usize;
    let words = count.div_ceil(64);
    let mut sieve = vec![0u64; words];
    let mut p = 3u64;
    while p * p <= limit {
        let pi = ((p - 3) / 2) as usize;
        if (sieve[pi / 64] >> (pi % 64)) & 1 == 0 {
            let mut m = p * p;
            while m <= limit {
                let mi = ((m - 3) / 2) as usize;
                sieve[mi / 64] |= 1u64 << (mi % 64);
                m += 2 * p;
            }
        }
        p += 2;
    }
    sieve
}

/// Return true if n is prime, using the sieve built for the same limit.
/// Panics if n > limit (caller's responsibility to stay in range).
fn is_prime(n: u64, sieve: &[u64]) -> bool {
    match n {
        0 | 1 => false,
        2 => true,
        _ if n.is_multiple_of(2) => false,
        _ => {
            let idx = ((n - 3) / 2) as usize;
            (sieve[idx / 64] >> (idx % 64)) & 1 == 0
        }
    }
}

// ---------------------------------------------------------------------------
// Core algorithm
// ---------------------------------------------------------------------------

/// Write all Goldbach pairs for even n in 4..=limit to `out`.
/// Each line: `n p q\n` with p ≤ q and p + q = n, ordered by n then p.
/// Returns the total number of pairs written.
fn goldbach_pairs<W: Write>(limit: u64, sieve: &[u64], out: &mut W) -> io::Result<u64> {
    let mut count = 0u64;
    let mut n = 4u64;
    while n <= limit {
        if is_prime(n - 2, sieve) {
            writeln!(out, "{n} 2 {}", n - 2)?;
            count += 1;
        }
        let mut p = 3u64;
        while p <= n / 2 {
            if is_prime(p, sieve) && is_prime(n - p, sieve) {
                writeln!(out, "{n} {p} {}", n - p)?;
                count += 1;
            }
            p += 2;
        }
        n += 2;
    }
    Ok(count)
}

// ---------------------------------------------------------------------------
// I/O helpers
// ---------------------------------------------------------------------------

fn prompt_n<R: BufRead, W: Write>(reader: &mut R, out: &mut W) -> io::Result<u64> {
    loop {
        write!(out, "Enter N (finds all Goldbach pairs up to 10^N, max 8): ")?;
        out.flush()?;
        let mut line = String::new();
        reader.read_line(&mut line)?;
        match line.trim().parse::<u64>() {
            Ok(v) if (1..=8).contains(&v) => return Ok(v),
            _ => writeln!(out, "N must be between 1 and 8.")?,
        }
    }
}

// ---------------------------------------------------------------------------
// Orchestration
// ---------------------------------------------------------------------------

fn run<R: BufRead, W: Write, E: Write>(
    cli: Cli,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    dir: &Path,
) -> io::Result<i32> {
    let exp: u64 = match cli.exponent {
        Some(v) => {
            if !(1..=8).contains(&v) {
                writeln!(err, "Error: N must be between 1 and 8.")?;
                return Ok(1);
            }
            if v > 6 {
                writeln!(err, "Warning: N={v} output may exceed 20 GB and take hours or days.")?;
            }
            v as u64
        }
        None => prompt_n(reader, out)?,
    };

    let limit = 10u64.pow(exp as u32);
    writeln!(out, "Goldbach Pair Finder (Rust)")?;
    writeln!(out, "{}", "=".repeat(40))?;
    writeln!(out, "Finding all Goldbach pairs for even n in 4..10^{exp} = {limit}")?;
    writeln!(out)?;
    writeln!(out, "Building sieve...")?;

    let sieve = build_sieve(limit);

    let path = dir.join(format!("goldbach_1e{exp}.txt"));
    writeln!(out, "Writing pairs to {}...", path.display())?;

    let file = std::fs::File::create(&path)?;
    let mut writer = BufWriter::new(file);
    let count = goldbach_pairs(limit, &sieve, &mut writer)?;
    writer.flush()?;

    writeln!(out)?;
    writeln!(out, "Found {count} pairs. Saved to {}", path.display())?;
    Ok(0)
}

#[cfg(not(tarpaulin_include))]
fn main() {
    let cli = Cli::parse();
    let stdin = io::stdin();
    let stdout = io::stdout();
    let stderr = io::stderr();
    let mut reader = stdin.lock();
    let mut out = stdout.lock();
    let mut err = stderr.lock();
    let cwd = std::env::current_dir().expect("cwd unavailable");
    let code = run(cli, &mut reader, &mut out, &mut err, &cwd).expect("io error");
    std::process::exit(code);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    use tempfile::tempdir;

    // --- build_sieve ---
    #[test]
    fn test_build_sieve_limit_2() {
        assert!(build_sieve(2).is_empty());
    }

    #[test]
    fn test_build_sieve_limit_10_primes_correct() {
        let sieve = build_sieve(10);
        assert!(is_prime(3, &sieve));
        assert!(is_prime(5, &sieve));
        assert!(is_prime(7, &sieve));
        assert!(!is_prime(9, &sieve));
    }

    #[test]
    fn test_build_sieve_limit_100_prime_count() {
        let sieve = build_sieve(100);
        // 24 odd primes in [3, 100]; total π(100) = 25 (including 2)
        let count = (3u64..=100).step_by(2).filter(|&n| is_prime(n, &sieve)).count();
        assert_eq!(count, 24);
    }

    // --- is_prime ---
    #[test]
    fn test_is_prime_edge_cases() {
        let sieve = build_sieve(10);
        assert!(!is_prime(0, &sieve));
        assert!(!is_prime(1, &sieve));
        assert!(is_prime(2, &sieve));
    }

    #[test]
    fn test_is_prime_small_values() {
        let sieve = build_sieve(10);
        assert!(is_prime(3, &sieve));
        assert!(!is_prime(4, &sieve));
        assert!(is_prime(5, &sieve));
        assert!(!is_prime(6, &sieve));
        assert!(is_prime(7, &sieve));
        assert!(!is_prime(9, &sieve));
    }

    #[test]
    fn test_is_prime_large_prime_and_composite() {
        let sieve = build_sieve(100);
        assert!(is_prime(97, &sieve));
        assert!(!is_prime(91, &sieve)); // 7 × 13
    }

    // --- goldbach_pairs ---
    #[test]
    fn test_goldbach_pairs_limit_4() {
        let sieve = build_sieve(4);
        let mut out = Vec::new();
        let count = goldbach_pairs(4, &sieve, &mut out).unwrap();
        assert_eq!(count, 1);
        assert_eq!(String::from_utf8_lossy(&out).trim(), "4 2 2");
    }

    #[test]
    fn test_goldbach_pairs_limit_10_exact() {
        let sieve = build_sieve(10);
        let mut out = Vec::new();
        let count = goldbach_pairs(10, &sieve, &mut out).unwrap();
        assert_eq!(count, 5);
        let output = String::from_utf8_lossy(&out).into_owned();
        let lines: Vec<&str> = output.trim().lines().collect();
        assert_eq!(lines[0], "4 2 2");
        assert_eq!(lines[1], "6 3 3");
        assert_eq!(lines[2], "8 3 5");
        assert_eq!(lines[3], "10 3 7");
        assert_eq!(lines[4], "10 5 5");
    }

    #[test]
    fn test_goldbach_pairs_count_matches_lines() {
        let sieve = build_sieve(10);
        let mut out = Vec::new();
        let count = goldbach_pairs(10, &sieve, &mut out).unwrap();
        let output = String::from_utf8_lossy(&out).into_owned();
        let line_count = output.trim().lines().count() as u64;
        assert_eq!(count, line_count);
    }

    struct FailWriter;
    impl Write for FailWriter {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::other("injected write failure"))
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    // --- run ---
    #[test]
    fn test_run_n0_returns_1() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(0) }, &mut reader, &mut out, &mut err_buf, dir.path())
            .unwrap();
        assert_eq!(code, 1);
        assert!(String::from_utf8_lossy(&err_buf).contains("between 1 and 8"));
    }

    #[test]
    fn test_run_n9_returns_1() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(9) }, &mut reader, &mut out, &mut err_buf, dir.path())
            .unwrap();
        assert_eq!(code, 1);
    }

    #[test]
    fn test_run_n1_creates_file() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(1) }, &mut reader, &mut out, &mut err_buf, dir.path())
            .unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("goldbach_1e1.txt");
        assert!(path.exists());
        let content = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<&str> = content.trim().lines().collect();
        assert_eq!(lines.len(), 5);
        assert_eq!(lines[0], "4 2 2");
        assert_eq!(lines[4], "10 5 5");
    }

    #[test]
    fn test_run_n2_last_line() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(2) }, &mut reader, &mut out, &mut err_buf, dir.path())
            .unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("goldbach_1e2.txt");
        let content = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<&str> = content.trim().lines().collect();
        assert!(lines.len() > 5);
        assert_eq!(*lines.last().unwrap(), "100 47 53");
    }

    #[test]
    fn test_run_no_arg_prompts() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("1\n");
        let code =
            run(Cli { exponent: None }, &mut reader, &mut out, &mut err_buf, dir.path()).unwrap();
        assert_eq!(code, 0);
        assert!(String::from_utf8_lossy(&out).contains("Enter N"));
    }

    #[test]
    fn test_run_invalid_stdin_prompt() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("0\nabc\n2\n");
        let code =
            run(Cli { exponent: None }, &mut reader, &mut out, &mut err_buf, dir.path()).unwrap();
        assert_eq!(code, 0);
    }

    #[test]
    fn test_run_err_on_stdout_failure() {
        let dir = tempdir().unwrap();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let result =
            run(Cli { exponent: Some(1) }, &mut reader, &mut FailWriter, &mut err_buf, dir.path());
        assert!(result.is_err());
    }

    #[test]
    fn test_run_err_on_stderr_failure() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut reader = Cursor::new("");
        let result =
            run(Cli { exponent: Some(0) }, &mut reader, &mut out, &mut FailWriter, dir.path());
        assert!(result.is_err());
    }
}
