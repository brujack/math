//! Complex numbers over interval parts, shared by theta and Euler-Maclaurin.
//!
//! Each part is an `Interval`, so every operation encloses the exact complex
//! result for any points of the operands. Rectangular enclosures lose a little
//! to the dependency problem; that only widens, never narrows.

use crate::interval::{Interval, IntervalError};
use rug::Float;

/// A complex interval `re + i im`.
#[derive(Debug, Clone)]
pub(crate) struct Complex {
    pub(crate) re: Interval,
    pub(crate) im: Interval,
}

impl Complex {
    pub(crate) fn new(re: Interval, im: Interval) -> Complex {
        Complex { re, im }
    }

    pub(crate) fn add(&self, o: &Complex) -> Complex {
        Complex { re: self.re.add(&o.re), im: self.im.add(&o.im) }
    }

    pub(crate) fn mul(&self, o: &Complex) -> Complex {
        Complex {
            re: self.re.mul(&o.re).sub(&self.im.mul(&o.im)),
            im: self.re.mul(&o.im).add(&self.im.mul(&o.re)),
        }
    }

    /// Scale both parts by a real interval.
    pub(crate) fn mul_real(&self, k: &Interval) -> Complex {
        Complex { re: self.re.mul(k), im: self.im.mul(k) }
    }

    /// `self / o` as `self * conj(o) / |o|^2`; refused when `|o|^2` may be zero.
    pub(crate) fn div(&self, o: &Complex) -> Result<Complex, IntervalError> {
        let modulus_sq = o.re.mul(&o.re).add(&o.im.mul(&o.im));
        let conj = Complex { re: o.re.clone(), im: Interval::point(0.0, o.re.prec()).sub(&o.im) };
        let num = self.mul(&conj);
        Ok(Complex { re: num.re.div(&modulus_sq)?, im: num.im.div(&modulus_sq)? })
    }

    /// `cos(phase) + i sin(phase)` for a real interval phase.
    pub(crate) fn cis(phase: &Interval) -> Complex {
        Complex { re: phase.cos(), im: phase.sin() }
    }

    /// Grow both parts by `|r|` on both sides.
    pub(crate) fn widen(&self, r: &Float) -> Complex {
        Complex { re: self.re.widen(r), im: self.im.widen(r) }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::interval::{Interval, IntervalError};
    use proptest::prelude::*;
    use rug::Float;

    const PREC: u32 = 64;

    fn pt(x: f64) -> Interval {
        Interval::point(x, PREC)
    }

    fn c(re: f64, im: f64) -> Complex {
        Complex::new(pt(re), pt(im))
    }

    /// Both parts are the single points `re` and `im` (exact operands, exact results).
    fn assert_exact(z: &Complex, re: f64, im: f64) {
        assert_eq!(z.re.lo().to_f64(), re, "re lo");
        assert_eq!(z.re.hi().to_f64(), re, "re hi");
        assert_eq!(z.im.lo().to_f64(), im, "im lo");
        assert_eq!(z.im.hi().to_f64(), im, "im hi");
    }

    #[test]
    fn add_adds_parts() {
        assert_exact(&c(1.0, 2.0).add(&c(3.0, 5.0)), 4.0, 7.0);
    }

    #[test]
    fn mul_is_complex_product() {
        // (1+2i)(3+4i) = (3-8) + (4+6)i
        assert_exact(&c(1.0, 2.0).mul(&c(3.0, 4.0)), -5.0, 10.0);
    }

    #[test]
    fn mul_real_scales_both_parts() {
        assert_exact(&c(3.0, -4.0).mul_real(&pt(2.0)), 6.0, -8.0);
    }

    #[test]
    fn div_is_complex_quotient() {
        // (-5+10i)/(3+4i) = 1+2i
        let q = c(-5.0, 10.0).div(&c(3.0, 4.0)).unwrap();
        assert_exact(&q, 1.0, 2.0);
    }

    #[test]
    fn div_by_zero_modulus_is_refused() {
        let err = c(1.0, 1.0).div(&c(0.0, 0.0)).unwrap_err();
        assert_eq!(err, IntervalError::DivisorContainsZero);
    }

    #[test]
    fn div_by_interval_straddling_zero_modulus_is_refused() {
        let den = Complex::new(
            Interval::new(Float::with_val(PREC, -1), Float::with_val(PREC, 1)).unwrap(),
            pt(0.0),
        );
        assert!(c(1.0, 1.0).div(&den).is_err());
    }

    #[test]
    fn cis_of_zero_is_one() {
        assert_exact(&Complex::cis(&pt(0.0)), 1.0, 0.0);
    }

    #[test]
    fn cis_of_one_matches_cos_and_sin() {
        let z = Complex::cis(&pt(1.0));
        let (cos1, sin1) = (0.540_302_305_868_139_7, 0.841_470_984_807_896_5);
        assert!((z.re.lo().to_f64() - cos1).abs() < 1e-15);
        assert!((z.re.hi().to_f64() - cos1).abs() < 1e-15);
        assert!((z.im.lo().to_f64() - sin1).abs() < 1e-15);
        assert!((z.im.hi().to_f64() - sin1).abs() < 1e-15);
    }

    #[test]
    fn widen_grows_both_parts() {
        let z = c(1.0, 2.0).widen(&Float::with_val(PREC, -0.5));
        assert_eq!(z.re.lo().to_f64(), 0.5);
        assert_eq!(z.re.hi().to_f64(), 1.5);
        assert_eq!(z.im.lo().to_f64(), 1.5);
        assert_eq!(z.im.hi().to_f64(), 2.5);
    }

    /// Precision of the reference values: far above `PREC`, and enough to hold a
    /// product of two `f64` exactly.
    const REF_PREC: u32 = 1000;

    fn rf(x: f64) -> Float {
        Float::with_val(REF_PREC, x)
    }

    fn holds(i: &Interval, v: &Float) -> bool {
        i.lo() <= v && v <= i.hi()
    }

    fn encloses(z: &Complex, re: &Float, im: &Float) -> bool {
        holds(&z.re, re) && holds(&z.im, im)
    }

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(256))]

        #[test]
        fn add_and_mul_enclose_the_exact_result(
            (ar, ai, br, bi) in (-1e6f64..1e6, -1e6f64..1e6, -1e6f64..1e6, -1e6f64..1e6),
        ) {
            let (a, b) = (c(ar, ai), c(br, bi));
            let (xr, xi, yr, yi) = (rf(ar), rf(ai), rf(br), rf(bi));
            prop_assert!(encloses(&a.add(&b), &Float::with_val(REF_PREC, &xr + &yr),
                &Float::with_val(REF_PREC, &xi + &yi)));
            let re = Float::with_val(REF_PREC, &xr * &yr) - Float::with_val(REF_PREC, &xi * &yi);
            let im = Float::with_val(REF_PREC, &xr * &yi) + Float::with_val(REF_PREC, &xi * &yr);
            prop_assert!(encloses(&a.mul(&b), &re, &im));
        }

        #[test]
        fn mul_real_encloses_the_exact_result(
            (ar, ai, k) in (-1e6f64..1e6, -1e6f64..1e6, -1e6f64..1e6),
        ) {
            let z = c(ar, ai).mul_real(&pt(k));
            prop_assert!(encloses(&z, &Float::with_val(REF_PREC, rf(ar) * rf(k)),
                &Float::with_val(REF_PREC, rf(ai) * rf(k))));
        }

        #[test]
        fn div_encloses_the_exact_quotient(
            (ar, ai, br, bi) in (-1e6f64..1e6, -1e6f64..1e6, -1e6f64..1e6, -1e6f64..1e6),
        ) {
            // A point divisor is nonzero unless both parts are exactly 0.
            prop_assume!(br != 0.0 || bi != 0.0);
            let q = c(ar, ai).div(&c(br, bi)).unwrap();
            let (xr, xi, yr, yi) = (rf(ar), rf(ai), rf(br), rf(bi));
            let den = Float::with_val(REF_PREC, &yr * &yr) + Float::with_val(REF_PREC, &yi * &yi);
            let re = (Float::with_val(REF_PREC, &xr * &yr) + Float::with_val(REF_PREC, &xi * &yi))
                / &den;
            let im = (Float::with_val(REF_PREC, &xi * &yr) - Float::with_val(REF_PREC, &xr * &yi))
                / &den;
            prop_assert!(encloses(&q, &Float::with_val(REF_PREC, re), &Float::with_val(REF_PREC, im)));
        }

        #[test]
        fn div_by_a_divisor_whose_modulus_may_be_zero_is_refused(
            (lo, hi, h) in (0.001f64..1e6, 0.001f64..1e6, 0.001f64..1e6),
        ) {
            // The real part straddles 0 and so does the imaginary part: |den|^2 contains 0.
            let den = Complex::new(
                Interval::new(Float::with_val(PREC, -lo), Float::with_val(PREC, hi)).unwrap(),
                Interval::new(Float::with_val(PREC, -h), Float::with_val(PREC, h)).unwrap(),
            );
            prop_assert_eq!(c(1.0, 1.0).div(&den).unwrap_err(), IntervalError::DivisorContainsZero);
        }

        #[test]
        fn cis_encloses_cosine_and_sine(phase in -100.0f64..100.0) {
            let z = Complex::cis(&pt(phase));
            let p = rf(phase);
            prop_assert!(encloses(&z, &p.clone().cos(), &p.sin()));
        }
    }
}
