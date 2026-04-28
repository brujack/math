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
/// write speed. Returns the absolute path written.
#[cfg(unix)]
fn write_e_file(dir: &Path, e_str: &str, digits: usize) -> io::Result<PathBuf> {
    let path = dir.join(format!("e_{}_digits.txt", digits));

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

    let file = File::create(&path)?;
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

    let progress_thread = thread::spawn(move || loop {
        thread::sleep(Duration::from_millis(200));
        if write_done_c.load(Ordering::Relaxed) {
            break;
        }
        let written = bytes_written_c.load(Ordering::Relaxed);
        let elapsed = t_write.elapsed().as_secs_f64();
        eprint!("\r{}", format_write_progress(written, e_total, elapsed));
        let _ = io::stderr().flush();
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

    Ok(path)
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Format the series-progress status line shown by the compute_e progress thread.
fn format_series_progress(completed: u64, n: u64) -> String {
    let pct = (completed * 100).checked_div(n).unwrap_or(100);
    format!(
        "  Computing series:  {:3}%  ({} / {} terms)   ",
        pct,
        fmt_int(completed as usize),
        fmt_int(n as usize),
    )
}

/// Format the file-write progress status line shown by write_e_file's progress
/// thread. `elapsed` is wall-clock seconds since write started.
fn format_write_progress(written: u64, e_total: u64, elapsed: f64) -> String {
    let speed = if elapsed > 0.001 {
        written as f64 / elapsed / 1_048_576.0
    } else {
        0.0
    };
    let pct = (written * 100).checked_div(e_total).unwrap_or(100);
    format!(
        "  Writing: {:3}%  ({:.1} / {:.1} MB)  {:.1} MB/s   ",
        pct,
        written as f64 / 1_048_576.0,
        e_total as f64 / 1_048_576.0,
        speed,
    )
}

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

fn read_line_from<R: BufRead>(reader: &mut R) -> io::Result<String> {
    let mut line = String::new();
    reader.read_line(&mut line)?;
    Ok(line.trim().to_string())
}

/// Prompt for the digit count on `out`, reading from `reader`, with errors on `err`.
/// Loops until a positive integer is supplied (and confirmed if > 1_000_000).
fn prompt_digits_with<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    err: &mut E,
) -> io::Result<usize> {
    loop {
        write!(out, "Enter the number of decimal places to calculate e: ")?;
        out.flush()?;
        match read_line_from(reader)?.parse::<usize>() {
            Ok(n) if n >= 1 => {
                if n > 1_000_000 && !confirm_large_digits_with(reader, out, err, n)? {
                    continue;
                }
                return Ok(n);
            }
            _ => writeln!(err, "Please enter a positive integer.")?,
        }
    }
}

/// Show a y/n confirmation for a large digit count. Returns `true` for "y"/"yes".
fn confirm_large_digits_with<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    n: usize,
) -> io::Result<bool> {
    writeln!(err, "Warning: very large numbers may take a long time.")?;
    write!(out, "Continue with {} digits? (y/n): ", fmt_int(n))?;
    out.flush()?;
    Ok(matches!(read_line_from(reader)?.as_str(), "y" | "yes"))
}

// ---------------------------------------------------------------------------
// Run / Entry point
// ---------------------------------------------------------------------------

/// Orchestrates a single CLI invocation. Returns the process exit code
/// (0 on success, 1 on validation error). All I/O is parameterised so tests
/// can inject pipes and a temp output directory.
fn run<R: BufRead, W: Write, E: Write>(
    cli: Cli,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    dir: &Path,
) -> io::Result<i32> {
    writeln!(out, "High-Precision e Calculator (Rust/Rayon)")?;
    writeln!(out, "{}", "=".repeat(40))?;

    let digits = match cli.digits {
        Some(d) => {
            if d < 1 {
                writeln!(err, "Error: digits must be >= 1")?;
                return Ok(1);
            }
            if d > 1_000_000 {
                writeln!(err, "Warning: very large numbers may take a long time.")?;
            }
            d
        }
        None => prompt_digits_with(reader, out, err)?,
    };

    writeln!(
        out,
        "Calculating e to {} decimal places...",
        fmt_int(digits)
    )?;
    writeln!(
        out,
        "Backend: Taylor / rug+GMP+MPFR / rayon ({} threads)",
        rayon::current_num_threads()
    )?;

    let t_total = Instant::now();
    let e_str = compute_e(digits);
    writeln!(out, "\nDone in {:.2}s", t_total.elapsed().as_secs_f64())?;

    if digits <= 1_000_000 {
        let preview = 100.min(digits);
        if let Some(dot) = e_str.find('.') {
            let end = (dot + 1 + preview).min(e_str.len());
            writeln!(out, "\ne = {}...", &e_str[..end])?;
            writeln!(out, "(Showing first {} decimal places)", preview)?;
        }
    }

    if digits > 10_000 {
        let path = save_e(dir, &e_str, digits, out)?;
        writeln!(out, "Full precision e saved to {}", path.display())?;
    } else {
        write!(out, "\nDisplay all {} digits? (y/n): ", fmt_int(digits))?;
        out.flush()?;
        if matches!(read_line_from(reader)?.as_str(), "y" | "yes") {
            writeln!(out, "\ne = {}", e_str)?;
            writeln!(out, "\nTotal digits: {}", fmt_int(digits))?;
        } else {
            let path = save_e(dir, &e_str, digits, out)?;
            writeln!(out, "\nFull precision e saved to {}", path.display())?;
        }
    }

    Ok(0)
}

/// Save e to `dir` and announce the filename. Unix-only — `write_e_file`
/// uses `pwrite(2)` which has no portable equivalent.
#[cfg(unix)]
fn save_e<W: Write>(dir: &Path, e_str: &str, digits: usize, out: &mut W) -> io::Result<PathBuf> {
    let filename = format!("e_{}_digits.txt", digits);
    writeln!(out, "\nSaving to {}...", filename)?;
    write_e_file(dir, e_str, digits)
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

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

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
        let pq = bs_leaf(1);
        assert_eq!(pq.p, Integer::from(2u32));
        assert_eq!(pq.q, Integer::from(2u32));
    }

    #[test]
    fn test_bs_leaf_two() {
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
        assert!(
            after >= before + 2,
            "expected counter to increase by at least 2"
        );
    }

    // --- bs_merge ---

    #[test]
    fn test_bs_merge_matches_two_leaves() {
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
    fn test_compute_e_one_digit() {
        // Exercises the `digits > 1` else branch (n = 20 fixed).
        let s = compute_e(1);
        assert_eq!(s, "2.7");
    }

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

    #[test]
    fn test_compute_e_long_enough_for_progress_thread() {
        // Large enough to make `bs` take >200ms in debug mode and trigger
        // the progress-thread loop body (otherwise it spawns and never ticks).
        let s = compute_e(20_000);
        assert!(s.starts_with(&E_REF[..50]));
        assert!(s.len() >= 20_002);
    }

    // --- format_series_progress / format_write_progress ---

    #[test]
    fn test_format_series_progress_zero_completed() {
        let s = format_series_progress(0, 100);
        assert!(s.contains("0%"));
        assert!(s.contains("0 / 100"));
    }

    #[test]
    fn test_format_series_progress_partial() {
        let s = format_series_progress(25, 100);
        assert!(s.contains("25%"));
        assert!(s.contains("25 / 100"));
    }

    #[test]
    fn test_format_series_progress_complete() {
        let s = format_series_progress(100, 100);
        assert!(s.contains("100%"));
    }

    #[test]
    fn test_format_series_progress_zero_total() {
        // Defensive: avoid div-by-zero if n is somehow 0.
        let s = format_series_progress(0, 0);
        assert!(s.contains("100%"));
    }

    #[test]
    fn test_format_write_progress_normal_speed() {
        let s = format_write_progress(2 * 1_048_576, 4 * 1_048_576, 1.0);
        assert!(s.contains("50%"));
        assert!(s.contains("2.0 / 4.0 MB"));
        assert!(s.contains("MB/s"));
    }

    #[test]
    fn test_format_write_progress_zero_elapsed_uses_zero_speed() {
        let s = format_write_progress(1024, 1_048_576, 0.0);
        assert!(s.contains("0.0 MB/s"));
    }

    #[test]
    fn test_format_write_progress_zero_total_pct_is_100() {
        // checked_div by 0 should fall back to 100%.
        let s = format_write_progress(0, 0, 0.5);
        assert!(s.contains("100%"));
    }

    #[test]
    fn test_format_write_progress_complete() {
        let s = format_write_progress(1_048_576, 1_048_576, 0.5);
        assert!(s.contains("100%"));
    }

    // --- bs above the parallel threshold ---

    #[test]
    fn test_bs_split_consistency_above_threshold() {
        // BS_PAR_THRESHOLD = 512 — using b - a = 600 hits the rayon::join branch.
        let full = bs(0, 600);
        let merged = bs_merge(bs(0, 300), bs(300, 600));
        assert_eq!(full.p, merged.p);
        assert_eq!(full.q, merged.q);
    }

    // --- e_to_string padding / no-dot branches ---

    #[test]
    fn test_e_to_string_strips_exponent_suffix() {
        // Values < 1 produce "X.YYYe-N" notation in rug; the strip branch
        // (Some(pos) =>) must remove the exponent before trimming.
        let f = Float::with_val(64, 0.01);
        let s = e_to_string(f, 5);
        assert!(!s.contains('e') && !s.contains('E'));
        assert!(s.starts_with("1."));
    }

    #[test]
    fn test_e_to_string_pads_when_no_dot() {
        // Float::with_val(64, 0) produces "0" with no decimal point.
        // The function must fabricate "0." and pad zeros.
        let f = Float::with_val(64, 0u32);
        let s = e_to_string(f, 4);
        assert_eq!(s, "0.0000");
    }

    // --- read_line_from ---

    #[test]
    fn test_read_line_from_trims_newline() {
        let mut input = &b"hello\n"[..];
        assert_eq!(read_line_from(&mut input).unwrap(), "hello");
    }

    #[test]
    fn test_read_line_from_empty_input_returns_empty() {
        let mut input = &b""[..];
        assert_eq!(read_line_from(&mut input).unwrap(), "");
    }

    #[test]
    fn test_read_line_from_trims_whitespace() {
        let mut input = &b"  spaced  \n"[..];
        assert_eq!(read_line_from(&mut input).unwrap(), "spaced");
    }

    // --- prompt_digits_with ---

    #[test]
    fn test_prompt_digits_with_valid_input() {
        let mut input = &b"42\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let n = prompt_digits_with(&mut input, &mut out, &mut err).unwrap();
        assert_eq!(n, 42);
        assert!(String::from_utf8(out).unwrap().contains("Enter"));
        assert!(err.is_empty());
    }

    #[test]
    fn test_prompt_digits_with_minimum_value() {
        let mut input = &b"1\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let n = prompt_digits_with(&mut input, &mut out, &mut err).unwrap();
        assert_eq!(n, 1);
    }

    #[test]
    fn test_prompt_digits_with_zero_then_valid() {
        let mut input = &b"0\n5\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let n = prompt_digits_with(&mut input, &mut out, &mut err).unwrap();
        assert_eq!(n, 5);
        assert!(String::from_utf8(err).unwrap().contains("positive integer"));
    }

    #[test]
    fn test_prompt_digits_with_non_numeric_then_valid() {
        let mut input = &b"abc\n7\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let n = prompt_digits_with(&mut input, &mut out, &mut err).unwrap();
        assert_eq!(n, 7);
        assert!(String::from_utf8(err).unwrap().contains("positive integer"));
    }

    #[test]
    fn test_prompt_digits_with_large_then_decline_then_small() {
        // Large value declined, then a small valid value accepted.
        let mut input = &b"2000000\nn\n10\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let n = prompt_digits_with(&mut input, &mut out, &mut err).unwrap();
        assert_eq!(n, 10);
        let err_s = String::from_utf8(err).unwrap();
        assert!(err_s.contains("very large"));
    }

    #[test]
    fn test_prompt_digits_with_large_then_accept() {
        let mut input = &b"2000000\ny\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let n = prompt_digits_with(&mut input, &mut out, &mut err).unwrap();
        assert_eq!(n, 2_000_000);
    }

    // --- confirm_large_digits_with ---

    #[test]
    fn test_confirm_large_digits_with_yes() {
        let mut input = &b"y\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let ok = confirm_large_digits_with(&mut input, &mut out, &mut err, 2_000_000).unwrap();
        assert!(ok);
        assert!(String::from_utf8(out).unwrap().contains("Continue"));
    }

    #[test]
    fn test_confirm_large_digits_with_yes_word() {
        let mut input = &b"yes\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let ok = confirm_large_digits_with(&mut input, &mut out, &mut err, 2_000_000).unwrap();
        assert!(ok);
    }

    #[test]
    fn test_confirm_large_digits_with_no() {
        let mut input = &b"n\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let ok = confirm_large_digits_with(&mut input, &mut out, &mut err, 2_000_000).unwrap();
        assert!(!ok);
    }

    #[test]
    fn test_confirm_large_digits_with_other_input() {
        let mut input = &b"maybe\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let ok = confirm_large_digits_with(&mut input, &mut out, &mut err, 2_000_000).unwrap();
        assert!(!ok);
    }

    // --- write_e_file ---

    #[cfg(unix)]
    #[test]
    fn test_write_e_file_creates_file_with_expected_contents() {
        let dir = tempdir().unwrap();
        let path = write_e_file(dir.path(), E_REF, 50).unwrap();
        assert!(path.exists());
        let contents = std::fs::read_to_string(&path).unwrap();
        assert!(contents.contains(E_REF));
        assert!(contents.contains("50 decimal places"));
        assert!(contents.contains("Total decimal places: 50"));
    }

    #[cfg(unix)]
    #[test]
    fn test_write_e_file_filename_includes_digits() {
        let dir = tempdir().unwrap();
        let path = write_e_file(dir.path(), "2.7", 1).unwrap();
        assert_eq!(path.file_name().unwrap(), "e_1_digits.txt");
    }

    #[cfg(unix)]
    #[test]
    fn test_write_e_file_idempotent() {
        let dir = tempdir().unwrap();
        let p1 = write_e_file(dir.path(), E_REF, 50).unwrap();
        let c1 = std::fs::read_to_string(&p1).unwrap();
        let p2 = write_e_file(dir.path(), E_REF, 50).unwrap();
        let c2 = std::fs::read_to_string(&p2).unwrap();
        assert_eq!(p1, p2);
        assert_eq!(c1, c2);
    }

    #[cfg(unix)]
    #[test]
    fn test_write_e_file_missing_dir_errors() {
        let bad = Path::new("/no/such/path/for/e/test");
        let res = write_e_file(bad, "2.7", 1);
        assert!(res.is_err());
    }

    // --- save_e ---

    #[test]
    fn test_save_e_writes_file() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let path = save_e(dir.path(), E_REF, 50, &mut out).unwrap();
        assert!(path.exists());
        assert!(String::from_utf8(out).unwrap().contains("Saving to"));
    }

    // --- run ---

    #[test]
    fn test_run_with_arg_zero_returns_one() {
        let dir = tempdir().unwrap();
        let cli = Cli { digits: Some(0) };
        let mut reader = &b""[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let rc = run(cli, &mut reader, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(rc, 1);
        assert!(String::from_utf8(err).unwrap().contains("digits must be"));
    }

    #[test]
    fn test_run_with_arg_displays_when_user_says_y() {
        let dir = tempdir().unwrap();
        let cli = Cli { digits: Some(10) };
        let mut reader = &b"y\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let rc = run(cli, &mut reader, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(rc, 0);
        let out_s = String::from_utf8(out).unwrap();
        assert!(out_s.contains(&E_REF[..12]));
        assert!(out_s.contains("Total digits"));
    }

    #[test]
    fn test_run_with_arg_saves_when_user_says_n() {
        let dir = tempdir().unwrap();
        let cli = Cli { digits: Some(10) };
        let mut reader = &b"n\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let rc = run(cli, &mut reader, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(rc, 0);
        let saved = dir.path().join("e_10_digits.txt");
        assert!(saved.exists());
        let body = std::fs::read_to_string(&saved).unwrap();
        assert!(body.contains(&E_REF[..12]));
    }

    #[test]
    fn test_run_with_arg_above_10k_auto_saves() {
        // digits > 10_000 takes the auto-save branch (no display prompt).
        let dir = tempdir().unwrap();
        let cli = Cli {
            digits: Some(10_001),
        };
        let mut reader = &b""[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let rc = run(cli, &mut reader, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(rc, 0);
        let saved = dir.path().join("e_10001_digits.txt");
        assert!(saved.exists());
        let out_s = String::from_utf8(out).unwrap();
        assert!(out_s.contains("Full precision e saved to"));
        // Should NOT contain the display prompt.
        assert!(!out_s.contains("Display all"));
    }

    #[test]
    fn test_run_no_arg_prompts_for_digits() {
        let dir = tempdir().unwrap();
        let cli = Cli { digits: None };
        // First line: digit count; second line: y/n for display
        let mut reader = &b"10\nn\n"[..];
        let mut out = Vec::new();
        let mut err = Vec::new();
        let rc = run(cli, &mut reader, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(rc, 0);
        let out_s = String::from_utf8(out).unwrap();
        assert!(out_s.contains("Enter the number"));
        let saved = dir.path().join("e_10_digits.txt");
        assert!(saved.exists());
    }
}
