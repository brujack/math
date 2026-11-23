//! Widen-only verification settings.
//!
//! Every accepted setting makes certification harder or equal, never easier,
//! so no configuration can turn a failed certification into a pass.

/// Why a [`VerifyConfig`] was rejected.
///
/// The multiplier's value is not carried: `f64` is not `Eq`, and NaN has no
/// useful value to report.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConfigError {
    /// The Gabcke multiplier was NaN or infinite.
    MultiplierNotFinite,
    /// The Gabcke multiplier was below 1.0, which would narrow the bounds.
    MultiplierBelowOne,
    /// The precision cap was below the minimum of 64 bits.
    PrecisionCapTooLow(u32),
    /// The precision cap was above the default of 512 bits.
    PrecisionCapTooHigh(u32),
    /// The depth cap was above the default of 40.
    DepthCapTooHigh(u32),
}

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
        Self { gabcke_multiplier: 1.0, precision_cap: 512, depth_cap: 40, move_points: true }
    }
}

impl VerifyConfig {
    /// Builds a config, rejecting any setting that would make certification easier.
    ///
    /// Accepted: multiplier finite and at least 1.0; precision cap 64..=512;
    /// depth cap at most 40 (0 is allowed: it only removes subdivision, which
    /// is harder). `move_points == false` removes a rescue, so it is allowed.
    pub fn new(
        gabcke_multiplier: f64,
        precision_cap: u32,
        depth_cap: u32,
        move_points: bool,
    ) -> Result<Self, ConfigError> {
        if !gabcke_multiplier.is_finite() {
            return Err(ConfigError::MultiplierNotFinite);
        }
        if gabcke_multiplier < 1.0 {
            return Err(ConfigError::MultiplierBelowOne);
        }
        if precision_cap < 64 {
            return Err(ConfigError::PrecisionCapTooLow(precision_cap));
        }
        if precision_cap > 512 {
            return Err(ConfigError::PrecisionCapTooHigh(precision_cap));
        }
        if depth_cap > 40 {
            return Err(ConfigError::DepthCapTooHigh(depth_cap));
        }
        Ok(Self { gabcke_multiplier, precision_cap, depth_cap, move_points })
    }

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
        for p in [0, 1, 63] {
            assert_eq!(
                VerifyConfig::new(1.0, p, 40, true),
                Err(ConfigError::PrecisionCapTooLow(p))
            );
        }
    }

    #[test]
    fn rejects_precision_cap_above_512() {
        for p in [513, u32::MAX] {
            assert_eq!(
                VerifyConfig::new(1.0, p, 40, true),
                Err(ConfigError::PrecisionCapTooHigh(p))
            );
        }
    }

    #[test]
    fn rejects_depth_cap_above_40() {
        for d in [41, u32::MAX] {
            assert_eq!(VerifyConfig::new(1.0, 512, d, true), Err(ConfigError::DepthCapTooHigh(d)));
        }
    }

    #[test]
    fn accepts_boundary_values() {
        for (m, p, d) in [(1.0, 512, 40), (1.0, 64, 0), (1e300, 65, 1), (2.5, 511, 39)] {
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
        assert_eq!(VerifyConfig::new(1.0, 512, 40, true), Ok(d.clone()));
        assert_eq!(
            (d.gabcke_multiplier(), d.precision_cap(), d.depth_cap(), d.move_points()),
            (1.0, 512, 40, true)
        );
    }

    #[test]
    fn getters_return_what_was_passed() {
        let c = VerifyConfig::new(3.0, 100, 7, false).expect("valid");
        assert_eq!(c.gabcke_multiplier(), 3.0);
        assert_eq!(c.precision_cap(), 100);
        assert_eq!(c.depth_cap(), 7);
        assert!(!c.move_points());
    }
}
