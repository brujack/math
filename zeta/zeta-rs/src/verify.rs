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
use std::sync::atomic::{AtomicU32, Ordering};

use rayon::prelude::*;
use rayon::{ThreadPool, ThreadPoolBuildError, ThreadPoolBuilder};

use crate::boundary::{Boundary, ZeroFreeBracket, certify_boundary, is_good};
use crate::config::VerifyConfig;
use crate::interval::Interval;
use crate::isolate::{
    BlockPoints, GramBlock, IsolateError, Point, PointsFault, Straddle, alternations,
    isolate_block, merge_points, resolve_straddle, sign_changes,
};
use crate::turing::{TuringBound, TuringFailure, choose_m};
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
    /// L = M + 1, but a block stayed short of Rosser's count after the neighbour
    /// search; its span is in `blocks` (spec: unresolved blocks are reported, exit 3).
    UnresolvedBlocks,
}

impl std::fmt::Display for NotVerifiedReason {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Turing(_) => f.write_str("Turing bound not established"),
            Self::NoLeftBoundary => f.write_str("g_-1 has no certified bracket"),
            Self::NoBlocks => f.write_str("no Gram block covers the range"),
            Self::ShortCount { found, needed } => {
                write!(f, "{found} of {needed} zeros isolated")
            }
            Self::ZeroSideUncertain => {
                f.write_str("the zero nearest the height could not be placed on one side of it")
            }
            Self::UnresolvedBlocks => f.write_str(
                "every zero isolated, but some Gram blocks stayed short of Rosser's count",
            ),
        }
    }
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
    Points(PointsFault),
    /// L > M + 1, which a correct implementation cannot produce.
    TooManySignChanges { found: usize, bound: usize },
    /// A panic in a worker, in choosing M or in the straddle step (spec text: "worker panicked").
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

/// What a verified run reports beside the count (the spec's output block).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RunStats {
    /// The Gram index M Turing's bound holds at.
    pub m: i64,
    /// g_M's certified zero-free bracket `[b_M, c_M]`, which encloses g_M.
    pub g_m: (f64, f64),
    /// Gram blocks processed.
    pub gram_blocks: usize,
    /// Blocks short of Rosser's count that the neighbour search then resolved.
    pub rosser_exceptions: usize,
    /// The highest precision (bits) any Z evaluation of the run used.
    pub max_precision: u32,
    /// Threads the run used: 1 when serial, including after a pool build failure.
    pub threads: usize,
}

/// A `ZSource` that records the highest precision at which the inner source
/// produced an enclosure, so the report can state the precision actually used.
struct PrecisionProbe<'a, Z> {
    inner: &'a Z,
    max: AtomicU32,
}

impl<Z> PrecisionProbe<'_, Z> {
    /// The highest precision at which a call so far produced an enclosure.
    fn highest(&self) -> u32 {
        self.max.load(Ordering::Relaxed)
    }
}

impl<Z: ZSource> ZSource for PrecisionProbe<'_, Z> {
    fn z(&self, t: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
        let result = self.inner.z(t, prec)?;
        if result.is_some() {
            self.max.fetch_max(prec, Ordering::Relaxed);
        }
        Ok(result)
    }

    fn z_over(&self, lo: f64, hi: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
        let result = self.inner.z_over(lo, hi, prec)?;
        if result.is_some() {
            self.max.fetch_max(prec, Ordering::Relaxed);
        }
        Ok(result)
    }
}

/// The outcome of `verify`.
#[derive(Debug, Clone, PartialEq)]
pub enum Verdict {
    /// Every zero with 0 < Im <= T is on the line and simple. `intervals[k]` is
    /// the certified sign-change interval holding the (k+1)-th zero; `count == intervals.len()`.
    Verified { count: usize, intervals: Vec<(f64, f64)>, stats: RunStats },
    /// Nothing is claimed; `blocks` names the Gram blocks left unresolved.
    NotVerified { reason: NotVerifiedReason, blocks: Vec<GramSpan> },
    /// An implementation fault.
    Fault { reason: Fault },
    /// The fallback notice could not be written to the caller's stderr (exit 4).
    WriteFailed { error: String },
}

/// How `verify` runs its blocks.
// The hidden `FailBuild` is a test hook, not a marker for future variants, so the
// manual-non-exhaustive heuristic does not apply.
#[allow(clippy::manual_non_exhaustive)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum PoolPolicy {
    /// A private pool with rayon's default thread count.
    #[default]
    Parallel,
    /// A private pool with this many threads; `Threads(0)` means no workers, so
    /// it runs serially like `Serial` (not rayon's "0 means default").
    Threads(usize),
    /// No pool: every block runs on the calling thread.
    Serial,
    /// A pool whose thread spawn fails, so the build error and fallback are testable.
    /// Public but hidden: `main.rs`'s test-only `run_with` is a separate crate and
    /// cannot see a `#[cfg(test)]` variant of this library.
    #[doc(hidden)]
    FailBuild,
}

/// The private pool, or `None` for serial. The global pool is never used (R11):
/// every parallel step runs inside `ThreadPool::install` on this pool.
pub(crate) struct Runner {
    pool: Option<ThreadPool>,
}

fn build_pool(policy: PoolPolicy) -> Result<Option<ThreadPool>, ThreadPoolBuildError> {
    match policy {
        PoolPolicy::Serial | PoolPolicy::Threads(0) => Ok(None),
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
    pub(crate) fn new<E: Write>(policy: PoolPolicy, stderr: &mut E) -> io::Result<Runner> {
        match build_pool(policy) {
            Ok(pool) => Ok(Runner { pool }),
            Err(error) => {
                writeln!(stderr, "Parallel mode unavailable ({error}); falling back to serial.")?;
                Ok(Runner { pool: None })
            }
        }
    }

    /// Threads the run uses: the pool's, or 1 when serial.
    fn threads(&self) -> usize {
        self.pool.as_ref().map_or(1, ThreadPool::current_num_threads)
    }

    /// Runs `f`, turning a panic into a fault (no partial verdict survives it).
    fn guard<R>(f: impl FnOnce() -> R) -> Result<R, Fault> {
        catch_unwind(AssertUnwindSafe(f)).map_err(|_| Fault::WorkerPanicked)
    }

    /// `f(0..len)` in index order, on the pool when there is one. The first `Err`
    /// stops the remaining work (which `Err` wins among several in parallel is not
    /// defined; any fault is a fault), and a panic is `Fault::WorkerPanicked`.
    pub(crate) fn try_map<R: Send>(
        &self,
        len: usize,
        f: impl Fn(usize) -> Result<R, Fault> + Sync + Send,
    ) -> Result<Vec<R>, Fault> {
        Runner::guard(|| match &self.pool {
            Some(pool) => {
                pool.install(|| (0..len).into_par_iter().map(&f).collect::<Result<Vec<R>, Fault>>())
            }
            None => (0..len).map(&f).collect::<Result<Vec<R>, Fault>>(),
        })
        .and_then(|collected| collected)
    }
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

/// The merged points whose height lies in `[lo, hi]` (R4: L counts only [b_-1, b_M]).
fn points_in_range(points: Vec<Point>, lo: f64, hi: f64) -> Result<Vec<Point>, PointsFault> {
    let mut merged = merge_points(points)?;
    merged.retain(|p| lo <= p.t && p.t <= hi);
    Ok(merged)
}

/// Every point found, and the blocks still short of Rosser's count after the neighbour search.
#[derive(Debug, Clone, PartialEq)]
struct Isolated {
    points: Vec<Point>,
    unresolved: Vec<GramSpan>,
    /// Blocks short of Rosser's count that the neighbour search resolved.
    exceptions: usize,
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

/// Isolates every block, then re-searches each unresolved block with its
/// neighbours. Consumes the plan and the per-block results so the copies do not
/// pile up at N = 7.
fn isolate_all<Z: ZSource + Sync>(
    planned: Vec<PlannedBlock>,
    z: &Z,
    cfg: &VerifyConfig,
    runner: &Runner,
) -> Result<Isolated, Fault> {
    let first_pass = runner.try_map(planned.len(), |i| {
        isolate_block(&planned[i].block, z, cfg).map_err(Fault::Isolate)
    })?;
    let mut results = Vec::with_capacity(planned.len());
    for (block, mut found) in planned.iter().zip(first_pass) {
        found.points.extend(block.between.iter().copied());
        results.push(found);
    }
    let short: Vec<usize> = (0..planned.len()).filter(|&i| !results[i].resolved).collect();
    let searched =
        runner.try_map(short.len(), |k| search_neighbours(short[k], &planned, &results, z, cfg))?;
    let unresolved: Vec<GramSpan> = short
        .iter()
        .zip(&searched)
        .filter(|(_, (_, resolved))| !resolved)
        .map(|(&i, _)| planned[i].span)
        .collect();
    let exceptions = short.len() - unresolved.len();
    drop(planned);
    let mut points = Vec::new();
    for found in results {
        points.extend(found.points);
    }
    for (fresh, _) in searched {
        points.extend(fresh);
    }
    Ok(Isolated { points, unresolved, exceptions })
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
    let certified =
        runner.try_map(count, |i| certify_boundary(i as i64 - 1, z, cfg).map_err(Fault::Z))?;
    let mut usable = Vec::with_capacity(count + 1);
    for (i, boundary) in certified.into_iter().enumerate() {
        if let Some(boundary) = boundary {
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
    points: &[Point],
    bracket: &ZeroFreeBracket,
    z: &Z,
    cfg: &VerifyConfig,
) -> Result<Option<Vec<(f64, f64)>>, Fault> {
    let mut intervals = Vec::new();
    for (a, b) in sign_changes(points) {
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
    probe: &PrecisionProbe<'_, Z>,
    cfg: &VerifyConfig,
    runner: &Runner,
) -> Result<Verdict, Fault> {
    let z = probe;
    let usable = certify_gram_points(bound.m, bound.boundary, z, cfg, runner)?;
    let (first_n, left) = usable[0];
    if first_n != -1 {
        return Ok(not_verified(NotVerifiedReason::NoLeftBoundary, Vec::new()));
    }
    let left_t = left.point().t;
    let planned = plan_blocks(&usable);
    let gram_blocks = planned.len();
    drop(usable);
    if planned.is_empty() {
        return Ok(not_verified(NotVerifiedReason::NoBlocks, Vec::new()));
    }
    let isolated = isolate_all(planned, z, cfg, runner)?;
    let points = points_in_range(isolated.points, left_t, bound.boundary.point().t)
        .map_err(Fault::Points)?;
    let found = sign_changes(&points).count();
    let needed = (bound.m + 1) as usize;
    if found > needed {
        return Err(Fault::TooManySignChanges { found, bound: needed });
    }
    if found < needed {
        let reason = NotVerifiedReason::ShortCount { found, needed };
        return Ok(not_verified(reason, isolated.unresolved));
    }
    if !isolated.unresolved.is_empty() {
        return Ok(not_verified(NotVerifiedReason::UnresolvedBlocks, isolated.unresolved));
    }
    // The straddle step calls Z on this thread, outside the pool, so it needs its own guard.
    let bracket = bound.boundary.bracket();
    let Some(intervals) = Runner::guard(|| intervals_up_to(t, &points, &bracket, z, cfg))?? else {
        return Ok(not_verified(NotVerifiedReason::ZeroSideUncertain, Vec::new()));
    };
    let stats = RunStats {
        m: bound.m,
        g_m: (bracket.lo(), bracket.hi()),
        gram_blocks,
        rosser_exceptions: isolated.exceptions,
        max_precision: probe.highest(),
        threads: runner.threads(),
    };
    Ok(Verdict::Verified { count: intervals.len(), intervals, stats })
}

fn run<Z: ZSource + Sync>(
    t: f64,
    z: &Z,
    cfg: &VerifyConfig,
    runner: &Runner,
) -> Result<Verdict, Fault> {
    let probe = PrecisionProbe { inner: z, max: AtomicU32::new(0) };
    let bound = match Runner::guard(|| choose_m(t, &probe, cfg))? {
        Ok(bound) => bound,
        Err(failure) if failure.is_fault() => return Err(Fault::Turing(failure)),
        Err(failure) => return Ok(not_verified(NotVerifiedReason::Turing(failure), Vec::new())),
    };
    verify_with_bound(t, &bound, &probe, cfg, runner)
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
    run(t, z, cfg, &runner).unwrap_or_else(|reason| Verdict::Fault { reason })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::interval::{Interval, Sign};
    use crate::theta::gram_bracket;
    use crate::turing::choose_m;
    use rug::Float;
    use std::f64::consts::PI;
    use std::sync::atomic::{AtomicUsize, Ordering};

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
        over_calls: AtomicUsize,
    }

    fn fake<F: Fn(f64) -> f64 + Sync>(f: F) -> Fake<F> {
        let none = (1.0, 0.0);
        Fake {
            f,
            refuse_below: f64::NEG_INFINITY,
            blind: none,
            z_fault: none,
            over_fault: none,
            over_calls: AtomicUsize::new(0),
        }
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
            self.over_calls.fetch_add(1, Ordering::SeqCst);
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
        let Verdict::Verified { count, intervals, .. } = &serial else {
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
            assert_eq!(err, "", "{policy:?}");
            let Verdict::Verified { count: c, intervals: i, .. } = &other else {
                panic!("{other:?}");
            };
            assert_eq!((c, i), (count, intervals), "{policy:?}");
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
        assert_eq!(reason, NotVerifiedReason::Turing(TuringFailure::Exhausted { tried: 11 }));
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
        let probe = PrecisionProbe { inner: &z, max: AtomicU32::new(0) };
        let verdict = verify_with_bound(5.0, &bound, &probe, &cfg(), &runner).unwrap();
        assert_eq!(
            verdict,
            Verdict::NotVerified { reason: NotVerifiedReason::NoBlocks, blocks: vec![] }
        );
    }

    // ---- exit 6 ----

    fn fault(verdict: Verdict) -> Fault {
        match verdict {
            Verdict::Fault { reason } => reason,
            other => panic!("expected Fault, got {other:?}"),
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
    fn a_panic_in_the_straddle_step_is_a_fault_not_an_unwound_panic() {
        // T sits inside one sign-change interval; Z is evaluated at T only by the straddle rule.
        let t = wave_zero(10) + 0.01;
        let z = fake(move |x| {
            assert!(x != t, "boom");
            wave(x)
        });
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            assert_eq!(fault(go(&z, t, &cfg(), policy).0), Fault::WorkerPanicked);
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
        assert!(Fault::Points(PointsFault::SignConflict).to_string().contains("two"));
        let turing = Fault::Turing(TuringFailure::BelowRange);
        assert!(turing.to_string().starts_with("Turing's method: "));
        let isolate = Fault::Isolate(IsolateError::BadInterval);
        assert!(isolate.to_string().starts_with("isolation refused its input: "));
    }

    // ---- the one-pass count ----

    /// The sign changes among the merged points in [lo, hi], as `verify` counts them.
    fn counted(points: Vec<Point>, lo: f64, hi: f64) -> Result<Vec<(Point, Point)>, PointsFault> {
        let inside = points_in_range(points, lo, hi)?;
        Ok(sign_changes(&inside).collect())
    }

    #[test]
    fn a_sign_conflict_or_a_nan_height_is_a_fault() {
        let conflict = vec![pt(1.0, pos()), pt(1.0, neg())];
        assert_eq!(counted(conflict, 0.0, 9.0), Err(PointsFault::SignConflict));
        let nan = vec![pt(1.0, pos()), pt(f64::NAN, neg())];
        assert_eq!(counted(nan, 0.0, 9.0), Err(PointsFault::NanHeight));
        // A NaN is a fault even outside the range.
        let far = vec![pt(1.0, pos()), pt(f64::NAN, neg())];
        assert_eq!(counted(far, 5.0, 9.0), Err(PointsFault::NanHeight));
    }

    #[test]
    fn a_duplicate_identical_point_counts_once() {
        let points = vec![pt(2.0, neg()), pt(1.0, pos()), pt(2.0, neg()), pt(1.0, pos())];
        let changes = counted(points, 0.0, 9.0).unwrap();
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
        let at = |lo: f64, hi: f64| counted(points.clone(), lo, hi).unwrap().len();
        assert_eq!(at(2.0, 5.0), 3);
        assert_eq!(at(2.5, 5.0), 2);
        assert_eq!(at(2.0, 4.5), 2);
        assert_eq!(at(0.0, 9.0), 5);
        assert_eq!(at(3.5, 3.9), 0);
    }

    #[test]
    fn equal_signs_between_points_are_not_a_change() {
        let points = vec![pt(1.0, pos()), pt(2.0, pos()), pt(3.0, neg()), pt(4.0, neg())];
        let changes = counted(points, 0.0, 9.0).unwrap();
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
        isolate_all(planned, &fake(&f), &shallow(), &runner).unwrap()
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

    /// No sign change over g_60..g_62 and two extra over g_70..g_72, so L is M + 1
    /// although the first block is short.
    fn short_block_offset_by_an_over_block(t: f64) -> f64 {
        if (0.0..=2.0).contains(&u_of(t, 60)) { 1.0 } else { patched(t, 70, 2.0, &FOUR_FIRST) }
    }

    #[test]
    fn a_block_still_short_after_merging_is_named() {
        let isolated = isolate_range(short_block_offset_by_an_over_block, 58, 74);
        assert_eq!(isolated.unresolved, vec![GramSpan { first: 60, last: 62 }]);
        assert_eq!(isolated.exceptions, 0, "an unresolved block is not an exception");
    }

    #[test]
    fn an_unresolved_block_is_not_verified_even_when_l_is_m_plus_1() {
        let z = fake(short_block_offset_by_an_over_block);
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            let (verdict, _) = go(&z, 100.0, &shallow(), policy);
            let (reason, blocks) = not_verified(verdict);
            assert_eq!(reason, NotVerifiedReason::UnresolvedBlocks, "{policy:?}");
            assert_eq!(blocks, vec![GramSpan { first: 60, last: 62 }]);
        }
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

    // ---- what the neighbour search contributes ----

    /// The union of block `i` with its neighbours, as `search_neighbours` builds it.
    fn union_of(planned: &[PlannedBlock], i: usize) -> GramBlock {
        let (a, b) = (i - 1, i + 1);
        GramBlock {
            lo: planned[a].block.lo,
            hi: planned[b].block.hi,
            expected: planned[a..=b].iter().map(|p| p.block.expected).sum(),
        }
    }

    fn index_of(planned: &[PlannedBlock], first: i64) -> usize {
        planned.iter().position(|p| p.span.first == first).unwrap()
    }

    #[test]
    fn points_only_the_union_search_finds_are_kept() {
        // g_62..g_64 resolves on its first window at depth 2; its second window sits
        // where only a finer grid looks, which only the union's fresh points supply.
        let f = |t: f64| patched(t, 60, 4.0, &[(2.3, 2.7), (3.2, 3.3)]);
        let planned = plan_blocks(&usable_range(f, 58, 66));
        let own = isolate_block(&planned[index_of(&planned, 62)].block, &fake(f), &shallow());
        let own = own.unwrap();
        assert!(own.resolved && alternations(&own.points) == 2);
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            let (verdict, _) = go(&fake(f), 100.0, &shallow(), policy);
            assert!(matches!(verdict, Verdict::Verified { count: 29, .. }), "{verdict:?}");
        }
    }

    #[test]
    fn the_union_is_judged_by_the_points_already_known_inside_it() {
        // The over-full neighbour's changes sit in 2e-6 windows at its own level-2
        // grid points, which the union's coarser grid misses: only the known points
        // make the union meet its expected count.
        let (lo, hi) = (bracket_of(62).0, bracket_of(64).0);
        let mid = lo + (hi - lo) / 2.0;
        let (q1, q3) = (lo + (mid - lo) / 2.0, mid + (hi - mid) / 2.0);
        let f = move |t: f64| {
            if (t - q1).abs() < 1e-6 || (t - q3).abs() < 1e-6 {
                -1.0
            } else {
                patched(t, 60, 4.0, &[])
            }
        };
        let planned = plan_blocks(&usable_range(f, 58, 66));
        let i = index_of(&planned, 60);
        let union = union_of(&planned, i);
        assert_eq!(union.expected, 5);
        assert!(!isolate_block(&union, &fake(f), &shallow()).unwrap().resolved);
        let isolated = isolate_range(f, 58, 66);
        assert!(isolated.unresolved.is_empty(), "{:?}", isolated.unresolved);
        let (verdict, _) = go(&fake(f), 100.0, &shallow(), PoolPolicy::Serial);
        assert!(matches!(verdict, Verdict::Verified { count: 29, .. }), "{verdict:?}");
    }

    /// g_60..g_64 cannot be sampled (its interior is uncertain), so its only
    /// negative point is the bad Gram point g_62; g_64..g_66 holds the surplus.
    fn dead_block_with_a_bad_point(t: f64) -> f64 {
        let u = u_of(t, 60);
        if (0.0..=4.0).contains(&u) {
            if (1.9..=2.1).contains(&u) { -1.0 } else { 1.0 }
        } else {
            patched(t, 64, 2.0, &FOUR_FIRST)
        }
    }

    #[test]
    fn a_bad_gram_point_inside_a_block_supplies_its_alternations() {
        let mut z = fake(dead_block_with_a_bad_point);
        z.blind = (bracket_of(60).1, bracket_of(64).0);
        let usable = usable_range(dead_block_with_a_bad_point, 58, 66);
        let planned = plan_blocks(&usable);
        let block = &planned[index_of(&planned, 60)];
        assert_eq!(block.span, GramSpan { first: 60, last: 64 });
        let signs: Vec<Sign> = block.between.iter().map(|p| p.sign).collect();
        assert_eq!(signs, vec![pos(), neg(), pos()]);
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            let (verdict, _) = go(&z, 100.0, &shallow(), policy);
            assert!(matches!(verdict, Verdict::Verified { count: 29, .. }), "{verdict:?}");
        }
    }

    #[test]
    fn a_fault_stops_certification_early() {
        let full = fake(wave);
        assert!(matches!(go(&full, 100.0, &cfg(), PoolPolicy::Serial).0, Verdict::Verified { .. }));
        let n0 = bracket_of(0).0;
        let mut early = fake(wave);
        early.over_fault = (n0 - 1e-3, n0 + 1e-3);
        let reason = fault(go(&early, 100.0, &cfg(), PoolPolicy::Serial).0);
        assert_eq!(reason, Fault::Z(ZFault::NanHeight));
        let (all, some) =
            (full.over_calls.load(Ordering::SeqCst), early.over_calls.load(Ordering::SeqCst));
        assert!(some + 250 < all, "{some} calls with the fault, {all} without");
    }

    #[test]
    fn t_below_the_first_zero_verifies_zero_zeros() {
        let (verdict, _) = go(&fake(wave), 10.0, &cfg(), PoolPolicy::Serial);
        let Verdict::Verified { count, intervals, .. } = verdict else { panic!("{verdict:?}") };
        assert_eq!((count, intervals), (0, vec![]));
    }

    // ---- the report: reason text and stats ----

    /// Refuses every precision below `min`, so the ladder must climb to it.
    struct NeedsPrecision<Z> {
        inner: Z,
        min: u32,
    }

    impl<Z: ZSource> ZSource for NeedsPrecision<Z> {
        fn z(&self, t: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
            if prec < self.min { Ok(None) } else { self.inner.z(t, prec) }
        }

        fn z_over(&self, lo: f64, hi: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
            if prec < self.min { Ok(None) } else { self.inner.z_over(lo, hi, prec) }
        }
    }

    fn stats_of(verdict: Verdict) -> RunStats {
        let Verdict::Verified { stats, .. } = verdict else { panic!("{verdict:?}") };
        stats
    }

    #[test]
    fn reasons_read_as_the_specs_wording() {
        let cases = [
            (
                NotVerifiedReason::Turing(TuringFailure::Exhausted { tried: 11 }),
                "Turing bound not established",
            ),
            (NotVerifiedReason::NoLeftBoundary, "g_-1 has no certified bracket"),
            (NotVerifiedReason::NoBlocks, "no Gram block covers the range"),
            (
                NotVerifiedReason::ShortCount { found: 647, needed: 649 },
                "647 of 649 zeros isolated",
            ),
            (
                NotVerifiedReason::ZeroSideUncertain,
                "the zero nearest the height could not be placed on one side of it",
            ),
            (
                NotVerifiedReason::UnresolvedBlocks,
                "every zero isolated, but some Gram blocks stayed short of Rosser's count",
            ),
        ];
        for (reason, text) in cases {
            assert_eq!(reason.to_string(), text);
        }
    }

    #[test]
    fn stats_report_m_the_bracket_blocks_and_threads() {
        let z = fake(wave);
        for (policy, threads) in
            [(PoolPolicy::Serial, 1), (PoolPolicy::Threads(3), 3), (PoolPolicy::Threads(0), 1)]
        {
            let stats = stats_of(go(&z, 100.0, &cfg(), policy).0);
            let m = m_at(100.0);
            assert_eq!(stats.m, m);
            assert_eq!(stats.g_m, bracket_of(m));
            assert!(stats.gram_blocks >= 1, "{stats:?}");
            assert_eq!(stats.rosser_exceptions, 0);
            assert_eq!(stats.max_precision, 64);
            assert_eq!(stats.threads, threads, "{policy:?}");
        }
    }

    #[test]
    fn a_pool_that_cannot_be_built_reports_one_thread() {
        let stats = stats_of(go(&fake(wave), 100.0, &cfg(), PoolPolicy::FailBuild).0);
        assert_eq!(stats.threads, 1);
    }

    #[test]
    fn stats_count_blocks_as_planned() {
        let m = m_at(100.0);
        let stats = stats_of(go(&fake(wave), 100.0, &cfg(), PoolPolicy::Serial).0);
        // Every Gram point is good, so g_-1 .. g_M bound M + 1 blocks of one interval.
        assert_eq!(stats.gram_blocks as i64, m + 1);
    }

    #[test]
    fn a_resolved_rosser_failure_counts_as_one_exception() {
        let z = fake(|t| patched(t, 60, 4.0, &FOUR_SECOND));
        let stats = stats_of(go(&z, 100.0, &shallow(), PoolPolicy::Serial).0);
        assert_eq!(stats.rosser_exceptions, 1);
        assert_eq!(isolate_range(|t| patched(t, 60, 4.0, &FOUR_SECOND), 60, 64).exceptions, 1);
        assert_eq!(isolate_range(wave, 60, 64).exceptions, 0);
    }

    #[test]
    fn max_precision_is_the_rung_the_ladder_had_to_reach() {
        for min in [64, 128, 256, 512] {
            let z = NeedsPrecision { inner: fake(wave), min };
            let stats = stats_of(go(&z, 100.0, &cfg(), PoolPolicy::Serial).0);
            assert_eq!(stats.max_precision, min);
        }
    }

    #[test]
    fn the_probe_records_only_precisions_that_produced_an_enclosure() {
        let source = NeedsPrecision { inner: fake(wave), min: 128 };
        let probe = PrecisionProbe { inner: &source, max: AtomicU32::new(0) };
        assert!(probe.z(20.0, 64).unwrap().is_none());
        assert_eq!(probe.max.load(Ordering::Relaxed), 0);
        assert!(probe.z(20.0, 128).unwrap().is_some());
        assert!(probe.z_over(20.0, 21.0, 256).unwrap().is_some());
        assert!(probe.z_over(20.0, 21.0, 64).unwrap().is_none());
        assert!(probe.z(20.0, 128).unwrap().is_some());
        assert_eq!(probe.max.load(Ordering::Relaxed), 256, "a later lower rung never lowers it");
    }

    #[test]
    fn the_probe_passes_a_fault_through() {
        let mut inner = fake(wave);
        inner.z_fault = (10.0, 30.0);
        inner.over_fault = (10.0, 30.0);
        let probe = PrecisionProbe { inner: &inner, max: AtomicU32::new(0) };
        assert_eq!(probe.z(20.0, 64).unwrap_err(), ZFault::NanHeight);
        assert_eq!(probe.z_over(20.0, 21.0, 64).unwrap_err(), ZFault::NanHeight);
        assert_eq!(probe.max.load(Ordering::Relaxed), 0);
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
        let sizes = runner.try_map(8, |_| Ok(rayon::current_num_threads())).unwrap();
        assert_eq!(sizes, vec![3; 8]);
        let doubled = runner.try_map(100, |i| Ok(i * 2)).unwrap();
        assert_eq!(doubled, (0..100).map(|i| i * 2).collect::<Vec<_>>());
        assert_eq!(runner.try_map(0, Ok).unwrap(), Vec::<usize>::new());
        let panicked = runner.try_map(4, |i| {
            assert!(i != 2, "boom");
            Ok(i)
        });
        assert_eq!(panicked, Err(Fault::WorkerPanicked));
        let serial = Runner::new(PoolPolicy::Serial, &mut Vec::new()).unwrap();
        assert_eq!(serial.try_map(3, |i| Ok(i + 1)).unwrap(), vec![1, 2, 3]);
        let panicked = serial.try_map(2, |i| {
            assert!(i != 1, "boom");
            Ok(i)
        });
        assert_eq!(panicked, Err(Fault::WorkerPanicked));
    }

    #[test]
    fn the_first_error_stops_the_remaining_work_on_either_runner() {
        for policy in [PoolPolicy::Serial, PoolPolicy::Threads(2)] {
            let runner = Runner::new(policy, &mut Vec::new()).unwrap();
            let ran = AtomicUsize::new(0);
            let out = runner.try_map(100_000, |i| {
                ran.fetch_add(1, Ordering::SeqCst);
                if i == 3 { Err(Fault::WorkerPanicked) } else { Ok(i) }
            });
            assert_eq!(out, Err(Fault::WorkerPanicked), "{policy:?}");
            assert!(
                ran.load(Ordering::SeqCst) < 50_000,
                "{policy:?}: {}",
                ran.load(Ordering::SeqCst)
            );
        }
    }

    #[test]
    fn zero_threads_means_no_workers_and_runs_serially() {
        let runner = Runner::new(PoolPolicy::Threads(0), &mut Vec::new()).unwrap();
        assert!(runner.pool.is_none());
        assert!(Runner::new(PoolPolicy::Threads(1), &mut Vec::new()).unwrap().pool.is_some());
    }

    #[test]
    fn the_default_policy_is_a_private_parallel_pool() {
        assert_eq!(PoolPolicy::default(), PoolPolicy::Parallel);
        let runner = Runner::new(PoolPolicy::Parallel, &mut Vec::new()).unwrap();
        assert!(runner.pool.is_some());
        assert!(Runner::new(PoolPolicy::Serial, &mut Vec::new()).unwrap().pool.is_none());
    }
}
