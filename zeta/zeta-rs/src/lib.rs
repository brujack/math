//! Certified verification of the Riemann Hypothesis up to height 10^N.
//!
//! - `interval`: MPFR interval arithmetic with directed rounding.
//! - `config`: widen-only verification settings that can only make certification harder.

pub mod config;
pub mod interval;
pub mod theta;
