use std::io::{self, BufRead, Write};
use std::path::{Path, PathBuf};

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

fn read_line_from<R: BufRead>(reader: &mut R) -> io::Result<String> {
    let mut line = String::new();
    reader.read_line(&mut line)?;
    Ok(line.trim().to_string())
}

fn prompt_n_with<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    err: &mut E,
) -> io::Result<u64> {
    loop {
        write!(out, "Enter N to compute N! : ")?;
        out.flush()?;
        let line = read_line_from(reader)?;
        match line.parse::<u64>() {
            Ok(n) => return Ok(n),
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
        None => prompt_n_with(reader, out, err)?,
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

#[cfg(not(tarpaulin_include))]
fn main() {
    let args: Vec<String> = std::env::args().collect();
    let n_arg = args.get(1).map(|s| s.as_str());
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
        assert_eq!(read_line_from(&mut r).unwrap(), "hello");
    }

    #[test]
    fn test_read_line_from_empty() {
        let mut r = io::Cursor::new(b"");
        assert_eq!(read_line_from(&mut r).unwrap(), "");
    }

    #[test]
    fn test_read_line_from_trims_whitespace() {
        let mut r = io::Cursor::new(b"  42  \n");
        assert_eq!(read_line_from(&mut r).unwrap(), "42");
    }

    // --- prompt_n_with ---

    #[test]
    fn test_prompt_n_valid() {
        let mut r = io::Cursor::new(b"10\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 10);
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("Enter N"), "stdout: {}", stdout);
    }

    #[test]
    fn test_prompt_n_zero() {
        let mut r = io::Cursor::new(b"0\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 0);
    }

    #[test]
    fn test_prompt_n_retry_on_non_numeric() {
        let mut r = io::Cursor::new(b"abc\n5\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 5);
        let stderr = String::from_utf8(err).unwrap();
        assert!(stderr.contains("Invalid input"), "stderr: {}", stderr);
    }

    #[test]
    fn test_prompt_n_retry_on_negative() {
        let mut r = io::Cursor::new(b"-1\n3\n");
        let mut out = Vec::new();
        let mut err = Vec::new();
        assert_eq!(prompt_n_with(&mut r, &mut out, &mut err).unwrap(), 3);
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
