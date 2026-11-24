//! `--refine`: certified bisection of each zero's bracket on `f64` points, then the
//! normalised spacings, their histogram against the Wigner surmise and the KS distance.

use std::f64::consts::{PI, TAU};
use std::io::{self, Write};

use rug::Float;
use rug::float::Round;

use crate::config::VerifyConfig;
use crate::interval::Sign;
use crate::isolate::candidates;
use crate::verify::{Fault, PoolPolicy, Runner};
use crate::zfun::{ZFault, ZSource, certified_sign_ladder};

/// Nearby `f64`s tried after the midpoint when the midpoint's sign stays uncertain.
const NEARBY_TRIES: usize = 8;

/// A nearby try sits at the midpoint plus or minus `(b - a) * 2^-k`, for these k.
const NEARBY_SHIFTS: [i32; NEARBY_TRIES / 2] = [5, 4, 3, 2];

/// Histogram bins over s in [0, 3], each 0.15 wide.
pub const BIN_COUNT: usize = 20;
pub const BIN_WIDTH: f64 = 0.15;
pub const S_MAX: f64 = 3.0;

/// The first candidate in `(a, b)` whose sign is certified, with that sign.
fn first_certified<F>(a: f64, b: f64, sign_at: &mut F) -> Result<Option<(f64, Sign)>, ZFault>
where
    F: FnMut(f64) -> Result<Option<Sign>, ZFault>,
{
    for c in candidates(a, b, &NEARBY_SHIFTS) {
        if let Some(sign) = sign_at(c)? {
            return Ok(Some((c, sign)));
        }
    }
    Ok(None)
}

/// Most bisection steps one bracket gets. Every step keeps at most 3/4 of the width
/// (the farthest candidate sits a quarter of the width from the midpoint), so 64
/// halvings of an `f64` bracket need at most log(2^64)/log(4/3), about 154, steps.
const MAX_BISECT_STEPS: usize = 256;

/// Bisects `(a, b)`, where `a` has certified sign `sign_a` and `b` the opposite one,
/// moving the end whose sign the new point shares. Both ends keep a certified sign,
/// so the certified sign change survives every step. Stops when no candidate point
/// certifies (midpoint plus 8 nearby tries), no `f64` lies strictly between, or the
/// step bound is reached; the bracket returned is always still certified.
fn bisect<F>(a: f64, b: f64, sign_a: Sign, sign_at: F) -> Result<(f64, f64), ZFault>
where
    F: FnMut(f64) -> Result<Option<Sign>, ZFault>,
{
    bisect_bounded(a, b, sign_a, sign_at, MAX_BISECT_STEPS)
}

fn bisect_bounded<F>(
    mut a: f64,
    mut b: f64,
    sign_a: Sign,
    mut sign_at: F,
    max_steps: usize,
) -> Result<(f64, f64), ZFault>
where
    F: FnMut(f64) -> Result<Option<Sign>, ZFault>,
{
    for _ in 0..max_steps {
        let Some((c, sign)) = first_certified(a, b, &mut sign_at)? else {
            break;
        };
        if sign == sign_a {
            a = c;
        } else {
            b = c;
        }
    }
    Ok((a, b))
}

/// Refines one bracket. A bracket whose ends do not both certify, with opposite
/// signs, is returned unchanged: it is never narrowed without a certified change.
fn refine_one<F>(a: f64, b: f64, mut sign_at: F) -> Result<(f64, f64), ZFault>
where
    F: FnMut(f64) -> Result<Option<Sign>, ZFault>,
{
    match (sign_at(a)?, sign_at(b)?) {
        (Some(sa), Some(sb)) if sa != sb => bisect(a, b, sa, sign_at),
        _ => Ok((a, b)),
    }
}

/// The narrowest certified bracket found for each `(a, b)`, in the same order, on
/// verify's private pool under the same `policy` (a pool that cannot be built is
/// announced on `stderr` and the work runs serially). The outer `Err` is a failed
/// write to `stderr`; the inner one a Z fault or a worker panic.
pub fn refine_intervals<Z: ZSource + Sync, E: Write>(
    z: &Z,
    cfg: &VerifyConfig,
    intervals: &[(f64, f64)],
    policy: PoolPolicy,
    stderr: &mut E,
) -> io::Result<Result<Vec<(f64, f64)>, Fault>> {
    let runner = Runner::new(policy, stderr)?;
    Ok(runner.try_map(intervals.len(), |i| {
        let (a, b) = intervals[i];
        refine_one(a, b, |t| certified_sign_ladder(cfg, |prec| z.z(t, prec))).map_err(Fault::Z)
    }))
}

/// The midpoint of a bracket: the zero's estimate `t_n`.
pub fn midpoint(a: f64, b: f64) -> f64 {
    a + (b - a) / 2.0
}

/// delta_n = (t_{n+1} - t_n) * ln(t_n / 2 pi) / 2 pi for every consecutive pair.
pub fn normalised_spacings(t: &[f64]) -> Vec<f64> {
    t.windows(2).map(|w| (w[1] - w[0]) * (w[0] / TAU).ln() / TAU).collect()
}

/// erf by Abramowitz and Stegun 7.1.26: absolute error at most 1.5e-7, far below the
/// resolution a KS distance over a few hundred spacings needs.
pub fn erf(x: f64) -> f64 {
    const P: f64 = 0.327_591_1;
    const A: [f64; 5] =
        [0.254_829_592, -0.284_496_736, 1.421_413_741, -1.453_152_027, 1.061_405_429];
    let ax = x.abs();
    let t = 1.0 / (1.0 + P * ax);
    let poly = A.iter().rev().fold(0.0, |acc, &c| (acc + c) * t);
    (1.0 - poly * (-ax * ax).exp()).copysign(x)
}

/// The Wigner surmise p(s) = (32 / pi^2) s^2 exp(-4 s^2 / pi).
pub fn wigner_pdf(s: f64) -> f64 {
    32.0 / (PI * PI) * s * s * (-4.0 * s * s / PI).exp()
}

/// Its CDF F(s) = erf(sqrt(a) s) - (2 / sqrt(pi)) sqrt(a) s exp(-a s^2), a = 4 / pi.
pub fn wigner_cdf(s: f64) -> f64 {
    if s <= 0.0 {
        return 0.0;
    }
    let a = 4.0 / PI;
    let x = a.sqrt() * s;
    erf(x) - 2.0 / PI.sqrt() * x * (-a * s * s).exp()
}

/// The bin of `s` in [0, 3] (3 itself belongs to the last bin); `None` outside.
pub fn bin_index(s: f64) -> Option<usize> {
    if !(0.0..=S_MAX).contains(&s) {
        return None;
    }
    Some(((s / BIN_WIDTH) as usize).min(BIN_COUNT - 1))
}

/// Counts per bin; spacings outside [0, 3] are not counted.
pub fn histogram(deltas: &[f64]) -> [usize; BIN_COUNT] {
    let mut counts = [0; BIN_COUNT];
    for &s in deltas {
        if let Some(i) = bin_index(s) {
            counts[i] += 1;
        }
    }
    counts
}

/// The Kolmogorov-Smirnov distance between the sample and the surmise's CDF;
/// `None` for an empty sample.
pub fn ks_distance(deltas: &[f64]) -> Option<f64> {
    if deltas.is_empty() {
        return None;
    }
    let mut sorted = deltas.to_vec();
    sorted.sort_by(f64::total_cmp);
    let n = sorted.len() as f64;
    let distance = sorted.iter().enumerate().fold(0.0_f64, |worst, (i, &s)| {
        let f = wigner_cdf(s);
        worst.max((i as f64 + 1.0) / n - f).max(f - i as f64 / n)
    });
    Some(distance)
}

/// A width to 3 significant digits, rounded up so the column never understates it,
/// in the `{:.2e}` shape (`1.24e-3`).
pub fn width_text(w: f64) -> String {
    let (_, digits, exp) = Float::with_val(120, w).to_sign_string_exp_round(10, Some(3), Round::Up);
    let Some(exp) = exp else {
        return "0.00e0".to_string();
    };
    format!("{}.{}e{}", &digits[..1], &digits[1..], exp - 1)
}

/// The spacing report for refined brackets: the histogram beside the surmise, the KS
/// distance and the largest w_n, with the interpretation notes.
pub fn write_report<W: Write>(out: &mut W, refined: &[(f64, f64)]) -> io::Result<()> {
    let t: Vec<f64> = refined.iter().map(|&(a, b)| midpoint(a, b)).collect();
    let deltas = normalised_spacings(&t);
    let total = deltas.len();
    writeln!(out)?;
    writeln!(
        out,
        "Spacing histogram: delta_n = (t_(n+1) - t_n) ln(t_n / 2 pi) / 2 pi, {total} spacings"
    )?;
    writeln!(out, "  {:<11}{:>7}{:>10}{:>14}", "s", "count", "observed", "Wigner p(s)")?;
    for (i, count) in histogram(&deltas).into_iter().enumerate() {
        let lo = i as f64 * BIN_WIDTH;
        let observed = if total == 0 { 0.0 } else { count as f64 / (total as f64 * BIN_WIDTH) };
        let surmise = wigner_pdf(lo + BIN_WIDTH / 2.0);
        writeln!(
            out,
            "  {:<11}{count:>7}{observed:>10.4}{surmise:>14.4}",
            format!("{lo:.2}-{:.2}", lo + BIN_WIDTH)
        )?;
    }
    match ks_distance(&deltas) {
        Some(d) => writeln!(out, "KS distance to the Wigner surmise CDF: {d:.4}")?,
        None => writeln!(out, "KS distance to the Wigner surmise CDF: n/a")?,
    }
    let widest = refined.iter().map(|&(a, b)| b - a).reduce(f64::max);
    match widest {
        Some(w) => writeln!(out, "Largest w_n: {}", width_text(w))?,
        None => writeln!(out, "Largest w_n: n/a")?,
    }
    writeln!(out, "The Wigner surmise approximates the exact GUE spacing law to within about 1%;")?;
    writeln!(out, "independent random points (Poisson) would instead peak at s = 0.")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::interval::Interval;
    use std::cell::{Cell, RefCell};

    fn pos() -> Sign {
        Sign::Positive
    }
    fn neg() -> Sign {
        Sign::Negative
    }

    /// Sign of a step function: negative below `z0`, positive from it.
    fn step(z0: f64) -> impl Fn(f64) -> Result<Option<Sign>, ZFault> {
        move |t| Ok(Some(if t < z0 { neg() } else { pos() }))
    }

    fn next_up(x: f64) -> f64 {
        f64::from_bits(x.to_bits() + 1)
    }

    // ---- bisect ----

    #[test]
    fn bisect_narrows_to_adjacent_floats_around_the_sign_change() {
        let z0 = std::f64::consts::PI * 10.0;
        let (a, b) = bisect(30.0, 33.0, neg(), step(z0)).unwrap();
        assert!(a < z0 && z0 <= b, "({a}, {b})");
        assert_eq!(b, next_up(a));
    }

    #[test]
    fn bisect_handles_a_positive_to_negative_change() {
        let z0 = 31.4;
        let flipped = |t: f64| Ok(Some(if t < z0 { pos() } else { neg() }));
        let (a, b) = bisect(30.0, 33.0, pos(), flipped).unwrap();
        assert!(a < z0 && z0 <= b);
        assert_eq!(b, next_up(a));
    }

    #[test]
    fn bisect_stops_when_the_midpoint_and_all_nearby_tries_are_uncertain() {
        let calls = Cell::new(0);
        let r = bisect(100.0, 101.0, neg(), |_| {
            calls.set(calls.get() + 1);
            Ok(None)
        })
        .unwrap();
        assert_eq!(r, (100.0, 101.0));
        assert_eq!(calls.get(), 1 + NEARBY_TRIES);
    }

    #[test]
    fn bisect_uses_a_nearby_point_when_only_the_midpoint_is_uncertain() {
        let z0 = 100.3;
        let r = bisect(100.0, 101.0, neg(), |t| if t == 100.5 { Ok(None) } else { step(z0)(t) })
            .unwrap();
        assert!(r.1 - r.0 < 1e-3, "{r:?}");
        assert!(r.0 < z0 && z0 <= r.1);
    }

    #[test]
    fn bisect_stops_when_the_certified_region_ends_mid_way() {
        // Only points within 0.01 of the zero certify; the rest are uncertain.
        let z0 = 100.3;
        let sign = |t: f64| if (t - z0).abs() < 0.01 { step(z0)(t) } else { Ok(None) };
        let r = bisect(100.0, 101.0, neg(), sign).unwrap();
        assert_eq!(r, (100.0, 101.0));
    }

    #[test]
    fn bisect_makes_no_call_when_no_float_lies_between() {
        let a = 100.0;
        let b = next_up(a);
        let r = bisect(a, b, neg(), |_| panic!("no point is strictly inside")).unwrap();
        assert_eq!(r, (a, b));
    }

    #[test]
    fn bisect_propagates_a_fault_and_stops() {
        let calls = Cell::new(0);
        let r = bisect(100.0, 101.0, neg(), |_| {
            calls.set(calls.get() + 1);
            Err(ZFault::NanHeight)
        });
        assert!(matches!(r, Err(ZFault::NanHeight)));
        assert_eq!(calls.get(), 1);
    }

    #[test]
    fn bisect_keeps_a_certified_sign_change_at_every_step() {
        let z0 = 100.123_456;
        let seen = RefCell::new(Vec::new());
        let r = bisect(100.0, 101.0, neg(), |t| {
            let s = step(z0)(t);
            seen.borrow_mut().push(t);
            s
        })
        .unwrap();
        assert!(seen.borrow().iter().all(|&t| t > 100.0 && t < 101.0));
        assert!(step(z0)(r.0).unwrap() == Some(neg()) && step(z0)(r.1).unwrap() == Some(pos()));
    }

    #[test]
    fn bisect_bounded_stops_after_max_steps_with_a_certified_bracket() {
        let z0 = 100.3;
        let calls = Cell::new(0);
        let r = bisect_bounded(
            100.0,
            101.0,
            neg(),
            |t| {
                calls.set(calls.get() + 1);
                step(z0)(t)
            },
            3,
        )
        .unwrap();
        // The midpoint certifies at once, so each step costs one call and halves the width.
        assert_eq!(calls.get(), 3);
        assert_eq!(r.1 - r.0, 0.125);
        assert!(step(z0)(r.0).unwrap() == Some(neg()) && step(z0)(r.1).unwrap() == Some(pos()));
        assert_eq!(bisect_bounded(100.0, 101.0, neg(), step(z0), 0).unwrap(), (100.0, 101.0));
    }

    #[test]
    fn the_worst_case_adversary_stays_under_the_step_bound() {
        // Certifies only the candidate farthest below the midpoint and always moves `a`
        // up to it: each step keeps 3/4 of the width, the slowest shrink there is.
        let (lo, hi) = (Cell::new(1.0e3), Cell::new(1.0e3 + 1.0));
        let steps = Cell::new(0);
        let r = bisect(lo.get(), hi.get(), neg(), |t| {
            let last = *candidates(lo.get(), hi.get(), &NEARBY_SHIFTS).last().unwrap();
            if t == last {
                steps.set(steps.get() + 1);
                lo.set(t);
                Ok(Some(neg()))
            } else {
                Ok(None)
            }
        })
        .unwrap();
        assert!(steps.get() > 90 && steps.get() <= MAX_BISECT_STEPS, "{}", steps.get());
        assert_eq!(r, (lo.get(), hi.get()));
        assert_eq!(r.1, 1.0e3 + 1.0);
    }

    // ---- refine_one / refine_intervals ----

    #[test]
    fn refine_one_leaves_a_bracket_whose_ends_do_not_both_certify() {
        let z0 = 100.3;
        assert_eq!(
            refine_one(100.0, 101.0, |t| if t == 100.0 { Ok(None) } else { step(z0)(t) }).unwrap(),
            (100.0, 101.0)
        );
        assert_eq!(
            refine_one(100.0, 101.0, |t| if t == 101.0 { Ok(None) } else { step(z0)(t) }).unwrap(),
            (100.0, 101.0)
        );
    }

    #[test]
    fn refine_one_leaves_a_bracket_whose_ends_share_a_sign() {
        let r = refine_one(100.0, 101.0, |_| Ok(Some(pos()))).unwrap();
        assert_eq!(r, (100.0, 101.0));
    }

    #[test]
    fn refine_one_refines_a_good_bracket_and_propagates_end_faults() {
        let r = refine_one(100.0, 101.0, step(100.3)).unwrap();
        assert!(r.1 - r.0 < 1e-12);
        assert!(refine_one(100.0, 101.0, |_| Err(ZFault::NanHeight)).is_err());
        let fault_at_b = |t: f64| if t == 101.0 { Err(ZFault::NanHeight) } else { step(100.3)(t) };
        assert!(refine_one(100.0, 101.0, fault_at_b).is_err());
    }

    /// A Z that is negative below `z0` and positive from it, as a point enclosure.
    struct StepZ(f64);

    impl ZSource for StepZ {
        fn z(&self, t: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
            if t.is_nan() {
                return Err(ZFault::NanHeight);
            }
            Ok(Some(Interval::point(if t < self.0 { -1.0 } else { 1.0 }, prec)))
        }

        fn z_over(&self, _lo: f64, _hi: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
            Ok(None)
        }
    }

    fn refine(z: &StepZ, ivs: &[(f64, f64)], policy: PoolPolicy) -> Result<Vec<(f64, f64)>, Fault> {
        refine_intervals(z, &VerifyConfig::default(), ivs, policy, &mut Vec::new()).unwrap()
    }

    #[test]
    fn refine_intervals_narrows_every_bracket_in_order() {
        let z = StepZ(100.3);
        let ivs = [(100.0, 101.0), (100.1, 100.4), (90.0, 91.0)];
        let out = refine(&z, &ivs, PoolPolicy::Serial).unwrap();
        assert_eq!(out.len(), 3);
        assert!(out[0].1 - out[0].0 < 1e-12 && out[0].0 < 100.3 && 100.3 <= out[0].1);
        assert!(out[1].1 - out[1].0 < 1e-12);
        assert_eq!(out[2], (90.0, 91.0), "same signs at both ends: unchanged");
        assert!(refine(&z, &[], PoolPolicy::Serial).unwrap().is_empty());
    }

    #[test]
    fn refine_intervals_is_identical_serial_and_on_a_pool() {
        let z = StepZ(100.3);
        let ivs: Vec<(f64, f64)> =
            (0..40).map(|i| (100.0 + i as f64 * 0.001, 100.5 + i as f64 * 0.01)).collect();
        let serial = refine(&z, &ivs, PoolPolicy::Serial).unwrap();
        for policy in [PoolPolicy::Threads(3), PoolPolicy::Parallel] {
            assert_eq!(refine(&z, &ivs, policy).unwrap(), serial, "{policy:?}");
        }
    }

    #[test]
    fn refine_intervals_reports_a_z_fault_serial_and_parallel() {
        let z = StepZ(100.3);
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            let r = refine(&z, &[(f64::NAN, 101.0)], policy);
            assert_eq!(r, Err(Fault::Z(ZFault::NanHeight)), "{policy:?}");
        }
    }

    /// A Z that panics.
    struct PanicZ;

    impl ZSource for PanicZ {
        fn z(&self, _: f64, _: u32) -> Result<Option<Interval>, ZFault> {
            panic!("boom")
        }

        fn z_over(&self, _: f64, _: f64, _: u32) -> Result<Option<Interval>, ZFault> {
            Ok(None)
        }
    }

    #[test]
    fn a_worker_panic_during_refinement_is_a_fault() {
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            let r = refine_intervals(
                &PanicZ,
                &VerifyConfig::default(),
                &[(100.0, 101.0)],
                policy,
                &mut Vec::new(),
            )
            .unwrap();
            assert_eq!(r, Err(Fault::WorkerPanicked), "{policy:?}");
        }
    }

    #[test]
    fn an_unbuildable_pool_falls_back_to_serial_with_a_message() {
        let mut err = Vec::new();
        let z = StepZ(100.3);
        let r = refine_intervals(
            &z,
            &VerifyConfig::default(),
            &[(100.0, 101.0)],
            PoolPolicy::FailBuild,
            &mut err,
        )
        .unwrap()
        .unwrap();
        assert_eq!(r.len(), 1);
        let msg = String::from_utf8(err).unwrap();
        assert!(msg.starts_with("Parallel mode unavailable ("), "{msg}");
        assert!(msg.ends_with("); falling back to serial.\n"), "{msg}");
    }

    #[test]
    fn a_failing_stderr_surfaces_from_the_fallback_message() {
        struct Failing;
        impl Write for Failing {
            fn write(&mut self, _: &[u8]) -> io::Result<usize> {
                Err(io::Error::other("closed"))
            }
            fn flush(&mut self) -> io::Result<()> {
                Ok(())
            }
        }
        let z = StepZ(100.3);
        let r = refine_intervals(
            &z,
            &VerifyConfig::default(),
            &[],
            PoolPolicy::FailBuild,
            &mut Failing,
        );
        assert!(r.is_err());
    }

    // ---- statistics ----

    #[test]
    fn midpoint_and_width_text() {
        assert_eq!(midpoint(14.0, 15.0), 14.5);
        assert_eq!(midpoint(1e308, 1.7e308), 1e308 + (1.7e308 - 1e308) / 2.0);
        assert_eq!(width_text(0.001_234_5), "1.24e-3", "rounds up, not to nearest");
        assert_eq!(width_text(0.001_231), "1.24e-3");
        assert_eq!(width_text(0.001_23), "1.23e-3");
        assert_eq!(width_text(0.5), "5.00e-1");
        assert_eq!(width_text(0.0), "0.00e0");
        assert_eq!(width_text(9.991), "1.00e1");
        assert_eq!(width_text(12345.0), "1.24e4");
        assert_eq!(width_text(2.0), "2.00e0");
    }

    #[test]
    fn spacings_are_normalised_by_the_local_density() {
        let t = [14.0, 15.0, 17.0];
        let d = normalised_spacings(&t);
        assert_eq!(d.len(), 2);
        assert_eq!(d[0], (15.0 - 14.0) * (14.0 / TAU).ln() / TAU);
        assert_eq!(d[1], (17.0 - 15.0) * (15.0 / TAU).ln() / TAU);
        assert!(normalised_spacings(&[14.0]).is_empty());
        assert!(normalised_spacings(&[]).is_empty());
    }

    #[test]
    fn erf_matches_known_values_within_the_documented_bound() {
        for (x, want) in [
            (0.0, 0.0),
            (0.5, 0.520_499_877_8),
            (1.0, 0.842_700_792_9),
            (2.0, 0.995_322_265_0),
            (3.0, 0.999_977_909_5),
        ] {
            assert!((erf(x) - want).abs() < 1.5e-7, "erf({x}) = {}", erf(x));
            assert!((erf(-x) + want).abs() < 1.5e-7);
        }
        assert!((erf(10.0) - 1.0).abs() < 1e-9);
    }

    /// Composite Simpson's rule on [0, s].
    fn integrate_pdf(s: f64) -> f64 {
        let n = 2000;
        let h = s / n as f64;
        let mut sum = wigner_pdf(0.0) + wigner_pdf(s);
        for i in 1..n {
            sum += wigner_pdf(i as f64 * h) * if i % 2 == 1 { 4.0 } else { 2.0 };
        }
        sum * h / 3.0
    }

    #[test]
    fn the_cdf_matches_the_integrated_pdf_at_five_points() {
        for s in [0.3, 0.8, 1.2, 2.0, 3.0] {
            assert!((wigner_cdf(s) - integrate_pdf(s)).abs() < 1e-6, "s = {s}");
        }
    }

    #[test]
    fn the_cdf_runs_from_0_to_1() {
        assert_eq!(wigner_cdf(0.0), 0.0);
        assert_eq!(wigner_cdf(-1.0), 0.0);
        assert!((wigner_cdf(100.0) - 1.0).abs() < 1e-9);
        assert!(wigner_cdf(0.5) < wigner_cdf(1.0));
    }

    #[test]
    fn the_pdf_vanishes_at_zero_and_peaks_near_the_surmise_mode() {
        assert_eq!(wigner_pdf(0.0), 0.0);
        // The mode is at s = sqrt(pi) / 2.
        let mode = PI.sqrt() / 2.0;
        assert!(wigner_pdf(mode) > wigner_pdf(mode - 0.1));
        assert!(wigner_pdf(mode) > wigner_pdf(mode + 0.1));
    }

    #[test]
    fn bin_index_edges() {
        assert_eq!(bin_index(0.0), Some(0));
        assert_eq!(bin_index(0.149), Some(0));
        assert_eq!(bin_index(0.15), Some(1));
        assert_eq!(bin_index(2.99), Some(19));
        assert_eq!(bin_index(3.0), Some(19));
        assert_eq!(bin_index(3.000_001), None);
        assert_eq!(bin_index(-0.000_001), None);
        assert_eq!(bin_index(f64::NAN), None);
        assert_eq!(bin_index(f64::INFINITY), None);
    }

    #[test]
    fn histogram_counts_each_spacing_once_and_drops_the_outside() {
        let h = histogram(&[0.0, 0.15, 0.16, 2.99, 3.0, 3.5, -1.0]);
        assert_eq!(h[0], 1);
        assert_eq!(h[1], 2);
        assert_eq!(h[19], 2);
        assert_eq!(h.iter().sum::<usize>(), 5);
        assert_eq!(histogram(&[]), [0; BIN_COUNT]);
    }

    #[test]
    fn ks_distance_on_tiny_known_samples() {
        assert_eq!(ks_distance(&[]), None);
        // One point at s = 0: F = 0, the empirical CDF jumps to 1.
        assert_eq!(ks_distance(&[0.0]), Some(1.0));
        // One far point: F = 1, the empirical CDF is 0 just before it.
        let d = ks_distance(&[100.0]).unwrap();
        assert!((d - 1.0).abs() < 1e-9, "{d}");
        // Half the mass at 0, half far out: 0.5, whatever the input order.
        for sample in [[0.0, 100.0], [100.0, 0.0]] {
            let d = ks_distance(&sample).unwrap();
            assert!((d - 0.5).abs() < 1e-8, "{d}");
        }
    }

    #[test]
    fn ks_distance_sees_the_upper_side_of_a_late_jump() {
        // F jumps from 0 to 1 at the second point: 1 - 1/3 = 2/3 beats every other term.
        let d = ks_distance(&[0.0, 100.0, 100.0]).unwrap();
        assert!((d - 2.0 / 3.0).abs() < 1e-8, "{d}");
    }

    #[test]
    fn ks_distance_reads_both_sides_of_each_step() {
        // F(lo) = 0.5, F(100) ~ 1: the largest gap is 0.5, both below the first point and just after it.
        let (mut lo, mut hi) = (0.1, 3.0);
        for _ in 0..60 {
            let mid = (lo + hi) / 2.0;
            if wigner_cdf(mid) < 0.5 { lo = mid } else { hi = mid }
        }
        let d = ks_distance(&[lo]).unwrap();
        assert!((d - 0.5).abs() < 1e-6, "{d}");
        let d = ks_distance(&[lo, 100.0]).unwrap();
        assert!((d - 0.5).abs() < 1e-6, "{d}");
    }

    // ---- report ----

    fn report_text(refined: &[(f64, f64)]) -> String {
        let mut out = Vec::new();
        write_report(&mut out, refined).unwrap();
        String::from_utf8(out).unwrap()
    }

    #[test]
    fn report_has_a_row_per_bin_the_ks_distance_the_largest_width_and_the_notes() {
        let refined = [(14.0, 14.001), (15.0, 15.002), (17.0, 17.0005), (20.0, 20.001)];
        let text = report_text(&refined);
        let lines: Vec<&str> = text.lines().collect();
        assert_eq!(lines[0], "");
        assert!(lines[1].starts_with("Spacing histogram: delta_n = "), "{text}");
        assert!(lines[1].ends_with(", 3 spacings"), "{text}");
        assert_eq!(lines[2], "  s            count  observed   Wigner p(s)");
        assert!(lines[3].starts_with("  0.00-0.15  "), "{text}");
        assert!(lines[3].ends_with("      1    2.2222        0.0181"), "{lines:?}");
        assert!(lines[4].ends_with("0.1539"), "{lines:?}");
        assert!(lines[8].ends_with("0.9277"), "{lines:?}");
        assert!(lines[22].starts_with("  2.85-3.00  "), "{text}");
        assert!(lines[23].starts_with("KS distance to the Wigner surmise CDF: 0."), "{text}");
        assert_eq!(lines[24], "Largest w_n: 2.01e-3");
        assert_eq!(
            lines[25],
            "The Wigner surmise approximates the exact GUE spacing law to within about 1%;"
        );
        assert_eq!(lines[26], "independent random points (Poisson) would instead peak at s = 0.");
        assert_eq!(lines.len(), 27);
    }

    #[test]
    fn report_for_an_empty_or_single_table_says_not_available() {
        let none = report_text(&[]);
        assert!(none.contains("0 spacings"), "{none}");
        assert!(none.contains("KS distance to the Wigner surmise CDF: n/a"), "{none}");
        assert!(none.contains("Largest w_n: n/a"), "{none}");
        let one = report_text(&[(14.0, 14.5)]);
        assert!(one.contains("CDF: n/a") && one.contains("Largest w_n: 5.00e-1"), "{one}");
    }

    #[test]
    fn report_observed_density_is_the_count_over_total_and_bin_width() {
        // Two spacings, both in bin 0 or near: build t so delta is tiny.
        let refined = [(100.0, 100.0), (100.01, 100.01), (100.02, 100.02)];
        let text = report_text(&refined);
        let row = text.lines().find(|l| l.starts_with("  0.00-0.15")).unwrap();
        assert!(row.contains("      2    6.6667"), "{row}");
    }

    #[test]
    fn report_write_errors_surface() {
        struct Failing;
        impl Write for Failing {
            fn write(&mut self, _: &[u8]) -> io::Result<usize> {
                Err(io::Error::other("closed"))
            }
            fn flush(&mut self) -> io::Result<()> {
                Ok(())
            }
        }
        assert!(write_report(&mut Failing, &[(14.0, 15.0)]).is_err());
    }
}
