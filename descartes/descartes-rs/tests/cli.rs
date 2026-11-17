use std::process::{Command, Output};

/// Run the binary in `dir` with stdin closed (so it is not a terminal) and stdout piped.
fn run_in(dir: &tempfile::TempDir, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_descartes"))
        .args(args)
        .current_dir(dir.path())
        .output()
        .unwrap()
}

fn text(bytes: &[u8]) -> String {
    String::from_utf8(bytes.to_vec()).unwrap()
}

fn has_line(output: &str, line: &str) -> bool {
    output.lines().any(|l| l == line)
}

fn braille_lines(output: &str) -> Vec<&str> {
    output.lines().filter(|l| l.chars().any(|c| ('\u{2800}'..='\u{28ff}').contains(&c))).collect()
}

fn no_files(dir: &tempfile::TempDir) -> bool {
    std::fs::read_dir(dir.path()).unwrap().next().is_none()
}

#[test]
fn missing_k_without_a_terminal_exits_2() {
    let dir = tempfile::tempdir().unwrap();
    let out = run_in(&dir, &[]);
    assert_eq!(out.status.code(), Some(2));
    assert!(has_line(&text(&out.stderr), "error: K is required when stdin is not a terminal"));
    assert!(out.stdout.is_empty());
    assert!(no_files(&dir));
}

#[test]
fn k_zero_and_nine_exit_2_naming_the_range() {
    for k in ["0", "9"] {
        let dir = tempfile::tempdir().unwrap();
        let out = run_in(&dir, &[k]);
        assert_eq!(out.status.code(), Some(2), "{k}");
        assert_eq!(text(&out.stderr), format!("K must be between 1 and 8, got {k}.\n"));
        assert!(out.stdout.is_empty());
        assert!(no_files(&dir));
    }
}

#[test]
fn non_integer_k_exits_2() {
    let dir = tempfile::tempdir().unwrap();
    let out = run_in(&dir, &["abc"]);
    assert_eq!(out.status.code(), Some(2));
    let line = "error: invalid value 'abc' for '[K]': invalid digit found in string";
    assert!(has_line(&text(&out.stderr), line), "{}", text(&out.stderr));
}

#[test]
fn root_failing_the_descartes_relation_exits_1() {
    let dir = tempfile::tempdir().unwrap();
    let out = run_in(&dir, &["1", "--root", "-1", "2", "2", "4"]);
    assert_eq!(out.status.code(), Some(1));
    let err = text(&out.stderr);
    assert!(err.starts_with("Error: "), "{err}");
    assert!(err.contains("(-1, 2, 2, 4)"), "{err}");
    assert!(no_files(&dir));
}

#[test]
fn root_above_the_cap_exits_2() {
    let dir = tempfile::tempdir().unwrap();
    let out = run_in(&dir, &["1", "--root", "-1", "2", "2", "100000001"]);
    assert_eq!(out.status.code(), Some(2));
    assert!(text(&out.stderr).starts_with("Error: "), "{}", text(&out.stderr));
    assert!(no_files(&dir));
}

#[test]
fn solve_non_tangent_circles_exit_1() {
    let dir = tempfile::tempdir().unwrap();
    let out = run_in(&dir, &["--solve", "-1,0,0", "2,0.5,0", "3,0,0.6667"]);
    assert_eq!(out.status.code(), Some(1));
    let err = text(&out.stderr);
    assert!(err.starts_with("Error: "), "{err}");
    assert!(err.contains("circles 1 and 3 are not tangent"), "{err}");
    assert!(out.stdout.is_empty());
}

#[test]
fn solve_with_a_leading_negative_curvature_prints_the_table() {
    let dir = tempfile::tempdir().unwrap();
    let out =
        run_in(&dir, &["--solve", "-1,0,0", "2,0.5,0", "3,0,0.6666666666666666", "--no-draw"]);
    assert_eq!(out.status.code(), Some(0), "{}", text(&out.stderr));
    let table = text(&out.stdout);
    assert_eq!(table.lines().count(), 6);
    assert!(has_line(
        &table,
        "solution  2  6          0.16666666666666666  0.5   0.6666666666666666"
    ));
    assert!(braille_lines(&table).is_empty());
}

#[test]
fn empty_packing_writes_an_empty_file_and_draws_nothing() {
    let dir = tempfile::tempdir().unwrap();
    let out = run_in(&dir, &["1", "--root", "-11", "21", "24", "28"]);
    assert_eq!(out.status.code(), Some(0));
    let stdout = text(&out.stdout);
    assert!(has_line(&stdout, "circles 0"), "{stdout}");
    assert!(braille_lines(&stdout).is_empty());
    let file = dir.path().join("descartes_1e1_root_-11_21_24_28.txt");
    assert_eq!(std::fs::read_to_string(file).unwrap(), "");
}

#[test]
fn piped_packing_draws_24_lines_of_60_cells() {
    let dir = tempfile::tempdir().unwrap();
    let out = run_in(&dir, &["2"]);
    assert_eq!(out.status.code(), Some(0), "{}", text(&out.stderr));
    let stdout = text(&out.stdout);
    let drawing = braille_lines(&stdout);
    assert_eq!(drawing.len(), 24);
    assert!(drawing.iter().all(|l| l.chars().count() == 60));
    assert!(drawing.iter().any(|l| l.chars().any(|c| c != '\u{2800}')));
    assert!(
        stdout.starts_with("root -1 2 2 3\ncircles 168\ndistinct 33\nSaved to descartes_1e2.txt\n")
    );
}

#[test]
fn packing_writes_the_curvature_file_in_the_working_directory() {
    let dir = tempfile::tempdir().unwrap();
    let out = run_in(&dir, &["3", "--no-draw"]);
    assert_eq!(out.status.code(), Some(0));
    assert_eq!(
        text(&out.stdout),
        "root -1 2 2 3\ncircles 3328\ndistinct 324\nSaved to descartes_1e3.txt\n"
    );
    assert!(text(&out.stderr).starts_with("Elapsed: "), "{}", text(&out.stderr));
    let file = std::fs::read_to_string(dir.path().join("descartes_1e3.txt")).unwrap();
    assert_eq!(file.lines().count(), 324);
}

#[test]
fn svg_cli_binary_writes_svg_in_cwd() {
    let dir = tempfile::tempdir().unwrap();
    let out = run_in(&dir, &["2", "--no-draw", "--svg", "out.svg"]);
    assert_eq!(out.status.code(), Some(0));
    let stdout = text(&out.stdout);
    let lines: Vec<&str> = stdout.lines().collect();
    assert_eq!(lines.last(), Some(&"Saved SVG to out.svg"));
    assert_eq!(lines[lines.len() - 2], "Saved to descartes_1e2.txt");
    let svg = std::fs::read_to_string(dir.path().join("out.svg")).unwrap();
    assert!(svg.contains("<svg "));
}
