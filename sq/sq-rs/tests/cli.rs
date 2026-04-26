use std::io::Write;
use std::process::{Command, Stdio};

use tempfile::tempdir;

fn bin() -> &'static str {
    env!("CARGO_BIN_EXE_sq")
}

#[test]
fn cli_with_arg_one_writes_file_and_skips_display() {
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
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains("Saved to"));
    assert!(!stdout.contains("9999800001 | 99999"));
    let path = dir.path().join("sq_1e1.txt");
    assert!(path.exists());
    let contents = std::fs::read_to_string(&path).unwrap();
    assert!(contents.contains("9999800001 | 99999"));
}

#[test]
fn cli_with_arg_two_exits_one() {
    let dir = tempdir().unwrap();
    let output = Command::new(bin())
        .arg("2")
        .current_dir(dir.path())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(stderr.contains("Error: N must be 1."));
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
    assert!(dir.path().join("sq_1e1.txt").exists());
}

#[test]
fn cli_yes_displays_buffer() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(bin())
        .arg("1")
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.as_mut().unwrap().write_all(b"y\n").unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains("9999800001 | 99999"));
}
