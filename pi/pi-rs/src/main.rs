/*!
Calculate π to a user-specified number of decimal places.

Uses the Chudnovsky algorithm with:
  - rayon::join()     — recursive parallel binary splitting across all cores
    (shared-memory threads; zero IPC / serialisation cost)
  - rug::Integer      — GMP big-integer arithmetic for the series accumulation
  - rug::Float        — MPFR arbitrary-precision float for the final value
  - pwrite(2)         — parallel file I/O (os::unix::fs::FileExt::write_at)

Build (requires GMP + MPFR; run install_deps.sh first):
    cargo build --release
    ./target/release/pi [digits]

Key difference from the Python version:
  Python spawns one *process* per CPU, serialising each chunk's (P,Q,T)
  integers through OS pipes.  For 50 M+ digits those integers are tens of
  megabytes each, and serialisation cost dominates.

  Rust uses *threads*: rayon::join() recurses into both halves of the binary
  tree simultaneously using a work-stealing pool.  Integers are in shared
  memory — no copies, no pipes.  This gives near-linear scaling to all cores
  for the series computation and removes the per-chunk startup overhead.
*/

use std::fs::File;
use std::io::{self, BufRead, Write};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

#[cfg(unix)]
use std::os::unix::fs::FileExt;

use clap::Parser;
use rayon::prelude::*;
use rug::{Float, Integer};

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

#[derive(Parser)]
#[command(
    name = "pi",
    about = "Calculate π to a specified number of decimal places",
    long_about = "Calculate π to a specified number of decimal places using the \
                  Chudnovsky algorithm with Rayon parallelism and GMP arithmetic.\n\n\
                  Run without arguments to use interactive prompts."
)]
struct Cli {
    /// Number of decimal places to calculate
    digits: Option<usize>,
}

// ---------------------------------------------------------------------------
// Chudnovsky series constants
// ---------------------------------------------------------------------------

const CHU_A: u64 = 13_591_409;
const CHU_B: u64 = 545_140_134;
/// 640320³ / 24  =  10_939_058_860_032_000  (fits in u64)
const CHU_C3_24: u64 = 10_939_058_860_032_000;

/// Switch from parallel rayon::join to serial recursion below this range size.
/// Each serial leaf does ~512 terms; overhead of spawning smaller tasks exceeds
/// the computation.  Rayon's work-stealing handles load-balancing automatically.
const BS_PAR_THRESHOLD: u64 = 512;

/// Counts completed leaf nodes during binary splitting; read by the progress thread.
static BS_LEAF_COUNT: AtomicU64 = AtomicU64::new(0);

// ---------------------------------------------------------------------------
// Binary splitting — the core of the Chudnovsky algorithm
// ---------------------------------------------------------------------------

/// (P, Q, T) accumulators for a range [a, b) of the Chudnovsky series.
///
/// Full series [0, N):  π = 426_880 × √10_005 × Q / T
struct Pqt {
    p: Integer,
    q: Integer,
    t: Integer,
}

/// Recursive binary splitting, parallelised with rayon::join().
///
/// Both halves of the tree are completely independent, so rayon can schedule
/// them onto separate threads with its work-stealing pool.  The threshold
/// switches to serial recursion once sub-problems are too small to justify
/// spawning more tasks.
fn bs(a: u64, b: u64) -> Pqt {
    debug_assert!(b > a);

    if b - a == 1 {
        return bs_leaf(a);
    }

    let m = a + (b - a) / 2;

    if b - a <= BS_PAR_THRESHOLD {
        // Serial path for small sub-problems.
        let l = bs(a, m);
        let r = bs(m, b);
        return bs_merge(l, r);
    }

    // Parallel path: both halves run concurrently on the thread pool.
    // Integer is Send; closures capture only u64 (Copy) → Send. ✓
    let (l, r) = rayon::join(|| bs(a, m), || bs(m, b));
    bs_merge(l, r)
}

fn bs_leaf(a: u64) -> Pqt {
    let result = if a == 0 {
        Pqt {
            p: Integer::from(1u32),
            q: Integer::from(1u32),
            t: Integer::from(CHU_A),
        }
    } else {
        // P = (6a−5)(2a−1)(6a−1)
        // These factors fit in u64 for all practical a values (a ≤ ~7 M for 100 M digits).
        let p = Integer::from(6 * a - 5)
            * Integer::from(2 * a - 1)
            * Integer::from(6 * a - 1);

        // Q = a³ × C³/24
        // a³ overflows u64 for a > ~2.6 M, so use Integer arithmetic.
        let ai = Integer::from(a);
        let q = Integer::from(&ai * &ai) * &ai * CHU_C3_24;

        // T = (−1)^a × P × (A + B×a)
        let t_abs =
            Integer::from(&p) * (Integer::from(CHU_A) + Integer::from(CHU_B) * &ai);
        let t = if a & 1 == 1 { -t_abs } else { t_abs };

        Pqt { p, q, t }
    };

    BS_LEAF_COUNT.fetch_add(1, Ordering::Relaxed);
    result
}

/// Combine two adjacent ranges [a,m) and [m,b):
///   P(a,b) = P(a,m) × P(m,b)
///   Q(a,b) = Q(a,m) × Q(m,b)
///   T(a,b) = Q(m,b) × T(a,m) + P(a,m) × T(m,b)
fn bs_merge(l: Pqt, r: Pqt) -> Pqt {
    Pqt {
        p: Integer::from(&l.p * &r.p),
        q: Integer::from(&l.q * &r.q),
        t: Integer::from(&r.q * &l.t) + Integer::from(&l.p * &r.t),
    }
}

// ---------------------------------------------------------------------------
// π computation
// ---------------------------------------------------------------------------

/// Compute π to `digits` decimal places and return it as a formatted string.
fn compute_pi(digits: usize) -> String {
    // Each Chudnovsky term contributes ≈14.1816 decimal digits.
    let n = (digits / 14 + 10) as u64;
    let threads = rayon::current_num_threads();

    eprintln!(
        "  Series: {} terms, {} threads, threshold {}",
        fmt_int(n as usize),
        threads,
        BS_PAR_THRESHOLD
    );

    // Reset leaf counter and spawn a progress-reporting thread.
    BS_LEAF_COUNT.store(0, Ordering::Relaxed);
    let series_done = Arc::new(AtomicBool::new(false));
    let series_done_c = Arc::clone(&series_done);
    let series_thread = thread::spawn(move || {
        loop {
            thread::sleep(Duration::from_millis(200));
            if series_done_c.load(Ordering::Relaxed) {
                break;
            }
            let completed = BS_LEAF_COUNT.load(Ordering::Relaxed);
            let pct = completed * 100 / n;
            eprint!(
                "\r  Computing series:  {:3}%  ({} / {} terms)   ",
                pct,
                fmt_int(completed as usize),
                fmt_int(n as usize),
            );
            let _ = io::stderr().flush();
        }
    });

    let t0 = Instant::now();
    let pqt = bs(0, n);
    series_done.store(true, Ordering::Relaxed);
    series_thread.join().unwrap();
    eprintln!(
        "\r  Computing series:  100%  ({} terms)   ",
        fmt_int(n as usize)
    );
    eprintln!("  Series done in {:.2}s", t0.elapsed().as_secs_f64());

    // π = 426_880 × √10_005 × Q / T
    let prec_bits = (digits as f64 * 3.321_928_094_887_362_6) as u32 + 100;
    eprintln!("  Computing final value ({} bits)…", prec_bits);

    let t1 = Instant::now();
    let sqrt10005 = Float::with_val(prec_bits, 10005).sqrt();
    let pi = Float::with_val(prec_bits, 426_880_u32)
        * sqrt10005
        * Float::with_val(prec_bits, &pqt.q)
        / Float::with_val(prec_bits, &pqt.t);
    eprintln!("  Value done in {:.2}s", t1.elapsed().as_secs_f64());

    eprintln!("  Converting to decimal string…");
    let t2 = Instant::now();
    let s = pi_to_string(pi, digits);
    eprintln!("  Conversion done in {:.2}s", t2.elapsed().as_secs_f64());

    s
}

/// Convert a `rug::Float` π value to a decimal string with exactly `digits`
/// decimal places.
///
/// `Float::to_string_radix(10, Some(n))` calls MPFR's mpfr_get_str and
/// returns n significant decimal digits in the form "3.14159…" for values
/// in [1, 10).  We trim to the requested decimal-place count.
fn pi_to_string(pi: Float, digits: usize) -> String {
    // Request digits+5 significant figures for rounding safety.
    let raw = pi.to_string_radix(10, Some(digits + 5));

    // Strip exponent suffix (e.g. "…e0") — only present for very large/small values,
    // but guard defensively.
    let raw: &str = match raw.find(['e', 'E']) {
        Some(pos) => &raw[..pos],
        None => &raw,
    };

    // Trim or pad to exactly `digits` decimal places after the '.'.
    if let Some(dot) = raw.find('.') {
        let want = dot + 1 + digits;
        if raw.len() >= want {
            raw[..want].to_string()
        } else {
            format!("{}{}", raw, "0".repeat(want - raw.len()))
        }
    } else {
        format!("{}.{}", raw, "0".repeat(digits))
    }
}

// ---------------------------------------------------------------------------
// File output
// ---------------------------------------------------------------------------

/// Write π to a file using parallel pwrite(2) chunks, reporting progress and
/// write speed.
///
/// The file is pre-allocated to its final size, then the header and footer are
/// written sequentially (they are small) and the π digit string is written
/// concurrently by rayon-dispatched pwrite calls — the same strategy as the
/// Python version, but using shared-memory threads instead of processes.
#[cfg(unix)]
fn write_pi_file(filename: &str, pi_str: &str, digits: usize) -> io::Result<()> {
    let header = format!(
        "π calculated to {} decimal places using Chudnovsky/Rayon\n{}\n\n",
        fmt_int(digits),
        "=".repeat(60),
    );
    let footer = format!("\n\nTotal decimal places: {}", fmt_int(digits));

    let hdr = header.as_bytes();
    let pi  = pi_str.as_bytes();   // ASCII digits — 1 byte per char
    let ftr = footer.as_bytes();

    let total     = (hdr.len() + pi.len() + ftr.len()) as u64;
    let pi_offset = hdr.len() as u64;
    let pi_total  = pi.len() as u64;

    // Pre-allocate file; pwrite does not extend a file past its current size.
    let file = File::create(filename)?;
    file.set_len(total)?;

    // Header and footer are small — write sequentially.
    file.write_at(hdr, 0)?;
    file.write_at(ftr, pi_offset + pi_total)?;

    // Set up progress tracking for the parallel write.
    let n_threads  = rayon::current_num_threads();
    let chunk_size = ((4 * 1024 * 1024) as usize).max(pi.len() / n_threads);

    let bytes_written = Arc::new(AtomicU64::new(0));
    let bytes_written_c = Arc::clone(&bytes_written);
    let write_done = Arc::new(AtomicBool::new(false));
    let write_done_c = Arc::clone(&write_done);
    let t_write = Instant::now();

    let progress_thread = thread::spawn(move || {
        loop {
            thread::sleep(Duration::from_millis(200));
            if write_done_c.load(Ordering::Relaxed) {
                break;
            }
            let written = bytes_written_c.load(Ordering::Relaxed);
            let elapsed = t_write.elapsed().as_secs_f64();
            let speed = if elapsed > 0.001 {
                written as f64 / elapsed / 1_048_576.0
            } else {
                0.0
            };
            let pct = if pi_total > 0 { written * 100 / pi_total } else { 100 };
            eprint!(
                "\r  Writing: {:3}%  ({:.1} / {:.1} MB)  {:.1} MB/s   ",
                pct,
                written as f64 / 1_048_576.0,
                pi_total as f64 / 1_048_576.0,
                speed,
            );
            let _ = io::stderr().flush();
        }
    });

    // π digit bytes: parallel pwrite chunks.
    // File: Sync on Unix (wraps OwnedFd which is Send + Sync). pwrite is
    // thread-safe — it does not move the file pointer. ✓
    pi.par_chunks(chunk_size)
        .enumerate()
        .try_for_each(|(i, chunk)| -> io::Result<()> {
            let base = pi_offset + (i * chunk_size) as u64;
            let mut written = 0;
            while written < chunk.len() {
                written +=
                    file.write_at(&chunk[written..], base + written as u64)?;
            }
            bytes_written.fetch_add(chunk.len() as u64, Ordering::Relaxed);
            Ok(())
        })?;

    write_done.store(true, Ordering::Relaxed);
    progress_thread.join().unwrap();

    let elapsed = t_write.elapsed().as_secs_f64();
    let speed = if elapsed > 0.001 {
        pi_total as f64 / elapsed / 1_048_576.0
    } else {
        0.0
    };
    eprintln!(
        "\r  Writing: 100%  ({:.1} MB)  {:.1} MB/s              ",
        pi_total as f64 / 1_048_576.0,
        speed,
    );

    Ok(())
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Format an integer with thousands separators (e.g. 1_000_000 → "1,000,000").
fn fmt_int(n: usize) -> String {
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

fn prompt_digits() -> usize {
    loop {
        print!("Enter the number of decimal places to calculate π: ");
        io::stdout().flush().unwrap();
        match read_line().parse::<usize>() {
            Ok(n) if n >= 1 => {
                if n > 1_000_000 {
                    eprintln!("Warning: very large numbers may take a long time.");
                    print!("Continue with {} digits? (y/n): ", fmt_int(n));
                    io::stdout().flush().unwrap();
                    if !matches!(read_line().as_str(), "y" | "yes") {
                        continue;
                    }
                }
                return n;
            }
            _ => eprintln!("Please enter a positive integer."),
        }
    }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

fn main() {
    let cli = Cli::parse();

    println!("High-Precision π Calculator (Rust/Rayon)");
    println!("{}", "=".repeat(40));

    let digits = match cli.digits {
        Some(d) => {
            if d < 1 {
                eprintln!("Error: digits must be ≥ 1");
                std::process::exit(1);
            }
            if d > 1_000_000 {
                eprintln!("Warning: very large numbers may take a long time.");
            }
            d
        }
        None => prompt_digits(),
    };

    println!(
        "Calculating π to {} decimal places…",
        fmt_int(digits)
    );
    println!(
        "Backend: Chudnovsky / rug+GMP+MPFR / rayon ({} threads)",
        rayon::current_num_threads()
    );

    let t_total = Instant::now();
    let pi_str = compute_pi(digits);
    println!("\nDone in {:.2}s", t_total.elapsed().as_secs_f64());

    // Preview: first 100 decimal places (or fewer for small requests).
    if digits <= 1_000_000 {
        let preview = 100.min(digits);
        if let Some(dot) = pi_str.find('.') {
            let end = (dot + 1 + preview).min(pi_str.len());
            println!("\nπ = {}…", &pi_str[..end]);
            println!("(Showing first {} decimal places)", preview);
        }
    }

    if digits > 10_000 {
        let filename = format!("pi_{}_digits.txt", digits);
        println!("\nSaving to {}…", filename);
        #[cfg(unix)]
        write_pi_file(&filename, &pi_str, digits).expect("file write failed");
        println!("Full precision π saved to {}", filename);
    } else {
        print!("\nDisplay all {} digits? (y/n): ", fmt_int(digits));
        io::stdout().flush().unwrap();
        if matches!(read_line().as_str(), "y" | "yes") {
            println!("\nπ = {}", pi_str);
            println!("\nTotal digits: {}", fmt_int(digits));
        } else {
            let filename = format!("pi_{}_digits.txt", digits);
            #[cfg(unix)]
            write_pi_file(&filename, &pi_str, digits).expect("file write failed");
            println!("\nFull precision π saved to {}", filename);
        }
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// First 50 decimal places of π — used as a reference for accuracy tests.
    const PI_REF: &str = "3.14159265358979323846264338327950288419716939937510";

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
    fn test_fmt_int_billions() {
        assert_eq!(fmt_int(1_000_000_000), "1,000,000,000");
    }

    // --- bs_leaf ---

    #[test]
    fn test_bs_leaf_zero() {
        // Base case: P=1, Q=1, T=CHU_A
        let pqt = bs_leaf(0);
        assert_eq!(pqt.p, Integer::from(1u32));
        assert_eq!(pqt.q, Integer::from(1u32));
        assert_eq!(pqt.t, Integer::from(CHU_A));
    }

    #[test]
    fn test_bs_leaf_one_formulas() {
        // a=1: P=(6−5)(2−1)(6−1)=1·1·5=5; Q=1³×C³/24=CHU_C3_24;
        //       T=−P×(A+B·1)=−5×558_731_543 (odd index → negative)
        let pqt = bs_leaf(1);
        assert_eq!(pqt.p, Integer::from(5u32));
        assert_eq!(pqt.q, Integer::from(CHU_C3_24));
        assert!(pqt.t < 0, "T should be negative for odd index");
        let expected_abs =
            Integer::from(5u32) * (Integer::from(CHU_A) + Integer::from(CHU_B));
        assert_eq!(-pqt.t, expected_abs);
    }

    #[test]
    fn test_bs_leaf_even_index_positive_t() {
        // Even index → T is positive.
        let pqt = bs_leaf(2);
        assert!(pqt.t > 0, "T should be positive for even index > 0");
    }

    #[test]
    fn test_bs_leaf_increments_counter() {
        // Tests run in parallel, so check the delta rather than the absolute value.
        let before = BS_LEAF_COUNT.load(Ordering::Relaxed);
        bs_leaf(0);
        bs_leaf(1);
        let after = BS_LEAF_COUNT.load(Ordering::Relaxed);
        assert!(after >= before + 2, "expected counter to increase by at least 2");
    }

    // --- bs_merge ---

    #[test]
    fn test_bs_merge_matches_two_leaves() {
        // bs(0,2) must equal merge(bs_leaf(0), bs_leaf(1))
        let merged = bs_merge(bs_leaf(0), bs_leaf(1));
        let full = bs(0, 2);
        assert_eq!(merged.p, full.p);
        assert_eq!(merged.q, full.q);
        assert_eq!(merged.t, full.t);
    }

    // --- bs (split consistency) ---

    #[test]
    fn test_bs_split_consistency_4() {
        // bs(0,4) == merge(bs(0,2), bs(2,4))
        let full = bs(0, 4);
        let merged = bs_merge(bs(0, 2), bs(2, 4));
        assert_eq!(full.p, merged.p);
        assert_eq!(full.q, merged.q);
        assert_eq!(full.t, merged.t);
    }

    #[test]
    fn test_bs_split_consistency_8() {
        // bs(0,8) == merge(bs(0,4), bs(4,8))
        let full = bs(0, 8);
        let merged = bs_merge(bs(0, 4), bs(4, 8));
        assert_eq!(full.p, merged.p);
        assert_eq!(full.q, merged.q);
        assert_eq!(full.t, merged.t);
    }

    // --- pi_to_string ---

    #[test]
    fn test_pi_to_string_starts_with_3_dot() {
        let pi = Float::with_val(200, rug::float::Constant::Pi);
        let s = pi_to_string(pi, 10);
        assert!(s.starts_with("3."));
    }

    #[test]
    fn test_pi_to_string_exact_decimal_count() {
        let pi = Float::with_val(200, rug::float::Constant::Pi);
        let s = pi_to_string(pi, 20);
        // "3." + 20 decimal digits = 22 chars
        assert_eq!(s.len(), 22);
    }

    #[test]
    fn test_pi_to_string_no_exponent_notation() {
        let pi = Float::with_val(200, rug::float::Constant::Pi);
        let s = pi_to_string(pi, 15);
        assert!(!s.contains('e') && !s.contains('E'));
    }

    #[test]
    fn test_pi_to_string_known_digits() {
        // 200-bit MPFR pi is accurate to ~60 decimal places.
        let pi = Float::with_val(200, rug::float::Constant::Pi);
        let s = pi_to_string(pi, 15);
        assert_eq!(&s[..17], &PI_REF[..17]);
    }

    // --- compute_pi (end-to-end accuracy) ---

    #[test]
    fn test_compute_pi_10_digits() {
        let s = compute_pi(10);
        assert_eq!(&s[..12], &PI_REF[..12]);
    }

    #[test]
    fn test_compute_pi_50_digits() {
        let s = compute_pi(50);
        assert_eq!(s, PI_REF);
    }
}
