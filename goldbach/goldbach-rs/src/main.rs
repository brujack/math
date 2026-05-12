use std::io::{self, BufRead, Write};
use std::path::Path;

use clap::Parser;

#[derive(Parser)]
#[command(name = "goldbach", about = "Find all Goldbach pairs for even numbers up to 10^N")]
struct Cli {
    /// N: finds all Goldbach pairs for even numbers up to 10^N (1-8)
    exponent: Option<u32>,
}

fn run<R: BufRead, W: Write, E: Write>(
    _cli: Cli,
    _reader: &mut R,
    _out: &mut W,
    _err: &mut E,
    _dir: &Path,
) -> io::Result<i32> {
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

    #[test]
    fn test_stub_compiles() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(1) }, &mut reader, &mut out, &mut err_buf, dir.path())
            .unwrap();
        assert_eq!(code, 0);
    }
}
