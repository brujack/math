use std::fs::File;
use std::io::{self, BufWriter, Write};

use clap::Parser;

#[derive(Parser)]
#[command(
    name = "twin-primes",
    about = "Find all twin prime pairs up to 10^N",
    long_about = "Find all twin prime pairs (p, p+2) where both primes are\n\
                  less than 10^N using a segmented Sieve of Eratosthenes.\n\n\
                  Output is written to twin-primes_1e{N}.txt, one pair per\n\
                  line in the format: p | p+2"
)]
struct Cli {
    /// N: finds every twin prime pair where both p and p+2 < 10^N (max 15)
    digits: u32,
}

/// Number range covered by one sieve segment. 2^19 = 524,288 numbers.
/// Packed bitset (odd numbers only) = 32,768 bytes — fits in L2 cache.
const SEG_SIZE: u64 = 1 << 19;

fn small_sieve(limit: u64) -> Vec<u64> {
    let n = limit as usize;
    if n < 2 {
        return vec![];
    }
    let mut composite = vec![false; n + 1];
    composite[0] = true;
    composite[1] = true;
    let mut i = 2usize;
    while i * i <= n {
        if !composite[i] {
            let mut j = i * i;
            while j <= n {
                composite[j] = true;
                j += i;
            }
        }
        i += 1;
    }
    (2..=n).filter(|&i| !composite[i]).map(|i| i as u64).collect()
}

fn fmt_int(n: u64) -> String {
    let s = n.to_string();
    let mut out = String::with_capacity(s.len() + s.len() / 3);
    for (i, ch) in s.chars().rev().enumerate() {
        if i > 0 && i % 3 == 0 {
            out.push(',');
        }
        out.push(ch);
    }
    out.chars().rev().collect()
}

/// Sieve odd numbers in [lo, lo + SEG_SIZE) ∩ [lo, limit] using `small_primes`.
///
/// Packed bitset: bit index i ↔ number lo + 2*i. 1 = composite, 0 = prime.
/// `lo` must be odd.
fn sieve_segment(lo: u64, limit: u64, small_primes: &[u64]) -> Vec<u64> {
    let hi = (lo + SEG_SIZE).min(limit + 1); // exclusive
    if lo >= hi {
        return vec![];
    }

    let n = (hi - lo).div_ceil(2) as usize;
    let n_bytes = n.div_ceil(8);
    let mut composite = vec![0u8; n_bytes];

    for &p in small_primes {
        if p == 2 {
            continue;
        }
        let rem = lo % p;
        let mut s = if rem == 0 { lo } else { lo + (p - rem) };
        if s % 2 == 0 {
            s += p;
        }
        if s >= hi {
            continue;
        }
        let mut idx = ((s - lo) / 2) as usize;
        let step = p as usize;
        while idx < n {
            composite[idx >> 3] |= 1u8 << (idx & 7);
            idx += step;
        }
    }

    (0..n)
        .filter(|&i| composite[i >> 3] & (1u8 << (i & 7)) == 0)
        .map(|i| lo + (i as u64) * 2)
        .collect()
}

/// Find all twin prime pairs (p, p+2) where both p and p+2 < limit.
/// Writes "p | p+2\n" per pair to `out`. Returns pair count.
fn find_twin_primes<W: Write>(limit: u64, out: &mut W) -> io::Result<u64> {
    if limit < 5 {
        return Ok(0);
    }

    let sqrt_limit = (limit as f64).sqrt() as u64 + 1;
    let small_primes = small_sieve(sqrt_limit);

    let mut count = 0u64;

    // Twin pairs within the small_primes range (both must be < limit).
    for w in small_primes.windows(2) {
        if w[1] - w[0] == 2 && w[1] < limit {
            writeln!(out, "{} | {}", w[0], w[1])?;
            count += 1;
        }
    }

    // Segmented sieve for (sqrt_limit, limit].
    // lo is always odd; SEG_SIZE is even so lo + SEG_SIZE stays odd.
    let mut last_prime: Option<u64> = small_primes.last().copied();
    let mut lo = sqrt_limit + 1 + (sqrt_limit & 1); // first odd > sqrt_limit

    while lo <= limit {
        let seg = sieve_segment(lo, limit, &small_primes);

        // Boundary: check if last prime from the previous segment + 2 equals
        // the first prime of this segment.
        if let (Some(lp), Some(&fp)) = (last_prime, seg.first()) {
            if fp == lp + 2 && fp < limit {
                writeln!(out, "{} | {}", lp, fp)?;
                count += 1;
            }
        }

        // Twin pairs within this segment.
        for w in seg.windows(2) {
            if w[1] - w[0] == 2 && w[1] < limit {
                writeln!(out, "{} | {}", w[0], w[1])?;
                count += 1;
            }
        }

        last_prime = seg.last().copied().or(last_prime);
        lo += SEG_SIZE;
    }

    Ok(count)
}

fn main() {
    let cli = Cli::parse();
    let digits = cli.digits;

    if !(1..=15).contains(&digits) {
        eprintln!("Error: N must be between 1 and 15.");
        std::process::exit(1);
    }

    let limit: u64 = 10u64.pow(digits);
    let filename = format!("twin-primes_1e{}.txt", digits);

    println!("Twin Prime Sieve");
    println!("{}", "=".repeat(40));
    println!("Finding twin prime pairs where both p and p+2 < 10^{} = {}", digits, fmt_int(limit));

    let file = File::create(&filename).unwrap_or_else(|e| {
        eprintln!("Error: cannot create {}: {}", filename, e);
        std::process::exit(1);
    });
    let mut writer = BufWriter::new(file);

    let count = find_twin_primes(limit, &mut writer).unwrap_or_else(|e| {
        eprintln!("Error writing output: {}", e);
        std::process::exit(1);
    });

    writer.flush().unwrap_or_else(|e| {
        eprintln!("Error flushing output: {}", e);
        std::process::exit(1);
    });

    println!("Found {} twin prime pairs up to 10^{}", fmt_int(count), digits);
    println!("Saved to {}", filename);
}

#[cfg(test)]
mod tests {
    use super::*;

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
        assert_eq!(
            small_sieve(30),
            vec![2u64, 3, 5, 7, 11, 13, 17, 19, 23, 29]
        );
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
        // Primes in [11, 30] given small primes [2,3,5,7].
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
            101u64, 103, 107, 109, 113, 127, 131, 137, 139, 149,
            151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199,
        ];
        assert_eq!(result, expected);
    }

    #[test]
    fn test_sieve_segment_all_odd() {
        // All returned values must be odd (segment starts at odd lo).
        let sp = small_sieve(32);
        let result = sieve_segment(101, 200, &sp);
        assert!(result.iter().all(|&p| p % 2 == 1));
    }

    #[test]
    fn test_sieve_segment_lo_exceeds_limit() {
        // lo > limit → empty.
        let sp = vec![2u64, 3, 5];
        assert!(sieve_segment(101, 100, &sp).is_empty());
    }

    #[test]
    fn test_sieve_segment_single_prime() {
        // lo == limit == 31 (a prime): returns exactly [31].
        let sp = small_sieve(5);
        assert_eq!(sieve_segment(31, 31, &sp), vec![31u64]);
    }

    // --- FailWriter ---

    struct FailWriter;
    impl Write for FailWriter {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::new(io::ErrorKind::Other, "write failed"))
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    // --- find_twin_primes ---

    #[test]
    fn test_find_twin_primes_limit_below_5() {
        // No twin pairs possible when limit < 5.
        for limit in [0u64, 1, 2, 3, 4] {
            let mut buf: Vec<u8> = Vec::new();
            let count = find_twin_primes(limit, &mut buf).unwrap();
            assert_eq!(count, 0, "limit={}", limit);
            assert!(buf.is_empty(), "limit={}", limit);
        }
    }

    #[test]
    fn test_find_twin_primes_limit_5_no_pair() {
        // (3,5): 5 is not < 5 → 0 pairs.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(5, &mut buf).unwrap();
        assert_eq!(count, 0);
        assert!(buf.is_empty());
    }

    #[test]
    fn test_find_twin_primes_limit_6_one_pair() {
        // (3,5): both < 6 → 1 pair.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(6, &mut buf).unwrap();
        assert_eq!(count, 1);
        assert_eq!(String::from_utf8(buf).unwrap(), "3 | 5\n");
    }

    #[test]
    fn test_find_twin_primes_n1_exact_output() {
        // N=1, limit=10 → pairs: (3,5) and (5,7).
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(10, &mut buf).unwrap();
        assert_eq!(count, 2);
        assert_eq!(
            String::from_utf8(buf).unwrap(),
            "3 | 5\n5 | 7\n"
        );
    }

    #[test]
    fn test_find_twin_primes_n2_exact_output() {
        // N=2, limit=100 → 8 known pairs.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(100, &mut buf).unwrap();
        assert_eq!(count, 8);
        assert_eq!(
            String::from_utf8(buf).unwrap(),
            "3 | 5\n5 | 7\n11 | 13\n17 | 19\n29 | 31\n41 | 43\n59 | 61\n71 | 73\n"
        );
    }

    #[test]
    fn test_find_twin_primes_n3_count() {
        // N=3, limit=1000 → 35 pairs.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(1_000, &mut buf).unwrap();
        assert_eq!(count, 35);
    }

    #[test]
    fn test_find_twin_primes_n4_count() {
        // N=4, limit=10_000 → 205 pairs.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(10_000, &mut buf).unwrap();
        assert_eq!(count, 205);
    }

    #[test]
    fn test_find_twin_primes_output_lines_match_count() {
        // Line count in output must equal the returned count.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_twin_primes(1_000, &mut buf).unwrap();
        let lines = String::from_utf8(buf).unwrap();
        assert_eq!(lines.lines().count() as u64, count);
    }

    #[test]
    fn test_find_twin_primes_write_error_propagates() {
        let result = find_twin_primes(100, &mut FailWriter);
        assert!(result.is_err());
    }

    #[test]
    fn test_find_twin_primes_idempotent() {
        // Running twice produces identical output.
        let mut buf1: Vec<u8> = Vec::new();
        let mut buf2: Vec<u8> = Vec::new();
        find_twin_primes(1_000, &mut buf1).unwrap();
        find_twin_primes(1_000, &mut buf2).unwrap();
        assert_eq!(buf1, buf2);
    }
}
