//! Certified verification of the Riemann Hypothesis up to height 10^N.
//!
//! - `interval`: MPFR interval arithmetic with directed rounding.
//! - `config`: widen-only verification settings that can only make certification harder.
//! - `theta`: certified Riemann-Siegel theta and Gram-point brackets.
//! - `boundary`: Gram boundaries whose Z sign is certified over the whole bracket.
//! - `isolate`: certified sign points per Gram block and the straddle rule at T.
//! - `zfun`: certified Hardy Z by Riemann-Siegel and Euler-Maclaurin, and the self-check.

pub mod boundary;
pub(crate) mod complex;
pub mod config;
pub mod interval;
pub mod isolate;
pub mod theta;
pub mod zfun;
