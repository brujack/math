//! Parity of the Rust binary against `descartes.py` (spec R15).
//!
//! Excluded from mutation runs (`.cargo/mutants.toml`): cargo-mutants copies only this crate,
//! so the Python program is not available there. Drawings are compared per language only.

use std::path::Path;
use std::process::{Command, Output, Stdio};

const PYTHON_PROGRAM: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../descartes.py");

fn run_python(dir: &Path, args: &[&str]) -> Output {
    Command::new("python3")
        .arg(PYTHON_PROGRAM)
        .args(args)
        .arg("--no-draw")
        .current_dir(dir)
        .stdin(Stdio::null())
        .output()
        .expect("python3 must be on PATH to run the parity tests (CI installs it)")
}

fn run_rust(dir: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_descartes"))
        .args(args)
        .arg("--no-draw")
        .current_dir(dir)
        .stdin(Stdio::null())
        .output()
        .unwrap()
}

fn text(bytes: &[u8]) -> String {
    String::from_utf8(bytes.to_vec()).unwrap()
}

/// The report lines whose text must match exactly (`Elapsed` varies per run).
fn stable_lines(stdout: &str) -> Vec<String> {
    ["root ", "circles ", "distinct ", "Saved to "]
        .iter()
        .map(|prefix| {
            let found: Vec<&str> = stdout.lines().filter(|l| l.starts_with(prefix)).collect();
            assert_eq!(found.len(), 1, "expected one `{prefix}` line in:\n{stdout}");
            found[0].to_string()
        })
        .collect()
}

fn saved_file(stdout: &str) -> String {
    let line = stdout.lines().find(|l| l.starts_with("Saved to ")).unwrap();
    line["Saved to ".len()..].to_string()
}

fn assert_packing_parity(args: &[&str]) {
    let py_dir = tempfile::tempdir().unwrap();
    let rs_dir = tempfile::tempdir().unwrap();
    let py = run_python(py_dir.path(), args);
    let rs = run_rust(rs_dir.path(), args);
    let (py_out, rs_out) = (text(&py.stdout), text(&rs.stdout));
    assert_eq!(py.status.code(), Some(0), "python {args:?}: {}", text(&py.stderr));
    assert_eq!(rs.status.code(), Some(0), "rust {args:?}: {}", text(&rs.stderr));
    for (who, out) in [("python", &py_out), ("rust", &rs_out)] {
        let circles = out.lines().find(|l| l.starts_with("circles "));
        assert!(
            circles.is_some_and(|l| l.len() > "circles ".len()),
            "{who} {args:?} printed no circles line:\n{out}"
        );
    }
    assert_eq!(stable_lines(&py_out), stable_lines(&rs_out), "{args:?}");
    let py_file = std::fs::read(py_dir.path().join(saved_file(&py_out))).unwrap();
    let rs_file = std::fs::read(rs_dir.path().join(saved_file(&rs_out))).unwrap();
    assert_eq!(py_file, rs_file, "curvature files differ for {args:?}");
}

#[test]
fn default_root_matches_for_k_1_to_5() {
    for k in 1..=5 {
        assert_packing_parity(&[&k.to_string()]);
    }
}

#[test]
fn root_minus_2_3_6_7_matches_for_k_1_to_3() {
    for k in 1..=3 {
        assert_packing_parity(&[&k.to_string(), "--root", "-2", "3", "6", "7"]);
    }
}

#[test]
fn root_minus_11_21_24_28_matches_for_k_1_to_3() {
    for k in 1..=3 {
        assert_packing_parity(&[&k.to_string(), "--root", "-11", "21", "24", "28"]);
    }
}

#[test]
fn repeated_root_keeps_the_last_for_k_2() {
    assert_packing_parity(&[
        "2", "--root", "-11", "21", "24", "28", "--root", "-11", "21", "24", "28",
    ]);
    assert_packing_parity(&["2", "--root", "-1", "2", "2", "3", "--root", "-2", "3", "6", "7"]);
}

/// The table rows after the header, split into cells.
fn table_rows(stdout: &str) -> Vec<Vec<String>> {
    stdout
        .lines()
        .filter(|l| !l.trim().is_empty() && !l.starts_with("Elapsed"))
        .map(|l| l.split_whitespace().map(str::to_string).collect())
        .collect()
}

#[test]
fn solve_tables_match_within_1e_12() {
    let args = ["--solve", "-1,0,0", "2,0.5,0", "3,0,0.6666666666666666"];
    let py_dir = tempfile::tempdir().unwrap();
    let rs_dir = tempfile::tempdir().unwrap();
    let py = run_python(py_dir.path(), &args);
    let rs = run_rust(rs_dir.path(), &args);
    assert_eq!(py.status.code(), Some(0), "python: {}", text(&py.stderr));
    assert_eq!(rs.status.code(), Some(0), "rust: {}", text(&rs.stderr));
    let (py_rows, rs_rows) = (table_rows(&text(&py.stdout)), table_rows(&text(&rs.stdout)));
    assert!(py_rows.len() > 1, "python printed no table");
    assert_eq!(py_rows.len(), rs_rows.len());
    for (p, r) in py_rows.iter().zip(&rs_rows) {
        assert_eq!(p.len(), r.len(), "{p:?} vs {r:?}");
        for (pc, rc) in p.iter().zip(r) {
            match (pc.parse::<f64>(), rc.parse::<f64>()) {
                (Ok(a), Ok(b)) => assert!((a - b).abs() <= 1e-12, "{pc} vs {rc} in {p:?}"),
                (Err(_), Err(_)) => assert_eq!(pc, rc),
                _ => panic!("cell type differs: {pc} vs {rc}"),
            }
        }
    }
}

/// One run of an SVG document: text, or a number written with 3 decimals as thousandths.
#[derive(Debug, PartialEq, Eq)]
enum Token {
    Text(String),
    Thousandths(i64),
}

/// Splits `svg` into text runs and numbers (`-?\d+\.\d{3}`), numbers parsed as integer
/// thousandths so no float rounding enters the comparison.
fn svg_tokens(svg: &str) -> Vec<Token> {
    let b = svg.as_bytes();
    let mut tokens = Vec::new();
    let (mut text_start, mut i) = (0, 0);
    while i < b.len() {
        match number_at(b, i) {
            Some((value, end)) => {
                if text_start < i {
                    tokens.push(Token::Text(svg[text_start..i].to_string()));
                }
                tokens.push(Token::Thousandths(value));
                i = end;
                text_start = end;
            }
            None => i += 1,
        }
    }
    if text_start < b.len() {
        tokens.push(Token::Text(svg[text_start..].to_string()));
    }
    tokens
}

/// The number starting at `start`, as `(thousandths, end index)`, if one does.
fn number_at(b: &[u8], start: usize) -> Option<(i64, usize)> {
    let negative = b[start] == b'-';
    let int_start = start + usize::from(negative);
    let int_end = int_start + b[int_start..].iter().take_while(|c| c.is_ascii_digit()).count();
    let frac_end = int_end + 4;
    let has_point = int_end > int_start && b.get(int_end) == Some(&b'.');
    if !has_point || frac_end > b.len() || !b[int_end + 1..frac_end].iter().all(u8::is_ascii_digit)
    {
        return None;
    }
    let digits = b[int_start..int_end].iter().chain(&b[int_end + 1..frac_end]);
    let magnitude = digits.fold(0i64, |acc, d| acc * 10 + i64::from(d - b'0'));
    Some((if negative { -magnitude } else { magnitude }, frac_end))
}

/// Number of `<circle ` elements in `svg`.
fn circle_count(svg: &str) -> usize {
    svg.matches("<circle ").count()
}

/// The first line (1-based) where `a` and `b` differ, with both texts.
fn first_differing_line(a: &str, b: &str) -> String {
    let (mut la, mut lb) = (a.lines(), b.lines());
    for n in 1.. {
        match (la.next(), lb.next()) {
            (Some(x), Some(y)) if x == y => {}
            (None, None) => return "no differing line".to_string(),
            (x, y) => return format!("line {n}: python `{x:?}` vs rust `{y:?}`"),
        }
    }
    unreachable!()
}

/// Runs both CLIs with `--svg out.svg` and compares the documents: same structure, same
/// text, every number within one thousandth.
fn assert_svg_parity(args: &[&str], circles: usize) {
    let py_dir = tempfile::tempdir().unwrap();
    let rs_dir = tempfile::tempdir().unwrap();
    let mut full: Vec<&str> = args.to_vec();
    full.extend(["--svg", "out.svg"]);
    let py = run_python(py_dir.path(), &full);
    let rs = run_rust(rs_dir.path(), &full);
    assert_eq!(py.status.code(), Some(0), "python {args:?}: {}", text(&py.stderr));
    assert_eq!(rs.status.code(), Some(0), "rust {args:?}: {}", text(&rs.stderr));
    let py_svg = std::fs::read_to_string(py_dir.path().join("out.svg")).unwrap();
    let rs_svg = std::fs::read_to_string(rs_dir.path().join("out.svg")).unwrap();
    assert_eq!(circle_count(&py_svg), circles, "python circle count for {args:?}");
    assert_eq!(circle_count(&rs_svg), circles, "rust circle count for {args:?}");
    let (py_tokens, rs_tokens) = (svg_tokens(&py_svg), svg_tokens(&rs_svg));
    let where_ = first_differing_line(&py_svg, &rs_svg);
    assert_eq!(py_tokens.len(), rs_tokens.len(), "token counts differ for {args:?}; {where_}");
    for (p, r) in py_tokens.iter().zip(&rs_tokens) {
        match (p, r) {
            (Token::Thousandths(a), Token::Thousandths(b)) => {
                assert!((a - b).abs() <= 1, "{a} vs {b} thousandths for {args:?}; {where_}");
            }
            _ => assert_eq!(p, r, "tokens differ for {args:?}; {where_}"),
        }
    }
}

#[test]
fn svg_tokens_parses_a_negative_number() {
    assert_eq!(svg_tokens("-0.500"), [Token::Thousandths(-500)]);
}

#[test]
fn svg_tokens_splits_a_number_from_adjacent_text() {
    assert_eq!(
        svg_tokens(r#"r="12.345"/>"#),
        [
            Token::Text("r=\"".to_string()),
            Token::Thousandths(12345),
            Token::Text("\"/>".to_string()),
        ]
    );
}

#[test]
fn svg_tokens_keeps_a_non_three_decimal_number_as_text() {
    assert_eq!(svg_tokens("12 3.5 7.50"), [Token::Text("12 3.5 7.50".to_string())]);
    assert_eq!(svg_tokens("-"), [Token::Text("-".to_string())]);
    assert_eq!(svg_tokens(""), []);
}

#[test]
fn svg_tokens_reads_a_large_number_without_float() {
    assert_eq!(svg_tokens("436.563"), [Token::Thousandths(436563)]);
}

#[test]
fn first_differing_line_names_the_line() {
    assert!(first_differing_line("a\nb\n", "a\nc\n").starts_with("line 2:"));
    assert_eq!(first_differing_line("a\n", "a\n"), "no differing line");
}

#[test]
fn svg_parity_default_root_k1() {
    assert_svg_parity(&["1"], 9);
}

#[test]
fn svg_parity_default_root_k2() {
    assert_svg_parity(&["2"], 169);
}

#[test]
fn svg_parity_default_root_k3() {
    assert_svg_parity(&["3"], 3329);
}

#[test]
fn svg_parity_tie_root_k5() {
    assert_svg_parity(&["5", "--root", "-12", "25", "25", "28"], 3327);
}

#[test]
fn svg_parity_solve() {
    assert_svg_parity(&["--solve", "-1,0,0", "2,0.5,0", "3,0,0.6666666666666666"], 5);
}
