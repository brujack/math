use std::process::Command;

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_descartes"))
}

#[test]
fn cli_prints_both_fourth_curvatures() {
    let dir = tempfile::tempdir().unwrap();
    let out = bin().args(["2", "3", "6"]).current_dir(dir.path()).output().unwrap();
    assert!(out.status.success());
    assert_eq!(String::from_utf8(out.stdout).unwrap(), "23\n-1\n");
}

#[test]
fn cli_negative_first_curvature_parses() {
    let dir = tempfile::tempdir().unwrap();
    let out = bin().args(["-1", "2", "2"]).current_dir(dir.path()).output().unwrap();
    assert!(out.status.success());
    assert_eq!(String::from_utf8(out.stdout).unwrap(), "3\n3\n");
}

#[test]
fn cli_no_solution_exits_1() {
    let out = bin().args(["1", "1", "-2"]).output().unwrap();
    assert_eq!(out.status.code(), Some(1));
    assert!(out.stdout.is_empty());
}

#[test]
fn cli_missing_arg_fails() {
    let out = bin().output().unwrap();
    assert_eq!(out.status.code(), Some(2));
}
