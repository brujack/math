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
