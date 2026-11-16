use clap::Parser;
use std::io::{self, Write};
use std::process;

use descartes::descartes_fourth;

/// Task 6 stub: the real CLI (packing and `--solve`) arrives in Task 9.
#[derive(Parser)]
#[command(
    about = "Curvatures tangent to three mutually tangent circles",
    allow_negative_numbers = true
)]
struct Args {
    /// Curvature of the first circle
    k1: f64,
    /// Curvature of the second circle
    k2: f64,
    /// Curvature of the third circle
    k3: f64,
}

/// Print the two fourth curvatures; return the process exit code
/// (0 ok, 1 no answer, 2 malformed input).
fn run<W: Write, E: Write>(stdout: &mut W, stderr: &mut E, k: [f64; 3]) -> io::Result<i32> {
    match descartes_fourth(k[0], k[1], k[2]) {
        Ok((plus, minus)) => {
            writeln!(stdout, "{plus}")?;
            writeln!(stdout, "{minus}")?;
            Ok(0)
        }
        Err(e) => {
            writeln!(stderr, "error: {e}")?;
            Ok(e.exit_code())
        }
    }
}

#[cfg(not(tarpaulin_include))]
fn main() {
    let args = Args::parse();
    match run(&mut io::stdout().lock(), &mut io::stderr().lock(), [args.k1, args.k2, args.k3]) {
        Ok(code) => process::exit(code),
        Err(e) => {
            eprintln!("error: {e}");
            process::exit(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::run;

    fn run_to_strings(k: [f64; 3]) -> (i32, String, String) {
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let code = run(&mut out, &mut err, k).unwrap();
        (code, String::from_utf8(out).unwrap(), String::from_utf8(err).unwrap())
    }

    #[test]
    fn run_prints_both_curvatures() {
        assert_eq!(run_to_strings([2.0, 3.0, 6.0]), (0, "23\n-1\n".into(), String::new()));
    }

    #[test]
    fn run_exits_1_with_message_when_no_circle_is_tangent() {
        let (code, out, err) = run_to_strings([1.0, 1.0, -2.0]);
        assert_eq!(code, 1);
        assert!(out.is_empty());
        assert!(err.starts_with("error: descartes_fourth(1, 1, -2)"), "{err}");
    }

    #[test]
    fn run_reports_write_failure() {
        struct Full;
        impl std::io::Write for Full {
            fn write(&mut self, _: &[u8]) -> std::io::Result<usize> {
                Err(std::io::Error::other("full"))
            }
            fn flush(&mut self) -> std::io::Result<()> {
                Ok(())
            }
        }
        assert!(run(&mut Full, &mut Vec::<u8>::new(), [2.0, 3.0, 6.0]).is_err());
    }
}
