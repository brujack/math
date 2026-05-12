use std::io::{self, BufRead, Write};
use std::path::Path;

use clap::Parser;

#[derive(Parser)]
#[command(name = "collatz", about = "Find Collatz chain record-setters up to 10^N")]
struct Cli {
    /// N: scans 1..10^N for chain-length records (1-12)
    exponent: Option<u32>,
}

// ---------------------------------------------------------------------------
// Core algorithm
// ---------------------------------------------------------------------------

fn collatz_next(n: u64) -> u64 {
    if n.is_multiple_of(2) {
        n / 2
    } else {
        3 * n + 1
    }
}

fn chain_length(n: u64, cache: &mut [u32], limit: u64) -> u32 {
    let mut path: Vec<u64> = Vec::new();
    let mut curr = n;
    loop {
        if curr <= limit && cache[curr as usize] != 0 {
            break;
        }
        path.push(curr);
        curr = collatz_next(curr);
    }
    let base = cache[curr as usize];
    for (i, &val) in path.iter().rev().enumerate() {
        if val <= limit {
            cache[val as usize] = base + i as u32 + 1;
        }
    }
    cache[n as usize] - 1
}

fn generate_records<W: Write, E: Write>(
    limit: u64,
    out: &mut W,
    _err: &mut E,
) -> io::Result<Vec<(u64, u32)>> {
    let mut cache = vec![0u32; (limit + 1) as usize];
    cache[1] = 1;
    let mut max_len: i64 = -1;
    let mut records = Vec::new();
    for n in 1..=limit {
        let length = chain_length(n, &mut cache, limit);
        if length as i64 > max_len {
            max_len = length as i64;
            writeln!(out, "{n} {length}")?;
            records.push((n, length));
        }
    }
    Ok(records)
}

// ---------------------------------------------------------------------------
// I/O helpers
// ---------------------------------------------------------------------------

fn prompt_n<R: BufRead, W: Write>(reader: &mut R, out: &mut W) -> io::Result<u64> {
    loop {
        write!(out, "Enter N (scans 1..10^N for Collatz records, max 12): ")?;
        out.flush()?;
        let mut line = String::new();
        reader.read_line(&mut line)?;
        match line.trim().parse::<u64>() {
            Ok(v) if (1..=12).contains(&v) => return Ok(v),
            _ => writeln!(out, "N must be between 1 and 12.")?,
        }
    }
}

// ---------------------------------------------------------------------------
// Orchestration
// ---------------------------------------------------------------------------

fn run<R: BufRead, W: Write, E: Write>(
    cli: Cli,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    dir: &Path,
) -> io::Result<i32> {
    let exp: u64 = match cli.exponent {
        Some(v) => {
            if !(1..=12).contains(&v) {
                writeln!(err, "Error: N must be between 1 and 12.")?;
                return Ok(1);
            }
            if v > 9 {
                writeln!(err, "Warning: N={v} may require significant time and memory.")?;
            }
            v as u64
        }
        None => prompt_n(reader, out)?,
    };

    let limit = 10u64.pow(exp as u32);
    writeln!(out, "Collatz Record Finder (Rust)")?;
    writeln!(out, "{}", "=".repeat(40))?;
    writeln!(out, "Scanning 1..10^{exp} = {limit} for chain-length records")?;
    writeln!(out)?;

    let records = generate_records(limit, out, err)?;

    let path = dir.join(format!("collatz_1e{exp}.txt"));
    let mut file = std::fs::File::create(&path)?;
    for (n, length) in &records {
        writeln!(file, "{n} {length}")?;
    }

    let count = records.len();
    writeln!(out)?;
    writeln!(out, "Found {count} records. Saved to {}", path.display())?;
    Ok(0)
}

#[cfg(not(tarpaulin_include))]
fn main() {
    let cli = Cli::parse();
    let stdin = io::stdin();
    let stdout = io::stdout();
    let stderr = io::stderr();
    let mut reader = stdin.lock();
    let mut out = stdout.lock();
    let mut err = stderr.lock();
    let cwd = std::env::current_dir().expect("cwd unavailable");
    let code = run(cli, &mut reader, &mut out, &mut err, &cwd).expect("io error");
    std::process::exit(code);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    use tempfile::tempdir;

    struct FailWriter;
    impl Write for FailWriter {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::other("injected write failure"))
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    fn make_cache(limit: u64) -> Vec<u32> {
        let mut cache = vec![0u32; (limit + 1) as usize];
        cache[1] = 1;
        cache
    }

    // --- collatz_next ---
    #[test]
    fn test_collatz_next_even() {
        assert_eq!(collatz_next(6), 3);
    }

    #[test]
    fn test_collatz_next_odd() {
        assert_eq!(collatz_next(3), 10);
    }

    // --- chain_length ---
    #[test]
    fn test_chain_length_n1() {
        let mut cache = make_cache(10);
        assert_eq!(chain_length(1, &mut cache, 10), 0);
    }

    #[test]
    fn test_chain_length_n2() {
        let mut cache = make_cache(10);
        assert_eq!(chain_length(2, &mut cache, 10), 1);
    }

    #[test]
    fn test_chain_length_n3() {
        let mut cache = make_cache(100);
        assert_eq!(chain_length(3, &mut cache, 100), 7);
    }

    #[test]
    fn test_chain_length_n27() {
        let mut cache = make_cache(10_000);
        assert_eq!(chain_length(27, &mut cache, 10_000), 111);
    }

    #[test]
    fn test_chain_length_cache_reuse() {
        let mut cache = make_cache(100);
        chain_length(3, &mut cache, 100);
        assert_ne!(cache[3], 0);
        assert_eq!(chain_length(3, &mut cache, 100), 7);
    }

    #[test]
    fn test_chain_length_value_exceeds_limit() {
        // n=3's chain passes through 10, 16, 8 which exceed limit=5
        let mut cache = make_cache(5);
        assert_eq!(chain_length(3, &mut cache, 5), 7);
    }

    // --- generate_records ---
    #[test]
    fn test_generate_records_limit_1() {
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let records = generate_records(1, &mut out, &mut err_buf).unwrap();
        assert_eq!(records, vec![(1u64, 0u32)]);
        assert_eq!(String::from_utf8_lossy(&out).trim(), "1 0");
    }

    #[test]
    fn test_generate_records_limit_10() {
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let records = generate_records(10, &mut out, &mut err_buf).unwrap();
        assert_eq!(records[0], (1, 0));
        assert_eq!(records[1], (2, 1));
        assert_eq!(records[2], (3, 7));
        assert_eq!(records[3], (6, 8));
        assert_eq!(records[4], (7, 16));
        assert_eq!(records[5], (9, 19));
    }

    // --- run ---
    #[test]
    fn test_run_n0_returns_1() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(0) }, &mut reader, &mut out, &mut err_buf, dir.path())
            .unwrap();
        assert_eq!(code, 1);
        assert!(String::from_utf8_lossy(&err_buf).contains("between 1 and 12"));
    }

    #[test]
    fn test_run_n13_returns_1() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(13) }, &mut reader, &mut out, &mut err_buf, dir.path())
            .unwrap();
        assert_eq!(code, 1);
    }

    #[test]
    fn test_run_n1_creates_file() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(1) }, &mut reader, &mut out, &mut err_buf, dir.path())
            .unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("collatz_1e1.txt");
        assert!(path.exists());
        let content = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<&str> = content.trim().lines().collect();
        assert_eq!(lines[0], "1 0");
        assert_eq!(lines[2], "3 7");
        assert_eq!(lines.len(), 6);
    }

    #[test]
    fn test_run_no_arg_prompts() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("1\n");
        let code =
            run(Cli { exponent: None }, &mut reader, &mut out, &mut err_buf, dir.path()).unwrap();
        assert_eq!(code, 0);
        assert!(String::from_utf8_lossy(&out).contains("Enter N"));
    }

    #[test]
    fn test_run_err_on_stdout_failure() {
        let dir = tempdir().unwrap();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let result =
            run(Cli { exponent: Some(1) }, &mut reader, &mut FailWriter, &mut err_buf, dir.path());
        assert!(result.is_err());
    }

    #[test]
    fn test_run_err_on_stderr_failure() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut reader = Cursor::new("");
        let result =
            run(Cli { exponent: Some(0) }, &mut reader, &mut out, &mut FailWriter, dir.path());
        assert!(result.is_err());
    }

    #[test]
    fn test_run_invalid_stdin_prompt() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("0\nabc\n5\n");
        let code =
            run(Cli { exponent: None }, &mut reader, &mut out, &mut err_buf, dir.path()).unwrap();
        assert_eq!(code, 0);
    }
}
