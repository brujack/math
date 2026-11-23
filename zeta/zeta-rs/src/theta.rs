//! Certified enclosure of the Riemann-Siegel theta function.
//!
//! theta(t) = Im Ln Gamma(1/4 + it/2) - (t/2) ln(pi). Ln Gamma comes from the
//! Stirling series (DLMF 5.11.1) with its error bound (DLMF 5.11(ii)), applied
//! at z + SHIFT and moved back by the recurrence
//! Ln Gamma(z) = Ln Gamma(z + m) - sum_{k<m} Ln(z + k), exact for Re z > 0.
//! The shift keeps |w| >= 10.25, where the series is accurate to about 3.4e-22
//! at 2*pi and far better above it; the accuracy floor is therefore about
//! 3.4e-22 at t = 2*pi however many bits are requested.

use crate::complex::Complex;
use crate::interval::{Interval, IntervalError, Sign};
use rug::Float;
use rug::float::Round;

/// Largest accepted precision; beyond this a request is a mistake, not a need.
pub const MAX_PREC: u32 = 1 << 16;

/// Shift m of the recurrence: the series is evaluated at z + SHIFT.
const SHIFT: u32 = 10;

/// Series order n: terms k = 1..n-1 are summed and B_2n enters the remainder.
/// At t = 2*pi (|w| = 10.72) the remainder bound 2^n |B_2n| / (2n(2n-1)|w|^(2n-1))
/// is smallest near n = 25, where it is 3.4e-22; it only falls as t grows.
const SERIES_ORDER: usize = 25;

/// B_2, B_4, ..., B_50 as exact (numerator, denominator) pairs in lowest terms.
pub(crate) const BERNOULLI: [(i128, u32); SERIES_ORDER] = [
    (1, 6),
    (-1, 30),
    (1, 42),
    (-1, 30),
    (5, 66),
    (-691, 2730),
    (7, 6),
    (-3617, 510),
    (43867, 798),
    (-174611, 330),
    (854513, 138),
    (-236364091, 2730),
    (8553103, 6),
    (-23749461029, 870),
    (8615841276005, 14322),
    (-7709321041217, 510),
    (2577687858367, 6),
    (-26315271553053477373, 1919190),
    (2929993913841559, 6),
    (-261082718496449122051, 13530),
    (1520097643918070802691, 1806),
    (-27833269579301024235023, 690),
    (596451111593912163277961, 282),
    (-5609403368997817686249127547, 46410),
    (495057205241079648212477525, 66),
];

/// Why a theta enclosure could not be produced.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ThetaError {
    /// The height was zero, negative, NaN or infinite.
    HeightNotPositive,
    /// The precision lies outside the MPFR range.
    PrecisionOutOfRange,
    /// An interval operation refused its operands.
    Interval(IntervalError),
}

impl std::fmt::Display for ThetaError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::HeightNotPositive => f.write_str("height is not a positive finite number"),
            Self::PrecisionOutOfRange => f.write_str("precision outside the MPFR range"),
            Self::Interval(e) => write!(f, "interval arithmetic failed: {e}"),
        }
    }
}

impl std::error::Error for ThetaError {}

impl From<IntervalError> for ThetaError {
    fn from(e: IntervalError) -> Self {
        Self::Interval(e)
    }
}

/// Interval enclosing pi.
pub(crate) fn pi_interval(prec: u32) -> Result<Interval, ThetaError> {
    let round = |r| Float::with_val_round(prec, rug::float::Constant::Pi, r).0;
    Ok(Interval::new(round(Round::Down), round(Round::Up))?)
}

/// Interval enclosing the integer `v`.
fn integer_interval(v: i128, prec: u32) -> Result<Interval, ThetaError> {
    let round = |r| Float::with_val_round(prec, v, r).0;
    Ok(Interval::new(round(Round::Down), round(Round::Up))?)
}

/// B_2k / (2k (2k - 1)) for k = 1..=SERIES_ORDER, as an interval.
fn series_coefficient(k: usize, prec: u32) -> Result<Interval, ThetaError> {
    let (num, den) = BERNOULLI[k - 1];
    let divisor = integer_interval(i128::from(den) * (2 * k as i128) * (2 * k as i128 - 1), prec)?;
    Ok(integer_interval(num, prec)?.div(&divisor)?)
}

fn validate_height(t: f64) -> Result<(), ThetaError> {
    if t.is_finite() && t > 0.0 { Ok(()) } else { Err(ThetaError::HeightNotPositive) }
}

/// Everything about theta that depends on the precision only: build it once and
/// evaluate many heights. It holds no caches that change after construction, so a
/// shared reference may be used from several threads.
#[derive(Debug, Clone)]
pub struct ThetaContext {
    prec: u32,
    half: Interval,
    /// Re(z + SHIFT) = 10.25.
    shifted_re: Interval,
    /// 0.25 + k for k = 0..SHIFT, the real parts of z + k (the atan arguments).
    recurrence_re: Vec<Interval>,
    /// B_2k / (2k (2k - 1)) for k = 1..SERIES_ORDER.
    coefficients: Vec<Interval>,
    /// 2^n |B_2n| / (2n (2n - 1)), the numerator of the remainder bound.
    remainder_scale: Interval,
    ln_pi: Interval,
}

impl ThetaContext {
    /// Precompute the t-independent constants at `prec` bits; a precision outside
    /// `prec_min()..=MAX_PREC` gives `PrecisionOutOfRange`.
    pub fn new(prec: u32) -> Result<ThetaContext, ThetaError> {
        if !(rug::float::prec_min()..=MAX_PREC).contains(&prec) {
            return Err(ThetaError::PrecisionOutOfRange);
        }
        let n = SERIES_ORDER;
        let mut coefficients = Vec::with_capacity(n - 1);
        for k in 1..n {
            coefficients.push(series_coefficient(k, prec)?);
        }
        let (num, den) = BERNOULLI[n - 1];
        let denominator = i128::from(den) * (2 * n as i128) * (2 * n as i128 - 1);
        let remainder_scale = integer_interval(num.abs(), prec)?
            .mul(&integer_interval(1i128 << n, prec)?)
            .div(&integer_interval(denominator, prec)?)?;
        Ok(ThetaContext {
            prec,
            half: Interval::point(0.5, prec),
            shifted_re: Interval::point(f64::from(SHIFT) + 0.25, prec),
            recurrence_re: (0..SHIFT).map(|k| Interval::point(f64::from(k) + 0.25, prec)).collect(),
            coefficients,
            remainder_scale,
            ln_pi: pi_interval(prec)?.ln()?,
        })
    }

    /// Upper bound of the Stirling remainder 2^n |B_2n| / (2n(2n-1) |w|^(2n-1)),
    /// given an enclosure of q^(2n-1) where q = |w|^2. |w|^(2n-1) = sqrt(q^(2n-1)),
    /// rounded down in its lower end, and the quotient's upper end is the bound.
    fn remainder_bound(&self, q_odd_power: &Interval) -> Result<Float, ThetaError> {
        let modulus_power = q_odd_power.sqrt()?;
        Ok(self.remainder_scale.div(&modulus_power)?.hi().clone())
    }

    /// Im Ln Gamma(w) for w = shifted_re + iy: the Stirling series with remainder.
    fn im_ln_gamma_stirling(&self, y: &Interval) -> Result<Interval, ThetaError> {
        let x = &self.shifted_re;
        let q = x.mul(x).add(&y.mul(y));
        let ln_modulus = q.ln()?.mul(&self.half);
        // Im[(w - 1/2) Ln w - w]
        let lead = x.sub(&self.half).mul(&y.div(x)?.atan()).add(&y.mul(&ln_modulus)).sub(y);
        // conj(w)^j / |w|^(2j) for j = 1, 3, 5, ...
        let zero = Interval::point(0.0, self.prec);
        let conj = Complex::new(x.clone(), zero.sub(y));
        let step = conj.mul(&conj);
        let q_step = q.mul(&q);
        let mut power = conj;
        let mut q_power = q;
        let mut series = zero;
        for coefficient in &self.coefficients {
            let term = power.im.div(&q_power)?.mul(coefficient);
            series = series.add(&term);
            power = power.mul(&step);
            q_power = q_power.mul(&q_step);
        }
        // After the loop q_power = q^(2n-1).
        let remainder = self.remainder_bound(&q_power)?;
        Ok(lead.add(&series).widen(&remainder))
    }

    /// Certified enclosure of theta(t).
    ///
    /// `t` is taken as the exact binary value of the f64. Heights that are zero,
    /// negative or not finite give `HeightNotPositive`. The result is valid for
    /// every t > 0 but is meant for t >= 2*pi.
    pub fn theta(&self, t: f64) -> Result<Interval, ThetaError> {
        validate_height(t)?;
        // t * 0.5 is exact in MPFR, unlike t / 2.0 on f64 subnormals.
        let y = Interval::point(t, self.prec).mul(&self.half);
        let mut value = self.im_ln_gamma_stirling(&y)?;
        for xk in &self.recurrence_re {
            value = value.sub(&y.div(xk)?.atan());
        }
        Ok(value.sub(&y.mul(&self.ln_pi)))
    }
}

/// Certified enclosure of theta(t) at `prec` bits: a context built for one call.
/// Use `ThetaContext` to evaluate many heights at one precision.
///
/// Heights that are zero, negative or not finite give `HeightNotPositive`; a
/// precision outside `prec_min()..=MAX_PREC` gives `PrecisionOutOfRange`.
pub fn theta(t: f64, prec: u32) -> Result<Interval, ThetaError> {
    validate_height(t)?;
    ThetaContext::new(prec)?.theta(t)
}

/// Certification precisions tried in order: 64, 128, 256, then `cap` itself.
/// Rungs at or above the cap are dropped so the cap is the last precision used.
fn precision_ladder(cap: u32) -> Vec<u32> {
    let mut ladder: Vec<u32> = [64, 128, 256].into_iter().filter(|&p| p < cap).collect();
    ladder.push(cap);
    ladder
}

/// Number of doubling steps, in units of one f64 ulp, searched on each side
/// of the estimate: the farthest endpoint is 2^(RUNGS-1) ulps away.
const RUNGS: u32 = 40;

/// Newton steps on the closed-form asymptotic theta and on the real enclosure.
const ASYMPTOTIC_STEPS: usize = 40;
const EXACT_STEPS: usize = 4;

/// Precision of the f64 estimate's theta evaluations.
const ESTIMATE_PREC: u32 = 64;

/// Brent's asymptotic form of theta for t >= 10 (error below 1e-9 at 14).
fn asymptotic_theta(t: f64) -> f64 {
    let t2 = t * t;
    0.5 * t * (t / std::f64::consts::TAU).ln() - 0.5 * t - std::f64::consts::PI / 8.0
        + 1.0 / (48.0 * t)
        + 7.0 / (5760.0 * t2 * t)
        + 31.0 / (80640.0 * t2 * t2 * t)
}

/// d/dt of `asymptotic_theta`.
fn asymptotic_slope(t: f64) -> f64 {
    let t2 = t * t;
    0.5 * (t / std::f64::consts::TAU).ln()
        - 1.0 / (48.0 * t2)
        - 7.0 / (1920.0 * t2 * t2)
        - 31.0 / (16128.0 * t2 * t2 * t2)
}

fn midpoint_f64(i: &Interval) -> f64 {
    let sum = Float::with_val(i.prec(), i.lo() + i.hi());
    (sum / 2u32).to_f64()
}

/// A height right of g_n where the asymptotic theta exceeds n*pi: Newton
/// started there climbs down to the root monotonically.
fn asymptotic_start(n: i64) -> f64 {
    std::f64::consts::TAU * (n as f64 + 3.0)
}

/// Uncertified f64 estimate of the Gram point g_n (theta(g_n) = n*pi, n >= -1):
/// Newton on the asymptotic theta from the right of the root, where that
/// function is convex and increasing, then a few steps on the real theta. Only
/// the starting point of the certified search, so a poor value costs rungs, not
/// soundness.
fn estimate_gram_point<G>(n: i64, f: &G) -> Option<f64>
where
    G: Fn(f64) -> Result<Interval, ThetaError>,
{
    let target = n as f64 * std::f64::consts::PI;
    let mut t = asymptotic_start(n);
    for _ in 0..ASYMPTOTIC_STEPS {
        t -= (asymptotic_theta(t) - target) / asymptotic_slope(t);
    }
    for _ in 0..EXACT_STEPS {
        let mid = midpoint_f64(&f(t).ok()?);
        t -= (mid - target) / asymptotic_slope(t);
    }
    t.is_finite().then_some(t)
}

/// The first height 2^j ulps from `estimate` (j = 0, 1, ..., in the direction
/// of `want`: below for a negative theta - n*pi, above for a positive one) at
/// which `f - target` has a certified sign `want`. `None` when the search
/// leaves (2*pi, f64::MAX] or runs out of rungs.
fn certified_end<G>(f: &G, target: &Interval, estimate: f64, want: Sign) -> Option<f64>
where
    G: Fn(f64) -> Result<Interval, ThetaError>,
{
    let bits = estimate.to_bits();
    for j in 0..RUNGS {
        let step = 1u64 << j;
        let moved = match want {
            Sign::Negative => bits.checked_sub(step)?,
            Sign::Positive => bits.checked_add(step)?,
        };
        let t = f64::from_bits(moved);
        if !t.is_finite() || t <= std::f64::consts::TAU {
            return None;
        }
        if f(t).ok()?.sub(target).sign() == Some(want) {
            return Some(t);
        }
    }
    None
}

/// Bracket of g_n around `estimate` certified at exactly `prec` bits.
fn bracket_around<G>(n: i64, estimate: f64, prec: u32, f: &G) -> Option<(f64, f64)>
where
    G: Fn(f64) -> Result<Interval, ThetaError>,
{
    let target = integer_interval(i128::from(n), prec).ok()?.mul(&pi_interval(prec).ok()?);
    let left = certified_end(f, &target, estimate, Sign::Negative);
    let right = certified_end(f, &target, estimate, Sign::Positive);
    Some((left?, right?))
}

/// `bracket_around` over the precision ladder up to `cap`; `make(p)` builds the
/// theta evaluator for precision p once per rung.
fn bracket_with_estimate<M, G>(n: i64, cap: u32, estimate: f64, make: &M) -> Option<(f64, f64)>
where
    M: Fn(u32) -> Result<G, ThetaError>,
    G: Fn(f64) -> Result<Interval, ThetaError>,
{
    precision_ladder(cap).into_iter().find_map(|p| {
        let theta_at = make(p).ok()?;
        bracket_around(n, estimate, p, &theta_at)
    })
}

/// `gram_bracket` with an injectable theta evaluator factory.
fn bracket_with<M, G>(n: i64, cap: u32, make: &M) -> Option<(f64, f64)>
where
    M: Fn(u32) -> Result<G, ThetaError>,
    G: Fn(f64) -> Result<Interval, ThetaError>,
{
    if n < -1 || !(rug::float::prec_min()..=MAX_PREC).contains(&cap) {
        return None;
    }
    let estimate = estimate_gram_point(n, &make(ESTIMATE_PREC).ok()?)?;
    bracket_with_estimate(n, cap, estimate, make)
}

/// Certified bracket of the Gram point g_n, the t > 2*pi solution of
/// theta(t) = n*pi, for n >= -1.
///
/// Returns f64 heights 2*pi < b < c with theta(b) - n*pi certified negative and
/// theta(c) - n*pi certified positive. theta is not increasing on
/// (2*pi, about 6.2898), but it stays below -pi there (its minimum is about
/// -3.529), so for n >= -1 no solution lies on that stretch; beyond it theta is
/// increasing, hence g_n is unique and lies in (b, c). Precision rises 64, 128,
/// 256 up to `prec`; `None` when n < -1, `prec` is outside
/// `prec_min()..=MAX_PREC`, or nothing is certified within the cap.
pub fn gram_bracket(n: i64, prec: u32) -> Option<(f64, f64)> {
    bracket_with(n, prec, &|p| ThetaContext::new(p).map(|ctx| move |t| ctx.theta(t)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;
    use rug::{Float, Integer};

    const FIXTURE: &str = include_str!("../tests/fixtures/gram_points.txt");

    fn big(s: &str) -> Float {
        Float::with_val(256, Float::parse(s).unwrap())
    }

    /// The 30-digit reference is rounded, so allow it 1e-25 beyond the enclosure.
    fn agrees(i: &Interval, reference: &Float) -> bool {
        let slack = Float::with_val(64, 1e-25);
        let wide = i.widen(&slack);
        wide.lo() <= reference && reference <= wide.hi()
    }

    /// Exact fraction over rug integers, reduced, positive denominator.
    #[derive(Clone)]
    struct Frac {
        num: Integer,
        den: Integer,
    }

    impl Frac {
        fn new(num: Integer, den: Integer) -> Frac {
            let g = num.clone().gcd(&den);
            let (mut num, mut den) = (num / &g, den / &g);
            if den < 0 {
                num = -num;
                den = -den;
            }
            Frac { num, den }
        }
        fn sub(&self, o: &Frac) -> Frac {
            Frac::new(
                self.num.clone() * &o.den - o.num.clone() * &self.den,
                self.den.clone() * &o.den,
            )
        }
        fn mul_int(&self, k: u32) -> Frac {
            Frac::new(self.num.clone() * k, self.den.clone())
        }
    }

    /// Akiyama-Tanigawa: B_m with the B_1 = +1/2 convention.
    fn bernoulli_exact(m: u32) -> Frac {
        let mut a: Vec<Frac> = Vec::new();
        for mm in 0..=m {
            a.push(Frac::new(Integer::from(1), Integer::from(mm + 1)));
            for j in (1..=mm as usize).rev() {
                let d = a[j - 1].sub(&a[j]).mul_int(j as u32);
                a[j - 1] = d;
            }
        }
        a[0].clone()
    }

    // mpmath 1.4.1: mp.dps = 40; siegeltheta(mpf(t)) at 30 digits.
    const REFS: [(f64, &str); 5] = [
        (6.5, "-3.52923288473498754863348099386"),
        (9.667, "-3.14157286775215073842919447671"),
        (14.134725141734693, "-1.72867024667583821146658143813"),
        (100.0, "87.9721652317872196254831291137"),
        (1000.0, "2034.54642803803160870334515121"),
    ];

    #[test]
    fn stored_bernoulli_numbers_match_the_exact_generator() {
        assert_eq!(BERNOULLI.len(), SERIES_ORDER);
        for (k, &(num, den)) in BERNOULLI.iter().enumerate() {
            let want = bernoulli_exact(2 * (k as u32 + 1));
            let got = Frac::new(Integer::from(num), Integer::from(den));
            assert_eq!(got.num, want.num, "B_{} numerator", 2 * (k + 1));
            assert_eq!(got.den, want.den, "B_{} denominator", 2 * (k + 1));
        }
    }

    fn same_bits(a: &Interval, b: &Interval) -> bool {
        a.lo() == b.lo() && a.hi() == b.hi() && a.prec() == b.prec()
    }

    #[test]
    fn a_context_gives_exactly_the_one_shot_enclosures() {
        for p in [64, 128, 512] {
            let ctx = ThetaContext::new(p).unwrap();
            for t in [6.3, 9.667, 14.134725141734693, 100.0, 1000.0, 1.0e7] {
                let (a, b) = (ctx.theta(t).unwrap(), theta(t, p).unwrap());
                assert!(same_bits(&a, &b), "t={t} p={p}");
                // Reusing the context changes nothing.
                assert!(same_bits(&a, &ctx.theta(t).unwrap()), "t={t} p={p} reuse");
            }
        }
    }

    #[test]
    fn a_context_rejects_bad_precision_and_bad_heights() {
        for p in [0, MAX_PREC + 1, u32::MAX] {
            assert_eq!(ThetaContext::new(p).unwrap_err(), ThetaError::PrecisionOutOfRange);
        }
        assert!(ThetaContext::new(MAX_PREC).is_ok());
        let ctx = ThetaContext::new(64).unwrap();
        for t in [0.0, -1.0, f64::NAN, f64::INFINITY] {
            assert_eq!(ctx.theta(t).unwrap_err(), ThetaError::HeightNotPositive);
        }
        assert!(format!("{ctx:?}").starts_with("ThetaContext"));
    }

    #[test]
    fn the_one_shot_reports_a_bad_height_before_a_bad_precision() {
        assert_eq!(theta(-1.0, 0).unwrap_err(), ThetaError::HeightNotPositive);
        assert_eq!(theta(1.0, 0).unwrap_err(), ThetaError::PrecisionOutOfRange);
    }

    #[test]
    fn theta_encloses_mpmath_values() {
        for p in [64, 128, 512] {
            for (t, r) in REFS {
                let e = theta(t, p).unwrap();
                assert!(agrees(&e, &big(r)), "t={t} p={p} [{}, {}]", e.lo(), e.hi());
            }
        }
    }

    #[test]
    fn theta_is_narrow_at_the_smallest_heights() {
        for t in [9.667, std::f64::consts::TAU] {
            let w = theta(t, 128).unwrap().width();
            assert!(w < 1e-20, "t={t} width {w}");
        }
    }

    #[test]
    fn theta_width_includes_the_stirling_remainder() {
        // At t = 2*pi, 512 bits: the truncation bound (about 3.4e-22 each side)
        // dominates the rounding error.
        let w = theta(std::f64::consts::TAU, 512).unwrap().width();
        assert!(w > 1e-22 && w < 1e-20, "width {w}");
        // At t = 1000 the remainder is negligible and the width follows the precision.
        let w = theta(1000.0, 512).unwrap().width();
        assert!(w < 1e-60, "width {w}");
    }

    #[test]
    fn theta_width_shrinks_with_precision_at_large_t() {
        let w64 = theta(1000.0, 64).unwrap().width();
        let w256 = theta(1000.0, 256).unwrap().width();
        assert!(w256 < w64);
    }

    #[test]
    fn theta_rejects_non_positive_and_non_finite_heights() {
        for t in [0.0, -0.0, -1.0, f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert_eq!(theta(t, 128).unwrap_err(), ThetaError::HeightNotPositive, "t={t}");
        }
        assert!(theta(f64::MIN_POSITIVE, 128).is_ok());
        assert!(theta(5e-324, 128).is_ok());
    }

    #[test]
    fn theta_rejects_precision_outside_the_mpfr_range() {
        assert_eq!(theta(10.0, 0).unwrap_err(), ThetaError::PrecisionOutOfRange);
        assert_eq!(theta(10.0, MAX_PREC + 1).unwrap_err(), ThetaError::PrecisionOutOfRange);
        assert!(theta(10.0, MAX_PREC).is_ok());
        assert!(theta(10.0, rug::float::prec_min()).is_ok());
    }

    #[test]
    fn theta_errors_display_their_reason() {
        assert_eq!(
            ThetaError::HeightNotPositive.to_string(),
            "height is not a positive finite number"
        );
        assert_eq!(ThetaError::PrecisionOutOfRange.to_string(), "precision outside the MPFR range");
        let inner = ThetaError::from(IntervalError::NotANumber);
        assert_eq!(inner.to_string(), "interval arithmetic failed: interval bound is NaN");
    }

    #[test]
    fn fixture_lists_four_gram_points() {
        let rows: Vec<&str> = FIXTURE.lines().filter(|l| !l.starts_with('#')).collect();
        assert_eq!(rows.len(), 4);
    }

    fn fixture_rows() -> Vec<(i64, Float)> {
        FIXTURE
            .lines()
            .filter(|l| !l.starts_with('#'))
            .map(|l| {
                let (n, g) = l.split_once(' ').unwrap();
                (n.parse().unwrap(), big(g))
            })
            .collect()
    }

    fn big80(s: &str) -> Float {
        Float::with_val(512, Float::parse(s).unwrap())
    }

    fn exact(x: f64) -> Float {
        Float::with_val(256, x)
    }

    type ThetaAt<'a> = Box<dyn Fn(f64) -> Result<Interval, ThetaError> + 'a>;

    /// Lift a `(t, prec)` fake into the per-precision factory the search takes.
    fn at_prec<'a, F>(f: F) -> impl Fn(u32) -> Result<ThetaAt<'a>, ThetaError> + 'a
    where
        F: Fn(f64, u32) -> Result<Interval, ThetaError> + Copy + 'a,
    {
        move |p| Ok(Box::new(move |t| f(t, p)) as ThetaAt<'a>)
    }

    fn point(x: f64) -> Result<Interval, ThetaError> {
        Ok(Interval::point(x, 64))
    }

    fn span(lo: f64, hi: f64) -> Result<Interval, ThetaError> {
        Ok(Interval::new(Float::with_val(64, lo), Float::with_val(64, hi)).unwrap())
    }

    #[test]
    fn brackets_hold_the_mpmath_gram_points() {
        for (n, g) in fixture_rows() {
            let (b, c) = gram_bracket(n, 128).unwrap();
            assert!(exact(b) < g && g < exact(c), "n={n}: [{b}, {c}]");
            assert!(c - b < 1e-9, "n={n}: width {}", c - b);
        }
    }

    #[test]
    fn brackets_strictly_increase_with_n() {
        let mut prev = f64::NEG_INFINITY;
        for n in -1..=1000 {
            let (b, c) = gram_bracket(n, 64).unwrap();
            assert!(b < c, "n={n}");
            assert!(b > prev, "n={n}: {b} after {prev}");
            assert!(b > std::f64::consts::TAU);
            prev = b;
        }
    }

    #[test]
    fn brackets_exist_at_both_precision_limits() {
        assert!(gram_bracket(-1, 64).is_some());
        assert!(gram_bracket(-1, 512).is_some());
    }

    #[test]
    fn gram_index_guard_rejects_before_any_theta_evaluator_is_built() {
        // Counting the factory calls isolates the `n < -1` guard: the search
        // alone would also return None for these inputs, but only after calling it.
        let calls = std::cell::Cell::new(0u32);
        let counting = |p: u32| {
            calls.set(calls.get() + 1);
            ThetaContext::new(p).map(|ctx| move |t: f64| ctx.theta(t))
        };
        for n in [-2, i64::MIN] {
            assert_eq!(bracket_with(n, 128, &counting), None, "n={n}");
            assert_eq!(calls.get(), 0, "n={n}: factory called despite the guard");
        }
        assert!(bracket_with(-1, 128, &counting).is_some());
        assert!(calls.get() > 0, "control: n=-1 must reach the factory");
        // The public entry point returns None for n < -1.
        assert_eq!(gram_bracket(-2, 128), None);
        assert_eq!(gram_bracket(i64::MIN, 128), None);
    }

    #[test]
    fn estimate_lands_near_the_gram_point() {
        for (n, g) in fixture_rows() {
            let est = estimate_gram_point(n, &|t| theta(t, 64)).unwrap();
            let err = (exact(est) - &g).abs();
            assert!(err < 1e-11, "n={n}: estimate {est} off by {err}");
        }
    }

    #[test]
    fn asymptotic_theta_matches_mpmath_to_its_truncation_error() {
        // The first omitted term is about 4e-11 at t = 14.13; each kept term is larger.
        for (t, r) in REFS.iter().filter(|(t, _)| *t > 14.0) {
            let want = big(r).to_f64();
            assert!((asymptotic_theta(*t) - want).abs() < 1e-9, "t={t}");
        }
    }

    #[test]
    fn asymptotic_slope_is_the_derivative_of_asymptotic_theta() {
        // The omitted -31/(16128 t^6) term is 1.9e-9 at t = 10 and 2.4e-10 at
        // t = 14.13; with h = 1e-4 the central difference is good to about 1e-11,
        // so a 1e-10 tolerance sees it. At t = 100 rounding noise dominates.
        let h = 1e-4;
        for (t, tol) in [(10.0, 1e-10), (14.134725141734693, 1e-10), (100.0, 1e-7)] {
            let fd = (asymptotic_theta(t + h) - asymptotic_theta(t - h)) / (2.0 * h);
            assert!((asymptotic_slope(t) - fd).abs() < tol, "t={t}");
        }
    }

    #[test]
    fn midpoint_is_the_centre_of_the_interval() {
        let i = Interval::new(Float::with_val(64, 1.0), Float::with_val(64, 4.0)).unwrap();
        assert_eq!(midpoint_f64(&i), 2.5);
    }

    #[test]
    fn newton_starts_right_of_the_root_where_theta_is_above_target() {
        for n in [-1, 0, 1, 2, 100, 1000, 1_000_000] {
            let t = asymptotic_start(n);
            let target = n as f64 * std::f64::consts::PI;
            assert!(asymptotic_theta(t) > target, "n={n}: start {t}");
            assert!(asymptotic_slope(t) > 0.0, "n={n}");
        }
    }

    #[test]
    fn remainder_bound_is_the_pinned_formula_rounded_up() {
        // 2^n |B_2n| / (2n (2n-1) m^(2n-1)) at m = 10.75 (exact in binary), from the
        // independent exact Bernoulli generator at 800 bits.
        let n = SERIES_ORDER as u32;
        let b = bernoulli_exact(2 * n);
        let m = Float::with_val(800, 10.75);
        let mut want = Float::with_val(800, &b.num) / Float::with_val(800, &b.den);
        want = want.abs() * Float::with_val(800, Integer::from(1) << n);
        want /= Float::with_val(800, 2 * n * (2 * n - 1));
        want /= Float::with_val(800, rug::ops::Pow::pow(&m, 2 * n - 1));
        let ctx = ThetaContext::new(256).unwrap();
        let q = Interval::point(10.75 * 10.75, 256);
        let q_odd_power = (1..2 * n - 1).fold(q.clone(), |acc, _| acc.mul(&q));
        let got = ctx.remainder_bound(&q_odd_power).unwrap();
        assert!(got >= want, "bound {got} below exact {want}");
        let ceiling = Float::with_val(800, &want * (Float::with_val(800, 1) + 1e-20));
        assert!(got <= ceiling, "bound {got} too loose against {want}");
    }

    #[test]
    fn precision_ladder_climbs_to_the_cap() {
        assert_eq!(precision_ladder(512), vec![64, 128, 256, 512]);
        assert_eq!(precision_ladder(256), vec![64, 128, 256]);
        assert_eq!(precision_ladder(100), vec![64, 100]);
        assert_eq!(precision_ladder(64), vec![64]);
        assert_eq!(precision_ladder(40), vec![40]);
    }

    /// A shifted fake whose enclosure straddles n*pi near g_n: endpoints only
    /// certify where the whole enclosure is on one side.
    #[test]
    fn a_wide_enclosure_is_not_a_certificate_near_the_crossing() {
        let wide = |t: f64, p: u32| theta(t, p).map(|i| i.widen(&Float::with_val(64, 1e-6)));
        for (n, g) in fixture_rows() {
            let (b, c) = bracket_with(n, 128, &at_prec(wide)).unwrap();
            let pi = Float::with_val(256, rug::float::Constant::Pi);
            let target = Float::with_val(256, &pi * n);
            let (tb, tc) = (theta(b, 256).unwrap(), theta(c, 256).unwrap());
            assert!(*tb.hi() < Float::with_val(256, &target - 9e-7), "n={n}");
            assert!(*tc.lo() > Float::with_val(256, &target + 9e-7), "n={n}");
            assert!(exact(b) < g && g < exact(c));
        }
    }

    /// A fake enclosure offset above the truth certifies c too early: the
    /// bracket then misses g_n, showing the certificate follows the theta it is
    /// given and nothing else (the soundness burden sits on `theta`).
    #[test]
    fn the_certificate_follows_whatever_theta_it_is_given() {
        let shifted = |t: f64, p: u32| theta(t, p).map(|i| i.add(&Interval::point(1e-6, p)));
        let (_, g) = fixture_rows().into_iter().find(|(n, _)| *n == 100).unwrap();
        let (_, c) = bracket_with(100, 128, &at_prec(shifted)).unwrap();
        assert!(exact(c) < g, "c = {c} should fall short of g");
    }

    /// A window centred above g_n whose enclosure is widened until its hull holds
    /// n*pi although the window itself excludes g_n: neither end earns a sign.
    #[test]
    fn an_offset_window_whose_hull_contains_the_target_certifies_nothing() {
        let (n, g) = fixture_rows().into_iter().find(|(n, _)| *n == 100).unwrap();
        let centre = g.to_f64() + 1e-3;
        let (win_lo, win_hi) = (centre - 1e-4, centre + 1e-4);
        assert!(exact(win_lo) > g, "window must exclude g_n");
        let (lo_end, hi_end) = (theta(win_lo, 128).unwrap(), theta(win_hi, 128).unwrap());
        let slack = Float::with_val(128, 0.01);
        let hull = Interval::new(
            Float::with_val(128, lo_end.lo() - &slack),
            Float::with_val(128, hi_end.hi() + &slack),
        )
        .unwrap();
        let n_pi = Float::with_val(256, rug::float::Constant::Pi) * n;
        assert!(*hull.lo() < n_pi && n_pi < *hull.hi(), "hull must contain n*pi");
        let fake = |_t: f64| Ok(hull.clone());
        assert_eq!(bracket_around(n, centre, 128, &fake), None);
        let target = integer_interval(100, 128).unwrap().mul(&pi_interval(128).unwrap());
        assert_eq!(certified_end(&fake, &target, centre, Sign::Negative), None);
        assert_eq!(certified_end(&fake, &target, centre, Sign::Positive), None);
    }

    #[test]
    fn a_precision_cap_outside_the_supported_range_gives_no_bracket() {
        assert_eq!(gram_bracket(5, 0), None);
        assert_eq!(gram_bracket(5, MAX_PREC + 1), None);
        assert_eq!(gram_bracket(5, u32::MAX), None);
        assert!(gram_bracket(5, MAX_PREC).is_some());
        assert!(gram_bracket(5, 64).is_some());
    }

    #[test]
    fn theta_agrees_with_an_80_digit_mpmath_reference() {
        // mpmath 1.4.1: mp.dps = 100; nstr(siegeltheta(mpf(1000)), 80)
        let want = big80(
            "2034.5464280380316087033451512075987668293250759094135131801544824944960254832591",
        );
        let e = theta(1000.0, 512).unwrap();
        let slack = Float::with_val(512, 1e-70);
        let wide = e.widen(&slack);
        assert!(*wide.lo() <= want && want <= *wide.hi(), "[{}, {}]", e.lo(), e.hi());
    }

    #[test]
    fn touching_zero_is_not_a_certificate() {
        let touching = |t: f64| if t < 10.0 { span(-1.0, 0.0) } else { span(0.0, 1.0) };
        assert_eq!(bracket_around(0, 10.0, 64, &touching), None);
        let firm = |t: f64| if t < 10.0 { span(-1.0, -0.5) } else { span(0.5, 1.0) };
        let (b, c) = bracket_around(0, 10.0, 64, &firm).unwrap();
        assert!(b < 10.0 && 10.0 <= c);
    }

    #[test]
    fn the_bracket_ends_straddle_the_estimate_by_whole_ulps() {
        let firm = |t: f64| if t < 10.0 { point(-1.0) } else { point(1.0) };
        let (b, c) = bracket_around(0, 10.0, 64, &firm).unwrap();
        assert_eq!(b.to_bits(), 10.0f64.to_bits() - 1);
        assert_eq!(c.to_bits(), 10.0f64.to_bits() + 1);
    }

    #[test]
    fn a_left_end_at_or_below_two_pi_is_refused() {
        let tau = std::f64::consts::TAU;
        let est = f64::from_bits(tau.to_bits() + 4);
        // Only t <= 2*pi certifies on the left; the rungs before it straddle.
        let fake = |t: f64| {
            if t <= tau {
                point(-1.0)
            } else if t < est {
                span(-1.0, 1.0)
            } else {
                point(1.0)
            }
        };
        assert_eq!(bracket_around(0, est, 64, &fake), None);
        // Eight ulps up, rungs step 1, 2, 4, 8 ulps from est; the third (j = 2) lands
        // four ulps above 2*pi and is accepted, the fourth would land on 2*pi (refused).
        let est = f64::from_bits(tau.to_bits() + 8);
        let ok_below = f64::from_bits(tau.to_bits() + 4);
        let fake = |t: f64| {
            if t <= ok_below {
                point(-1.0)
            } else if t < est {
                span(-1.0, 1.0)
            } else {
                point(1.0)
            }
        };
        let (b, _) = bracket_around(0, est, 64, &fake).unwrap();
        assert_eq!(b, ok_below);
    }

    #[test]
    fn the_search_never_evaluates_infinite_or_nan_heights() {
        let seen = std::cell::RefCell::new(Vec::new());
        let never = |t: f64| {
            seen.borrow_mut().push(t);
            span(-1.0, 1.0)
        };
        let near_max = f64::from_bits(f64::MAX.to_bits() - 2);
        assert_eq!(bracket_around(0, near_max, 64, &never), None);
        assert_eq!(bracket_around(0, f64::NAN, 64, &never), None);
        assert!(seen.borrow().iter().all(|t| t.is_finite() && *t > std::f64::consts::TAU));
    }

    #[test]
    fn uncertified_pairs_raise_precision_up_to_the_cap() {
        let seen = std::cell::RefCell::new(Vec::new());
        let needs_256 = |t: f64, p: u32| {
            seen.borrow_mut().push(p);
            match (p >= 256, t < 10.0) {
                (true, true) => point(-1.0),
                (true, false) => point(1.0),
                (false, _) => span(-1.0, 1.0),
            }
        };
        assert!(bracket_with_estimate(0, 512, 10.0, &at_prec(needs_256)).is_some());
        let mut ps = seen.borrow().clone();
        ps.dedup();
        assert_eq!(ps, vec![64, 128, 256]);
        seen.borrow_mut().clear();
        assert_eq!(bracket_with_estimate(0, 100, 10.0, &at_prec(needs_256)), None);
        let mut ps = seen.borrow().clone();
        ps.dedup();
        assert_eq!(ps, vec![64, 100]);
    }

    #[test]
    fn a_bracket_needs_both_ends() {
        let only_left = |t: f64| if t < 10.0 { point(-1.0) } else { span(-1.0, 1.0) };
        assert_eq!(bracket_around(0, 10.0, 64, &only_left), None);
        let only_right = |t: f64| if t < 10.0 { span(-1.0, 1.0) } else { point(1.0) };
        assert_eq!(bracket_around(0, 10.0, 64, &only_right), None);
    }

    #[test]
    fn a_failing_theta_gives_no_bracket() {
        let broken = |_t: f64| Err(ThetaError::HeightNotPositive);
        assert_eq!(
            bracket_with(5, 128, &at_prec(|_t: f64, _p: u32| Err(ThetaError::HeightNotPositive))),
            None
        );
        assert_eq!(bracket_around(0, 10.0, 64, &broken), None);
    }

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(24))]

        /// Enclosures at two precisions both hold the true value, so they overlap.
        #[test]
        fn enclosures_at_two_precisions_overlap(t in 6.3f64..2000.0) {
            let a = theta(t, 64).unwrap();
            let b = theta(t, 256).unwrap();
            prop_assert!(a.lo() <= b.hi() && b.lo() <= a.hi());
        }
    }
}
