use clap::Parser;

#[derive(Parser, Debug)]
#[command(
    name = "zeta",
    about = "Verify the Riemann Hypothesis up to height 10^N with certified interval arithmetic"
)]
struct Cli {
    /// N: target height 10^N (range 2-7 enforced once verification lands; this build exits 3 for any input)
    exponent: Option<u32>,
}

/// The stub never claims verification: it always reports that and exits 3.
fn run<W: std::io::Write>(_cli: &Cli, err: &mut W) -> std::io::Result<i32> {
    writeln!(err, "RH NOT verified: zeta is under construction")?;
    Ok(3)
}

/// Maps a `run` outcome to a process exit code; a failed stderr write is exit 1.
fn exit_code(result: std::io::Result<i32>) -> i32 {
    result.unwrap_or(1)
}

#[cfg(not(tarpaulin_include))]
fn main() {
    let cli = Cli::parse();
    std::process::exit(exit_code(run(&cli, &mut std::io::stderr())));
}

#[cfg(test)]
mod tests {
    use super::*;
    use clap::CommandFactory;

    #[test]
    fn help_parses() {
        let err = Cli::try_parse_from(["zeta", "--help"]).unwrap_err();
        assert_eq!(err.kind(), clap::error::ErrorKind::DisplayHelp);
    }

    #[test]
    fn command_definition_is_valid() {
        Cli::command().debug_assert();
    }

    #[test]
    fn exponent_is_optional_and_parsed() {
        assert_eq!(Cli::try_parse_from(["zeta"]).unwrap().exponent, None);
        assert_eq!(Cli::try_parse_from(["zeta", "3"]).unwrap().exponent, Some(3));
    }

    struct FailingWriter;

    impl std::io::Write for FailingWriter {
        fn write(&mut self, _buf: &[u8]) -> std::io::Result<usize> {
            Err(std::io::Error::other("stderr closed"))
        }

        fn flush(&mut self) -> std::io::Result<()> {
            Err(std::io::Error::other("stderr closed"))
        }
    }

    #[test]
    fn stub_exits_with_code_and_exact_stderr_line() {
        for args in [vec!["zeta"], vec!["zeta", "3"], vec!["zeta", "99"]] {
            let cli = Cli::try_parse_from(&args).unwrap();
            let mut err = Vec::new();
            let code = run(&cli, &mut err).unwrap();
            assert_eq!(code, 3, "{args:?}");
            assert_eq!(
                String::from_utf8(err).unwrap(),
                "RH NOT verified: zeta is under construction\n",
                "{args:?}"
            );
        }
    }

    #[test]
    fn failing_stderr_is_an_error_and_maps_to_exit_1() {
        let cli = Cli::try_parse_from(["zeta"]).unwrap();
        let result = run(&cli, &mut FailingWriter);
        assert!(result.is_err());
        assert_eq!(exit_code(result), 1);
    }

    #[test]
    fn exit_code_passes_through_success_codes() {
        assert_eq!(exit_code(Ok(3)), 3);
        assert_eq!(exit_code(Ok(0)), 0);
    }

    #[test]
    fn non_numeric_exponent_is_rejected() {
        assert!(Cli::try_parse_from(["zeta", "x"]).is_err());
    }
}
