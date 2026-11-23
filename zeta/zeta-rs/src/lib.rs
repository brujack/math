//! Certified verification of the Riemann Hypothesis up to height 10^N.
//!
//! Skeleton: later tasks add interval arithmetic, Hardy's Z and zero isolation.

use rug::Float;

/// Bits of MPFR precision at which every certified computation starts.
pub const BASE_PRECISION: u32 = 128;

/// A zero at `BASE_PRECISION` bits. Anchors the `rug` dependency until the
/// interval module replaces it.
pub fn base_float() -> Float {
    Float::new(BASE_PRECISION)
}

/// Worker threads available to the verification pool. Anchors the `rayon`
/// dependency until the parallel driver replaces it.
pub fn pool_threads() -> usize {
    rayon::current_num_threads()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base_float_has_base_precision_and_is_zero() {
        let x = base_float();
        assert_eq!(x.prec(), BASE_PRECISION);
        assert_eq!(x, 0);
    }

    #[test]
    fn pool_has_at_least_one_thread() {
        assert!(pool_threads() >= 1);
    }
}
