use std::io::Write;
use std::process::{Command, Stdio};

fn zeta_bin() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_BIN_EXE_zeta"))
}

/// Runs zeta in `dir` with the given stdin; returns (code, stdout, stderr).
fn run_in(dir: &std::path::Path, args: &[&str], stdin: &str) -> (Option<i32>, String, String) {
    let mut child = Command::new(zeta_bin())
        .args(args)
        .current_dir(dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(stdin.as_bytes()).unwrap();
    let output = child.wait_with_output().unwrap();
    (
        output.status.code(),
        String::from_utf8_lossy(&output.stdout).into_owned(),
        String::from_utf8_lossy(&output.stderr).into_owned(),
    )
}

/// Runs zeta in a fresh scratch directory and asserts it wrote no file.
fn run(args: &[&str], stdin: &str) -> (Option<i32>, String, String) {
    let dir = tempfile::tempdir().unwrap();
    let result = run_in(dir.path(), args, stdin);
    assert!(std::fs::read_dir(dir.path()).unwrap().next().is_none(), "{args:?}: wrote a file");
    result
}

/// The first 649 Odlyzko zeros (height <= 1000), from the committed fixture.
fn odlyzko() -> Vec<f64> {
    let text = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/fixtures/odlyzko_1e3.txt"
    ))
    .unwrap();
    text.lines().filter(|l| !l.starts_with('#')).map(|l| l.trim().parse().unwrap()).collect()
}

/// Runs `zeta <n>` in a scratch directory and checks the verified contract: exit 0,
/// the verified line with `count`, a table of `count` lines whose nth interval holds
/// the nth Odlyzko zero, and no temporary file left behind.
fn assert_verified(n: &str, height: u32, count: usize) {
    let dir = tempfile::tempdir().unwrap();
    let (code, out, err) = run_in(dir.path(), &[n], "");
    assert_eq!(code, Some(0), "{out}{err}");
    let line = format!(
        "RH verified: all {count} nontrivial zeros with 0 < Im s <= {height} lie on Re s = 1/2 and are simple\n"
    );
    assert!(out.contains(&line), "{out}");
    let table = std::fs::read_to_string(dir.path().join(format!("zeta_1e{n}.txt"))).unwrap();
    let mut lines = table.lines();
    assert_eq!(lines.next(), Some("# n a b"));
    let rows: Vec<&str> = lines.collect();
    assert_eq!(rows.len(), count);
    let zeros = odlyzko();
    for (i, row) in rows.iter().enumerate() {
        let fields: Vec<&str> = row.split(' ').collect();
        assert_eq!(fields.len(), 3, "{row}");
        assert_eq!(fields[0], (i + 1).to_string());
        let (a, b): (f64, f64) = (fields[1].parse().unwrap(), fields[2].parse().unwrap());
        assert!(a <= zeros[i] && zeros[i] <= b, "zero {} = {} outside [{a}, {b}]", i + 1, zeros[i]);
    }
    let names: Vec<_> =
        std::fs::read_dir(dir.path()).unwrap().map(|e| e.unwrap().file_name()).collect();
    assert_eq!(names, vec![std::ffi::OsString::from(format!("zeta_1e{n}.txt"))]);
}

#[test]
fn fixture_holds_649_increasing_zeros_with_a_source_header() {
    let zeros = odlyzko();
    assert_eq!(zeros.len(), 649);
    assert!(zeros.windows(2).all(|w| w[0] < w[1]));
    assert!(zeros[648] < 1000.0);
    let text = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/fixtures/odlyzko_1e3.txt"
    ))
    .unwrap();
    assert!(text.contains("https://www-users.cse.umn.edu/~odlyzko/zeta_tables/zeros1"));
    assert!(text.contains("Retrieved: 2026-11-23"));
}

#[test]
fn e2e_n_2_verifies_29_zeros() {
    assert_verified("2", 100, 29);
}

#[test]
fn e2e_n_3_verifies_649_zeros() {
    assert_verified("3", 1000, 649);
}

#[test]
fn e2e_stale_temporary_file_is_removed_by_a_verified_run() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("zeta_1e2.tmp.txt"), "stale").unwrap();
    let (code, ..) = run_in(dir.path(), &["2"], "");
    assert_eq!(code, Some(0));
    assert!(!dir.path().join("zeta_1e2.tmp.txt").exists());
    assert!(dir.path().join("zeta_1e2.txt").exists());
}

#[test]
fn e2e_prompted_n_is_accepted() {
    let (code, out, _) = {
        let dir = tempfile::tempdir().unwrap();
        run_in(dir.path(), &[], "2\n")
    };
    assert_eq!(code, Some(0));
    assert!(out.contains("RH verified: all 29 nontrivial zeros with 0 < Im s <= 100 "), "{out}");
}

#[test]
fn e2e_stale_removal_failure_exits_4_without_a_verified_claim() {
    let dir = tempfile::tempdir().unwrap();
    // A directory at the temporary name makes the start-of-run stale removal fail.
    std::fs::create_dir(dir.path().join("zeta_1e2.tmp.txt")).unwrap();
    let (code, out, err) = run_in(dir.path(), &["2"], "");
    assert_eq!(code, Some(4), "{out}{err}");
    assert!(!out.contains("RH verified"), "{out}");
    assert!(!dir.path().join("zeta_1e2.txt").exists());
}

#[test]
fn out_of_range_and_non_numeric_n_exit_1() {
    for arg in ["1", "8", "abc", "-1", "-5"] {
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
fn no_failing_path_claims_verification() {
    for (args, stdin) in [(vec!["8"], ""), (vec![], ""), (vec![], "9\n"), (vec!["x"], "")] {
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

/// A read-only work directory: verification succeeds, then creating the temporary file
/// fails (exit 4) and no verified claim is printed. Skipped when the process can write
/// to a read-only directory anyway (root).
#[test]
fn e2e_create_failure_after_verification_exits_4_without_a_verified_claim() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o555)).unwrap();
    let probe = dir.path().join("probe");
    if std::fs::write(&probe, "x").is_ok() {
        std::fs::remove_file(&probe).unwrap();
        std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o755)).unwrap();
        eprintln!("skipped: this process can write to a read-only directory (root)");
        return;
    }
    let (code, out, err) = run_in(dir.path(), &["2"], "");
    std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o755)).unwrap();
    assert_eq!(code, Some(4), "{out}{err}");
    assert!(!out.contains("RH verified"), "{out}");
    let last = err.lines().last().unwrap_or_default();
    assert!(last.starts_with("Error: cannot write zeta_1e2.txt: "), "{err}");
    assert!(std::fs::read_dir(dir.path()).unwrap().next().is_none());
}
