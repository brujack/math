use std::io::Write;
use std::process::{Command, Stdio};
use tempfile::tempdir;

fn collatz_bin() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_BIN_EXE_collatz"))
}

#[test]
fn cli_invalid_arg_exits_nonzero() {
    let dir = tempdir().unwrap();
    let output = Command::new(collatz_bin()).arg("abc").current_dir(dir.path()).output().unwrap();
    assert_ne!(output.status.code().unwrap(), 0);
}

#[test]
fn cli_out_of_range_exits_one() {
    let dir = tempdir().unwrap();
    let output = Command::new(collatz_bin()).arg("0").current_dir(dir.path()).output().unwrap();
    assert_eq!(output.status.code().unwrap(), 1);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("between 1 and 12"), "stderr: {stderr}");
}

#[test]
fn cli_arg_one_creates_file() {
    let dir = tempdir().unwrap();
    let output = Command::new(collatz_bin()).arg("1").current_dir(dir.path()).output().unwrap();
    assert_eq!(output.status.code().unwrap(), 0);
    let path = dir.path().join("collatz_1e1.txt");
    assert!(path.exists(), "collatz_1e1.txt not created");
    let content = std::fs::read_to_string(&path).unwrap();
    let lines: Vec<&str> = content.trim().lines().collect();
    assert_eq!(lines.len(), 6, "expected 6 records for exponent=1");
    assert_eq!(lines[0], "1 0");
    assert_eq!(lines[2], "3 7");
}

#[test]
fn cli_idempotent_overwrite() {
    let dir = tempdir().unwrap();
    for _ in 0..2 {
        let output = Command::new(collatz_bin()).arg("1").current_dir(dir.path()).output().unwrap();
        assert_eq!(output.status.code().unwrap(), 0);
    }
    let path = dir.path().join("collatz_1e1.txt");
    let content = std::fs::read_to_string(&path).unwrap();
    let lines: Vec<&str> = content.trim().lines().collect();
    assert_eq!(lines.len(), 6);
    assert_eq!(lines[0], "1 0");
}

#[test]
fn cli_no_arg_prompts_and_computes() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(collatz_bin())
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.as_mut().unwrap().write_all(b"1\n").unwrap();
    let output = child.wait_with_output().unwrap();
    assert_eq!(output.status.code().unwrap(), 0);
    let path = dir.path().join("collatz_1e1.txt");
    assert!(path.exists(), "collatz_1e1.txt not created via stdin");
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Enter N"), "expected prompt in stdout");
}
