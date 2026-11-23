//! Certified sign points for one Gram block, and the side-of-T rule for a
//! sign-change interval that straddles the target height.
//!
//! Every returned point is an exact `f64` height whose Z sign is certified on
//! the degenerate interval `[t, t]`. A point whose sign cannot be certified is
//! moved to a nearby `f64` or discarded, never used. Rosser's expected count only
//! steers where to subdivide; it is never credited (spec, "The proof" step 4).

use std::collections::HashSet;

use crate::config::VerifyConfig;
use crate::interval::Sign;
use crate::zfun::{ZFault, ZSource};

/// A sample height with its certified Z sign.
pub type Point = (f64, Sign);

/// Precision ladder for a sign: each rung is tried while it is within the cap.
const PRECISION_RUNGS: [u32; 4] = [64, 128, 256, 512];

/// Most midpoint evaluations `resolve_straddle` makes (spec R23).
pub const MAX_BISECTIONS: u32 = 60;

/// Bound on the points one block may hold: a block whose zeros are not there
/// (a Rosser failure) would otherwise double up to 2^depth_cap points. Halving
/// every gap gives 2^d + 1 points at depth d, so this allows depth 16, a spacing
/// of about 3e-5 on a block under 2 long, well below the closest zero pairs
/// known below 10^7 (about 2e-3); Lehmer's pair needs depth 6.
pub const MAX_BLOCK_POINTS: usize = 1 << 16;

/// How many fractions of a gap a moved point may sit away from the gap's midpoint.
const MOVE_SHIFTS: std::ops::RangeInclusive<i32> = 6..=12;

/// A Gram block as Task 8/9 hand it over: certified boundary points (their
/// signs come from the Gram bracket's certificate) and Rosser's expected number
/// of sign changes (the block's Gram-interval count).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GramBlock {
    pub lo: Point,
    pub hi: Point,
    pub expected: usize,
}

/// The certified points of a block in increasing height, boundaries included;
/// `resolved` is true when they alternate at least `expected` times.
#[derive(Debug, Clone, PartialEq)]
pub struct BlockPoints {
    pub points: Vec<Point>,
    pub resolved: bool,
}

/// Why a block or straddle could not be processed at all.
#[derive(Debug, Clone, PartialEq)]
pub enum IsolateError {
    /// The Z source reported an implementation fault; never a sign or a refusal.
    Fault(ZFault),
    /// The block's boundaries are not finite or not strictly increasing.
    BadBlock,
    /// The straddle interval's end signs are equal, so it need not hold a zero.
    NotSignChange,
}

impl std::fmt::Display for IsolateError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Fault(e) => write!(f, "Z fault: {e}"),
            Self::BadBlock => f.write_str("block boundaries are not finite and increasing"),
            Self::NotSignChange => f.write_str("interval ends have equal signs"),
        }
    }
}

impl std::error::Error for IsolateError {}

impl From<ZFault> for IsolateError {
    fn from(e: ZFault) -> Self {
        Self::Fault(e)
    }
}

/// Which side of T the zero in a sign-change interval lies on.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Straddle {
    /// The zero is certified below T.
    Below,
    /// The zero is certified above T.
    Above,
    /// 60 bisections left the zero's side unknown: the run exits 3.
    Uncertain,
}

/// The number of adjacent pairs with different signs.
pub fn alternations(points: &[Point]) -> usize {
    points.windows(2).filter(|w| w[0].1 != w[1].1).count()
}

/// Z's sign at exactly `t`, certified on `[t, t]` at the first rung (within the
/// cap) that excludes 0; `None` when no rung does. A fault propagates.
fn certified_sign<Z: ZSource>(z: &Z, t: f64, cfg: &VerifyConfig) -> Result<Option<Sign>, ZFault> {
    for prec in PRECISION_RUNGS.into_iter().filter(|&p| p <= cfg.precision_cap()) {
        if let Some(sign) = z.z(t, prec)?.and_then(|i| i.sign()) {
            return Ok(Some(sign));
        }
    }
    Ok(None)
}

/// A certified point strictly inside `(a, b)`: the midpoint, or (when allowed)
/// the first of a few nearby `f64`s whose sign certifies. `None` discards it.
fn sample_in_gap<Z: ZSource>(
    z: &Z,
    a: f64,
    b: f64,
    cfg: &VerifyConfig,
) -> Result<Option<Point>, ZFault> {
    let mid = a + (b - a) / 2.0;
    let mut candidates = vec![mid];
    if cfg.move_points() {
        for shift in MOVE_SHIFTS {
            let step = (b - a) * 0.5_f64.powi(shift);
            candidates.push(mid + step);
            candidates.push(mid - step);
        }
    }
    for c in candidates {
        if c > a
            && c < b
            && let Some(sign) = certified_sign(z, c, cfg)?
        {
            return Ok(Some((c, sign)));
        }
    }
    Ok(None)
}

/// Certified (t, sign) points for one Gram block. Starting from the boundaries,
/// each round halves every gap (a gap with different end signs can still hold
/// 3, 5, ... zeros, as in an odd-length block) until the points alternate `expected` times, the
/// depth cap is reached or `MAX_BLOCK_POINTS` is hit; then `resolved` is false.
pub fn isolate_block<Z: ZSource>(
    block: &GramBlock,
    z: &Z,
    cfg: &VerifyConfig,
) -> Result<BlockPoints, IsolateError> {
    let (lo, hi) = (block.lo.0, block.hi.0);
    if !(lo.is_finite() && hi.is_finite() && lo < hi) {
        return Err(IsolateError::BadBlock);
    }
    let mut points = vec![block.lo, block.hi];
    // Gaps whose midpoint could not be certified: retrying them cannot succeed.
    let mut dead: HashSet<(u64, u64)> = HashSet::new();
    let mut depth = 0;
    loop {
        if alternations(&points) >= block.expected {
            return Ok(BlockPoints { points, resolved: true });
        }
        if depth >= cfg.depth_cap() || points.len() >= MAX_BLOCK_POINTS {
            return Ok(BlockPoints { points, resolved: false });
        }
        let mut next = Vec::with_capacity(points.len() * 2);
        let mut grew = false;
        for w in points.windows(2) {
            next.push(w[0]);
            let key = (w[0].0.to_bits(), w[1].0.to_bits());
            if dead.contains(&key) {
                continue;
            }
            match sample_in_gap(z, w[0].0, w[1].0, cfg)? {
                Some(p) => {
                    next.push(p);
                    grew = true;
                }
                None => {
                    dead.insert(key);
                }
            }
        }
        next.push(block.hi);
        points = next;
        depth += 1;
        if !grew {
            return Ok(BlockPoints { points, resolved: false });
        }
    }
}

/// Which side of `t` the zero inside the sign-change interval `[lo, hi]` lies on.
///
/// A zero-free certified bracket `[b, c]` of g_M that holds `t` decides without
/// evaluating when `lo` is at or above `b` (the zero is above `c`) or `hi` is at
/// or below `c` (the zero is below `b`). Otherwise Z's sign at `t` decides in one
/// evaluation; if that is uncertain the interval is bisected, at most
/// `MAX_BISECTIONS` times, keeping the half that holds the zero, until it no
/// longer contains `t`. An uncertain midpoint or exhausted bisections is
/// `Uncertain`.
pub fn resolve_straddle<Z: ZSource>(
    lo: Point,
    hi: Point,
    t: f64,
    bracket: Option<(f64, f64)>,
    z: &Z,
    cfg: &VerifyConfig,
) -> Result<Straddle, IsolateError> {
    if t.is_nan() {
        return Err(IsolateError::Fault(ZFault::NanHeight));
    }
    if !(lo.0.is_finite() && hi.0.is_finite()) || lo.0 >= hi.0 {
        return Err(IsolateError::BadBlock);
    }
    if lo.1 == hi.1 {
        return Err(IsolateError::NotSignChange);
    }
    let (mut a, mut b) = (lo, hi);
    if let Some(side) = decided(a.0, b.0, t) {
        return Ok(side);
    }
    if let Some((bl, br)) = bracket
        && bl <= t
        && t <= br
    {
        if a.0 >= bl {
            return Ok(Straddle::Above);
        }
        if b.0 <= br {
            return Ok(Straddle::Below);
        }
    }
    if let Some(sign) = certified_sign(z, t, cfg)? {
        // The zero lies on the side of t whose end has the opposite sign.
        return Ok(if sign == a.1 { Straddle::Above } else { Straddle::Below });
    }
    for _ in 0..MAX_BISECTIONS {
        // Halve each end first so a huge finite pair cannot overflow; t lies
        // strictly inside (a, b), so the midpoint does too.
        let mid = a.0 * 0.5 + b.0 * 0.5;
        let Some(sign) = certified_sign(z, mid, cfg)? else {
            return Ok(Straddle::Uncertain);
        };
        if sign == a.1 {
            a = (mid, sign);
        } else {
            b = (mid, sign);
        }
        if let Some(side) = decided(a.0, b.0, t) {
            return Ok(side);
        }
    }
    Ok(Straddle::Uncertain)
}

/// The side of `t` when the open interval `(a, b)` holding the zero excludes it.
/// A point equal to `t` has a certified nonzero sign, so the zero is not there.
fn decided(a: f64, b: f64, t: f64) -> Option<Straddle> {
    if t <= a {
        Some(Straddle::Above)
    } else if t >= b {
        Some(Straddle::Below)
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::interval::Interval;
    use crate::theta::gram_bracket;
    use crate::zfun::RealZ;
    use proptest::prelude::*;
    use rug::Float;
    use std::cell::RefCell;

    type Verdict = Result<Option<Sign>, ZFault>;

    /// A fake whose verdict is a function of (t, prec); records every call.
    struct Fake<F: Fn(f64, u32) -> Verdict> {
        verdict: F,
        calls: RefCell<Vec<(f64, u32)>>,
    }

    fn fake<F: Fn(f64, u32) -> Verdict>(verdict: F) -> Fake<F> {
        Fake { verdict, calls: RefCell::new(Vec::new()) }
    }

    fn uncertain() -> Interval {
        Interval::new(Float::with_val(64, -1), Float::with_val(64, 1)).unwrap()
    }

    impl<F: Fn(f64, u32) -> Verdict> ZSource for Fake<F> {
        fn z(&self, t: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
            self.calls.borrow_mut().push((t, prec));
            Ok(match (self.verdict)(t, prec)? {
                Some(Sign::Positive) => Some(Interval::point(1.0, prec)),
                Some(Sign::Negative) => Some(Interval::point(-1.0, prec)),
                None => Some(uncertain()),
            })
        }
    }

    impl<F: Fn(f64, u32) -> Verdict> Fake<F> {
        fn count(&self) -> usize {
            self.calls.borrow().len()
        }
    }

    fn pos() -> Sign {
        Sign::Positive
    }
    fn neg() -> Sign {
        Sign::Negative
    }

    fn cfg_prec(cap: u32) -> VerifyConfig {
        VerifyConfig::new(1.0, cap, 40, true).unwrap()
    }

    /// Negative on [0.3, 0.4], positive elsewhere.
    fn dip(t: f64, _prec: u32) -> Verdict {
        Ok(Some(if (0.3..=0.4).contains(&t) { neg() } else { pos() }))
    }

    fn block01(expected: usize) -> GramBlock {
        GramBlock { lo: (0.0, pos()), hi: (1.0, pos()), expected }
    }

    // ---- certified_sign ----

    #[test]
    fn sign_climbs_precision_rungs_until_certified() {
        let z = fake(|_, prec| Ok((prec >= 256).then(pos)));
        assert_eq!(certified_sign(&z, 1.0, &cfg_prec(512)).unwrap(), Some(pos()));
        let precs: Vec<u32> = z.calls.borrow().iter().map(|c| c.1).collect();
        assert_eq!(precs, vec![64, 128, 256]);
    }

    #[test]
    fn sign_respects_precision_cap() {
        let z = fake(|_, prec| Ok((prec >= 256).then(pos)));
        assert_eq!(certified_sign(&z, 1.0, &cfg_prec(128)).unwrap(), None);
        let precs: Vec<u32> = z.calls.borrow().iter().map(|c| c.1).collect();
        assert_eq!(precs, vec![64, 128]);
    }

    #[test]
    fn sign_cap_equal_to_rung_includes_it() {
        let z = fake(|_, prec| Ok((prec == 64).then(neg)));
        assert_eq!(certified_sign(&z, 1.0, &cfg_prec(64)).unwrap(), Some(neg()));
    }

    #[test]
    fn sign_treats_refusal_as_uncertain() {
        struct Refuse;
        impl ZSource for Refuse {
            fn z(&self, _: f64, _: u32) -> Result<Option<Interval>, ZFault> {
                Ok(None)
            }
        }
        assert_eq!(certified_sign(&Refuse, 1.0, &cfg_prec(512)).unwrap(), None);
    }

    #[test]
    fn sign_fault_propagates_not_read_as_sign_or_refusal() {
        let z = fake(|_, prec| if prec == 128 { Err(ZFault::NanHeight) } else { Ok(None) });
        assert_eq!(certified_sign(&z, 1.0, &cfg_prec(512)), Err(ZFault::NanHeight));
        assert_eq!(z.count(), 2, "no rung after the fault is tried");
    }

    // ---- alternations ----

    #[test]
    fn alternations_counts_adjacent_changes() {
        assert_eq!(alternations(&[]), 0);
        assert_eq!(alternations(&[(0.0, pos())]), 0);
        assert_eq!(alternations(&[(0.0, pos()), (1.0, pos())]), 0);
        assert_eq!(alternations(&[(0.0, pos()), (1.0, neg())]), 1);
        assert_eq!(alternations(&[(0.0, pos()), (1.0, neg()), (2.0, pos()), (3.0, pos())]), 2);
    }

    proptest! {
        /// Dropping points from a sign sequence never adds an alternation.
        #[test]
        fn discarding_points_never_creates_an_alternation(
            signs in proptest::collection::vec(any::<bool>(), 0..40),
            keep in proptest::collection::vec(any::<bool>(), 0..40),
        ) {
            let all: Vec<Point> = signs
                .iter()
                .enumerate()
                .map(|(i, &s)| (i as f64, if s { pos() } else { neg() }))
                .collect();
            let kept: Vec<Point> = all
                .iter()
                .zip(keep.iter().chain(std::iter::repeat(&true)))
                .filter(|(_, k)| **k)
                .map(|(p, _)| *p)
                .collect();
            prop_assert!(alternations(&kept) <= alternations(&all));
        }
    }

    // ---- isolate_block ----

    #[test]
    fn block_resolves_at_exact_depth_cap_and_not_one_below() {
        // The dip is first sampled at 0.375, the third halving round.
        let at3 = VerifyConfig::new(1.0, 512, 3, true).unwrap();
        let r = isolate_block(&block01(2), &fake(dip), &at3).unwrap();
        assert!(r.resolved);
        assert_eq!(alternations(&r.points), 2);
        let at2 = VerifyConfig::new(1.0, 512, 2, true).unwrap();
        let r = isolate_block(&block01(2), &fake(dip), &at2).unwrap();
        assert!(!r.resolved);
        assert_eq!(r.points.len(), 5, "0, .25, .5, .75, 1");
    }

    #[test]
    fn block_points_are_sorted_with_boundaries_and_distinct_signs_where_changed() {
        let r = isolate_block(&block01(2), &fake(dip), &VerifyConfig::default()).unwrap();
        assert_eq!(r.points.first().unwrap(), &(0.0, pos()));
        assert_eq!(r.points.last().unwrap(), &(1.0, pos()));
        assert!(r.points.windows(2).all(|w| w[0].0 < w[1].0));
        for (t, s) in &r.points[1..r.points.len() - 1] {
            assert_eq!(*s, dip(*t, 64).unwrap().unwrap());
        }
    }

    #[test]
    fn block_with_no_expected_changes_is_resolved_without_calls() {
        let z = fake(dip);
        let r = isolate_block(&block01(0), &z, &VerifyConfig::default()).unwrap();
        assert!(r.resolved);
        assert_eq!(r.points, vec![(0.0, pos()), (1.0, pos())]);
        assert_eq!(z.count(), 0);
    }

    #[test]
    fn block_already_alternating_makes_no_calls() {
        let z = fake(dip);
        let b = GramBlock { lo: (0.0, pos()), hi: (1.0, neg()), expected: 1 };
        let r = isolate_block(&b, &z, &VerifyConfig::default()).unwrap();
        assert!(r.resolved);
        assert_eq!(z.count(), 0);
    }

    /// Positive on [0, .2), negative on [.2, .4), positive on [.4, .6), negative
    /// from .6: three zeros inside one gap whose ends differ in sign.
    fn three_zeros(t: f64, _prec: u32) -> Verdict {
        Ok(Some(if (0.2..0.4).contains(&t) || t >= 0.6 { neg() } else { pos() }))
    }

    fn odd_block() -> GramBlock {
        GramBlock { lo: (0.0, pos()), hi: (1.0, neg()), expected: 3 }
    }

    #[test]
    fn odd_length_block_with_opposite_end_signs_resolves() {
        let r = isolate_block(&odd_block(), &fake(three_zeros), &VerifyConfig::default()).unwrap();
        assert!(r.resolved);
        assert_eq!(alternations(&r.points), 3);
    }

    #[test]
    fn odd_length_block_is_unresolved_at_depth_cap_one() {
        let cfg = VerifyConfig::new(1.0, 512, 1, true).unwrap();
        let r = isolate_block(&odd_block(), &fake(three_zeros), &cfg).unwrap();
        assert!(!r.resolved);
        assert_eq!(alternations(&r.points), 1);
    }

    #[test]
    fn block_rejects_degenerate_boundaries() {
        let cfg = VerifyConfig::default();
        let z = fake(dip);
        for (lo, hi) in [
            (1.0, 1.0),
            (2.0, 1.0),
            (f64::NAN, 1.0),
            (0.0, f64::NAN),
            (f64::NEG_INFINITY, 1.0),
            (0.0, f64::INFINITY),
        ] {
            let b = GramBlock { lo: (lo, pos()), hi: (hi, pos()), expected: 2 };
            assert_eq!(isolate_block(&b, &z, &cfg), Err(IsolateError::BadBlock), "{lo} {hi}");
        }
        assert_eq!(z.count(), 0);
    }

    #[test]
    fn block_fault_propagates() {
        let z = fake(|t, _| if t == 0.5 { Err(ZFault::NanHeight) } else { dip(t, 64) });
        let r = isolate_block(&block01(2), &z, &VerifyConfig::default());
        assert_eq!(r, Err(IsolateError::Fault(ZFault::NanHeight)));
    }

    #[test]
    fn block_fault_while_moving_a_point_propagates() {
        // Uncertain at the midpoint, fault at a moved candidate.
        let z = fake(|t, _| {
            if t == 0.5 {
                Ok(None)
            } else if t > 0.5 && t < 0.52 {
                Err(ZFault::NanHeight)
            } else {
                dip(t, 64)
            }
        });
        let r = isolate_block(&block01(2), &z, &VerifyConfig::default());
        assert_eq!(r, Err(IsolateError::Fault(ZFault::NanHeight)));
    }

    #[test]
    fn uncertain_midpoint_is_moved_when_allowed() {
        let z = fake(|t, _| if t == 0.5 { Ok(None) } else { dip(t, 64) });
        let r = isolate_block(&block01(2), &z, &VerifyConfig::default()).unwrap();
        assert!(r.resolved);
        assert!(r.points.iter().all(|p| p.0 != 0.5), "0.5 is never used");
        assert!(r.points.iter().any(|p| (p.0 - 0.5).abs() < 0.5 / 32.0 + 1e-12 && p.0 != 0.5));
    }

    #[test]
    fn uncertain_midpoint_is_discarded_when_moving_is_off() {
        let z = fake(|t, _| if t == 0.5 { Ok(None) } else { dip(t, 64) });
        let cfg = VerifyConfig::new(1.0, 512, 40, false).unwrap();
        let r = isolate_block(&block01(2), &z, &cfg).unwrap();
        // The gap (0, 1) is dead after its midpoint fails: nothing else to try.
        assert!(!r.resolved);
        assert_eq!(r.points, vec![(0.0, pos()), (1.0, pos())]);
        assert_eq!(z.count(), 4, "0.5 at each rung and no retry");
    }

    #[test]
    fn dead_gap_is_not_retried_but_other_gaps_continue() {
        // 0.25 is never certifiable; with moving off, gap (0, .5) dies there while
        // (.5, 1) keeps being halved until the dip at 0.375 is not in it: so the
        // block stays unresolved but terminates.
        let z = fake(|t, _| if t == 0.25 { Ok(None) } else { dip(t, 64) });
        let cfg = VerifyConfig::new(1.0, 512, 40, false).unwrap();
        let r = isolate_block(&block01(2), &z, &cfg).unwrap();
        assert!(!r.resolved);
        let at_quarter = z.calls.borrow().iter().filter(|c| c.0 == 0.25).count();
        assert_eq!(at_quarter, 4, "tried once per rung, never again");
    }

    #[test]
    fn block_with_no_float_between_ends_is_unresolved() {
        let hi = 1.0_f64;
        let lo = hi.next_down();
        let b = GramBlock { lo: (lo, pos()), hi: (hi, pos()), expected: 2 };
        let z = fake(dip);
        let r = isolate_block(&b, &z, &VerifyConfig::default()).unwrap();
        assert!(!r.resolved);
        assert_eq!(r.points.len(), 2);
    }

    #[test]
    fn block_point_budget_stops_an_unresolvable_block() {
        // All positive: a block that wants changes that are not there.
        let z = fake(|_, _| Ok(Some(pos())));
        let r = isolate_block(&block01(2), &z, &VerifyConfig::default()).unwrap();
        assert!(!r.resolved);
        assert!(r.points.len() >= MAX_BLOCK_POINTS);
        assert!(r.points.len() <= 2 * MAX_BLOCK_POINTS);
    }

    #[test]
    fn block_is_idempotent() {
        let cfg = VerifyConfig::default();
        let a = isolate_block(&block01(2), &fake(dip), &cfg).unwrap();
        let b = isolate_block(&block01(2), &fake(dip), &cfg).unwrap();
        assert_eq!(a, b);
    }

    // ---- real Z: Lehmer's pair ----

    fn real_block() -> (RealZ, GramBlock) {
        let cfg = VerifyConfig::default();
        let z = RealZ::new(&cfg).unwrap();
        let end = |n: i64| {
            let (b, _) = gram_bracket(n, 512).unwrap();
            let s = certified_sign(&z, b, &cfg).unwrap().unwrap();
            (b, s)
        };
        let block = GramBlock { lo: end(6707), hi: end(6709), expected: 2 };
        (z, block)
    }

    fn brackets(points: &[Point], zero: f64) -> bool {
        points.windows(2).any(|w| w[0].0 < zero && zero < w[1].0 && w[0].1 != w[1].1)
    }

    const LEHMER: [f64; 2] = [7005.062866175, 7005.100564674];

    #[test]
    fn lehmer_block_brackets_both_zeros_at_default_depth() {
        let (z, block) = real_block();
        let r = isolate_block(&block, &z, &VerifyConfig::default()).unwrap();
        assert!(r.resolved);
        assert!(brackets(&r.points, LEHMER[0]));
        assert!(brackets(&r.points, LEHMER[1]));
        // Two distinct sign changes, not one pair counted twice.
        let first = r.points.windows(2).position(|w| w[0].0 < LEHMER[0] && LEHMER[0] < w[1].0);
        let second = r.points.windows(2).position(|w| w[0].0 < LEHMER[1] && LEHMER[1] < w[1].0);
        assert_ne!(first, second);
    }

    #[test]
    fn lehmer_block_is_unresolved_at_depth_cap_one() {
        let (z, block) = real_block();
        let cfg = VerifyConfig::new(1.0, 512, 1, true).unwrap();
        let r = isolate_block(&block, &z, &cfg).unwrap();
        assert!(!r.resolved);
    }

    #[test]
    fn real_odd_length_gram_block_resolves() {
        // g_2144 and g_2147 are consecutive good Gram points (found by scanning
        // n < 30000), so [g_2144, g_2147) is a Gram block of length 3 whose
        // boundary signs (+ and -) differ.
        let cfg = VerifyConfig::default();
        let z = RealZ::new(&cfg).unwrap();
        let end = |n: i64| {
            let (b, _) = gram_bracket(n, 512).unwrap();
            (b, certified_sign(&z, b, &cfg).unwrap().unwrap())
        };
        let block = GramBlock { lo: end(2144), hi: end(2147), expected: 3 };
        assert_ne!(block.lo.1, block.hi.1);
        let r = isolate_block(&block, &z, &cfg).unwrap();
        assert!(r.resolved);
        assert!(alternations(&r.points) >= 3);
    }

    #[test]
    fn lehmer_straddle_with_real_z() {
        let (z, block) = real_block();
        let cfg = VerifyConfig::default();
        let r = isolate_block(&block, &z, &cfg).unwrap();
        let i = r.points.windows(2).position(|w| w[0].0 < LEHMER[0] && LEHMER[0] < w[1].0).unwrap();
        let (p, q) = (r.points[i], r.points[i + 1]);
        let side = |t| resolve_straddle(p, q, t, None, &z, &cfg).unwrap();
        assert_eq!(side(LEHMER[0] - 1e-3), Straddle::Above);
        assert_eq!(side(LEHMER[0] + 1e-3), Straddle::Below);
    }

    // ---- resolve_straddle ----

    fn step_at(z0: f64) -> impl Fn(f64, u32) -> Verdict {
        move |t, _| Ok(Some(if t < z0 { neg() } else { pos() }))
    }

    #[test]
    fn straddle_certified_sign_at_t_decides_with_one_call() {
        let cfg = VerifyConfig::default();
        let z = fake(step_at(0.7));
        let (lo, hi) = ((0.0, neg()), (1.0, pos()));
        assert_eq!(resolve_straddle(lo, hi, 0.5, None, &z, &cfg).unwrap(), Straddle::Above);
        assert_eq!(z.count(), 1);
        let z = fake(step_at(0.7));
        assert_eq!(resolve_straddle(lo, hi, 0.9, None, &z, &cfg).unwrap(), Straddle::Below);
        assert_eq!(z.count(), 1);
    }

    #[test]
    fn straddle_t_outside_or_on_the_ends_needs_no_evaluation() {
        let cfg = VerifyConfig::default();
        let z = fake(step_at(0.7));
        let (lo, hi) = ((0.0, neg()), (1.0, pos()));
        for (t, want) in [
            (-1.0, Straddle::Above),
            (0.0, Straddle::Above),
            (1.0, Straddle::Below),
            (2.0, Straddle::Below),
        ] {
            assert_eq!(resolve_straddle(lo, hi, t, None, &z, &cfg).unwrap(), want, "{t}");
        }
        assert_eq!(z.count(), 0);
    }

    #[test]
    fn straddle_zero_free_bracket_skips_evaluation() {
        let cfg = VerifyConfig::default();
        let z = fake(step_at(0.7));
        let (lo, hi) = ((0.0, neg()), (1.0, pos()));
        // t in the bracket, lo at the bracket start: the zero is above the bracket.
        let r = resolve_straddle(lo, hi, 0.1, Some((0.0, 0.2)), &z, &cfg).unwrap();
        assert_eq!(r, Straddle::Above);
        // hi at the bracket end: the zero is below it.
        let r = resolve_straddle(lo, hi, 0.9, Some((0.8, 1.0)), &z, &cfg).unwrap();
        assert_eq!(r, Straddle::Below);
        assert_eq!(z.count(), 0);
    }

    #[test]
    fn straddle_bracket_not_holding_t_is_ignored() {
        let cfg = VerifyConfig::default();
        let z = fake(step_at(0.7));
        let (lo, hi) = ((0.0, neg()), (1.0, pos()));
        let r = resolve_straddle(lo, hi, 0.5, Some((0.0, 0.2)), &z, &cfg).unwrap();
        assert_eq!(r, Straddle::Above);
        assert_eq!(z.count(), 1);
        // t in the bracket but the bracket sits strictly inside the interval.
        let z = fake(step_at(0.7));
        let r = resolve_straddle(lo, hi, 0.5, Some((0.4, 0.6)), &z, &cfg).unwrap();
        assert_eq!(r, Straddle::Above);
        assert_eq!(z.count(), 1);
    }

    #[test]
    fn straddle_bisects_when_sign_at_t_is_uncertain() {
        let cfg = VerifyConfig::default();
        let z0 = 0.7;
        let z = fake(move |t, _| if t == 0.3 { Ok(None) } else { step_at(z0)(t, 64) });
        let (lo, hi) = ((0.0, neg()), (1.0, pos()));
        let r = resolve_straddle(lo, hi, 0.3, None, &z, &cfg).unwrap();
        assert_eq!(r, Straddle::Above);
        // 4 rungs at t, then the midpoint 0.5 (negative) lifts lo above t.
        assert_eq!(z.count(), 4 + 1);
    }

    #[test]
    fn straddle_below_after_bisection() {
        let cfg = VerifyConfig::default();
        let z = fake(move |t, _| if t == 0.8 { Ok(None) } else { step_at(0.3)(t, 64) });
        let (lo, hi) = ((0.0, neg()), (1.0, pos()));
        let r = resolve_straddle(lo, hi, 0.8, None, &z, &cfg).unwrap();
        assert_eq!(r, Straddle::Below);
    }

    #[test]
    fn straddle_exhausts_sixty_bisections_when_zero_sits_on_t() {
        let cfg = VerifyConfig::default();
        let t = 1e-30;
        // Zero exactly at t: uncertain only there, certified at every midpoint.
        let z = fake(move |x, _| if x == t { Ok(None) } else { step_at(t)(x, 64) });
        let (lo, hi) = ((0.0, neg()), (1.0, pos()));
        let r = resolve_straddle(lo, hi, t, None, &z, &cfg).unwrap();
        assert_eq!(r, Straddle::Uncertain);
        // 4 rungs at t, then exactly 60 midpoints (one rung each: certified at 64).
        assert_eq!(z.count(), 4 + 60);
    }

    #[test]
    fn straddle_uncertain_midpoint_is_uncertain() {
        let cfg = VerifyConfig::default();
        let z = fake(|_, _| Ok(None));
        let (lo, hi) = ((0.0, neg()), (1.0, pos()));
        let r = resolve_straddle(lo, hi, 0.3, None, &z, &cfg).unwrap();
        assert_eq!(r, Straddle::Uncertain);
        assert_eq!(z.count(), 8, "four rungs at t, four at the first midpoint");
    }

    #[test]
    fn straddle_stops_when_no_float_lies_between() {
        let cfg = VerifyConfig::default();
        let hi_t = 1.0_f64;
        let lo_t = hi_t.next_down();
        let z = fake(|_, _| Ok(None));
        let r = resolve_straddle((lo_t, neg()), (hi_t, pos()), 0.5 * (lo_t + hi_t), None, &z, &cfg);
        // t equals an end in floating point or lies between; either way no midpoint exists.
        assert!(matches!(r, Ok(Straddle::Uncertain | Straddle::Above | Straddle::Below)));
        assert!(z.count() <= 4);
    }

    #[test]
    fn straddle_input_errors() {
        let cfg = VerifyConfig::default();
        let z = fake(step_at(0.7));
        let (lo, hi) = ((0.0, neg()), (1.0, pos()));
        assert_eq!(
            resolve_straddle(lo, hi, f64::NAN, None, &z, &cfg),
            Err(IsolateError::Fault(ZFault::NanHeight))
        );
        assert_eq!(
            resolve_straddle((0.0, pos()), hi, 0.5, None, &z, &cfg),
            Err(IsolateError::NotSignChange)
        );
        for (a, b) in [(1.0, 0.0), (0.0, 0.0), (f64::NAN, 1.0), (0.0, f64::INFINITY)] {
            assert_eq!(
                resolve_straddle((a, neg()), (b, pos()), 0.5, None, &z, &cfg),
                Err(IsolateError::BadBlock)
            );
        }
        assert_eq!(z.count(), 0);
    }

    #[test]
    fn straddle_fault_propagates_at_t_and_at_a_midpoint() {
        let cfg = VerifyConfig::default();
        let (lo, hi) = ((0.0, neg()), (1.0, pos()));
        let z = fake(|_, _| Err(ZFault::NanHeight));
        assert_eq!(
            resolve_straddle(lo, hi, 0.3, None, &z, &cfg),
            Err(IsolateError::Fault(ZFault::NanHeight))
        );
        let z = fake(|x, _| if x == 0.3 { Ok(None) } else { Err(ZFault::NanHeight) });
        assert_eq!(
            resolve_straddle(lo, hi, 0.3, None, &z, &cfg),
            Err(IsolateError::Fault(ZFault::NanHeight))
        );
    }

    #[test]
    fn straddle_respects_precision_cap() {
        let cfg = cfg_prec(64);
        let z = fake(|_, _| Ok(None));
        let (lo, hi) = ((0.0, neg()), (1.0, pos()));
        let _ = resolve_straddle(lo, hi, 0.3, None, &z, &cfg).unwrap();
        assert!(z.calls.borrow().iter().all(|c| c.1 == 64));
    }

    #[test]
    fn moved_candidates_are_tried_in_order_around_the_midpoint() {
        let z = fake(|_, _| Ok(None));
        let b = GramBlock { lo: (2.0, pos()), hi: (3.0, pos()), expected: 2 };
        let r = isolate_block(&b, &z, &VerifyConfig::default()).unwrap();
        assert!(!r.resolved);
        let firsts: Vec<f64> = z.calls.borrow().iter().filter(|c| c.1 == 64).map(|c| c.0).collect();
        let mut want = vec![2.5];
        for shift in 6..=12 {
            let step = 0.5_f64.powi(shift);
            want.push(2.5 + step);
            want.push(2.5 - step);
        }
        assert_eq!(firsts, want);
    }

    #[test]
    fn block_whose_midpoint_rounds_to_the_lower_end_evaluates_nothing() {
        // 1 + 2^-53 ties to even, so the midpoint is the lower end itself.
        let lo = 1.0_f64;
        let hi = lo.next_up();
        let z = fake(dip);
        let b = GramBlock { lo: (lo, pos()), hi: (hi, pos()), expected: 2 };
        let r = isolate_block(&b, &z, &VerifyConfig::default()).unwrap();
        assert!(!r.resolved);
        assert_eq!(r.points.len(), 2);
        assert_eq!(z.count(), 0);
    }

    #[test]
    fn straddle_midpoints_follow_the_bisection_exactly() {
        let cfg = VerifyConfig::default();
        let zero = 1.5e-30_f64;
        let z = fake(move |x, _| if x == zero { Ok(None) } else { step_at(zero)(x, 64) });
        let (lo, hi) = ((1e-31, neg()), (3e-30, pos()));
        let r = resolve_straddle(lo, hi, zero, None, &z, &cfg).unwrap();
        assert_eq!(r, Straddle::Uncertain);
        // One entry per midpoint: the last one is uncertain and tried at every rung.
        let mut mids: Vec<f64> = z.calls.borrow().iter().skip(4).map(|c| c.0).collect();
        mids.dedup();
        assert!(mids.len() > 50 && mids.len() <= 60, "{}", mids.len());
        let (mut a, mut b) = (1e-31_f64, 3e-30_f64);
        for m in &mids {
            assert_eq!(*m, (a + b) / 2.0);
            if *m < zero { a = *m } else { b = *m }
        }
    }

    #[test]
    fn error_display_names_each_case() {
        assert!(IsolateError::Fault(ZFault::NanHeight).to_string().contains("NaN"));
        assert!(IsolateError::BadBlock.to_string().contains("increasing"));
        assert!(IsolateError::NotSignChange.to_string().contains("equal"));
    }
}
