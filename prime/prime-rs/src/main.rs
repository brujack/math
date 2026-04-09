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
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use clap::Parser;
use rayon::prelude::*;

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
// Constants
// ---------------------------------------------------------------------------

/// Number range covered by one sieve segment.  2^19 = 524 288 numbers.
/// Packed bitset (odd numbers only) = 32 768 bytes = 32 KB — fits in L2 cache.
const SEG_SIZE: u64 = 1 << 19;

/// Numbers processed per sequential rayon batch (100 M).
/// At most ~6 M primes per block → Vec overhead ≤ ~50 MB while writing.
const BLOCK_SIZE: u64 = 100_000_000;

// ---------------------------------------------------------------------------
// Phase 1 — simple Eratosthenes sieve
// ---------------------------------------------------------------------------

/// Sieve [2, limit] and return all primes up to `limit`.
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

// ---------------------------------------------------------------------------
// Phase 2 — one segment of the segmented sieve
// ---------------------------------------------------------------------------

/// Sieve odd numbers in [lo, lo + SEG_SIZE) ∩ [lo, limit] using `small_primes`.
///
/// Representation: packed bitset, one bit per odd number.
///   bit index i  ↔  number lo + 2*i
///   1 = composite, 0 = prime candidate
///
/// `lo` must be odd.  `lo > max(small_primes)` is required so that every
/// composite in the segment has a factor in `small_primes`.
fn sieve_segment(lo: u64, limit: u64, small_primes: &[u64]) -> Vec<u64> {
    let hi = (lo + SEG_SIZE).min(limit + 1); // exclusive
    if lo >= hi {
        return vec![];
    }

    // Number of odd integers in [lo, hi): lo, lo+2, …
    let n = (hi - lo + 1).div_ceil(2) as usize;
    let n_bytes = n.div_ceil(8);
    let mut composite = vec![0u8; n_bytes]; // 0 = prime candidate

    for &p in small_primes {
        if p == 2 {
            continue;
        }
        // First odd multiple of p that is >= lo.
        let rem = lo % p;
        let mut s = if rem == 0 { lo } else { lo + (p - rem) };
        if s % 2 == 0 {
            s += p; // p is odd → s+p is odd
        }
        if s >= hi {
            continue;
        }

        // Bit index of s in our packed array.
        // Consecutive odd multiples of p are 2p apart → bit-index step = p.
        let mut idx = ((s - lo) / 2) as usize;
        let step = p as usize;
        while idx < n {
            composite[idx >> 3] |= 1u8 << (idx & 7);
            idx += step;
        }
    }

    // Collect primes: odd numbers whose bit is still 0.
    (0..n)
        .filter(|&i| composite[i >> 3] & (1u8 << (i & 7)) == 0)
        .map(|i| lo + (i as u64) * 2)
        .collect()
}

// ---------------------------------------------------------------------------
// Driver
// ---------------------------------------------------------------------------

/// Find all primes up to `limit`, writing one prime per line to `out`.
/// Reports progress to stderr.  Returns the total prime count.
fn find_primes<W: Write>(limit: u64, out: &mut W) -> io::Result<u64> {
    if limit < 2 {
        return Ok(0);
    }

    let sqrt_limit = (limit as f64).sqrt() as u64 + 1;

    // ---- Phase 1 ----
    eprint!("  Phase 1: sieve [2, {}] … ", fmt_int(sqrt_limit));
    let _ = io::stderr().flush();
    let t1 = Instant::now();
    let small_primes = small_sieve(sqrt_limit);
    eprintln!(
        "{} primes  ({:.3}s)",
        fmt_int(small_primes.len() as u64),
        t1.elapsed().as_secs_f64()
    );

    let mut total = small_primes.len() as u64;
    for &p in &small_primes {
        writeln!(out, "{}", p)?;
    }

    if limit <= sqrt_limit {
        return Ok(total);
    }

    // ---- Phase 2 ----
    // First odd number strictly above sqrt_limit.
    let phase2_start = sqrt_limit + 1 + (sqrt_limit & 1); // round up to odd
    let phase2_total = limit - phase2_start + 1;

    let processed = Arc::new(AtomicU64::new(0));
    let processed_c = Arc::clone(&processed);
    let done = Arc::new(AtomicBool::new(false));
    let done_c = Arc::clone(&done);
    let t2 = Instant::now();

    let progress_thread = thread::spawn(move || {
        loop {
            thread::sleep(Duration::from_millis(200));
            if done_c.load(Ordering::Relaxed) {
                break;
            }
            let n = processed_c.load(Ordering::Relaxed);
            let elapsed = t2.elapsed().as_secs_f64();
            let pct = n * 100 / phase2_total.max(1);
            let rate = if elapsed > 0.001 { n as f64 / elapsed / 1e6 } else { 0.0 };
            eprint!(
                "\r  Phase 2: {:3}%  ({} / {} numbers sieved)  {:.1} M/s   ",
                pct,
                fmt_int(n),
                fmt_int(phase2_total),
                rate,
            );
            let _ = io::stderr().flush();
        }
    });

    let mut block_lo = phase2_start;
    while block_lo <= limit {
        let block_hi = (block_lo + BLOCK_SIZE - 1).min(limit);

        // Collect segment starts (all odd) within this block.
        let seg_starts: Vec<u64> =
            std::iter::successors(Some(block_lo), |&s| {
                let next = s + SEG_SIZE;
                if next <= block_hi { Some(next) } else { None }
            })
            .collect();

        // Sieve all segments in this block in parallel.
        let batch: Vec<Vec<u64>> = seg_starts
            .par_iter()
            .map(|&lo| sieve_segment(lo, block_hi, &small_primes))
            .collect();

        // Stream this block's primes to output.
        for seg_primes in batch {
            total += seg_primes.len() as u64;
            for p in seg_primes {
                writeln!(out, "{}", p)?;
            }
        }

        processed.fetch_add(block_hi - block_lo + 1, Ordering::Relaxed);

        // Advance to the next odd number after block_hi.
        block_lo = block_hi + 1;
        if block_lo.is_multiple_of(2) {
            block_lo += 1;
        }
    }

    done.store(true, Ordering::Relaxed);
    progress_thread.join().unwrap();

    let elapsed2 = t2.elapsed().as_secs_f64();
    let rate2 = if elapsed2 > 0.001 { phase2_total as f64 / elapsed2 / 1e6 } else { 0.0 };
    eprintln!(
        "\r  Phase 2: 100%  ({} numbers sieved)  {:.1} M/s              ",
        fmt_int(phase2_total),
        rate2,
    );

    Ok(total)
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

fn read_line() -> String {
    let stdin = io::stdin();
    let mut line = String::new();
    stdin.lock().read_line(&mut line).unwrap();
    line.trim().to_string()
}

fn prompt_digits() -> u32 {
    loop {
        print!("Enter N (finds all primes up to 10^N, max 18): ");
        io::stdout().flush().unwrap();
        match read_line().parse::<u32>() {
            Ok(n) if (1..=18).contains(&n) => return n,
            Ok(_) => eprintln!("N must be between 1 and 18."),
            _ => eprintln!("Please enter a positive integer."),
        }
    }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

fn main() {
    let cli = Cli::parse();

    println!("Prime Number Sieve (Rust/Rayon)");
    println!("{}", "=".repeat(40));

    let digits = match cli.digits {
        Some(d) => {
            if !(1..=18).contains(&d) {
                eprintln!("Error: N must be between 1 and 18.");
                std::process::exit(1);
            }
            d
        }
        None => prompt_digits(),
    };

    let limit: u64 = 10u64.pow(digits);

    if digits >= 11 {
        eprintln!(
            "Warning: N={} means sieving up to {} — this may take a long time",
            digits,
            fmt_int(limit)
        );
        eprintln!("         and produce a very large output file.");
        print!("Continue? (y/n): ");
        io::stdout().flush().unwrap();
        if !matches!(read_line().as_str(), "y" | "yes") {
            return;
        }
    }

    println!(
        "Finding all primes up to 10^{} = {}",
        digits,
        fmt_int(limit)
    );
    println!(
        "Backend: segmented sieve / packed bitset / rayon ({} threads)",
        rayon::current_num_threads()
    );

    let t_total = Instant::now();

    if digits <= 6 {
        // Small result: buffer in memory, let user choose to display or save.
        let mut buf: Vec<u8> = Vec::new();
        let count = find_primes(limit, &mut buf).expect("sieve error");

        println!("\nFound {} primes up to 10^{}", fmt_int(count), digits);
        print!("Display all {} primes? (y/n): ", fmt_int(count));
        io::stdout().flush().unwrap();
        if matches!(read_line().as_str(), "y" | "yes") {
            io::stdout().write_all(&buf).unwrap();
        } else {
            let filename = format!("primes_1e{}.txt", digits);
            std::fs::write(&filename, &buf).expect("file write failed");
            println!("Saved to {}", filename);
        }
    } else {
        // Large result: stream directly to file.
        let filename = format!("primes_1e{}.txt", digits);
        println!("\nSaving to {}…", filename);
        let file = File::create(&filename).expect("cannot create output file");
        let mut writer = BufWriter::with_capacity(8 * 1024 * 1024, file);
        let count = find_primes(limit, &mut writer).expect("sieve/write error");
        writer.flush().expect("flush error");

        println!("Found {} primes up to 10^{}", fmt_int(count), digits);
        println!("Saved to {}", filename);
    }

    println!("Total time: {:.2}s", t_total.elapsed().as_secs_f64());
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

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
            101u64, 103, 107, 109, 113, 127, 131, 137, 139, 149,
            151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199,
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

    // --- find_primes (end-to-end) ---

    #[test]
    fn test_find_primes_below_2() {
        let mut buf: Vec<u8> = Vec::new();
        let count = find_primes(1, &mut buf).unwrap();
        assert_eq!(count, 0);
        assert!(buf.is_empty());
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
}
