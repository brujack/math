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
use std::path::{Path, PathBuf};
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
        Pqt { p: Integer::from(1u32), q: Integer::from(1u32), t: Integer::from(CHU_A) }
    } else {
        // P = (6a−5)(2a−1)(6a−1)
        // These factors fit in u64 for all practical a values (a ≤ ~7 M for 100 M digits).
        let p = Integer::from(6 * a - 5) * Integer::from(2 * a - 1) * Integer::from(6 * a - 1);

        // Q = a³ × C³/24
        // a³ overflows u64 for a > ~2.6 M, so use Integer arithmetic.
        let ai = Integer::from(a);
        let q = Integer::from(&ai * &ai) * &ai * CHU_C3_24;

        // T = (−1)^a × P × (A + B×a)
        let t_abs = Integer::from(&p) * (Integer::from(CHU_A) + Integer::from(CHU_B) * &ai);
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

/// Format the series-progress status line shown by the compute_pi progress thread.
fn format_series_progress(completed: u64, n: u64) -> String {
    let pct = (completed * 100).checked_div(n).unwrap_or(100);
    format!(
        "  Computing series:  {:3}%  ({} / {} terms)   ",
        pct,
        fmt_int(completed as usize),
        fmt_int(n as usize),
    )
}

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
    let series_thread = thread::spawn(move || loop {
        thread::sleep(Duration::from_millis(200));
        if series_done_c.load(Ordering::Relaxed) {
            break;
        }
        let completed = BS_LEAF_COUNT.load(Ordering::Relaxed);
        eprint!("\r{}", format_series_progress(completed, n));
        let _ = io::stderr().flush();
    });

    let t0 = Instant::now();
    let pqt = bs(0, n);
    series_done.store(true, Ordering::Relaxed);
    series_thread.join().unwrap();
    eprintln!("\r  Computing series:  100%  ({} terms)   ", fmt_int(n as usize));
    eprintln!("  Series done in {:.2}s", t0.elapsed().as_secs_f64());

    // π = 426_880 × √10_005 × Q / T
    let prec_bits = (digits as f64 * 3.321_928_094_887_362_6) as u32 + 100;
    eprintln!("  Computing final value ({} bits)…", prec_bits);

    let t1 = Instant::now();
    let sqrt10005 = Float::with_val(prec_bits, 10005).sqrt();
    let pi =
        Float::with_val(prec_bits, 426_880_u32) * sqrt10005 * Float::with_val(prec_bits, &pqt.q)
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

/// Format the file-write progress status line shown by write_pi_file's progress
/// thread. `elapsed` is wall-clock seconds since write started.
fn format_write_progress(written: u64, pi_total: u64, elapsed: f64) -> String {
    let speed = if elapsed > 0.001 { written as f64 / elapsed / 1_048_576.0 } else { 0.0 };
    let pct = (written * 100).checked_div(pi_total).unwrap_or(100);
    format!(
        "  Writing: {:3}%  ({:.1} / {:.1} MB)  {:.1} MB/s   ",
        pct,
        written as f64 / 1_048_576.0,
        pi_total as f64 / 1_048_576.0,
        speed,
    )
}

/// Write π to `dir/pi_<digits>_digits.txt` using parallel pwrite(2) chunks.
///
/// The file is pre-allocated to its final size, then the header and footer are
/// written sequentially (they are small) and the π digit string is written
/// concurrently by rayon-dispatched pwrite calls — the same strategy as the
/// Python version, but using shared-memory threads instead of processes.
#[cfg(unix)]
fn write_pi_file(dir: &Path, pi_str: &str, digits: usize) -> io::Result<PathBuf> {
    let filename = format!("pi_{}_digits.txt", digits);
    let path = dir.join(&filename);

    let header = format!(
        "π calculated to {} decimal places using Chudnovsky/Rayon\n{}\n\n",
        fmt_int(digits),
        "=".repeat(60),
    );
    let footer = format!("\n\nTotal decimal places: {}", fmt_int(digits));

    let hdr = header.as_bytes();
    let pi = pi_str.as_bytes(); // ASCII digits — 1 byte per char
    let ftr = footer.as_bytes();

    let total = (hdr.len() + pi.len() + ftr.len()) as u64;
    let pi_offset = hdr.len() as u64;
    let pi_total = pi.len() as u64;

    // Pre-allocate file; pwrite does not extend a file past its current size.
    let file = File::create(&path)?;
    file.set_len(total)?;

    // Header and footer are small — write sequentially.
    file.write_at(hdr, 0)?;
    file.write_at(ftr, pi_offset + pi_total)?;

    // Set up progress tracking for the parallel write.
    let n_threads = rayon::current_num_threads();
    let chunk_size = ((4 * 1024 * 1024) as usize).max(pi.len() / n_threads);

    let bytes_written = Arc::new(AtomicU64::new(0));
    let bytes_written_c = Arc::clone(&bytes_written);
    let write_done = Arc::new(AtomicBool::new(false));
    let write_done_c = Arc::clone(&write_done);
    let t_write = Instant::now();

    let progress_thread = thread::spawn(move || loop {
        thread::sleep(Duration::from_millis(200));
        if write_done_c.load(Ordering::Relaxed) {
            break;
        }
        let written = bytes_written_c.load(Ordering::Relaxed);
        let elapsed = t_write.elapsed().as_secs_f64();
        eprint!("\r{}", format_write_progress(written, pi_total, elapsed));
        let _ = io::stderr().flush();
    });

    // π digit bytes: parallel pwrite chunks.
    // File: Sync on Unix (wraps OwnedFd which is Send + Sync). pwrite is
    // thread-safe — it does not move the file pointer. ✓
    pi.par_chunks(chunk_size).enumerate().try_for_each(|(i, chunk)| -> io::Result<()> {
        let base = pi_offset + (i * chunk_size) as u64;
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
    let speed = if elapsed > 0.001 { pi_total as f64 / elapsed / 1_048_576.0 } else { 0.0 };
    eprintln!(
        "\r  Writing: 100%  ({:.1} MB)  {:.1} MB/s              ",
        pi_total as f64 / 1_048_576.0,
        speed,
    );

    Ok(path)
}

/// Announce the output filename and delegate to `write_pi_file`.
#[cfg(unix)]
fn save_pi<W: Write>(dir: &Path, pi_str: &str, digits: usize, out: &mut W) -> io::Result<PathBuf> {
    let path = write_pi_file(dir, pi_str, digits)?;
    writeln!(out, "\nFull precision π saved to {}", path.display())?;
    Ok(path)
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

fn read_line_from<R: BufRead>(reader: &mut R) -> io::Result<String> {
    let mut line = String::new();
    reader.read_line(&mut line)?;
    Ok(line.trim().to_string())
}

fn confirm_large_digits_with<R, W, E>(
    reader: &mut R,
    out: &mut W,
    _err: &mut E,
    n: usize,
) -> io::Result<bool>
where
    R: BufRead,
    W: Write,
    E: Write,
{
    write!(out, "Continue with {} digits? (y/n): ", fmt_int(n))?;
    out.flush()?;
    let line = read_line_from(reader)?;
    Ok(matches!(line.as_str(), "y" | "yes"))
}

fn prompt_digits_with<R, W, E>(reader: &mut R, out: &mut W, err: &mut E) -> io::Result<usize>
where
    R: BufRead,
    W: Write,
    E: Write,
{
    loop {
        write!(out, "Enter the number of decimal places to calculate π: ")?;
        out.flush()?;
        let line = read_line_from(reader)?;
        match line.parse::<usize>() {
            Ok(n) if n >= 1 => {
                if n > 1_000_000 {
                    writeln!(err, "Warning: very large numbers may take a long time.")?;
                    if !confirm_large_digits_with(reader, out, err, n)? {
                        continue;
                    }
                }
                return Ok(n);
            }
            _ => writeln!(err, "Please enter a positive integer.")?,
        }
    }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

fn run<R, W, E>(cli: Cli, reader: &mut R, out: &mut W, err: &mut E, dir: &Path) -> io::Result<i32>
where
    R: BufRead,
    W: Write,
    E: Write,
{
    writeln!(out, "High-Precision π Calculator (Rust/Rayon)")?;
    writeln!(out, "{}", "=".repeat(40))?;

    let digits = match cli.digits {
        Some(d) => {
            if d < 1 {
                writeln!(err, "Error: digits must be ≥ 1")?;
                return Ok(1);
            }
            if d > 1_000_000 {
                writeln!(err, "Warning: very large numbers may take a long time.")?;
            }
            d
        }
        None => prompt_digits_with(reader, out, err)?,
    };

    writeln!(out, "Calculating π to {} decimal places…", fmt_int(digits))?;
    writeln!(
        out,
        "Backend: Chudnovsky / rug+GMP+MPFR / rayon ({} threads)",
        rayon::current_num_threads()
    )?;

    let t_total = Instant::now();
    let pi_str = compute_pi(digits);
    writeln!(out, "\nDone in {:.2}s", t_total.elapsed().as_secs_f64())?;

    // Preview: first 100 decimal places (or fewer for small requests).
    if digits <= 1_000_000 {
        let preview = 100.min(digits);
        if let Some(dot) = pi_str.find('.') {
            let end = (dot + 1 + preview).min(pi_str.len());
            writeln!(out, "\nπ = {}…", &pi_str[..end])?;
            writeln!(out, "(Showing first {} decimal places)", preview)?;
        }
    }

    if digits > 10_000 {
        #[cfg(unix)]
        save_pi(dir, &pi_str, digits, out)?;
        #[cfg(not(unix))]
        writeln!(out, "\nFile output not supported on this platform.")?;
    } else {
        write!(out, "\nDisplay all {} digits? (y/n): ", fmt_int(digits))?;
        out.flush()?;
        if matches!(read_line_from(reader)?.as_str(), "y" | "yes") {
            writeln!(out, "\nπ = {}", pi_str)?;
            writeln!(out, "\nTotal digits: {}", fmt_int(digits))?;
        } else {
            #[cfg(unix)]
            save_pi(dir, &pi_str, digits, out)?;
            #[cfg(not(unix))]
            writeln!(out, "\nFile output not supported on this platform.")?;
        }
    }

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
    let dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let code = run(cli, &mut reader, &mut out, &mut err, &dir).unwrap_or(1);
    std::process::exit(code);
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;
    use tempfile::tempdir;

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
        let expected_abs = Integer::from(5u32) * (Integer::from(CHU_A) + Integer::from(CHU_B));
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

    #[test]
    fn test_bs_split_consistency_above_threshold() {
        // n=600 exercises the rayon::join() parallel branch (threshold is 512).
        let full = bs(0, 600);
        let merged = bs_merge(bs(0, 300), bs(300, 600));
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

    #[test]
    fn test_pi_to_string_single_decimal_place() {
        // digits=1: "3." + 1 digit = "3.1"
        let pi = Float::with_val(200, rug::float::Constant::Pi);
        let s = pi_to_string(pi, 1);
        assert_eq!(s.len(), 3);
        assert_eq!(s, "3.1");
    }

    #[test]
    fn test_pi_to_string_strips_exponent() {
        // A value like 0.01 produces exponent notation from MPFR;
        // the exponent suffix must be stripped before trimming.
        let v = Float::with_val(64, 0.01_f64);
        let s = pi_to_string(v, 5);
        assert!(!s.contains('e') && !s.contains('E'));
    }

    #[test]
    fn test_pi_to_string_no_dot_path() {
        // rug formats 0 as "0" (no decimal point); pi_to_string must append ".000…"
        let v = Float::with_val(64, 0u32);
        let s = pi_to_string(v, 3);
        assert!(s.contains('.'), "must contain a decimal point");
        assert_eq!(s, "0.000");
    }

    // --- format_series_progress ---

    #[test]
    fn test_format_series_progress_zero_completed() {
        let s = format_series_progress(0, 100);
        assert!(s.contains("  0%"), "should show 0%: {}", s);
        assert!(s.contains("0 / 100 terms"), "should show term counts: {}", s);
    }

    #[test]
    fn test_format_series_progress_partial() {
        let s = format_series_progress(50, 100);
        assert!(s.contains(" 50%"), "should show 50%: {}", s);
    }

    #[test]
    fn test_format_series_progress_complete() {
        let s = format_series_progress(100, 100);
        assert!(s.contains("100%"), "should show 100%: {}", s);
    }

    #[test]
    fn test_format_series_progress_zero_total() {
        // n=0 must not panic; checked_div falls back to 100%.
        let s = format_series_progress(0, 0);
        assert!(s.contains("100%"), "zero total should show 100%: {}", s);
    }

    // --- format_write_progress ---

    #[test]
    fn test_format_write_progress_normal_speed() {
        let s = format_write_progress(512 * 1024, 1024 * 1024, 0.5);
        assert!(s.contains(" 50%"), "should show 50%: {}", s);
        assert!(s.contains("MB/s"), "should contain MB/s: {}", s);
    }

    #[test]
    fn test_format_write_progress_zero_elapsed_uses_zero_speed() {
        let s = format_write_progress(0, 1024, 0.0);
        assert!(s.contains("0.0 MB/s"), "should show 0.0 MB/s: {}", s);
    }

    #[test]
    fn test_format_write_progress_zero_total_pct_is_100() {
        let s = format_write_progress(0, 0, 1.0);
        assert!(s.contains("100%"), "zero total should show 100%: {}", s);
    }

    #[test]
    fn test_format_write_progress_complete() {
        let s = format_write_progress(1024, 1024, 1.0);
        assert!(s.contains("100%"), "complete should show 100%: {}", s);
    }

    // --- read_line_from ---

    #[test]
    fn test_read_line_from_trims_newline() {
        let input = b"hello\n";
        let mut r = &input[..];
        assert_eq!(read_line_from(&mut r).unwrap(), "hello");
    }

    #[test]
    fn test_read_line_from_empty_input_returns_empty() {
        let input = b"";
        let mut r = &input[..];
        assert_eq!(read_line_from(&mut r).unwrap(), "");
    }

    #[test]
    fn test_read_line_from_trims_whitespace() {
        let input = b"  42  \n";
        let mut r = &input[..];
        assert_eq!(read_line_from(&mut r).unwrap(), "42");
    }

    // --- confirm_large_digits_with ---

    #[test]
    fn test_confirm_large_digits_with_y() {
        let mut r = &b"y\n"[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        assert!(confirm_large_digits_with(&mut r, &mut out, &mut err, 2_000_000).unwrap());
    }

    #[test]
    fn test_confirm_large_digits_with_yes() {
        let mut r = &b"yes\n"[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        assert!(confirm_large_digits_with(&mut r, &mut out, &mut err, 2_000_000).unwrap());
    }

    #[test]
    fn test_confirm_large_digits_with_n() {
        let mut r = &b"n\n"[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        assert!(!confirm_large_digits_with(&mut r, &mut out, &mut err, 2_000_000).unwrap());
    }

    #[test]
    fn test_confirm_large_digits_with_other_input() {
        let mut r = &b"maybe\n"[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        assert!(!confirm_large_digits_with(&mut r, &mut out, &mut err, 2_000_000).unwrap());
    }

    // --- prompt_digits_with ---

    #[test]
    fn test_prompt_digits_with_valid_input() {
        let mut r = &b"10\n"[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        assert_eq!(prompt_digits_with(&mut r, &mut out, &mut err).unwrap(), 10);
    }

    #[test]
    fn test_prompt_digits_with_minimum_value() {
        let mut r = &b"1\n"[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        assert_eq!(prompt_digits_with(&mut r, &mut out, &mut err).unwrap(), 1);
    }

    #[test]
    fn test_prompt_digits_with_zero_then_valid() {
        let input = b"0\n5\n";
        let mut r = &input[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        assert_eq!(prompt_digits_with(&mut r, &mut out, &mut err).unwrap(), 5);
        let err_str = String::from_utf8(err).unwrap();
        assert!(err_str.contains("positive integer"));
    }

    #[test]
    fn test_prompt_digits_with_non_numeric_then_valid() {
        let input = b"abc\n7\n";
        let mut r = &input[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        assert_eq!(prompt_digits_with(&mut r, &mut out, &mut err).unwrap(), 7);
    }

    #[test]
    fn test_prompt_digits_with_large_then_decline_then_small() {
        // 2_000_001 > 1_000_000 → warning + confirm prompt → "n" → retry → 5
        let input = b"2000001\nn\n5\n";
        let mut r = &input[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        assert_eq!(prompt_digits_with(&mut r, &mut out, &mut err).unwrap(), 5);
    }

    #[test]
    fn test_prompt_digits_with_large_then_accept() {
        let input = b"2000001\ny\n";
        let mut r = &input[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        assert_eq!(prompt_digits_with(&mut r, &mut out, &mut err).unwrap(), 2_000_001);
    }

    // --- write_pi_file ---

    #[test]
    #[cfg(unix)]
    fn test_write_pi_file_creates_file_with_expected_contents() {
        let dir = tempdir().unwrap();
        let pi_str = PI_REF;
        let path = write_pi_file(dir.path(), pi_str, 50).unwrap();
        let contents = std::fs::read_to_string(&path).unwrap();
        assert!(contents.contains(PI_REF));
        assert!(contents.contains("50"));
    }

    #[test]
    #[cfg(unix)]
    fn test_write_pi_file_filename_includes_digits() {
        let dir = tempdir().unwrap();
        let path = write_pi_file(dir.path(), PI_REF, 50).unwrap();
        assert!(path.to_string_lossy().contains("50"));
        assert!(path.to_string_lossy().contains("pi_"));
    }

    #[test]
    #[cfg(unix)]
    fn test_write_pi_file_idempotent() {
        let dir = tempdir().unwrap();
        let path1 = write_pi_file(dir.path(), PI_REF, 50).unwrap();
        let path2 = write_pi_file(dir.path(), PI_REF, 50).unwrap();
        assert_eq!(path1, path2);
        let c1 = std::fs::read_to_string(&path1).unwrap();
        let c2 = std::fs::read_to_string(&path2).unwrap();
        assert_eq!(c1, c2);
    }

    #[test]
    #[cfg(unix)]
    fn test_write_pi_file_missing_dir_errors() {
        let result = write_pi_file(Path::new("/nonexistent/path"), PI_REF, 50);
        assert!(result.is_err());
    }

    // --- save_pi ---

    #[test]
    #[cfg(unix)]
    fn test_save_pi_writes_file_and_announces() {
        let dir = tempdir().unwrap();
        let mut out = Vec::<u8>::new();
        let path = save_pi(dir.path(), PI_REF, 50, &mut out).unwrap();
        assert!(path.exists());
        let announcement = String::from_utf8(out).unwrap();
        assert!(announcement.contains("π saved to"));
    }

    // --- run ---

    #[test]
    fn test_run_with_arg_zero_returns_one() {
        let cli = Cli { digits: Some(0) };
        let mut r = &b""[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let dir = tempdir().unwrap();
        let code = run(cli, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 1);
        assert!(String::from_utf8(err).unwrap().contains("≥ 1"));
    }

    #[test]
    fn test_run_with_arg_displays_when_user_says_y() {
        let cli = Cli { digits: Some(10) };
        let mut r = &b"y\n"[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let dir = tempdir().unwrap();
        let code = run(cli, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("π = 3.1415926535"));
    }

    #[test]
    #[cfg(unix)]
    fn test_run_with_arg_saves_when_user_says_n() {
        let cli = Cli { digits: Some(10) };
        let mut r = &b"n\n"[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let dir = tempdir().unwrap();
        let code = run(cli, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("π saved to"));
    }

    #[test]
    fn test_run_no_arg_prompts_for_digits() {
        let cli = Cli { digits: None };
        let mut r = &b"10\ny\n"[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let dir = tempdir().unwrap();
        let code = run(cli, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("decimal places to calculate"));
    }

    #[test]
    #[cfg(unix)]
    fn test_run_with_arg_above_10k_auto_saves() {
        let cli = Cli { digits: Some(20_000) };
        let mut r = &b""[..];
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let dir = tempdir().unwrap();
        let code = run(cli, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("π saved to"));
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

    struct FailWriter;

    impl std::io::Write for FailWriter {
        fn write(&mut self, _buf: &[u8]) -> std::io::Result<usize> {
            Err(std::io::Error::other("injected write failure"))
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn run_returns_err_on_stdout_failure() {
        let dir = tempdir().unwrap();
        let mut err = Vec::new();
        let mut reader = std::io::Cursor::new("n\n");
        let cli = Cli { digits: Some(10) };
        let result = run(cli, &mut reader, &mut FailWriter, &mut err, dir.path());
        assert!(result.is_err());
    }

    #[test]
    fn run_returns_err_on_stderr_failure() {
        // digits=0 is invalid; run() writes error to stderr
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut reader = std::io::Cursor::new("");
        let cli = Cli { digits: Some(0) };
        let result = run(cli, &mut reader, &mut out, &mut FailWriter, dir.path());
        assert!(result.is_err());
    }

    proptest! {
        #[test]
        fn prop_generate_succeeds(max_digits in 1usize..=5usize) {
            let result = compute_pi(max_digits);
            prop_assert!(!result.is_empty());
            prop_assert!(result.starts_with("3."));
        }
    }
}
