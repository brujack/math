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
    if n % 2 == 0 { n / 2 } else { 3 * n + 1 }
}

fn chain_length(n: u64, cache: &mut Vec<u32>, limit: u64) -> u32 {
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

fn run<R: BufRead, W: Write, E: Write>(
    _cli: Cli,
    _reader: &mut R,
    _out: &mut W,
    _err: &mut E,
    _dir: &Path,
) -> io::Result<i32> {
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

    #[test]
    fn test_stub_compiles() {
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut err_buf = Vec::new();
        let mut reader = Cursor::new("");
        let code = run(Cli { exponent: Some(1) }, &mut reader, &mut out, &mut err_buf, dir.path()).unwrap();
        assert_eq!(code, 0);
    }
}
