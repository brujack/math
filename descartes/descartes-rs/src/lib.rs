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
}
