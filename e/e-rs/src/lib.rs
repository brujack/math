use std::io::{self, Write};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use rug::{Float, Integer};

// ---------------------------------------------------------------------------
// Taylor series constants
// ---------------------------------------------------------------------------

/// Switch from parallel rayon::join to serial recursion below this range size.
pub const BS_PAR_THRESHOLD: u64 = 512;

/// Counts completed leaf nodes during binary splitting; read by the progress thread.
pub static BS_LEAF_COUNT: AtomicU64 = AtomicU64::new(0);

// ---------------------------------------------------------------------------
// Binary splitting — the core of the Taylor series for e
// ---------------------------------------------------------------------------

/// (P, Q) accumulators for a range [a, b) of the Taylor series.
///
/// Full series [0, N):  e = Q / P
pub struct Pq {
    pub p: Integer,
    pub q: Integer,
}

/// Recursive binary splitting, parallelised with rayon::join().
pub fn bs(a: u64, b: u64) -> Pq {
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

pub fn bs_leaf(a: u64) -> Pq {
    let result = if a == 0 {
        Pq { p: Integer::from(1u32), q: Integer::from(1u32) }
    } else {
        let val = a + 1;
        Pq { p: Integer::from(val), q: Integer::from(val) }
    };

    BS_LEAF_COUNT.fetch_add(1, Ordering::Relaxed);
    result
}

/// Combine two adjacent ranges [a,m) and [m,b):
///   P(a,b) = P(a,m) × P(m,b)
///   Q(a,b) = Q(a,m) × P(m,b) + Q(m,b)
pub fn bs_merge(l: Pq, r: Pq) -> Pq {
    Pq { p: Integer::from(&l.p * &r.p), q: Integer::from(&l.q * &r.p) + &r.q }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

pub fn fmt_int(n: usize) -> String {
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

pub fn format_series_progress(completed: u64, n: u64) -> String {
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
pub fn format_write_progress(written: u64, e_total: u64, elapsed: f64) -> String {
    let speed = if elapsed > 0.001 { written as f64 / elapsed / 1_048_576.0 } else { 0.0 };
    let pct = (written * 100).checked_div(e_total).unwrap_or(100);
    format!(
        "  Writing: {:3}%  ({:.1} / {:.1} MB)  {:.1} MB/s   ",
        pct,
        written as f64 / 1_048_576.0,
        e_total as f64 / 1_048_576.0,
        speed,
    )
}

pub fn e_to_string(e: Float, digits: usize) -> String {
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
// e computation
// ---------------------------------------------------------------------------

/// Compute e to `digits` decimal places and return it as a formatted string.
pub fn compute_e(digits: usize) -> String {
    let n: u64 = if digits > 1 {
        let d = digits as f64;
        let n0 = d / (d + 1.0).log10();
        let log_n0 = n0.log10().max(1.0);
        let deficit = (d - n0 * (log_n0 - std::f64::consts::LOG10_E)).max(0.0);
        (n0 + deficit / log_n0) as u64 + 50
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
    eprintln!("\r  Computing series:  100%  ({} terms)   ", fmt_int(n as usize));
    eprintln!("  Series done in {:.2}s", t0.elapsed().as_secs_f64());

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
