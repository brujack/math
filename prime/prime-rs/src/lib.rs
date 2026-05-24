use std::io::{self, Write};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use rayon::prelude::*;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Number range covered by one sieve segment.  2^19 = 524 288 numbers.
/// Packed bitset (odd numbers only) = 32 768 bytes = 32 KB — fits in L2 cache.
pub const SEG_SIZE: u64 = 1 << 19;

/// Numbers processed per sequential rayon batch (100 M).
pub const BLOCK_SIZE: u64 = 100_000_000;

// ---------------------------------------------------------------------------
// Phase 1 — simple Eratosthenes sieve
// ---------------------------------------------------------------------------

/// Sieve [2, limit] and return all primes up to `limit`.
pub fn small_sieve(limit: u64) -> Vec<u64> {
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
pub fn sieve_segment(lo: u64, limit: u64, small_primes: &[u64]) -> Vec<u64> {
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

pub fn fmt_int(n: u64) -> String {
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

/// Pure formatter for the phase-2 progress line (allows unit testing of format).
pub fn format_phase2_progress(n: u64, phase2_total: u64, elapsed: f64) -> String {
    let pct = n * 100 / phase2_total.max(1);
    let rate = if elapsed > 0.001 { n as f64 / elapsed / 1e6 } else { 0.0 };
    format!(
        "\r  Phase 2: {:3}%  ({} / {} numbers sieved)  {:.1} M/s   ",
        pct,
        fmt_int(n),
        fmt_int(phase2_total),
        rate,
    )
}

// ---------------------------------------------------------------------------
// Driver
// ---------------------------------------------------------------------------

/// Find all primes up to `limit`, writing one prime per line to `out`.
/// Reports progress to stderr.  Returns the total prime count.
pub fn find_primes<W: Write>(limit: u64, out: &mut W) -> io::Result<u64> {
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
    let phase2_start = sqrt_limit + 1 + (sqrt_limit & 1);
    let phase2_total = limit - phase2_start + 1;

    let processed = Arc::new(AtomicU64::new(0));
    let processed_c = Arc::clone(&processed);
    let done = Arc::new(AtomicBool::new(false));
    let done_c = Arc::clone(&done);
    let t2 = Instant::now();

    let progress_thread = thread::spawn(move || loop {
        thread::sleep(Duration::from_millis(200));
        if done_c.load(Ordering::Relaxed) {
            break;
        }
        let n = processed_c.load(Ordering::Relaxed);
        let elapsed = t2.elapsed().as_secs_f64();
        eprint!("{}", format_phase2_progress(n, phase2_total, elapsed));
        let _ = io::stderr().flush();
    });

    let mut block_lo = phase2_start;
    while block_lo <= limit {
        let block_hi = (block_lo + BLOCK_SIZE - 1).min(limit);

        let seg_starts: Vec<u64> = std::iter::successors(Some(block_lo), |&s| {
            let next = s + SEG_SIZE;
            if next <= block_hi {
                Some(next)
            } else {
                None
            }
        })
        .collect();

        let batch: Vec<Vec<u64>> =
            seg_starts.par_iter().map(|&lo| sieve_segment(lo, block_hi, &small_primes)).collect();

        for seg_primes in batch {
            total += seg_primes.len() as u64;
            for p in seg_primes {
                writeln!(out, "{}", p)?;
            }
        }

        processed.fetch_add(block_hi - block_lo + 1, Ordering::Relaxed);

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
