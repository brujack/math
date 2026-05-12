use std::io::{self, BufRead, Write};
use std::path::Path;

use clap::Parser;

#[derive(Parser)]
#[command(name = "collatz", about = "Find Collatz chain record-setters up to 10^N")]
struct Cli {
    /// N: scans 1..10^N for chain-length records (1-12)
    exponent: Option<u32>,
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
