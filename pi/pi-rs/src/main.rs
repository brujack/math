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
use std::time::Instant;

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
    if a == 0 {
        return Pqt {
            p: Integer::from(1u32),
            q: Integer::from(1u32),
            t: Integer::from(CHU_A),
        };
    }

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

    let t0 = Instant::now();
    let pqt = bs(0, n);
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

/// Write π to a file using parallel pwrite(2) chunks.
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

    // Pre-allocate file; pwrite does not extend a file past its current size.
    let file = File::create(filename)?;
    file.set_len(total)?;

    // Header and footer are small — write sequentially.
    file.write_at(hdr, 0)?;
    file.write_at(ftr, pi_offset + pi.len() as u64)?;

    // π digit bytes: parallel pwrite chunks.
    // File: Sync on Unix (wraps OwnedFd which is Send + Sync). pwrite is
    // thread-safe — it does not move the file pointer. ✓
    let n_threads  = rayon::current_num_threads();
    let chunk_size = ((4 * 1024 * 1024) as usize).max(pi.len() / n_threads);

    pi.par_chunks(chunk_size)
        .enumerate()
        .try_for_each(|(i, chunk)| -> io::Result<()> {
            let base = pi_offset + (i * chunk_size) as u64;
            let mut written = 0;
            while written < chunk.len() {
                written +=
                    file.write_at(&chunk[written..], base + written as u64)?;
            }
            Ok(())
        })?;

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
        let t_write = Instant::now();
        #[cfg(unix)]
        write_pi_file(&filename, &pi_str, digits).expect("file write failed");
        println!("Written in {:.2}s", t_write.elapsed().as_secs_f64());
        println!("\nFull precision π saved to {}", filename);
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
