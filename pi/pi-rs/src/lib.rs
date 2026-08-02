use std::io::{self, Write};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use rug::{Float, Integer};

// ---------------------------------------------------------------------------
// Chudnovsky series constants
// ---------------------------------------------------------------------------

pub const CHU_A: u64 = 13_591_409;
const CHU_B: u64 = 545_140_134;
/// 640320³ / 24  =  10_939_058_860_032_000  (fits in u64)
pub const CHU_C3_24: u64 = 10_939_058_860_032_000;

/// Switch from parallel rayon::join to serial recursion below this range size.
pub const BS_PAR_THRESHOLD: u64 = 512;

/// Counts completed leaf nodes during binary splitting; read by the progress thread.
pub static BS_LEAF_COUNT: AtomicU64 = AtomicU64::new(0);

// ---------------------------------------------------------------------------
// Binary splitting — the core of the Chudnovsky algorithm
// ---------------------------------------------------------------------------

/// (P, Q, T) accumulators for a range [a, b) of the Chudnovsky series.
#[derive(Debug)]
pub struct Pqt {
    pub p: Integer,
    pub q: Integer,
    pub t: Integer,
}

pub fn bs(a: u64, b: u64) -> Pqt {
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

pub fn bs_leaf(a: u64) -> Pqt {
    let result = if a == 0 {
        Pqt { p: Integer::from(1u32), q: Integer::from(1u32), t: Integer::from(CHU_A) }
    } else {
        let p = Integer::from(6 * a - 5) * Integer::from(2 * a - 1) * Integer::from(6 * a - 1);
        let ai = Integer::from(a);
        let q = Integer::from(&ai * &ai) * &ai * CHU_C3_24;
        let t_abs = Integer::from(&p) * (Integer::from(CHU_A) + Integer::from(CHU_B) * &ai);
        let t = if a & 1 == 1 { -t_abs } else { t_abs };
        Pqt { p, q, t }
    };

    BS_LEAF_COUNT.fetch_add(1, Ordering::Relaxed);
    result
}

pub fn bs_merge(l: Pqt, r: Pqt) -> Pqt {
    Pqt {
        p: Integer::from(&l.p * &r.p),
        q: Integer::from(&l.q * &r.q),
        t: Integer::from(&r.q * &l.t) + Integer::from(&l.p * &r.t),
    }
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

pub fn pi_to_string(pi: Float, digits: usize) -> String {
    let raw = pi.to_string_radix(10, Some(digits + 5));
    let raw: &str = match raw.find(['e', 'E']) {
        Some(pos) => &raw[..pos],
        None => &raw,
    };
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
// π computation
// ---------------------------------------------------------------------------

/// Compute π to `digits` decimal places and return it as a formatted string.
pub fn compute_pi(digits: usize) -> String {
    let n = (digits / 14 + 10) as u64;
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
    let pqt = bs(0, n);
    series_done.store(true, Ordering::Relaxed);
    series_thread.join().unwrap();
    eprintln!("\r  Computing series:  100%  ({} terms)   ", fmt_int(n as usize));
    eprintln!("  Series done in {:.2}s", t0.elapsed().as_secs_f64());

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
