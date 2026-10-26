use std::io::Write;
use std::process::{Command, Stdio};
use tempfile::tempdir;

#[test]
fn cli_arg_zero_exits_one() {
    let out =
        Command::new(env!("CARGO_BIN_EXE_prime")).arg("0").output().expect("failed to run binary");
    assert_ne!(out.status.code().unwrap_or(0), 0, "exit code should be non-zero");
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

#[cfg(unix)]
#[test]
fn cli_unwritable_output_dir() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempdir().unwrap();
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o555)).unwrap();

    let mut child = Command::new(env!("CARGO_BIN_EXE_prime"))
        .arg("1")
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
    let mut child = Command::new(env!("CARGO_BIN_EXE_prime"))
        .arg("8")
        .current_dir(dir.path())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::from(std::fs::File::create(dir.path().join("stderr.log")).unwrap()))
        .spawn()
        .expect("failed to spawn binary");

    let deadline = Instant::now() + Duration::from_secs(60);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            assert!(status.success(), "binary failed: {status}");
            // The test proves nothing if compute ends before the first tick:
            // require a progress line printed by the thread mid-run.
            let log = std::fs::read_to_string(dir.path().join("stderr.log")).unwrap();
            assert!(
                mid_run_ticks(&log, MARKER) > 0,
                "no progress tick from the compute thread on stderr; the run no longer outlasts its first tick"
            );
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

/// Progress marker printed by the compute thread's ticks.
const MARKER: &str = "Phase 2:";

/// Counts progress ticks printed by the compute thread: segments (split on `\r`/`\n`)
/// carrying `marker` and a `completed / total` count, which only the thread prints.
fn mid_run_ticks(log: &str, marker: &str) -> usize {
    log.split(['\r', '\n']).filter(|seg| seg.contains(marker) && seg.contains(" / ")).count()
}
