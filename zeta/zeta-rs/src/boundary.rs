//! Certified Gram-block boundaries (spec R22).
//!
//! A block boundary is the Gram point g_n. Its f64 bracket `[b_n, c_n]` comes
//! from `theta::gram_bracket`; the boundary is usable only when Z has one
//! certified sign on all of `[b_n, c_n]`, which also proves the bracket holds
//! no zero. An unusable Gram point is `Ok(None)`, never a guess.

use crate::config::VerifyConfig;
use crate::interval::Sign;
use crate::isolate::Point;
use crate::theta::gram_bracket;
use crate::zfun::{ZFault, ZSource, certified_sign_ladder};

/// A closed range of heights over which Z has been certified zero-free. Only
/// `certify_boundary` builds one, so holding one is the proof.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ZeroFreeBracket {
    lo: f64,
    hi: f64,
}

impl ZeroFreeBracket {
    pub fn lo(&self) -> f64 {
        self.lo
    }

    pub fn hi(&self) -> f64 {
        self.hi
    }

    /// Test-only: other modules' tests need a bracket without a Z source. Never
    /// compiled into the library, so production code cannot forge the proof.
    #[cfg(test)]
    pub(crate) fn for_test(lo: f64, hi: f64) -> ZeroFreeBracket {
        ZeroFreeBracket { lo, hi }
    }
}

/// A block boundary: `point` is b_n with Z's certified sign over `bracket`.
/// The fields are private so only `certify_boundary` builds one.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Boundary {
    point: Point,
    bracket: ZeroFreeBracket,
}

impl Boundary {
    pub fn point(&self) -> Point {
        self.point
    }

    pub fn bracket(&self) -> ZeroFreeBracket {
        self.bracket
    }
}

/// Good means (-1)^n Z(g_n) > 0.
pub(crate) fn is_good(n: i64, sign: Sign) -> bool {
    sign == if n.rem_euclid(2) == 0 { Sign::Positive } else { Sign::Negative }
}

/// The boundary at Gram point g_n (n >= -1): `Ok(None)` when theta cannot be
/// certified around g_n or Z's sign over the bracket stays uncertain (an unusable
/// Gram point), `Err` only for a Z fault.
pub fn certify_boundary<Z: ZSource>(
    n: i64,
    z: &Z,
    cfg: &VerifyConfig,
) -> Result<Option<Boundary>, ZFault> {
    let Some((lo, hi)) = gram_bracket(n, cfg.precision_cap()) else {
        return Ok(None);
    };
    Ok(certified_sign_ladder(cfg, |prec| z.z_over(lo, hi, prec))?
        .map(|sign| Boundary { point: Point { t: lo, sign }, bracket: ZeroFreeBracket { lo, hi } }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::interval::{Interval, Sign};
    use crate::zfun::{RealZ, ZError, ZEvaluator};
    use proptest::prelude::*;
    use std::cell::RefCell;

    #[test]
    fn goodness_follows_the_parity_of_the_index() {
        assert!(is_good(4, Sign::Positive));
        assert!(!is_good(4, Sign::Negative));
        assert!(is_good(5, Sign::Negative));
        assert!(!is_good(5, Sign::Positive));
    }

    fn cfg() -> VerifyConfig {
        VerifyConfig::default()
    }

    fn real() -> RealZ {
        RealZ::new(&cfg()).unwrap()
    }

    /// Scripted `z_over`: records `(lo, hi, prec)` and answers by precision.
    struct Scripted {
        answer: Box<dyn Fn(u32) -> Result<Option<Interval>, ZFault>>,
        calls: RefCell<Vec<(f64, f64, u32)>>,
    }

    impl Scripted {
        fn new(answer: impl Fn(u32) -> Result<Option<Interval>, ZFault> + 'static) -> Scripted {
            Scripted { answer: Box::new(answer), calls: RefCell::new(Vec::new()) }
        }
    }

    impl ZSource for Scripted {
        fn z(&self, _t: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
            panic!("boundary certification must use z_over");
        }

        fn z_over(&self, lo: f64, hi: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
            self.calls.borrow_mut().push((lo, hi, prec));
            (self.answer)(prec)
        }
    }

    fn span(lo: f64, hi: f64) -> Option<Interval> {
        Some(Interval::new(rug::Float::with_val(64, lo), rug::Float::with_val(64, hi)).unwrap())
    }

    #[test]
    fn g_minus_one_and_a_mid_range_gram_point_certify() {
        let z = real();
        for (n, want) in [(-1, Sign::Negative), (0, Sign::Positive), (1000, Sign::Positive)] {
            let b = certify_boundary(n, &z, &cfg()).unwrap().expect("certifies");
            assert_eq!(b.point().sign, want, "n = {n}");
            assert_eq!(b.point().t, b.bracket().lo());
            assert!(b.bracket().lo() < b.bracket().hi(), "n = {n}");
        }
    }

    #[test]
    fn the_test_constructor_round_trips_through_the_accessors() {
        let b = ZeroFreeBracket::for_test(9.5, 9.75);
        assert_eq!((b.lo(), b.hi()), (9.5, 9.75));
    }

    #[test]
    fn bracket_is_the_gram_bracket() {
        let b = certify_boundary(1000, &real(), &cfg()).unwrap().unwrap();
        assert_eq!(
            (b.bracket().lo(), b.bracket().hi()),
            gram_bracket(1000, cfg().precision_cap()).unwrap()
        );
    }

    #[test]
    fn sign_matches_gram_s_law_at_good_points_and_flips_at_the_first_bad_one() {
        let z = real();
        let sign_of = |n: i64| certify_boundary(n, &z, &cfg()).unwrap().unwrap().point().sign;
        let law = |n: i64| if n % 2 == 0 { Sign::Positive } else { Sign::Negative };
        for n in [2, 3, 50, 100, 125, 127] {
            assert_eq!(sign_of(n), law(n), "good Gram point n = {n}");
        }
        // g_126 is the first Gram point where (-1)^n Z(g_n) < 0.
        let bad = (0..=200).find(|&n| sign_of(n) != law(n)).unwrap();
        assert_eq!(bad, 126);
        assert_ne!(sign_of(126), law(126));
    }

    /// A Z enclosure `[-w, w]` that excludes 0 never.
    fn around_zero(width: f64) -> Result<Option<Interval>, ZFault> {
        Ok(span(-width, width))
    }

    #[test]
    fn a_halving_straddle_climbs_every_rung_then_gives_none() {
        let z = Scripted::new(|prec| around_zero(64.0 / f64::from(prec)));
        assert_eq!(certify_boundary(10, &z, &cfg()).unwrap(), None);
        let precs: Vec<u32> = z.calls.borrow().iter().map(|c| c.2).collect();
        assert_eq!(precs, vec![64, 128, 256, 512]);
    }

    #[test]
    fn the_width_stop_rule_applies_to_boundaries_too() {
        let z = Scripted::new(|_| around_zero(1.0));
        assert_eq!(certify_boundary(10, &z, &cfg()).unwrap(), None);
        let precs: Vec<u32> = z.calls.borrow().iter().map(|c| c.2).collect();
        assert_eq!(precs, vec![64, 128]);
    }

    #[test]
    fn a_refusing_source_gives_none() {
        let z = Scripted::new(|_| Ok(None));
        assert_eq!(certify_boundary(10, &z, &cfg()).unwrap(), None);
    }

    #[test]
    fn precision_climbs_until_the_sign_certifies() {
        let z = Scripted::new(|prec| {
            if prec >= 256 { Ok(span(2.0, 3.0)) } else { around_zero(64.0 / f64::from(prec)) }
        });
        let b = certify_boundary(10, &z, &cfg()).unwrap().unwrap();
        assert_eq!(b.point().sign, Sign::Positive);
        let precs: Vec<u32> = z.calls.borrow().iter().map(|c| c.2).collect();
        assert_eq!(precs, vec![64, 128, 256]);
    }

    #[test]
    fn the_precision_cap_bounds_the_ladder() {
        let capped = VerifyConfig::new(1.0, 128, 40, true).unwrap();
        let z = Scripted::new(|prec| around_zero(64.0 / f64::from(prec)));
        assert_eq!(certify_boundary(10, &z, &capped).unwrap(), None);
        let precs: Vec<u32> = z.calls.borrow().iter().map(|c| c.2).collect();
        assert_eq!(precs, vec![64, 128]);
    }

    #[test]
    fn the_sign_is_taken_from_the_enclosure() {
        let z = Scripted::new(|_| Ok(span(-3.0, -2.0)));
        assert_eq!(certify_boundary(10, &z, &cfg()).unwrap().unwrap().point().sign, Sign::Negative);
    }

    #[test]
    fn a_fault_propagates_even_after_a_refusal() {
        let z = Scripted::new(|prec| if prec == 64 { Ok(None) } else { Err(ZFault::NanHeight) });
        assert_eq!(certify_boundary(10, &z, &cfg()), Err(ZFault::NanHeight));
    }

    #[test]
    fn the_source_is_asked_about_the_gram_bracket() {
        let z = Scripted::new(|_| Ok(span(1.0, 2.0)));
        certify_boundary(10, &z, &cfg()).unwrap().unwrap();
        let (lo, hi) = gram_bracket(10, cfg().precision_cap()).unwrap();
        assert_eq!(z.calls.borrow()[0], (lo, hi, 64));
    }

    #[test]
    fn an_n_with_no_gram_bracket_gives_none_without_asking_z() {
        let z = Scripted::new(|_| Ok(span(1.0, 2.0)));
        assert_eq!(certify_boundary(-2, &z, &cfg()).unwrap(), None);
        assert!(z.calls.borrow().is_empty());
    }

    #[test]
    fn z_over_refuses_unheld_precisions_and_faults_on_nan() {
        let z = real();
        assert!(matches!(z.z_over(300.0, 300.1, 100), Ok(None)));
        assert!(matches!(z.z_over(f64::NAN, 300.0, 64), Err(ZFault::NanHeight)));
        assert!(matches!(z.z_over(300.0, f64::NAN, 64), Err(ZFault::NanHeight)));
        assert!(matches!(z.z_over(300.1, 300.0, 64), Ok(None)));
    }

    #[test]
    fn z_over_refuses_a_theta_unsafe_interval_but_accepts_a_point() {
        let z = real();
        assert!(matches!(z.z_over(3.0, 4.0, 128), Ok(None)));
        assert!(z.z_over(3.0, 3.0, 128).unwrap().is_some());
        // The threshold itself is usable: 7 is the first height an interval may start at.
        assert!(z.z_over(7.0, 7.001, 128).unwrap().is_some());
    }

    #[test]
    fn an_interval_spanning_a_split_change_is_a_refusal_not_a_fault() {
        // 2 pi 6^2 = 226.19: N = floor(sqrt(t / 2 pi)) is 5 below it and 6 above.
        let ev = ZEvaluator::new(128, &cfg()).unwrap();
        assert_eq!(ev.riemann_siegel_over(226.0, 226.4).unwrap_err(), ZError::AmbiguousSplit);
        let z = real();
        assert!(matches!(z.z_over(226.0, 226.4, 128), Ok(None)));
        assert_eq!(certified_sign_ladder(&cfg(), |p| z.z_over(226.0, 226.4, p)), Ok(None));
    }

    #[test]
    fn an_interval_over_p_one_quarter_is_a_refusal_not_a_fault() {
        // 2 pi 6.25^2 = 245.44: p = 1/4 there, so cos(2 pi p) holds 0.
        let ev = ZEvaluator::new(128, &cfg()).unwrap();
        assert_eq!(ev.riemann_siegel_over(245.4, 245.5).unwrap_err(), ZError::SingularCorrection);
        let z = real();
        assert!(matches!(z.z_over(245.4, 245.5, 128), Ok(None)));
        assert_eq!(certified_sign_ladder(&cfg(), |p| z.z_over(245.4, 245.5, p)), Ok(None));
    }

    #[test]
    fn z_over_dispatches_on_the_lower_end() {
        let z = real();
        // Below 200 Euler-Maclaurin, from 200 Riemann-Siegel; both enclose the point value.
        for (lo, hi) in [(150.0, 150.001), (199.999, 200.001), (200.0, 200.001), (5000.0, 5000.01)]
        {
            let over = z.z_over(lo, hi, 128).unwrap().expect("certifies");
            let at = z.z(lo, 128).unwrap().unwrap();
            assert!(over.lo() <= at.hi() && at.lo() <= over.hi(), "[{lo}, {hi}]");
        }
        assert!(matches!(z.z_over(150.0, 1e4 + 1.0, 128), Ok(None)));
    }

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(24))]

        #[test]
        fn the_interval_enclosure_covers_point_enclosures(
            lo in 8.0f64..400.0, width in 1e-6f64..0.05, frac in 0.0f64..1.0,
        ) {
            let z = real();
            let hi = lo + width;
            let mid = lo + frac * width;
            if let Some(over) = z.z_over(lo, hi, 128).unwrap() {
                for t in [lo, mid, hi] {
                    let at = z.z(t, 128).unwrap().unwrap();
                    prop_assert!(over.lo() <= at.lo() && at.hi() <= over.hi(), "t = {t}");
                }
            }
        }
    }
}
