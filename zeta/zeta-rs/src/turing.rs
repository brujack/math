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

use crate::boundary::{Boundary, certify_boundary, is_good};
use crate::config::VerifyConfig;
use crate::interval::Interval;
use crate::isolate::{GramBlock, IsolateError, Point, PointsFault, isolate_block, merge_points};
use crate::theta::{pi_interval, theta};
use crate::zfun::{MAX_HEIGHT, ZFault, ZSource};
use rug::Float;
use rug::float::{Constant, Round};

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

/// Trudgian 2011 Theorem 2.2: |integral of S| <= A + B ln t, with A = 2067/1000 and
/// B = 59/1000 held as exact ratios (the nearest `f64`s are not those decimals).
const TRUDGIAN_A_MILLIS: f64 = 2067.0;
const TRUDGIAN_B_MILLIS: f64 = 59.0;

/// Working precision of the eq. 2.1 enclosure: far more than a block count needs.
const RHS_PRECISION: u32 = 128;

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
    /// g_M's certified boundary: b_M with its sign and the zero-free bracket
    /// (the one source of truth for b_M, and for T inside g_M's bracket).
    pub boundary: Boundary,
}

/// An inconsistency in the points Turing's pass was given: never a candidate failure.
#[derive(Debug, Clone, PartialEq)]
pub enum InternalFault {
    /// An adjacent pair of points lies in no single Gram block.
    PairInNoBlock,
    /// The merged points carried a NaN height or one height with two signs.
    Points(PointsFault),
    /// T is NaN or infinite.
    NonFiniteHeight,
    /// T is above `zfun::MAX_HEIGHT`, the largest height Z is evaluated at.
    HeightAboveRange,
    /// A Gram index would overflow `i64`.
    IndexOverflow,
    /// Eq. 2.1 gave a bound that is not finite and positive, or its height was not.
    BadBlockBound,
    /// `isolate_block` refused an interval that Turing built itself.
    Isolate(IsolateError),
}

impl std::fmt::Display for InternalFault {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::PairInNoBlock => {
                f.write_str("an adjacent pair of points lies in no single Gram block")
            }
            Self::Points(e) => write!(f, "{e}"),
            Self::NonFiniteHeight => f.write_str("T is not finite"),
            Self::HeightAboveRange => f.write_str("T is above the largest height Z supports"),
            Self::IndexOverflow => f.write_str("a Gram index overflowed"),
            Self::BadBlockBound => f.write_str("eq. 2.1 gave no finite positive block bound"),
            Self::Isolate(e) => write!(f, "isolate_block refused a Turing block: {e}"),
        }
    }
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
            Self::Internal(e) => write!(f, "internal fault: {e}"),
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

/// Outward-rounded enclosure of the right side of Trudgian's eq. 2.1 at `g_p`:
/// (b / 6pi) ln^2 g_p + ((a - b ln 2pi) / 6pi) ln g_p. `None` when `g_p` is not
/// positive (its logarithm has no enclosure) or a step has none.
fn trudgian_rhs(g_p: f64) -> Option<Interval> {
    let prec = RHS_PRECISION;
    let thousand = Interval::point(1000.0, prec);
    let a = Interval::point(TRUDGIAN_A_MILLIS, prec).div(&thousand).ok()?;
    let b = Interval::point(TRUDGIAN_B_MILLIS, prec).div(&thousand).ok()?;
    let pi = pi_interval(prec).ok()?;
    let six_pi = Interval::point(6.0, prec).mul(&pi);
    let ln_two_pi = Interval::point(2.0, prec).mul(&pi).ln().ok()?;
    let ln = Interval::point(g_p, prec).ln().ok()?;
    let quadratic = b.div(&six_pi).ok()?.mul(&ln).mul(&ln);
    let linear = a.sub(&b.mul(&ln_two_pi)).div(&six_pi).ok()?.mul(&ln);
    Some(quadratic.add(&linear))
}

/// Blocks eq. 2.1 asks for when the last block's upper height is `g_p`: the smallest
/// integer strictly above the enclosure's upper end, so no rounding can leave one
/// block too few. A bound that is not finite and positive (which a NaN, infinite or
/// non-positive height gives) is an internal fault, never zero blocks.
fn blocks_needed(g_p: f64) -> Result<usize, InternalFault> {
    let rhs = trudgian_rhs(g_p).ok_or(InternalFault::BadBlockBound)?;
    if !rhs.hi().is_finite() || *rhs.hi() <= 0.0 {
        return Err(InternalFault::BadBlockBound);
    }
    let (floor, _) = rhs.hi().to_integer_round(Round::Down).ok_or(InternalFault::BadBlockBound)?;
    let floor = floor.to_usize().ok_or(InternalFault::BadBlockBound)?;
    Ok(floor + 1)
}

/// One Turing block: the closed range [lo, hi] of heights, from g_`start`, `len` Gram intervals long.
#[derive(Debug, Clone, Copy, PartialEq)]
struct BlockRange {
    lo: f64,
    hi: f64,
    start: i64,
    len: usize,
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
    establish_with(m, z, cfg, &mut None)
}

/// `establish` with a memory of the last Rosser failure: a chain that reaches the
/// block starting at that failure's index fails with it again, without isolating
/// the block a second time. Only a chain that reaches that start is cut short: a
/// candidate before it can still meet eq. 2.1 on blocks that end at or before it.
fn establish_with<Z: ZSource>(
    m: i64,
    z: &Z,
    cfg: &VerifyConfig,
    known: &mut Option<TuringFailure>,
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
        if let Some(failure @ TuringFailure::RosserFailed { start: failed, .. }) = known.as_ref()
            && *failed == start_n
        {
            return Err(failure.clone());
        }
        let len = (end_n - start_n) as usize;
        let block = GramBlock { lo: start.point(), hi: end.point(), expected: len };
        points.extend(isolate_block(&block, z, cfg).map_err(from_isolate)?.points);
        points.extend(between);
        blocks.push(BlockRange { lo: start.point().t, hi: end.point().t, start: start_n, len });
        let verdict =
            check_rosser(&merge_points(points.clone()).map_err(InternalFault::Points)?, &blocks);
        if let Err(failure @ TuringFailure::RosserFailed { .. }) = &verdict {
            *known = Some(failure.clone());
        }
        verdict?;
        let upper = end.bracket().hi();
        if blocks.len() >= blocks_needed(upper)? {
            return Ok(TuringBound {
                m,
                blocks: blocks.len(),
                last_index: end_n,
                upper,
                boundary: first,
            });
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

/// The Gram index after `n`, or an internal fault where it would overflow.
fn next_index(n: i64) -> Result<i64, InternalFault> {
    n.checked_add(1).ok_or(InternalFault::IndexOverflow)
}

/// True when theta(T) - n*pi <= 0 is certified for the enclosure `theta_t` of theta(T),
/// i.e. g_n >= T (theta is increasing at these heights): its upper end is at or
/// below n*pi rounded down.
fn g_at_or_above(n: i64, theta_t: &Interval) -> bool {
    let prec = theta_t.prec();
    let pi_down = Float::with_val_round(prec, Constant::Pi, Round::Down).0;
    let n_pi_down = Float::with_val_round(prec, &pi_down * n, Round::Down).0;
    *theta_t.hi() <= n_pi_down
}

/// The smallest n with g_n >= max(T, 168*pi), certified through theta(T) - n*pi <= 0
/// at the precision cap. An index where that is uncertain is passed over (the next
/// is certain), so M is never smaller than the true first index. T may then lie
/// inside g_M's zero-free bracket. The 168*pi test on b_M is `establish`'s.
fn first_candidate(t: f64, cfg: &VerifyConfig) -> Result<i64, TuringFailure> {
    if !t.is_finite() {
        return Err(InternalFault::NonFiniteHeight.into());
    }
    if t > MAX_HEIGHT {
        return Err(InternalFault::HeightAboveRange.into());
    }
    let theta_t = theta(t.max(RANGE_START), cfg.precision_cap()).map_err(ZFault::Theta)?;
    let mut n = walk_start(theta_t.lo().to_f64());
    while !g_at_or_above(n, &theta_t) {
        n = next_index(n)?;
    }
    Ok(n)
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

/// The smallest M with g_M >= max(T, 168*pi) at which Turing's method establishes
/// N(g_M) <= M + 1, trying at most `MAX_CANDIDATES` consecutive indices (a
/// candidate refused for any reason, or cut short by an already-failed block,
/// still counts as tried). T that is not finite is an internal fault.
pub fn choose_m<Z: ZSource>(
    t: f64,
    z: &Z,
    cfg: &VerifyConfig,
) -> Result<TuringBound, TuringFailure> {
    let mut known = None;
    try_candidates(first_candidate(t, cfg)?, |m| establish_with(m, z, cfg, &mut known))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::interval::Sign;
    use crate::theta::gram_bracket;
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
        refuse_below: f64,
        z_calls: Cell<usize>,
        over_calls: Cell<usize>,
    }

    fn fake<F: Fn(f64) -> f64>(f: F) -> Fake<F> {
        Fake {
            f,
            z_fault: false,
            refuse_below: f64::NEG_INFINITY,
            z_calls: Cell::new(0),
            over_calls: Cell::new(0),
        }
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
            if hi < self.refuse_below {
                return Ok(None);
            }
            let (a, b) = ((self.f)(lo), (self.f)(hi));
            Ok(Some(span(a.min(b), a.max(b))))
        }
    }

    fn bracket(n: i64) -> (f64, f64) {
        gram_bracket(n, cfg().precision_cap()).unwrap()
    }

    /// g_n's certified boundary under the all-good `wave` fake (the sign is the same under
    /// any fake that agrees with `wave` on the bracket).
    fn boundary_of(n: i64) -> Boundary {
        certify_boundary(n, &fake(wave), &cfg()).unwrap().unwrap()
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
            let rhs = trudgian_rhs(g).unwrap();
            let (lo, hi) = (rhs.lo().to_f64(), rhs.hi().to_f64());
            assert!(lo <= hi && hi - lo < 1e-30, "g = {g}: [{lo}, {hi}] is not tight");
            assert!((lo - want).abs() < 1e-9, "g = {g}: {lo}");
        }
    }

    /// The right side is 1 at g = 2426.3888 and 2 at g = 840759.87 (bisection in
    /// Python), so the block count steps from 1 to 2 and from 2 to 3 there.
    #[test]
    fn block_count_steps_at_the_independent_thresholds() {
        let needed = |g: f64| blocks_needed(g).unwrap();
        assert_eq!(needed(RANGE_START), 1);
        assert_eq!(needed(2426.38), 1);
        assert_eq!(needed(2426.40), 2);
        assert_eq!(needed(840_759.0), 2);
        assert_eq!(needed(840_761.0), 3);
    }

    #[test]
    fn a_height_or_bound_that_is_not_finite_and_positive_is_an_internal_fault() {
        // ln 1 = 0 gives a zero bound; below 1 the bound is negative.
        for g in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY, 0.0, -5.0, 1.0, 0.5] {
            assert_eq!(blocks_needed(g), Err(InternalFault::BadBlockBound), "g = {g}");
        }
        assert_eq!(blocks_needed(1.5), Ok(1));
    }

    /// The certified enclosure must contain eq. 2.1 evaluated independently at 512 bits
    /// with a = 2067/1000, b = 59/1000 and a 512-bit pi, as Floats (never through f64).
    #[test]
    fn trudgian_rhs_encloses_a_512_bit_reference() {
        let p = 512;
        let pi = Float::with_val(p, Constant::Pi);
        let a = Float::with_val(p, 2067) / Float::with_val(p, 1000);
        let b = Float::with_val(p, 59) / Float::with_val(p, 1000);
        let six_pi = Float::with_val(p, 6) * &pi;
        let ln_two_pi = (Float::with_val(p, 2) * &pi).ln();
        for g in [168.0 * PI, 1e3, 2426.3888, 1e5, 840_759.87, 1e7] {
            let ln = Float::with_val(p, g).ln();
            let quadratic = &b / Float::with_val(p, &six_pi) * &ln * &ln;
            let linear =
                (Float::with_val(p, &a) - &b * &ln_two_pi) / Float::with_val(p, &six_pi) * &ln;
            let want = quadratic + linear;
            let rhs = trudgian_rhs(g).unwrap();
            assert!(
                *rhs.lo() <= want && want <= *rhs.hi(),
                "g = {g}: {want} not in [{}, {}]",
                rhs.lo(),
                rhs.hi()
            );
        }
    }

    /// Eq. 2.1 reaches 1 near g = 2426.3888: the block count steps from 1 to 2
    /// between two adjacent `f64`s, found by bisection on the certified upper end.
    #[test]
    fn the_block_count_steps_between_adjacent_floats_at_an_integer_bound() {
        let (mut below, mut above) = (2426.0_f64, 2427.0_f64);
        while f64::from_bits(below.to_bits() + 1) < above {
            let mid = below + (above - below) / 2.0;
            if blocks_needed(mid).unwrap() == 1 { below = mid } else { above = mid }
        }
        assert_eq!(blocks_needed(below), Ok(1));
        assert_eq!(blocks_needed(above), Ok(2));
        assert_eq!(f64::from_bits(below.to_bits() + 1), above);
    }

    // ---- point merging and crediting ----

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
    fn faults_are_told_apart_from_candidate_failures() {
        assert!(TuringFailure::Fault(ZFault::NanHeight).is_fault());
        assert!(
            TuringFailure::Internal(InternalFault::Points(PointsFault::SignConflict)).is_fault()
        );
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
    fn display_gives_the_message_for_every_failure() {
        let shows = |failure: TuringFailure, text: &str| assert_eq!(failure.to_string(), text);
        shows(TuringFailure::BelowRange, "b_M is not above 168*pi");
        shows(TuringFailure::BadGramPoint, "g_M is not a good Gram point");
        shows(TuringFailure::NoCertifiedBracket { n: 7 }, "Gram point 7 has no certified bracket");
        shows(TuringFailure::BlockTooLong { from: 8 }, "no good Gram point soon after g_8");
        shows(
            TuringFailure::RosserFailed { start: 3, length: 2, credited: 1 },
            "block from g_3 of length 2 holds 1 certified sign changes",
        );
        shows(TuringFailure::Exhausted { tried: 11 }, "no candidate of 11 established the bound");
        shows(TuringFailure::Fault(ZFault::NanHeight), "Z fault: height is NaN");
        shows(
            TuringFailure::Internal(InternalFault::Points(PointsFault::SignConflict)),
            "internal fault: one height carries two different certified signs",
        );
    }

    #[test]
    fn display_gives_the_message_for_every_internal_fault() {
        let shows = |fault: InternalFault, text: &str| assert_eq!(fault.to_string(), text);
        shows(
            InternalFault::PairInNoBlock,
            "an adjacent pair of points lies in no single Gram block",
        );
        shows(
            InternalFault::Points(PointsFault::SignConflict),
            "one height carries two different certified signs",
        );
        shows(InternalFault::Points(PointsFault::NanHeight), "a point height is NaN");
        shows(InternalFault::NonFiniteHeight, "T is not finite");
        shows(InternalFault::HeightAboveRange, "T is above the largest height Z supports");
        shows(InternalFault::IndexOverflow, "a Gram index overflowed");
        shows(InternalFault::BadBlockBound, "eq. 2.1 gave no finite positive block bound");
        shows(
            InternalFault::Isolate(IsolateError::BadInterval),
            &format!("isolate_block refused a Turing block: {}", IsolateError::BadInterval),
        );
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
            TuringBound {
                m: 1912,
                blocks: 1,
                last_index: 1913,
                upper: bracket(1913).1,
                boundary: boundary_of(1912)
            }
        );
        let above = establish(1913, &z, &cfg()).unwrap();
        assert_eq!(
            above,
            TuringBound {
                m: 1913,
                blocks: 2,
                last_index: 1915,
                upper: bracket(1915).1,
                boundary: boundary_of(1913)
            }
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

    /// Block [g_1912, g_1916) with bad g_1913..g_1915 (signs + - +) needs 4 sign changes.
    /// Sampling (depth 2, no moved points) finds only a dip at the quarter point and one at
    /// the midpoint (the other quarter point is blind), which alone give 2; the bad Gram
    /// points between them supply the other 2, so dropping them from the merged points
    /// must fail the block.
    #[test]
    fn a_bad_gram_point_inside_a_block_supplies_its_alternations() {
        let cfg = VerifyConfig::new(1.0, 512, 2, false).unwrap();
        let brackets: Vec<(f64, f64)> = (1912..=1916).map(bracket).collect();
        let (lo, hi) = (boundary_of(1912).point().t, boundary_of(1916).point().t);
        let mid = lo + (hi - lo) / 2.0;
        let quarter = lo + (mid - lo) / 2.0;
        let signs = [1.0, 1.0, -1.0, 1.0, 1.0];
        let z = fake(move |t| {
            if t > brackets[4].1 {
                return wave(t);
            }
            let in_bracket = brackets.iter().zip(signs).find(|((b, c), _)| (*b..=*c).contains(&t));
            match in_bracket {
                Some((_, sign)) => sign,
                None if t == quarter || t == mid => -1.0,
                None => 0.0,
            }
        });
        let bound = establish(1912, &z, &cfg).unwrap();
        assert_eq!((bound.m, bound.last_index >= 1916), (1912, true));
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
            Ok(TuringBound {
                m: 1912,
                blocks: 2,
                last_index: 1929,
                upper: bracket(1929).1,
                boundary: boundary_of(1912)
            })
        );
    }

    /// One bad Gram point past the longest block fails the candidate even though
    /// a good point follows: Z = -cos theta on (c_1912, c_1928] makes g_1913..g_1928
    /// bad (16 points, a block of 17 intervals) and g_1929 good again. The search
    /// for the next good point must stop at g_(from + MAX_BLOCK_LEN), not run on.
    #[test]
    fn a_block_one_past_the_longest_length_fails_even_with_a_good_point_after() {
        let (_, c0) = bracket(1912);
        let (_, c16) = bracket(1928);
        let z = fake(move |t| if t > c0 && t <= c16 { -wave(t) } else { wave(t) });
        assert_eq!(establish(1912, &z, &cfg()), Err(TuringFailure::BlockTooLong { from: 1912 }));
    }

    // ---- candidate search ----

    #[test]
    fn the_walk_starts_two_below_the_theta_estimate_and_never_below_minus_one() {
        assert_eq!(walk_start(6000.5), 1908); // floor(6000.5 / pi) = 1910
        assert_eq!(walk_start(3.5 * PI), 1);
        assert_eq!(walk_start(0.0), -1);
    }

    fn theta_enclosure(lo: f64, hi: f64) -> Interval {
        span(lo, hi)
    }

    #[test]
    fn g_at_or_above_needs_the_whole_theta_enclosure_at_or_below_n_pi() {
        // pi = 3.14159...: hi = 3.1 is below 1*pi, 3.2 is above.
        assert!(g_at_or_above(1, &theta_enclosure(3.0, 3.1)));
        assert!(!g_at_or_above(1, &theta_enclosure(3.0, 3.2)));
        assert!(g_at_or_above(0, &theta_enclosure(-1.0, 0.0)));
        assert!(!g_at_or_above(0, &theta_enclosure(-1.0, 1e-9)));
        assert!(g_at_or_above(2, &theta_enclosure(6.0, 2.0 * PI - 1e-9)));
        assert!(!g_at_or_above(2, &theta_enclosure(6.0, 2.0 * PI + 1e-9)));
    }

    /// g_1912 = 2424.4358, g_1913 = 2425.4907, g_1914 = 2426.5457 (Python, independent).
    #[test]
    fn m_is_the_smallest_index_with_g_m_at_or_above_t() {
        let first = |t: f64| first_candidate(t, &cfg()).unwrap();
        assert_eq!(first(2425.49), 1913); // just below g_1913
        assert_eq!(first(2425.4908), 1914); // just above g_1913
        assert_eq!(first(2424.0), 1912);
        // T at b_1913 lies inside g_1913's bracket, so g_1913 >= T still holds
        assert_eq!(first(bracket(1913).0), 1913);
        // T at c_1913 is above g_1913
        assert_eq!(first(bracket(1913).1), 1914);
        // below 168*pi the floor is 168*pi: g_288 = 527.697 < 168*pi <= g_289
        assert_eq!(first(0.0), 289);
        assert_eq!(first(-5.0), 289);
        assert_eq!(first(100.0), 289);
    }

    #[test]
    fn a_t_above_the_z_range_is_refused_before_any_work() {
        let z = fake(wave);
        for t in [1e300, MAX_HEIGHT * 2.0, MAX_HEIGHT.next_up()] {
            assert_eq!(
                choose_m(t, &z, &cfg()),
                Err(TuringFailure::Internal(InternalFault::HeightAboveRange)),
                "t = {t}"
            );
        }
        assert_eq!((z.over_calls.get(), z.z_calls.get()), (0, 0));
    }

    /// T = MAX_HEIGHT is inside the range: the walk finds g_M at about theta(1e10)/pi ~ 3e10.
    #[test]
    fn a_t_at_the_z_range_is_accepted_by_the_index_search() {
        let m = first_candidate(MAX_HEIGHT, &cfg()).unwrap();
        assert!((1e10..1e11).contains(&(m as f64)), "m = {m}");
    }

    #[test]
    fn the_index_step_refuses_to_overflow() {
        assert_eq!(next_index(5), Ok(6));
        assert_eq!(next_index(-1), Ok(0));
        assert_eq!(next_index(i64::MAX - 1), Ok(i64::MAX));
        assert_eq!(next_index(i64::MAX), Err(InternalFault::IndexOverflow));
    }

    #[test]
    fn a_t_that_is_not_finite_is_refused_before_any_work() {
        let z = fake(wave);
        for t in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert_eq!(
                choose_m(t, &z, &cfg()),
                Err(TuringFailure::Internal(InternalFault::NonFiniteHeight)),
                "t = {t}"
            );
        }
        assert_eq!((z.over_calls.get(), z.z_calls.get()), (0, 0));
    }

    #[test]
    fn choose_m_carries_g_m_s_boundary_with_t_inside_its_bracket() {
        let (b, c) = bracket(1913);
        let got = choose_m(b, &fake(wave), &cfg()).unwrap();
        assert_eq!(got.m, 1913);
        assert_eq!(got.boundary, boundary_of(1913));
        assert!(got.boundary.bracket().lo() <= b && b <= got.boundary.bracket().hi());
        assert_eq!((got.boundary.point().t, got.boundary.bracket().hi()), (b, c));
    }

    #[test]
    fn indices_below_the_first_candidate_are_never_certified() {
        // Every bracket below g_1913's is refused: a walk that certified them would fail.
        let mut z = fake(wave);
        z.refuse_below = bracket(1913).0;
        assert_eq!(choose_m(2425.49, &z, &cfg()).unwrap().m, 1913);
    }

    /// Z positive above c_1914: from M = 1913 the second block [g_1914, g_1916) fails.
    /// A later chain that reaches g_1914 fails with the remembered failure, and the block
    /// is not isolated again; a chain that ends before g_1914 still establishes.
    #[test]
    fn a_failed_block_is_isolated_once() {
        let (_, c) = bracket(1914);
        let z = fake(move |t| if t > c { 1.0 } else { wave(t) });
        let mut known = None;
        let failure = Err(TuringFailure::RosserFailed { start: 1914, length: 2, credited: 0 });
        assert_eq!(establish_with(1913, &z, &cfg(), &mut known).map(|b| b.m), failure);
        let calls = z.z_calls.get();
        assert!(calls > 1000, "the failed block was sampled: {calls}");
        assert_eq!(establish_with(1914, &z, &cfg(), &mut known).map(|b| b.m), failure);
        assert_eq!(z.z_calls.get(), calls, "g_1914's block was not sampled again");
        // g_1912's single block ends at g_1913 and needs no more
        assert_eq!(establish_with(1912, &z, &cfg(), &mut known).unwrap().blocks, 1);
        assert_eq!(known, failure.err());
    }

    // ---- candidates ----

    fn bound(m: i64) -> TuringBound {
        TuringBound { m, blocks: 1, last_index: m + 1, upper: 0.0, boundary: boundary_of(1000) }
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

    /// 168*pi lies between g_288 and g_289, so a small T starts at 289; for T = 1000
    /// the first index with g_M >= 1000 is chosen (c_{M-1} < 1000 < c_M).
    #[test]
    fn choose_m_starts_at_the_first_index_with_g_m_at_or_above_t() {
        let z = fake(wave);
        assert_eq!(choose_m(100.0, &z, &cfg()).unwrap().m, 289);
        let m = choose_m(1000.0, &z, &cfg()).unwrap().m;
        assert!(bracket(m - 1).1 < 1000.0 && bracket(m).1 > 1000.0, "m = {m}");
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
