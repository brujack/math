//! Certified enclosure of the Riemann-Siegel theta function.
//!
//! theta(t) = Im Ln Gamma(1/4 + it/2) - (t/2) ln(pi). Ln Gamma comes from the
//! Stirling series (DLMF 5.11.1) with its error bound (DLMF 5.11(ii)), applied
//! at z + SHIFT and moved back by the recurrence
//! Ln Gamma(z) = Ln Gamma(z + m) - sum_{k<m} Ln(z + k), exact for Re z > 0.
//! The shift keeps |w| >= 10.25, where the series is accurate to about 3e-22
//! at 2*pi and far better above it; the accuracy floor is therefore about 1e-22
//! however many bits are requested.

use crate::interval::{Interval, IntervalError};
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
const BERNOULLI: [(i128, u32); SERIES_ORDER] = [
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
fn pi_interval(prec: u32) -> Result<Interval, ThetaError> {
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

/// Upper bound of the Stirling remainder |R_n(w)| for w with |w| = `modulus`
/// (an interval) and ph w in (0, pi/2), where sec^{2n}(ph/2) <= 2^n.
fn remainder_bound(modulus: &Interval, prec: u32) -> Result<Float, ThetaError> {
    let n = SERIES_ORDER;
    let mut power = modulus.clone();
    for _ in 1..2 * n - 1 {
        power = power.mul(modulus);
    }
    let (num, den) = BERNOULLI[n - 1];
    let two_pow = integer_interval(1i128 << n, prec)?;
    let numerator = integer_interval(num.abs(), prec)?.mul(&two_pow);
    let scale = integer_interval(i128::from(den) * (2 * n as i128) * (2 * n as i128 - 1), prec)?;
    Ok(numerator.div(&scale.mul(&power))?.hi().clone())
}

/// Complex interval, just enough for powers of conj(w).
struct Complex {
    re: Interval,
    im: Interval,
}

impl Complex {
    fn mul(&self, o: &Complex) -> Complex {
        Complex {
            re: self.re.mul(&o.re).sub(&self.im.mul(&o.im)),
            im: self.re.mul(&o.im).add(&self.im.mul(&o.re)),
        }
    }
}

/// Im Ln Gamma(w) for w = x + iy, x > 0: the Stirling series with remainder.
fn im_ln_gamma_stirling(x: &Interval, y: &Interval, prec: u32) -> Result<Interval, ThetaError> {
    let half = Interval::point(0.5, prec);
    let q = x.mul(x).add(&y.mul(y));
    let ln_modulus = q.ln()?.mul(&half);
    // Im[(w - 1/2) Ln w - w]
    let lead = x.sub(&half).mul(&y.div(x)?.atan()).add(&y.mul(&ln_modulus)).sub(y);
    // conj(w)^j / |w|^(2j) for j = 1, 3, 5, ...
    let zero = Interval::point(0.0, prec);
    let conj = Complex { re: x.clone(), im: zero.sub(y) };
    let step = conj.mul(&conj);
    let q_step = q.mul(&q);
    let mut power = conj;
    let mut q_power = q.clone();
    let mut series = zero.clone();
    for k in 1..SERIES_ORDER {
        let term = power.im.div(&q_power)?.mul(&series_coefficient(k, prec)?);
        series = series.add(&term);
        power = power.mul(&step);
        q_power = q_power.mul(&q_step);
    }
    let remainder = remainder_bound(&q.sqrt()?, prec)?;
    Ok(lead.add(&series).widen(&remainder))
}

/// Certified enclosure of theta(t) at `prec` bits.
///
/// `t` is taken as the exact binary value of the f64. Heights that are zero,
/// negative or not finite give `HeightNotPositive`; a precision outside the MPFR
/// range gives `PrecisionOutOfRange`. The result is valid for every t > 0 but is
/// meant for t >= 2*pi.
pub fn theta(t: f64, prec: u32) -> Result<Interval, ThetaError> {
    if !(t.is_finite() && t > 0.0) {
        return Err(ThetaError::HeightNotPositive);
    }
    if !(rug::float::prec_min()..=MAX_PREC).contains(&prec) {
        return Err(ThetaError::PrecisionOutOfRange);
    }
    // t * 0.5 is exact in MPFR, unlike t / 2.0 on f64 subnormals.
    let y = Interval::point(t, prec).mul(&Interval::point(0.5, prec));
    let x = Interval::point(f64::from(SHIFT) + 0.25, prec);
    let mut value = im_ln_gamma_stirling(&x, &y, prec)?;
    for k in 0..SHIFT {
        let xk = Interval::point(f64::from(k) + 0.25, prec);
        value = value.sub(&y.div(&xk)?.atan());
    }
    let ln_pi = pi_interval(prec)?.ln()?;
    Ok(value.sub(&y.mul(&ln_pi)))
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
