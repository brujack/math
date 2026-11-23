use clap::Parser;

#[derive(Parser, Debug)]
#[command(
    name = "zeta",
    about = "Verify the Riemann Hypothesis up to height 10^N with certified interval arithmetic"
)]
struct Cli {
    /// N: verify all zeros with 0 < Im s <= 10^N (2-7)
    exponent: Option<u32>,
}

#[cfg(not(tarpaulin_include))]
fn main() {
    let cli = Cli::parse();
    let _ = cli.exponent;
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

    #[test]
    fn non_numeric_exponent_is_rejected() {
        assert!(Cli::try_parse_from(["zeta", "x"]).is_err());
    }
}
