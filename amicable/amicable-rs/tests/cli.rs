use std::process::Command;

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_amicable"))
}

#[test]
fn cli_n3_produces_one_pair() {
    let dir = tempfile::tempdir().unwrap();
    let out = bin().arg("3").current_dir(dir.path()).output().unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8(out.stdout).unwrap();
    assert_eq!(stdout.trim(), "220 284");
}

#[test]
fn cli_n1_no_output() {
    let dir = tempfile::tempdir().unwrap();
    let out = bin().arg("1").current_dir(dir.path()).output().unwrap();
    assert!(out.status.success());
    assert!(out.stdout.is_empty());
}

#[test]
fn cli_missing_arg_fails() {
    let out = bin().output().unwrap();
    assert!(!out.status.success());
}

#[test]
fn cli_n9_out_of_range_fails() {
    let out = bin().arg("9").output().unwrap();
    assert!(!out.status.success());
}
