use std::cmp::Ordering;
use std::fmt;

/// Why a computation produced no answer; mirrors Python's `BadInput` (exit 2)
/// and `NoSolution` (exit 1).
#[derive(Debug, PartialEq)]
pub enum DescartesError {
    /// The input is malformed.
    BadInput(String),
    /// The input is well formed but has no answer.
    NoSolution(String),
}

impl DescartesError {
    /// The CLI exit code: 2 for malformed input, 1 for no answer.
    pub fn exit_code(&self) -> i32 {
        match self {
            Self::BadInput(_) => 2,
            Self::NoSolution(_) => 1,
        }
    }
}

impl fmt::Display for DescartesError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::BadInput(msg) | Self::NoSolution(msg) => f.write_str(msg),
        }
    }
}

/// Both curvatures tangent to three mutually tangent circles of curvature
/// `k1`, `k2`, `k3`: `k1+k2+k3 ± 2√(k1k2+k2k3+k3k1)`.
///
/// A radicand below `-1e-12 × (|k1k2|+|k2k3|+|k3k1|)` is `NoSolution`;
/// anything between that and zero is rounding noise and clamps to zero (R23).
pub fn descartes_fourth(k1: f64, k2: f64, k3: f64) -> Result<(f64, f64), DescartesError> {
    let s = k1 * k2 + k2 * k3 + k3 * k1;
    if s < -1e-12 * ((k1 * k2).abs() + (k2 * k3).abs() + (k3 * k1).abs()) {
        let call = format!("descartes_fourth({k1}, {k2}, {k3})");
        let detail = format!("k1k2+k2k3+k3k1 = {s} is negative");
        return Err(DescartesError::NoSolution(format!(
            "{call}: no circle is tangent to all three, {detail}"
        )));
    }
    let root = 2.0 * s.max(0.0).sqrt();
    let total = k1 + k2 + k3;
    Ok((total + root, total - root))
}

/// Largest |curvature| `validate_root` accepts (spec R28). Reduction takes one
/// step per reflection and `(-1, 2, n²+2, (n+1)²+2)` needs `n` of them, so the
/// cap bounds reduction at about 10^4 steps.
pub const ROOT_MAX: i64 = 100_000_000;
/// Largest `n` `pack` accepts (spec R22): K = 8, about 1.1e10 circles.
pub const N_MAX: i64 = 100_000_000;

/// `"(a, b, c, d)"`, the way Python prints a root tuple.
fn show(q: [i64; 4]) -> String {
    format!("({}, {}, {}, {})", q[0], q[1], q[2], q[3])
}

fn over_ceiling(q: [i64; 4]) -> Option<i64> {
    q.into_iter().find(|&k| !(-ROOT_MAX..=ROOT_MAX).contains(&k))
}

/// `((Σk)², 2Σk²)`; equal exactly when `q` satisfies Descartes' relation.
///
/// Callers have checked every `|k| <= ROOT_MAX = 10^8`, so `|Σk| <= 4·10^8` and
/// `(Σk)² <= 1.6·10^17`; `2Σk² <= 2·4·10^16 = 8·10^16`. Both are far below
/// `i64::MAX` (about 9.2·10^18), so neither expression can overflow.
fn relation_sides(q: [i64; 4]) -> (i64, i64) {
    let total: i64 = q.iter().sum();
    (total * total, 2 * q.iter().map(|k| k * k).sum::<i64>())
}

fn negatives(q: [i64; 4]) -> usize {
    q.iter().filter(|&&k| k < 0).count()
}

/// Check a root quadruple and reduce it to the packing's canonical root,
/// returned ascending. Checks run in order: curvature ceiling (`BadInput`),
/// Descartes relation, exactly one negative (both `NoSolution`).
pub fn validate_root(q: [i64; 4]) -> Result<[i64; 4], DescartesError> {
    let shown = show(q);
    if let Some(k) = over_ceiling(q) {
        return Err(DescartesError::BadInput(format!(
            "root {shown}: curvatures must be at most 10^8 in absolute value, got {k}"
        )));
    }
    let (square, doubled) = relation_sides(q);
    if square != doubled {
        return Err(DescartesError::NoSolution(format!(
            "root {shown} is not a Descartes quadruple: (Σk)²={square}, 2Σk²={doubled}"
        )));
    }
    if negatives(q) != 1 {
        return Err(DescartesError::NoSolution(format!(
            "root {shown} needs exactly one negative curvature (the bounding circle)"
        )));
    }
    let mut values = q;
    values.sort_unstable();
    loop {
        let reflected = 2 * (values[0] + values[1] + values[2]) - values[3];
        if reflected >= values[3] {
            return Ok(values);
        }
        values[3] = reflected;
        values.sort_unstable();
    }
}

/// `BadInput` unless `0 <= n <= max`; `op` and `arg` name the caller's function
/// and argument in the message.
fn check_n(n: i64, max: i64, op: &str, arg: &str) -> Result<(), DescartesError> {
    if n < 0 {
        return Err(DescartesError::BadInput(format!(
            "{op}({arg}={n}): {arg} must not be negative"
        )));
    }
    if n > max {
        return Err(DescartesError::BadInput(format!(
            "{op}({arg}={n}): {arg} must be at most {max}"
        )));
    }
    Ok(())
}

/// `BadInput` unless `root` is a sorted, reduced Descartes root within the cap;
/// `op` names the caller in the message.
fn check_reduced_root(root: [i64; 4], op: &str) -> Result<(), DescartesError> {
    if over_ceiling(root).is_some() {
        // Not summed: beyond the cap the relation could overflow i64.
        return Err(DescartesError::BadInput(format!(
            "{op}(root={}, ...): root is beyond the cap of at most 10^8 in absolute value",
            show(root)
        )));
    }
    let (square, doubled) = relation_sides(root);
    let problem = if root.windows(2).any(|w| w[0] > w[1]) {
        "not sorted ascending"
    } else if square != doubled {
        "not a Descartes quadruple"
    } else if negatives(root) != 1 {
        "needs exactly one negative curvature"
    } else if 2 * (root[0] + root[1] + root[2]) - root[3] < root[3] {
        "not reduced (use validate_root first)"
    } else {
        return Ok(());
    };
    Err(DescartesError::BadInput(format!("{op}(root={}, ...): root is {problem}", show(root))))
}

/// Set bit `k` of the bitmap: word `k / 64`, bit `k % 64`.
fn mark(bitmap: &mut [u64], k: i64) {
    bitmap[(k >> 6) as usize] |= 1u64 << (k & 63);
}

/// Count circles of curvature at most `n` in the packing of a reduced `root`
/// and mark their curvatures in a bitmap of `n / 64 + 1` words.
///
/// The bounding circle is never counted. Returns `Result` (the plan's bare
/// tuple has no path for the `n` ceiling or a bad root): `BadInput` when `n` is
/// negative or above `N_MAX`, or when `root` is not a sorted, reduced Descartes
/// root within the 10^8 cap.
pub fn pack(root: [i64; 4], n: i64) -> Result<(i64, Vec<u64>), DescartesError> {
    check_n(n, N_MAX, "pack", "n")?;
    check_reduced_root(root, "pack")?;
    Ok(walk(root, n, &mut || {}))
}

/// The DFS behind `pack`, with no precondition checks; `on_mark` runs once per
/// counted circle so a test can budget the work.
///
/// Termination does not rest on the root being valid: the root's four
/// reflections are seeded when at most `n`, and every later reflection is
/// pushed only when it strictly increases the curvature it replaces and stays
/// at most `n`, so every DFS path climbs a finite integer range. For a reduced
/// root the increase always holds, so the guard never prunes a valid circle.
/// **Do not remove this growth guard as dead code**: without it the walk is
/// unbounded and exhausts memory (spec R21). Reflecting the circle just
/// reflected gives back the smaller parent curvature, which the same guard
/// rejects, so no separate "skip the parent" test is needed.
fn walk(root: [i64; 4], n: i64, on_mark: &mut impl FnMut()) -> (i64, Vec<u64>) {
    let mut bitmap = vec![0u64; (n / 64 + 1) as usize];
    let mut count: i64 = 0;
    for &k in &root[1..] {
        if k <= n {
            count += 1;
            mark(&mut bitmap, k);
            on_mark();
        }
    }
    let mut stack: Vec<([i64; 4], usize)> = Vec::new();
    let total: i64 = root.iter().sum();
    for (i, &old) in root.iter().enumerate() {
        let k = 2 * (total - old) - old;
        if k <= n {
            let mut quad = root;
            quad[i] = k;
            stack.push((quad, i));
        }
    }
    while let Some((quad, j)) = stack.pop() {
        count += 1;
        mark(&mut bitmap, quad[j]);
        on_mark();
        let total: i64 = quad.iter().sum();
        for (i, &old) in quad.iter().enumerate() {
            let k = 2 * (total - old) - old;
            if old < k && k <= n {
                let mut child = quad;
                child[i] = k;
                stack.push((child, i));
            }
        }
    }
    (count, bitmap)
}

/// The curvatures marked in the bitmap, ascending.
pub fn distinct(bitmap: &[u64]) -> Vec<i64> {
    let mut found = Vec::new();
    for (w, &word) in bitmap.iter().enumerate() {
        for b in 0..64 {
            if word >> b & 1 == 1 {
                found.push((w * 64 + b) as i64);
            }
        }
    }
    found
}

/// A circle as `(curvature, x, y)`: radius `1/k`, centre `(x, y)`.
pub type Circle = (f64, f64, f64);

/// A complex number `(re, im)`. Hand-written arithmetic keeps the crate free of
/// a complex-number dependency (spec N4).
type Complex = (f64, f64);

/// Relative tolerance of every tangency and identity test (spec Component 2,
/// R24(a), R26). The functions that use it take it as a parameter so a test can
/// widen it and hit each bound exactly.
const TANGENT_TOL: f64 = 1e-9;

fn c_add(a: Complex, b: Complex) -> Complex {
    (a.0 + b.0, a.1 + b.1)
}

fn c_sub(a: Complex, b: Complex) -> Complex {
    (a.0 - b.0, a.1 - b.1)
}

fn c_mul(a: Complex, b: Complex) -> Complex {
    (a.0 * b.0 - a.1 * b.1, a.0 * b.1 + a.1 * b.0)
}

fn c_scale(a: Complex, s: f64) -> Complex {
    (a.0 * s, a.1 * s)
}

fn c_div(a: Complex, s: f64) -> Complex {
    (a.0 / s, a.1 / s)
}

/// The principal square root of `w`.
///
/// `t = sqrt((|w| + |re|) / 2)` is computed without cancellation, and the other
/// component is `im / 2t`; which of the two parts `t` becomes depends on the
/// sign of `re`, so neither subtraction `|w| - re` is ever formed. A real
/// negative input gives an exactly imaginary root, so circles on an axis keep
/// `y` or `x` exactly zero.
fn c_sqrt(w: Complex) -> Complex {
    let modulus = w.0.hypot(w.1);
    if modulus == 0.0 {
        return (0.0, 0.0);
    }
    let t = ((modulus + w.0.abs()) / 2.0).sqrt();
    let s = w.1 / (2.0 * t);
    if w.0.is_sign_negative() { (s.abs(), t.copysign(w.1)) } else { (t, s) }
}

/// `"(k, x, y)"` with Rust's shortest round-trip float form (Python's `repr`).
fn show_circle(c: Circle) -> String {
    format!("({}, {}, {})", c.0, c.1, c.2)
}

/// `"solve((k, x, y), ...)"`, naming the operation and its input in a message.
fn solve_call(circles: &[Circle]) -> String {
    let shown: Vec<String> = circles.iter().map(|&c| show_circle(c)).collect();
    format!("solve({})", shown.join(", "))
}

/// `(measured distance, expected distance, tolerance)` for two circles.
///
/// Radii are signed (`r = 1/k`), so a pair is tangent when the centre distance
/// equals `|r_a + r_b|`: the sum for two positive circles, the difference when
/// one is the bounding circle (R24(a)).
fn pair_gap(a: Circle, b: Circle, tol: f64) -> (f64, f64, f64) {
    let (r_a, r_b) = (1.0 / a.0, 1.0 / b.0);
    let measured = (a.1 - b.1).hypot(a.2 - b.2);
    (measured, (r_a + r_b).abs(), tol * (r_a.abs() + r_b.abs()))
}

fn is_tangent(a: Circle, b: Circle, tol: f64) -> bool {
    let (measured, expected, bound) = pair_gap(a, b, tol);
    (measured - expected).abs() <= bound
}

/// True for a non-integer whose shortest round-trip form has 1 to 6 decimals.
///
/// Rust's `Display` never uses an exponent, so `1e-5` prints `0.00001` and
/// counts 5; an integer-valued, infinite or NaN float prints without a point
/// (R24(b)).
fn has_short_decimal(v: f64) -> bool {
    v.to_string().split_once('.').is_some_and(|(_, decimals)| decimals.len() <= 6)
}

/// Why a circle cannot be an input (R26), or `None`.
fn input_problem((k, x, y): Circle) -> Option<&'static str> {
    if !(k.is_finite() && x.is_finite() && y.is_finite()) {
        Some("has a NaN or infinite value")
    } else if k == 0.0 {
        Some("has zero curvature")
    } else if !(1.0 / k).is_finite() {
        Some("has a curvature whose radius 1/k is not finite")
    } else {
        None
    }
}

/// `Ok` when the circles are mutually tangent: pairs 1-2, 1-3, 2-3, ... each
/// within `1e-9 x (|r_i| + |r_j|)` (R24(a)).
///
/// A non-finite value, a zero curvature or a non-finite radius is `BadInput`,
/// checked for every circle before any pair; the first failing pair is
/// `NoSolution`, with a hint when a centre coordinate looks rounded (R24(b)).
pub fn check_tangent(circles: &[Circle]) -> Result<(), DescartesError> {
    check_tangent_with(circles, TANGENT_TOL)
}

fn check_tangent_with(circles: &[Circle], tol: f64) -> Result<(), DescartesError> {
    for (number, &c) in circles.iter().enumerate() {
        if let Some(problem) = input_problem(c) {
            return Err(DescartesError::BadInput(format!(
                "{}: circle {} {problem} (curvature {}, centre ({}, {}))",
                solve_call(circles),
                number + 1,
                c.0,
                c.1,
                c.2
            )));
        }
    }
    for (i, &a) in circles.iter().enumerate() {
        for (j, &b) in circles.iter().enumerate().skip(i + 1) {
            let (measured, expected, bound) = pair_gap(a, b, tol);
            if (measured - expected).abs() <= bound {
                continue;
            }
            let mut message = format!(
                "{}: circles {} and {} are not tangent: measured distance {measured}, expected {expected}, tolerance {bound}",
                solve_call(circles),
                i + 1,
                j + 1
            );
            if circles.iter().any(|c| has_short_decimal(c.1) || has_short_decimal(c.2)) {
                message.push_str(
                    "; a coordinate has 6 or fewer decimal places, so it may be rounded: use full-precision values",
                );
            }
            return Err(DescartesError::NoSolution(message));
        }
    }
    Ok(())
}

/// True unless `a` and `b` differ in curvature or centre (R26): different means
/// curvatures more than `tol x |k_b|` apart or centres more than
/// `tol x |1/k_b|` apart, so the test holds at every scale.
fn same_circle(a: Circle, b: Circle, tol: f64) -> bool {
    let curvature_gap = (a.0 - b.0).abs();
    let centre_gap = (a.1 - b.1).hypot(a.2 - b.2);
    curvature_gap <= tol * b.0.abs() && centre_gap <= tol * (1.0 / b.0).abs()
}

/// Sort order of `solve`'s results: curvature, then y, then x. Floats compare
/// by value, so `-0.0` and `0.0` tie on y and fall through to x.
fn circle_order(a: &Circle, b: &Circle) -> Ordering {
    let by = |l: f64, r: f64| l.partial_cmp(&r).unwrap_or(Ordering::Equal);
    by(a.0, b.0).then(by(a.2, b.2)).then(by(a.1, b.1))
}

/// Distinct circles tangent to all three, ordered by curvature, y, then x.
///
/// The four sign combinations of the complex Descartes theorem
/// `k4 z4 = sum(k z) +- 2 sqrt(sum(k_i k_j z_i z_j))` are tried and kept only
/// when tangent to all three inputs. A fourth curvature within
/// `tol x (|k1| + |k2| + |k3|)` of zero is a straight line, or its rounding
/// ghost, and is omitted (R24(c), R25).
fn tangent_circles(
    c1: Circle,
    c2: Circle,
    c3: Circle,
    tol: f64,
) -> Result<Vec<Circle>, DescartesError> {
    let (k1, k2, k3) = (c1.0, c2.0, c3.0);
    let (z1, z2, z3) = ((c1.1, c1.2), (c2.1, c2.2), (c3.1, c3.2));
    let pairs = c_add(
        c_add(c_scale(c_mul(z1, z2), k1 * k2), c_scale(c_mul(z2, z3), k2 * k3)),
        c_scale(c_mul(z3, z1), k3 * k1),
    );
    let root_w = c_sqrt(pairs);
    let zsum = c_add(c_add(c_scale(z1, k1), c_scale(z2, k2)), c_scale(z3, k3));
    let line_limit = tol * (k1.abs() + k2.abs() + k3.abs());
    let (plus, minus) = descartes_fourth(k1, k2, k3)?;
    let mut found: Vec<Circle> = Vec::new();
    for k in [plus, minus] {
        if k.abs() <= line_limit {
            continue;
        }
        for factor in [2.0, -2.0] {
            let z = c_div(c_add(zsum, c_scale(root_w, factor)), k);
            let candidate = (k, z.0, z.1);
            if ![c1, c2, c3].iter().all(|&c| is_tangent(candidate, c, tol)) {
                continue;
            }
            if !found.iter().any(|&f| same_circle(candidate, f, tol)) {
                found.push(candidate);
            }
        }
    }
    found.sort_by(circle_order);
    Ok(found)
}

/// Every circle tangent to three mutually tangent circles (R24(c)).
///
/// `BadInput` for a non-finite, zero-curvature or zero-radius input circle,
/// `NoSolution` when the circles are not mutually tangent or no candidate
/// survives. Two circles come back for a zero radicand (one curvature, two
/// centres), one when the other curvature is a line.
pub fn solve(c1: Circle, c2: Circle, c3: Circle) -> Result<Vec<Circle>, DescartesError> {
    check_tangent(&[c1, c2, c3])?;
    let found = tangent_circles(c1, c2, c3, TANGENT_TOL)?;
    if found.is_empty() {
        return Err(DescartesError::NoSolution(format!(
            "{}: no circle is tangent to all three",
            solve_call(&[c1, c2, c3])
        )));
    }
    Ok(found)
}

/// The candidate of curvature `d` (within `tol x |d|`) with the largest y; the
/// first of equal y.
fn pick_fourth(candidates: &[Circle], d: f64, tol: f64) -> Option<Circle> {
    candidates
        .iter()
        .copied()
        .filter(|f| (f.0 - d).abs() <= tol * d.abs())
        .min_by(|a, b| b.2.total_cmp(&a.2))
}

/// Centres of a reduced root: bounding circle at the origin, second on +x.
///
/// With `A = -a`, the radii are `R = 1/A`, `r2 = 1/b`, `r3 = 1/c`, and the
/// triangle of centre distances `R - r2`, `R - r3`, `r2 + r3` gives, after
/// clearing denominators,
///
/// * `x2 = (b - A) / (A b)`
/// * `x3 = P / Q` with `P = bc - A(b + c) - A^2` and `Q = A c (b - A)`
/// * `y3^2 = (h^2 - P^2) / Q^2` with `h = (b - A)(c - A)`
///
/// so the third circle is exact in integers and a collinear root has
/// `h^2 = P^2` and `y3 = 0` exactly, where float arithmetic leaves `y3 = 1e-8`
/// (R25). Overflow: a root past the `10^8` cap never gets here, so
/// `A, b, c <= 10^8` and `b > A` (a circle inside the bounding circle has a
/// larger curvature). Then `|P| <= 3 * 10^16`, `|h| <= 10^16`, `Q <= 10^24`,
/// so `P^2 <= 9 * 10^32` and `h^2 <= 10^32`, about five millionths of
/// `i128::MAX` (1.7 * 10^38; 9e32 / 1.7e38 is about 5e-6): no operation can
/// overflow, so none is checked.
/// `Q > 0` because `b > A`, so no division is by zero.
///
/// The fourth is the candidate of curvature `d` with the larger y, from the
/// complex theorem; none is `NoSolution`. No tangency check runs here.
fn place_root(root: [i64; 4]) -> Result<[Circle; 4], DescartesError> {
    let [a, b, c, d] = root;
    let bound = -a;
    let (big, wide, third) = (i128::from(bound), i128::from(b), i128::from(c));
    let p = wide * third - big * (wide + third) - big * big;
    let q = big * third * (wide - big);
    let h = (wide - big) * (third - big);
    let x2 = (b - bound) as f64 / (bound * b) as f64;
    let x3 = p as f64 / q as f64;
    let y3 = ((h * h - p * p) as f64).sqrt() / q as f64;
    let (c1, c2, c3) = ((a as f64, 0.0, 0.0), (b as f64, x2, 0.0), (c as f64, x3, y3));
    let candidates = tangent_circles(c1, c2, c3, TANGENT_TOL)?;
    let fourth = pick_fourth(&candidates, d as f64, TANGENT_TOL).ok_or_else(|| {
        DescartesError::NoSolution(format!(
            "root {}: no circle of curvature {d} is tangent to its first three circles",
            show(root)
        ))
    })?;
    Ok([c1, c2, c3, fourth])
}

/// The four circles `(k, x, y)` of a reduced root, for drawing.
///
/// `BadInput` unless `root` is a sorted, reduced Descartes root within the cap.
pub fn root_centres(root: [i64; 4]) -> Result<Vec<Circle>, DescartesError> {
    check_reduced_root(root, "root_centres")?;
    Ok(place_root(root)?.to_vec())
}

/// Replace circle `i` of the quadruple by its reflection of curvature `k`; the
/// new centre is `(2 x sum(k z) of the other three - k_i z_i) / k`.
fn child(ks: [i64; 4], zs: [Complex; 4], i: usize, k: i64) -> ([i64; 4], [Complex; 4], usize) {
    let others = (0..4)
        .filter(|&m| m != i)
        .fold((0.0, 0.0), |acc, m| c_add(acc, c_scale(zs[m], ks[m] as f64)));
    let mut child_ks = ks;
    let mut child_zs = zs;
    child_ks[i] = k;
    child_zs[i] = c_div(c_sub(c_scale(others, 2.0), c_scale(zs[i], ks[i] as f64)), k as f64);
    (child_ks, child_zs, i)
}

/// Every positive circle of the packing with curvature at most `limit`, with
/// centres, so `visible(root, n).len() == pack(root, n).0`.
///
/// The same search as `pack`, carrying centres; the growth guard keeps the walk
/// bounded as there (spec R21). The bounding circle is not returned (R24(d)).
pub fn visible(root: [i64; 4], limit: i64) -> Result<Vec<Circle>, DescartesError> {
    check_n(limit, N_MAX, "visible", "limit")?;
    check_reduced_root(root, "visible")?;
    let placed = place_root(root)?;
    let mut found = Vec::new();
    walk_centres(root, placed, limit, &mut |circle| found.push(circle));
    Ok(found)
}

/// The DFS behind `visible`, with no precondition checks; `on_circle` runs once
/// per circle so a test can budget the work. It repeats `walk`'s control flow
/// rather than sharing it, because the stack here carries centres and `pack`'s
/// counting loop must stay free of floats (spec Component 6).
fn walk_centres(
    root: [i64; 4],
    placed: [Circle; 4],
    limit: i64,
    on_circle: &mut impl FnMut(Circle),
) {
    for (&k, &circle) in root.iter().zip(&placed).skip(1) {
        if k <= limit {
            on_circle(circle);
        }
    }
    let centres = placed.map(|c| (c.1, c.2));
    let total: i64 = root.iter().sum();
    let mut stack: Vec<([i64; 4], [Complex; 4], usize)> = Vec::new();
    for (i, &old) in root.iter().enumerate() {
        let k = 2 * (total - old) - old;
        if k <= limit {
            stack.push(child(root, centres, i, k));
        }
    }
    while let Some((quad, zs, j)) = stack.pop() {
        on_circle((quad[j] as f64, zs[j].0, zs[j].1));
        let total: i64 = quad.iter().sum();
        for (i, &old) in quad.iter().enumerate() {
            let k = 2 * (total - old) - old;
            if old < k && k <= limit {
                stack.push(child(quad, zs, i, k));
            }
        }
    }
}

// SVG output (spec R8-R11): one 1000 x 1000 viewBox, y flipped so up is up.

const SVG_HEAD: [&str; 3] = [
    r#"<?xml version="1.0" encoding="UTF-8"?>"#,
    r#"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">"#,
    r#"<rect width="1000" height="1000" fill="white"/>"#,
];

const SVG_BLACK: &str = r#"stroke="black""#;
const SVG_SOLUTION: &str = r##"stroke="#c00" stroke-dasharray="6 4""##;

/// Three decimals, with `-0.000` written as `0.000`.
fn fmt3(v: f64) -> String {
    let text = format!("{v:.3}");
    if text == "-0.000" { "0.000".to_string() } else { text }
}

/// Map a circle `(k, x, y)` to SVG `(cx, cy, r)` for centre `(x0, y0)` and scale `s`.
fn svg_geometry(c: Circle, x0: f64, y0: f64, s: f64) -> (f64, f64, f64) {
    (500.0 + (c.1 - x0) * s, 500.0 - (c.2 - y0) * s, s / c.0.abs())
}

fn svg_circle(cx: f64, cy: f64, r: f64, stroke: &str) -> String {
    // `stroke` is the attribute text, so a solution can add its dash pattern.
    let width = fmt3((r / 4.0).min(1.0));
    format!(
        r#"<circle cx="{}" cy="{}" r="{}" fill="none" {stroke} stroke-width="{width}"/>"#,
        fmt3(cx),
        fmt3(cy),
        fmt3(r)
    )
}

fn svg_label(cx: f64, cy: f64, r: f64, k: f64) -> String {
    format!(
        r#"<text x="{}" y="{}" font-size="{}" text-anchor="middle" dominant-baseline="central">{}</text>"#,
        fmt3(cx),
        fmt3(cy),
        fmt3((0.6 * r).min(48.0)),
        k.round() as i64
    )
}

fn svg_document(body: Vec<String>) -> String {
    let mut lines: Vec<String> = SVG_HEAD.iter().map(|l| l.to_string()).collect();
    lines.extend(body);
    lines.push("</svg>".to_string());
    lines.join("\n") + "\n"
}

/// The packing as SVG text: the outer circle, then every visible circle up to
/// curvature `min(10^k, 1000 |k0|)`; circles with radius 20 or more are labelled
/// with their curvature (the outer one is not).
///
/// Errors as `root_centres` and `visible`.
pub fn svg_packing(root: [i64; 4], k: u32) -> Result<String, DescartesError> {
    let (k0, x0, y0) = root_centres(root)?[0];
    let s = 500.0 * k0.abs();
    let limit = 10_f64.powi(k as i32).min(1000.0 * k0.abs()) as i64;
    let mut body = Vec::new();
    let (cx, cy, r) = svg_geometry((k0, x0, y0), x0, y0, s);
    body.push(svg_circle(cx, cy, r, SVG_BLACK));
    for c in visible(root, limit)? {
        let (cx, cy, r) = svg_geometry(c, x0, y0, s);
        body.push(svg_circle(cx, cy, r, SVG_BLACK));
        if r >= 20.0 {
            body.push(svg_label(cx, cy, r, c.0));
        }
    }
    Ok(svg_document(body))
}

/// The `--solve` result as SVG text: the givens in black, then the solutions
/// dashed red, framed so every given and every enclosing solution fits.
pub fn svg_solve(given: &[Circle], solutions: &[Circle]) -> String {
    let framed: Vec<Circle> =
        given.iter().chain(solutions.iter().filter(|c| c.0 < 0.0)).copied().collect();
    let extent = |pick: fn(&Circle) -> f64| {
        let lo = framed.iter().map(|c| pick(c) - 1.0 / c.0.abs()).fold(f64::INFINITY, f64::min);
        let hi = framed.iter().map(|c| pick(c) + 1.0 / c.0.abs()).fold(f64::NEG_INFINITY, f64::max);
        (lo, hi)
    };
    let (x_lo, x_hi) = extent(|c| c.1);
    let (y_lo, y_hi) = extent(|c| c.2);
    let side = 1.1 * (x_hi - x_lo).max(y_hi - y_lo);
    let (x0, y0, s) = ((x_lo + x_hi) / 2.0, (y_lo + y_hi) / 2.0, 1000.0 / side);
    let mut body = Vec::new();
    for c in given {
        let (cx, cy, r) = svg_geometry(*c, x0, y0, s);
        body.push(svg_circle(cx, cy, r, SVG_BLACK));
    }
    for c in solutions {
        let (cx, cy, r) = svg_geometry(*c, x0, y0, s);
        body.push(svg_circle(cx, cy, r, SVG_SOLUTION));
    }
    svg_document(body)
}

// Braille as in triangle.py: a cell is 2 dots wide and 4 tall, and is drawn
// twice as tall as wide, so a unit of length is the same number of dots in x
// and in y.
const BRAILLE_BASE: u32 = 0x2800;
/// Dot bits by (column within the cell, row within the cell).
const DOT_BITS: [[u8; 4]; 2] = [[0x01, 0x02, 0x04, 0x40], [0x08, 0x10, 0x20, 0x80]];

fn braille(bits: u8) -> char {
    char::from_u32(BRAILLE_BASE + u32::from(bits)).unwrap_or(' ')
}

/// `BadInput` for a canvas under 1 x 1 or a circle that cannot be drawn.
fn check_render_input(
    circles: &[Circle],
    width: usize,
    height: usize,
) -> Result<(), DescartesError> {
    if width < 1 || height < 1 {
        return Err(DescartesError::BadInput(format!(
            "render: canvas {width}x{height} is too small, need at least 1x1"
        )));
    }
    for (number, &c) in circles.iter().enumerate() {
        if let Some(problem) = input_problem(c) {
            return Err(DescartesError::BadInput(format!(
                "render: circle {} {problem} (curvature {}, centre ({}, {}))",
                number + 1,
                c.0,
                c.1,
                c.2
            )));
        }
    }
    Ok(())
}

/// `(min, max)` of `centre(c) -/+ r` over the circles.
fn extent(circles: &[Circle], radii: &[f64], centre: impl Fn(&Circle) -> f64) -> (f64, f64) {
    circles.iter().zip(radii).fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), (c, r)| {
        (lo.min(centre(c) - r), hi.max(centre(c) + r))
    })
}

/// Centre and radius in dots (x right, y down) of each circle on the grid.
///
/// The bounding box of all circles is fitted into dots `0.5 ..= W - 1.5` (and
/// likewise in y) at one scale and centred, so rounding a centre and a radius
/// to whole dots moves an edge by under one dot and never off the grid.
/// Rounding is `floor(v + 0.5)`.
fn dot_circles(
    circles: &[Circle],
    width: usize,
    height: usize,
) -> Result<Vec<(i64, i64, i64)>, DescartesError> {
    let radii: Vec<f64> = circles.iter().map(|c| (1.0 / c.0).abs()).collect();
    let (x_min, x_max) = extent(circles, &radii, |c| c.1);
    let (y_min, y_max) = extent(circles, &radii, |c| c.2);
    let (x_span, y_span) = (x_max - x_min, y_max - y_min);
    let (dots_x, dots_y) = ((2 * width) as f64, (4 * height) as f64);
    let scale = ((dots_x - 2.0) / x_span).min((dots_y - 2.0) / y_span);
    if !(x_span.is_finite() && y_span.is_finite() && scale.is_finite()) {
        return Err(DescartesError::BadInput(format!(
            "render: the circles' bounding box ({x_span} x {y_span}) cannot be scaled onto a {width}x{height} canvas"
        )));
    }
    let left = (dots_x - 1.0 - x_span * scale) / 2.0;
    let top = (dots_y - 1.0 - y_span * scale) / 2.0;
    let round = |v: f64| (v + 0.5).floor() as i64;
    Ok(circles
        .iter()
        .zip(&radii)
        .map(|(c, &r)| {
            (
                round(left + (c.1 - x_min) * scale),
                round(top + (y_max - c.2) * scale),
                round(r * scale),
            )
        })
        .collect())
}

/// Dots on the circle of the given radius (midpoint algorithm), repeats
/// allowed; a radius of 0 is the centre dot alone.
fn midpoint_circle(cx: i64, cy: i64, radius: i64) -> Vec<(i64, i64)> {
    let mut dots = Vec::new();
    let (mut x, mut y) = (radius, 0);
    let mut decision = 1 - radius;
    while x >= y {
        for (dx, dy) in [(x, y), (y, x)] {
            for px in [cx - dx, cx + dx] {
                for py in [cy - dy, cy + dy] {
                    dots.push((px, py));
                }
            }
        }
        y += 1;
        if decision <= 0 {
            decision += 2 * y + 1;
        } else {
            x -= 1;
            decision += 2 * (y - x) + 1;
        }
    }
    dots
}

/// Light dot `(x, y)` in the cell grid; a dot off the grid is ignored. A
/// negative coordinate must not wrap to the far edge.
fn plot(cells: &mut [Vec<u8>], x: i64, y: i64, width: usize, height: usize) {
    let (Ok(col), Ok(row)) = (usize::try_from(x), usize::try_from(y)) else {
        return;
    };
    if col < 2 * width && row < 4 * height {
        cells[row / 4][col / 2] |= DOT_BITS[col % 2][row % 4];
    }
}

/// Draw circles as braille text, `width` x `height` cells, y up on the page.
///
/// Reads only the `(k, x, y)` list. `BadInput` for a canvas under 1 x 1, a
/// circle with a non-finite value or zero curvature, or a bounding box that
/// cannot be scaled onto the canvas.
pub fn render(
    circles: &[Circle],
    width: usize,
    height: usize,
) -> Result<Vec<String>, DescartesError> {
    check_render_input(circles, width, height)?;
    let mut cells = vec![vec![0u8; width]; height];
    if !circles.is_empty() {
        for (cx, cy, radius) in dot_circles(circles, width, height)? {
            for (x, y) in midpoint_circle(cx, cy, radius) {
                plot(&mut cells, x, y, width, height);
            }
        }
    }
    Ok(cells.iter().map(|row| row.iter().map(|&bits| braille(bits)).collect()).collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    #[test]
    fn fourth_of_the_default_root() {
        // s = -2 + 4 - 2 = 0, so both roots are -1 + 2 + 2
        assert_eq!(descartes_fourth(-1.0, 2.0, 2.0), Ok((3.0, 3.0)));
    }

    #[test]
    fn fourth_gives_both_roots() {
        // 2,3,6: s = 6+18+12 = 36, so 11 +- 12
        assert_eq!(descartes_fourth(2.0, 3.0, 6.0), Ok((23.0, -1.0)));
    }

    #[test]
    fn fourth_is_symmetric_in_its_arguments() {
        assert_eq!(descartes_fourth(6.0, 2.0, 3.0), descartes_fourth(2.0, 3.0, 6.0));
    }

    #[test]
    fn fourth_with_zero_curvature_line() {
        // 0,0,1: s = 0, both roots 1
        assert_eq!(descartes_fourth(0.0, 0.0, 1.0), Ok((1.0, 1.0)));
    }

    #[test]
    fn tolerance_is_one_ppt_of_the_summed_products() {
        // Same four fixtures and outcomes as Python's
        // test_tolerance_is_one_ppt_of_the_summed_products (R23).
        let cases: [((f64, f64, f64), bool); 4] = [
            ((0.003, 0.004, -0.0017142857142925713), true),
            ((-0.20473980815368198, 0.361, 0.473), false),
            ((0.203, 1.144, -0.1724068299927485), false),
            // s is exactly -4 and the tolerance 1e-12 * 4e12 = 4: equal is
            // inside the window, so it clamps.
            ((2.0, 999999999999.0, -2.0), false),
        ];
        for ((k1, k2, k3), raises) in cases {
            let got = descartes_fourth(k1, k2, k3);
            if raises {
                assert!(
                    matches!(got, Err(DescartesError::NoSolution(_))),
                    "({k1}, {k2}, {k3}) should raise, got {got:?}"
                );
            } else {
                let (plus, minus) = got.unwrap_or_else(|e| panic!("({k1}, {k2}, {k3}): {e}"));
                assert_eq!(plus, minus);
                assert_eq!(plus, k1 + k2 + k3);
            }
        }
    }

    #[test]
    fn no_solution_message_names_the_operation_and_inputs() {
        let Err(DescartesError::NoSolution(msg)) = descartes_fourth(1.0, 1.0, -2.0) else {
            panic!("expected NoSolution");
        };
        assert!(msg.contains("descartes_fourth(1, 1, -2)"), "{msg}");
        assert!(msg.contains("negative"), "{msg}");
    }

    #[test]
    fn exit_codes_follow_python() {
        assert_eq!(DescartesError::BadInput("x".into()).exit_code(), 2);
        assert_eq!(DescartesError::NoSolution("x".into()).exit_code(), 1);
    }

    #[test]
    fn display_is_the_message() {
        assert_eq!(DescartesError::BadInput("bad".into()).to_string(), "bad");
        assert_eq!(DescartesError::NoSolution("none".into()).to_string(), "none");
    }

    proptest! {
        #[test]
        fn prop_result_satisfies_descartes_relation(
            k1 in 0.1f64..50.0, k2 in 0.1f64..50.0, k3 in 0.1f64..50.0,
        ) {
            let (plus, minus) = descartes_fourth(k1, k2, k3).unwrap();
            for k4 in [plus, minus] {
                let total = k1 + k2 + k3 + k4;
                let squares = 2.0 * (k1 * k1 + k2 * k2 + k3 * k3 + k4 * k4);
                prop_assert!((total * total - squares).abs() <= 1e-9 * squares);
            }
        }
    }

    // --- validate_root and pack (Python's TestValidateRoot, TestRootCeiling,
    // TestPack*): same values, rules and messages ---------------------------------

    type Root = [i64; 4];

    const ROOT_A: Root = [-1, 2, 2, 3];
    const ROOT_B: Root = [-2, 3, 6, 7];
    const ROOT_C: Root = [-3, 4, 12, 13];
    const ROOT_D: Root = [-11, 21, 24, 28];
    const ROOT_E: Root = [-3, 5, 8, 8];
    const ALL_ROOTS: [Root; 5] = [ROOT_A, ROOT_B, ROOT_C, ROOT_D, ROOT_E];

    // (root, n, circle count, distinct curvatures): Python's PINNED table, spec R2.
    const PINNED: [(Root, i64, i64, usize); 19] = [
        (ROOT_A, 30, 38, 11),
        (ROOT_A, 100, 168, 33),
        (ROOT_A, 1000, 3328, 324),
        (ROOT_A, 10_000, 67_166, 3299),
        (ROOT_A, 100_000, 1_359_170, 33_273),
        (ROOT_B, 30, 14, 8),
        (ROOT_B, 100, 66, 28),
        (ROOT_B, 1000, 1300, 297),
        (ROOT_C, 30, 10, 6),
        (ROOT_C, 100, 40, 17),
        (ROOT_C, 1000, 744, 200),
        (ROOT_D, 10, 0, 0),
        (ROOT_D, 30, 3, 3),
        (ROOT_D, 100, 9, 9),
        (ROOT_D, 1000, 144, 114),
        (ROOT_E, 10, 3, 2),
        (ROOT_E, 30, 10, 6),
        (ROOT_E, 100, 38, 16),
        (ROOT_E, 1000, 785, 203),
    ];

    const ROOT_A_DISTINCT_30: [i64; 11] = [2, 3, 6, 11, 14, 15, 18, 23, 26, 27, 30];

    fn reflect(q: Root, i: usize) -> Root {
        let others = q.iter().sum::<i64>() - q[i];
        let mut r = q;
        r[i] = 2 * others - q[i];
        r
    }

    /// Sorted quads reachable from `root` in at most `depth` reflections that
    /// keep exactly one negative curvature, root excluded: valid but unreduced
    /// roots whose canonical root is `root` (derived from the reflection theorem).
    fn descendants(root: Root, depth: usize) -> Vec<Root> {
        let mut seen = std::collections::HashSet::from([root]);
        let mut frontier = vec![root];
        let mut found = Vec::new();
        for _ in 0..depth {
            let mut next = Vec::new();
            for quad in frontier {
                for i in 0..4 {
                    let mut child = reflect(quad, i);
                    child.sort_unstable();
                    if seen.insert(child) {
                        next.push(child);
                        if child.iter().filter(|&&k| k < 0).count() == 1 {
                            found.push(child);
                        }
                    }
                }
            }
            frontier = next;
        }
        found
    }

    fn unreduced() -> Vec<(Root, Root)> {
        ALL_ROOTS
            .iter()
            .flat_map(|&root| descendants(root, 3).into_iter().map(move |q| (root, q)))
            .collect()
    }

    fn bad_input(r: Result<impl std::fmt::Debug, DescartesError>) -> String {
        match r {
            Err(DescartesError::BadInput(m)) => m,
            other => panic!("expected BadInput, got {other:?}"),
        }
    }

    fn no_solution(r: Result<impl std::fmt::Debug, DescartesError>) -> String {
        match r {
            Err(DescartesError::NoSolution(m)) => m,
            other => panic!("expected NoSolution, got {other:?}"),
        }
    }

    /// Independent oracle: same walk over a `HashSet`, no bitmap.
    fn oracle(root: Root, n: i64) -> (i64, std::collections::BTreeSet<i64>) {
        let mut count = 0;
        let mut set = std::collections::BTreeSet::new();
        for &k in &root[1..] {
            if k <= n {
                count += 1;
                set.insert(k);
            }
        }
        let mut stack: Vec<(Root, usize)> =
            (0..4).map(|i| (reflect(root, i), i)).filter(|(q, i)| q[*i] <= n).collect();
        while let Some((quad, j)) = stack.pop() {
            count += 1;
            set.insert(quad[j]);
            for i in 0..4 {
                let child = reflect(quad, i);
                if quad[i] < child[i] && child[i] <= n {
                    stack.push((child, i));
                }
            }
        }
        (count, set)
    }

    #[test]
    fn ceilings_are_pinned() {
        assert_eq!(ROOT_MAX, 100_000_000);
        assert_eq!(N_MAX, 100_000_000);
    }

    #[test]
    fn validate_valid_reduced_root_unchanged() {
        assert_eq!(validate_root([-1, 2, 2, 3]), Ok(ROOT_A));
    }

    #[test]
    fn validate_sorts_unordered_input() {
        assert_eq!(validate_root([3, 2, -1, 2]), Ok(ROOT_A));
    }

    #[test]
    fn validate_reduces_to_root_a() {
        for root in [[-1, 2, 3, 6], [-1, 3, 6, 14], [-1, 2, 2, 3]] {
            assert_eq!(validate_root(root), Ok(ROOT_A), "{root:?}");
        }
    }

    #[test]
    fn validate_every_descendant_reduces_to_its_root() {
        let all = unreduced();
        assert!(all.len() > 20, "generator produced {}", all.len());
        for (root, quad) in all {
            assert_eq!(validate_root(quad), Ok(root), "{quad:?}");
        }
    }

    #[test]
    fn validate_reduction_stops_at_a_tied_maximum() {
        // (-3, 5, 8, 12) reflects to (-3, 5, 8, 8): the tie must not end it early.
        assert_eq!(validate_root([-3, 5, 8, 12]), Ok(ROOT_E));
    }

    #[test]
    fn validate_reduced_roots_are_fixed_points() {
        for root in ALL_ROOTS {
            assert_eq!(validate_root(root), Ok(root));
        }
    }

    #[test]
    fn validate_not_a_descartes_quadruple_names_both_sides() {
        let m = no_solution(validate_root([-1, 2, 2, 4]));
        assert!(m.contains("(-1, 2, 2, 4)"), "{m}");
        assert!(m.contains("(Σk)²=49, 2Σk²=50"), "{m}");
        assert!(m.contains("not a Descartes quadruple"), "{m}");
    }

    #[test]
    fn validate_relation_fails_with_square_sum_above() {
        // (Σk)² = 64 exceeds 2Σk² = 56.
        let m = no_solution(validate_root([-1, 3, 3, 3]));
        assert!(m.contains("(Σk)²=64, 2Σk²=56"), "{m}");
    }

    #[test]
    fn validate_zero_is_not_negative() {
        // (0, 1, 1, 4) satisfies the relation; zero must not count as negative.
        let m = no_solution(validate_root([0, 1, 1, 4]));
        assert!(m.contains("exactly one negative"), "{m}");
        assert!(m.contains("(0, 1, 1, 4)"), "{m}");
    }

    #[test]
    fn validate_rejects_zero_two_negative_and_all_positive_roots() {
        for (root, shown) in [
            ([0, 0, 1, 1], "(0, 0, 1, 1)"),
            ([-1, -1, 0, 0], "(-1, -1, 0, 0)"),
            ([2, 2, 3, 15], "(2, 2, 3, 15)"),
        ] {
            let m = no_solution(validate_root(root));
            assert!(m.contains("exactly one negative"), "{m}");
            assert!(m.contains(shown), "{m}");
        }
    }

    #[test]
    fn validate_names_the_input_order_not_the_sorted_order() {
        let m = no_solution(validate_root([4, 2, -1, 2]));
        assert!(m.contains("(4, 2, -1, 2)"), "{m}");
    }

    #[test]
    fn validate_values_above_the_ceiling_are_bad_input() {
        for root in [
            [-1, 2, 2, 100_000_001],
            [-100_000_001, 2, 2, 3],
            // n = 10^4: just above the cap, and only 10^4 steps without it, so a
            // regressed cap fails here at once instead of looping.
            [-1, 2, 100_000_002, 10_001 * 10_001 + 2],
            [i64::MAX, 2, 2, 3],
            [i64::MIN, 2, 2, 3],
        ] {
            let m = bad_input(validate_root(root));
            assert!(m.contains("at most 10^8 in absolute value"), "{m}");
        }
    }

    #[test]
    fn validate_ceiling_message_names_root_and_value() {
        let m = bad_input(validate_root([-1, 2, 2, 100_000_001]));
        assert!(m.contains("root (-1, 2, 2, 100000001)"), "{m}");
        assert!(m.ends_with("got 100000001"), "{m}");
    }

    #[test]
    fn validate_values_at_the_ceiling_reach_the_descartes_check() {
        for root in [[-1, 2, 2, 100_000_000], [-100_000_000, 2, 2, 3]] {
            let m = no_solution(validate_root(root));
            assert!(m.contains("not a Descartes quadruple"), "{m}");
        }
    }

    #[test]
    fn validate_longest_chain_under_the_ceiling_reduces() {
        // n = 9998 gives 99960006 and 99980003, both under 10^8.
        let n = 9998;
        assert_eq!(validate_root([-1, 2, n * n + 2, (n + 1) * (n + 1) + 2]), Ok(ROOT_A));
    }

    #[test]
    fn pack_pinned_values() {
        for (root, n, count, n_distinct) in PINNED {
            let (got, bitmap) = pack(root, n).unwrap();
            assert_eq!((got, distinct(&bitmap).len()), (count, n_distinct), "{root:?} n={n}");
        }
    }

    #[test]
    fn pack_agrees_with_an_independent_walk() {
        for root in ALL_ROOTS {
            for n in [0, 1, 63, 64, 65, 127, 128, 300, 1000] {
                let (count, bitmap) = pack(root, n).unwrap();
                let (want_count, want) = oracle(root, n);
                assert_eq!(count, want_count, "{root:?} n={n}");
                assert_eq!(
                    distinct(&bitmap),
                    want.into_iter().collect::<Vec<_>>(),
                    "{root:?} n={n}"
                );
            }
        }
    }

    #[test]
    fn pack_distinct_list_root_a_30() {
        let (_, bitmap) = pack(ROOT_A, 30).unwrap();
        assert_eq!(distinct(&bitmap), ROOT_A_DISTINCT_30);
    }

    #[test]
    fn pack_bitmap_size_is_n_div_64_plus_one_words() {
        for (n, words) in [(0, 1), (30, 1), (63, 1), (64, 2), (127, 2), (128, 3)] {
            assert_eq!(pack(ROOT_A, n).unwrap().1.len(), words, "n={n}");
        }
    }

    #[test]
    fn distinct_reads_every_bit_of_every_word() {
        let bitmap = [(1u64 << 63) | 1, 1 | (1 << 63), 1 << 5, 0];
        assert_eq!(distinct(&bitmap), vec![0, 63, 64, 127, 133]);
        assert_eq!(distinct(&[]), Vec::<i64>::new());
        assert_eq!(distinct(&[0, 0]), Vec::<i64>::new());
        assert_eq!(distinct(&[u64::MAX]), (0..64).collect::<Vec<i64>>());
    }

    #[test]
    fn pack_n_below_every_curvature_is_empty() {
        let (count, bitmap) = pack(ROOT_A, 1).unwrap();
        assert_eq!((count, distinct(&bitmap)), (0, vec![]));
        assert!(bitmap.iter().all(|&w| w == 0));
    }

    #[test]
    fn pack_n_zero() {
        assert_eq!(pack(ROOT_A, 0), Ok((0, vec![0])));
    }

    #[test]
    fn pack_n_equal_to_smallest_curvature_counts_each_circle() {
        let (count, bitmap) = pack(ROOT_A, 2).unwrap();
        assert_eq!((count, distinct(&bitmap)), (2, vec![2]));
    }

    #[test]
    fn pack_each_curvature_is_absent_one_below_and_present_at_n() {
        for c in ROOT_A_DISTINCT_30 {
            assert!(!distinct(&pack(ROOT_A, c - 1).unwrap().1).contains(&c), "c={c}");
            assert!(distinct(&pack(ROOT_A, c).unwrap().1).contains(&c), "c={c}");
        }
    }

    #[test]
    fn pack_never_counts_the_bounding_circle() {
        for root in ALL_ROOTS {
            assert!(distinct(&pack(root, 100).unwrap().1).iter().all(|&k| k > 0));
        }
    }

    #[test]
    fn pack_negative_n_is_bad_input() {
        for n in [-1, -9] {
            let m = bad_input(pack(ROOT_A, n));
            assert_eq!(m, format!("pack(n={n}): n must not be negative"));
        }
    }

    #[test]
    fn pack_n_above_the_ceiling_is_bad_input() {
        let m = bad_input(pack(ROOT_A, N_MAX + 1));
        assert_eq!(m, "pack(n=100000001): n must be at most 100000000");
        assert!(pack(ROOT_A, i64::MAX).is_err());
    }

    #[test]
    fn check_n_pins_both_bounds_at_a_small_ceiling() {
        assert_eq!(check_n(0, 30, "pack", "n"), Ok(()));
        assert_eq!(check_n(30, 30, "pack", "n"), Ok(()));
        assert_eq!(
            check_n(31, 30, "pack", "n"),
            Err(DescartesError::BadInput("pack(n=31): n must be at most 30".into()))
        );
        assert_eq!(
            check_n(-1, 30, "visible", "limit"),
            Err(DescartesError::BadInput("visible(limit=-1): limit must not be negative".into()))
        );
    }

    #[test]
    fn pack_checks_n_before_the_root() {
        let m = bad_input(pack([-1, 2, 3, 6], -1));
        assert!(m.contains("n must not be negative"), "{m}");
    }

    #[test]
    fn pack_unreduced_root_is_rejected_and_named() {
        let m = bad_input(pack([-1, 2, 3, 6], 100));
        assert_eq!(
            m,
            "pack(root=(-1, 2, 3, 6), ...): root is not reduced (use validate_root first)"
        );
    }

    #[test]
    fn pack_unsorted_root_is_named_unsorted() {
        let m = bad_input(pack([2, -1, 2, 3], 100));
        assert_eq!(m, "pack(root=(2, -1, 2, 3), ...): root is not sorted ascending");
    }

    #[test]
    fn pack_relation_failures_are_named_in_both_directions() {
        for root in [[-1, 2, 2, 4], [-1, 3, 3, 3]] {
            let m = bad_input(pack(root, 100));
            assert!(m.ends_with("root is not a Descartes quadruple"), "{m}");
        }
    }

    #[test]
    fn pack_negative_count_is_checked_before_reduction() {
        for root in [[-1, -1, 0, 0], [0, 1, 1, 4], [0, 0, 1, 1], [2, 2, 3, 15]] {
            let m = bad_input(pack(root, 100));
            assert!(m.ends_with("root is needs exactly one negative curvature"), "{m}");
        }
    }

    #[test]
    fn pack_every_unreduced_descendant_is_rejected() {
        for (_, quad) in unreduced() {
            let m = bad_input(pack(quad, 100));
            assert!(m.contains("not reduced"), "{quad:?}: {m}");
        }
    }

    #[test]
    fn pack_reduced_roots_are_accepted() {
        for root in ALL_ROOTS {
            assert!(pack(root, 100).is_ok(), "{root:?}");
        }
    }

    #[test]
    fn pack_root_beyond_the_ceiling_is_bad_input_without_overflow() {
        for root in [
            [-1, 2, 2, 100_000_001],
            [-100_000_001, 2, 2, 3],
            [i64::MAX, i64::MAX, i64::MAX, i64::MAX],
            [i64::MIN, 2, 2, 3],
        ] {
            let m = bad_input(pack(root, 100));
            assert!(m.contains("at most 10^8 in absolute value"), "{root:?}: {m}");
        }
    }

    #[test]
    fn pack_is_repeatable_and_independent_of_earlier_runs() {
        assert_eq!(pack(ROOT_A, 100), pack(ROOT_A, 100));
        let _ = pack(ROOT_A, 1000);
        assert_eq!(pack(ROOT_A, 30).unwrap().0, 38);
    }

    #[test]
    fn pack_count_is_monotone_in_n() {
        let counts: Vec<i64> = (0..80).map(|n| pack(ROOT_A, n).unwrap().0).collect();
        assert!(counts.windows(2).all(|w| w[0] <= w[1]), "{counts:?}");
    }

    // R21: for a real Descartes quadruple the only decreasing reflection is the
    // one just made, so the growth guard cannot be exercised on valid input. Both
    // roots break the relation: without the guard (-1, 1, 1, 1) reflects forever,
    // and with only `k != quad[i]` (-1, 1, 1, 2) pushes a falling curvature. The
    // walk is budgeted so a missing guard fails within the 10,000-step budget.
    #[test]
    fn walk_terminates_when_the_root_invariant_is_broken() {
        for root in [[-1, 1, 1, 1], [-1, 1, 1, 2]] {
            let mut marks: i64 = 0;
            let (count, bitmap) = walk(root, 30, &mut || {
                marks += 1;
                assert!(marks < 10_000, "walk did not terminate for {root:?}");
            });
            assert_eq!(count, marks, "{root:?}");
            assert!(distinct(&bitmap).iter().all(|&k| (0..=30).contains(&k)), "{root:?}");
        }
    }

    #[test]
    fn walk_on_a_valid_root_counts_every_circle_once() {
        let mut marks: i64 = 0;
        let (count, _) = walk(ROOT_A, 100, &mut || marks += 1);
        assert_eq!((count, marks), (168, 168));
    }

    proptest! {
        #[test]
        fn prop_count_is_monotone_and_distinct_stays_in_range(
            which in 0usize..5, n in 0i64..400,
        ) {
            let root = ALL_ROOTS[which];
            let (lo, bitmap) = pack(root, n).unwrap();
            let (hi, _) = pack(root, n + 1).unwrap();
            prop_assert!(lo <= hi);
            let ks = distinct(&bitmap);
            prop_assert!(ks.iter().all(|&k| 1 <= k && k <= n));
            prop_assert!(ks.len() as i64 <= lo);
        }
    }

    // --- geometry and render: Python's TestRootCentres, TestCheckTangent,
    // TestSolve, TestSameCircle, TestVisible, TestRender and TestPlot, with the
    // same hand-derived values ---------------------------------------------------

    const R9_C1: Circle = (-1.0, 0.0, 0.0);
    const R9_C2: Circle = (2.0, 0.5, 0.0);
    const R9_C3: Circle = (3.0, 0.0, 0.666_666_666_666_666_6);
    const UNIT: Circle = (1.0, 0.0, 0.0);
    const BOUNDING: Circle = (-1.0, 0.0, 0.0);
    const BLANK: char = '\u{2800}';

    fn close(a: Circle, b: Circle, tol: f64) -> bool {
        (a.0 - b.0).abs() <= tol && (a.1 - b.1).abs() <= tol && (a.2 - b.2).abs() <= tol
    }

    /// Tangency error of two circles, written without `pair_gap`: the centre
    /// distance against the sum of the signed radii.
    fn gap(a: Circle, b: Circle) -> f64 {
        let dist = ((a.1 - b.1).powi(2) + (a.2 - b.2).powi(2)).sqrt();
        (dist - (1.0 / a.0 + 1.0 / b.0).abs()).abs()
    }

    fn sorted_circles(mut v: Vec<Circle>) -> Vec<Circle> {
        v.sort_by(|a, b| a.partial_cmp(b).unwrap());
        v
    }

    // root_centres

    #[test]
    fn root_centres_root_a_values() {
        // Radius-1 bounding circle, two radius-1/2 circles at x = +-1/2 and the
        // curvature-3 circle at y = 2/3.
        let want = [(-1.0, 0.0, 0.0), (2.0, 0.5, 0.0), (2.0, -0.5, 0.0), (3.0, 0.0, 2.0 / 3.0)];
        let got = root_centres(ROOT_A).unwrap();
        assert_eq!(got.len(), 4);
        for (g, w) in got.iter().zip(want) {
            assert!(close(*g, w, 1e-12), "{g:?} != {w:?}");
        }
    }

    #[test]
    fn root_centres_root_e_values() {
        // R=1/3, r2=1/5, r3=1/8: x2 = 2/15, d1 = 5/24, d2 = 13/40, x3 = -1/6,
        // y3^2 = 1/64. The two curvature-8 circles mirror in the x axis.
        let want = [
            (-3.0, 0.0, 0.0),
            (5.0, 2.0 / 15.0, 0.0),
            (8.0, -1.0 / 6.0, 0.125),
            (8.0, -1.0 / 6.0, -0.125),
        ];
        for (g, w) in root_centres(ROOT_E).unwrap().iter().zip(want) {
            assert!(close(*g, w, 1e-12), "{g:?} != {w:?}");
        }
    }

    #[test]
    fn root_centres_root_d_second_and_third_values() {
        // R=1/11, r2=1/21, r3=1/24: x2 = 10/231, x3 = -112/2640 = -7/165,
        // y3^2 = 66^2 / 2640^2, so y3 = 1/40.
        let got = root_centres(ROOT_D).unwrap();
        assert!(close(got[1], (21.0, 10.0 / 231.0, 0.0), 1e-12), "{:?}", got[1]);
        assert!(close(got[2], (24.0, -7.0 / 165.0, 0.025), 1e-12), "{:?}", got[2]);
        assert_eq!(got[3].0, 28.0);
    }

    #[test]
    fn root_centres_curvatures_follow_the_root() {
        for root in ALL_ROOTS {
            let ks: Vec<f64> = root_centres(root).unwrap().iter().map(|c| c.0).collect();
            assert_eq!(ks, root.map(|k| k as f64), "{root:?}");
        }
    }

    #[test]
    fn root_centres_placement_convention() {
        for root in ALL_ROOTS {
            let got = root_centres(root).unwrap();
            assert_eq!((got[0].1, got[0].2), (0.0, 0.0), "{root:?}");
            assert_eq!(got[1].2, 0.0, "{root:?}");
            let want_x2 = 1.0 / (-root[0]) as f64 - 1.0 / root[1] as f64;
            assert!((got[1].1 - want_x2).abs() < 1e-12 && got[1].1 > 0.0, "{root:?}");
            assert!(got[2].2 >= 0.0, "{root:?}");
        }
    }

    #[test]
    fn root_centres_all_six_pairs_are_tangent() {
        for root in ALL_ROOTS.into_iter().chain([[-15, 32, 32, 33]]) {
            let c = root_centres(root).unwrap();
            for i in 0..4 {
                for j in i + 1..4 {
                    assert!(gap(c[i], c[j]) <= 1e-9, "{root:?} pair {} {}", i + 1, j + 1);
                }
            }
        }
    }

    #[test]
    fn root_centres_high_third_circle_matches_the_exact_values() {
        // (-15, 32, 32, 33): P = -161, Q = 8160, y3^2 = 240^2 / 8160^2, so the
        // third circle's squared height is about 11% above 2 x^2
        // (numerators over Q^2 = 8160^2: y3^2 = 57600 against 2 x3^2 = 51842).
        let got = root_centres([-15, 32, 32, 33]).unwrap();
        assert!(close(got[2], (32.0, -161.0 / 8160.0, 240.0 / 8160.0), 1e-12), "{:?}", got[2]);
    }

    #[test]
    fn root_centres_collinear_roots_have_exactly_zero_y() {
        // R25: float rounding would leave y = 1e-8 here.
        for root in [ROOT_A, ROOT_B, ROOT_C] {
            assert_eq!(root_centres(root).unwrap()[2].2, 0.0, "{root:?}");
        }
    }

    #[test]
    fn root_centres_non_collinear_roots_have_positive_y() {
        for root in [ROOT_D, ROOT_E] {
            assert!(root_centres(root).unwrap()[2].2 > 0.01, "{root:?}");
        }
    }

    #[test]
    fn root_centres_is_repeatable() {
        assert_eq!(root_centres(ROOT_D), root_centres(ROOT_D));
    }

    #[test]
    fn root_centres_rejects_invalid_roots_naming_the_operation() {
        for (root, what) in [
            ([-1, 2, 3, 6], "not reduced"),
            ([2, -1, 2, 3], "not sorted"),
            ([-1, 2, 2, 4], "not a Descartes quadruple"),
            ([0, 1, 1, 4], "exactly one negative"),
        ] {
            let m = bad_input(root_centres(root));
            assert!(m.starts_with("root_centres(root="), "{m}");
            assert!(m.contains(what), "{m}");
        }
    }

    #[test]
    fn place_root_without_a_matching_candidate_names_root_and_curvature() {
        // (-1, 2, 2) has curvature 3 as its only fourth circle, not 4.
        let m = no_solution(place_root([-1, 2, 2, 4]));
        assert!(m.contains("root (-1, 2, 2, 4)"), "{m}");
        assert!(m.contains("curvature 4"), "{m}");
    }

    #[test]
    fn pick_fourth_takes_the_larger_y_among_curvature_d() {
        // The curvature-40 circle has the largest y but is not curvature 28.
        let candidates = [(28.0, 0.0, -1.0), (40.0, 0.0, 5.0), (28.0, 0.0, 1.0)];
        assert_eq!(pick_fourth(&candidates, 28.0, TANGENT_TOL), Some((28.0, 0.0, 1.0)));
    }

    #[test]
    fn pick_fourth_chooses_by_y_not_by_x_or_list_order() {
        let candidates = [(28.0, 7.0, -1.0), (28.0, -7.0, 1.0), (28.0, 0.0, 0.5)];
        assert_eq!(pick_fourth(&candidates, 28.0, TANGENT_TOL), Some((28.0, -7.0, 1.0)));
    }

    #[test]
    fn pick_fourth_keeps_the_first_of_equal_y() {
        let candidates = [(28.0, 7.0, 1.0), (28.0, -7.0, 1.0)];
        assert_eq!(pick_fourth(&candidates, 28.0, TANGENT_TOL), Some((28.0, 7.0, 1.0)));
    }

    #[test]
    fn pick_fourth_with_no_candidate_of_curvature_d_is_none() {
        assert_eq!(pick_fourth(&[], 28.0, TANGENT_TOL), None);
        assert_eq!(pick_fourth(&[(40.0, 0.0, 5.0)], 28.0, TANGENT_TOL), None);
    }

    #[test]
    fn pick_fourth_curvature_match_is_relative_to_d() {
        // 0.5e-9 off is kept and 2e-9 off rejected at every magnitude of d.
        for d in [3.0, 7.0, 28.0, 1e6] {
            for near in [d * (1.0 + 0.5e-9), d * (1.0 - 0.5e-9)] {
                let c = (near, 0.0, 1.0);
                assert_eq!(pick_fourth(&[c], d, TANGENT_TOL), Some(c), "d={d}");
            }
            for far in [d * (1.0 + 2e-9), d * (1.0 - 2e-9), 2.0 * d, d / 2.0] {
                assert_eq!(pick_fourth(&[(far, 0.0, 1.0)], d, TANGENT_TOL), None, "d={d}");
            }
        }
    }

    #[test]
    fn pick_fourth_accepts_exactly_the_tolerance() {
        // Tolerance 0.5 and d = 3 make the bound exactly 1.5.
        assert_eq!(pick_fourth(&[(4.5, 0.0, 1.0)], 3.0, 0.5), Some((4.5, 0.0, 1.0)));
        assert_eq!(pick_fourth(&[(4.75, 0.0, 1.0)], 3.0, 0.5), None);
    }

    // complex helpers

    #[test]
    fn complex_helpers_follow_the_textbook_formulas() {
        assert_eq!(c_add((1.0, 2.0), (3.0, 5.0)), (4.0, 7.0));
        assert_eq!(c_sub((4.0, 7.0), (3.0, 5.0)), (1.0, 2.0));
        assert_eq!(c_mul((1.0, 2.0), (3.0, 4.0)), (-5.0, 10.0));
        assert_eq!(c_scale((1.5, -2.0), 4.0), (6.0, -8.0));
        assert_eq!(c_div((6.0, -8.0), 4.0), (1.5, -2.0));
    }

    #[test]
    fn c_sqrt_gives_the_principal_root_in_every_quadrant() {
        // (2+i)^2 = 3+4i, (1+2i)^2 = -3+4i, and conjugates.
        assert_eq!(c_sqrt((3.0, 4.0)), (2.0, 1.0));
        assert_eq!(c_sqrt((3.0, -4.0)), (2.0, -1.0));
        assert_eq!(c_sqrt((-3.0, 4.0)), (1.0, 2.0));
        assert_eq!(c_sqrt((-3.0, -4.0)), (1.0, -2.0));
    }

    #[test]
    fn c_sqrt_of_real_and_zero_inputs_is_exact() {
        assert_eq!(c_sqrt((0.0, 0.0)), (0.0, 0.0));
        assert_eq!(c_sqrt((4.0, 0.0)), (2.0, 0.0));
        assert_eq!(c_sqrt((-4.0, 0.0)), (0.0, 2.0));
        assert_eq!(c_sqrt((-4.0, -0.0)), (0.0, -2.0));
        assert_eq!(c_sqrt((0.0, 2.0)), (1.0, 1.0));
    }

    // check_tangent

    #[test]
    fn check_tangent_r9_triple_passes() {
        assert_eq!(check_tangent(&[R9_C1, R9_C2, R9_C3]), Ok(()));
    }

    #[test]
    fn check_tangent_r9_scaled_by_100_passes() {
        let scaled = [
            (-100.0, 0.0, 0.0),
            (200.0, 0.5 / 100.0, 0.0),
            (300.0, 0.0, 0.666_666_666_666_666_6 / 100.0),
        ];
        assert_eq!(check_tangent(&scaled), Ok(()));
    }

    #[test]
    fn check_tangent_external_triple_passes() {
        // Unit circles at (0,0) and (2,0) and radius 1/4 at (1, 3/4): centre
        // distances 2, 5/4, 5/4 by Pythagoras.
        assert_eq!(check_tangent(&[(1.0, 0.0, 0.0), (1.0, 2.0, 0.0), (4.0, 1.0, 0.75)]), Ok(()));
    }

    #[test]
    fn check_tangent_empty_and_pair_lists_pass() {
        assert_eq!(check_tangent(&[]), Ok(()));
        assert_eq!(check_tangent(&[(1.0, 0.0, 0.0), (1.0, 2.0, 0.0)]), Ok(()));
    }

    #[test]
    fn check_tangent_zero_curvature_is_bad_input_at_every_position() {
        for position in 0..3 {
            let mut triple = [R9_C1, R9_C2, R9_C3];
            triple[position] = (0.0, 0.0, 0.0);
            let m = bad_input(check_tangent(&triple));
            assert!(m.starts_with("solve("), "{m}");
            assert!(m.contains(&format!("circle {} has zero curvature", position + 1)), "{m}");
            assert!(m.contains("(curvature 0, centre (0, 0))"), "{m}");
        }
    }

    #[test]
    fn check_tangent_zero_curvature_wins_over_non_tangency() {
        bad_input(check_tangent(&[(1.0, 0.0, 0.0), (1.0, 9.0, 9.0), (0.0, 0.0, 0.0)]));
    }

    #[test]
    fn check_tangent_third_circle_moved_names_one_and_three_with_measurements() {
        // y = 0.7: pair 1-2 stays tangent; for 1-3 the distance is 0.7, the
        // expected |-1 + 1/3| = 2/3 and the tolerance 1e-9 x (1 + 1/3).
        let m = no_solution(check_tangent(&[R9_C1, R9_C2, (3.0, 0.0, 0.7)]));
        assert!(m.starts_with("solve((-1, 0, 0), (2, 0.5, 0), (3, 0, 0.7))"), "{m}");
        assert!(m.contains("circles 1 and 3 are not tangent"), "{m}");
        assert!(m.contains("measured distance 0.7,"), "{m}");
        assert!(m.contains("expected 0.66666666666666"), "{m}");
        assert!(m.contains("tolerance 0.00000000133333"), "{m}");
    }

    #[test]
    fn check_tangent_pairs_are_checked_in_order_and_the_first_failure_named() {
        // Only 2-3 fails: circle 2 at (0, 0.5) is 0.5 from the origin as needed
        // but 1/6 from circle 3 where 5/6 is needed.
        let m = no_solution(check_tangent(&[R9_C1, (2.0, 0.0, 0.5), R9_C3]));
        assert!(m.contains("circles 2 and 3 are not tangent"), "{m}");
        let m = no_solution(check_tangent(&[R9_C1, R9_C2, (3.0, 5.0, 5.0)]));
        assert!(m.contains("circles 1 and 3 are not tangent"), "{m}");
        let m = no_solution(check_tangent(&[R9_C1, (2.0, 5.0, 5.0), R9_C3]));
        assert!(m.contains("circles 1 and 2 are not tangent"), "{m}");
    }

    #[test]
    fn check_tangent_tolerance_is_relative_to_the_pair() {
        // Moving the third centre up by d moves the 1-3 gap by d (tolerance
        // 1.333e-9) and the 2-3 gap by 0.8 d (tolerance 0.833e-9).
        assert_eq!(
            check_tangent(&[R9_C1, R9_C2, (3.0, 0.0, 0.666_666_666_666_666_6 + 0.9e-9)]),
            Ok(())
        );
        let m =
            no_solution(check_tangent(&[R9_C1, R9_C2, (3.0, 0.0, 0.666_666_666_666_666_6 + 3e-9)]));
        assert!(m.contains("circles 1 and 3"), "{m}");
    }

    /// Whether the NoSolution for a non-tangent triple carries the hint.
    fn hint_for(circles: &[Circle]) -> bool {
        no_solution(check_tangent(circles)).contains("full-precision")
    }

    #[test]
    fn check_tangent_hint_for_six_or_fewer_decimals() {
        for y in [0.6667, -0.6667, 0.5, -0.5, 0.7, 0.123456] {
            assert!(hint_for(&[(1.0, 0.0, 0.0), (1.0, 2.0, 0.0), (4.0, 1.0, y)]), "y={y}");
        }
    }

    #[test]
    fn check_tangent_no_hint_for_long_decimals() {
        for y in [0.6666666666666666, -0.6666666666666666, 0.1234567, 0.3333333333333333] {
            assert!(!hint_for(&[(1.0, 0.0, 0.0), (1.0, 2.0, 0.0), (4.0, 1.0, y)]), "y={y}");
        }
    }

    #[test]
    fn check_tangent_hint_counts_positional_decimals_of_small_values() {
        // 1e-5 is 0.00001 (5 decimals) and 1.5e-5 is 0.000015 (6): hint; 1e-7 is
        // 0.0000001 (7): none.
        let wanted = [(1e-5, true), (1.5e-5, true), (1e-7, false), (1.5e-7, false)];
        for (y, hint) in wanted {
            assert_eq!(hint_for(&[(1.0, 0.0, 0.0), (1.0, 2.0, 0.0), (4.0, 1.0, y)]), hint, "y={y}");
        }
    }

    #[test]
    fn check_tangent_no_hint_for_integer_coordinates() {
        assert!(!hint_for(&[(1.0, 0.0, 0.0), (1.0, 3.0, 0.0), (4.0, 1.0, 1.0)]));
        assert!(!hint_for(&[(1.0, -3.0, 0.0), (1.0, 2.0, 0.0), (4.0, 1.0, 1e5)]));
    }

    #[test]
    fn check_tangent_hint_looks_at_every_coordinate_of_every_circle() {
        // The failing pair is 2-3 in the first case; the short decimal sits in
        // circle 1's x, circle 3's y and circle 2's x in turn.
        assert!(hint_for(&[(1.0, 0.25, 0.0), (1.0, 2.0, 0.0), (4.0, 1.0, 3.0)]));
        assert!(hint_for(&[(1.0, 0.0, 0.0), (1.0, 2.0, 0.0), (4.0, 1.0, 0.9)]));
        assert!(hint_for(&[(1.0, 0.0, 0.0), (1.0, 2.5, 0.0), (4.0, 1.0, 3.0)]));
        // ... and circle 1's y and circle 2's y.
        assert!(hint_for(&[(1.0, 0.0, 0.25), (1.0, 2.0, 0.0), (4.0, 1.0, 3.0)]));
        assert!(hint_for(&[(1.0, 0.0, 0.0), (1.0, 2.0, 0.5), (4.0, 1.0, 3.0)]));
    }

    #[test]
    fn check_tangent_hint_ignores_short_decimal_curvatures() {
        // Curvatures 0.5 and 0.25 have short forms; every coordinate is an integer.
        assert!(!hint_for(&[(0.5, 0.0, 0.0), (0.5, 4.0, 0.0), (0.25, 1.0, 1.0)]));
    }

    #[test]
    fn has_short_decimal_boundaries() {
        for (v, want) in [
            (0.5, true),
            (0.123456, true),
            (0.1234567, false),
            (-0.000001, true),
            (1.0, false),
            (0.0, false),
            (f64::NAN, false),
            (f64::INFINITY, false),
            (1e21, false),
        ] {
            assert_eq!(has_short_decimal(v), want, "{v}");
        }
    }

    #[test]
    fn check_tangent_non_finite_values_are_bad_input_at_every_position() {
        // R26: even the all-tangent R9 triple with one value replaced is
        // refused, since an infinite tolerance would pass every pair.
        let cases: [(usize, f64); 7] = [
            (1, f64::NAN),
            (2, f64::INFINITY),
            (2, f64::NEG_INFINITY),
            (0, f64::INFINITY),
            (0, f64::NAN),
            (0, 5e-324),
            (0, -5e-324),
        ];
        for position in 0..3 {
            for (slot, value) in cases {
                let mut triple = [R9_C1, R9_C2, R9_C3];
                let mut parts = [triple[position].0, triple[position].1, triple[position].2];
                parts[slot] = value;
                triple[position] = (parts[0], parts[1], parts[2]);
                for m in [
                    bad_input(check_tangent(&triple)),
                    bad_input(solve(triple[0], triple[1], triple[2])),
                ] {
                    assert!(m.starts_with("solve("), "{m}");
                    assert!(m.contains(&format!("circle {} has", position + 1)), "{m}");
                }
            }
        }
    }

    #[test]
    fn check_tangent_names_which_problem_each_input_has() {
        let m = bad_input(check_tangent(&[R9_C1, (2.0, f64::NAN, 0.0), R9_C3]));
        assert!(m.contains("circle 2 has a NaN or infinite value"), "{m}");
        let m = bad_input(check_tangent(&[(5e-324, 0.0, 0.0), R9_C2, R9_C3]));
        assert!(m.contains("circle 1 has a curvature whose radius 1/k is not finite"), "{m}");
    }

    #[test]
    fn check_tangent_radius_overflow_boundary() {
        // DBL_MAX is 1.797e308: k = 5.6e-309 has radius 1.786e308 (finite, so it
        // is an input that fails tangency); 5.5e-309 gives 1.818e308 = inf.
        let rest = [(1.0, 3.0, 0.0), (1.0, 0.0, 3.0)];
        no_solution(check_tangent(&[(5.6e-309, 0.0, 0.0), rest[0], rest[1]]));
        let m = bad_input(check_tangent(&[(5.5e-309, 0.0, 0.0), rest[0], rest[1]]));
        assert!(m.contains("circle 1 has"), "{m}");
    }

    #[test]
    fn check_tangent_non_finite_is_bad_input_even_when_pairs_are_far_apart() {
        let m = bad_input(check_tangent(&[(1.0, 0.0, 0.0), (1.0, 9.0, 9.0), (4.0, f64::NAN, 0.0)]));
        assert!(m.contains("circle 3 has"), "{m}");
    }

    #[test]
    fn check_tangent_first_bad_circle_is_the_one_named() {
        let m = bad_input(check_tangent(&[
            (1.0, 0.0, 0.0),
            (1.0, f64::INFINITY, 0.0),
            (4.0, f64::NAN, 0.0),
        ]));
        assert!(m.contains("circle 2 has"), "{m}");
    }

    #[test]
    fn check_tangent_pair_tolerance_includes_exactly_the_bound() {
        // Tolerance 0.5: unit circles at distance 3 miss the expected 2 by
        // exactly 1 = 0.5 x (1 + 1), still tangent; 3.25 is not.
        let at_bound = [(1.0, 0.0, 0.0), (1.0, 3.0, 0.0)];
        let past = [(1.0, 0.0, 0.0), (1.0, 3.25, 0.0)];
        assert_eq!(check_tangent_with(&at_bound, 0.5), Ok(()));
        assert!(is_tangent(at_bound[0], at_bound[1], 0.5));
        no_solution(check_tangent_with(&past, 0.5));
        assert!(!is_tangent(past[0], past[1], 0.5));
    }

    #[test]
    fn check_tangent_r10_example_names_the_pair_and_carries_the_hint() {
        let m = no_solution(solve((-1.0, 0.0, 0.0), (2.0, 0.5, 0.0), (3.0, 0.0, 0.6667)));
        assert!(m.contains("circles 1 and 3 are not tangent"), "{m}");
        assert!(m.contains("full-precision"), "{m}");
    }

    // solve

    #[test]
    fn solve_r9_values() {
        // Spec R9: curvature 2 at (-0.5, 0), curvature 6 at (0.5, 2/3).
        let got = solve(R9_C1, R9_C2, R9_C3).unwrap();
        assert_eq!(got.len(), 2);
        assert!(close(got[0], (2.0, -0.5, 0.0), 1e-9), "{:?}", got[0]);
        assert!(close(got[1], (6.0, 0.5, 0.666_666_666_666_666_6), 1e-9), "{:?}", got[1]);
    }

    #[test]
    fn solve_every_result_is_tangent_to_all_three_inputs() {
        for result in solve(R9_C1, R9_C2, R9_C3).unwrap() {
            for given in [R9_C1, R9_C2, R9_C3] {
                assert!(gap(result, given) <= 1e-9, "{result:?} vs {given:?}");
            }
        }
    }

    #[test]
    fn solve_scaled_by_100() {
        let got = solve(
            (-100.0, 0.0, 0.0),
            (200.0, 0.005, 0.0),
            (300.0, 0.0, 0.666_666_666_666_666_6 / 100.0),
        )
        .unwrap();
        assert_eq!(got.len(), 2);
        assert!(close(got[0], (200.0, -0.005, 0.0), 1e-9), "{:?}", got[0]);
        assert!(
            close(got[1], (600.0, 0.005, 0.666_666_666_666_666_6 / 100.0), 1e-9),
            "{:?}",
            got[1]
        );
    }

    #[test]
    fn solve_pasting_a_result_back_recovers_the_third_circle() {
        // Four mutually tangent circles are symmetric: replacing the third
        // input by a result gives the third input back among the results.
        for result in solve(R9_C1, R9_C2, R9_C3).unwrap() {
            let again = solve(R9_C1, R9_C2, result).unwrap();
            assert!(again.iter().any(|&c| close(c, R9_C3, 1e-9)), "{result:?} -> {again:?}");
        }
    }

    #[test]
    fn solve_straight_line_fourth_is_omitted() {
        // Curvatures 1, 1, 4 give 6 +- 2 sqrt(9) = 12 and 0. k4 z4 = 6+3i +-
        // 2(3+i) puts the curvature-12 circle at 1 + 5i/12; the line is dropped.
        let got = solve((1.0, 0.0, 0.0), (1.0, 2.0, 0.0), (4.0, 1.0, 0.75)).unwrap();
        assert_eq!(got.len(), 1);
        assert!(close(got[0], (12.0, 1.0, 5.0 / 12.0), 1e-9), "{:?}", got[0]);
    }

    #[test]
    fn solve_zero_radicand_gives_two_centres_ordered_by_y() {
        // (-1, 2, 2): radicand 0, one curvature 3 with centres y = -+2/3.
        let got = solve((-1.0, 0.0, 0.0), (2.0, 0.5, 0.0), (2.0, -0.5, 0.0)).unwrap();
        assert_eq!(got.len(), 2);
        assert!(close(got[0], (3.0, 0.0, -2.0 / 3.0), 1e-9), "{:?}", got[0]);
        assert!(close(got[1], (3.0, 0.0, 2.0 / 3.0), 1e-9), "{:?}", got[1]);
    }

    #[test]
    fn solve_zero_radicand_pair_survives_at_scale_1e10() {
        // R26: (-1, 2, 2) with curvatures x1e10 and centres /1e10; an absolute
        // 1e-9 distance would merge the two curvature-3e10 circles.
        let got = solve((-1e10, 0.0, 0.0), (2e10, 0.5e-10, 0.0), (2e10, -0.5e-10, 0.0)).unwrap();
        assert_eq!(got.len(), 2);
        for (circle, sign) in got.iter().zip([-1.0, 1.0]) {
            assert!((circle.0 / 3e10 - 1.0).abs() < 1e-9, "{circle:?}");
            assert!(circle.1.abs() <= 1e-9 / circle.0, "{circle:?}");
            assert!((circle.2 / (sign * 2e-10 / 3.0) - 1.0).abs() < 1e-9, "{circle:?}");
        }
    }

    #[test]
    fn solve_zero_radicand_pair_survives_at_small_scale() {
        let got = solve((-1e-5, 0.0, 0.0), (2e-5, 5e4, 0.0), (2e-5, -5e4, 0.0)).unwrap();
        assert_eq!(got.len(), 2);
        assert!((got[0].0 / 1e-5 - 3.0).abs() < 1e-6 && (got[1].0 / 1e-5 - 3.0).abs() < 1e-6);
        assert!(got[0].2 < 0.0 && got[1].2 > 0.0, "{got:?}");
    }

    #[test]
    fn solve_rounding_ghost_of_a_line_is_not_a_circle() {
        // The (1, 1, 4) triple (fourth curvatures 12 and a line) with
        // curvatures x scale and centres / scale: float rounding turns the
        // line's 0 into +-1e-16 at some scales, and without the R25 threshold a
        // fake circle of radius ~1e15 passes tangency. Exactly one circle.
        for scale in [0.3, 1e-3, 1.0, 7.0, 1e10, 1e-10] {
            let t = |k: f64, x: f64, y: f64| (k * scale, x / scale, y / scale);
            let got = solve(t(1.0, 0.0, 0.0), t(1.0, 2.0, 0.0), t(4.0, 1.0, 0.75)).unwrap();
            assert_eq!(got.len(), 1, "scale={scale}");
            assert!((got[0].0 / (12.0 * scale) - 1.0).abs() < 1e-9, "scale={scale}: {:?}", got[0]);
            assert!((got[0].1 * scale - 1.0).abs() < 1e-9, "scale={scale}: {:?}", got[0]);
            assert!((got[0].2 * scale - 5.0 / 12.0).abs() < 1e-9, "scale={scale}: {:?}", got[0]);
        }
    }

    #[test]
    fn solve_line_listed_first_does_not_hide_the_circle() {
        // All-negative curvatures: descartes_fourth returns (0, -12), the line
        // first. By the k -> -k symmetry the answer is (-12, 1, 5/12).
        let got = solve((-1.0, 0.0, 0.0), (-1.0, 2.0, 0.0), (-4.0, 1.0, 0.75)).unwrap();
        assert_eq!(got.len(), 1);
        assert!(close(got[0], (-12.0, 1.0, 5.0 / 12.0), 1e-9), "{got:?}");
    }

    #[test]
    fn tangent_circles_line_threshold_includes_exactly_the_bound() {
        // Tolerance 2: for curvatures 1, 1, 4 the bound is 2 x 6 = 12 and the
        // fourth curvatures are 12 and 0, so both count as the line.
        let both = tangent_circles((1.0, 0.0, 0.0), (1.0, 2.0, 0.0), (4.0, 1.0, 0.75), 2.0);
        assert_eq!(both, Ok(vec![]));
        let some =
            tangent_circles((1.0, 0.0, 0.0), (1.0, 2.0, 0.0), (4.0, 1.0, 0.75), 1.9).unwrap();
        assert!(!some.is_empty());
    }

    #[test]
    fn solve_equal_curvature_and_y_are_ordered_by_x() {
        // (-1, 2, 2) on its side: both curvature-3 circles sit on the x axis at
        // x = -+2/3 (y exactly 0), so only x can order them.
        let got = solve((-1.0, 0.0, 0.0), (2.0, 0.0, 0.5), (2.0, 0.0, -0.5)).unwrap();
        assert_eq!(got.len(), 2);
        assert!(close(got[0], (3.0, -2.0 / 3.0, 0.0), 1e-9), "{:?}", got[0]);
        assert!(close(got[1], (3.0, 2.0 / 3.0, 0.0), 1e-9), "{:?}", got[1]);
    }

    #[test]
    fn solve_equal_curvatures_are_ordered_by_y_not_x() {
        // (-1, 2, 2) rotated by the 3-4-5 angle: the curvature-3 centres are
        // +-(0.4, -8/15); the one with the smaller y has the larger x.
        let got = solve((-1.0, 0.0, 0.0), (2.0, 0.4, 0.3), (2.0, -0.4, -0.3)).unwrap();
        assert_eq!(got.len(), 2);
        assert!(close(got[0], (3.0, 0.4, -8.0 / 15.0), 1e-9), "{:?}", got[0]);
        assert!(close(got[1], (3.0, -0.4, 8.0 / 15.0), 1e-9), "{:?}", got[1]);
    }

    #[test]
    fn solve_results_are_ordered_by_curvature() {
        let got = solve(R9_C1, R9_C2, R9_C3).unwrap();
        assert!(got[0].0 < got[1].0);
    }

    #[test]
    fn circle_order_sorts_by_curvature_then_y_then_x() {
        let mut v = vec![
            (3.0, 2.0, 1.0),
            (3.0, 1.0, 1.0),
            (3.0, 9.0, 0.5),
            (2.0, 9.0, 9.0),
            (3.0, 1.0, -0.0),
            (3.0, 1.0, 0.0),
        ];
        v.sort_by(circle_order);
        // -0.0 and 0.0 tie on y, then the stable order of the ties holds.
        assert_eq!(
            v,
            [
                (2.0, 9.0, 9.0),
                (3.0, 1.0, -0.0),
                (3.0, 1.0, 0.0),
                (3.0, 9.0, 0.5),
                (3.0, 1.0, 1.0),
                (3.0, 2.0, 1.0)
            ]
        );
    }

    #[test]
    fn solve_any_three_circles_of_a_root_give_the_fourth() {
        for root in ALL_ROOTS {
            let circles = root_centres(root).unwrap();
            for omitted in 0..4 {
                let triple: Vec<Circle> = circles
                    .iter()
                    .enumerate()
                    .filter(|&(i, _)| i != omitted)
                    .map(|(_, &c)| c)
                    .collect();
                let got = solve(triple[0], triple[1], triple[2]).unwrap();
                assert!(
                    got.iter().any(|&c| close(c, circles[omitted], 1e-7)),
                    "{root:?} omitted {omitted}: {got:?}"
                );
            }
        }
    }

    #[test]
    fn solve_rejects_non_tangent_input_before_solving() {
        let m = no_solution(solve(R9_C1, R9_C2, (3.0, 0.0, 0.6667)));
        assert!(m.contains("circles 1 and 3 are not tangent"), "{m}");
    }

    #[test]
    fn solve_zero_curvature_is_bad_input() {
        let m = bad_input(solve((0.0, 0.0, 0.0), R9_C2, R9_C3));
        assert!(m.contains("zero curvature"), "{m}");
    }

    #[test]
    fn solve_ill_conditioned_input_with_no_passing_candidate_is_no_solution() {
        // The collinear (-2, 3, 6) triple with y moved by 1e-8 passes the input
        // check, but both curvature-7 solutions miss tangency by about 7x the
        // tolerance (spec, Known limits), so nothing survives.
        let triple = [(-2.0, 0.0, 0.0), (3.0, 1.0 / 6.0, 0.0), (6.0, -1.0 / 3.0, 1e-8)];
        assert_eq!(check_tangent(&triple), Ok(()));
        let m = no_solution(solve(triple[0], triple[1], triple[2]));
        assert!(m.starts_with("solve((-2, 0, 0), (3, "), "{m}");
        assert!(m.ends_with("no circle is tangent to all three"), "{m}");
    }

    #[test]
    fn solve_is_repeatable() {
        assert_eq!(solve(R9_C1, R9_C2, R9_C3), solve(R9_C1, R9_C2, R9_C3));
    }

    #[test]
    fn tangent_circles_propagates_the_descartes_fourth_error() {
        // Three mutually external unit-ish radicand failures: k1k2+k2k3+k3k1 < 0.
        let m = no_solution(tangent_circles(
            (1.0, 0.0, 0.0),
            (1.0, 2.0, 0.0),
            (-3.0, 0.0, 0.0),
            TANGENT_TOL,
        ));
        assert!(m.contains("descartes_fourth(1, 1, -3)"), "{m}");
    }

    // same_circle: distinct when curvatures differ by more than tol x |k| or
    // centres by more than tol x |1/k|, at every scale (R26)

    const SCALES: [f64; 4] = [1e-10, 0.5, 3.0, 1e10];

    #[test]
    fn same_circle_identical_circles_are_the_same() {
        for k in SCALES {
            assert!(same_circle((k, 1.0, 2.0), (k, 1.0, 2.0), TANGENT_TOL), "k={k}");
        }
    }

    #[test]
    fn same_circle_curvature_gap_is_relative() {
        for k in SCALES {
            assert!(
                same_circle((k, 0.0, 0.0), (k * (1.0 + 0.5e-9), 0.0, 0.0), TANGENT_TOL),
                "k={k}"
            );
            assert!(
                !same_circle((k, 0.0, 0.0), (k * (1.0 + 2e-9), 0.0, 0.0), TANGENT_TOL),
                "k={k}"
            );
        }
    }

    #[test]
    fn same_circle_centre_gap_is_relative_on_each_axis() {
        for k in SCALES {
            let (near, far) = (0.5e-9 / k, 2e-9 / k);
            for (dx, dy) in [(near, 0.0), (0.0, near)] {
                assert!(same_circle((k, dx, dy), (k, 0.0, 0.0), TANGENT_TOL), "k={k}");
            }
            for (dx, dy) in [(far, 0.0), (0.0, far)] {
                assert!(!same_circle((k, dx, dy), (k, 0.0, 0.0), TANGENT_TOL), "k={k}");
            }
        }
    }

    #[test]
    fn same_circle_centre_distance_is_euclidean() {
        // Each coordinate is off by 0.8 of the bound, the distance by 1.13.
        for k in SCALES {
            let shift = 0.8e-9 / k;
            assert!(!same_circle((k, shift, shift), (k, 0.0, 0.0), TANGENT_TOL), "k={k}");
        }
    }

    #[test]
    fn same_circle_needs_both_conditions() {
        assert!(!same_circle((3.0, 0.0, 0.0), (6.0, 0.0, 0.0), TANGENT_TOL));
        assert!(!same_circle((3.0, 0.0, 0.0), (3.0, 1.0, 0.0), TANGENT_TOL));
    }

    #[test]
    fn same_circle_bounds_are_inclusive() {
        // Tolerance 0.5: |3 - 2| = 1 = 0.5 x 2 and a centre shift of 0.25 =
        // 0.5 x |1/2|, both exact in binary.
        assert!(same_circle((3.0, 0.0, 0.0), (2.0, 0.0, 0.0), 0.5));
        assert!(!same_circle((3.5, 0.0, 0.0), (2.0, 0.0, 0.0), 0.5));
        assert!(same_circle((2.0, 0.25, 0.0), (2.0, 0.0, 0.0), 0.5));
        assert!(!same_circle((2.0, 0.3125, 0.0), (2.0, 0.0, 0.0), 0.5));
    }

    #[test]
    fn same_circle_measures_against_the_second_circle() {
        // The bounds come from b: a curvature gap of 1 is within 0.4 x 3 but
        // not within 0.4 x 2, and a centre gap of 0.4 is within 1 x |1/2| but
        // not within 1 x |1/3|.
        assert!(same_circle((2.0, 0.0, 0.0), (3.0, 0.0, 0.0), 0.4));
        assert!(!same_circle((3.0, 0.0, 0.0), (2.0, 0.0, 0.0), 0.4));
        assert!(same_circle((3.0, 0.4, 0.0), (2.0, 0.0, 0.0), 1.0));
        assert!(!same_circle((2.0, 0.4, 0.0), (3.0, 0.0, 0.0), 1.0));
    }

    // visible

    #[test]
    fn visible_r2_circle_count() {
        assert_eq!(visible(ROOT_A, 30).unwrap().len(), 38);
    }

    #[test]
    fn visible_count_and_curvatures_match_pack() {
        for root in ALL_ROOTS {
            for n in [0, 1, 2, 3, 10, 30, 100, 300] {
                let (count, bitmap) = pack(root, n).unwrap();
                let got = visible(root, n).unwrap();
                assert_eq!(got.len() as i64, count, "{root:?} n={n}");
                let mut ks: Vec<i64> = got.iter().map(|c| c.0.round() as i64).collect();
                ks.sort_unstable();
                ks.dedup();
                assert_eq!(ks, distinct(&bitmap), "{root:?} n={n}");
            }
        }
    }

    #[test]
    fn visible_pinned_counts() {
        for (root, n, count, _) in PINNED {
            if n <= 1000 {
                assert_eq!(visible(root, n).unwrap().len() as i64, count, "{root:?} n={n}");
            }
        }
    }

    #[test]
    fn visible_only_positive_circles() {
        for root in ALL_ROOTS {
            assert!(visible(root, 100).unwrap().iter().all(|c| c.0 > 0.0), "{root:?}");
        }
    }

    #[test]
    fn visible_hand_derived_small_case() {
        // At limit 3 the (-1,2,2,3) packing shows the root's own 2, 2, 3 and the
        // mirror curvature-3 circle: centres (+-1/2, 0) and (0, +-2/3).
        let got = sorted_circles(visible(ROOT_A, 3).unwrap());
        let want =
            [(2.0, -0.5, 0.0), (2.0, 0.5, 0.0), (3.0, 0.0, -2.0 / 3.0), (3.0, 0.0, 2.0 / 3.0)];
        assert_eq!(got.len(), 4);
        for (g, w) in got.iter().zip(want) {
            assert!(close(*g, w, 1e-12), "{g:?} != {w:?}");
        }
    }

    #[test]
    fn visible_limit_edges() {
        assert_eq!(visible(ROOT_A, 0), Ok(vec![]));
        assert_eq!(visible(ROOT_A, 1), Ok(vec![]));
        assert_eq!(visible(ROOT_D, 10), Ok(vec![]));
        let two: Vec<f64> = visible(ROOT_A, 2).unwrap().iter().map(|c| c.0).collect();
        assert_eq!(two, [2.0, 2.0]);
    }

    #[test]
    fn visible_limit_checks_name_visible_and_limit() {
        assert_eq!(bad_input(visible(ROOT_A, -1)), "visible(limit=-1): limit must not be negative");
        assert_eq!(
            bad_input(visible(ROOT_A, N_MAX + 1)),
            "visible(limit=100000001): limit must be at most 100000000"
        );
    }

    #[test]
    fn visible_invalid_roots_are_rejected_naming_visible() {
        for (root, what) in [
            ([-1, 2, 3, 6], "not reduced"),
            ([2, -1, 2, 3], "not sorted"),
            ([-1, 2, 2, 4], "not a Descartes quadruple"),
            ([0, 1, 1, 4], "exactly one negative"),
        ] {
            let m = bad_input(visible(root, 100));
            assert!(m.starts_with("visible(root="), "{m}");
            assert!(m.contains(what), "{m}");
        }
    }

    /// The centres are checked by geometry alone, never by the code under test:
    /// no two circles overlap, all lie inside the bounding circle, and every
    /// circle touches at least three others (its parents are never larger).
    fn assert_packing_geometry(root: Root, n: i64) {
        let circles = visible(root, n).unwrap();
        let bounding = (root[0] as f64, 0.0, 0.0);
        let radius = |c: Circle| (1.0 / c.0).abs();
        let dist = |a: Circle, b: Circle| ((a.1 - b.1).powi(2) + (a.2 - b.2).powi(2)).sqrt();
        for (i, &a) in circles.iter().enumerate() {
            assert!(
                dist(a, bounding) + radius(a) <= radius(bounding) * (1.0 + 1e-9),
                "{root:?} {a:?} outside"
            );
            let mut touching = 0;
            for (j, &b) in circles.iter().enumerate().chain([(usize::MAX, &bounding)]) {
                if i == j {
                    continue;
                }
                let slack = 1e-9 * (radius(a) + radius(b));
                if gap(a, b) <= slack {
                    touching += 1;
                }
                if j != usize::MAX {
                    assert!(
                        dist(a, b) >= radius(a) + radius(b) - slack,
                        "{root:?} {a:?} overlaps {b:?}"
                    );
                }
            }
            assert!(touching >= 3, "{root:?} n={n}: {a:?} touches {touching}");
        }
    }

    #[test]
    fn visible_centres_form_a_valid_packing() {
        for root in ALL_ROOTS {
            assert_packing_geometry(root, 100);
        }
        assert_packing_geometry(ROOT_A, 1000);
    }

    // As for pack: no valid quadruple can fail the growth test, so it is tested
    // on roots that break the Descartes relation, with the placement supplied
    // directly and the walk budgeted so a missing guard fails within the 10,000-step
    // budget (the weakened guard runs past the budget on (-1, 1, 3, 5)).
    #[test]
    fn walk_centres_terminates_when_the_root_invariant_is_broken() {
        for root in [[-1, 1, 1, 1], [-1, 1, 3, 5], [-1, 2, 2, 2]] {
            let mut calls = 0;
            let mut found = Vec::new();
            walk_centres(root, root.map(|k| (k as f64, 0.0, 0.0)), 30, &mut |c| {
                calls += 1;
                assert!(calls < 10_000, "visible walk did not terminate for {root:?}");
                found.push(c);
            });
            assert!(found.iter().all(|c| 0.0 <= c.0 && c.0 <= 30.0), "{root:?}");
        }
    }

    #[test]
    fn walk_centres_reports_each_root_circle_but_the_bounding_one() {
        let mut found = Vec::new();
        let placed = [(-1.0, 0.0, 0.0), (2.0, 0.5, 0.0), (2.0, -0.5, 0.0), (3.0, 0.0, 2.0 / 3.0)];
        walk_centres(ROOT_A, placed, 2, &mut |c| found.push(c));
        assert_eq!(&found, &[placed[1], placed[2]]);
    }

    #[test]
    fn visible_is_repeatable_and_independent_of_earlier_runs() {
        assert_eq!(visible(ROOT_A, 100), visible(ROOT_A, 100));
        let _ = visible(ROOT_A, 1000);
        assert_eq!(visible(ROOT_A, 30).unwrap().len(), 38);
    }

    #[test]
    fn child_centre_is_the_reflection_of_the_replaced_circle() {
        // (-1, 2, 2, 3) at (0,0), (1/2,0), (-1/2,0), (0,2/3): reflecting the
        // curvature-3 circle gives k' = 2(-1+2+2) - 3 = 3 at
        // (2 sum(k z) of the others - 3 z4) / 3 = (0, -2/3).
        let zs = [(0.0, 0.0), (0.5, 0.0), (-0.5, 0.0), (0.0, 2.0 / 3.0)];
        let (ks, centres, replaced) = child([-1, 2, 2, 3], zs, 3, 3);
        assert_eq!((ks, replaced), ([-1, 2, 2, 3], 3));
        assert!(
            close((3.0, centres[3].0, centres[3].1), (3.0, 0.0, -2.0 / 3.0), 1e-12),
            "{centres:?}"
        );
        assert_eq!(&centres[..3], &zs[..3]);
        // Replacing the curvature-2 circle at (1/2, 0): k' = 2(-1+2+3) - 2 = 6;
        // sum of k z over the others = 2 (-1/2) + 3 (2i/3) = -1 + 2i, so
        // z' = (2 (-1 + 2i) - 2 (1/2)) / 6 = (-3 + 4i) / 6 = (-1/2, 2/3).
        let (ks, centres, replaced) = child([-1, 2, 2, 3], zs, 1, 6);
        assert_eq!((ks, replaced), ([-1, 6, 2, 3], 1));
        assert!(
            close((6.0, centres[1].0, centres[1].1), (6.0, -0.5, 2.0 / 3.0), 1e-12),
            "{centres:?}"
        );
    }

    // render

    /// Bit of each dot by (column, row) in a cell, written out independently of
    /// the renderer's table.
    const BIT_TO_DOT: [(u32, i64, i64); 8] = [
        (0x01, 0, 0),
        (0x02, 0, 1),
        (0x04, 0, 2),
        (0x40, 0, 3),
        (0x08, 1, 0),
        (0x10, 1, 1),
        (0x20, 1, 2),
        (0x80, 1, 3),
    ];

    /// Decode braille lines back to the set of lit (x, y) dots, y down.
    fn lit_dots(lines: &[String]) -> std::collections::BTreeSet<(i64, i64)> {
        let mut dots = std::collections::BTreeSet::new();
        for (row, line) in lines.iter().enumerate() {
            for (col, ch) in line.chars().enumerate() {
                let bits = ch as u32 - 0x2800;
                for (bit, dx, dy) in BIT_TO_DOT {
                    if bits & bit != 0 {
                        dots.insert((2 * col as i64 + dx, 4 * row as i64 + dy));
                    }
                }
            }
        }
        dots
    }

    fn dots_of(
        circles: &[Circle],
        width: usize,
        height: usize,
    ) -> std::collections::BTreeSet<(i64, i64)> {
        lit_dots(&render(circles, width, height).unwrap())
    }

    fn extent(dots: &std::collections::BTreeSet<(i64, i64)>) -> ((i64, i64), (i64, i64)) {
        let xs = dots.iter().map(|d| d.0);
        let ys = dots.iter().map(|d| d.1);
        (
            (xs.clone().min().unwrap(), xs.max().unwrap()),
            (ys.clone().min().unwrap(), ys.max().unwrap()),
        )
    }

    const R9_CIRCLES: [Circle; 5] = [
        (-1.0, 0.0, 0.0),
        (2.0, 0.5, 0.0),
        (3.0, 0.0, 0.666_666_666_666_666_6),
        (2.0, -0.5, 0.0),
        (6.0, 0.5, 0.666_666_666_666_666_6),
    ];

    #[test]
    fn render_empty_list_is_an_all_blank_grid() {
        // R11: exactly 24 lines of 60 blank braille cells.
        let lines = render(&[], 60, 24).unwrap();
        assert_eq!(lines.len(), 24);
        assert!(lines.iter().all(|l| *l == BLANK.to_string().repeat(60)));
    }

    #[test]
    fn render_shape_and_alphabet() {
        for (width, height) in [(1, 1), (2, 1), (1, 3), (7, 5), (60, 24), (100, 10)] {
            let lines = render(&[BOUNDING, (2.0, 0.5, 0.0)], width, height).unwrap();
            assert_eq!(lines.len(), height);
            for line in &lines {
                assert_eq!(line.chars().count(), width);
                assert!(line.chars().all(|c| ('\u{2800}'..='\u{28FF}').contains(&c)));
            }
        }
    }

    #[test]
    fn render_single_circle_and_r9_are_not_blank_at_60_by_24() {
        for circles in [&[UNIT][..], &R9_CIRCLES[..]] {
            let lines = render(circles, 60, 24).unwrap();
            assert_eq!(lines.len(), 24);
            assert!(lines.iter().all(|l| l.chars().count() == 60));
            assert!(lines.iter().any(|l| l.chars().any(|c| c != BLANK)));
        }
    }

    #[test]
    fn render_one_by_one_lights_a_dot() {
        assert_ne!(render(&[UNIT], 1, 1).unwrap(), [BLANK.to_string()]);
    }

    #[test]
    fn render_canvas_below_one_by_one_is_bad_input() {
        for (width, height) in [(0, 24), (60, 0), (0, 0)] {
            let m = bad_input(render(&[UNIT], width, height));
            assert_eq!(
                m,
                format!("render: canvas {width}x{height} is too small, need at least 1x1")
            );
        }
    }

    #[test]
    fn render_size_error_precedes_the_empty_list() {
        bad_input(render(&[], 0, 5));
        bad_input(render(&[], 5, 0));
    }

    #[test]
    fn render_non_finite_or_zero_circle_is_bad_input() {
        for bad in [
            (f64::NAN, 0.0, 0.0),
            (f64::INFINITY, 0.0, 0.0),
            (1.0, f64::NAN, 0.0),
            (1.0, 0.0, f64::INFINITY),
            (0.0, 0.0, 0.0),
        ] {
            let m = bad_input(render(&[BOUNDING, bad], 60, 24));
            assert!(m.starts_with("render: circle 2 has"), "{m}");
        }
    }

    #[test]
    fn render_bad_circle_message_names_its_number_and_values() {
        for (circles, number) in [
            ([(f64::NAN, 0.0, 0.0), BOUNDING, UNIT], 1),
            ([BOUNDING, (1.0, f64::INFINITY, 0.0), UNIT], 2),
            ([BOUNDING, UNIT, (0.0, 0.0, 0.0)], 3),
        ] {
            let m = bad_input(render(&circles, 60, 24));
            assert!(m.starts_with(&format!("render: circle {number} ")), "{m}");
            assert!(m.contains("(curvature "), "{m}");
        }
    }

    #[test]
    fn render_bounding_box_overflow_is_bad_input() {
        let m = bad_input(render(&[(1.0, 1.7e308, 0.0), (1.0, -1.7e308, 0.0)], 60, 24));
        assert!(m.contains("bounding box") && m.contains("60x24"), "{m}");
    }

    #[test]
    fn render_scale_overflow_is_bad_input() {
        bad_input(render(&[(1e308, 0.0, 0.0)], 60, 24));
    }

    #[test]
    fn render_single_circle_hand_derived_extremes() {
        // 120 x 96 dots: scale 47 dots per unit, centre (60, 48), radius 47.
        let dots = dots_of(&[UNIT], 60, 24);
        for dot in [(13, 48), (107, 48), (60, 1), (60, 95)] {
            assert!(dots.contains(&dot), "{dot:?}");
        }
        assert_eq!(extent(&dots), ((13, 107), (1, 95)));
    }

    #[test]
    fn render_single_circle_fills_width_when_width_binds() {
        // 10 x 24 cells = 20 x 96 dots: scale min(18/2, 94/2) = 9, left 0.5,
        // top 38.5, so centre (10, 48) and radius 9.
        assert_eq!(extent(&dots_of(&[UNIT], 10, 24)), ((1, 19), (39, 57)));
    }

    #[test]
    fn render_wide_pair_hand_derived() {
        // Two unit circles at x = 0 and 2: box 4 x 2, width binds at 29.5 dots
        // per unit; extents 119 x 60 dots, the 2 : 1 of the box.
        let dots = dots_of(&[(1.0, 0.0, 0.0), (1.0, 2.0, 0.0)], 60, 24);
        assert_eq!(extent(&dots), ((0, 119), (18, 78)));
    }

    #[test]
    fn render_three_circle_extremes_hand_derived() {
        let dots = dots_of(&[BOUNDING, (2.0, 0.5, 0.0), (2.0, -0.5, 0.0)], 60, 24);
        for dot in [
            (59, 48),
            (107, 48),
            (83, 24),
            (83, 72), // centre (83, 48), radius 24
            (12, 48),
            (60, 48),
            (36, 24),
            (36, 72), // centre (36, 48), radius 24
        ] {
            assert!(dots.contains(&dot), "{dot:?}");
        }
    }

    #[test]
    fn render_every_lit_dot_is_on_some_circle() {
        // Unrounded geometry of R9 at 60 x 24: bounding box x -1..1 and y -1..1
        // (the bounding circle), scale 47, centre (60, 48), written out here.
        let geometry: Vec<(f64, f64, f64)> = R9_CIRCLES
            .iter()
            .map(|&(k, x, y)| (60.0 + 47.0 * x, 48.0 - 47.0 * y, 47.0 / k.abs()))
            .collect();
        for (x, y) in dots_of(&R9_CIRCLES, 60, 24) {
            let nearest = geometry
                .iter()
                .map(|&(cx, cy, r)| {
                    (((x as f64 - cx).powi(2) + (y as f64 - cy).powi(2)).sqrt() - r).abs()
                })
                .fold(f64::INFINITY, f64::min);
            assert!(nearest <= 1.5, "dot ({x}, {y}) is {nearest} from every circle");
        }
    }

    #[test]
    fn render_extreme_dots_of_every_circle_are_lit() {
        let dots = dots_of(&R9_CIRCLES, 60, 24);
        for &(k, x, y) in &R9_CIRCLES {
            // left 12.5 and top 0.5 put the centre at floor(60 + 47 x), floor(48 - 47 y).
            let cx = (60.0 + 47.0 * x).floor() as i64;
            let cy = (48.0 - 47.0 * y).floor() as i64;
            let r = (47.0 / k.abs() + 0.5).floor() as i64;
            for dot in [(cx - r, cy), (cx + r, cy), (cx, cy - r), (cx, cy + r)] {
                assert!(dots.contains(&dot), "{dot:?} of {k}");
            }
        }
    }

    #[test]
    fn render_orientation_y_up_is_rows_up() {
        let base = dots_of(&[BOUNDING], 60, 24);
        let above: Vec<_> =
            dots_of(&[BOUNDING, (10.0, 0.0, 0.5)], 60, 24).difference(&base).copied().collect();
        assert!(!above.is_empty() && above.iter().all(|d| d.1 < 48), "{above:?}");
        let below: Vec<_> =
            dots_of(&[BOUNDING, (10.0, 0.0, -0.5)], 60, 24).difference(&base).copied().collect();
        assert!(!below.is_empty() && below.iter().all(|d| d.1 >= 48), "{below:?}");
    }

    #[test]
    fn render_orientation_x_right_is_columns_right() {
        let base = dots_of(&[BOUNDING], 60, 24);
        let right: Vec<_> =
            dots_of(&[BOUNDING, (10.0, 0.5, 0.0)], 60, 24).difference(&base).copied().collect();
        assert!(!right.is_empty() && right.iter().all(|d| d.0 > 60), "{right:?}");
        let left: Vec<_> =
            dots_of(&[BOUNDING, (10.0, -0.5, 0.0)], 60, 24).difference(&base).copied().collect();
        assert!(!left.is_empty() && left.iter().all(|d| d.0 < 60), "{left:?}");
    }

    #[test]
    fn render_inner_circle_touches_the_bounding_circles_right_edge() {
        let both = dots_of(&[BOUNDING, (2.0, 0.5, 0.0)], 60, 24);
        let inner: Vec<_> = both.difference(&dots_of(&[BOUNDING], 60, 24)).copied().collect();
        assert!(!inner.is_empty() && inner.iter().all(|d| d.0 >= 59), "{inner:?}");
        assert!(both.contains(&(107, 48)));
        assert_eq!(extent(&both).0.1, 107);
    }

    #[test]
    fn render_zero_dot_radius_lights_exactly_one_dot() {
        // Radius 1e-9 is 0 dots at 47 dots per unit; its centre is (83, 48).
        let extra: Vec<_> = dots_of(&[BOUNDING, (1e9, 0.5, 0.0)], 60, 24)
            .difference(&dots_of(&[BOUNDING], 60, 24))
            .copied()
            .collect();
        assert_eq!(extra, [(83, 48)]);
    }

    #[test]
    fn render_width_binding_fractional_scale_exact() {
        // Box 2.5 x 5 on 4 x 4 cells (8 x 16 dots): width gives 6 / 2.5 = 2.4,
        // height 14 / 5 = 2.8, so width binds at 2.4; left 0.5, top 1.5. Circle
        // 1: centre (3, 11), radius 2; circle 2: centre (4, 4), radius 2.
        let dots = dots_of(&[UNIT, (1.0, 0.5, 3.0)], 4, 4);
        for dot in [(1, 11), (5, 11), (3, 9), (3, 13), (2, 4), (6, 4), (4, 2), (4, 6)] {
            assert!(dots.contains(&dot), "{dot:?}");
        }
        assert_eq!(extent(&dots), ((1, 6), (2, 13)));
    }

    #[test]
    fn render_height_binding_fractional_scale_exact() {
        // Same circles on 3 x 1 cells (6 x 4 dots): width 4 / 2.5 = 1.6, height
        // 2 / 5 = 0.4, so height binds; left 2, top 0.5; both radii round to 0
        // dots with centres (2, 2) and (3, 1).
        let want: std::collections::BTreeSet<(i64, i64)> = [(2, 2), (3, 1)].into();
        assert_eq!(dots_of(&[UNIT, (1.0, 0.5, 3.0)], 3, 1), want);
    }

    #[test]
    fn render_off_grid_dots_are_not_plotted_and_do_not_wrap() {
        // A 1-cell canvas is 2 x 4 dots and the bounding circle overflows it.
        let lines = render(&[BOUNDING, (2.0, 0.5, 0.0)], 1, 1).unwrap();
        assert_eq!((lines.len(), lines[0].chars().count()), (1, 1));
    }

    #[test]
    fn render_does_not_mutate_input_and_is_order_independent() {
        let circles = R9_CIRCLES;
        let first = render(&circles, 60, 24).unwrap();
        assert_eq!(circles, R9_CIRCLES);
        assert_eq!(render(&circles, 60, 24).unwrap(), first);
        let mut reversed = R9_CIRCLES;
        reversed.reverse();
        assert_eq!(render(&reversed, 60, 24).unwrap(), first);
    }

    #[test]
    fn braille_maps_bits_onto_the_block() {
        assert_eq!(braille(0), BLANK);
        assert_eq!(braille(0xFF), '\u{28FF}');
        assert_eq!(braille(0x01), '\u{2801}');
    }

    // midpoint_circle: hand-derived from the algorithm (x = r, y = 0,
    // d = 1 - r; plot the eight symmetric points; y += 1; d <= 0 -> d += 2y+1,
    // else x -= 1 and d += 2(y-x)+1; while x >= y)

    fn flipped(base: &[(i64, i64)]) -> std::collections::BTreeSet<(i64, i64)> {
        base.iter().flat_map(|&(x, y)| [(x, y), (-x, y), (x, -y), (-x, -y)]).collect()
    }

    fn circle_dots(cx: i64, cy: i64, r: i64) -> std::collections::BTreeSet<(i64, i64)> {
        midpoint_circle(cx, cy, r).into_iter().collect()
    }

    #[test]
    fn midpoint_circle_radius_zero_is_the_centre_dot() {
        assert_eq!(circle_dots(0, 0, 0), [(0, 0)].into());
    }

    #[test]
    fn midpoint_circle_radius_one_is_the_eight_neighbours() {
        // d = 0 at the start: the <= 0 branch keeps the diagonal (1, 1).
        assert_eq!(circle_dots(0, 0, 1), flipped(&[(1, 0), (0, 1), (1, 1)]));
    }

    #[test]
    fn midpoint_circle_radius_two() {
        assert_eq!(circle_dots(0, 0, 2), flipped(&[(2, 0), (0, 2), (2, 1), (1, 2)]));
    }

    #[test]
    fn midpoint_circle_radius_three_includes_the_diagonal() {
        // x = y = 2 is plotted because the loop runs while x >= y.
        assert_eq!(circle_dots(0, 0, 3), flipped(&[(3, 0), (0, 3), (3, 1), (1, 3), (2, 2)]));
    }

    /// Independent of the incremental decision variable: in the first octant
    /// the algorithm keeps x while the midpoint (x - 1/2, y) lies within
    /// `r^2 + 1/4` of the origin, i.e. x is the largest integer with
    /// `(2x - 1)^2 + 4y^2 <= 4r^2 + 1`; the octant ends when x < y.
    fn octant_oracle(r: i64) -> std::collections::BTreeSet<(i64, i64)> {
        let mut base = Vec::new();
        for y in 0.. {
            let x = (0..=r)
                .rev()
                .find(|&x| (2 * x - 1).pow(2) + 4 * y * y <= 4 * r * r + 1)
                .unwrap_or(-1);
            if x < y {
                break;
            }
            base.extend([(x, y), (y, x)]);
        }
        flipped(&base)
    }

    #[test]
    fn midpoint_circle_matches_the_integer_octant_oracle() {
        // Radii 8, 12, 13, 15, 17 are where a wrong decision update first
        // changes the picture.
        for r in 0..=60 {
            assert_eq!(circle_dots(0, 0, r), octant_oracle(r), "r={r}");
        }
    }

    #[test]
    fn midpoint_circle_is_translated_by_its_centre() {
        let moved: std::collections::BTreeSet<(i64, i64)> =
            circle_dots(0, 0, 3).into_iter().map(|(x, y)| (x + 10, y - 20)).collect();
        assert_eq!(circle_dots(10, -20, 3), moved);
    }

    #[test]
    fn midpoint_circle_radius_five_matches_the_hand_trace() {
        // d = -4, -1, 4 plot (5,0), (5,1), (5,2); then x drops to 4 and (4,3) is
        // plotted; x drops to 3 < y = 4 and the loop ends. The swapped points
        // (0,5), (1,5), (2,5), (3,4) are plotted alongside.
        let want = flipped(&[(5, 0), (0, 5), (5, 1), (1, 5), (5, 2), (2, 5), (4, 3), (3, 4)]);
        assert_eq!(circle_dots(0, 0, 5), want);
    }

    // plot

    fn lit_after(
        width: usize,
        height: usize,
        dots: &[(i64, i64)],
    ) -> std::collections::BTreeSet<(i64, i64)> {
        let mut cells = vec![vec![0u8; width]; height];
        for &(x, y) in dots {
            plot(&mut cells, x, y, width, height);
        }
        let lines: Vec<String> =
            cells.iter().map(|row| row.iter().map(|&b| braille(b)).collect()).collect();
        lit_dots(&lines)
    }

    #[test]
    fn plot_in_grid_corners_are_lit() {
        for (width, height) in [(3usize, 2usize), (1, 1), (5, 4)] {
            let (w, h) = (2 * width as i64, 4 * height as i64);
            for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)] {
                assert_eq!(
                    lit_after(width, height, &[corner]),
                    [corner].into(),
                    "{width}x{height}"
                );
            }
        }
    }

    #[test]
    fn plot_off_grid_dots_change_nothing_and_do_not_wrap() {
        for (width, height) in [(3usize, 2usize), (1, 1), (5, 4)] {
            let (w, h) = (2 * width as i64, 4 * height as i64);
            for dot in [
                (-1, 0),
                (w, 0),
                (0, -1),
                (0, h),
                (-1, -1),
                (w, h),
                (w + 1, 1),
                (1, h + 1),
                (-w, 1),
                (1, -h),
            ] {
                assert!(lit_after(width, height, &[dot]).is_empty(), "{width}x{height} {dot:?}");
            }
        }
    }

    #[test]
    fn plot_dot_bits_land_in_the_right_cell() {
        assert_eq!(lit_after(3, 2, &[(3, 5)]), [(3, 5)].into());
        let mut cells = vec![vec![0u8; 3]; 2];
        plot(&mut cells, 3, 5, 3, 2);
        assert_eq!(cells[1][1], 0x10);
    }

    #[test]
    fn plot_twice_and_with_others_accumulates() {
        assert_eq!(lit_after(2, 1, &[(0, 0), (1, 0), (0, 0)]), [(0, 0), (1, 0)].into());
    }

    // svg

    fn lines_of(svg: &str) -> Vec<&str> {
        svg.lines().collect()
    }

    #[test]
    fn svg_packing_default_root_k3_counts() {
        let svg = svg_packing([-1, 2, 2, 3], 3).unwrap();
        assert_eq!(svg.matches("<circle ").count(), 3329);
        assert_eq!(svg.matches("<text ").count(), 26);
    }

    #[test]
    fn svg_packing_first_lines_exact() {
        let svg = svg_packing([-1, 2, 2, 3], 3).unwrap();
        let lines = lines_of(&svg);
        assert_eq!(lines[0], r#"<?xml version="1.0" encoding="UTF-8"?>"#);
        assert_eq!(lines[1], r#"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">"#);
        assert_eq!(lines[2], r#"<rect width="1000" height="1000" fill="white"/>"#);
        assert_eq!(
            lines[3],
            r#"<circle cx="500.000" cy="500.000" r="500.000" fill="none" stroke="black" stroke-width="1.000"/>"#
        );
        assert!(svg.ends_with("</svg>\n"));
        assert_eq!(lines[lines.len() - 1], "</svg>");
    }

    #[test]
    fn svg_packing_first_labelled_circle_exact() {
        let svg = svg_packing([-1, 2, 2, 3], 3).unwrap();
        let lines = lines_of(&svg);
        assert_eq!(
            lines[4],
            r#"<circle cx="750.000" cy="500.000" r="250.000" fill="none" stroke="black" stroke-width="1.000"/>"#
        );
        assert_eq!(
            lines[5],
            r#"<text x="750.000" y="500.000" font-size="48.000" text-anchor="middle" dominant-baseline="central">2</text>"#
        );
    }

    #[test]
    fn svg_packing_k1_limit_is_10_pow_k() {
        let svg = svg_packing([-1, 2, 2, 3], 1).unwrap();
        assert_eq!(svg.matches("<circle ").count(), 9);
    }

    #[test]
    fn svg_packing_rejects_invalid_root() {
        assert_eq!(svg_packing([1, 2, 3, 4], 3).unwrap_err().exit_code(), 2);
    }

    #[test]
    fn svg_fmt3_negative_zero() {
        assert_eq!(fmt3(-0.0001), "0.000");
        assert_eq!(fmt3(-0.0), "0.000");
        assert_eq!(fmt3(1.5), "1.500");
        assert_eq!(fmt3(-1.0005e-3), "-0.001");
    }

    #[test]
    fn svg_solve_counts_and_styles() {
        let givens = [(-1.0, 0.0, 0.0), (2.0, 0.5, 0.0), (3.0, 0.0, 2.0 / 3.0)];
        let sols = solve(givens[0], givens[1], givens[2]).unwrap();
        assert_eq!(sols.len(), 2);
        let svg = svg_solve(&givens, &sols);
        assert_eq!(svg.matches("<circle ").count(), 5);
        assert_eq!(svg.matches(r##"stroke="black""##).count(), 3);
        assert_eq!(svg.matches(r##"stroke="#c00" stroke-dasharray="6 4""##).count(), 2);
        assert_eq!(svg.matches("<text ").count(), 0);
        assert!(svg.ends_with("</svg>\n"));
    }

    #[test]
    fn svg_solve_enclosing_solution_inside_view() {
        let placed = root_centres([-1, 2, 2, 3]).unwrap();
        let givens = &placed[1..];
        let sols = solve(givens[0], givens[1], givens[2]).unwrap();
        assert!(sols.iter().any(|c| c.0 < 0.0));
        let svg = svg_solve(givens, &sols);
        let mut n = 0;
        for line in svg.lines().filter(|l| l.starts_with("<circle ")) {
            let attr = |name: &str| -> f64 {
                let key = format!(" {name}=\"");
                let at = line.find(&key).unwrap() + key.len();
                line[at..].split('"').next().unwrap().parse().unwrap()
            };
            let (x, y, r) = (attr("cx"), attr("cy"), attr("r"));
            assert!(x - r >= -0.01 && x + r <= 1000.01, "{line}");
            assert!(y - r >= -0.01 && y + r <= 1000.01, "{line}");
            n += 1;
        }
        assert_eq!(n, 3 + sols.len());
    }
}
