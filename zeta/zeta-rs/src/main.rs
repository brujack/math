use std::io::{self, BufRead, Write};

use clap::Parser;
use zeta::config::VerifyConfig;
use zeta::zfun::{SELF_CHECK_PREC, ZEvaluator, self_check};

/// Smallest and largest accepted N (the height is 10^N).
const MIN_N: u32 = 2;
const MAX_N: u32 = 7;

#[derive(Parser, Debug)]
#[command(
    name = "zeta",
    about = "Verify the Riemann Hypothesis up to height 10^N with certified interval arithmetic"
)]
struct Cli {
    /// N: target height 10^N (2-7); prompted for when omitted
    ///
    /// Kept as text so that every invalid N exits 1 (R1), not clap's usage code 2.
    exponent: Option<String>,
}

/// Parses N and checks the 2-7 range.
fn parse_n(text: &str) -> Option<u32> {
    text.trim().parse::<u32>().ok().filter(|n| (MIN_N..=MAX_N).contains(n))
}

/// Prompts for N until valid. `Ok(Err(code))` means end the run with exit `code`
/// (end of input, already reported on `err`).
fn prompt_n<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    err: &mut E,
) -> io::Result<Result<u32, i32>> {
    loop {
        write!(out, "Enter N (verifies RH up to height 10^N, {MIN_N}-{MAX_N}): ")?;
        out.flush()?;
        let mut line = String::new();
        if reader.read_line(&mut line)? == 0 {
            writeln!(out)?;
            writeln!(err, "Error: no input; pass SIZE as an argument (e.g. zeta 3).")?;
            return Ok(Err(1));
        }
        match parse_n(&line) {
            Some(n) => return Ok(Ok(n)),
            None => writeln!(out, "N must be between {MIN_N} and {MAX_N}.")?,
        }
    }
}

/// Runs the CLI against injectable streams. `self_check` is the runtime canary of
/// the Z paths; production passes the real one.
fn run<R, W, E, C>(
    cli: &Cli,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    self_check: C,
) -> io::Result<i32>
where
    R: BufRead,
    W: Write,
    E: Write,
    C: FnOnce() -> Result<(), String>,
{
    let n = match &cli.exponent {
        Some(text) => match parse_n(text) {
            Some(n) => n,
            None => {
                writeln!(err, "Error: N must be between {MIN_N} and {MAX_N}.")?;
                return Ok(1);
            }
        },
        None => match prompt_n(reader, out, err)? {
            Ok(n) => n,
            Err(code) => return Ok(code),
        },
    };
    if n == MAX_N {
        writeln!(
            err,
            "Warning: N=7 writes about 1.5 GB (about 2.2 GB with --refine) and may take many hours."
        )?;
    }
    if let Err(reason) = self_check() {
        writeln!(err, "self-check failed: {reason}")?;
        return Ok(5);
    }
    writeln!(out, "RH NOT verified up to {}: zero isolation is not implemented yet", 10u64.pow(n))?;
    Ok(3)
}

/// The self-check of both Z paths at `SELF_CHECK_PREC`; production passes default
/// settings (a Gabcke multiplier above 1 always fails it).
fn self_check_with(cfg: &VerifyConfig) -> Result<(), String> {
    let z = ZEvaluator::new(SELF_CHECK_PREC, cfg).map_err(|e| e.to_string())?;
    self_check(&z).map_err(|e| e.to_string())
}

/// Maps a `run` outcome to a process exit code; a failed stderr write is exit 1.
fn exit_code(result: std::io::Result<i32>) -> i32 {
    result.unwrap_or(1)
}

#[cfg(not(tarpaulin_include))]
fn main() {
    let cli = Cli::parse();
    let (stdin, stdout, stderr) = (io::stdin(), io::stdout(), io::stderr());
    let result = run(&cli, &mut stdin.lock(), &mut stdout.lock(), &mut stderr.lock(), || {
        self_check_with(&VerifyConfig::default())
    });
    std::process::exit(exit_code(result));
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
        assert_eq!(Cli::try_parse_from(["zeta", "3"]).unwrap().exponent.as_deref(), Some("3"));
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

    fn run_args(args: &[&str], input: &str) -> (i32, String, String) {
        run_with(args, input, || Ok(()))
    }

    fn run_with<C: FnOnce() -> Result<(), String>>(
        args: &[&str],
        input: &str,
        check: C,
    ) -> (i32, String, String) {
        let mut argv = vec!["zeta"];
        argv.extend_from_slice(args);
        let cli = Cli::try_parse_from(argv).unwrap();
        let (mut out, mut err) = (Vec::new(), Vec::new());
        let code = run(&cli, &mut input.as_bytes(), &mut out, &mut err, check).unwrap();
        (code, String::from_utf8(out).unwrap(), String::from_utf8(err).unwrap())
    }

    #[test]
    fn out_of_range_or_non_numeric_n_exits_1_with_message() {
        for arg in ["0", "1", "8", "99", "abc", "3x", "3.5", ""] {
            let (code, out, err) = run_args(&[arg], "");
            assert_eq!(code, 1, "{arg:?}");
            assert_eq!(err, "Error: N must be between 2 and 7.\n", "{arg:?}");
            assert!(out.is_empty(), "{arg:?}: {out:?}");
        }
    }

    const PROMPT: &str = "Enter N (verifies RH up to height 10^N, 2-7): ";

    #[test]
    fn end_of_input_at_prompt_prints_newline_and_exits_1() {
        let (code, out, err) = run_args(&[], "");
        assert_eq!(code, 1);
        assert_eq!(out, format!("{PROMPT}\n"));
        assert_eq!(err, "Error: no input; pass SIZE as an argument (e.g. zeta 3).\n");
    }

    #[test]
    fn prompt_reprompts_on_invalid_input_then_accepts() {
        let (code, out, err) = run_args(&[], "abc\n8\n1\n 3 \n");
        assert_eq!(code, 3);
        let expected_prefix = format!(
            "{PROMPT}N must be between 2 and 7.\n{PROMPT}N must be between 2 and 7.\n\
             {PROMPT}N must be between 2 and 7.\n{PROMPT}"
        );
        assert!(out.starts_with(&expected_prefix), "{out:?}");
        assert!(!err.contains("no input"), "{err:?}");
    }

    #[test]
    fn prompt_accepts_both_range_ends() {
        for n in ["2", "7"] {
            let (code, out, _) = run_args(&[], &format!("{n}\n"));
            assert_eq!(code, 3, "{n}");
            assert!(out.starts_with(PROMPT), "{n}");
        }
    }

    #[test]
    fn prompt_is_not_shown_when_n_is_an_argument() {
        let (_, out, _) = run_args(&["3"], "");
        assert!(!out.contains("Enter N"), "{out:?}");
    }

    #[test]
    fn prompt_flush_failure_is_an_error() {
        let cli = Cli::try_parse_from(["zeta"]).unwrap();
        let result =
            run(&cli, &mut "2\n".as_bytes(), &mut FailingWriter, &mut Vec::new(), || Ok(()));
        assert!(result.is_err());
        assert_eq!(exit_code(result), 1);
    }

    const WARNING: &str =
        "Warning: N=7 writes about 1.5 GB (about 2.2 GB with --refine) and may take many hours.\n";

    #[test]
    fn passing_self_check_ends_with_not_verified_and_exit_3() {
        for (n, t) in [("2", "100"), ("3", "1000"), ("6", "1000000"), ("7", "10000000")] {
            let (code, out, _) = run_args(&[n], "");
            assert_eq!(code, 3, "{n}");
            assert_eq!(
                out,
                format!("RH NOT verified up to {t}: zero isolation is not implemented yet\n"),
                "{n}"
            );
        }
    }

    #[test]
    fn failing_self_check_exits_5_and_reports_on_stderr() {
        let (code, out, err) = run_with(&["3"], "", || Err("fake reason".to_string()));
        assert_eq!(code, 5);
        assert_eq!(err, "self-check failed: fake reason\n");
        assert!(out.is_empty(), "{out:?}");
    }

    #[test]
    fn self_check_runs_exactly_once_and_only_for_a_valid_n() {
        let calls = std::cell::Cell::new(0u32);
        let counting = || {
            calls.set(calls.get() + 1);
            Ok(())
        };
        run_with(&["3"], "", counting);
        assert_eq!(calls.get(), 1);
        for bad in [vec!["1"], vec!["8"], vec!["x"], vec![]] {
            run_with(&bad, "", counting);
            assert_eq!(calls.get(), 1, "{bad:?}: self-check ran without a valid N");
        }
    }

    #[test]
    fn n_7_warns_on_stderr_before_the_self_check_and_other_n_do_not() {
        let (_, out, err) = run_with(&["7"], "", || Err("x".to_string()));
        assert_eq!(err, format!("{WARNING}self-check failed: x\n"));
        assert!(!out.contains("Warning"), "{out:?}");
        let (_, _, err) = run_args(&[], "7\n");
        assert_eq!(err, WARNING, "prompted N=7 also warns");
        for n in ["2", "3", "4", "5", "6"] {
            let (_, _, err) = run_args(&[n], "");
            assert!(err.is_empty(), "{n}: {err:?}");
        }
    }

    #[test]
    fn no_path_claims_verification() {
        let mut outputs = Vec::new();
        for n in ["0", "2", "3", "7", "8", "x"] {
            outputs.push(run_args(&[n], ""));
            outputs.push(run_with(&[n], "", || Err("boom".to_string())));
        }
        outputs.push(run_args(&[], ""));
        outputs.push(run_args(&[], "9\n3\n"));
        for (_, out, err) in outputs {
            for text in [out, err] {
                assert!(!text.contains("RH holds"), "{text:?}");
                assert!(!text.contains("RH verified"), "{text:?}");
            }
        }
    }

    #[test]
    fn write_failures_on_the_work_path_are_errors() {
        let cli = Cli::try_parse_from(["zeta", "3"]).unwrap();
        let result = run(&cli, &mut "".as_bytes(), &mut FailingWriter, &mut Vec::new(), || Ok(()));
        assert!(result.is_err());
        let cli = Cli::try_parse_from(["zeta", "7"]).unwrap();
        let result = run(&cli, &mut "".as_bytes(), &mut Vec::new(), &mut FailingWriter, || Ok(()));
        assert!(result.is_err());
        let cli = Cli::try_parse_from(["zeta", "3"]).unwrap();
        let result =
            run(&cli, &mut "".as_bytes(), &mut Vec::new(), &mut FailingWriter, || Err("e".into()));
        assert!(result.is_err());
        let cli = Cli::try_parse_from(["zeta", "9"]).unwrap();
        let result = run(&cli, &mut "".as_bytes(), &mut Vec::new(), &mut FailingWriter, || Ok(()));
        assert!(result.is_err());
    }

    #[test]
    fn real_self_check_passes_by_default_and_fails_with_a_widened_bound() {
        assert_eq!(self_check_with(&VerifyConfig::default()), Ok(()));
        let widened = VerifyConfig::new(2.0, 512, 40, true).unwrap();
        let err = self_check_with(&widened).unwrap_err();
        assert!(err.contains("Riemann-Siegel enclosure wider"), "{err}");
    }

    #[test]
    fn exit_code_passes_through_success_codes() {
        assert_eq!(exit_code(Ok(3)), 3);
        assert_eq!(exit_code(Ok(0)), 0);
    }
}
