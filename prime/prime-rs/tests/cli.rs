use std::io::Write;
use std::process::{Command, Stdio};
use tempfile::tempdir;

#[test]
fn cli_arg_zero_exits_one() {
    let out = Command::new(env!("CARGO_BIN_EXE_prime"))
        .arg("0")
        .output()
        .expect("failed to run binary");
    assert_ne!(
        out.status.code().unwrap_or(0),
        0,
        "exit code should be non-zero"
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(stderr.contains("between 1 and 18"), "stderr: {}", stderr);
}

#[test]
fn cli_arg_one_displays_when_y() {
    let mut child = Command::new(env!("CARGO_BIN_EXE_prime"))
        .arg("1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("failed to spawn binary");
    child.stdin.as_mut().unwrap().write_all(b"y\n").unwrap();
    let out = child.wait_with_output().unwrap();
    assert_eq!(out.status.code().unwrap_or(1), 0);
    let stdout = String::from_utf8_lossy(&out.stdout);
    // Primes up to 10: 2, 3, 5, 7
    assert!(stdout.contains("2\n"), "stdout: {}", stdout);
    assert!(stdout.contains("7\n"), "stdout: {}", stdout);
}

#[test]
fn cli_arg_one_saves_when_n() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_prime"))
        .arg("1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .current_dir(dir.path())
        .spawn()
        .expect("failed to spawn binary");
    child.stdin.as_mut().unwrap().write_all(b"n\n").unwrap();
    let out = child.wait_with_output().unwrap();
    assert_eq!(out.status.code().unwrap_or(1), 0);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("Saved to"), "stdout: {}", stdout);
    assert!(dir.path().join("primes_1e1.txt").exists());
}

#[test]
fn cli_no_arg_prompts_then_displays() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_prime"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .current_dir(dir.path())
        .spawn()
        .expect("failed to spawn binary");
    // Enter N=1, then choose to display
    child.stdin.as_mut().unwrap().write_all(b"1\ny\n").unwrap();
    let out = child.wait_with_output().unwrap();
    assert_eq!(out.status.code().unwrap_or(1), 0);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("Enter N"), "stdout: {}", stdout);
    assert!(stdout.contains("2\n"), "stdout: {}", stdout);
}
