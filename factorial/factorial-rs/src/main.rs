use std::io::{self, BufRead, Write};
use std::path::{Path, PathBuf};

use rug::ops::Pow;
use rug::Integer;

fn sieve(n: u64) -> Vec<u32> {
    if n < 2 {
        return vec![];
    }
    let n = n as usize;
    let mut is_composite = vec![false; n + 1];
    is_composite[0] = true;
    is_composite[1] = true;
    let mut p = 2usize;
    while p * p <= n {
        if !is_composite[p] {
            let mut m = p * p;
            while m <= n {
                is_composite[m] = true;
                m += p;
            }
        }
        p += 1;
    }
    (2..=n)
        .filter(|&i| !is_composite[i])
        .map(|i| i as u32)
        .collect()
}

fn compute_swing_chunk(m: u64, primes: &[u32]) -> Integer {
    let mut result = Integer::from(1u64);
    for &p in primes {
        let p = p as u64;
        if p > m {
            break; // primes is sorted ascending
        }
        let mut exp = 0u32;
        let mut q = m;
        while q >= p {
            q /= p;
            if q & 1 == 1 {
                exp += 1;
            }
        }
        if exp > 0 {
            result *= Integer::from(p).pow(exp);
        }
    }
    result
}

fn compute_swing(m: u64, primes: &[u32]) -> Integer {
    use rayon::prelude::*;

    let relevant: Vec<u32> = primes
        .iter()
        .copied()
        .take_while(|&p| p as u64 <= m)
        .collect();
    if relevant.is_empty() {
        return Integer::from(1u64);
    }

    let num_threads = rayon::current_num_threads().max(1);
    let chunk_size = relevant.len().div_ceil(num_threads).max(1);

    relevant
        .par_chunks(chunk_size)
        .map(|chunk| compute_swing_chunk(m, chunk))
        .reduce(
            || Integer::from(1u64),
            |a, b| {
                let mut r = a;
                r *= b;
                r
            },
        )
}

fn factorial_rec(n: u64, primes: &[u32]) -> Integer {
    if n <= 1 {
        return Integer::from(1u64);
    }
    let half = factorial_rec(n / 2, primes);
    let swing = compute_swing(n, primes);
    Integer::from(&half * &half) * swing
}

fn calculate_factorial(n: u64) -> Integer {
    if n <= 1 {
        return Integer::from(1u64);
    }
    let primes = sieve(n);
    factorial_rec(n, &primes)
}

fn fmt_int(n: u64) -> String {
    let s = n.to_string();
    let mut result = String::new();
    let chars: Vec<char> = s.chars().collect();
    let len = chars.len();
    for (i, &c) in chars.iter().enumerate() {
        if i > 0 && (len - i).is_multiple_of(3) {
            result.push(',');
        }
        result.push(c);
    }
    result
}

fn read_line_from<R: BufRead>(reader: &mut R) -> io::Result<String> {
    let mut line = String::new();
    reader.read_line(&mut line)?;
    Ok(line.trim().to_string())
}

fn prompt_n_with<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    err: &mut E,
) -> io::Result<u64> {
    loop {
        write!(out, "Enter N to compute N! : ")?;
        out.flush()?;
        let line = read_line_from(reader)?;
        match line.parse::<u64>() {
            Ok(n) => return Ok(n),
            Err(_) => writeln!(
                err,
                "Invalid input '{}'. Please enter a non-negative integer.",
                line
            )?,
        }
    }
}

// ---------------------------------------------------------------------------
// Orchestrator
// ---------------------------------------------------------------------------

fn run<R: BufRead, W: Write, E: Write>(
    n_arg: Option<&str>,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    dir: &Path,
) -> io::Result<i32> {
    let n = match n_arg {
        Some(s) => match s.parse::<u64>() {
            Ok(v) => v,
            Err(_) => {
                writeln!(err, "Error: '{}' is not a valid non-negative integer", s)?;
                return Ok(1);
            }
        },
        None => prompt_n_with(reader, out, err)?,
    };

    writeln!(err, "Computing {}! ...", fmt_int(n))?;
    let start = std::time::Instant::now();
    let result = calculate_factorial(n);
    let elapsed = start.elapsed();
    writeln!(err, "Computed in {:.2}s", elapsed.as_secs_f64())?;

    let digits_str = result.to_string_radix(10);
    let digit_count = digits_str.len();
    let path = dir.join(format!("factorial_{}.txt", n));

    writeln!(
        err,
        "Writing {} digits to {} ...",
        fmt_int(digit_count as u64),
        path.display()
    )?;
    let write_start = std::time::Instant::now();
    std::fs::write(&path, &digits_str)?;
    let write_elapsed = write_start.elapsed();
    writeln!(
        err,
        "{} digits written to {} in {:.2}s",
        fmt_int(digit_count as u64),
        path.display(),
        write_elapsed.as_secs_f64()
    )?;

    Ok(0)
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let n_arg = args.get(1).map(|s| s.as_str());
    let stdin = io::stdin();
    let mut reader = stdin.lock();
    let stdout = io::stdout();
    let mut out = stdout.lock();
    let stderr = io::stderr();
    let mut err = stderr.lock();
    let dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let code = run(n_arg, &mut reader, &mut out, &mut err, &dir).unwrap_or(1);
    std::process::exit(code);
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    // --- sieve ---

    #[test]
    fn test_sieve_below_2_empty() {
        assert!(sieve(0).is_empty());
        assert!(sieve(1).is_empty());
    }

    #[test]
    fn test_sieve_n_equals_2() {
        assert_eq!(sieve(2), vec![2u32]);
    }

    #[test]
    fn test_sieve_small_known() {
        assert_eq!(sieve(10), vec![2u32, 3, 5, 7]);
    }

    #[test]
    fn test_sieve_no_composites() {
        let primes = sieve(20);
        for &p in &primes {
            assert!(p < 2 || (2..p).all(|d| p % d != 0), "{} is composite", p);
        }
    }

    #[test]
    fn test_sieve_count_to_100() {
        // π(100) = 25
        assert_eq!(sieve(100).len(), 25);
    }

    #[test]
    fn test_sieve_count_to_1000() {
        // π(1000) = 168
        assert_eq!(sieve(1000).len(), 168);
    }

    // --- compute_swing_chunk ---

    #[test]
    fn test_swing_chunk_empty() {
        assert_eq!(compute_swing_chunk(10, &[]), Integer::from(1u64));
    }

    #[test]
    fn test_swing_chunk_prime_exceeds_m() {
        assert_eq!(compute_swing_chunk(2, &[3u32, 5, 7]), Integer::from(1u64));
    }

    #[test]
    fn test_swing_chunk_m_equals_2() {
        // p=2: q=2->1(odd,+1) -> exp=1, 2^1=2
        assert_eq!(compute_swing_chunk(2, &[2u32]), Integer::from(2u64));
    }

    #[test]
    fn test_swing_chunk_p2_contribution_for_m6() {
        // p=2 for m=6: q=6->3(odd,+1)->1(odd,+1) -> exp=2, contrib=4
        assert_eq!(compute_swing_chunk(6, &[2u32]), Integer::from(4u64));
    }

    #[test]
    fn test_swing_chunk_p3_contribution_for_m6() {
        // p=3 for m=6: q=6->2(even) -> exp=0, contrib=1
        assert_eq!(compute_swing_chunk(6, &[3u32]), Integer::from(1u64));
    }

    #[test]
    fn test_swing_chunk_p5_contribution_for_m6() {
        // p=5 for m=6: q=6->1(odd,+1) -> exp=1, contrib=5
        assert_eq!(compute_swing_chunk(6, &[5u32]), Integer::from(5u64));
    }

    // --- compute_swing ---

    #[test]
    fn test_swing_0() {
        let primes = sieve(10);
        assert_eq!(compute_swing(0, &primes), Integer::from(1u64));
    }

    #[test]
    fn test_swing_1() {
        let primes = sieve(10);
        assert_eq!(compute_swing(1, &primes), Integer::from(1u64));
    }

    #[test]
    fn test_swing_2() {
        let primes = sieve(10);
        assert_eq!(compute_swing(2, &primes), Integer::from(2u64));
    }

    #[test]
    fn test_swing_6() {
        // swing(6) = 4 * 1 * 5 = 20
        let primes = sieve(10);
        assert_eq!(compute_swing(6, &primes), Integer::from(20u64));
    }

    #[test]
    fn test_swing_4() {
        // swing(4): p=2 exp=1->2, p=3 exp=1->3. swing(4) = 6
        let primes = sieve(10);
        assert_eq!(compute_swing(4, &primes), Integer::from(6u64));
    }

    #[test]
    fn test_swing_empty_primes() {
        assert_eq!(compute_swing(100, &[]), Integer::from(1u64));
    }

    #[test]
    fn test_swing_satisfies_factorial_identity() {
        // swing(6) * 3!^2 = 20 * 36 = 720 = 6!
        let primes = sieve(10);
        let sw6 = compute_swing(6, &primes);
        let three_factorial_sq = Integer::from(36u64);
        assert_eq!(sw6 * three_factorial_sq, Integer::from(720u64));
    }

    // --- factorial_rec ---

    #[test]
    fn test_factorial_rec_base_0() {
        let primes = sieve(10);
        assert_eq!(factorial_rec(0, &primes), Integer::from(1u64));
    }

    #[test]
    fn test_factorial_rec_base_1() {
        let primes = sieve(10);
        assert_eq!(factorial_rec(1, &primes), Integer::from(1u64));
    }

    #[test]
    fn test_factorial_rec_2() {
        let primes = sieve(10);
        assert_eq!(factorial_rec(2, &primes), Integer::from(2u64));
    }

    #[test]
    fn test_factorial_rec_5() {
        let primes = sieve(10);
        assert_eq!(factorial_rec(5, &primes), Integer::from(120u64));
    }

    // --- fmt_int ---

    #[test]
    fn test_fmt_int_zero() {
        assert_eq!(fmt_int(0), "0");
    }

    #[test]
    fn test_fmt_int_sub_thousand() {
        assert_eq!(fmt_int(999), "999");
    }

    #[test]
    fn test_fmt_int_thousands() {
        assert_eq!(fmt_int(1000), "1,000");
    }

    #[test]
    fn test_fmt_int_millions() {
        assert_eq!(fmt_int(1_234_567), "1,234,567");
    }

    #[test]
    fn test_fmt_int_large() {
        assert_eq!(fmt_int(1_000_000_000), "1,000,000,000");
    }

    // --- calculate_factorial ---

    #[test]
    fn test_calculate_factorial_0() {
        assert_eq!(calculate_factorial(0), Integer::from(1u64));
    }

    #[test]
    fn test_calculate_factorial_1() {
        assert_eq!(calculate_factorial(1), Integer::from(1u64));
    }

    #[test]
    fn test_calculate_factorial_2() {
        assert_eq!(calculate_factorial(2), Integer::from(2u64));
    }

    #[test]
    fn test_calculate_factorial_3() {
        assert_eq!(calculate_factorial(3), Integer::from(6u64));
    }

    #[test]
    fn test_calculate_factorial_4() {
        assert_eq!(calculate_factorial(4), Integer::from(24u64));
    }

    #[test]
    fn test_calculate_factorial_5() {
        assert_eq!(calculate_factorial(5), Integer::from(120u64));
    }

    #[test]
    fn test_calculate_factorial_10() {
        assert_eq!(calculate_factorial(10), Integer::from(3628800u64));
    }

    #[test]
    fn test_calculate_factorial_20() {
        assert_eq!(
            calculate_factorial(20),
            Integer::from(2432902008176640000u64)
        );
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
        let mut r = io::Cursor::new(b"  42  \n");
        assert_eq!(read_line_from(&mut r).unwrap(), "42");
    }

    // --- prompt_n_with ---

    #[test]
    fn test_prompt_n_valid() {
        let mut r = io::Cursor::new(b"10\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 10);
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("Enter N"), "stdout: {}", stdout);
    }

    #[test]
    fn test_prompt_n_zero() {
        let mut r = io::Cursor::new(b"0\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 0);
    }

    #[test]
    fn test_prompt_n_retry_on_non_numeric() {
        let mut r = io::Cursor::new(b"abc\n5\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 5);
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("Invalid input"), "stderr: {}", stderr);
    }

    #[test]
    fn test_prompt_n_retry_on_negative() {
        // u64 doesn't parse negative, so "-1" is a parse error → retry
        let mut r = io::Cursor::new(b"-1\n3\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 3);
    }

    // --- run ---

    #[test]
    fn test_run_invalid_arg_exits_one() {
        let dir = tempdir().unwrap();
        let mut r = io::Cursor::new(b"" as &[u8]);
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(Some("abc"), &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 1);
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("not a valid"), "stderr: {}", stderr);
    }

    #[test]
    fn test_run_valid_arg_creates_file() {
        let dir = tempdir().unwrap();
        let mut r = io::Cursor::new(b"" as &[u8]);
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(Some("10"), &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("factorial_10.txt");
        assert!(path.exists());
        let content = std::fs::read_to_string(&path).unwrap();
        assert_eq!(content.trim(), "3628800");
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("digits written"), "stderr: {}", stderr);
    }

    #[test]
    fn test_run_no_arg_prompts() {
        let dir = tempdir().unwrap();
        let mut r = io::Cursor::new(b"5\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(None, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        assert!(dir.path().join("factorial_5.txt").exists());
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("Enter N"), "stdout: {}", stdout);
    }

    #[test]
    fn test_run_n_0_creates_file() {
        // 0! = 1
        let dir = tempdir().unwrap();
        let mut r = io::Cursor::new(b"" as &[u8]);
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(Some("0"), &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("factorial_0.txt");
        assert!(path.exists());
        let content = std::fs::read_to_string(&path).unwrap();
        assert_eq!(content.trim(), "1");
    }

    #[test]
    fn test_run_idempotent() {
        // Running twice for same n overwrites the file with identical content
        let dir = tempdir().unwrap();
        for _ in 0..2 {
            let mut r = io::Cursor::new(b"" as &[u8]);
            let mut out = Vec::new();
            let mut err = Vec::new();
            let code = run(Some("3"), &mut r, &mut out, &mut err, dir.path()).unwrap();
            assert_eq!(code, 0);
        }
        let content = std::fs::read_to_string(dir.path().join("factorial_3.txt")).unwrap();
        assert_eq!(content.trim(), "6");
    }
}
