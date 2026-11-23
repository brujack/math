use std::io::Write;
use std::process::{Command, Stdio};

fn zeta_bin() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_BIN_EXE_zeta"))
}

/// Runs zeta in a scratch directory with the given stdin; returns (code, stdout, stderr).
fn run(args: &[&str], stdin: &str) -> (Option<i32>, String, String) {
    let dir = tempfile::tempdir().unwrap();
    let mut child = Command::new(zeta_bin())
        .args(args)
        .current_dir(dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(stdin.as_bytes()).unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(std::fs::read_dir(dir.path()).unwrap().next().is_none(), "{args:?}: wrote a file");
    (
        output.status.code(),
        String::from_utf8_lossy(&output.stdout).into_owned(),
        String::from_utf8_lossy(&output.stderr).into_owned(),
    )
}

#[test]
fn valid_n_runs_self_check_then_reports_not_verified_with_exit_3() {
    let (code, out, err) = run(&["3"], "");
    assert_eq!(code, Some(3));
    assert_eq!(out, "RH NOT verified up to 1000: zero isolation is not implemented yet\n");
    assert!(err.is_empty(), "{err:?}");
}

#[test]
fn n_7_warns_on_stderr_and_still_exits_3() {
    let (code, out, err) = run(&["7"], "");
    assert_eq!(code, Some(3));
    assert!(out.starts_with("RH NOT verified up to 10000000:"), "{out:?}");
    assert_eq!(
        err,
        "Warning: N=7 writes about 1.5 GB (about 2.2 GB with --refine) and may take many hours.\n"
    );
}

#[test]
fn out_of_range_and_non_numeric_n_exit_1() {
    for arg in ["1", "8", "abc"] {
        let (code, out, err) = run(&[arg], "");
        assert_eq!(code, Some(1), "{arg}");
        assert_eq!(err, "Error: N must be between 2 and 7.\n", "{arg}");
        assert!(out.is_empty(), "{arg}: {out:?}");
    }
}

#[test]
fn end_of_input_at_the_prompt_exits_1() {
    let (code, out, err) = run(&[], "");
    assert_eq!(code, Some(1));
    assert!(out.ends_with('\n') && out.contains("Enter N"), "{out:?}");
    assert_eq!(err, "Error: no input; pass SIZE as an argument (e.g. zeta 3).\n");
}

#[test]
fn prompted_n_is_accepted() {
    let (code, out, _) = run(&[], "2\n");
    assert_eq!(code, Some(3));
    assert!(out.ends_with("RH NOT verified up to 100: zero isolation is not implemented yet\n"));
}

#[test]
fn no_path_claims_verification() {
    for (args, stdin) in [(vec!["3"], ""), (vec!["8"], ""), (vec![], ""), (vec![], "5\n")] {
        let (_, out, err) = run(&args, stdin);
        for text in [out, err] {
            assert!(!text.contains("RH holds") && !text.contains("RH verified"), "{text:?}");
        }
    }
}

#[test]
fn cli_help_exits_0() {
    let output = Command::new(zeta_bin()).arg("--help").output().unwrap();
    assert_eq!(output.status.code(), Some(0));
    assert!(!output.stdout.is_empty());
}
