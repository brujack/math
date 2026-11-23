use std::process::Command;

fn zeta_bin() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_BIN_EXE_zeta"))
}

#[test]
fn cli_stub_exits_3_with_exact_stderr_and_empty_stdout() {
    let cases: [&[&str]; 3] = [&[], &["3"], &["99"]];
    for args in cases {
        let output = Command::new(zeta_bin()).args(args).output().unwrap();
        assert_eq!(output.status.code(), Some(3), "{args:?}");
        assert_eq!(
            String::from_utf8_lossy(&output.stderr),
            "RH NOT verified: zeta is under construction\n",
            "{args:?}"
        );
        assert!(output.stdout.is_empty(), "{args:?}");
    }
}

#[test]
fn cli_help_exits_0() {
    let output = Command::new(zeta_bin()).arg("--help").output().unwrap();
    assert_eq!(output.status.code(), Some(0));
    assert!(!output.stdout.is_empty());
}
