/*!
Calculate Euler's number e to a user-specified number of decimal places.

Uses the Taylor series with:
  - rayon::join()     — recursive parallel binary splitting across all cores
    (shared-memory threads; zero IPC / serialisation cost)
  - rug::Integer      — GMP big-integer arithmetic for the series accumulation
  - rug::Float        — MPFR arbitrary-precision float for the final value
  - pwrite(2)         — parallel file I/O (os::unix::fs::FileExt::write_at)

Build (requires GMP + MPFR; run install_deps.sh first):
    cargo build --release
    ./target/release/e [digits]

Algorithm:
  e = sum(1/n! for n=0..N) computed via binary splitting.
  Each leaf produces Pq{p, q} and the merge rule is:
    p = l.p * r.p
    q = l.q * r.p + r.q
  Final value: e = Q / P (as Float).
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
    name = "e",
    about = "Calculate Euler's number e to a specified number of decimal places",
    long_about = "Calculate Euler's number e to a specified number of decimal places using the \
                  Taylor series with Rayon parallelism and GMP arithmetic.\n\n\
                  Run without arguments to use interactive prompts."
)]
struct Cli {
    /// Number of decimal places to calculate
    digits: Option<usize>,
}

// ---------------------------------------------------------------------------
// Taylor series constants
// ---------------------------------------------------------------------------

/// Switch from parallel rayon::join to serial recursion below this range size.
const BS_PAR_THRESHOLD: u64 = 512;

/// Counts completed leaf nodes during binary splitting; read by the progress thread.
static BS_LEAF_COUNT: AtomicU64 = AtomicU64::new(0);

// ---------------------------------------------------------------------------
// Binary splitting — the core of the Taylor series for e
// ---------------------------------------------------------------------------

/// (P, Q) accumulators for a range [a, b) of the Taylor series.
///
/// Full series [0, N):  e = Q / P
struct Pq {
    p: Integer,
    q: Integer,
}

/// Recursive binary splitting, parallelised with rayon::join().
fn bs(a: u64, b: u64) -> Pq {
    debug_assert!(b > a);

    if b - a == 1 {
        return bs_leaf(a);
    }

    let m = a + (b - a) / 2;

    if b - a <= BS_PAR_THRESHOLD {
        let l = bs(a, m);
        let r = bs(m, b);
        return bs_merge(l, r);
    }

    let (l, r) = rayon::join(|| bs(a, m), || bs(m, b));
    bs_merge(l, r)
}

fn bs_leaf(a: u64) -> Pq {
    let result = if a == 0 {
        Pq {
            p: Integer::from(1u32),
            q: Integer::from(1u32),
        }
    } else {
        let val = a + 1;
        Pq {
            p: Integer::from(val),
            q: Integer::from(val),
        }
    };

    BS_LEAF_COUNT.fetch_add(1, Ordering::Relaxed);
    result
}

/// Combine two adjacent ranges [a,m) and [m,b):
///   P(a,b) = P(a,m) × P(m,b)
///   Q(a,b) = Q(a,m) × P(m,b) + Q(m,b)
fn bs_merge(l: Pq, r: Pq) -> Pq {
    Pq {
        p: Integer::from(&l.p * &r.p),
        q: Integer::from(&l.q * &r.p) + &r.q,
    }
}

// ---------------------------------------------------------------------------
// e computation
// ---------------------------------------------------------------------------

/// Compute e to `digits` decimal places and return it as a formatted string.
fn compute_e(digits: usize) -> String {
    // Term count: enough terms so that N! > 10^digits.
    // Each term contributes about log10(N) digits on average.
    let n: u64 = if digits > 1 {
        (digits as f64 / (digits as f64 + 1.0).log10()) as u64 + 50
    } else {
        20
    };
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
    let pq = bs(0, n);
    series_done.store(true, Ordering::Relaxed);
    series_thread.join().unwrap();
    eprintln!(
        "\r  Computing series:  100%  ({} terms)   ",
        fmt_int(n as usize)
    );
    eprintln!("  Series done in {:.2}s", t0.elapsed().as_secs_f64());

    // e = Q / P
    let prec_bits = (digits as f64 * 3.321_928_094_887_362_6) as u32 + 100;
    eprintln!("  Computing final value ({} bits)...", prec_bits);

    let t1 = Instant::now();
    let e = Float::with_val(prec_bits, &pq.q) / Float::with_val(prec_bits, &pq.p);
    eprintln!("  Value done in {:.2}s", t1.elapsed().as_secs_f64());

    eprintln!("  Converting to decimal string...");
    let t2 = Instant::now();
    let s = e_to_string(e, digits);
    eprintln!("  Conversion done in {:.2}s", t2.elapsed().as_secs_f64());

    s
}

/// Convert a `rug::Float` e value to a decimal string with exactly `digits`
/// decimal places.
fn e_to_string(e: Float, digits: usize) -> String {
    let raw = e.to_string_radix(10, Some(digits + 5));

    // Strip exponent suffix (e.g. "...e0").
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

/// Write e to a file using parallel pwrite(2) chunks, reporting progress and
/// write speed.
#[cfg(unix)]
fn write_e_file(filename: &str, e_str: &str, digits: usize) -> io::Result<()> {
    let header = format!(
        "e calculated to {} decimal places using Taylor/Rayon\n{}\n\n",
        fmt_int(digits),
        "=".repeat(60),
    );
    let footer = format!("\n\nTotal decimal places: {}", fmt_int(digits));

    let hdr = header.as_bytes();
    let e_bytes = e_str.as_bytes();
    let ftr = footer.as_bytes();

    let total = (hdr.len() + e_bytes.len() + ftr.len()) as u64;
    let e_offset = hdr.len() as u64;
    let e_total = e_bytes.len() as u64;

    let file = File::create(filename)?;
    file.set_len(total)?;

    file.write_at(hdr, 0)?;
    file.write_at(ftr, e_offset + e_total)?;

    let n_threads = rayon::current_num_threads();
    let chunk_size = (4 * 1024 * 1024_usize).max(e_bytes.len() / n_threads);

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
            let pct = (written * 100).checked_div(e_total).unwrap_or(100);
            eprint!(
                "\r  Writing: {:3}%  ({:.1} / {:.1} MB)  {:.1} MB/s   ",
                pct,
                written as f64 / 1_048_576.0,
                e_total as f64 / 1_048_576.0,
                speed,
            );
            let _ = io::stderr().flush();
        }
    });

    e_bytes
        .par_chunks(chunk_size)
        .enumerate()
        .try_for_each(|(i, chunk)| -> io::Result<()> {
            let base = e_offset + (i * chunk_size) as u64;
            let mut written = 0;
            while written < chunk.len() {
                written += file.write_at(&chunk[written..], base + written as u64)?;
            }
            bytes_written.fetch_add(chunk.len() as u64, Ordering::Relaxed);
            Ok(())
        })?;

    write_done.store(true, Ordering::Relaxed);
    progress_thread.join().unwrap();

    let elapsed = t_write.elapsed().as_secs_f64();
    let speed = if elapsed > 0.001 {
        e_total as f64 / elapsed / 1_048_576.0
    } else {
        0.0
    };
    eprintln!(
        "\r  Writing: 100%  ({:.1} MB)  {:.1} MB/s              ",
        e_total as f64 / 1_048_576.0,
        speed,
    );

    Ok(())
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Format an integer with thousands separators (e.g. 1_000_000 -> "1,000,000").
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
        print!("Enter the number of decimal places to calculate e: ");
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

    println!("High-Precision e Calculator (Rust/Rayon)");
    println!("{}", "=".repeat(40));

    let digits = match cli.digits {
        Some(d) => {
            if d < 1 {
                eprintln!("Error: digits must be >= 1");
                std::process::exit(1);
            }
            if d > 1_000_000 {
                eprintln!("Warning: very large numbers may take a long time.");
            }
            d
        }
        None => prompt_digits(),
    };

    println!("Calculating e to {} decimal places...", fmt_int(digits));
    println!(
        "Backend: Taylor / rug+GMP+MPFR / rayon ({} threads)",
        rayon::current_num_threads()
    );

    let t_total = Instant::now();
    let e_str = compute_e(digits);
    println!("\nDone in {:.2}s", t_total.elapsed().as_secs_f64());

    // Preview: first 100 decimal places (or fewer for small requests).
    if digits <= 1_000_000 {
        let preview = 100.min(digits);
        if let Some(dot) = e_str.find('.') {
            let end = (dot + 1 + preview).min(e_str.len());
            println!("\ne = {}...", &e_str[..end]);
            println!("(Showing first {} decimal places)", preview);
        }
    }

    if digits > 10_000 {
        let filename = format!("e_{}_digits.txt", digits);
        println!("\nSaving to {}...", filename);
        #[cfg(unix)]
        write_e_file(&filename, &e_str, digits).expect("file write failed");
        println!("Full precision e saved to {}", filename);
    } else {
        print!("\nDisplay all {} digits? (y/n): ", fmt_int(digits));
        io::stdout().flush().unwrap();
        if matches!(read_line().as_str(), "y" | "yes") {
            println!("\ne = {}", e_str);
            println!("\nTotal digits: {}", fmt_int(digits));
        } else {
            let filename = format!("e_{}_digits.txt", digits);
            #[cfg(unix)]
            write_e_file(&filename, &e_str, digits).expect("file write failed");
            println!("\nFull precision e saved to {}", filename);
        }
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// First 50 decimal places of e — used as a reference for accuracy tests.
    const E_REF: &str = "2.71828182845904523536028747135266249775724709369995";

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
        let pq = bs_leaf(0);
        assert_eq!(pq.p, Integer::from(1u32));
        assert_eq!(pq.q, Integer::from(1u32));
    }

    #[test]
    fn test_bs_leaf_one() {
        // a=1: p = a+1 = 2, q = a+1 = 2
        let pq = bs_leaf(1);
        assert_eq!(pq.p, Integer::from(2u32));
        assert_eq!(pq.q, Integer::from(2u32));
    }

    #[test]
    fn test_bs_leaf_two() {
        // a=2: p = a+1 = 3, q = a+1 = 3
        let pq = bs_leaf(2);
        assert_eq!(pq.p, Integer::from(3u32));
        assert_eq!(pq.q, Integer::from(3u32));
    }

    #[test]
    fn test_bs_leaf_increments_counter() {
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
    }

    // --- bs (split consistency) ---

    #[test]
    fn test_bs_split_consistency_4() {
        let full = bs(0, 4);
        let merged = bs_merge(bs(0, 2), bs(2, 4));
        assert_eq!(full.p, merged.p);
        assert_eq!(full.q, merged.q);
    }

    #[test]
    fn test_bs_split_consistency_8() {
        let full = bs(0, 8);
        let merged = bs_merge(bs(0, 4), bs(4, 8));
        assert_eq!(full.p, merged.p);
        assert_eq!(full.q, merged.q);
    }

    // --- e_to_string ---

    #[test]
    fn test_e_to_string_starts_with_2_dot() {
        let e = Float::with_val(200, 1u32).exp();
        let s = e_to_string(e, 10);
        assert!(s.starts_with("2."));
    }

    #[test]
    fn test_e_to_string_exact_decimal_count() {
        let e = Float::with_val(200, 1u32).exp();
        let s = e_to_string(e, 20);
        // "2." + 20 decimal digits = 22 chars
        assert_eq!(s.len(), 22);
    }

    #[test]
    fn test_e_to_string_no_exponent_notation() {
        let e = Float::with_val(200, 1u32).exp();
        let s = e_to_string(e, 15);
        assert!(!s.contains('e') && !s.contains('E'));
    }

    #[test]
    fn test_e_to_string_known_digits() {
        let e = Float::with_val(200, 1u32).exp();
        let s = e_to_string(e, 15);
        assert_eq!(&s[..17], &E_REF[..17]);
    }

    #[test]
    fn test_e_to_string_single_decimal_place() {
        let e = Float::with_val(200, 1u32).exp();
        let s = e_to_string(e, 1);
        assert_eq!(s.len(), 3);
        assert_eq!(s, "2.7");
    }

    // --- compute_e (end-to-end accuracy) ---

    #[test]
    fn test_compute_e_10_digits() {
        let s = compute_e(10);
        assert_eq!(&s[..12], &E_REF[..12]);
    }

    #[test]
    fn test_compute_e_50_digits() {
        let s = compute_e(50);
        assert_eq!(s, E_REF);
    }
}
