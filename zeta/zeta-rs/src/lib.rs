//! Certified verification of the Riemann Hypothesis up to height 10^N.
//!
//! - `interval`: MPFR interval arithmetic with directed rounding.
//! - `config`: widen-only verification settings that can only make certification harder.
//! - `theta`: certified Riemann-Siegel theta and Gram-point brackets.
//! - `zfun`: certified Hardy Z by Riemann-Siegel and Euler-Maclaurin, and the self-check.

pub(crate) mod complex;
pub mod config;
pub mod interval;
pub mod theta;
pub mod zfun;
