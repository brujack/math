use std::io::Write;
use std::process::{Command, Stdio};
use tempfile::tempdir;

fn bin() -> &'static str {
    env!("CARGO_BIN_EXE_perfect-numbers")
}

#[test]
fn cli_arg_zero_exits_one() {
    let dir = tempdir().unwrap();
    let output =
        Command::new(bin()).arg("0").current_dir(dir.path()).stdin(Stdio::null()).output().unwrap();
    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("between 1 and 54"), "stderr: {stderr}");
}

#[test]
fn cli_arg_one_creates_file_with_6() {
    let dir = tempdir().unwrap();
    let output =
        Command::new(bin()).arg("1").current_dir(dir.path()).stdin(Stdio::null()).output().unwrap();
    assert_eq!(output.status.code(), Some(0));
    let path = dir.path().join("perfect-numbers_1e1.txt");
    assert!(path.exists(), "expected file to exist");
    assert_eq!(std::fs::read_to_string(&path).unwrap().trim(), "6");
}

#[test]
fn cli_no_arg_prompts_then_creates_file() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(bin())
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.as_mut().unwrap().write_all(b"1\n").unwrap();
    let output = child.wait_with_output().unwrap();
    assert_eq!(output.status.code(), Some(0));
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Enter N"), "stdout: {stdout}");
    assert!(dir.path().join("perfect-numbers_1e1.txt").exists());
}

#[cfg(unix)]
#[test]
fn cli_unwritable_output_dir() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempdir().unwrap();
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o555)).unwrap();
    let output = Command::new(bin())
        .arg("1")
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
        "expected non-zero exit for unwritable directory"
    );
}
