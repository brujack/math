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

fn check_n(n: i64, max: i64) -> Result<(), DescartesError> {
    if n < 0 {
        return Err(DescartesError::BadInput(format!("pack(n={n}): n must not be negative")));
    }
    if n > max {
        return Err(DescartesError::BadInput(format!("pack(n={n}): n must be at most {max}")));
    }
    Ok(())
}

fn check_reduced_root(root: [i64; 4]) -> Result<(), DescartesError> {
    if over_ceiling(root).is_some() {
        // Not summed: beyond the cap the relation could overflow i64.
        return Err(DescartesError::BadInput(format!(
            "pack(root={}, ...): root is beyond the cap of at most 10^8 in absolute value",
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
    Err(DescartesError::BadInput(format!("pack(root={}, ...): root is {problem}", show(root))))
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
    check_n(n, N_MAX)?;
    check_reduced_root(root)?;
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
        assert_eq!(check_n(0, 30), Ok(()));
        assert_eq!(check_n(30, 30), Ok(()));
        assert_eq!(
            check_n(31, 30),
            Err(DescartesError::BadInput("pack(n=31): n must be at most 30".into()))
        );
        assert_eq!(
            check_n(-1, 30),
            Err(DescartesError::BadInput("pack(n=-1): n must not be negative".into()))
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
    // walk is budgeted so a missing guard fails in a few thousand steps.
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
}
