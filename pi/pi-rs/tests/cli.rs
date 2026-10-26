use std::io::Write;
use std::process::{Command, Stdio};
use tempfile::tempdir;

/// First 10 decimal places of π.
const PI_10: &str = "3.1415926535";

#[test]
fn cli_arg_zero_exits_one() {
    let out =
        Command::new(env!("CARGO_BIN_EXE_pi")).arg("0").output().expect("failed to run binary");
    assert_ne!(out.status.code().unwrap_or(0), 0, "exit code should be non-zero");
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(stderr.contains("≥ 1") || stderr.contains(">= 1"), "stderr: {}", stderr);
}

#[test]
fn cli_arg_displays_when_y() {
    let mut child = Command::new(env!("CARGO_BIN_EXE_pi"))
        .arg("10")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("failed to spawn binary");
    child.stdin.as_mut().unwrap().write_all(b"y\n").unwrap();
    let out = child.wait_with_output().unwrap();
    assert_eq!(out.status.code().unwrap_or(1), 0);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains(PI_10), "stdout: {}", stdout);
}

#[test]
#[cfg(unix)]
fn cli_arg_saves_when_n() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_pi"))
        .arg("10")
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
    assert!(stdout.contains("π saved to"), "stdout: {}", stdout);
}

#[test]
fn cli_no_arg_prompts_then_saves() {
    let dir = tempdir().unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_pi"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .current_dir(dir.path())
        .spawn()
        .expect("failed to spawn binary");
    child.stdin.as_mut().unwrap().write_all(b"10\ny\n").unwrap();
    let out = child.wait_with_output().unwrap();
    assert_eq!(out.status.code().unwrap_or(1), 0);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("decimal places to calculate"), "stdout: {}", stdout);
}

#[cfg(unix)]
#[test]
fn cli_unwritable_output_dir() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempdir().unwrap();
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o555)).unwrap();

    let mut child = Command::new(env!("CARGO_BIN_EXE_pi"))
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

/// Regression: `main()` once held the `StderrLock` across `run()`, so the
/// progress thread's first `eprint!` blocked on a lock owned by the main
/// thread, which was itself blocked in `join()`. Any run long enough to reach
/// the first progress tick hung forever; this one must exit on its own.
#[test]
fn regression_progress_thread_does_not_deadlock_on_locked_stderr() {
    use std::time::{Duration, Instant};

    let dir = tempdir().unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_pi"))
        .arg("5000000")
        .current_dir(dir.path())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("failed to spawn binary");

    let deadline = Instant::now() + Duration::from_secs(60);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            assert!(status.success(), "binary failed: {status}");
            return;
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            panic!("binary did not exit within 60 s: progress thread deadlocked on stderr");
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}
