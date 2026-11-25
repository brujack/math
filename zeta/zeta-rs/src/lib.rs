//! Certified verification of the Riemann Hypothesis up to height 10^N.
//!
//! - `interval`: MPFR interval arithmetic with directed rounding.
//! - `config`: widen-only verification settings that can only make certification harder.
//! - `theta`: certified Riemann-Siegel theta and Gram-point brackets.
//! - `boundary`: Gram boundaries whose Z sign is certified over the whole bracket.
//! - `isolate`: certified sign points per Gram block and the straddle rule at T.
//! - `turing`: Turing's method with Trudgian's bound, and the choice of M.
//! - `zfun`: certified Hardy Z by Riemann-Siegel and Euler-Maclaurin, and the self-check.
//! - `spacing`: `--refine` bracket bisection, the spacing histogram and the KS distance.
//! - `verify`: the one-pass count of sign changes on a private rayon pool.

pub mod boundary;
pub(crate) mod complex;
pub mod config;
pub mod interval;
pub mod isolate;
pub mod spacing;
pub mod theta;
pub mod turing;
pub mod verify;
pub mod zfun;
