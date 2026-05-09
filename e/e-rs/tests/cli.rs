use std::io::Write;
use std::process::{Command, Stdio};
use tempfile::tempdir;

fn bin() -> &'static str {
    env!("CARGO_BIN_EXE_e")
}

#[test]
fn cli_arg_zero_exits_one() {
    let dir = tempdir().unwrap();
    let output = Command::new(bin())
        .arg("0")
        .current_dir(dir.path())
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(stderr.contains("digits must be"));
}

#[test]
fn cli_arg_displays_when_y() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(bin())
        .arg("10")
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
    assert!(stdout.contains("2.7182818284"));
    assert!(stdout.contains("Total digits"));
}

#[test]
fn cli_arg_saves_when_n() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(bin())
        .arg("10")
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.as_mut().unwrap().write_all(b"n\n").unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    let saved = dir.path().join("e_10_digits.txt");
    assert!(saved.exists());
    let body = std::fs::read_to_string(&saved).unwrap();
    assert!(body.contains("2.7182818284"));
}

#[test]
fn cli_no_arg_prompts() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(bin())
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.as_mut().unwrap().write_all(b"10\nn\n").unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    let saved = dir.path().join("e_10_digits.txt");
    assert!(saved.exists());
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains("Enter the number"));
}

#[cfg(unix)]
#[test]
fn cli_unwritable_output_dir() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempdir().unwrap();
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o555)).unwrap();

    let mut child = Command::new(bin())
        .arg("10")
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();

    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(b"n\n");
    }

    let output = child.wait_with_output().unwrap();
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o755)).unwrap();

    assert_ne!(
        output.status.code().unwrap_or(0),
        0,
        "expected non-zero exit for unwritable directory, stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}
