//! Turing's method with Trudgian's bound (spec R19, plan appendix section 4).
//!
//! At a good Gram point g_M above 168*pi, if K consecutive Gram blocks after
//! g_M each hold at least as many certified sign changes as Gram intervals
//! (Rosser's rule, counted from certified points only), and K satisfies
//! Trudgian 2011 eq. 2.1 at the upper height of the last block, then
//! N(g_M) <= M + 1.
//!
//! Faults (a Z fault, or an internal inconsistency in the points) are kept
//! apart from candidate failures: `TuringFailure::is_fault` tells them apart.

use std::f64::consts::PI;

use crate::boundary::{Boundary, certify_boundary};
use crate::config::VerifyConfig;
use crate::interval::Sign;
use crate::isolate::{GramBlock, IsolateError, Point, isolate_block};
use crate::theta::{gram_bracket, theta};
use crate::zfun::{ZFault, ZSource};

/// Most candidates `choose_m` tries: the first and ten retries (spec step 3).
pub const MAX_CANDIDATES: usize = 11;

/// Longest Gram block accepted (Gram points between two good ones). Real
/// blocks are far shorter; a longer run fails the candidate rather than
/// looping on a source in which no Gram point is good.
const MAX_BLOCK_LEN: i64 = 16;

/// Trudgian's range starts at 168*pi; the test is `b_M > 168*pi`. `b_M` is an
/// `f64`, and the nearest `f64` to 168*pi lies within half an ulp of it, so any
/// `f64` above this constant is above 168*pi itself.
const RANGE_START: f64 = 168.0 * PI;

/// Trudgian 2011 Theorem 2.2: |integral of S| <= A + B ln t.
const TRUDGIAN_A: f64 = 2.067;
const TRUDGIAN_B: f64 = 0.059;

/// Added before rounding the right side of eq. 2.1 up, so an `f64` error cannot
/// turn an exact integer bound into one block too few.
const ROUNDING_MARGIN: f64 = 1e-9;

/// What `establish` proved: N(g_m) <= m + 1.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct TuringBound {
    /// The Gram index M of the good point the bound holds at.
    pub m: i64,
    /// The number of Gram blocks after g_M, each satisfying Rosser's rule.
    pub blocks: usize,
    /// The Gram index ending the last block.
    pub last_index: i64,
    /// The upper end c of the last block's boundary bracket, the height eq. 2.1 used.
    pub upper: f64,
}

/// An inconsistency in the points Turing's pass was given: never a candidate failure.
#[derive(Debug, Clone, PartialEq)]
pub enum InternalFault {
    /// An adjacent pair of points lies in no single Gram block.
    PairInNoBlock,
    /// One height carries two different certified signs.
    SignConflict,
    /// A point's height is NaN.
    NanHeight,
    /// `isolate_block` refused an interval that Turing built itself.
    Isolate(IsolateError),
}

/// Why `establish` or `choose_m` did not produce a bound.
#[derive(Debug, Clone, PartialEq)]
pub enum TuringFailure {
    /// b_M <= 168*pi: outside Trudgian's proven range.
    BelowRange,
    /// g_M is not good: (-1)^M Z(g_M) is not positive.
    BadGramPoint,
    /// Gram point `n` (g_M itself or one in Turing's region) has no certified bracket.
    NoCertifiedBracket { n: i64 },
    /// No good Gram point within `MAX_BLOCK_LEN` after g_`from`.
    BlockTooLong { from: i64 },
    /// The block of `length` Gram intervals starting at `start` has only `credited` sign changes.
    RosserFailed { start: i64, length: usize, credited: usize },
    /// `MAX_CANDIDATES` candidates were tried and none established the bound.
    Exhausted { tried: usize },
    /// A Z fault (exit 6).
    Fault(ZFault),
    /// An inconsistency in the points (exit 6).
    Internal(InternalFault),
}

impl TuringFailure {
    /// True for a fault (a Z fault or an internal inconsistency): it ends the
    /// search instead of moving on to the next candidate.
    pub fn is_fault(&self) -> bool {
        matches!(self, Self::Fault(_) | Self::Internal(_))
    }
}

impl From<ZFault> for TuringFailure {
    fn from(fault: ZFault) -> TuringFailure {
        TuringFailure::Fault(fault)
    }
}

impl From<InternalFault> for TuringFailure {
    fn from(fault: InternalFault) -> TuringFailure {
        TuringFailure::Internal(fault)
    }
}

impl std::fmt::Display for TuringFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::BelowRange => f.write_str("b_M is not above 168*pi"),
            Self::BadGramPoint => f.write_str("g_M is not a good Gram point"),
            Self::NoCertifiedBracket { n } => write!(f, "Gram point {n} has no certified bracket"),
            Self::BlockTooLong { from } => write!(f, "no good Gram point soon after g_{from}"),
            Self::RosserFailed { start, length, credited } => write!(
                f,
                "block from g_{start} of length {length} holds {credited} certified sign changes"
            ),
            Self::Exhausted { tried } => write!(f, "no candidate of {tried} established the bound"),
            Self::Fault(e) => write!(f, "Z fault: {e}"),
            Self::Internal(e) => write!(f, "internal fault: {e:?}"),
        }
    }
}

impl std::error::Error for TuringFailure {}

/// Map `isolate_block`'s error: a fault stays a fault, and any
/// other refusal means Turing handed it a bad interval, an internal fault.
fn from_isolate(error: IsolateError) -> TuringFailure {
    match error {
        IsolateError::Fault(fault) => TuringFailure::Fault(fault),
        other => TuringFailure::Internal(InternalFault::Isolate(other)),
    }
}

/// The right side of Trudgian's eq. 2.1 at `g_p`:
/// (b / 6pi) ln^2 g_p + ((a - b ln 2pi) / 6pi) ln g_p.
fn trudgian_rhs(g_p: f64) -> f64 {
    let ln = g_p.ln();
    let six_pi = 6.0 * PI;
    (TRUDGIAN_B / six_pi) * ln * ln + ((TRUDGIAN_A - TRUDGIAN_B * (2.0 * PI).ln()) / six_pi) * ln
}

/// `x` rounded up to a block count, with `ROUNDING_MARGIN` so an exact integer rounds up.
fn ceil_with_margin(x: f64) -> usize {
    (x + ROUNDING_MARGIN).ceil() as usize
}

/// Blocks eq. 2.1 asks for when the last block's upper height is `g_p`.
fn blocks_needed(g_p: f64) -> usize {
    ceil_with_margin(trudgian_rhs(g_p))
}

/// Good means (-1)^n Z(g_n) > 0.
fn is_good(n: i64, sign: Sign) -> bool {
    sign == if n.rem_euclid(2) == 0 { Sign::Positive } else { Sign::Negative }
}

/// One Turing block: the closed range [lo, hi] of heights, from g_`start`, `len` Gram intervals long.
#[derive(Debug, Clone, Copy, PartialEq)]
struct BlockRange {
    lo: f64,
    hi: f64,
    start: i64,
    len: usize,
}

/// Sort certified points by height, keep one copy of an identical (t, sign), and
/// reject a NaN height or one height with two signs.
fn merge_points(mut points: Vec<Point>) -> Result<Vec<Point>, InternalFault> {
    if points.iter().any(|p| p.t.is_nan()) {
        return Err(InternalFault::NanHeight);
    }
    points.sort_by(|a, b| a.t.total_cmp(&b.t));
    let mut merged: Vec<Point> = Vec::with_capacity(points.len());
    for p in points {
        match merged.last() {
            Some(last) if last.t == p.t => {
                if last.sign != p.sign {
                    return Err(InternalFault::SignConflict);
                }
            }
            _ => merged.push(p),
        }
    }
    Ok(merged)
}

/// Sign changes credited to each block: an adjacent pair counts for the block
/// whose closed range holds both points, so a pair starting at a shared boundary
/// b_k belongs to the block starting there. A pair in no block is a fault.
fn credit_blocks(points: &[Point], blocks: &[BlockRange]) -> Result<Vec<usize>, InternalFault> {
    let mut credited = vec![0; blocks.len()];
    for pair in points.windows(2) {
        let (p, q) = (pair[0], pair[1]);
        let j = blocks
            .iter()
            .position(|b| b.lo <= p.t && q.t <= b.hi)
            .ok_or(InternalFault::PairInNoBlock)?;
        if p.sign != q.sign {
            credited[j] += 1;
        }
    }
    Ok(credited)
}

/// Fail with `RosserFailed` for the first block with fewer sign changes than Gram intervals.
fn check_rosser(points: &[Point], blocks: &[BlockRange]) -> Result<(), TuringFailure> {
    let credited = credit_blocks(points, blocks)?;
    match blocks.iter().zip(credited).find(|(b, c)| *c < b.len) {
        Some((b, c)) => {
            Err(TuringFailure::RosserFailed { start: b.start, length: b.len, credited: c })
        }
        None => Ok(()),
    }
}

/// The certified boundary of g_n, or the failure that says it has none.
fn boundary_at<Z: ZSource>(n: i64, z: &Z, cfg: &VerifyConfig) -> Result<Boundary, TuringFailure> {
    certify_boundary(n, z, cfg)?.ok_or(TuringFailure::NoCertifiedBracket { n })
}

/// The next good Gram point after g_`from`, with the certified boundary points of
/// the bad ones between them.
fn next_good<Z: ZSource>(
    from: i64,
    z: &Z,
    cfg: &VerifyConfig,
) -> Result<(i64, Boundary, Vec<Point>), TuringFailure> {
    let mut between = Vec::new();
    for n in from + 1..=from + MAX_BLOCK_LEN {
        let boundary = boundary_at(n, z, cfg)?;
        if is_good(n, boundary.point().sign) {
            return Ok((n, boundary, between));
        }
        between.push(boundary.point());
    }
    Err(TuringFailure::BlockTooLong { from })
}

/// Establish N(g_m) <= m + 1 by Turing's method (Trudgian 2011), or say why not.
///
/// Refuses b_m <= 168*pi, a bad g_m and a g_m without a certified bracket. Blocks
/// are added after g_m until their count meets eq. 2.1 at the last block's
/// upper height; every block must satisfy Rosser's rule by certified sign changes.
pub fn establish<Z: ZSource>(
    m: i64,
    z: &Z,
    cfg: &VerifyConfig,
) -> Result<TuringBound, TuringFailure> {
    let first = boundary_at(m, z, cfg)?;
    if first.point().t <= RANGE_START {
        return Err(TuringFailure::BelowRange);
    }
    if !is_good(m, first.point().sign) {
        return Err(TuringFailure::BadGramPoint);
    }
    let mut points = vec![first.point()];
    let mut blocks: Vec<BlockRange> = Vec::new();
    let (mut start_n, mut start) = (m, first);
    loop {
        let (end_n, end, between) = next_good(start_n, z, cfg)?;
        let len = (end_n - start_n) as usize;
        let block = GramBlock { lo: start.point(), hi: end.point(), expected: len };
        points.extend(isolate_block(&block, z, cfg).map_err(from_isolate)?.points);
        points.extend(between);
        blocks.push(BlockRange { lo: start.point().t, hi: end.point().t, start: start_n, len });
        check_rosser(&merge_points(points.clone())?, &blocks)?;
        let upper = end.bracket().hi();
        if blocks.len() >= blocks_needed(upper) {
            return Ok(TuringBound { m, blocks: blocks.len(), last_index: end_n, upper });
        }
        (start_n, start) = (end_n, end);
    }
}

/// Where `first_candidate` starts walking: two indices below theta's lower bound
/// over pi, which is at or below the answer (g_n < t exactly when theta(t) > n*pi),
/// and never below -1.
fn walk_start(theta_lo: f64) -> i64 {
    ((theta_lo / PI).floor() as i64 - 2).max(-1)
}

/// Whether a Gram point with lower bracket end `b` may serve as g_M for a search floor.
fn qualifies(b: f64, floor: f64) -> bool {
    b > RANGE_START && b >= floor
}

/// The first Gram index worth trying: the smallest n with b_n above 168*pi and
/// at least `t_min`, found by walking up from `walk_start`.
fn first_candidate(t_min: f64, cfg: &VerifyConfig) -> Result<i64, TuringFailure> {
    let floor = t_min.max(RANGE_START);
    let theta_lo = theta(floor, cfg.precision_cap()).map_err(ZFault::Theta)?.lo().to_f64();
    let mut n = walk_start(theta_lo);
    loop {
        let (b, _) =
            gram_bracket(n, cfg.precision_cap()).ok_or(TuringFailure::NoCertifiedBracket { n })?;
        if qualifies(b, floor) {
            return Ok(n);
        }
        n += 1;
    }
}

/// Run `attempt` on `first`, `first + 1`, ... until one succeeds, at most
/// `MAX_CANDIDATES` times. A fault ends the search at once.
fn try_candidates<F>(first: i64, mut attempt: F) -> Result<TuringBound, TuringFailure>
where
    F: FnMut(i64) -> Result<TuringBound, TuringFailure>,
{
    for m in first..first + MAX_CANDIDATES as i64 {
        match attempt(m) {
            Ok(bound) => return Ok(bound),
            Err(failure) if failure.is_fault() => return Err(failure),
            Err(_) => {}
        }
    }
    Err(TuringFailure::Exhausted { tried: MAX_CANDIDATES })
}

/// The smallest M with b_M above 168*pi and at least `t_min` at which Turing's
/// method establishes N(g_M) <= M + 1, trying at most `MAX_CANDIDATES` indices
/// in a row (a candidate refused for any reason counts as tried).
pub fn choose_m<Z: ZSource>(
    t_min: f64,
    z: &Z,
    cfg: &VerifyConfig,
) -> Result<TuringBound, TuringFailure> {
    try_candidates(first_candidate(t_min, cfg)?, |m| establish(m, z, cfg))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::interval::Interval;
    use crate::zfun::RealZ;
    use rug::Float;
    use std::cell::Cell;

    fn cfg() -> VerifyConfig {
        VerifyConfig::default()
    }

    fn pos() -> Sign {
        Sign::Positive
    }

    fn neg() -> Sign {
        Sign::Negative
    }

    fn pt(t: f64, sign: Sign) -> Point {
        Point { t, sign }
    }

    /// theta by Stirling in f64: the fakes only need a smooth phase with
    /// theta(g_n) = n*pi to about 1e-9.
    fn theta_f64(t: f64) -> f64 {
        t / 2.0 * (t / (2.0 * PI)).ln() - t / 2.0 - PI / 8.0
            + 1.0 / (48.0 * t)
            + 7.0 / (5760.0 * t.powi(3))
    }

    /// cos(theta(t)): +-1 at every Gram point (all good) with one sign change per Gram interval.
    fn wave(t: f64) -> f64 {
        theta_f64(t).cos()
    }

    /// A Z whose value is `f(t)`; values within 1e-6 of 0 are uncertain.
    struct Fake<F: Fn(f64) -> f64> {
        f: F,
        z_fault: bool,
        z_calls: Cell<usize>,
        over_calls: Cell<usize>,
    }

    fn fake<F: Fn(f64) -> f64>(f: F) -> Fake<F> {
        Fake { f, z_fault: false, z_calls: Cell::new(0), over_calls: Cell::new(0) }
    }

    fn span(lo: f64, hi: f64) -> Interval {
        Interval::new(Float::with_val(64, lo), Float::with_val(64, hi)).unwrap()
    }

    impl<F: Fn(f64) -> f64> ZSource for Fake<F> {
        fn z(&self, t: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
            self.z_calls.set(self.z_calls.get() + 1);
            if self.z_fault {
                return Err(ZFault::NanHeight);
            }
            let v = (self.f)(t);
            Ok(Some(if v.abs() < 1e-6 { span(-1e-6, 1e-6) } else { Interval::point(v, prec) }))
        }

        fn z_over(&self, lo: f64, hi: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
            self.over_calls.set(self.over_calls.get() + 1);
            let (a, b) = ((self.f)(lo), (self.f)(hi));
            Ok(Some(span(a.min(b), a.max(b))))
        }
    }

    fn bracket(n: i64) -> (f64, f64) {
        gram_bracket(n, cfg().precision_cap()).unwrap()
    }

    // ---- Trudgian's inequality ----

    /// Reference values from an independent f64 evaluation of eq. 2.1 in Python
    /// with (a, b) = (2.067, 0.059), and the appendix table.
    #[test]
    fn trudgian_rhs_matches_the_independent_values() {
        for (g, want) in [
            (168.0 * PI, 0.774_349_321_079),
            (1e3, 0.867_107_821_049),
            (1e4, 1.222_524_527_04),
            (1e5, 1.611_131_615_852),
            (1e6, 2.032_929_087_485),
            (1e7, 2.487_916_941_938),
        ] {
            assert!((trudgian_rhs(g) - want).abs() < 1e-9, "g = {g}: {}", trudgian_rhs(g));
        }
    }

    /// The right side is 1 at g = 2426.3888 and 2 at g = 840759.87 (bisection in
    /// Python), so the block count steps from 1 to 2 and from 2 to 3 there.
    #[test]
    fn block_count_steps_at_the_independent_thresholds() {
        assert_eq!(blocks_needed(RANGE_START), 1);
        assert_eq!(blocks_needed(2426.38), 1);
        assert_eq!(blocks_needed(2426.40), 2);
        assert_eq!(blocks_needed(840_759.0), 2);
        assert_eq!(blocks_needed(840_761.0), 3);
    }

    #[test]
    fn an_exact_integer_bound_rounds_up_one_block() {
        assert_eq!(ceil_with_margin(2.0), 3);
        assert_eq!(ceil_with_margin(2.0 - 5e-9), 2);
        assert_eq!(ceil_with_margin(1.5), 2);
    }

    // ---- point merging and crediting ----

    #[test]
    fn merge_sorts_and_keeps_an_identical_point_once() {
        let merged = merge_points(vec![pt(2.0, neg()), pt(1.0, pos()), pt(2.0, neg())]).unwrap();
        assert_eq!(merged, vec![pt(1.0, pos()), pt(2.0, neg())]);
    }

    #[test]
    fn merge_refuses_a_sign_conflict_and_a_nan() {
        assert_eq!(
            merge_points(vec![pt(1.0, pos()), pt(1.0, neg())]),
            Err(InternalFault::SignConflict)
        );
        assert_eq!(
            merge_points(vec![pt(1.0, pos()), pt(f64::NAN, neg())]),
            Err(InternalFault::NanHeight)
        );
        assert_eq!(merge_points(vec![]), Ok(vec![]));
    }

    fn two_blocks() -> Vec<BlockRange> {
        vec![
            BlockRange { lo: 0.0, hi: 1.0, start: 10, len: 1 },
            BlockRange { lo: 1.0, hi: 2.0, start: 11, len: 1 },
        ]
    }

    /// The sign change whose left point is the shared boundary 1.0 belongs to the
    /// second block only.
    #[test]
    fn a_change_starting_at_the_shared_boundary_is_credited_to_the_next_block() {
        let points =
            [pt(0.0, pos()), pt(0.5, pos()), pt(1.0, pos()), pt(1.5, neg()), pt(2.0, neg())];
        assert_eq!(credit_blocks(&points, &two_blocks()), Ok(vec![0, 1]));
    }

    /// A change ending at the shared boundary belongs to the first block only.
    #[test]
    fn a_change_ending_at_the_shared_boundary_is_credited_to_the_first_block() {
        let points =
            [pt(0.0, pos()), pt(0.5, neg()), pt(1.0, neg()), pt(1.5, neg()), pt(2.0, neg())];
        assert_eq!(credit_blocks(&points, &two_blocks()), Ok(vec![1, 0]));
    }

    #[test]
    fn a_pair_in_no_block_is_an_internal_fault() {
        let points = [pt(0.5, pos()), pt(2.5, neg())];
        assert_eq!(credit_blocks(&points, &two_blocks()), Err(InternalFault::PairInNoBlock));
        // a pair straddling the shared boundary lies in neither block
        let straddle = [pt(0.5, pos()), pt(1.5, neg())];
        assert_eq!(credit_blocks(&straddle, &two_blocks()), Err(InternalFault::PairInNoBlock));
        assert_eq!(credit_blocks(&[], &two_blocks()), Ok(vec![0, 0]));
    }

    #[test]
    fn rosser_check_names_the_first_short_block() {
        let points = [pt(0.0, pos()), pt(1.0, neg()), pt(2.0, neg())];
        assert_eq!(
            check_rosser(&points, &two_blocks()),
            Err(TuringFailure::RosserFailed { start: 11, length: 1, credited: 0 })
        );
        let enough = [pt(0.0, pos()), pt(1.0, neg()), pt(2.0, pos())];
        assert_eq!(check_rosser(&enough, &two_blocks()), Ok(()));
        let internal = [pt(0.5, pos()), pt(2.5, neg())];
        assert_eq!(
            check_rosser(&internal, &two_blocks()),
            Err(TuringFailure::Internal(InternalFault::PairInNoBlock))
        );
    }

    #[test]
    fn goodness_follows_the_parity_of_the_index() {
        assert!(is_good(4, pos()));
        assert!(!is_good(4, neg()));
        assert!(is_good(5, neg()));
        assert!(!is_good(5, pos()));
    }

    #[test]
    fn faults_are_told_apart_from_candidate_failures() {
        assert!(TuringFailure::Fault(ZFault::NanHeight).is_fault());
        assert!(TuringFailure::Internal(InternalFault::SignConflict).is_fault());
        for failure in [
            TuringFailure::BelowRange,
            TuringFailure::BadGramPoint,
            TuringFailure::NoCertifiedBracket { n: 1 },
            TuringFailure::BlockTooLong { from: 1 },
            TuringFailure::RosserFailed { start: 1, length: 2, credited: 0 },
            TuringFailure::Exhausted { tried: 11 },
        ] {
            assert!(!failure.is_fault(), "{failure}");
        }
    }

    #[test]
    fn isolate_errors_map_to_a_fault_or_an_internal_fault() {
        assert_eq!(
            from_isolate(IsolateError::Fault(ZFault::NanHeight)),
            TuringFailure::Fault(ZFault::NanHeight)
        );
        assert_eq!(
            from_isolate(IsolateError::BadInterval),
            TuringFailure::Internal(InternalFault::Isolate(IsolateError::BadInterval))
        );
    }

    #[test]
    fn display_names_every_failure() {
        assert!(TuringFailure::BelowRange.to_string().contains("168"));
        assert!(TuringFailure::BadGramPoint.to_string().contains("good"));
        assert!(TuringFailure::NoCertifiedBracket { n: 7 }.to_string().contains('7'));
        assert!(TuringFailure::BlockTooLong { from: 8 }.to_string().contains('8'));
        let rosser = TuringFailure::RosserFailed { start: 3, length: 2, credited: 1 };
        assert!(rosser.to_string().contains("length 2"));
        assert!(TuringFailure::Exhausted { tried: 11 }.to_string().contains("11"));
        assert!(TuringFailure::Fault(ZFault::NanHeight).to_string().contains("NaN"));
        assert!(TuringFailure::Internal(InternalFault::SignConflict).to_string().contains("Sign"));
    }

    // ---- refusals ----

    /// Gram points 288 and 289 bracket 168*pi = 527.7876 (g_288 = 527.697, g_289 = 529.115).
    #[test]
    fn refuses_b_m_at_or_below_168_pi_and_accepts_the_next_index() {
        let z = fake(wave);
        assert_eq!(establish(288, &z, &cfg()), Err(TuringFailure::BelowRange));
        assert!(bracket(288).0 < RANGE_START && bracket(289).0 > RANGE_START);
        assert!(establish(289, &z, &cfg()).is_ok());
    }

    #[test]
    fn refuses_a_bad_g_m() {
        // Z > 0 everywhere: g_1913 (odd) needs Z < 0, so it is bad.
        let z = fake(|_| 1.0);
        assert_eq!(establish(1913, &z, &cfg()), Err(TuringFailure::BadGramPoint));
    }

    #[test]
    fn refuses_a_g_m_without_a_certified_bracket() {
        struct Refuses;
        impl ZSource for Refuses {
            fn z(&self, _t: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
                Ok(None)
            }
            fn z_over(&self, _lo: f64, _hi: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
                Ok(None)
            }
        }
        assert_eq!(
            establish(1912, &Refuses, &cfg()),
            Err(TuringFailure::NoCertifiedBracket { n: 1912 })
        );
    }

    #[test]
    fn an_uncertifiable_gram_point_in_the_region_fails_the_candidate() {
        // Z straddles 0 over the bracket of g_1913, the end of the first block.
        let (b, _) = bracket(1913);
        let z = fake(move |t| if t >= b { 0.0 } else { wave(t) });
        assert_eq!(establish(1912, &z, &cfg()), Err(TuringFailure::NoCertifiedBracket { n: 1913 }));
    }

    #[test]
    fn a_z_fault_is_a_fault_not_a_candidate_failure() {
        struct Faulty;
        impl ZSource for Faulty {
            fn z(&self, _t: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
                Err(ZFault::NanHeight)
            }
            fn z_over(&self, _lo: f64, _hi: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
                Err(ZFault::ImaginaryPartNonzero)
            }
        }
        assert_eq!(
            establish(1912, &Faulty, &cfg()),
            Err(TuringFailure::Fault(ZFault::ImaginaryPartNonzero))
        );
    }

    #[test]
    fn a_fault_while_isolating_a_block_propagates() {
        // Z > 0 after g_1912: the block [1912, 1914) has no sign change and needs sampling.
        let (_, c) = bracket(1912);
        let mut z = fake(move |t| if t > c { 1.0 } else { wave(t) });
        z.z_fault = true;
        assert_eq!(establish(1912, &z, &cfg()), Err(TuringFailure::Fault(ZFault::NanHeight)));
        assert!(z.z_calls.get() > 0);
    }

    // ---- known answers ----

    /// Eq. 2.1 reaches 1 at g = 2426.3888 (independent bisection in Python);
    /// g_1913 = 2425.49 lies below it and g_1914 = 2426.55 above, so from M = 1912
    /// one block is enough (upper height c_1913) and from M = 1913 the first block
    /// ends at c_1914 and needs a second, ending at c_1915.
    #[test]
    fn one_block_establishes_below_the_threshold_and_two_above_it() {
        let z = fake(wave);
        let below = establish(1912, &z, &cfg()).unwrap();
        assert_eq!(
            below,
            TuringBound { m: 1912, blocks: 1, last_index: 1913, upper: bracket(1913).1 }
        );
        let above = establish(1913, &z, &cfg()).unwrap();
        assert_eq!(
            above,
            TuringBound { m: 1913, blocks: 2, last_index: 1915, upper: bracket(1915).1 }
        );
    }

    /// The same fake with Z positive above c_1914: from M = 1912 the single
    /// block needed lies below that and still establishes; from M = 1913 the
    /// second block [g_1914, g_1916) (g_1915 is bad) holds no sign change and fails.
    #[test]
    fn the_second_block_that_eq_2_1_needs_must_satisfy_rosser() {
        let (_, c) = bracket(1914);
        let z = fake(move |t| if t > c { 1.0 } else { wave(t) });
        assert_eq!(establish(1912, &z, &cfg()).unwrap().blocks, 1);
        assert_eq!(
            establish(1913, &z, &cfg()),
            Err(TuringFailure::RosserFailed { start: 1914, length: 2, credited: 0 })
        );
    }

    #[test]
    fn a_run_of_bad_gram_points_fails_the_candidate() {
        // g_1912 is good; every later Gram point is bad (Z = -cos theta).
        let (_, c) = bracket(1912);
        let z = fake(move |t| if t > c { -wave(t) } else { wave(t) });
        assert_eq!(establish(1912, &z, &cfg()), Err(TuringFailure::BlockTooLong { from: 1912 }));
    }

    /// A block of exactly MAX_BLOCK_LEN Gram intervals is accepted: Z = -cos theta
    /// on (c_1912, c_1927] makes g_1913..g_1927 bad and g_1928 good again, and its
    /// 16 sign changes satisfy Rosser's rule. Eq. 2.1 at c_1928 asks for a second
    /// block, [g_1928, g_1929).
    #[test]
    fn a_block_of_the_longest_length_is_still_a_block() {
        let (_, c0) = bracket(1912);
        let (_, c15) = bracket(1927);
        let z = fake(move |t| if t > c0 && t <= c15 { -wave(t) } else { wave(t) });
        assert_eq!(
            establish(1912, &z, &cfg()),
            Ok(TuringBound { m: 1912, blocks: 2, last_index: 1929, upper: bracket(1929).1 })
        );
    }

    // ---- candidate search ----

    #[test]
    fn the_walk_starts_two_below_the_theta_estimate_and_never_below_minus_one() {
        assert_eq!(walk_start(6000.5), 1908); // floor(6000.5 / pi) = 1910
        assert_eq!(walk_start(3.5 * PI), 1);
        assert_eq!(walk_start(0.0), -1);
    }

    #[test]
    fn qualifying_needs_b_strictly_above_168_pi_and_at_least_the_floor() {
        assert!(!qualifies(RANGE_START, RANGE_START));
        assert!(qualifies(RANGE_START.next_up(), RANGE_START));
        assert!(qualifies(1000.0, 1000.0));
        assert!(!qualifies(999.9, 1000.0));
        assert!(qualifies(1000.1, 1000.0));
    }

    // ---- candidates ----

    fn bound(m: i64) -> TuringBound {
        TuringBound { m, blocks: 1, last_index: m + 1, upper: 0.0 }
    }

    #[test]
    fn at_most_eleven_candidates_are_tried_and_a_twelfth_never_is() {
        let tried = Cell::new(Vec::new());
        let result = try_candidates(100, |m| {
            let mut v = tried.take();
            v.push(m);
            tried.set(v);
            Err(TuringFailure::BadGramPoint)
        });
        assert_eq!(result, Err(TuringFailure::Exhausted { tried: 11 }));
        assert_eq!(tried.take(), (100..111).collect::<Vec<i64>>());
    }

    #[test]
    fn the_first_success_wins_and_stops_the_search() {
        let calls = Cell::new(0);
        let result = try_candidates(100, |m| {
            calls.set(calls.get() + 1);
            if m == 103 { Ok(bound(m)) } else { Err(TuringFailure::BelowRange) }
        });
        assert_eq!(result, Ok(bound(103)));
        assert_eq!(calls.get(), 4);
    }

    #[test]
    fn the_eleventh_candidate_may_still_succeed() {
        let result = try_candidates(0, |m| {
            if m == 10 { Ok(bound(m)) } else { Err(TuringFailure::BadGramPoint) }
        });
        assert_eq!(result, Ok(bound(10)));
    }

    #[test]
    fn a_fault_ends_the_search_at_once() {
        let calls = Cell::new(0);
        let result = try_candidates(0, |_| {
            calls.set(calls.get() + 1);
            if calls.get() == 3 {
                Err(TuringFailure::Fault(ZFault::NanHeight))
            } else {
                Err(TuringFailure::BadGramPoint)
            }
        });
        assert_eq!(result, Err(TuringFailure::Fault(ZFault::NanHeight)));
        assert_eq!(calls.get(), 3);
    }

    /// 168*pi lies between g_288 and g_289, so a small T starts at 289; for
    /// t_min = 1000 the first Gram point with b above 1000 is chosen.
    #[test]
    fn choose_m_starts_at_the_first_qualifying_index() {
        let z = fake(wave);
        assert_eq!(choose_m(100.0, &z, &cfg()).unwrap().m, 289);
        let m = choose_m(1000.0, &z, &cfg()).unwrap().m;
        assert!(bracket(m).0 >= 1000.0 && bracket(m - 1).0 < 1000.0, "m = {m}");
        // NaN falls back to the 168*pi floor
        assert_eq!(choose_m(f64::NAN, &z, &cfg()).unwrap().m, 289);
    }

    #[test]
    fn choose_m_skips_a_candidate_that_fails_and_takes_the_next() {
        // g_289 (odd) is made bad by Z > 0 on its bracket, so 289 is refused and 290 is chosen.
        let (_, c288) = bracket(288);
        let (_, c289) = bracket(289);
        let z = fake(move |t| if t > c288 && t <= c289 { 1.0 } else { wave(t) });
        assert_eq!(establish(289, &z, &cfg()), Err(TuringFailure::BadGramPoint));
        assert_eq!(choose_m(100.0, &z, &cfg()).unwrap().m, 290);
    }

    #[test]
    fn choose_m_gives_up_after_eleven_failing_indices() {
        // Z positive everywhere: odd g are bad, and every block after an even g holds no change.
        let z = fake(|_| 1.0);
        assert_eq!(
            choose_m(100.0, &z, &cfg()),
            Err(TuringFailure::Exhausted { tried: MAX_CANDIDATES })
        );
    }

    #[test]
    fn choose_m_reports_a_theta_failure_as_a_fault() {
        let z = fake(wave);
        assert!(matches!(
            choose_m(f64::INFINITY, &z, &cfg()),
            Err(TuringFailure::Fault(ZFault::Theta(_)))
        ));
    }

    // ---- real Z ----

    #[test]
    fn real_z_establishes_at_the_first_gram_point_above_168_pi() {
        let z = RealZ::new(&cfg()).unwrap();
        let bound = establish(289, &z, &cfg()).unwrap();
        assert_eq!((bound.m, bound.blocks), (289, 1));
        assert!(bound.last_index > 289);
        assert_eq!(choose_m(100.0, &z, &cfg()).unwrap(), bound);
    }
}
