use std::io::{self, Write};

pub fn collatz_next(n: u64) -> u64 {
    if n.is_multiple_of(2) {
        n / 2
    } else {
        3 * n + 1
    }
}

pub fn chain_length(n: u64, cache: &mut [u32], limit: u64) -> u32 {
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

pub fn generate_records<W: Write, E: Write>(
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
