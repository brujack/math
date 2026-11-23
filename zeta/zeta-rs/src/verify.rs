//! One-pass verification up to T (spec R4, R10, R11, R17; plan Task 9).
//!
//! `verify` chooses M by Turing's method, certifies every Gram point from g_-1
//! to g_M, cuts [b_-1, b_M] into Brent blocks, isolates every block on a
//! private rayon pool, and only then counts L, the sign changes of all the
//! collected certified points sorted by height. L = M + 1 proves every zero up
//! to g_M is on the line and simple; the zeros up to T are those whose
//! sign-change interval lies below T (the interval holding T is bisected).
//!
//! Nothing here is credited on trust: Rosser's expected counts only decide where
//! to subdivide and which blocks are reported, and anything unexpected is a
//! `Fault` (exit 6) or a `NotVerified` (exit 3), never a quiet pass.

use std::io::{self, Write};
use std::panic::{AssertUnwindSafe, catch_unwind};

use rayon::prelude::*;
use rayon::{ThreadPool, ThreadPoolBuildError, ThreadPoolBuilder};

use crate::boundary::{Boundary, ZeroFreeBracket, certify_boundary};
use crate::config::VerifyConfig;
use crate::interval::Sign;
use crate::isolate::{
    BlockPoints, GramBlock, IsolateError, Point, Straddle, alternations, isolate_block,
    resolve_straddle,
};
use crate::turing::{InternalFault, TuringBound, TuringFailure, choose_m};
use crate::zfun::{ZFault, ZSource};

/// A run of Gram intervals g_`first` .. g_`last`, named when a block stays unresolved.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GramSpan {
    pub first: i64,
    pub last: i64,
}

/// Why nothing is claimed (exit 3).
#[derive(Debug, Clone, PartialEq)]
pub enum NotVerifiedReason {
    /// Turing's method did not establish N(g_M) <= M + 1 at any candidate.
    Turing(TuringFailure),
    /// g_-1 has no certified bracket, so L has no left boundary.
    NoLeftBoundary,
    /// No Gram block covers [b_-1, b_M].
    NoBlocks,
    /// L is below M + 1: some zero's sign change was not found.
    ShortCount { found: usize, needed: usize },
    /// The zero in the sign-change interval holding T could not be put on one side of T.
    ZeroSideUncertain,
}

/// An implementation fault (exit 6): never reported as merely "not verified".
#[derive(Debug, Clone, PartialEq)]
pub enum Fault {
    /// Turing's pass hit a fault.
    Turing(TuringFailure),
    /// Z reported a fault.
    Z(ZFault),
    /// `isolate_block` or `resolve_straddle` refused an input verify built itself.
    Isolate(IsolateError),
    /// A NaN height, or one height with two signs, among the collected points.
    Points(InternalFault),
    /// L > M + 1, which a correct implementation cannot produce.
    TooManySignChanges { found: usize, bound: usize },
    /// A worker thread panicked.
    WorkerPanicked,
}

impl std::fmt::Display for Fault {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Turing(e) => write!(f, "Turing's method: {e}"),
            Self::Z(e) => write!(f, "Z fault: {e}"),
            Self::Isolate(e) => write!(f, "isolation refused its input: {e}"),
            Self::Points(e) => write!(f, "collected points: {e}"),
            Self::TooManySignChanges { found, bound } => {
                write!(f, "L > M+1 (L = {found}, M+1 = {bound})")
            }
            Self::WorkerPanicked => f.write_str("worker panicked"),
        }
    }
}

/// The outcome of `verify`.
#[derive(Debug, Clone, PartialEq)]
pub enum Verdict {
    /// Every zero with 0 < Im <= T is on the line and simple. `intervals[k]` is
    /// the certified sign-change interval holding the (k+1)-th zero; `count == intervals.len()`.
    Verified { count: usize, intervals: Vec<(f64, f64)> },
    /// Nothing is claimed; `blocks` names the Gram blocks left unresolved.
    NotVerified { reason: NotVerifiedReason, blocks: Vec<GramSpan> },
    /// An implementation fault.
    InternalFault { reason: Fault },
    /// The fallback notice could not be written to the caller's stderr (exit 4).
    WriteFailed { error: String },
}

/// How `verify` runs its blocks.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum PoolPolicy {
    /// A private pool with rayon's default thread count.
    #[default]
    Parallel,
    /// A private pool with this many threads.
    Threads(usize),
    /// No pool: every block runs on the calling thread.
    Serial,
    /// A pool whose thread spawn fails, so the build error and fallback are testable.
    FailBuild,
}

/// The private pool, or `None` for serial. The global pool is never used (R11):
/// every parallel step runs inside `ThreadPool::install` on this pool.
struct Runner {
    pool: Option<ThreadPool>,
}

fn build_pool(policy: PoolPolicy) -> Result<Option<ThreadPool>, ThreadPoolBuildError> {
    match policy {
        PoolPolicy::Serial => Ok(None),
        PoolPolicy::Parallel => ThreadPoolBuilder::new().build().map(Some),
        PoolPolicy::Threads(n) => ThreadPoolBuilder::new().num_threads(n).build().map(Some),
        PoolPolicy::FailBuild => ThreadPoolBuilder::new()
            .spawn_handler(|_| Err(io::Error::other("forced by PoolPolicy::FailBuild")))
            .build()
            .map(Some),
    }
}

impl Runner {
    /// Builds the pool; when it cannot be built, says so on `stderr` and goes serial.
    fn new<E: Write>(policy: PoolPolicy, stderr: &mut E) -> io::Result<Runner> {
        match build_pool(policy) {
            Ok(pool) => Ok(Runner { pool }),
            Err(error) => {
                writeln!(stderr, "Parallel mode unavailable ({error}); falling back to serial.")?;
                Ok(Runner { pool: None })
            }
        }
    }

    /// Runs `f`, turning a panic into a fault (no partial verdict survives it).
    fn guard<R>(f: impl FnOnce() -> R) -> Result<R, Fault> {
        catch_unwind(AssertUnwindSafe(f)).map_err(|_| Fault::WorkerPanicked)
    }

    /// `f(0..len)` in index order, on the pool when there is one.
    fn map<R: Send>(
        &self,
        len: usize,
        f: impl Fn(usize) -> R + Sync + Send,
    ) -> Result<Vec<R>, Fault> {
        Runner::guard(|| match &self.pool {
            Some(pool) => pool.install(|| (0..len).into_par_iter().map(&f).collect()),
            None => (0..len).map(&f).collect(),
        })
    }
}

/// Good means (-1)^n Z(g_n) > 0.
fn is_good(n: i64, sign: Sign) -> bool {
    sign == if n.rem_euclid(2) == 0 { Sign::Positive } else { Sign::Negative }
}

/// A Brent block ready to isolate: ends at good Gram points, `between` holds the
/// certified bad Gram points inside it.
#[derive(Debug, Clone, PartialEq)]
struct PlannedBlock {
    span: GramSpan,
    block: GramBlock,
    between: Vec<Point>,
}

/// Cuts the usable boundaries (ascending Gram index) into blocks that end at a
/// good Gram point, Rosser's expected count being the number of Gram intervals
/// spanned. An unusable Gram point is simply absent, which merges its block with
/// the next (R22). A trailing run with no good end becomes a block of its own so
/// the range stays covered.
fn plan_blocks(usable: &[(i64, Boundary)]) -> Vec<PlannedBlock> {
    let mut planned = Vec::new();
    let Some(&(first_n, first)) = usable.first() else {
        return planned;
    };
    let (mut start_n, mut start) = (first_n, first);
    let mut between = Vec::new();
    for (idx, &(n, boundary)) in usable.iter().enumerate().skip(1) {
        let is_last = idx + 1 == usable.len();
        if is_good(n, boundary.point().sign) || is_last {
            planned.push(PlannedBlock {
                span: GramSpan { first: start_n, last: n },
                block: GramBlock {
                    lo: start.point(),
                    hi: boundary.point(),
                    expected: (n - start_n) as usize,
                },
                between: std::mem::take(&mut between),
            });
            (start_n, start) = (n, boundary);
        } else {
            between.push(boundary.point());
        }
    }
    planned
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

/// The adjacent pairs with different signs among the merged points whose height
/// lies in `[lo, hi]` (R4: L counts only [b_-1, b_M]).
fn sign_changes(
    points: Vec<Point>,
    lo: f64,
    hi: f64,
) -> Result<Vec<(Point, Point)>, InternalFault> {
    let inside: Vec<Point> =
        merge_points(points)?.into_iter().filter(|p| lo <= p.t && p.t <= hi).collect();
    Ok(inside.windows(2).filter(|w| w[0].sign != w[1].sign).map(|w| (w[0], w[1])).collect())
}

/// Every point found, and the blocks still short of Rosser's count after the neighbour search.
#[derive(Debug, Clone, PartialEq)]
struct Isolated {
    points: Vec<Point>,
    unresolved: Vec<GramSpan>,
}

/// Rosser neighbour search for block `i`: merge it with its neighbours (expected
/// counts add), re-isolate the union and judge it by every point known inside it.
/// Returns the fresh points (all certified, so always usable) and whether the union is resolved.
fn search_neighbours<Z: ZSource>(
    i: usize,
    planned: &[PlannedBlock],
    results: &[BlockPoints],
    z: &Z,
    cfg: &VerifyConfig,
) -> Result<(Vec<Point>, bool), Fault> {
    let (a, b) = (i.saturating_sub(1), (i + 1).min(planned.len() - 1));
    let union = GramBlock {
        lo: planned[a].block.lo,
        hi: planned[b].block.hi,
        expected: planned[a..=b].iter().map(|p| p.block.expected).sum(),
    };
    let fresh = isolate_block(&union, z, cfg).map_err(Fault::Isolate)?;
    let known: Vec<Point> = results[a..=b]
        .iter()
        .flat_map(|r| r.points.iter().copied())
        .chain(fresh.points.iter().copied())
        .collect();
    let merged = merge_points(known).map_err(Fault::Points)?;
    Ok((fresh.points, alternations(&merged) >= union.expected))
}

/// Isolates every block, then re-searches each unresolved block with its neighbours.
fn isolate_all<Z: ZSource + Sync>(
    planned: &[PlannedBlock],
    z: &Z,
    cfg: &VerifyConfig,
    runner: &Runner,
) -> Result<Isolated, Fault> {
    let first_pass = runner.map(planned.len(), |i| isolate_block(&planned[i].block, z, cfg))?;
    let mut results = Vec::with_capacity(planned.len());
    for (block, result) in planned.iter().zip(first_pass) {
        let mut found = result.map_err(Fault::Isolate)?;
        found.points.extend(block.between.iter().copied());
        results.push(found);
    }
    let short: Vec<usize> = (0..planned.len()).filter(|&i| !results[i].resolved).collect();
    let searched =
        runner.map(short.len(), |k| search_neighbours(short[k], planned, &results, z, cfg))?;
    let mut points: Vec<Point> = results.iter().flat_map(|r| r.points.iter().copied()).collect();
    let mut unresolved = Vec::new();
    for (&i, outcome) in short.iter().zip(searched) {
        let (fresh, resolved) = outcome?;
        points.extend(fresh);
        if !resolved {
            unresolved.push(planned[i].span);
        }
    }
    Ok(Isolated { points, unresolved })
}

/// Certifies g_-1 .. g_(m-1) on the pool; g_m is `last`, the boundary Turing's
/// method already holds. Unusable Gram points are absent from the result.
fn certify_gram_points<Z: ZSource + Sync>(
    m: i64,
    last: Boundary,
    z: &Z,
    cfg: &VerifyConfig,
    runner: &Runner,
) -> Result<Vec<(i64, Boundary)>, Fault> {
    let count = (m + 1) as usize;
    let certified = runner.map(count, |i| certify_boundary(i as i64 - 1, z, cfg))?;
    let mut usable = Vec::with_capacity(count + 1);
    for (i, result) in certified.into_iter().enumerate() {
        if let Some(boundary) = result.map_err(Fault::Z)? {
            usable.push((i as i64 - 1, boundary));
        }
    }
    usable.push((m, last));
    Ok(usable)
}

/// The sign-change intervals whose zero lies at or below `t`; `None` when the
/// zero in the interval holding `t` cannot be put on one side of it (R23).
fn intervals_up_to<Z: ZSource>(
    t: f64,
    changes: &[(Point, Point)],
    bracket: &ZeroFreeBracket,
    z: &Z,
    cfg: &VerifyConfig,
) -> Result<Option<Vec<(f64, f64)>>, Fault> {
    let mut intervals = Vec::new();
    for &(a, b) in changes {
        match resolve_straddle(a, b, t, Some(bracket), z, cfg).map_err(Fault::Isolate)? {
            Straddle::Below => intervals.push((a.t, b.t)),
            Straddle::Above => {}
            Straddle::Uncertain => return Ok(None),
        }
    }
    Ok(Some(intervals))
}

fn not_verified(reason: NotVerifiedReason, blocks: Vec<GramSpan>) -> Verdict {
    Verdict::NotVerified { reason, blocks }
}

/// Everything after Turing's method: blocks, one-pass count L, and the zeros up to `t`.
fn verify_with_bound<Z: ZSource + Sync>(
    t: f64,
    bound: &TuringBound,
    z: &Z,
    cfg: &VerifyConfig,
    runner: &Runner,
) -> Result<Verdict, Fault> {
    let usable = certify_gram_points(bound.m, bound.boundary, z, cfg, runner)?;
    let (first_n, left) = usable[0];
    if first_n != -1 {
        return Ok(not_verified(NotVerifiedReason::NoLeftBoundary, Vec::new()));
    }
    let planned = plan_blocks(&usable);
    if planned.is_empty() {
        return Ok(not_verified(NotVerifiedReason::NoBlocks, Vec::new()));
    }
    let isolated = isolate_all(&planned, z, cfg, runner)?;
    let changes = sign_changes(isolated.points, left.point().t, bound.boundary.point().t)
        .map_err(Fault::Points)?;
    let needed = (bound.m + 1) as usize;
    if changes.len() > needed {
        return Err(Fault::TooManySignChanges { found: changes.len(), bound: needed });
    }
    if changes.len() < needed {
        let reason = NotVerifiedReason::ShortCount { found: changes.len(), needed };
        return Ok(not_verified(reason, isolated.unresolved));
    }
    let Some(intervals) = intervals_up_to(t, &changes, &bound.boundary.bracket(), z, cfg)? else {
        return Ok(not_verified(NotVerifiedReason::ZeroSideUncertain, Vec::new()));
    };
    Ok(Verdict::Verified { count: intervals.len(), intervals })
}

fn run<Z: ZSource + Sync>(
    t: f64,
    z: &Z,
    cfg: &VerifyConfig,
    runner: &Runner,
) -> Result<Verdict, Fault> {
    let bound = match Runner::guard(|| choose_m(t, z, cfg))? {
        Ok(bound) => bound,
        Err(failure) if failure.is_fault() => return Err(Fault::Turing(failure)),
        Err(failure) => return Ok(not_verified(NotVerifiedReason::Turing(failure), Vec::new())),
    };
    verify_with_bound(t, &bound, z, cfg, runner)
}

/// Verifies the Riemann Hypothesis up to `t`: the one verdict a run reports.
/// `stderr` receives the serial-fallback notice when the pool cannot be built.
pub fn verify<Z: ZSource + Sync, E: Write>(
    t: f64,
    z: &Z,
    cfg: &VerifyConfig,
    policy: PoolPolicy,
    stderr: &mut E,
) -> Verdict {
    let runner = match Runner::new(policy, stderr) {
        Ok(runner) => runner,
        Err(error) => return Verdict::WriteFailed { error: error.to_string() },
    };
    run(t, z, cfg, &runner).unwrap_or_else(|reason| Verdict::InternalFault { reason })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::interval::Interval;
    use crate::theta::gram_bracket;
    use crate::turing::choose_m;
    use rug::Float;
    use std::f64::consts::PI;

    fn cfg() -> VerifyConfig {
        VerifyConfig::default()
    }

    /// Depth 8 keeps an unresolvable block to 257 points instead of 2^16.
    fn shallow() -> VerifyConfig {
        VerifyConfig::new(1.0, 512, 8, true).unwrap()
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

    /// theta by Stirling in f64: the fakes need only a smooth phase with theta(g_n) = n*pi.
    fn theta_f64(t: f64) -> f64 {
        t / 2.0 * (t / (2.0 * PI)).ln() - t / 2.0 - PI / 8.0
            + 1.0 / (48.0 * t)
            + 7.0 / (5760.0 * t.powi(3))
    }

    /// cos(theta(t)): every Gram point good, one sign change per Gram interval.
    fn wave(t: f64) -> f64 {
        theta_f64(t).cos()
    }

    /// The zero of `wave` with theta = (k + 1/2) pi.
    fn wave_zero(k: i64) -> f64 {
        let target = (k as f64 + 0.5) * PI;
        let (mut lo, mut hi) = (10.0, 1000.0);
        for _ in 0..200 {
            let mid = 0.5 * (lo + hi);
            if theta_f64(mid) < target {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        lo
    }

    fn bracket_of(n: i64) -> (f64, f64) {
        gram_bracket(n, 512).unwrap()
    }

    /// Phase of t in Gram intervals past g_n0.
    fn u_of(t: f64, n0: i64) -> f64 {
        (theta_f64(t) - n0 as f64 * PI) / PI
    }

    /// +1 over u in [0, span] (Gram intervals past g_n0) except -1 in each `negs`
    /// window; `wave` elsewhere. Puts bad Gram points and chosen change counts into a block.
    fn patched(t: f64, n0: i64, span: f64, negs: &[(f64, f64)]) -> f64 {
        let u = u_of(t, n0);
        if !(0.0..=span).contains(&u) {
            return wave(t);
        }
        if negs.iter().any(|&(a, b)| a <= u && u <= b) { -1.0 } else { 1.0 }
    }

    const PAIR: [(f64, f64); 1] = [(0.25, 0.75)];
    const FOUR_FIRST: [(f64, f64); 2] = [(0.3, 0.7), (1.3, 1.7)];
    const FOUR_SECOND: [(f64, f64); 2] = [(2.3, 2.7), (3.3, 3.7)];

    fn span(lo: f64, hi: f64) -> Interval {
        Interval::new(Float::with_val(64, lo), Float::with_val(64, hi)).unwrap()
    }

    fn inside(range: (f64, f64), t: f64) -> bool {
        range.0 <= t && t <= range.1
    }

    /// A Z whose value is `f(t)`; values within 1e-6 of 0 are uncertain. `z_over` is
    /// the end values' span. No interior mutability, so it is `Sync`.
    struct Fake<F: Fn(f64) -> f64 + Sync> {
        f: F,
        refuse_below: f64,
        blind: (f64, f64),
        z_fault: (f64, f64),
        over_fault: (f64, f64),
    }

    fn fake<F: Fn(f64) -> f64 + Sync>(f: F) -> Fake<F> {
        let none = (1.0, 0.0);
        Fake { f, refuse_below: f64::NEG_INFINITY, blind: none, z_fault: none, over_fault: none }
    }

    impl<F: Fn(f64) -> f64 + Sync> ZSource for Fake<F> {
        fn z(&self, t: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
            if inside(self.z_fault, t) {
                return Err(ZFault::NanHeight);
            }
            if inside(self.blind, t) {
                return Ok(Some(span(-1e-6, 1e-6)));
            }
            let v = (self.f)(t);
            Ok(Some(if v.abs() < 1e-6 { span(-1e-6, 1e-6) } else { Interval::point(v, prec) }))
        }

        fn z_over(&self, lo: f64, hi: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
            if inside(self.over_fault, lo) {
                return Err(ZFault::NanHeight);
            }
            if hi < self.refuse_below {
                return Ok(None);
            }
            let (a, b) = ((self.f)(lo), (self.f)(hi));
            Ok(Some(span(a.min(b), a.max(b))))
        }
    }

    fn go<Z: ZSource + Sync>(
        z: &Z,
        t: f64,
        cfg: &VerifyConfig,
        policy: PoolPolicy,
    ) -> (Verdict, String) {
        let mut stderr = Vec::new();
        let verdict = verify(t, z, cfg, policy, &mut stderr);
        (verdict, String::from_utf8(stderr).unwrap())
    }

    fn m_at(t: f64) -> i64 {
        choose_m(t, &fake(wave), &cfg()).unwrap().m
    }

    fn usable_range(f: impl Fn(f64) -> f64 + Sync, from: i64, to: i64) -> Vec<(i64, Boundary)> {
        let z = fake(f);
        (from..=to).map(|n| (n, certify_boundary(n, &z, &cfg()).unwrap().unwrap())).collect()
    }

    // ---- the happy path ----

    #[test]
    fn verifies_the_wave_to_100_with_29_zeros_under_every_policy() {
        let z = fake(wave);
        let (serial, err) = go(&z, 100.0, &cfg(), PoolPolicy::Serial);
        assert_eq!(err, "");
        let Verdict::Verified { count, intervals } = &serial else {
            panic!("expected Verified, got {serial:?}");
        };
        assert_eq!((*count, intervals.len()), (29, 29));
        for (k, &(a, b)) in intervals.iter().enumerate() {
            let zero = wave_zero(k as i64 - 1);
            assert!(a < zero && zero < b, "interval {k} = ({a}, {b}) misses {zero}");
            assert!(wave(a) * wave(b) < 0.0);
        }
        assert!(intervals.windows(2).all(|w| w[0].1 <= w[1].0));
        for policy in [PoolPolicy::Parallel, PoolPolicy::Threads(3)] {
            let (other, err) = go(&z, 100.0, &cfg(), policy);
            assert_eq!((other, err), (serial.clone(), String::new()), "{policy:?}");
        }
    }

    #[test]
    fn a_zero_just_below_or_above_t_is_counted_or_not() {
        let z = fake(wave);
        let zero = wave_zero(10);
        let count = |t: f64| match go(&z, t, &cfg(), PoolPolicy::Serial).0 {
            Verdict::Verified { count, .. } => count,
            other => panic!("expected Verified, got {other:?}"),
        };
        assert_eq!(count(zero - 0.01), 11);
        assert_eq!(count(zero + 0.01), 12);
    }

    #[test]
    fn t_at_b_m_counts_every_zero_below_it() {
        let m = m_at(540.0);
        let t = bracket_of(m).0;
        let (verdict, _) = go(&fake(wave), t, &cfg(), PoolPolicy::Serial);
        let Verdict::Verified { count, .. } = verdict else { panic!("{verdict:?}") };
        assert_eq!(count as i64, m + 1);
    }

    #[test]
    fn a_zero_whose_side_of_t_stays_uncertain_is_not_verified() {
        let zero = wave_zero(10);
        let z = fake(move |t| if (t - zero).abs() < 0.3 { 0.0 } else { wave(t) });
        let (verdict, _) = go(&z, zero, &cfg(), PoolPolicy::Serial);
        assert_eq!(
            verdict,
            Verdict::NotVerified { reason: NotVerifiedReason::ZeroSideUncertain, blocks: vec![] }
        );
    }

    #[test]
    fn a_bad_gram_point_pair_inside_one_block_still_verifies() {
        let z = fake(|t| patched(t, 60, 2.0, &PAIR));
        let (verdict, _) = go(&z, 100.0, &shallow(), PoolPolicy::Serial);
        assert!(matches!(verdict, Verdict::Verified { count: 29, .. }), "{verdict:?}");
    }

    // ---- exit 3 ----

    fn not_verified(verdict: Verdict) -> (NotVerifiedReason, Vec<GramSpan>) {
        match verdict {
            Verdict::NotVerified { reason, blocks } => (reason, blocks),
            other => panic!("expected NotVerified, got {other:?}"),
        }
    }

    fn short_by(deficit: usize, span: GramSpan, f: impl Fn(f64) -> f64 + Sync) {
        let m = m_at(100.0) as usize;
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            let (verdict, _) = go(&fake(&f), 100.0, &shallow(), policy);
            let (reason, blocks) = not_verified(verdict);
            let found = m + 1 - deficit;
            assert_eq!(reason, NotVerifiedReason::ShortCount { found, needed: m + 1 });
            assert_eq!(blocks, vec![span]);
        }
    }

    #[test]
    fn a_missing_sign_change_is_short_and_names_its_block() {
        short_by(2, GramSpan { first: 60, last: 62 }, |t| patched(t, 60, 2.0, &[]));
    }

    #[test]
    fn a_double_root_is_short_and_names_its_block() {
        short_by(2, GramSpan { first: 60, last: 62 }, |t| {
            if (0.0..=2.0).contains(&u_of(t, 60)) { wave(t).abs() } else { wave(t) }
        });
    }

    #[test]
    fn a_sign_that_stays_uncertain_is_short_and_names_its_block() {
        let (lo, hi) = (bracket_of(60).1, bracket_of(62).0);
        let mut z = fake(|t| patched(t, 60, 2.0, &PAIR));
        z.blind = (lo, hi);
        let m = m_at(100.0) as usize;
        let (verdict, _) = go(&z, 100.0, &shallow(), PoolPolicy::Serial);
        let (reason, blocks) = not_verified(verdict);
        assert_eq!(reason, NotVerifiedReason::ShortCount { found: m - 1, needed: m + 1 });
        assert_eq!(blocks, vec![GramSpan { first: 60, last: 62 }]);
    }

    #[test]
    fn an_irregular_pattern_after_g_m_fails_turing() {
        let z = fake(|t| if t > 520.0 { 1.0 } else { wave(t) });
        let (verdict, _) = go(&z, 100.0, &shallow(), PoolPolicy::Serial);
        let (reason, blocks) = not_verified(verdict);
        assert!(matches!(reason, NotVerifiedReason::Turing(_)), "{reason:?}");
        assert!(blocks.is_empty());
    }

    #[test]
    fn an_uncertifiable_g_minus_1_is_not_verified() {
        let mut z = fake(wave);
        z.refuse_below = 12.0;
        let (verdict, _) = go(&z, 100.0, &cfg(), PoolPolicy::Serial);
        assert_eq!(
            verdict,
            Verdict::NotVerified { reason: NotVerifiedReason::NoLeftBoundary, blocks: vec![] }
        );
    }

    #[test]
    fn an_empty_block_list_is_not_verified() {
        let z = fake(wave);
        let boundary = certify_boundary(-1, &z, &cfg()).unwrap().unwrap();
        let bound = TuringBound { m: -1, blocks: 1, last_index: 0, upper: 20.0, boundary };
        let runner = Runner::new(PoolPolicy::Serial, &mut Vec::new()).unwrap();
        let verdict = verify_with_bound(5.0, &bound, &z, &cfg(), &runner).unwrap();
        assert_eq!(
            verdict,
            Verdict::NotVerified { reason: NotVerifiedReason::NoBlocks, blocks: vec![] }
        );
    }

    // ---- exit 6 ----

    fn fault(verdict: Verdict) -> Fault {
        match verdict {
            Verdict::InternalFault { reason } => reason,
            other => panic!("expected InternalFault, got {other:?}"),
        }
    }

    #[test]
    fn an_extra_sign_change_is_an_internal_fault() {
        let m = m_at(100.0) as usize;
        let z = fake(|t| patched(t, 60, 2.0, &FOUR_FIRST));
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            let reason = fault(go(&z, 100.0, &shallow(), policy).0);
            assert_eq!(reason, Fault::TooManySignChanges { found: m + 3, bound: m + 1 });
        }
    }

    #[test]
    fn a_worker_panic_in_isolation_is_an_internal_fault() {
        let z = fake(|t| {
            let u = u_of(t, 60);
            assert!(!(0.2..=0.8).contains(&u), "boom");
            patched(t, 60, 2.0, &PAIR)
        });
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            assert_eq!(fault(go(&z, 100.0, &shallow(), policy).0), Fault::WorkerPanicked);
        }
    }

    #[test]
    fn a_worker_panic_in_certification_is_an_internal_fault() {
        let n100 = bracket_of(100).0;
        let z = fake(move |t| {
            assert!((t - n100).abs() > 1e-3, "boom");
            wave(t)
        });
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            assert_eq!(fault(go(&z, 100.0, &cfg(), policy).0), Fault::WorkerPanicked);
        }
    }

    #[test]
    fn a_panic_while_choosing_m_is_an_internal_fault() {
        let z = fake(|t| {
            assert!(t < 500.0, "boom");
            wave(t)
        });
        assert_eq!(fault(go(&z, 100.0, &cfg(), PoolPolicy::Serial).0), Fault::WorkerPanicked);
    }

    #[test]
    fn a_z_fault_in_certification_is_an_internal_fault() {
        let n100 = bracket_of(100).0;
        let mut z = fake(wave);
        z.over_fault = (n100 - 1e-3, n100 + 1e-3);
        let reason = fault(go(&z, 100.0, &cfg(), PoolPolicy::Serial).0);
        assert_eq!(reason, Fault::Z(ZFault::NanHeight));
    }

    #[test]
    fn a_z_fault_in_isolation_is_an_internal_fault() {
        let mut z = fake(|t| patched(t, 60, 2.0, &PAIR));
        z.z_fault = (bracket_of(60).1, bracket_of(62).0);
        let reason = fault(go(&z, 100.0, &shallow(), PoolPolicy::Serial).0);
        assert_eq!(reason, Fault::Isolate(IsolateError::Fault(ZFault::NanHeight)));
    }

    #[test]
    fn a_turing_fault_is_an_internal_fault_not_a_refusal() {
        let reason = fault(go(&fake(wave), f64::NAN, &cfg(), PoolPolicy::Serial).0);
        assert!(matches!(reason, Fault::Turing(_)), "{reason:?}");
    }

    #[test]
    fn faults_name_themselves() {
        assert_eq!(
            Fault::TooManySignChanges { found: 7, bound: 5 }.to_string(),
            "L > M+1 (L = 7, M+1 = 5)"
        );
        assert_eq!(Fault::WorkerPanicked.to_string(), "worker panicked");
        assert!(Fault::Z(ZFault::NanHeight).to_string().starts_with("Z fault: "));
        assert!(Fault::Points(InternalFault::SignConflict).to_string().contains("two"));
        let turing = Fault::Turing(TuringFailure::BelowRange);
        assert!(turing.to_string().starts_with("Turing's method: "));
        let isolate = Fault::Isolate(IsolateError::BadInterval);
        assert!(isolate.to_string().starts_with("isolation refused its input: "));
    }

    // ---- the one-pass count ----

    #[test]
    fn a_sign_conflict_or_a_nan_height_is_a_fault() {
        let conflict = vec![pt(1.0, pos()), pt(1.0, neg())];
        assert_eq!(sign_changes(conflict, 0.0, 9.0), Err(InternalFault::SignConflict));
        let nan = vec![pt(1.0, pos()), pt(f64::NAN, neg())];
        assert_eq!(sign_changes(nan, 0.0, 9.0), Err(InternalFault::NanHeight));
        // A NaN is a fault even outside the range.
        let far = vec![pt(1.0, pos()), pt(f64::NAN, neg())];
        assert_eq!(sign_changes(far, 5.0, 9.0), Err(InternalFault::NanHeight));
    }

    #[test]
    fn a_duplicate_identical_point_counts_once() {
        let points = vec![pt(2.0, neg()), pt(1.0, pos()), pt(2.0, neg()), pt(1.0, pos())];
        let changes = sign_changes(points, 0.0, 9.0).unwrap();
        assert_eq!(changes, vec![(pt(1.0, pos()), pt(2.0, neg()))]);
    }

    #[test]
    fn only_points_in_the_closed_range_are_counted() {
        let points = vec![
            pt(1.0, neg()),
            pt(2.0, pos()),
            pt(3.0, neg()),
            pt(4.0, pos()),
            pt(5.0, neg()),
            pt(6.0, pos()),
        ];
        let at = |lo: f64, hi: f64| sign_changes(points.clone(), lo, hi).unwrap().len();
        assert_eq!(at(2.0, 5.0), 3);
        assert_eq!(at(2.5, 5.0), 2);
        assert_eq!(at(2.0, 4.5), 2);
        assert_eq!(at(0.0, 9.0), 5);
        assert_eq!(at(3.5, 3.9), 0);
    }

    #[test]
    fn equal_signs_between_points_are_not_a_change() {
        let points = vec![pt(1.0, pos()), pt(2.0, pos()), pt(3.0, neg()), pt(4.0, neg())];
        let changes = sign_changes(points, 0.0, 9.0).unwrap();
        assert_eq!(changes, vec![(pt(2.0, pos()), pt(3.0, neg()))]);
    }

    // ---- planning blocks ----

    #[test]
    fn no_usable_boundary_plans_no_block() {
        assert!(plan_blocks(&[]).is_empty());
        let one = usable_range(wave, 58, 58);
        assert!(plan_blocks(&one).is_empty());
    }

    #[test]
    fn good_boundaries_each_close_a_block_of_one_interval() {
        let planned = plan_blocks(&usable_range(wave, 58, 61));
        let spans: Vec<_> = planned.iter().map(|p| (p.span.first, p.span.last)).collect();
        assert_eq!(spans, vec![(58, 59), (59, 60), (60, 61)]);
        assert!(planned.iter().all(|p| p.block.expected == 1 && p.between.is_empty()));
    }

    #[test]
    fn an_unusable_gram_point_merges_its_block_with_the_next() {
        let mut usable = usable_range(wave, 58, 62);
        usable.remove(2);
        let planned = plan_blocks(&usable);
        let blocks: Vec<_> = planned.iter().map(|p| (p.span, p.block.expected)).collect();
        assert_eq!(
            blocks,
            vec![
                (GramSpan { first: 58, last: 59 }, 1),
                (GramSpan { first: 59, last: 61 }, 2),
                (GramSpan { first: 61, last: 62 }, 1),
            ]
        );
    }

    #[test]
    fn a_bad_gram_point_stays_inside_its_block_as_a_point() {
        let usable = usable_range(|t| patched(t, 60, 2.0, &PAIR), 59, 63);
        let planned = plan_blocks(&usable);
        let block = planned.iter().find(|p| p.span.first == 60).unwrap();
        assert_eq!(block.span, GramSpan { first: 60, last: 62 });
        assert_eq!(block.block.expected, 2);
        assert_eq!(block.block.lo, usable[1].1.point());
        assert_eq!(block.block.hi, usable[3].1.point());
        assert_eq!(block.between, vec![usable[2].1.point()]);
        assert_eq!(block.between[0].sign, pos());
    }

    #[test]
    fn a_trailing_bad_point_still_closes_the_last_block() {
        let usable = usable_range(|t| patched(t, 60, 2.0, &PAIR), 59, 61);
        let planned = plan_blocks(&usable);
        let spans: Vec<_> = planned.iter().map(|p| (p.span.first, p.span.last)).collect();
        assert_eq!(spans, vec![(59, 60), (60, 61)]);
        assert_eq!(planned[1].block.hi, usable[2].1.point());
    }

    // ---- Rosser neighbour search ----

    fn isolate_range(f: impl Fn(f64) -> f64 + Sync, from: i64, to: i64) -> Isolated {
        let planned = plan_blocks(&usable_range(&f, from, to));
        let runner = Runner::new(PoolPolicy::Serial, &mut Vec::new()).unwrap();
        isolate_all(&planned, &fake(&f), &shallow(), &runner).unwrap()
    }

    #[test]
    fn a_first_block_one_pair_short_is_resolved_by_its_next_neighbour() {
        let isolated = isolate_range(|t| patched(t, 60, 4.0, &FOUR_SECOND), 60, 64);
        assert!(isolated.unresolved.is_empty(), "{:?}", isolated.unresolved);
    }

    #[test]
    fn a_last_block_short_is_resolved_by_its_previous_neighbour() {
        let isolated = isolate_range(|t| patched(t, 60, 4.0, &FOUR_FIRST), 60, 64);
        assert!(isolated.unresolved.is_empty(), "{:?}", isolated.unresolved);
    }

    #[test]
    fn a_middle_block_short_is_resolved_by_a_neighbour_that_is_over() {
        let isolated = isolate_range(|t| patched(t, 60, 4.0, &FOUR_SECOND), 58, 66);
        assert!(isolated.unresolved.is_empty(), "{:?}", isolated.unresolved);
        let isolated = isolate_range(|t| patched(t, 60, 4.0, &FOUR_FIRST), 58, 66);
        assert!(isolated.unresolved.is_empty(), "{:?}", isolated.unresolved);
    }

    #[test]
    fn a_block_still_short_after_merging_is_named() {
        let isolated = isolate_range(|t| patched(t, 60, 2.0, &[]), 58, 66);
        assert_eq!(isolated.unresolved, vec![GramSpan { first: 60, last: 62 }]);
    }

    #[test]
    fn a_lone_short_block_is_named_without_a_neighbour() {
        let isolated = isolate_range(|t| patched(t, 60, 2.0, &[]), 60, 62);
        assert_eq!(isolated.unresolved, vec![GramSpan { first: 60, last: 62 }]);
    }

    #[test]
    fn the_rosser_failure_pair_verifies() {
        let z = fake(|t| patched(t, 60, 4.0, &FOUR_SECOND));
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            let (verdict, _) = go(&z, 100.0, &shallow(), policy);
            assert!(matches!(verdict, Verdict::Verified { count: 29, .. }), "{verdict:?}");
        }
    }

    // ---- the pool ----

    #[test]
    fn a_pool_that_cannot_be_built_falls_back_with_the_notice() {
        let z = fake(wave);
        let (forced, err) = go(&z, 100.0, &cfg(), PoolPolicy::FailBuild);
        assert!(err.starts_with("Parallel mode unavailable ("), "{err:?}");
        assert!(err.contains("forced by PoolPolicy::FailBuild"), "{err:?}");
        assert!(err.ends_with("); falling back to serial.\n"), "{err:?}");
        assert_eq!(err.lines().count(), 1);
        let (serial, quiet) = go(&z, 100.0, &cfg(), PoolPolicy::Serial);
        assert_eq!(quiet, "");
        assert_eq!(forced, serial);
    }

    struct Broken;

    impl Write for Broken {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::other("stderr is closed"))
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn a_notice_that_cannot_be_written_is_reported() {
        let verdict = verify(100.0, &fake(wave), &cfg(), PoolPolicy::FailBuild, &mut Broken);
        assert_eq!(verdict, Verdict::WriteFailed { error: "stderr is closed".to_string() });
    }

    #[test]
    fn the_runner_uses_its_own_pool_in_order_and_catches_a_panic() {
        let runner = Runner::new(PoolPolicy::Threads(3), &mut Vec::new()).unwrap();
        let sizes = runner.map(8, |_| rayon::current_num_threads()).unwrap();
        assert_eq!(sizes, vec![3; 8]);
        assert_eq!(
            runner.map(100, |i| i * 2).unwrap(),
            (0..100).map(|i| i * 2).collect::<Vec<_>>()
        );
        assert_eq!(runner.map(0, |i| i).unwrap(), Vec::<usize>::new());
        let panicked = runner.map(4, |i| assert!(i != 2, "boom"));
        assert_eq!(panicked, Err(Fault::WorkerPanicked));
        let serial = Runner::new(PoolPolicy::Serial, &mut Vec::new()).unwrap();
        assert_eq!(serial.map(3, |i| i + 1).unwrap(), vec![1, 2, 3]);
        assert_eq!(serial.map(2, |i| assert!(i != 1, "boom")), Err(Fault::WorkerPanicked));
    }

    #[test]
    fn the_default_policy_is_a_private_parallel_pool() {
        assert_eq!(PoolPolicy::default(), PoolPolicy::Parallel);
        let runner = Runner::new(PoolPolicy::Parallel, &mut Vec::new()).unwrap();
        assert!(runner.pool.is_some());
        assert!(Runner::new(PoolPolicy::Serial, &mut Vec::new()).unwrap().pool.is_none());
    }
}
