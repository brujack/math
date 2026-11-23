//! Hardy's Z function, certified, by two independent expansions.
//!
//! Riemann-Siegel (Gabcke's C_0 term and remainder bound, valid for t >= 200)
//! serves large heights; Euler-Maclaurin (Johansson 2015, Theorem 1) serves the
//! rest and cross-checks Riemann-Siegel in the self-check. Every enclosure is a
//! sound interval for the true Z(t) of the exact binary `f64` height, and a
//! condition that cannot be certified is an error, never a guess.

use crate::complex::Complex;
use crate::config::VerifyConfig;
use crate::interval::{Interval, IntervalError, Sign};
use crate::theta::{BERNOULLI, ThetaContext, ThetaError, pi_interval};
use rug::float::Round;
use rug::{Float, Integer};
use std::cmp::Ordering;

/// Riemann-Siegel is certified (Gabcke, Satz 3.2.2) only from this height.
pub const MIN_RS_HEIGHT: f64 = 200.0;

/// Largest height either expansion accepts. The term count grows like sqrt(t),
/// so a larger request is a mistake (the CLI stops at 10^7), not a need.
pub const MAX_HEIGHT: f64 = 1e10;

/// Default Riemann-Siegel limit of a `ZEvaluator`: 10x the CLI's 10^7, which
/// keeps the ln k / 1/sqrt k tables at about 4000 entries.
pub const DEFAULT_MAX_HEIGHT: f64 = 1e8;

/// Euler-Maclaurin is used only up to this height: its term count grows like t.
pub const EM_MAX_HEIGHT: f64 = 1e4;

/// Euler-Maclaurin correction terms M (Bernoulli numbers B_2 .. B_2M). With
/// N = ceil(hi) + 2M terms in the direct sum (hi = t for a point), (|s| + 2M) / (2 pi (N + 1)) stays
/// below 1 / (2 pi), and Johansson's bound is about 1e-34 at t = 300.
const EM_TERMS: usize = 20;

/// Why a Z enclosure could not be produced.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ZError {
    /// The height is outside the range the expansion is certified for, or not a number.
    HeightOutOfRange,
    /// floor(sqrt(t / 2 pi)) is not determined by the enclosure of the square root.
    AmbiguousSplit,
    /// cos(2 pi p) may be zero, where the C_0 quotient is a removable singularity.
    SingularCorrection,
    /// The imaginary part of e^(i theta) zeta(1/2 + it) does not contain 0: a fault.
    ImaginaryPartNonzero,
    /// The theta enclosure failed.
    Theta(ThetaError),
    /// An interval operation refused its operands.
    Interval(IntervalError),
}

impl ZError {
    /// True for a refusal (the height cannot be certified by this path, so a
    /// caller may retry at higher precision); false for an internal fault.
    pub fn is_refusal(&self) -> bool {
        self.clone().into_fault().is_none()
    }

    /// The fault this error is, or `None` for a refusal. The one exhaustive
    /// match over the variants: a new `ZError` variant fails to compile here until
    /// it is classified, and `is_refusal` and `refusal_or_fault` both follow it.
    fn into_fault(self) -> Option<ZFault> {
        match self {
            Self::HeightOutOfRange | Self::AmbiguousSplit | Self::SingularCorrection => None,
            Self::ImaginaryPartNonzero => Some(ZFault::ImaginaryPartNonzero),
            Self::Theta(e) => Some(ZFault::Theta(e)),
            Self::Interval(e) => Some(ZFault::Interval(e)),
        }
    }
}

impl std::fmt::Display for ZError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::HeightOutOfRange => f.write_str("height outside the certified range"),
            Self::AmbiguousSplit => f.write_str("floor(sqrt(t / 2 pi)) is not determined"),
            Self::SingularCorrection => f.write_str("cos(2 pi p) may be zero"),
            Self::ImaginaryPartNonzero => {
                f.write_str("imaginary part of e^(i theta) zeta does not contain 0")
            }
            Self::Theta(e) => write!(f, "theta failed: {e}"),
            Self::Interval(e) => write!(f, "interval arithmetic failed: {e}"),
        }
    }
}

impl std::error::Error for ZError {}

impl From<ThetaError> for ZError {
    fn from(e: ThetaError) -> Self {
        Self::Theta(e)
    }
}

impl From<IntervalError> for ZError {
    fn from(e: IntervalError) -> Self {
        Self::Interval(e)
    }
}

/// Interval enclosing `multiplier * 0.127 * t^(-3/4)`, every step rounded outward.
/// 0.127 is held as 127/1000 because the nearest `f64` may lie below it.
pub fn gabcke_bound(t: f64, prec: u32, multiplier: f64) -> Result<Interval, ZError> {
    let t_pow = Interval::point(t, prec).ln()?.mul(&Interval::point(-0.75, prec)).exp();
    let constant = Interval::point(127.0, prec).div(&Interval::point(1000.0, prec))?;
    Ok(t_pow.mul(&constant).mul(&Interval::point(multiplier, prec)))
}

/// Z(t) by Euler-Maclaurin together with the remainder bound added to the real
/// and imaginary parts of zeta before the rotation (the self-check needs it).
#[derive(Debug, Clone)]
pub struct EmEnclosure {
    pub z: Interval,
    pub remainder: Float,
}

/// Theta is increasing from about 6.29; an interval of heights uses its end
/// values only from here (7 leaves a margin).
const THETA_MONOTONE_FROM: f64 = 7.0;

/// Enclosure of the heights `[lo, hi]`: the lower end rounded down, the upper up.
fn height_interval(lo: f64, hi: f64, prec: u32) -> Result<Interval, IntervalError> {
    Interval::new(Interval::point(lo, prec).lo().clone(), Interval::point(hi, prec).hi().clone())
}

/// Interval enclosing the integer `v`, each bound rounded outward.
fn integer_interval(v: &Integer, prec: u32) -> Result<Interval, IntervalError> {
    let round = |r| Float::with_val_round(prec, v, r).0;
    Interval::new(round(Round::Down), round(Round::Up))
}

/// B_2k / (2k)! for k = 1..=EM_TERMS.
fn bernoulli_over_factorial(k: usize, prec: u32) -> Result<Interval, IntervalError> {
    let (num, den) = BERNOULLI[k - 1];
    let denominator = Integer::from(den) * Integer::from(Integer::factorial(2 * k as u32));
    integer_interval(&Integer::from(num), prec)?.div(&integer_interval(&denominator, prec)?)
}

/// `base^e` by repeated multiplication (e >= 1).
fn power(base: &Interval, e: usize) -> Interval {
    (1..e).fold(base.clone(), |acc, _| acc.mul(base))
}

/// Z = Re(e^(i theta) zeta) for zeta = zeta(1/2 + it); the imaginary part of
/// the product is exactly 0, so an enclosure that excludes 0 is a fault.
fn hardy_z(theta: &Interval, zeta: &Complex) -> Result<Interval, ZError> {
    let rotated = Complex::cis(theta).mul(zeta);
    if rotated.im.lo() > &0 || rotated.im.hi() < &0 {
        return Err(ZError::ImaginaryPartNonzero);
    }
    Ok(rotated.re)
}

/// Everything about Z that depends on the precision only: build it once and
/// evaluate many heights. No state changes after construction.
#[derive(Debug, Clone)]
pub struct ZEvaluator {
    prec: u32,
    theta: ThetaContext,
    multiplier: f64,
    two_pi: Interval,
    /// Largest height `riemann_siegel` accepts; the tables below cover it.
    max_height: f64,
    /// ln k for k = 1..=floor(sqrt(max_height / 2 pi)) + 1 (index k - 1).
    ln_k: Vec<Interval>,
    /// 1 / sqrt(k), same indexing.
    inv_sqrt_k: Vec<Interval>,
    /// B_2k / (2k)! for k = 1..=EM_TERMS.
    em_coefficients: Vec<Interval>,
    /// 4 / ((2 pi)^(2M) (2M - 1/2)), the t-independent factor of Johansson's bound.
    em_remainder_scale: Interval,
}

impl ZEvaluator {
    /// Build the evaluator for `prec` bits with Riemann-Siegel up to
    /// `DEFAULT_MAX_HEIGHT`; the Gabcke multiplier comes from `cfg`.
    pub fn new(prec: u32, cfg: &VerifyConfig) -> Result<ZEvaluator, ZError> {
        Self::with_max_height(prec, cfg, DEFAULT_MAX_HEIGHT)
    }

    /// Like `new`, with Riemann-Siegel accepted up to `max_height` (a larger
    /// limit costs a larger table). `max_height` must lie in
    /// `MIN_RS_HEIGHT..=MAX_HEIGHT`, else `HeightOutOfRange`.
    pub fn with_max_height(
        prec: u32,
        cfg: &VerifyConfig,
        max_height: f64,
    ) -> Result<ZEvaluator, ZError> {
        if !(MIN_RS_HEIGHT..=MAX_HEIGHT).contains(&max_height) {
            return Err(ZError::HeightOutOfRange);
        }
        let theta = ThetaContext::new(prec)?;
        let two_pi = pi_interval(prec)?.mul(&Interval::point(2.0, prec));
        let em_coefficients = (1..=EM_TERMS)
            .map(|k| bernoulli_over_factorial(k, prec))
            .collect::<Result<Vec<_>, _>>()?;
        let degree = Interval::point(2.0 * EM_TERMS as f64 - 0.5, prec);
        let em_remainder_scale =
            Interval::point(4.0, prec).div(&power(&two_pi, 2 * EM_TERMS).mul(&degree))?;
        // N = floor(a) <= floor(sqrt(max_height / 2 pi)); the extra entry absorbs
        // the f64 rounding of that estimate.
        let terms = (max_height / std::f64::consts::TAU).sqrt().floor() as u64 + 1;
        let mut ln_k = Vec::new();
        let mut inv_sqrt_k = Vec::new();
        for k in 1..=terms {
            let k = Interval::point(k as f64, prec);
            ln_k.push(k.ln()?);
            inv_sqrt_k.push(Interval::point(1.0, prec).div(&k.sqrt()?)?);
        }
        Ok(ZEvaluator {
            prec,
            theta,
            multiplier: cfg.gabcke_multiplier(),
            two_pi,
            max_height,
            ln_k,
            inv_sqrt_k,
            em_coefficients,
            em_remainder_scale,
        })
    }

    /// floor(a) when the enclosure of `a` pins it, else `AmbiguousSplit`.
    fn certified_floor(a: &Interval) -> Result<u64, ZError> {
        let lo = a.lo().clone().floor();
        if lo != a.hi().clone().floor() {
            return Err(ZError::AmbiguousSplit);
        }
        lo.to_integer().and_then(|n| n.to_u64()).ok_or(ZError::AmbiguousSplit)
    }

    /// Theta over the heights `[lo, hi]`: the point value when `lo == hi`, else
    /// the hull of the end values, valid because theta is increasing from
    /// `THETA_MONOTONE_FROM`; a lower end below it is `HeightOutOfRange`.
    fn theta_over(&self, lo: f64, hi: f64) -> Result<Interval, ZError> {
        if lo == hi {
            return Ok(self.theta.theta(lo)?);
        }
        if lo < THETA_MONOTONE_FROM {
            return Err(ZError::HeightOutOfRange);
        }
        let (at_lo, at_hi) = (self.theta.theta(lo)?, self.theta.theta(hi)?);
        Ok(Interval::new(at_lo.lo().clone(), at_hi.hi().clone())?)
    }

    /// Z(t) by the Riemann-Siegel formula with C_0 and Gabcke's remainder bound.
    ///
    /// `t` must lie in `MIN_RS_HEIGHT..=max_height`, else `HeightOutOfRange`.
    pub fn riemann_siegel(&self, t: f64) -> Result<Interval, ZError> {
        self.riemann_siegel_over(t, t)
    }

    /// An enclosure of Z(t) for every t in `[lo, hi]` by Riemann-Siegel.
    ///
    /// `MIN_RS_HEIGHT <= lo <= hi <= max_height` is required, else
    /// `HeightOutOfRange`. The split N = floor(sqrt(t / 2 pi)) must be one value
    /// over the whole interval, else `AmbiguousSplit`; Gabcke's bound is
    /// decreasing in t, so its value at `lo` bounds every height.
    pub fn riemann_siegel_over(&self, lo: f64, hi: f64) -> Result<Interval, ZError> {
        if !(MIN_RS_HEIGHT..=self.max_height).contains(&lo) || !(lo..=self.max_height).contains(&hi)
        {
            return Err(ZError::HeightOutOfRange);
        }
        let prec = self.prec;
        let height = height_interval(lo, hi, prec)?;
        let a = height.div(&self.two_pi)?.sqrt()?;
        let n = Self::certified_floor(&a)?;
        let p = a.sub(&Interval::point(n as f64, prec));
        let theta = self.theta_over(lo, hi)?;
        let terms = n as usize;
        let (Some(ln_k), Some(inv_sqrt_k)) = (self.ln_k.get(..terms), self.inv_sqrt_k.get(..terms))
        else {
            return Err(ZError::HeightOutOfRange);
        };
        let mut sum = Interval::point(0.0, prec);
        for (ln, inv_sqrt) in ln_k.iter().zip(inv_sqrt_k) {
            let phase = theta.sub(&height.mul(ln));
            sum = sum.add(&phase.cos().mul(inv_sqrt));
        }
        let main = sum.mul(&Interval::point(2.0, prec));
        // C_0 = cos(2 pi (p^2 - p - 1/16)) / cos(2 pi p).
        let inner = p.mul(&p).sub(&p).sub(&Interval::point(0.0625, prec));
        let numerator = self.two_pi.mul(&inner).cos();
        let denominator = self.two_pi.mul(&p).cos();
        let c0 = match numerator.div(&denominator) {
            Err(IntervalError::DivisorContainsZero) => return Err(ZError::SingularCorrection),
            other => other?,
        };
        let amplitude = Interval::point(1.0, prec).div(&a.sqrt()?)?;
        let correction = amplitude.mul(&c0);
        // (-1)^(N-1): the correction is added for odd N and subtracted for even N.
        let correction =
            if n % 2 == 0 { Interval::point(0.0, prec).sub(&correction) } else { correction };
        let bound = gabcke_bound(lo, prec, self.multiplier)?;
        Ok(main.add(&correction).widen(bound.hi()))
    }

    /// x^(-s) = x^(-1/2) e^(-it ln x) for s = 1/2 + it.
    fn neg_power(&self, x: u64, height: &Interval) -> Result<Complex, IntervalError> {
        let x = Interval::point(x as f64, self.prec);
        let phase = height.mul(&x.ln()?);
        let amplitude = Interval::point(1.0, self.prec).div(&x.sqrt()?)?;
        Ok(Complex::cis(&Interval::point(0.0, self.prec).sub(&phase)).mul_real(&amplitude))
    }

    /// Johansson's bound 4 |(s)_2M| / (2 pi)^2M / ((2M - 1/2) n1^(2M - 1/2)),
    /// n1 = N + 1, as an upper bound.
    fn em_remainder(&self, height: &Interval, n1: u64) -> Result<Float, IntervalError> {
        let prec = self.prec;
        let mut rising = Interval::point(1.0, prec);
        for j in 0..2 * EM_TERMS {
            let re = Interval::point(0.5 + j as f64, prec);
            rising = rising.mul(&re.mul(&re).add(&height.mul(height)).sqrt()?);
        }
        let n1 = Interval::point(n1 as f64, prec);
        let n1_power = power(&n1, 2 * EM_TERMS - 1).mul(&n1.sqrt()?);
        Ok(self.em_remainder_scale.mul(&rising).div(&n1_power)?.hi().clone())
    }

    /// Z(t) by Euler-Maclaurin for zeta(1/2 + it) (Johansson 2015, Theorem 1,
    /// a = 1, no derivatives) with N = ceil(hi) + 2M direct terms (hi = t for a point) and M = 20.
    ///
    /// `t` must lie in `(0, EM_MAX_HEIGHT]`, else `HeightOutOfRange`. The remainder
    /// bound is added to both parts of zeta; a rotated imaginary part that excludes
    /// 0 is `ImaginaryPartNonzero`.
    pub fn euler_maclaurin(&self, t: f64) -> Result<EmEnclosure, ZError> {
        self.euler_maclaurin_over(t, t)
    }

    /// An enclosure of Z(t) for every t in `[lo, hi]` by Euler-Maclaurin, with N
    /// taken from `hi` (any N is valid; the remainder bound grows with t).
    ///
    /// `MIN_POSITIVE <= lo <= hi <= EM_MAX_HEIGHT` is required, else
    /// `HeightOutOfRange`; an interval (`lo < hi`) whose `lo` is below
    /// `THETA_MONOTONE_FROM` is also `HeightOutOfRange`.
    pub fn euler_maclaurin_over(&self, lo: f64, hi: f64) -> Result<EmEnclosure, ZError> {
        if !(f64::MIN_POSITIVE..=EM_MAX_HEIGHT).contains(&lo) || !(lo..=EM_MAX_HEIGHT).contains(&hi)
        {
            return Err(ZError::HeightOutOfRange);
        }
        let prec = self.prec;
        let height = height_interval(lo, hi, prec)?;
        let zero = Interval::point(0.0, prec);
        let half = Interval::point(0.5, prec);
        let n = hi.ceil() as u64 + 2 * EM_TERMS as u64;
        let n1 = n + 1;
        let s = Complex::new(half.clone(), height.clone());
        let mut direct = Complex::new(zero.clone(), zero.clone());
        for k in 1..=n {
            direct = direct.add(&self.neg_power(k, &height)?);
        }
        // (N+1)^(1-s) / (s-1), with s - 1 = -1/2 + it.
        let n1_point = Interval::point(n1 as f64, prec);
        let s_minus_one = Complex::new(Interval::point(-0.5, prec), height.clone());
        let n1_neg_s = self.neg_power(n1, &height)?;
        let pole = n1_neg_s.mul_real(&n1_point).div(&s_minus_one)?;
        // 1/2 + sum_k B_2k/(2k)! (s)_(2k-1) / (N+1)^(2k-1).
        let inv_n1 = Interval::point(1.0, prec).div(&n1_point)?;
        let inv_n1_sq = inv_n1.mul(&inv_n1);
        let mut bracket = Complex::new(half, zero);
        let mut rising = s.clone();
        let mut inv_power = inv_n1;
        for (index, coefficient) in self.em_coefficients.iter().enumerate() {
            bracket = bracket.add(&rising.mul_real(&inv_power).mul_real(coefficient));
            // (s)_(2k-1) -> (s)_(2k+1): times (s + 2k - 1)(s + 2k).
            let k = (index + 1) as f64;
            for shift in [2.0 * k - 1.0, 2.0 * k] {
                rising =
                    rising.mul(&Complex::new(Interval::point(0.5 + shift, prec), height.clone()));
            }
            inv_power = inv_power.mul(&inv_n1_sq);
        }
        let remainder = self.em_remainder(&height, n1)?;
        let zeta = direct.add(&pole).add(&n1_neg_s.mul(&bracket)).widen(&remainder);
        let z = hardy_z(&self.theta_over(lo, hi)?, &zeta)?;
        Ok(EmEnclosure { z, remainder })
    }

    /// Z(t): Riemann-Siegel from `MIN_RS_HEIGHT` (the exact `f64` height is its
    /// own lower bound), Euler-Maclaurin below it.
    pub fn try_z(&self, t: f64) -> Result<Interval, ZError> {
        self.try_z_over(t, t)
    }

    /// Z over `[lo, hi]`, dispatching on the lower end as `try_z` does on the height.
    pub fn try_z_over(&self, lo: f64, hi: f64) -> Result<Interval, ZError> {
        if lo >= MIN_RS_HEIGHT {
            self.riemann_siegel_over(lo, hi)
        } else {
            Ok(self.euler_maclaurin_over(lo, hi)?.z)
        }
    }
}

/// An implementation fault in a Z evaluation, as opposed to a refusal: the
/// verifier (plan Tasks 9–10) must surface it as an internal error (exit 6), never
/// as a merely uncertified height. `ZFault` never reaches the self-check: that runs
/// over `ZPaths`, where any `ZError` from either path (refusal or fault) becomes a
/// `SelfCheckFailure` and exit 5, since the self-check runs before any verdict.
#[derive(Debug, Clone, PartialEq)]
pub enum ZFault {
    /// The imaginary part of e^(i theta) zeta(1/2 + it) does not contain 0.
    ImaginaryPartNonzero,
    /// The height was NaN.
    NanHeight,
    /// The theta enclosure failed.
    Theta(ThetaError),
    /// An interval operation refused its operands.
    Interval(IntervalError),
}

impl std::fmt::Display for ZFault {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::ImaginaryPartNonzero => {
                f.write_str("imaginary part of e^(i theta) zeta does not contain 0")
            }
            Self::NanHeight => f.write_str("height is NaN"),
            Self::Theta(e) => write!(f, "theta failed: {e}"),
            Self::Interval(e) => write!(f, "interval arithmetic failed: {e}"),
        }
    }
}

impl std::error::Error for ZFault {}

/// A source of certified Z enclosures. `Ok(None)` is a refusal (the height
/// cannot be certified at this precision, so a caller may retry higher or give
/// up); `Err` is an implementation fault. Later stages take this trait so tests
/// can inject fakes.
pub trait ZSource {
    fn z(&self, t: f64, prec: u32) -> Result<Option<Interval>, ZFault>;

    /// An enclosure of Z(t) for every t in `[lo, hi]`, with the same refusal and
    /// fault convention as `z`. Required, so a source that cannot bound Z over an
    /// interval must say so by refusing rather than inherit a default.
    fn z_over(&self, lo: f64, hi: f64, prec: u32) -> Result<Option<Interval>, ZFault>;
}

/// Split a Z result into a refusal (`Ok(None)`) and a fault (`Err`).
fn refusal_or_fault(result: Result<Interval, ZError>) -> Result<Option<Interval>, ZFault> {
    match result {
        Ok(z) => Ok(Some(z)),
        Err(e) => e.into_fault().map_or(Ok(None), Err),
    }
}

/// A rung must at least halve the enclosure width to justify climbing further:
/// otherwise the width is dominated by truncation, not by working precision.
const MIN_WIDTH_SHRINK: f64 = 0.5;

/// The sign of a Z enclosure, certified at the first rung (within the cap of
/// `cfg`) whose `eval(prec)` excludes 0; `None` when no rung does. Climbing stops
/// once a rung fails to shrink the enclosure width by `MIN_WIDTH_SHRINK` (more
/// bits cannot help). A refusal carries no width and moves to the next rung. A
/// fault propagates. The one ladder for points and for intervals.
pub(crate) fn certified_sign_ladder<F>(
    cfg: &VerifyConfig,
    mut eval: F,
) -> Result<Option<Sign>, ZFault>
where
    F: FnMut(u32) -> Result<Option<Interval>, ZFault>,
{
    let mut previous_width: Option<f64> = None;
    for prec in PRECISION_RUNGS.into_iter().filter(|&p| p <= cfg.precision_cap()) {
        let Some(enclosure) = eval(prec)? else {
            continue;
        };
        if let Some(sign) = enclosure.sign() {
            return Ok(Some(sign));
        }
        let width = enclosure.width().to_f64();
        if let Some(previous) = previous_width
            && !matches!(
                width.partial_cmp(&(previous * MIN_WIDTH_SHRINK)),
                Some(Ordering::Less | Ordering::Equal)
            )
        {
            return Ok(None);
        }
        previous_width = Some(width);
    }
    Ok(None)
}

/// Precisions of the certification ladder; `RealZ` holds those up to the cap.
pub(crate) const PRECISION_RUNGS: [u32; 4] = [64, 128, 256, 512];

/// The real `ZSource`: one `ZEvaluator` per precision rung, built once.
#[derive(Debug, Clone)]
pub struct RealZ {
    evaluators: Vec<ZEvaluator>,
}

impl RealZ {
    /// Build an evaluator for each of 64, 128, 256, 512 bits not above
    /// `cfg.precision_cap()`.
    pub fn new(cfg: &VerifyConfig) -> Result<RealZ, ZError> {
        let evaluators = PRECISION_RUNGS
            .into_iter()
            .filter(|&prec| prec <= cfg.precision_cap())
            .map(|prec| ZEvaluator::new(prec, cfg))
            .collect::<Result<Vec<_>, _>>()?;
        Ok(RealZ { evaluators })
    }
}

impl ZSource for RealZ {
    /// NaN is a fault; a precision that is not a held rung, or a height that is
    /// out of range or not certifiable at that rung, is a refusal.
    fn z(&self, t: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
        if t.is_nan() {
            return Err(ZFault::NanHeight);
        }
        match self.evaluators.iter().find(|ev| ev.prec == prec) {
            Some(evaluator) => refusal_or_fault(evaluator.try_z(t)),
            None => Ok(None),
        }
    }

    /// NaN at either end is a fault; otherwise as `z`, with `lo > hi` a refusal.
    fn z_over(&self, lo: f64, hi: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
        if lo.is_nan() || hi.is_nan() {
            return Err(ZFault::NanHeight);
        }
        match self.evaluators.iter().find(|ev| ev.prec == prec) {
            Some(evaluator) => refusal_or_fault(evaluator.try_z_over(lo, hi)),
            None => Ok(None),
        }
    }
}

/// The two Z paths, separately reachable so the self-check can be faked.
pub trait ZPaths {
    fn riemann_siegel(&self, t: f64) -> Result<Interval, ZError>;
    fn euler_maclaurin(&self, t: f64) -> Result<EmEnclosure, ZError>;
}

impl ZPaths for ZEvaluator {
    fn riemann_siegel(&self, t: f64) -> Result<Interval, ZError> {
        ZEvaluator::riemann_siegel(self, t)
    }

    fn euler_maclaurin(&self, t: f64) -> Result<EmEnclosure, ZError> {
        ZEvaluator::euler_maclaurin(self, t)
    }
}

/// Precision of the self-check's limits; the paths under test must run at it too.
pub const SELF_CHECK_PREC: u32 = 128;

/// The eight heights of the self-check, all in [200, 300].
const SELF_CHECK_POINTS: [f64; 8] = [200.0, 214.5, 229.0, 243.5, 258.0, 272.5, 287.0, 300.0];

/// The first condition of the self-check that failed, and where.
#[derive(Debug, Clone, PartialEq)]
pub enum SelfCheckFailure {
    /// The two enclosures at `t` do not intersect.
    NoIntersection { t: f64 },
    /// The Euler-Maclaurin enclosure is wider than 1e-10.
    EulerMaclaurinTooWide { t: f64 },
    /// The Euler-Maclaurin enclosure is narrower than twice its stated remainder.
    EulerMaclaurinTooNarrow { t: f64 },
    /// The Riemann-Siegel enclosure is wider than 2 x 0.127 t^(-3/4) + 1e-10.
    RiemannSiegelTooWide { t: f64 },
    /// The Riemann-Siegel enclosure is narrower than 2 x 0.127 t^(-3/4).
    RiemannSiegelTooNarrow { t: f64 },
    /// The Riemann-Siegel path produced no enclosure at `t`.
    RiemannSiegelFailed { t: f64, error: ZError },
    /// The Euler-Maclaurin path produced no enclosure at `t`.
    EulerMaclaurinFailed { t: f64, error: ZError },
}

impl std::fmt::Display for SelfCheckFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NoIntersection { t } => write!(f, "enclosures do not intersect at t = {t}"),
            Self::EulerMaclaurinTooWide { t } => {
                write!(f, "Euler-Maclaurin enclosure wider than 1e-10 at t = {t}")
            }
            Self::EulerMaclaurinTooNarrow { t } => {
                write!(f, "Euler-Maclaurin enclosure narrower than its remainder at t = {t}")
            }
            Self::RiemannSiegelTooWide { t } => {
                write!(f, "Riemann-Siegel enclosure wider than its bound at t = {t}")
            }
            Self::RiemannSiegelTooNarrow { t } => {
                write!(f, "Riemann-Siegel enclosure narrower than its bound at t = {t}")
            }
            Self::RiemannSiegelFailed { t, error } => {
                write!(f, "Riemann-Siegel failed at t = {t}: {error}")
            }
            Self::EulerMaclaurinFailed { t, error } => {
                write!(f, "Euler-Maclaurin failed at t = {t}: {error}")
            }
        }
    }
}

impl std::error::Error for SelfCheckFailure {}

/// Check one height; see `self_check`.
fn self_check_point<P: ZPaths>(paths: &P, t: f64) -> Result<(), SelfCheckFailure> {
    let rs = paths
        .riemann_siegel(t)
        .map_err(|error| SelfCheckFailure::RiemannSiegelFailed { t, error })?;
    let em = paths
        .euler_maclaurin(t)
        .map_err(|error| SelfCheckFailure::EulerMaclaurinFailed { t, error })?;
    if rs.lo() > em.z.hi() || em.z.lo() > rs.hi() {
        return Err(SelfCheckFailure::NoIntersection { t });
    }
    let nano_tenth = Interval::point(1.0, SELF_CHECK_PREC)
        .div(&Interval::point(1e10, SELF_CHECK_PREC))
        .map_err(|e| SelfCheckFailure::RiemannSiegelFailed { t, error: e.into() })?;
    let em_width = em.z.width();
    if em_width > *nano_tenth.hi() {
        return Err(SelfCheckFailure::EulerMaclaurinTooWide { t });
    }
    if em_width < Float::with_val(em.remainder.prec(), &em.remainder * 2u32) {
        return Err(SelfCheckFailure::EulerMaclaurinTooNarrow { t });
    }
    // Always the unscaled 0.127, whatever the configured multiplier.
    let two_bound = gabcke_bound(t, SELF_CHECK_PREC, 1.0)
        .map_err(|error| SelfCheckFailure::RiemannSiegelFailed { t, error })?
        .mul(&Interval::point(2.0, SELF_CHECK_PREC));
    let rs_width = rs.width();
    if rs_width > *two_bound.add(&nano_tenth).hi() {
        return Err(SelfCheckFailure::RiemannSiegelTooWide { t });
    }
    if rs_width < *two_bound.lo() {
        return Err(SelfCheckFailure::RiemannSiegelTooNarrow { t });
    }
    Ok(())
}

/// Canary on the two Z paths at eight heights in [200, 300]: they must intersect,
/// Euler-Maclaurin must be at most 1e-10 wide and at least twice its stated
/// remainder, and Riemann-Siegel must lie within [2 b, 2 b + 1e-10] wide for
/// b = 0.127 t^(-3/4). The floors catch an implementation that drops a
/// truncation bound. Both paths share `theta`, so a theta error is invisible.
///
/// Callers must pass paths built with `VerifyConfig::default()` (multiplier 1) at
/// `SELF_CHECK_PREC`: the limits use the unscaled constant, so a multiplier
/// noticeably above 1 fails with `RiemannSiegelTooWide` (exit 5). The 1e-10 slack
/// admits a multiplier up to about 1 + 2e-8 at t = 200, the tightest point.
pub fn self_check<P: ZPaths>(paths: &P) -> Result<(), SelfCheckFailure> {
    SELF_CHECK_POINTS.iter().try_for_each(|&t| self_check_point(paths, t))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::complex::Complex;
    use crate::config::VerifyConfig;
    use crate::interval::{Interval, IntervalError, Sign};
    use crate::theta::ThetaError;
    use proptest::prelude::*;
    use rug::Float;

    const PREC: u32 = 128;

    fn evaluator() -> ZEvaluator {
        ZEvaluator::new(PREC, &VerifyConfig::default()).unwrap()
    }

    /// A reference value as an exact-enough MPFR float.
    fn reference(decimal: &str) -> Float {
        Float::with_val(256, Float::parse(decimal).unwrap())
    }

    fn contains(i: &Interval, r: &Float) -> bool {
        i.lo() <= r && r <= i.hi()
    }

    fn width_f64(i: &Interval) -> f64 {
        i.width().to_f64()
    }

    /// Gabcke's bound 0.127 t^(-3/4) in plain f64, for width checks to 1e-9 relative.
    fn gabcke_f64(t: f64) -> f64 {
        0.127 * t.powf(-0.75)
    }

    // Reference values: mpmath 1.4.1, `mp.dps = 60; nstr(siegelz(mpf(t)), 50)`, t an exact f64.
    const Z_200: &str = "5.5897836231501089613651582814243424451099714413616";
    const Z_250: &str = "-0.91863341835615242704537890685860604320384086356064";
    const Z_299: &str = "3.2608149954017572133548006827007371849276231509775";
    const Z_7005: &str = "0.0039670888106902280331020370958441865167050240526088";

    #[test]
    fn riemann_siegel_encloses_reference_values() {
        let ev = evaluator();
        for (t, z) in [(200.0, Z_200), (250.0, Z_250), (299.0, Z_299), (7005.0817, Z_7005)] {
            let enclosure = ev.riemann_siegel(t).unwrap();
            assert!(contains(&enclosure, &reference(z)), "RS at {t}: {enclosure:?}");
        }
    }

    #[test]
    fn riemann_siegel_width_is_twice_gabcke_bound() {
        let ev = evaluator();
        for t in [200.0, 250.0, 299.0, 7005.0817] {
            let w = width_f64(&ev.riemann_siegel(t).unwrap());
            let two_bound = 2.0 * gabcke_f64(t);
            assert!(w >= two_bound * (1.0 - 1e-9), "t={t}: width {w} below {two_bound}");
            assert!(w <= two_bound * (1.0 + 1e-9), "t={t}: width {w} above {two_bound}");
        }
    }

    #[test]
    fn riemann_siegel_certifies_lehmer_peak_positive() {
        // Lehmer's pair (7005.0629, 7005.1006): Z peaks at +0.003967 between the zeros.
        let enclosure = evaluator().riemann_siegel(7005.0817).unwrap();
        assert_eq!(enclosure.sign(), Some(Sign::Positive));
    }

    #[test]
    fn riemann_siegel_refuses_below_two_hundred() {
        let ev = evaluator();
        let just_below = f64::from_bits(200.0f64.to_bits() - 1);
        assert_eq!(ev.riemann_siegel(just_below).unwrap_err(), ZError::HeightOutOfRange);
        assert_eq!(ev.riemann_siegel(0.0).unwrap_err(), ZError::HeightOutOfRange);
        assert_eq!(ev.riemann_siegel(f64::NAN).unwrap_err(), ZError::HeightOutOfRange);
        assert!(ev.riemann_siegel(200.0).is_ok());
    }

    #[test]
    fn riemann_siegel_refuses_beyond_the_evaluator_s_table() {
        let ev = evaluator();
        assert_eq!(ev.riemann_siegel(f64::INFINITY).unwrap_err(), ZError::HeightOutOfRange);
        let beyond = f64::from_bits(DEFAULT_MAX_HEIGHT.to_bits() + 1);
        assert_eq!(ev.riemann_siegel(beyond).unwrap_err(), ZError::HeightOutOfRange);
        let small = ZEvaluator::with_max_height(PREC, &VerifyConfig::default(), 300.0).unwrap();
        assert!(small.riemann_siegel(300.0).is_ok());
        let just_above = f64::from_bits(300.0f64.to_bits() + 1);
        assert_eq!(small.riemann_siegel(just_above).unwrap_err(), ZError::HeightOutOfRange);
    }

    #[test]
    fn with_max_height_rejects_unusable_limits() {
        let cfg = VerifyConfig::default();
        let just_below = f64::from_bits(MIN_RS_HEIGHT.to_bits() - 1);
        let just_above = f64::from_bits(MAX_HEIGHT.to_bits() + 1);
        for limit in [f64::NAN, just_below, just_above, 0.0, f64::INFINITY] {
            let err = ZEvaluator::with_max_height(PREC, &cfg, limit).unwrap_err();
            assert_eq!(err, ZError::HeightOutOfRange, "limit = {limit}");
        }
        assert!(ZEvaluator::with_max_height(PREC, &cfg, MIN_RS_HEIGHT).is_ok());
    }

    #[test]
    fn tables_hold_ln_k_and_inverse_sqrt_k_up_to_the_limit() {
        // floor(sqrt(300 / 2 pi)) + 1 = 7 entries.
        let ev = ZEvaluator::with_max_height(PREC, &VerifyConfig::default(), 300.0).unwrap();
        assert_eq!(ev.ln_k.len(), 7);
        assert_eq!(ev.inv_sqrt_k.len(), 7);
        for (index, (ln, inv)) in ev.ln_k.iter().zip(&ev.inv_sqrt_k).enumerate() {
            let k = (index + 1) as f64;
            for (value, want) in [(ln, k.ln()), (inv, 1.0 / k.sqrt())] {
                assert!((value.lo().to_f64() - want).abs() < 1e-15, "k = {k}");
                assert!((value.hi().to_f64() - want).abs() < 1e-15, "k = {k}");
                assert!(value.lo() <= value.hi());
            }
        }
    }

    #[test]
    fn riemann_siegel_refuses_an_ambiguous_split() {
        // t = 2 pi 10^2 puts a = sqrt(t / 2 pi) on the integer 10; at 30 bits the
        // enclosure of a straddles it, so N = floor(a) is not certified.
        let ev = ZEvaluator::new(30, &VerifyConfig::default()).unwrap();
        let t = 2.0 * std::f64::consts::PI * 100.0;
        assert_eq!(ev.riemann_siegel(t).unwrap_err(), ZError::AmbiguousSplit);
    }

    #[test]
    fn riemann_siegel_refuses_the_removable_singularity() {
        // a = 10.25 gives p = 1/4, where cos(2 pi p) = 0; at 30 bits the enclosure holds 0.
        let ev = ZEvaluator::new(30, &VerifyConfig::default()).unwrap();
        let t = 2.0 * std::f64::consts::PI * 10.25 * 10.25;
        assert_eq!(ev.riemann_siegel(t).unwrap_err(), ZError::SingularCorrection);
    }

    #[test]
    fn multiplier_widens_riemann_siegel_by_the_scaled_bound() {
        let base = evaluator();
        let scaled =
            ZEvaluator::new(PREC, &VerifyConfig::new(3.0, 512, 40, true).unwrap()).unwrap();
        let t = 250.0;
        let (one, three) = (base.riemann_siegel(t).unwrap(), scaled.riemann_siegel(t).unwrap());
        // Each side grows by (3 - 1) x 0.127 t^(-3/4).
        let grow = 2.0 * gabcke_f64(t);
        let lo_shift = Float::with_val(PREC, one.lo() - three.lo()).to_f64();
        let hi_shift = Float::with_val(PREC, three.hi() - one.hi()).to_f64();
        assert!((lo_shift - grow).abs() < grow * 1e-9, "lo grew {lo_shift}, want {grow}");
        assert!((hi_shift - grow).abs() < grow * 1e-9, "hi grew {hi_shift}, want {grow}");
    }

    const Z_20: &str = "1.147842412185197277635034087179664116972641409744";
    const Z_100: &str = "2.6926970566644634749953798286850324206190216376727";

    #[test]
    fn euler_maclaurin_encloses_reference_values() {
        let ev = evaluator();
        for (t, z) in [(20.0, Z_20), (100.0, Z_100), (200.0, Z_200), (250.0, Z_250), (299.0, Z_299)]
        {
            let enclosure = ev.euler_maclaurin(t).unwrap().z;
            assert!(contains(&enclosure, &reference(z)), "EM at {t}: {enclosure:?}");
        }
    }

    #[test]
    fn euler_maclaurin_signs_around_the_first_zeros() {
        // mpmath siegelz: -0.1056 at 14.0, +0.1328 at 14.3, +0.0251 at 21.0,
        // -0.0882 at 21.1, -0.0149 at 25.0, +0.1236 at 25.1.
        let ev = evaluator();
        let cases = [
            (14.0, Sign::Negative),
            (14.3, Sign::Positive),
            (21.0, Sign::Positive),
            (21.1, Sign::Negative),
            (25.0, Sign::Negative),
            (25.1, Sign::Positive),
        ];
        for (t, sign) in cases {
            assert_eq!(ev.euler_maclaurin(t).unwrap().z.sign(), Some(sign), "t = {t}");
        }
    }

    #[test]
    fn euler_maclaurin_remainder_is_johanssons_bound() {
        // N = ceil(t) + 40, M = 20; mpmath: 4 |(s)_40| / (2 pi)^40 / (39.5 (N+1)^39.5).
        let ev = evaluator();
        for (t, want) in
            [(14.0, 3.56038148096e-47), (100.0, 4.23265929248e-38), (299.0, 1.45623499676e-34)]
        {
            let got = ev.euler_maclaurin(t).unwrap().remainder.to_f64();
            assert!((got - want).abs() < want * 1e-6, "t = {t}: {got} vs {want}");
        }
    }

    #[test]
    fn euler_maclaurin_width_covers_twice_the_remainder() {
        let ev = evaluator();
        for t in [20.0, 100.0, 250.0] {
            let em = ev.euler_maclaurin(t).unwrap();
            let two_r = Float::with_val(PREC, &em.remainder * 2u32);
            assert!(em.z.width() >= two_r, "t = {t}");
            assert!(width_f64(&em.z) < 1e-10, "t = {t}");
        }
    }

    #[test]
    fn euler_maclaurin_refuses_out_of_range_heights() {
        let ev = evaluator();
        for t in [0.0, -1.0, f64::NAN, f64::INFINITY, EM_MAX_HEIGHT * 1.0000001] {
            assert_eq!(ev.euler_maclaurin(t).unwrap_err(), ZError::HeightOutOfRange, "t = {t}");
        }
    }

    #[test]
    fn euler_maclaurin_range_boundaries_are_inclusive_and_exact() {
        let ev = evaluator();
        assert!(ev.euler_maclaurin(EM_MAX_HEIGHT).is_ok());
        assert!(ev.euler_maclaurin(f64::MIN_POSITIVE).is_ok());
        let above = f64::from_bits(EM_MAX_HEIGHT.to_bits() + 1);
        assert_eq!(ev.euler_maclaurin(above).unwrap_err(), ZError::HeightOutOfRange);
        let below = f64::from_bits(f64::MIN_POSITIVE.to_bits() - 1);
        assert_eq!(ev.euler_maclaurin(below).unwrap_err(), ZError::HeightOutOfRange);
    }

    #[test]
    fn gabcke_bound_rejects_non_positive_and_nan_heights() {
        for t in [0.0, -1.0, f64::NAN] {
            let err = gabcke_bound(t, PREC, 1.0).unwrap_err();
            assert_eq!(err, ZError::Interval(IntervalError::LogOfNonPositive), "t = {t}");
        }
    }

    #[test]
    fn hardy_z_takes_the_real_part_when_the_imaginary_part_vanishes() {
        // theta = 0: Z = Re(zeta); a zeta of 3 + [-1, 1] i has Im containing 0.
        let zeta = Complex::new(
            Interval::point(3.0, PREC),
            Interval::new(Float::with_val(PREC, -1), Float::with_val(PREC, 1)).unwrap(),
        );
        let z = hardy_z(&Interval::point(0.0, PREC), &zeta).unwrap();
        assert_eq!(z.lo().to_f64(), 3.0);
        assert_eq!(z.hi().to_f64(), 3.0);
    }

    #[test]
    fn hardy_z_rejects_a_nonzero_imaginary_part() {
        // theta = 0 and zeta = 1 + i: e^(i theta) zeta has imaginary part exactly 1.
        let zeta = Complex::new(Interval::point(1.0, PREC), Interval::point(1.0, PREC));
        let err = hardy_z(&Interval::point(0.0, PREC), &zeta).unwrap_err();
        assert_eq!(err, ZError::ImaginaryPartNonzero);
    }

    #[test]
    fn hardy_z_rejects_an_imaginary_part_just_below_zero_and_above_zero() {
        for im in [-1e-9, 1e-9] {
            let zeta = Complex::new(Interval::point(1.0, PREC), Interval::point(im, PREC));
            assert_eq!(
                hardy_z(&Interval::point(0.0, PREC), &zeta).unwrap_err(),
                ZError::ImaginaryPartNonzero
            );
        }
    }

    #[test]
    fn hardy_z_accepts_an_imaginary_part_touching_zero() {
        for (lo, hi) in [(-1.0, 0.0), (0.0, 1.0)] {
            let zeta = Complex::new(
                Interval::point(1.0, PREC),
                Interval::new(Float::with_val(PREC, lo), Float::with_val(PREC, hi)).unwrap(),
            );
            assert!(hardy_z(&Interval::point(0.0, PREC), &zeta).is_ok(), "[{lo}, {hi}]");
        }
    }

    #[test]
    fn riemann_siegel_accepts_the_height_limit() {
        let ev = ZEvaluator::with_max_height(PREC, &VerifyConfig::default(), MAX_HEIGHT).unwrap();
        assert!(ev.riemann_siegel(MAX_HEIGHT).is_ok());
        let beyond = f64::from_bits(MAX_HEIGHT.to_bits() + 1);
        assert_eq!(ev.riemann_siegel(beyond).unwrap_err(), ZError::HeightOutOfRange);
    }

    #[test]
    fn evaluator_rejects_a_precision_beyond_theta_s_limit() {
        let err = ZEvaluator::new(crate::theta::MAX_PREC + 1, &VerifyConfig::default());
        assert_eq!(err.unwrap_err(), ZError::Theta(ThetaError::PrecisionOutOfRange));
    }

    #[test]
    fn z_uses_euler_maclaurin_below_two_hundred_and_riemann_siegel_from_it() {
        let ev = evaluator();
        let just_below = f64::from_bits(200.0f64.to_bits() - 1);
        // Euler-Maclaurin is far narrower than Gabcke's 2.4e-3 band.
        assert!(width_f64(&ev.try_z(just_below).unwrap()) < 1e-10);
        let at_boundary = width_f64(&ev.try_z(200.0).unwrap());
        assert!(at_boundary > 2.0 * gabcke_f64(200.0) * (1.0 - 1e-9));
    }

    #[test]
    fn z_signs_at_lehmer_peak_and_first_zeros() {
        let ev = evaluator();
        assert_eq!(ev.try_z(7005.0817).unwrap().sign(), Some(Sign::Positive));
        assert_eq!(ev.try_z(14.0).unwrap().sign(), Some(Sign::Negative));
        assert_eq!(ev.try_z(14.3).unwrap().sign(), Some(Sign::Positive));
    }

    #[test]
    fn z_refuses_unusable_heights() {
        let ev = evaluator();
        for t in [0.0, -5.0, f64::NAN, f64::INFINITY, MAX_HEIGHT * 1.0000001] {
            assert_eq!(ev.try_z(t).unwrap_err(), ZError::HeightOutOfRange, "t = {t}");
        }
    }

    #[test]
    fn refusals_are_distinguished_from_faults() {
        assert!(ZError::HeightOutOfRange.is_refusal());
        assert!(ZError::AmbiguousSplit.is_refusal());
        assert!(ZError::SingularCorrection.is_refusal());
        assert!(!ZError::ImaginaryPartNonzero.is_refusal());
        assert!(!ZError::Theta(ThetaError::HeightNotPositive).is_refusal());
        assert!(!ZError::Interval(IntervalError::NotANumber).is_refusal());
    }

    #[test]
    fn z_errors_display_distinct_messages() {
        let errors = [
            ZError::HeightOutOfRange,
            ZError::AmbiguousSplit,
            ZError::SingularCorrection,
            ZError::ImaginaryPartNonzero,
            ZError::Theta(ThetaError::HeightNotPositive),
            ZError::Interval(IntervalError::NotANumber),
        ];
        let texts: Vec<String> = errors.iter().map(ToString::to_string).collect();
        for (i, a) in texts.iter().enumerate() {
            assert!(!a.is_empty());
            for b in &texts[i + 1..] {
                assert_ne!(a, b);
            }
        }
        assert!(texts[4].contains("theta") && texts[5].contains("interval"));
    }

    // ---- self-check ----------------------------------------------------

    type RsFn = Box<dyn Fn(f64) -> Result<Interval, ZError>>;
    type EmFn = Box<dyn Fn(f64) -> Result<EmEnclosure, ZError>>;

    /// Injectable paths; records every call.
    struct Fake {
        rs: RsFn,
        em: EmFn,
        calls: std::cell::RefCell<Vec<(&'static str, f64)>>,
    }

    impl ZPaths for Fake {
        fn riemann_siegel(&self, t: f64) -> Result<Interval, ZError> {
            self.calls.borrow_mut().push(("rs", t));
            (self.rs)(t)
        }

        fn euler_maclaurin(&self, t: f64) -> Result<EmEnclosure, ZError> {
            self.calls.borrow_mut().push(("em", t));
            (self.em)(t)
        }
    }

    fn fake(rs: RsFn, em: EmFn) -> Fake {
        Fake { rs, em, calls: std::cell::RefCell::new(Vec::new()) }
    }

    fn iv(lo: &Float, hi: &Float) -> Interval {
        Interval::new(lo.clone(), hi.clone()).unwrap()
    }

    fn f(x: f64) -> Float {
        Float::with_val(PREC, x)
    }

    /// 2 x Gabcke's unscaled bound at t, lower and upper ends.
    fn two_bound(t: f64) -> Interval {
        gabcke_bound(t, PREC, 1.0).unwrap().mul(&Interval::point(2.0, PREC))
    }

    fn tenth_nano() -> Interval {
        Interval::point(1.0, PREC).div(&Interval::point(1e10, PREC)).unwrap()
    }

    /// An RS path whose enclosure is [0, width(t)].
    fn rs_width(width: fn(f64) -> Float) -> RsFn {
        Box::new(move |t| Ok(iv(&f(0.0), &width(t))))
    }

    /// An EM path whose enclosure is [-width, 0] with the given stated remainder.
    fn em_width(width: Float, remainder: f64) -> EmFn {
        Box::new(move |_| {
            Ok(EmEnclosure { z: iv(&-width.clone(), &f(0.0)), remainder: f(remainder) })
        })
    }

    fn rs_floor(t: f64) -> Float {
        two_bound(t).lo().clone()
    }

    fn rs_ceiling(t: f64) -> Float {
        two_bound(t).add(&tenth_nano()).hi().clone()
    }

    fn passing() -> Fake {
        fake(rs_width(rs_floor), em_width(f(1e-11), 1e-12))
    }

    #[test]
    fn self_check_passes_on_the_real_paths() {
        assert_eq!(self_check(&evaluator()), Ok(()));
    }

    #[test]
    fn self_check_evaluates_both_paths_at_eight_points_in_range() {
        let fake = passing();
        self_check(&fake).unwrap();
        let calls = fake.calls.borrow();
        for path in ["rs", "em"] {
            let mut ts: Vec<f64> = calls.iter().filter(|c| c.0 == path).map(|c| c.1).collect();
            assert_eq!(ts.len(), 8, "{path}");
            assert!(ts.iter().all(|t| (200.0..=300.0).contains(t)));
            ts.sort_by(f64::total_cmp);
            ts.dedup();
            assert_eq!(ts.len(), 8, "{path} points must be distinct");
        }
        assert_eq!(calls.iter().filter(|c| c.0 == "rs").count(), 8);
    }

    #[test]
    fn self_check_fails_when_the_enclosures_do_not_intersect() {
        let fake =
            fake(Box::new(|t| Ok(iv(&f(1.0), &(f(1.0) + rs_floor(t))))), em_width(f(1e-11), 1e-12));
        assert!(matches!(self_check(&fake), Err(SelfCheckFailure::NoIntersection { .. })));
    }

    #[test]
    fn self_check_accepts_enclosures_that_only_touch() {
        // passing() has em = [-1e-11, 0] and rs = [0, floor]: they share the point 0.
        assert_eq!(self_check(&passing()), Ok(()));
    }

    /// An Euler-Maclaurin path whose enclosure is [lo, lo + 1e-11] (remainder 1e-12).
    fn em_from(lo: f64) -> EmFn {
        Box::new(move |_| {
            Ok(EmEnclosure { z: iv(&f(lo), &(f(lo) + f(1e-11))), remainder: f(1e-12) })
        })
    }

    #[test]
    fn self_check_handles_euler_maclaurin_above_riemann_siegel() {
        // rs = [-floor, 0]; em touching at 0 passes, em just above 0 is disjoint.
        let rs_below = || -> RsFn { Box::new(|t| Ok(iv(&-rs_floor(t), &f(0.0)))) };
        assert_eq!(self_check(&fake(rs_below(), em_from(0.0))), Ok(()));
        let apart = fake(rs_below(), em_from(1e-11));
        assert!(matches!(self_check(&apart), Err(SelfCheckFailure::NoIntersection { .. })));
    }

    #[test]
    fn self_check_fails_when_euler_maclaurin_is_too_wide() {
        let fake = fake(rs_width(rs_floor), em_width(f(2e-10), 1e-12));
        assert!(matches!(self_check(&fake), Err(SelfCheckFailure::EulerMaclaurinTooWide { .. })));
    }

    #[test]
    fn self_check_accepts_euler_maclaurin_exactly_at_the_ceiling() {
        let ceiling = tenth_nano().hi().clone();
        assert_eq!(self_check(&fake(rs_width(rs_floor), em_width(ceiling, 1e-13))), Ok(()));
    }

    #[test]
    fn self_check_fails_when_euler_maclaurin_is_narrower_than_its_remainder() {
        let fake = fake(rs_width(rs_floor), em_width(f(1e-12), 1e-12));
        assert!(matches!(self_check(&fake), Err(SelfCheckFailure::EulerMaclaurinTooNarrow { .. })));
    }

    #[test]
    fn self_check_accepts_euler_maclaurin_exactly_twice_its_remainder() {
        assert_eq!(self_check(&fake(rs_width(rs_floor), em_width(f(2e-12), 1e-12))), Ok(()));
    }

    #[test]
    fn self_check_fails_when_riemann_siegel_is_too_wide() {
        let fake = fake(rs_width(|_| Float::with_val(PREC, 1)), em_width(f(1e-11), 1e-12));
        assert!(matches!(self_check(&fake), Err(SelfCheckFailure::RiemannSiegelTooWide { .. })));
    }

    #[test]
    fn self_check_accepts_riemann_siegel_exactly_at_the_ceiling() {
        assert_eq!(self_check(&fake(rs_width(rs_ceiling), em_width(f(1e-11), 1e-12))), Ok(()));
    }

    #[test]
    fn self_check_fails_when_riemann_siegel_drops_its_widening() {
        let fake = fake(rs_width(|_| Float::with_val(PREC, 1e-20)), em_width(f(1e-11), 1e-12));
        assert!(matches!(self_check(&fake), Err(SelfCheckFailure::RiemannSiegelTooNarrow { .. })));
    }

    #[test]
    fn self_check_fails_just_below_the_riemann_siegel_floor() {
        let fake = fake(
            Box::new(|t| Ok(iv(&f(0.0), &(rs_floor(t) * 0.999_999f64)))),
            em_width(f(1e-11), 1e-12),
        );
        assert!(matches!(self_check(&fake), Err(SelfCheckFailure::RiemannSiegelTooNarrow { .. })));
    }

    #[test]
    fn self_check_accepts_riemann_siegel_exactly_at_the_floor() {
        // rs_width(rs_floor) is exactly 2 x bound.lo wide, and passing() uses it.
        assert_eq!(self_check(&passing()), Ok(()));
    }

    #[test]
    fn self_check_reports_a_failed_path() {
        let rs_down = fake(Box::new(|_| Err(ZError::AmbiguousSplit)), em_width(f(1e-11), 1e-12));
        assert_eq!(
            self_check(&rs_down),
            Err(SelfCheckFailure::RiemannSiegelFailed { t: 200.0, error: ZError::AmbiguousSplit })
        );
        let em_down = fake(rs_width(rs_floor), Box::new(|_| Err(ZError::HeightOutOfRange)));
        assert_eq!(
            self_check(&em_down),
            Err(SelfCheckFailure::EulerMaclaurinFailed {
                t: 200.0,
                error: ZError::HeightOutOfRange
            })
        );
    }

    #[test]
    fn self_check_always_uses_the_unscaled_constant() {
        // A multiplier of 1000 widens RS to about 1000 x the unscaled bound: too wide.
        let cfg = VerifyConfig::new(1000.0, 512, 40, true).unwrap();
        let scaled = ZEvaluator::new(PREC, &cfg).unwrap();
        assert!(matches!(self_check(&scaled), Err(SelfCheckFailure::RiemannSiegelTooWide { .. })));
    }

    #[test]
    fn self_check_failures_display_distinct_messages() {
        let t = 200.0;
        let failures = [
            SelfCheckFailure::NoIntersection { t },
            SelfCheckFailure::EulerMaclaurinTooWide { t },
            SelfCheckFailure::EulerMaclaurinTooNarrow { t },
            SelfCheckFailure::RiemannSiegelTooWide { t },
            SelfCheckFailure::RiemannSiegelTooNarrow { t },
            SelfCheckFailure::RiemannSiegelFailed { t, error: ZError::AmbiguousSplit },
            SelfCheckFailure::EulerMaclaurinFailed { t, error: ZError::AmbiguousSplit },
        ];
        let texts: Vec<String> = failures.iter().map(ToString::to_string).collect();
        for (i, a) in texts.iter().enumerate() {
            assert!(a.contains("200"), "{a}");
            for b in &texts[i + 1..] {
                assert_ne!(a, b);
            }
        }
        assert!(texts[5].contains("height") || texts[5].contains("floor"));
    }

    // ---- RealZ and the fault/refusal split -----------------------------

    /// t = f64 nearest 2 pi 917^2: a = sqrt(t / 2 pi) sits 3.4e-21 (relative) from the
    /// integer 917, inside a 64-bit enclosure of a but outside a 128-bit one.
    const T_AMBIGUOUS_AT_64: f64 = 5283461.409768935;

    fn real_z(cap: u32) -> RealZ {
        RealZ::new(&VerifyConfig::new(1.0, cap, 40, true).unwrap()).unwrap()
    }

    #[test]
    fn each_z_error_maps_to_a_refusal_or_a_fault() {
        let interval = Interval::point(1.0, PREC);
        assert!(refusal_or_fault(Ok(interval)).unwrap().is_some());
        for refusal in
            [ZError::HeightOutOfRange, ZError::AmbiguousSplit, ZError::SingularCorrection]
        {
            assert!(refusal_or_fault(Err(refusal)).unwrap().is_none());
        }
        let theta = ThetaError::HeightNotPositive;
        let interval = IntervalError::NotANumber;
        let faults = [
            (ZError::ImaginaryPartNonzero, ZFault::ImaginaryPartNonzero),
            (ZError::Theta(theta.clone()), ZFault::Theta(theta)),
            (ZError::Interval(interval.clone()), ZFault::Interval(interval)),
        ];
        for (error, fault) in faults {
            assert_eq!(refusal_or_fault(Err(error)).unwrap_err(), fault);
        }
    }

    #[test]
    fn zfault_displays_distinct_messages() {
        let faults = [
            ZFault::ImaginaryPartNonzero,
            ZFault::NanHeight,
            ZFault::Theta(ThetaError::HeightNotPositive),
            ZFault::Interval(IntervalError::NotANumber),
        ];
        let texts: Vec<String> = faults.iter().map(ToString::to_string).collect();
        for (i, a) in texts.iter().enumerate() {
            assert!(!a.is_empty());
            for b in &texts[i + 1..] {
                assert_ne!(a, b);
            }
        }
        assert!(texts[2].contains("theta") && texts[3].contains("interval"));
    }

    #[test]
    fn real_z_certifies_through_the_source_trait() {
        let real = real_z(512);
        let source: &dyn ZSource = &real;
        let sign = |t, prec| source.z(t, prec).unwrap().unwrap().sign();
        assert_eq!(sign(7005.0817, 128), Some(Sign::Positive));
        assert_eq!(sign(14.0, 64), Some(Sign::Negative));
        assert_eq!(sign(14.3, 512), Some(Sign::Positive));
    }

    #[test]
    fn real_z_reports_a_nan_height_as_a_fault() {
        let real = real_z(512);
        assert_eq!(real.z(f64::NAN, 128).unwrap_err(), ZFault::NanHeight);
        // Checked before the rung lookup: a held-nowhere precision still faults.
        assert_eq!(real.z(f64::NAN, 77).unwrap_err(), ZFault::NanHeight);
    }

    #[test]
    fn real_z_refuses_unusable_heights_without_a_fault() {
        let real = real_z(512);
        for t in [0.0, -5.0, f64::INFINITY, f64::NEG_INFINITY, MAX_HEIGHT * 1.0000001] {
            assert!(real.z(t, 128).unwrap().is_none(), "t = {t}");
        }
    }

    #[test]
    fn real_z_picks_the_evaluator_of_the_requested_rung() {
        let real = real_z(512);
        // Ambiguous floor at 64 bits (refusal, not a fault), certified at 128 and up.
        assert!(real.z(T_AMBIGUOUS_AT_64, 64).unwrap().is_none());
        assert!(real.z(T_AMBIGUOUS_AT_64, 128).unwrap().is_some());
        assert!(real.z(T_AMBIGUOUS_AT_64, 512).unwrap().is_some());
    }

    #[test]
    fn real_z_holds_exactly_the_rungs_up_to_the_cap() {
        let capped = real_z(128);
        assert!(capped.z(250.0, 64).unwrap().is_some());
        assert!(capped.z(250.0, 128).unwrap().is_some());
        assert!(capped.z(250.0, 256).unwrap().is_none());
        assert!(capped.z(250.0, 512).unwrap().is_none());
        // A precision that is not a rung is not held.
        assert!(capped.z(250.0, 100).unwrap().is_none());
        let floor = real_z(64);
        assert!(floor.z(250.0, 64).unwrap().is_some());
        assert!(floor.z(250.0, 128).unwrap().is_none());
        let full = real_z(512);
        assert!(full.z(250.0, 256).unwrap().is_some());
        assert!(full.z(250.0, 512).unwrap().is_some());
    }

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(8))]

        /// Both paths enclose the true Z(t), so they overlap, and any sign both
        /// certify is the same.
        #[test]
        fn riemann_siegel_and_euler_maclaurin_agree(t in 200.0f64..400.0) {
            let ev = evaluator();
            let rs = ev.riemann_siegel(t).unwrap();
            let em = ev.euler_maclaurin(t).unwrap().z;
            prop_assert!(rs.lo() <= em.hi() && em.lo() <= rs.hi());
            if let (Some(a), Some(b)) = (rs.sign(), em.sign()) {
                prop_assert_eq!(a, b);
            }
        }
    }
}
