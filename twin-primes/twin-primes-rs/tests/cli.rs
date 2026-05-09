use std::process::Command;
use tempfile::tempdir;

fn twin_primes_bin() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_BIN_EXE_twin-primes"))
}

#[test]
fn cli_invalid_digits_zero_exits_nonzero() {
    let dir = tempdir().unwrap();
    let output = Command::new(twin_primes_bin())
        .arg("0")
        .current_dir(dir.path())
        .output()
        .unwrap();
    assert_ne!(output.status.code().unwrap(), 0);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("between 1 and 15"), "stderr: {stderr}");
}

#[test]
fn cli_invalid_digits_16_exits_nonzero() {
    let dir = tempdir().unwrap();
    let output = Command::new(twin_primes_bin())
        .arg("16")
        .current_dir(dir.path())
        .output()
        .unwrap();
    assert_ne!(output.status.code().unwrap(), 0);
}

#[test]
fn cli_n1_creates_file_with_2_pairs() {
    let dir = tempdir().unwrap();
    let output = Command::new(twin_primes_bin())
        .arg("1")
        .current_dir(dir.path())
        .output()
        .unwrap();
    assert_eq!(output.status.code().unwrap(), 0);
    let file = dir.path().join("twin-primes_1e1.txt");
    assert!(file.exists(), "twin-primes_1e1.txt not created");
    let content = std::fs::read_to_string(&file).unwrap();
    assert_eq!(content, "3 | 5\n5 | 7\n");
}

#[test]
fn cli_n2_creates_file_with_8_pairs() {
    let dir = tempdir().unwrap();
    let output = Command::new(twin_primes_bin())
        .arg("2")
        .current_dir(dir.path())
        .output()
        .unwrap();
    assert_eq!(output.status.code().unwrap(), 0);
    let file = dir.path().join("twin-primes_1e2.txt");
    assert!(file.exists(), "twin-primes_1e2.txt not created");
    let content = std::fs::read_to_string(&file).unwrap();
    assert_eq!(content.lines().count(), 8);
}

#[test]
fn cli_stdout_contains_header_and_saved() {
    let dir = tempdir().unwrap();
    let output = Command::new(twin_primes_bin())
        .arg("1")
        .current_dir(dir.path())
        .output()
        .unwrap();
    assert_eq!(output.status.code().unwrap(), 0);
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Twin Prime Sieve"), "stdout: {stdout}");
    assert!(stdout.contains("Saved to"), "stdout: {stdout}");
}

#[test]
fn cli_idempotent_overwrite() {
    let dir = tempdir().unwrap();
    for _ in 0..2 {
        let output = Command::new(twin_primes_bin())
            .arg("1")
            .current_dir(dir.path())
            .output()
            .unwrap();
        assert_eq!(output.status.code().unwrap(), 0);
    }
    let file = dir.path().join("twin-primes_1e1.txt");
    let content = std::fs::read_to_string(&file).unwrap();
    assert_eq!(content, "3 | 5\n5 | 7\n");
}

#[cfg(unix)]
#[test]
fn cli_unwritable_output_dir() {
    use std::os::unix::fs::PermissionsExt;
    use std::process::Stdio;
    let dir = tempdir().unwrap();
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o555)).unwrap();

    let output = Command::new(twin_primes_bin())
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
        "expected non-zero exit for unwritable directory, stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}
