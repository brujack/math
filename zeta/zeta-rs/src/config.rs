//! Widen-only verification settings.
//!
//! This module admits only settings that make certification harder or equal.
//! The caller contract: downstream code must be monotone in each setting, so
//! a larger multiplier, a lower precision cap, a lower depth cap or fixed
//! points can only widen enclosures or remove rescues, never narrow them.

use std::fmt;

/// Smallest accepted Gabcke multiplier, and its default.
pub const MIN_GABCKE_MULTIPLIER: f64 = 1.0;
/// Smallest accepted precision cap in bits.
pub const MIN_PRECISION_CAP: u32 = 64;
/// Largest accepted precision cap in bits, and its default.
pub const MAX_PRECISION_CAP: u32 = 512;
/// Largest accepted depth cap, and its default.
pub const MAX_DEPTH_CAP: u32 = 40;

/// Why a [`VerifyConfig`] was rejected.
///
/// The multiplier's value is not carried: `f64` is not `Eq`, and NaN has no
/// useful value to report.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConfigError {
    /// The Gabcke multiplier was NaN or infinite.
    MultiplierNotFinite,
    /// The Gabcke multiplier was below [`MIN_GABCKE_MULTIPLIER`], which would narrow the bounds.
    MultiplierBelowOne,
    /// The precision cap was below [`MIN_PRECISION_CAP`].
    PrecisionCapTooLow(u32),
    /// The precision cap was above [`MAX_PRECISION_CAP`].
    PrecisionCapTooHigh(u32),
    /// The depth cap was above [`MAX_DEPTH_CAP`].
    DepthCapTooHigh(u32),
}

impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MultiplierNotFinite => write!(f, "gabcke multiplier is not finite"),
            Self::MultiplierBelowOne => {
                write!(f, "gabcke multiplier below minimum {MIN_GABCKE_MULTIPLIER}")
            }
            Self::PrecisionCapTooLow(p) => {
                write!(f, "precision cap {p} below minimum {MIN_PRECISION_CAP}")
            }
            Self::PrecisionCapTooHigh(p) => {
                write!(f, "precision cap {p} above maximum {MAX_PRECISION_CAP}")
            }
            Self::DepthCapTooHigh(d) => write!(f, "depth cap {d} above maximum {MAX_DEPTH_CAP}"),
        }
    }
}

impl std::error::Error for ConfigError {}

/// Verification settings. Fields are private so only [`VerifyConfig::new`]
/// can build a non-default value.
#[derive(Debug, Clone, PartialEq)]
pub struct VerifyConfig {
    gabcke_multiplier: f64,
    precision_cap: u32,
    depth_cap: u32,
    move_points: bool,
}

impl Default for VerifyConfig {
    fn default() -> Self {
        Self {
            gabcke_multiplier: MIN_GABCKE_MULTIPLIER,
            precision_cap: MAX_PRECISION_CAP,
            depth_cap: MAX_DEPTH_CAP,
            move_points: true,
        }
    }
}

impl VerifyConfig {
    /// Builds a config, rejecting any setting that would make certification easier.
    ///
    /// Accepted: multiplier finite and at least [`MIN_GABCKE_MULTIPLIER`];
    /// precision cap in [`MIN_PRECISION_CAP`]..=[`MAX_PRECISION_CAP`]; depth cap
    /// at most [`MAX_DEPTH_CAP`] (0 is allowed: it only removes subdivision,
    /// which is harder). `move_points == false` removes a rescue, so it is allowed.
    pub fn new(
        gabcke_multiplier: f64,
        precision_cap: u32,
        depth_cap: u32,
        move_points: bool,
    ) -> Result<Self, ConfigError> {
        if !gabcke_multiplier.is_finite() {
            return Err(ConfigError::MultiplierNotFinite);
        }
        if gabcke_multiplier < MIN_GABCKE_MULTIPLIER {
            return Err(ConfigError::MultiplierBelowOne);
        }
        if precision_cap < MIN_PRECISION_CAP {
            return Err(ConfigError::PrecisionCapTooLow(precision_cap));
        }
        if precision_cap > MAX_PRECISION_CAP {
            return Err(ConfigError::PrecisionCapTooHigh(precision_cap));
        }
        if depth_cap > MAX_DEPTH_CAP {
            return Err(ConfigError::DepthCapTooHigh(depth_cap));
        }
        Ok(Self { gabcke_multiplier, precision_cap, depth_cap, move_points })
    }

    /// Multiplier on the Gabcke error bound; callers must apply it with
    /// rounding toward +infinity so it can only widen the bound.
    pub fn gabcke_multiplier(&self) -> f64 {
        self.gabcke_multiplier
    }

    pub fn precision_cap(&self) -> u32 {
        self.precision_cap
    }

    pub fn depth_cap(&self) -> u32 {
        self.depth_cap
    }

    pub fn move_points(&self) -> bool {
        self.move_points
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_multiplier_below_one() {
        for m in [0.5, 0.0, -1.0, 1.0 - f64::EPSILON / 2.0, 0.999_999_999] {
            assert_eq!(
                VerifyConfig::new(m, 512, 40, true),
                Err(ConfigError::MultiplierBelowOne),
                "{m}"
            );
        }
    }

    #[test]
    fn rejects_non_finite_multiplier() {
        for m in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert_eq!(
                VerifyConfig::new(m, 512, 40, true),
                Err(ConfigError::MultiplierNotFinite),
                "{m}"
            );
        }
    }

    #[test]
    fn rejects_precision_cap_below_64() {
        for p in [0, 1, MIN_PRECISION_CAP - 1] {
            assert_eq!(
                VerifyConfig::new(1.0, p, 40, true),
                Err(ConfigError::PrecisionCapTooLow(p))
            );
        }
    }

    #[test]
    fn rejects_precision_cap_above_512() {
        for p in [MAX_PRECISION_CAP + 1, u32::MAX] {
            assert_eq!(
                VerifyConfig::new(1.0, p, 40, true),
                Err(ConfigError::PrecisionCapTooHigh(p))
            );
        }
    }

    #[test]
    fn rejects_depth_cap_above_40() {
        for d in [MAX_DEPTH_CAP + 1, u32::MAX] {
            assert_eq!(VerifyConfig::new(1.0, 512, d, true), Err(ConfigError::DepthCapTooHigh(d)));
        }
    }

    #[test]
    fn accepts_boundary_values() {
        for (m, p, d) in [
            (MIN_GABCKE_MULTIPLIER, MAX_PRECISION_CAP, MAX_DEPTH_CAP),
            (1.0, MIN_PRECISION_CAP, 0),
            (1e300, MIN_PRECISION_CAP + 1, 1),
            (2.5, MAX_PRECISION_CAP - 1, MAX_DEPTH_CAP - 1),
        ] {
            let c = VerifyConfig::new(m, p, d, true).expect("boundary accepted");
            assert_eq!((c.gabcke_multiplier(), c.precision_cap(), c.depth_cap()), (m, p, d));
        }
    }

    #[test]
    fn accepts_move_points_off() {
        let c = VerifyConfig::new(1.0, 512, 40, false).expect("harder setting accepted");
        assert!(!c.move_points());
    }

    #[test]
    fn default_passes_validation_and_has_documented_values() {
        let d = VerifyConfig::default();
        assert_eq!(
            VerifyConfig::new(MIN_GABCKE_MULTIPLIER, MAX_PRECISION_CAP, MAX_DEPTH_CAP, true),
            Ok(d.clone())
        );
        assert_eq!(
            (d.gabcke_multiplier(), d.precision_cap(), d.depth_cap(), d.move_points()),
            (1.0, 512, 40, true)
        );
    }

    #[test]
    fn config_error_display_names_value_and_limit() {
        let cases = [
            (ConfigError::MultiplierNotFinite, "gabcke multiplier is not finite"),
            (ConfigError::MultiplierBelowOne, "gabcke multiplier below minimum 1"),
            (ConfigError::PrecisionCapTooLow(63), "precision cap 63 below minimum 64"),
            (ConfigError::PrecisionCapTooHigh(513), "precision cap 513 above maximum 512"),
            (ConfigError::DepthCapTooHigh(41), "depth cap 41 above maximum 40"),
        ];
        for (e, want) in cases {
            assert_eq!(format!("{e}"), want);
        }
        let boxed: Box<dyn std::error::Error> = Box::new(ConfigError::DepthCapTooHigh(41));
        assert_eq!(boxed.to_string(), "depth cap 41 above maximum 40");
    }

    #[test]
    fn limits_have_documented_values() {
        assert_eq!(
            (MIN_GABCKE_MULTIPLIER, MIN_PRECISION_CAP, MAX_PRECISION_CAP, MAX_DEPTH_CAP),
            (1.0, 64, 512, 40)
        );
    }
}
