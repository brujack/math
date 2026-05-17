use std::io::{self, Write};
use std::path::Path;
use std::process;

fn run<W: Write, E: Write>(
    _stdout: &mut W,
    _stderr: &mut E,
    _out_path: &Path,
    _limit: usize,
) -> io::Result<()> {
    Ok(())
}

#[cfg(not(tarpaulin_include))]
fn main() {
    if let Err(e) =
        run(&mut io::stdout().lock(), &mut io::stderr().lock(), &Path::new("amicable_1e0.txt"), 0)
    {
        eprintln!("error: {e}");
        process::exit(1);
    }
}
