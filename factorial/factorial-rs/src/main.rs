use std::io::{self, BufRead, Write};
use std::path::{Path, PathBuf};

use clap::Parser;

use factorial::calculate_factorial;

fn fmt_int(n: u64) -> String {
    let s = n.to_string();
    let mut result = String::new();
    let chars: Vec<char> = s.chars().collect();
    let len = chars.len();
    for (i, &c) in chars.iter().enumerate() {
        if i > 0 && (len - i).is_multiple_of(3) {
            result.push(',');
        }
        result.push(c);
    }
    result
}

/// Reads one trimmed line; `None` means end of input (distinct from a blank line).
fn read_line_from<R: BufRead>(reader: &mut R) -> io::Result<Option<String>> {
    let mut line = String::new();
    if reader.read_line(&mut line)? == 0 {
        return Ok(None);
    }
    Ok(Some(line.trim().to_string()))
}

/// Outer `Err(code)` is the exit code to return when input ended before a valid answer.
fn prompt_n_with<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    err: &mut E,
) -> io::Result<Result<u64, i32>> {
    loop {
        write!(out, "Enter N to compute N! : ")?;
        out.flush()?;
        let Some(line) = read_line_from(reader)? else {
            writeln!(out)?;
            writeln!(err, "Error: no input; pass SIZE as an argument (e.g. factorial 1000).")?;
            return Ok(Err(1));
        };
        match line.parse::<u64>() {
            Ok(n) => return Ok(Ok(n)),
            Err(_) => {
                writeln!(err, "Invalid input '{}'. Please enter a non-negative integer.", line)?
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Orchestrator
// ---------------------------------------------------------------------------

fn run<R: BufRead, W: Write, E: Write>(
    n_arg: Option<&str>,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    dir: &Path,
) -> io::Result<i32> {
    let n = match n_arg {
        Some(s) => match s.parse::<u64>() {
            Ok(v) => v,
            Err(_) => {
                writeln!(err, "Error: '{}' is not a valid non-negative integer", s)?;
                return Ok(1);
            }
        },
        None => match prompt_n_with(reader, out, err)? {
            Ok(n) => n,
            Err(code) => return Ok(code),
        },
    };

    writeln!(
        err,
        "Backend: prime swing / rug+GMP / rayon ({} threads)",
        rayon::current_num_threads()
    )?;
    writeln!(err, "Computing {}! ...", fmt_int(n))?;
    let start = std::time::Instant::now();
    let result = calculate_factorial(n);
    let elapsed = start.elapsed();
    writeln!(err, "Computed in {:.2}s", elapsed.as_secs_f64())?;

    let digits_str = result.to_string_radix(10);
    let digit_count = digits_str.len();
    let path = dir.join(format!("factorial_{}.txt", n));

    writeln!(err, "Writing {} digits to {} ...", fmt_int(digit_count as u64), path.display())?;
    let write_start = std::time::Instant::now();
    std::fs::write(&path, &digits_str)?;
    let write_elapsed = write_start.elapsed();
    writeln!(
        err,
        "{} digits written to {} in {:.2}s",
        fmt_int(digit_count as u64),
        path.display(),
        write_elapsed.as_secs_f64()
    )?;

    Ok(0)
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

/// Command-line arguments; `n` stays a string so `run` keeps its own parse error message.
#[derive(Parser, Debug)]
#[command(version, about = "Compute N! with prime swing, GMP and rayon")]
struct Cli {
    /// N to compute N! for (prompted for when omitted)
    #[arg(value_name = "N", allow_hyphen_values = true)]
    n: Option<String>,
}

#[cfg(not(tarpaulin_include))]
fn main() {
    let cli = Cli::parse();
    let n_arg = cli.n.as_deref();
    let stdin = io::stdin();
    let mut reader = stdin.lock();
    let stdout = io::stdout();
    let mut out = stdout.lock();
    let stderr = io::stderr();
    let mut err = stderr.lock();
    let dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let code = run(n_arg, &mut reader, &mut out, &mut err, &dir).unwrap_or(1);
    std::process::exit(code);
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;
    use tempfile::tempdir;

    // --- fmt_int ---

    #[test]
    fn test_fmt_int_zero() {
        assert_eq!(fmt_int(0), "0");
    }

    #[test]
    fn test_fmt_int_sub_thousand() {
        assert_eq!(fmt_int(999), "999");
    }

    #[test]
    fn test_fmt_int_thousands() {
        assert_eq!(fmt_int(1000), "1,000");
    }

    #[test]
    fn test_fmt_int_millions() {
        assert_eq!(fmt_int(1_234_567), "1,234,567");
    }

    #[test]
    fn test_fmt_int_large() {
        assert_eq!(fmt_int(1_000_000_000), "1,000,000,000");
    }

    // --- read_line_from ---

    #[test]
    fn test_read_line_from_trims_newline() {
        let mut r = io::Cursor::new(b"hello\n");
        assert_eq!(read_line_from(&mut r).unwrap(), Some("hello".to_string()));
    }

    #[test]
    fn test_read_line_from_empty() {
        let mut r = io::Cursor::new(b"");
        assert_eq!(read_line_from(&mut r).unwrap(), None);
    }

    #[test]
    fn test_read_line_from_trims_whitespace() {
        let mut r = io::Cursor::new(b"  42  \n");
        assert_eq!(read_line_from(&mut r).unwrap(), Some("42".to_string()));
    }

    // --- prompt_n_with ---

    #[test]
    fn test_prompt_n_valid() {
        let mut r = io::Cursor::new(b"10\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), Ok(10));
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("Enter N"), "stdout: {}", stdout);
    }

    #[test]
    fn test_prompt_n_zero() {
        let mut r = io::Cursor::new(b"0\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), Ok(0));
    }

    #[test]
    fn test_prompt_n_retry_on_non_numeric() {
        let mut r = io::Cursor::new(b"abc\n5\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), Ok(5));
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("Invalid input"), "stderr: {}", stderr);
    }

    #[test]
    fn test_prompt_n_retry_on_negative() {
        let mut r = io::Cursor::new(b"-1\n3\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), Ok(3));
    }

    // --- run ---

    #[test]
    fn test_run_invalid_arg_exits_one() {
        let dir = tempdir().unwrap();
        let mut r = io::Cursor::new(b"" as &[u8]);
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(Some("abc"), &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 1);
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("not a valid"), "stderr: {}", stderr);
    }

    #[test]
    fn test_run_valid_arg_creates_file() {
        let dir = tempdir().unwrap();
        let mut r = io::Cursor::new(b"" as &[u8]);
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(Some("10"), &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("factorial_10.txt");
        assert!(path.exists());
        let content = std::fs::read_to_string(&path).unwrap();
        assert_eq!(content.trim(), "3628800");
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("digits written"), "stderr: {}", stderr);
    }

    #[test]
    fn test_run_no_arg_prompts() {
        let dir = tempdir().unwrap();
        let mut r = io::Cursor::new(b"5\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(None, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        assert!(dir.path().join("factorial_5.txt").exists());
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("Enter N"), "stdout: {}", stdout);
    }

    #[test]
    fn test_run_n_0_creates_file() {
        let dir = tempdir().unwrap();
        let mut r = io::Cursor::new(b"" as &[u8]);
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(Some("0"), &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("factorial_0.txt");
        assert!(path.exists());
        let content = std::fs::read_to_string(&path).unwrap();
        assert_eq!(content.trim(), "1");
    }

    #[test]
    fn test_run_idempotent() {
        let dir = tempdir().unwrap();
        for _ in 0..2 {
            let mut r = io::Cursor::new(b"" as &[u8]);
            let mut out = Vec::new();
            let mut err = Vec::new();
            let code = run(Some("3"), &mut r, &mut out, &mut err, dir.path()).unwrap();
            assert_eq!(code, 0);
        }
        let content = std::fs::read_to_string(dir.path().join("factorial_3.txt")).unwrap();
        assert_eq!(content.trim(), "6");
    }

    // --- end of input at the prompt ---

    const NO_INPUT_LINE: &str =
        "Error: no input; pass SIZE as an argument (e.g. factorial 1000).\n";

    #[test]
    fn prompt_eof_at_prompt_exits_1_with_no_input_message() {
        let dir = tempdir().unwrap();
        let mut r = io::Cursor::new(b"" as &[u8]);
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(None, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 1);
        assert_eq!(String::from_utf8(out).unwrap(), "Enter N to compute N! : \n");
        assert_eq!(String::from_utf8(err).unwrap(), NO_INPUT_LINE);
    }

    #[test]
    fn prompt_eof_after_a_rejected_answer_exits_1() {
        let dir = tempdir().unwrap();
        let mut r = io::Cursor::new(b"abc\n" as &[u8]);
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = run(None, &mut r, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 1);
        let expected =
            format!("Invalid input 'abc'. Please enter a non-negative integer.\n{}", NO_INPUT_LINE);
        assert_eq!(String::from_utf8(err).unwrap(), expected);
    }

    #[test]
    fn prompt_eof_read_line_from_eof_differs_from_blank_line() {
        assert_eq!(read_line_from(&mut io::Cursor::new("")).unwrap(), None);
        assert_eq!(read_line_from(&mut io::Cursor::new("\n")).unwrap(), Some(String::new()));
    }

    proptest! {
        #[test]
        fn prop_generate_succeeds(n in 1u64..=20u64) {
            let result = calculate_factorial(n);
            prop_assert!(result > 0u64);
        }
    }

    struct FailWriter;

    impl std::io::Write for FailWriter {
        fn write(&mut self, _buf: &[u8]) -> std::io::Result<usize> {
            Err(std::io::Error::other("injected write failure"))
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn run_returns_err_on_stdout_failure() {
        let dir = tempdir().unwrap();
        let mut err = Vec::new();
        let mut reader = std::io::Cursor::new("5\n");
        let result = run(None, &mut reader, &mut FailWriter, &mut err, dir.path());
        assert!(result.is_err());
    }

    #[test]
    fn run_returns_err_on_stderr_failure() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut reader = std::io::Cursor::new("");
        let result = run(Some("abc"), &mut reader, &mut out, &mut FailWriter, dir.path());
        assert!(result.is_err());
    }
}
