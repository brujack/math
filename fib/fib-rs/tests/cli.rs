use std::io::Write;
use std::process::{Command, Stdio};

use tempfile::tempdir;

fn bin() -> &'static str {
    env!("CARGO_BIN_EXE_fib")
}

#[test]
fn cli_x_one_save_branch_writes_file() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(bin())
        .arg("1")
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.as_mut().unwrap().write_all(b"n\n").unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    let path = dir.path().join("fib_1e1.txt");
    assert!(path.exists());
    let contents = std::fs::read_to_string(&path).unwrap();
    let lines: Vec<&str> = contents.lines().collect();
    assert_eq!(lines.first().copied(), Some("1"));
    assert_eq!(lines.last().copied(), Some("7778742049"));
    assert_eq!(lines.len(), 49);
}

#[test]
fn cli_x_six_exits_one() {
    let dir = tempdir().unwrap();
    let output = Command::new(bin())
        .arg("6")
        .current_dir(dir.path())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(stderr.contains("X must be between 1 and 5"));
}

#[test]
fn cli_x_three_streams_to_file() {
    let dir = tempdir().unwrap();
    let output = Command::new(bin())
        .arg("3")
        .current_dir(dir.path())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .unwrap();
    assert!(output.status.success());
    let path = dir.path().join("fib_1e3.txt");
    assert!(path.exists());
    let contents = std::fs::read_to_string(&path).unwrap();
    assert!(contents.lines().count() > 100);
}

#[test]
fn cli_no_arg_prompts_then_succeeds() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(bin())
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.as_mut().unwrap().write_all(b"1\nn\n").unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    assert!(dir.path().join("fib_1e1.txt").exists());
}
