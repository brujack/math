//! Interval arithmetic over MPFR floats with directed rounding.
//!
//! Every operation returns an interval enclosing the exact real result of the
//! operation applied to any points of the inputs: lower bounds round down and
//! upper bounds round up.

use rug::Float;
use rug::float::Round;
use rug::ops::AssignRound;
use std::cmp::Ordering;

/// Failure modes of interval construction and operations.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IntervalError {
    /// A bound was NaN.
    NotANumber,
    /// The lower bound exceeded the upper bound.
    Inverted,
    /// The divisor interval contains zero.
    DivisorContainsZero,
    /// `ln` of an interval whose lower bound is not strictly positive.
    LogOfNonPositive,
    /// `sqrt` of an interval whose lower bound is negative.
    SqrtOfNegative,
}

/// Definite sign of an interval that excludes zero.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Sign {
    Positive,
    Negative,
}

/// A closed interval `[lo, hi]` whose bounds are MPFR floats.
#[derive(Debug, Clone)]
pub struct Interval {
    lo: Float,
    hi: Float,
}

fn rounded<T>(prec: u32, value: T, round: Round) -> Float
where
    Float: AssignRound<T, Round = Round, Ordering = Ordering>,
{
    Float::with_val_round(prec, value, round).0
}

/// NaN can only arise from an indeterminate form such as inf - inf; the
/// sound enclosure of an unknown value is the whole line.
fn lower_or_unbounded(f: Float) -> Float {
    if f.is_nan() { Float::with_val(f.prec(), f64::NEG_INFINITY) } else { f }
}

fn upper_or_unbounded(f: Float) -> Float {
    if f.is_nan() { Float::with_val(f.prec(), f64::INFINITY) } else { f }
}

impl Interval {
    /// The interval enclosing the single value `x` at precision `prec`.
    /// NaN yields the whole line.
    pub fn point(x: f64, prec: u32) -> Interval {
        if x.is_nan() {
            return Interval {
                lo: Float::with_val(prec, f64::NEG_INFINITY),
                hi: Float::with_val(prec, f64::INFINITY),
            };
        }
        Interval { lo: rounded(prec, x, Round::Down), hi: rounded(prec, x, Round::Up) }
    }

    /// Build `[lo, hi]`, rejecting NaN bounds and `lo > hi`.
    pub fn new(lo: Float, hi: Float) -> Result<Interval, IntervalError> {
        if lo.is_nan() || hi.is_nan() {
            return Err(IntervalError::NotANumber);
        }
        if lo > hi {
            return Err(IntervalError::Inverted);
        }
        Ok(Interval { lo, hi })
    }

    pub fn lo(&self) -> &Float {
        &self.lo
    }

    pub fn hi(&self) -> &Float {
        &self.hi
    }

    /// Working precision used for results of operations on this interval.
    pub fn prec(&self) -> u32 {
        self.lo.prec().max(self.hi.prec())
    }

    fn joint_prec(&self, other: &Interval) -> u32 {
        self.prec().max(other.prec())
    }

    pub fn add(&self, other: &Interval) -> Interval {
        let p = self.joint_prec(other);
        Interval {
            lo: lower_or_unbounded(rounded(p, &self.lo + &other.lo, Round::Down)),
            hi: upper_or_unbounded(rounded(p, &self.hi + &other.hi, Round::Up)),
        }
    }

    pub fn sub(&self, other: &Interval) -> Interval {
        let p = self.joint_prec(other);
        Interval {
            lo: lower_or_unbounded(rounded(p, &self.lo - &other.hi, Round::Down)),
            hi: upper_or_unbounded(rounded(p, &self.hi - &other.lo, Round::Up)),
        }
    }

    /// Minimum of the four endpoint combinations (rounded down) and maximum
    /// (rounded up); `op` is the exact operation on two endpoints.
    fn combine_corners<F>(&self, other: &Interval, op: F) -> Interval
    where
        F: Fn(&Float, &Float, u32, Round) -> Float,
    {
        let p = self.joint_prec(other);
        let mut lo = Float::with_val(p, f64::INFINITY);
        let mut hi = Float::with_val(p, f64::NEG_INFINITY);
        for a in [&self.lo, &self.hi] {
            for b in [&other.lo, &other.hi] {
                let down = lower_or_unbounded(op(a, b, p, Round::Down));
                let up = upper_or_unbounded(op(a, b, p, Round::Up));
                if down < lo {
                    lo = down;
                }
                if up > hi {
                    hi = up;
                }
            }
        }
        Interval { lo, hi }
    }

    pub fn mul(&self, other: &Interval) -> Interval {
        self.combine_corners(other, |a, b, p, r| rounded(p, a * b, r))
    }

    pub fn div(&self, other: &Interval) -> Result<Interval, IntervalError> {
        if other.lo <= 0 && other.hi >= 0 {
            return Err(IntervalError::DivisorContainsZero);
        }
        Ok(self.combine_corners(other, |a, b, p, r| rounded(p, a / b, r)))
    }

    pub fn sqrt(&self) -> Result<Interval, IntervalError> {
        if self.lo < 0 {
            return Err(IntervalError::SqrtOfNegative);
        }
        let p = self.prec();
        Ok(Interval {
            lo: rounded(p, self.lo.sqrt_ref(), Round::Down),
            hi: rounded(p, self.hi.sqrt_ref(), Round::Up),
        })
    }

    pub fn ln(&self) -> Result<Interval, IntervalError> {
        if self.lo <= 0 {
            return Err(IntervalError::LogOfNonPositive);
        }
        let p = self.prec();
        Ok(Interval {
            lo: rounded(p, self.lo.ln_ref(), Round::Down),
            hi: rounded(p, self.hi.ln_ref(), Round::Up),
        })
    }

    pub fn exp(&self) -> Interval {
        let p = self.prec();
        Interval {
            lo: rounded(p, self.lo.exp_ref(), Round::Down),
            hi: rounded(p, self.hi.exp_ref(), Round::Up),
        }
    }

    /// Shared body of `cos` and `sin`: `eval` is the correctly rounded
    /// function on a point. Wide arguments give [-1, 1]; otherwise the
    /// midpoint value is widened by the radius (the functions are 1-Lipschitz).
    fn periodic<F>(&self, eval: F) -> Interval
    where
        F: Fn(&Float, u32, Round) -> Float,
    {
        let p = self.prec();
        let full = || Interval { lo: Float::with_val(p, -1), hi: Float::with_val(p, 1) };
        let pi_down = rounded(p, rug::float::Constant::Pi, Round::Down);
        let width = self.width();
        if !width.is_finite() || width > pi_down {
            return full();
        }
        let mut m = rounded(p, &self.lo + &self.hi, Round::Nearest);
        m /= 2u32;
        let r_hi = rounded(p, &self.hi - &m, Round::Up);
        let r_lo = rounded(p, &m - &self.lo, Round::Up);
        let r = if r_hi > r_lo { r_hi } else { r_lo };
        let f_down = eval(&m, p, Round::Down);
        let f_up = eval(&m, p, Round::Up);
        let mut lo = rounded(p, &f_down - &r, Round::Down);
        let mut hi = rounded(p, &f_up + &r, Round::Up);
        if lo < -1 || lo.is_nan() {
            lo = Float::with_val(p, -1);
        }
        if hi > 1 || hi.is_nan() {
            hi = Float::with_val(p, 1);
        }
        Interval { lo, hi }
    }

    pub fn cos(&self) -> Interval {
        self.periodic(|m, p, r| rounded(p, m.cos_ref(), r))
    }

    pub fn sin(&self) -> Interval {
        self.periodic(|m, p, r| rounded(p, m.sin_ref(), r))
    }

    /// Grow the interval by `|r|` on both sides.
    pub fn widen(&self, r: &Float) -> Interval {
        let p = self.prec();
        let r = Float::with_val(r.prec(), r.abs_ref());
        Interval {
            lo: lower_or_unbounded(rounded(p, &self.lo - &r, Round::Down)),
            hi: upper_or_unbounded(rounded(p, &self.hi + &r, Round::Up)),
        }
    }

    /// True only when both bounds are finite and zero lies outside.
    pub fn excludes_zero(&self) -> bool {
        self.lo.is_finite() && self.hi.is_finite() && (self.lo > 0 || self.hi < 0)
    }

    pub fn sign(&self) -> Option<Sign> {
        if !self.excludes_zero() {
            None
        } else if self.lo > 0 {
            Some(Sign::Positive)
        } else {
            Some(Sign::Negative)
        }
    }

    /// `hi - lo`, rounded up.
    pub fn width(&self) -> Float {
        rounded(self.prec(), &self.hi - &self.lo, Round::Up)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    const PREC: u32 = 80;

    fn fl(prec: u32, x: f64) -> Float {
        Float::with_val(prec, x)
    }

    fn iv(prec: u32, lo: f64, hi: f64) -> Interval {
        Interval::new(fl(prec, lo), fl(prec, hi)).unwrap()
    }

    /// An f64 inside [lo, hi] chosen by fraction `t` in [0, 1].
    fn pick(lo: f64, hi: f64, t: f64) -> f64 {
        (lo + t * (hi - lo)).clamp(lo, hi)
    }

    fn contains(i: &Interval, v: &Float) -> bool {
        i.lo() <= v && v <= i.hi()
    }

    /// Point fraction, biased towards the endpoints where outward rounding bites.
    fn fraction() -> impl Strategy<Value = f64> {
        prop_oneof![Just(0.0), Just(1.0), 0.0f64..=1.0]
    }

    /// Interval strategy: ordered endpoints up to 1e9 in magnitude plus a point
    /// fraction.
    fn span() -> impl Strategy<Value = (f64, f64, f64)> {
        (-1e9f64..1e9, -1e9f64..1e9, fraction()).prop_map(|(a, b, t)| {
            let (lo, hi) = if a <= b { (a, b) } else { (b, a) };
            (lo, hi, t)
        })
    }

    fn positive_span() -> impl Strategy<Value = (f64, f64, f64)> {
        (1e-9f64..1e9, 1e-9f64..1e9, fraction()).prop_map(|(a, b, t)| {
            let (lo, hi) = if a <= b { (a, b) } else { (b, a) };
            (lo, hi, t)
        })
    }

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(256))]

        #[test]
        fn add_sub_mul_enclose((alo, ahi, at) in span(), (blo, bhi, bt) in span(), p in 64u32..200) {
            let a = iv(p, alo, ahi);
            let b = iv(p, blo, bhi);
            let (x, y) = (pick(alo, ahi, at), pick(blo, bhi, bt));
            let hp = 4 * p;
            let (fx, fy) = (fl(hp, x), fl(hp, y));
            prop_assert!(contains(&a.add(&b), &Float::with_val(hp, &fx + &fy)));
            prop_assert!(contains(&a.sub(&b), &Float::with_val(hp, &fx - &fy)));
            prop_assert!(contains(&a.mul(&b), &Float::with_val(hp, &fx * &fy)));
        }

        #[test]
        fn div_encloses((alo, ahi, at) in span(), (blo, bhi, bt) in positive_span(), neg in any::<bool>(), p in 64u32..200) {
            let (blo, bhi) = if neg { (-bhi, -blo) } else { (blo, bhi) };
            let a = iv(p, alo, ahi);
            let b = iv(p, blo, bhi);
            let x = pick(alo, ahi, at);
            let y = pick(blo, bhi, bt);
            let hp = 4 * p;
            let q = Float::with_val(hp, fl(hp, x) / fl(hp, y));
            prop_assert!(contains(&a.div(&b).unwrap(), &q));
        }

        #[test]
        fn sqrt_ln_enclose((lo, hi, t) in positive_span(), p in 64u32..200) {
            let a = iv(p, lo, hi);
            let x = fl(4 * p, pick(lo, hi, t));
            prop_assert!(contains(&a.sqrt().unwrap(), &Float::with_val(4 * p, x.sqrt_ref())));
            prop_assert!(contains(&a.ln().unwrap(), &Float::with_val(4 * p, x.ln_ref())));
        }

        #[test]
        fn exp_encloses((lo, hi, t) in (-50.0f64..50.0, -50.0f64..50.0, fraction()), p in 64u32..200) {
            let (lo, hi) = if lo <= hi { (lo, hi) } else { (hi, lo) };
            let a = iv(p, lo, hi);
            let x = fl(4 * p, pick(lo, hi, t));
            prop_assert!(contains(&a.exp(), &Float::with_val(4 * p, x.exp_ref())));
        }

        #[test]
        fn cos_sin_enclose((lo, hi, t) in span(), p in 64u32..200) {
            let a = iv(p, lo, hi);
            let x = fl(4 * p, pick(lo, hi, t));
            prop_assert!(contains(&a.cos(), &Float::with_val(4 * p, x.cos_ref())));
            prop_assert!(contains(&a.sin(), &Float::with_val(4 * p, x.sin_ref())));
        }

        #[test]
        fn narrow_cos_sin_enclose(c in -1e6f64..1e6, w in 0.0f64..3.0, t in fraction(), p in 64u32..200) {
            let (lo, hi) = (c, c + w);
            let a = iv(p, lo, hi);
            let x = fl(4 * p, pick(lo, hi, t));
            prop_assert!(contains(&a.cos(), &Float::with_val(4 * p, x.cos_ref())));
            prop_assert!(contains(&a.sin(), &Float::with_val(4 * p, x.sin_ref())));
        }
    }

    #[test]
    fn new_rejects_inverted_and_nan() {
        assert_eq!(
            Interval::new(fl(PREC, 2.0), fl(PREC, 1.0)).unwrap_err(),
            IntervalError::Inverted
        );
        assert_eq!(
            Interval::new(fl(PREC, f64::NAN), fl(PREC, 1.0)).unwrap_err(),
            IntervalError::NotANumber
        );
        assert_eq!(
            Interval::new(fl(PREC, 1.0), fl(PREC, f64::NAN)).unwrap_err(),
            IntervalError::NotANumber
        );
        assert!(Interval::new(fl(PREC, 1.0), fl(PREC, 1.0)).is_ok());
    }

    #[test]
    fn point_is_exact_at_adequate_precision_and_outward_below() {
        let p = Interval::point(0.1, 64);
        assert_eq!(p.lo(), p.hi());
        assert_eq!(p.prec(), 64);
        let q = Interval::point(0.1, 10);
        assert!(q.lo() < q.hi());
        assert!(*q.lo() <= 0.1 && *q.hi() >= 0.1);
    }

    #[test]
    fn point_nan_is_the_whole_line() {
        let p = Interval::point(f64::NAN, PREC);
        assert!(p.lo().is_infinite() && p.lo().is_sign_negative());
        assert!(p.hi().is_infinite() && p.hi().is_sign_positive());
        assert!(!p.excludes_zero());
    }

    #[test]
    fn addition_of_inexact_values_rounds_outward() {
        let a = Interval::point(0.1, 53);
        let b = Interval::point(0.2, 53);
        let s = a.add(&b);
        let exact = Float::with_val(200, 0.1) + Float::with_val(200, 0.2);
        assert!(*s.lo() <= exact && exact <= *s.hi());
    }

    #[test]
    fn inexact_results_are_strictly_enclosed_by_directed_rounding() {
        let a = Interval::point(0.1, 53);
        let m = a.mul(&a);
        let exact = Float::with_val(300, 0.1) * Float::with_val(300, 0.1);
        assert!(*m.lo() < exact && exact < *m.hi());
        let d = Interval::point(1.0, 53).div(&Interval::point(3.0, 53)).unwrap();
        let third = Float::with_val(300, 1) / 3u32;
        assert!(*d.lo() < third && third < *d.hi());
        let two = Interval::point(2.0, 53);
        let s = two.sqrt().unwrap();
        let root = Float::with_val(300, 2).sqrt();
        assert!(*s.lo() < root && root < *s.hi());
        let l = two.ln().unwrap();
        let ln2 = Float::with_val(300, 2).ln();
        assert!(*l.lo() < ln2 && ln2 < *l.hi());
    }

    #[test]
    fn mul_sign_cases_take_min_and_max_corners() {
        let r = iv(PREC, -2.0, 3.0).mul(&iv(PREC, -5.0, 4.0));
        assert_eq!(*r.lo(), -15.0);
        assert_eq!(*r.hi(), 12.0);
    }

    #[test]
    fn mul_zero_by_infinity_stays_sound() {
        let inf = Interval::new(fl(PREC, 0.0), fl(PREC, f64::INFINITY)).unwrap();
        let r = Interval::point(0.0, PREC).mul(&inf);
        assert!(r.lo().is_infinite() && r.lo().is_sign_negative());
        assert!(r.hi().is_infinite() && r.hi().is_sign_positive());
    }

    #[test]
    fn div_errors_when_divisor_contains_zero() {
        let a = iv(PREC, 1.0, 2.0);
        for (lo, hi) in [(-1.0, 1.0), (0.0, 1.0), (-1.0, 0.0), (0.0, 0.0)] {
            assert_eq!(a.div(&iv(PREC, lo, hi)).unwrap_err(), IntervalError::DivisorContainsZero);
        }
        assert!(a.div(&iv(PREC, 1.0, 2.0)).is_ok());
    }

    #[test]
    fn ln_errors_when_lower_bound_not_positive() {
        assert_eq!(iv(PREC, 0.0, 1.0).ln().unwrap_err(), IntervalError::LogOfNonPositive);
        assert_eq!(iv(PREC, -1.0, 1.0).ln().unwrap_err(), IntervalError::LogOfNonPositive);
        assert!(iv(PREC, 1e-300, 1.0).ln().is_ok());
    }

    #[test]
    fn sqrt_errors_on_negative_but_accepts_zero() {
        assert_eq!(iv(PREC, -1.0, 4.0).sqrt().unwrap_err(), IntervalError::SqrtOfNegative);
        let r = iv(PREC, 0.0, 4.0).sqrt().unwrap();
        assert_eq!(*r.lo(), 0.0);
        assert_eq!(*r.hi(), 2.0);
    }

    #[test]
    fn zero_width_cos_sin_inputs_give_tight_enclosures() {
        for x in [0.0, 1.0, 1e6, -3.5] {
            let a = Interval::point(x, 100);
            for r in [a.cos(), a.sin()] {
                assert!(r.width() < 1e-25, "width {} at x={x}", r.width());
            }
        }
        let c0 = Interval::point(0.0, 100).cos();
        assert!(*c0.hi() <= 1 && *c0.lo() >= 1.0 - 1e-25);
    }

    #[test]
    fn wide_cos_sin_arguments_give_full_range() {
        let a = iv(PREC, 0.0, 3.2);
        for r in [a.cos(), a.sin()] {
            assert_eq!(*r.lo(), -1.0);
            assert_eq!(*r.hi(), 1.0);
        }
        let inf = Interval::new(fl(PREC, 0.0), fl(PREC, f64::INFINITY)).unwrap();
        assert_eq!(*inf.cos().lo(), -1.0);
    }

    #[test]
    fn cos_sin_never_leave_unit_range() {
        let a = iv(PREC, 0.0, 0.0001);
        assert!(*a.cos().hi() <= 1.0 && *a.cos().lo() >= -1.0);
        assert!(*a.sin().hi() <= 1.0 && *a.sin().lo() >= -1.0);
    }

    #[test]
    fn width_shrinks_as_precision_grows() {
        let w =
            |p: u32| Interval::point(0.1, p).add(&Interval::point(0.2, p)).sqrt().unwrap().width();
        let (w20, w60, w200) = (w(20), w(60), w(200));
        assert!(w60 < w20);
        assert!(w200 < w60);
        let c = |p: u32| Interval::point(1.0, p).cos().width();
        assert!(c(200) < c(40));
    }

    #[test]
    fn excludes_zero_requires_finite_bounds_and_strict_sign() {
        assert!(iv(PREC, 1.0, 2.0).excludes_zero());
        assert!(iv(PREC, -2.0, -1.0).excludes_zero());
        assert!(!iv(PREC, 0.0, 1.0).excludes_zero());
        assert!(!iv(PREC, -1.0, 0.0).excludes_zero());
        assert!(!iv(PREC, -1.0, 1.0).excludes_zero());
        let pos_inf = Interval::new(fl(PREC, 1.0), fl(PREC, f64::INFINITY)).unwrap();
        let neg_inf = Interval::new(fl(PREC, f64::NEG_INFINITY), fl(PREC, -1.0)).unwrap();
        assert!(!pos_inf.excludes_zero());
        assert!(!neg_inf.excludes_zero());
    }

    #[test]
    fn sign_is_some_only_when_zero_excluded() {
        assert_eq!(iv(PREC, 1.0, 2.0).sign(), Some(Sign::Positive));
        assert_eq!(iv(PREC, -2.0, -1.0).sign(), Some(Sign::Negative));
        assert_eq!(iv(PREC, -1.0, 1.0).sign(), None);
        assert_eq!(iv(PREC, 0.0, 1.0).sign(), None);
    }

    #[test]
    fn widen_grows_both_sides_and_ignores_sign_of_radius() {
        let a = iv(PREC, 1.0, 2.0);
        for r in [0.5, -0.5] {
            let w = a.widen(&fl(PREC, r));
            assert_eq!(*w.lo(), 0.5);
            assert_eq!(*w.hi(), 2.5);
        }
        let same = a.widen(&fl(PREC, 0.0));
        assert_eq!(*same.lo(), 1.0);
        assert_eq!(*same.hi(), 2.0);
    }

    #[test]
    fn widen_by_infinity_is_unbounded_and_inf_minus_inf_is_sound() {
        let a = iv(PREC, 1.0, 2.0).widen(&fl(PREC, f64::INFINITY));
        assert!(a.lo().is_infinite() && a.hi().is_infinite());
        let inf = Interval::new(fl(PREC, f64::NEG_INFINITY), fl(PREC, f64::INFINITY)).unwrap();
        let d = inf.sub(&inf);
        assert!(d.lo().is_infinite() && d.hi().is_infinite());
    }

    #[test]
    fn width_is_hi_minus_lo() {
        assert_eq!(iv(PREC, 1.0, 3.5).width(), 2.5);
        assert_eq!(Interval::point(1.0, PREC).width(), 0.0);
    }

    #[test]
    fn exp_of_point_encloses_e() {
        let r = Interval::point(1.0, 100).exp();
        let e = Float::with_val(300, 1).exp();
        assert!(*r.lo() <= e && e <= *r.hi());
        assert!(r.lo() < r.hi());
    }
}
