use std::io::Write;
use std::process::{Command, Stdio};
use tempfile::tempdir;

fn factorial_bin() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_BIN_EXE_factorial"))
}

#[test]
fn cli_invalid_arg_exits_one() {
    let dir = tempdir().unwrap();
    let output = Command::new(factorial_bin()).arg("abc").current_dir(dir.path()).output().unwrap();
    assert_ne!(output.status.code().unwrap(), 0);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("not a valid"), "stderr: {stderr}");
}

#[test]
fn cli_arg_zero_creates_file() {
    let dir = tempdir().unwrap();
    let output = Command::new(factorial_bin()).arg("0").current_dir(dir.path()).output().unwrap();
    assert_eq!(output.status.code().unwrap(), 0);
    let file = dir.path().join("factorial_0.txt");
    assert!(file.exists(), "factorial_0.txt not created");
    let content = std::fs::read_to_string(&file).unwrap();
    assert_eq!(content.trim(), "1");
}

#[test]
fn cli_arg_five_creates_file_with_correct_value() {
    let dir = tempdir().unwrap();
    let output = Command::new(factorial_bin()).arg("5").current_dir(dir.path()).output().unwrap();
    assert_eq!(output.status.code().unwrap(), 0);
    let file = dir.path().join("factorial_5.txt");
    assert!(file.exists(), "factorial_5.txt not created");
    let content = std::fs::read_to_string(&file).unwrap();
    assert_eq!(content.trim(), "120");
}

#[test]
fn cli_no_arg_prompts_and_computes() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(factorial_bin())
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.as_mut().unwrap().write_all(b"3\n").unwrap();
    let output = child.wait_with_output().unwrap();
    assert_eq!(output.status.code().unwrap(), 0);
    let file = dir.path().join("factorial_3.txt");
    assert!(file.exists(), "factorial_3.txt not created");
    let content = std::fs::read_to_string(&file).unwrap();
    assert_eq!(content.trim(), "6");
}

#[test]
fn cli_no_arg_retries_on_bad_input() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(factorial_bin())
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.as_mut().unwrap().write_all(b"bad\n4\n").unwrap();
    let output = child.wait_with_output().unwrap();
    assert_eq!(output.status.code().unwrap(), 0);
    let file = dir.path().join("factorial_4.txt");
    assert!(file.exists(), "factorial_4.txt not created");
    let content = std::fs::read_to_string(&file).unwrap();
    assert_eq!(content.trim(), "24");
}

#[test]
fn cli_idempotent_overwrite() {
    let dir = tempdir().unwrap();
    for _ in 0..2 {
        let output =
            Command::new(factorial_bin()).arg("2").current_dir(dir.path()).output().unwrap();
        assert_eq!(output.status.code().unwrap(), 0);
    }
    let file = dir.path().join("factorial_2.txt");
    let content = std::fs::read_to_string(&file).unwrap();
    assert_eq!(content.trim(), "2");
}

#[test]
fn cli_backend_line_shows_thread_count() {
    let dir = tempdir().unwrap();
    let output = Command::new(factorial_bin()).arg("5").current_dir(dir.path()).output().unwrap();
    assert_eq!(output.status.code().unwrap(), 0);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains("rayon (") && stderr.contains("threads)"),
        "expected Backend line with thread count in stderr, got: {stderr}",
    );
}

#[cfg(unix)]
#[test]
fn cli_unwritable_output_dir() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempdir().unwrap();
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o555)).unwrap();

    let output = Command::new(factorial_bin())
        .arg("5")
        .current_dir(dir.path())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .unwrap();

    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o755)).unwrap();

    assert_ne!(
        output.status.code().unwrap_or(0),
        0,
        "expected non-zero exit for unwritable directory, stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}
