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
    /// Both bounds are the same infinity, so no real number lies inside.
    NoRealPoint,
    /// The divisor interval contains zero.
    DivisorContainsZero,
    /// `ln` of an interval whose lower bound is not strictly positive.
    LogOfNonPositive,
    /// `sqrt` of an interval whose lower bound is negative.
    SqrtOfNegative,
}

impl std::fmt::Display for IntervalError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let msg = match self {
            Self::NotANumber => "interval bound is NaN",
            Self::Inverted => "interval lower bound exceeds upper bound",
            Self::NoRealPoint => "interval has both bounds at the same infinity",
            Self::DivisorContainsZero => "division by an interval containing zero",
            Self::LogOfNonPositive => "ln of an interval not strictly positive",
            Self::SqrtOfNegative => "sqrt of an interval containing negative values",
        };
        f.write_str(msg)
    }
}

impl std::error::Error for IntervalError {}

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
    ///
    /// # Panics
    ///
    /// Panics if `prec` is outside `rug::float::prec_min()..=rug::float::prec_max()`.
    pub fn point(x: f64, prec: u32) -> Interval {
        assert!(
            (rug::float::prec_min()..=rug::float::prec_max()).contains(&prec),
            "Interval::point: precision {prec} outside the MPFR range"
        );
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
        if lo.is_infinite() && lo == hi {
            return Err(IntervalError::NoRealPoint);
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
                // down/up are NaN-free here, so MPFR min/max are plain comparisons.
                lo = lo.min(&down);
                hi = hi.max(&up);
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

    /// `atan` is increasing, so the endpoint images bound the image.
    pub fn atan(&self) -> Interval {
        let p = self.prec();
        Interval {
            lo: rounded(p, self.lo.atan_ref(), Round::Down),
            hi: rounded(p, self.hi.atan_ref(), Round::Up),
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
        let r = r_hi.max(&r_lo);
        let f_down = eval(&m, p, Round::Down);
        let f_up = eval(&m, p, Round::Up);
        let lo = rounded(p, &f_down - &r, Round::Down);
        let hi = rounded(p, &f_up + &r, Round::Up);
        // MPFR max/min return the non-NaN operand, so a NaN bound clamps to the unit limit.
        let lo = lo.max(&Float::with_val(p, -1));
        let hi = hi.min(&Float::with_val(p, 1));
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
        } else if self.lo.is_sign_positive() {
            // excludes_zero holds, so lo is either > 0 or negative with hi < 0.
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

    /// Exact f64 bounds of an interval whose endpoints are at most 53 bits wide
    /// or came from f64 values.
    fn bounds_f64(i: &Interval) -> (f64, f64) {
        (i.lo().to_f64(), i.hi().to_f64())
    }

    /// An f64 inside [lo, hi] chosen by fraction `t` in [0, 1].
    fn pick(lo: f64, hi: f64, t: f64) -> f64 {
        (lo + t * (hi - lo)).clamp(lo, hi)
    }

    fn contains(i: &Interval, v: &Float) -> bool {
        i.lo() <= v && v <= i.hi()
    }

    /// R18 reference: the value computed at `hp` bits with outward rounding is a
    /// subset of the enclosure.
    fn encloses<F: Fn(Round) -> Float>(i: &Interval, f: F) -> bool {
        contains(i, &f(Round::Down)) && contains(i, &f(Round::Up))
    }

    /// `inner` is a subset of `outer`.
    fn nested(inner: &Interval, outer: &Interval) -> bool {
        inner.lo() >= outer.lo() && inner.hi() <= outer.hi()
    }

    fn at_prec(i: &Interval, prec: u32) -> Interval {
        Interval::new(Float::with_val(prec, i.lo()), Float::with_val(prec, i.hi())).unwrap()
    }

    /// Point fraction, biased towards the endpoints where outward rounding bites.
    fn fraction() -> impl Strategy<Value = f64> {
        prop_oneof![Just(0.0), Just(1.0), 0.0f64..=1.0]
    }

    /// Signed f64 with a log-uniform magnitude 2^e, e in [lo_exp, hi_exp], or zero.
    fn endpoint(lo_exp: i32, hi_exp: i32) -> impl Strategy<Value = f64> {
        prop_oneof![
            1 => Just(0.0),
            9 => (any::<bool>(), 1.0f64..2.0, lo_exp..=hi_exp).prop_map(|(neg, m, e)| {
                let v = m * 2f64.powi(e);
                if neg { -v } else { v }
            }),
        ]
    }

    fn positive(lo_exp: i32, hi_exp: i32) -> impl Strategy<Value = f64> {
        (1.0f64..2.0, lo_exp..=hi_exp).prop_map(|(m, e)| m * 2f64.powi(e))
    }

    fn sorted(a: f64, b: f64) -> (f64, f64) {
        if a <= b { (a, b) } else { (b, a) }
    }

    /// Interval at precision `p` from two f64 endpoints (rounded to `p` bits,
    /// which preserves order), plus its exact f64 bounds.
    fn make(p: u32, a: f64, b: f64) -> (Interval, f64, f64) {
        let (lo, hi) = sorted(a, b);
        let i = iv(p, lo, hi);
        let (l, h) = bounds_f64(&i);
        (i, l, h)
    }

    /// Centre and width, as R18 prescribes for cos/sin, with widths past pi.
    fn centred() -> impl Strategy<Value = (f64, f64)> {
        (
            prop_oneof![-1e9f64..1e9, endpoint(-60, 30)],
            prop_oneof![Just(0.0), 0.0f64..4.0, endpoint(-60, -1).prop_map(f64::abs)],
        )
    }

    fn exact_midpoint_and_radius(i: &Interval, p: u32) -> (Float, Float) {
        let mut m = rounded(p, i.lo() + i.hi(), Round::Nearest);
        m /= 2u32;
        let r_hi = Float::with_val(2000, i.hi() - &m);
        let r_lo = Float::with_val(2000, &m - i.lo());
        (m, if r_hi > r_lo { r_hi } else { r_lo })
    }

    /// Result bounds are at least as wide as f(m) -/+ r (outward-rounded at 2000
    /// bits), clamped to [-1, 1]; `m` is the midpoint the implementation uses.
    fn covers_formula<F: Fn(&Float, Round) -> Float>(
        res: &Interval,
        m: &Float,
        r: &Float,
        f: F,
    ) -> bool {
        let want_lo =
            rounded(2000, &f(m, Round::Down) - r, Round::Down).max(&Float::with_val(2000, -1));
        let want_hi = rounded(2000, &f(m, Round::Up) + r, Round::Up).min(&Float::with_val(2000, 1));
        *res.lo() <= want_lo && *res.hi() >= want_hi
    }

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(256))]

        #[test]
        fn add_sub_mul_enclose(
            a in (endpoint(-60, 30), endpoint(-60, 30)),
            b in (endpoint(-60, 30), endpoint(-60, 30)),
            (ta, tb) in (fraction(), fraction()),
            p in 2u32..200,
        ) {
            let (ia, alo, ahi) = make(p, a.0, a.1);
            let (ib, blo, bhi) = make(p, b.0, b.1);
            let (x, y) = (pick(alo, ahi, ta), pick(blo, bhi, tb));
            let hp = 4 * p + 100;
            let (fx, fy) = (fl(hp, x), fl(hp, y));
            prop_assert!(encloses(&ia.add(&ib), |r| rounded(hp, &fx + &fy, r)));
            prop_assert!(encloses(&ia.sub(&ib), |r| rounded(hp, &fx - &fy, r)));
            prop_assert!(encloses(&ia.mul(&ib), |r| rounded(hp, &fx * &fy, r)));
        }

        #[test]
        fn div_encloses(
            a in (endpoint(-60, 30), endpoint(-60, 30)),
            b in (positive(-60, 30), positive(-60, 30)),
            neg in any::<bool>(),
            (ta, tb) in (fraction(), fraction()),
            p in 2u32..200,
        ) {
            let (blo, bhi) = sorted(b.0, b.1);
            let (blo, bhi) = if neg { (-bhi, -blo) } else { (blo, bhi) };
            let (ia, alo, ahi) = make(p, a.0, a.1);
            let (ib, blo, bhi) = make(p, blo, bhi);
            let (x, y) = (pick(alo, ahi, ta), pick(blo, bhi, tb));
            let hp = 4 * p + 100;
            let (fx, fy) = (fl(hp, x), fl(hp, y));
            let q = ia.div(&ib).unwrap();
            prop_assert!(encloses(&q, |r| rounded(hp, &fx / &fy, r)));
        }

        #[test]
        fn sqrt_ln_enclose(a in (positive(-60, 30), positive(-60, 30)), t in fraction(), p in 2u32..200) {
            let (i, lo, hi) = make(p, a.0, a.1);
            let hp = 4 * p + 100;
            let x = fl(hp, pick(lo, hi, t));
            prop_assert!(encloses(&i.sqrt().unwrap(), |r| rounded(hp, x.sqrt_ref(), r)));
            // ln of an interval whose lower bound rounds to 1 can straddle zero; fine.
            prop_assert!(encloses(&i.ln().unwrap(), |r| rounded(hp, x.ln_ref(), r)));
        }

        #[test]
        fn atan_encloses(a in (endpoint(-60, 30), endpoint(-60, 30)), t in fraction(), p in 2u32..200) {
            let (i, lo, hi) = make(p, a.0, a.1);
            let hp = 4 * p + 100;
            let x = fl(hp, pick(lo, hi, t));
            prop_assert!(encloses(&i.atan(), |r| rounded(hp, x.atan_ref(), r)));
        }

        #[test]
        fn exp_encloses(a in -50.0f64..50.0, b in -50.0f64..50.0, t in fraction(), p in 2u32..200) {
            let (i, lo, hi) = make(p, a, b);
            let hp = 4 * p + 100;
            let x = fl(hp, pick(lo, hi, t));
            prop_assert!(encloses(&i.exp(), |r| rounded(hp, x.exp_ref(), r)));
        }

        #[test]
        fn cos_sin_enclose((c, w) in centred(), t in fraction(), p in 2u32..200) {
            let (i, lo, hi) = make(p, c, c + w);
            let hp = 4 * p + 100;
            let x = fl(hp, pick(lo, hi, t));
            prop_assert!(encloses(&i.cos(), |r| rounded(hp, x.cos_ref(), r)));
            prop_assert!(encloses(&i.sin(), |r| rounded(hp, x.sin_ref(), r)));
        }

        #[test]
        fn narrow_cos_sin_enclose(c in -1e9f64..1e9, w in 0.0f64..3.0, t in fraction(), p in 2u32..200) {
            let (i, lo, hi) = make(p, c, c + w);
            let hp = 4 * p + 100;
            let x = fl(hp, pick(lo, hi, t));
            prop_assert!(encloses(&i.cos(), |r| rounded(hp, x.cos_ref(), r)));
            prop_assert!(encloses(&i.sin(), |r| rounded(hp, x.sin_ref(), r)));
        }

        #[test]
        fn zero_width_cos_sin_near_1e9_enclose(c in 9e8f64..1.1e9, p in 2u32..200) {
            let i = Interval::point(c, p);
            let hp = 4 * p + 100;
            let x = fl(hp, c);
            prop_assert!(encloses(&i.cos(), |r| rounded(hp, x.cos_ref(), r)));
            prop_assert!(encloses(&i.sin(), |r| rounded(hp, x.sin_ref(), r)));
        }

        /// The enclosure is no tighter than f(m) -/+ r computed from the same
        /// midpoint with an exactly evaluated radius (kills radius rounding bugs).
        #[test]
        fn cos_sin_bounds_cover_the_midpoint_formula((c, w) in centred(), p in 2u32..120) {
            let (i, _, _) = make(p, c, c + w);
            let (m, r) = exact_midpoint_and_radius(&i, p);
            prop_assert!(covers_formula(&i.cos(), &m, &r, |x, rd| rounded(2000, x.cos_ref(), rd)));
            prop_assert!(covers_formula(&i.sin(), &m, &r, |x, rd| rounded(2000, x.sin_ref(), rd)));
        }

        /// Same formula check on intervals straddling zero at low precision, where
        /// the midpoint rounds and `hi - m` / `m - lo` are inexact.
        #[test]
        fn cos_sin_bounds_cover_the_formula_when_straddling_zero(
            a in 0.05f64..1.5,
            b in 0.05f64..1.5,
            p in 2u32..40,
        ) {
            let (i, _, _) = make(p, -a, b);
            let (m, r) = exact_midpoint_and_radius(&i, p);
            prop_assert!(covers_formula(&i.cos(), &m, &r, |x, rd| rounded(2000, x.cos_ref(), rd)));
            prop_assert!(covers_formula(&i.sin(), &m, &r, |x, rd| rounded(2000, x.sin_ref(), rd)));
        }

        /// Raising the precision on identical inputs only tightens the result.
        #[test]
        fn higher_precision_nests_inside_lower(
            a in (endpoint(-200, 200), endpoint(-200, 200)),
            b in (endpoint(-200, 200), endpoint(-200, 200)),
            pa in (positive(-200, 200), positive(-200, 200)),
            pb in (positive(-200, 200), positive(-200, 200)),
            e in (-20.0f64..20.0, -20.0f64..20.0),
            r in endpoint(-200, 200),
            p in 2u32..=200,
        ) {
            let (ia, ..) = make(p, a.0, a.1);
            let (ib, ..) = make(p, b.0, b.1);
            let (qa, ..) = make(p, pa.0, pa.1);
            let (qb, ..) = make(p, pb.0, pb.1);
            let (ie, ..) = make(p, e.0, e.1);
            let q = 4 * p;
            let up = |i: &Interval| at_prec(i, q);
            prop_assert!(nested(&up(&ia).add(&up(&ib)), &ia.add(&ib)));
            prop_assert!(nested(&up(&ia).sub(&up(&ib)), &ia.sub(&ib)));
            prop_assert!(nested(&up(&ia).mul(&up(&ib)), &ia.mul(&ib)));
            prop_assert!(nested(&up(&qa).div(&up(&qb)).unwrap(), &qa.div(&qb).unwrap()));
            prop_assert!(nested(&up(&qa).sqrt().unwrap(), &qa.sqrt().unwrap()));
            prop_assert!(nested(&up(&qa).ln().unwrap(), &qa.ln().unwrap()));
            prop_assert!(nested(&up(&ie).exp(), &ie.exp()));
            prop_assert!(nested(&up(&ia).atan(), &ia.atan()));
            // cos/sin are excluded: the midpoint form recentres per precision, so
            // nesting across precisions is not implied (see the formula tests).
            let rr = fl(p, r);
            prop_assert!(nested(&up(&ia).widen(&Float::with_val(q, &rr)), &ia.widen(&rr)));
            let exact = Float::with_val(2000, ia.hi() - ia.lo());
            prop_assert!(ia.width() >= exact);
            prop_assert!(up(&ia).width() >= exact);
            prop_assert!(up(&ia).width() <= ia.width());
        }
    }

    #[test]
    fn mixed_precision_operands_give_the_larger_precision() {
        let narrow = Interval::point(1.5, 53);
        let wide = iv(200, 2.0, 3.0);
        assert_eq!(narrow.add(&wide).prec(), 200);
        assert_eq!(wide.add(&narrow).prec(), 200);
        assert_eq!(narrow.sub(&wide).prec(), 200);
        assert_eq!(narrow.mul(&wide).prec(), 200);
        assert_eq!(narrow.div(&wide).unwrap().prec(), 200);
        let skew = Interval::new(fl(53, 1.0), fl(200, 2.0)).unwrap();
        assert_eq!(skew.prec(), 200);
        assert_eq!(skew.sqrt().unwrap().prec(), 200);
        assert_eq!(skew.exp().prec(), 200);
        assert_eq!(skew.cos().prec(), 200);
    }

    #[test]
    fn new_rejects_a_pure_infinity() {
        for x in [f64::INFINITY, f64::NEG_INFINITY] {
            assert_eq!(
                Interval::new(fl(PREC, x), fl(PREC, x)).unwrap_err(),
                IntervalError::NoRealPoint
            );
        }
        assert!(Interval::new(fl(PREC, f64::NEG_INFINITY), fl(PREC, f64::INFINITY)).is_ok());
        assert!(Interval::new(fl(PREC, 1.0), fl(PREC, f64::INFINITY)).is_ok());
    }

    #[test]
    #[should_panic(expected = "outside the MPFR range")]
    fn point_panics_clearly_on_zero_precision() {
        let _ = Interval::point(1.0, 0);
    }

    #[test]
    fn point_accepts_the_minimum_precision() {
        let p = Interval::point(0.1, rug::float::prec_min());
        assert!(*p.lo() <= 0.1 && *p.hi() >= 0.1);
    }

    #[test]
    fn clamps_hold_where_the_radius_overshoots_the_unit_range() {
        let pi = std::f64::consts::PI;
        let half = std::f64::consts::FRAC_PI_2;
        let around_pi = iv(PREC, pi - 0.1, pi + 0.1).cos();
        assert_eq!(*around_pi.lo(), -1.0);
        assert!(*around_pi.hi() < -0.8);
        let around_zero = iv(PREC, -0.1, 0.1).cos();
        assert_eq!(*around_zero.hi(), 1.0);
        let sin_top = iv(PREC, half - 0.1, half + 0.1).sin();
        assert_eq!(*sin_top.hi(), 1.0);
        let sin_bottom = iv(PREC, -half - 0.1, -half + 0.1).sin();
        assert_eq!(*sin_bottom.lo(), -1.0);
    }

    #[test]
    fn narrow_edge_cases_enclose() {
        for (c, w, p) in
            [(0.0, 0.0, 2), (1e-300, 1e-300, 30), (0.0, 3.0, 40), (1e9, 1.0, 52), (-1e9, 2.0, 10)]
        {
            let (i, lo, hi) = make(p, c, c + w);
            let hp = 4 * p + 100;
            for t in [0.0, 0.5, 1.0] {
                let x = fl(hp, pick(lo, hi, t));
                assert!(encloses(&i.cos(), |r| rounded(hp, x.cos_ref(), r)));
                assert!(encloses(&i.sin(), |r| rounded(hp, x.sin_ref(), r)));
            }
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
    fn atan_rounds_outward_and_handles_infinite_bounds() {
        let one = Interval::point(1.0, 53);
        let r = one.atan();
        let quarter_pi = Float::with_val(300, rug::float::Constant::Pi) / 4u32;
        assert!(*r.lo() < quarter_pi && quarter_pi < *r.hi());
        let wide = Interval::new(fl(PREC, f64::NEG_INFINITY), fl(PREC, f64::INFINITY)).unwrap();
        let w = wide.atan();
        let half_pi = Float::with_val(300, rug::float::Constant::Pi) / 2u32;
        assert!(*w.lo() <= -half_pi.clone() && *w.hi() >= half_pi);
        assert!(w.lo().is_finite() && w.hi().is_finite());
        let m = iv(PREC, -2.0, 3.0).atan();
        assert!(*m.lo() < 0 && *m.hi() > 0);
    }

    #[test]
    fn exp_of_point_encloses_e() {
        let r = Interval::point(1.0, 100).exp();
        let e = Float::with_val(300, 1).exp();
        assert!(*r.lo() <= e && e <= *r.hi());
        assert!(r.lo() < r.hi());
    }

    #[test]
    fn interval_error_display_names_each_failure() {
        let cases = [
            (IntervalError::NotANumber, "interval bound is NaN"),
            (IntervalError::Inverted, "interval lower bound exceeds upper bound"),
            (IntervalError::NoRealPoint, "interval has both bounds at the same infinity"),
            (IntervalError::DivisorContainsZero, "division by an interval containing zero"),
            (IntervalError::LogOfNonPositive, "ln of an interval not strictly positive"),
            (IntervalError::SqrtOfNegative, "sqrt of an interval containing negative values"),
        ];
        for (e, want) in cases {
            assert_eq!(format!("{e}"), want);
        }
        let boxed: Box<dyn std::error::Error> = Box::new(IntervalError::NotANumber);
        assert_eq!(boxed.to_string(), "interval bound is NaN");
    }

    #[test]
    fn cos_of_width_exactly_pi_down_uses_the_midpoint_path() {
        let pi_down = rounded(PREC, rug::float::Constant::Pi, Round::Down);
        let h = Float::with_val(PREC, &pi_down / 2u32);
        let i = Interval::new(Float::with_val(PREC, -&h), h).unwrap();
        assert_eq!(i.width(), pi_down);
        // Midpoint 0 gives cos in about [cos(pi/2) - pi/2, 1]; the full-circle
        // fallback would give lo == -1.
        assert!(i.cos().lo > -1);
    }
}
