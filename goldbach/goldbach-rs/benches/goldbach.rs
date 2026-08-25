use std::io;

use criterion::{criterion_group, criterion_main, Criterion};
use goldbach::{build_sieve, goldbach_pairs};
use std::hint::black_box;

fn bench_goldbach(c: &mut Criterion) {
    let mut group = c.benchmark_group("goldbach");
    group.bench_function("sieve=10000", |b| b.iter(|| build_sieve(black_box(10_000))));
    group.bench_function("sieve=100000", |b| b.iter(|| build_sieve(black_box(100_000))));
    group.bench_function("sieve=1000000", |b| b.iter(|| build_sieve(black_box(1_000_000))));
    group.bench_function("pairs=10000", |b| {
        let sieve = build_sieve(10_000);
        b.iter(|| goldbach_pairs(black_box(10_000), &sieve, &mut io::sink()).unwrap())
    });
    group.finish();
}

criterion_group!(benches, bench_goldbach);
criterion_main!(benches);
