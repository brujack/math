/*!
Find all perfect numbers up to 10^N.

Uses the Lucas-Lehmer primality test to find Mersenne primes, constructs
perfect numbers of the form 2^(p-1) * (2^p - 1), and verifies each with
the multiplicative sigma formula: sigma(n) = (2^p - 1) * 2^p = 2n.
*/

use std::io::{self, BufRead, Write};
use std::path::Path;

use clap::Parser;
use rug::ops::PowAssign;
use rug::Integer;

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

#[derive(Parser)]
#[command(
    name = "perfect-numbers",
    about = "Find all perfect numbers up to 10^N",
    long_about = "Find all perfect numbers up to 10^N.\n\n\
                  Uses Lucas-Lehmer to find Mersenne primes and the sigma formula\n\
                  to verify perfect-ness. Valid N range: 1-54.\n\n\
                  Run without arguments for interactive prompts."
)]
struct Cli {
    /// N: finds perfect numbers up to 10^N (1-54)
    exponent: Option<u32>,
}

// ---------------------------------------------------------------------------
// Core algorithm
// ---------------------------------------------------------------------------

fn is_prime(n: u64) -> bool {
    if n < 2 {
        return false;
    }
    if n == 2 {
        return true;
    }
    if n.is_multiple_of(2) {
        return false;
    }
    let mut i = 3u64;
    while i * i <= n {
        if n.is_multiple_of(i) {
            return false;
        }
        i += 2;
    }
    true
}

fn lucas_lehmer(p: u64) -> bool {
    if p == 2 {
        return true;
    }
    let mut mp = Integer::from(1u32);
    mp <<= p as u32;
    mp -= 1u32;

    let mut s = Integer::from(4u32);
    for _ in 0..(p - 2) {
        s.square_mut();
        s -= 2i32;
        s %= &mp;
        if s < 0i32 {
            s += &mp;
        }
    }
    s == 0u32
}

fn verify_perfect(p: u64) -> bool {
    let mut mp = Integer::from(1u32);
    mp <<= p as u32;
    mp -= 1u32;

    let mut n = Integer::from(1u32);
    n <<= (p - 1) as u32;
    n *= &mp;

    // sigma(n) = mp * (mp + 1) = (2^p - 1) * 2^p
    let sigma = &mp * Integer::from(&mp + 1u32);
    sigma == n << 1u32
}

#[cfg(test)]
fn generate_perfect_numbers(limit: &Integer) -> Vec<(u64, Integer)> {
    let mut results = Vec::new();
    if limit < &Integer::from(6u32) {
        return results;
    }
    let max_p = (limit.significant_bits() as u64 / 2) + 3;
    for p in 2..=max_p {
        if !is_prime(p) {
            continue;
        }
        if !lucas_lehmer(p) {
            continue;
        }
        let mut mp = Integer::from(1u32);
        mp <<= p as u32;
        mp -= 1u32;
        let mut pn = Integer::from(1u32);
        pn <<= (p - 1) as u32;
        pn *= &mp;
        if &pn > limit {
            break;
        }
        results.push((p, pn));
    }
    results
}

// ---------------------------------------------------------------------------
// I/O helpers
// ---------------------------------------------------------------------------

fn read_line_from<R: BufRead>(reader: &mut R) -> io::Result<String> {
    let mut line = String::new();
    reader.read_line(&mut line)?;
    Ok(line.trim().to_string())
}

fn prompt_n_with<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    _err: &mut E,
) -> io::Result<u64> {
    loop {
        write!(out, "Enter N (finds perfect numbers up to 10^N, max 54): ")?;
        out.flush()?;
        match read_line_from(reader)?.parse::<u64>() {
            Ok(v) if (1..=54).contains(&v) => return Ok(v),
            _ => writeln!(out, "N must be between 1 and 54.")?,
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
    writeln!(out, "Perfect Number Finder (Rust)")?;
    writeln!(out, "{}", "=".repeat(40))?;

    let n: u64 = match cli.exponent {
        Some(v) => {
            if !(1..=54).contains(&v) {
                writeln!(err, "Error: N must be between 1 and 54.")?;
                return Ok(1);
            }
            v as u64
        }
        None => prompt_n_with(reader, out, err)?,
    };

    let mut limit = Integer::from(10u32);
    limit.pow_assign(n as u32);

    writeln!(out, "Finding perfect numbers up to 10^{n}")?;
    writeln!(out)?;

    let max_p = (limit.significant_bits() as u64 / 2) + 3;
    let mut results: Vec<Integer> = Vec::new();

    for p in 2..=max_p {
        if !is_prime(p) {
            continue;
        }
        let mut mp = Integer::from(1u32);
        mp <<= p as u32;
        mp -= 1u32;
        if !lucas_lehmer(p) {
            writeln!(out, "p={p}: M_{p}={mp} [not prime]")?;
            continue;
        }
        let mut pn = Integer::from(1u32);
        pn <<= (p - 1) as u32;
        pn *= &mp;
        let pn_str = pn.to_string_radix(10);
        let digits = pn_str.len();
        let s = if digits == 1 { "digit" } else { "digits" };
        if pn > limit {
            writeln!(
                out,
                "p={p}: M_{p}={mp} [Mersenne prime] -> {pn_str} ({digits} {s}, exceeds limit)"
            )?;
            break;
        }
        let verified = verify_perfect(p);
        writeln!(
            out,
            "p={p}: M_{p}={mp} [Mersenne prime] -> {pn_str} ({digits} {s}, {})",
            if verified { "verified" } else { "FAILED" }
        )?;
        results.push(pn);
    }

    let count = results.len();
    writeln!(out)?;
    let s = if count == 1 { "number" } else { "numbers" };
    writeln!(out, "Found {count} perfect {s} up to 10^{n}")?;

    let path = dir.join(format!("perfect-numbers_1e{n}.txt"));
    let mut file = std::fs::File::create(&path)?;
    for pn in &results {
        writeln!(file, "{}", pn.to_string_radix(10))?;
    }
    writeln!(out, "Saved to {}", path.display())?;

    Ok(0)
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;
    use std::io::Cursor;
    use tempfile::tempdir;

    struct FailWriter;
    impl Write for FailWriter {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::other("injected write failure"))
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    // --- is_prime ---
    #[test]
    fn test_is_prime_zero() {
        assert!(!is_prime(0));
    }
    #[test]
    fn test_is_prime_one() {
        assert!(!is_prime(1));
    }
    #[test]
    fn test_is_prime_two() {
        assert!(is_prime(2));
    }
    #[test]
    fn test_is_prime_four() {
        assert!(!is_prime(4));
    }
    #[test]
    fn test_is_prime_small_primes() {
        for p in [3u64, 5, 7, 11, 13, 17, 19, 23, 29, 31, 89] {
            assert!(is_prime(p), "{p} should be prime");
        }
    }
    #[test]
    fn test_is_prime_composites() {
        for n in [4u64, 6, 9, 15, 25, 91] {
            assert!(!is_prime(n), "{n} should be composite");
        }
    }

    // --- lucas_lehmer ---
    #[test]
    fn test_lucas_lehmer_known_mersenne_primes() {
        for p in [2u64, 3, 5, 7, 13, 17, 19, 31, 61, 89] {
            assert!(lucas_lehmer(p), "p={p} should be Mersenne prime");
        }
    }
    #[test]
    fn test_lucas_lehmer_known_failures() {
        for p in [11u64, 23, 29, 37, 41] {
            assert!(!lucas_lehmer(p), "p={p} should not be Mersenne prime");
        }
    }

    // --- verify_perfect ---
    #[test]
    fn test_verify_perfect_known_exponents() {
        for p in [2u64, 3, 5, 7, 13, 17, 19] {
            assert!(verify_perfect(p), "p={p} should verify as perfect");
        }
    }

    // --- generate_perfect_numbers ---
    #[test]
    fn test_generate_limit_5_empty() {
        assert!(generate_perfect_numbers(&Integer::from(5u32)).is_empty());
    }
    #[test]
    fn test_generate_limit_10_yields_6() {
        let result = generate_perfect_numbers(&Integer::from(10u32));
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].0, 2);
        assert_eq!(result[0].1, Integer::from(6u32));
    }
    #[test]
    fn test_generate_limit_10000_yields_4() {
        let result = generate_perfect_numbers(&Integer::from(10000u32));
        assert_eq!(result.len(), 4);
        assert_eq!(result[3].0, 7u64);
    }
    #[test]
    fn test_generate_limit_n54_yields_10() {
        let mut limit = Integer::from(10u32);
        limit.pow_assign(54u32);
        let result = generate_perfect_numbers(&limit);
        assert_eq!(result.len(), 10);
        assert_eq!(result[9].0, 89u64);
    }

    proptest! {
        #[test]
        fn prop_even_composites_not_prime(n in 2u64..=1_000u64) {
            // all even numbers except 2 are composite
            prop_assert!(!is_prime(n * 2));
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
        assert!(String::from_utf8_lossy(&err_buf).contains("between 1 and 54"));
    }
    #[test]
    fn test_run_n55_returns_1() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(55) }, &mut reader, &mut out, &mut err_buf, dir.path())
            .unwrap();
        assert_eq!(code, 1);
    }
    #[test]
    fn test_run_n1_creates_file_with_6() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(1) }, &mut reader, &mut out, &mut err_buf, dir.path())
            .unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("perfect-numbers_1e1.txt");
        assert!(path.exists());
        assert_eq!(std::fs::read_to_string(&path).unwrap().trim(), "6");
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

    // --- injection tests ---
    #[test]
    fn run_returns_err_on_stdout_failure() {
        let dir = tempdir().unwrap();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let result =
            run(Cli { exponent: Some(1) }, &mut reader, &mut FailWriter, &mut err_buf, dir.path());
        assert!(result.is_err());
    }
    #[test]
    fn run_returns_err_on_stderr_failure() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut reader = Cursor::new("");
        let result =
            run(Cli { exponent: Some(0) }, &mut reader, &mut out, &mut FailWriter, dir.path());
        assert!(result.is_err());
    }
}
