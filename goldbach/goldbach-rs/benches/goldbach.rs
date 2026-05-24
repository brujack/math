use criterion::{black_box, criterion_group, criterion_main, Criterion};
use goldbach::{build_sieve, goldbach_pairs};
use std::io::sink;

fn bench_goldbach(c: &mut Criterion) {
    let mut group = c.benchmark_group("goldbach");
    group.bench_function("limit=100", |b| {
        b.iter(|| {
            let sieve = build_sieve(black_box(100));
            goldbach_pairs(black_box(100), &sieve, &mut sink())
        })
    });
    group.bench_function("limit=1000", |b| {
        b.iter(|| {
            let sieve = build_sieve(black_box(1_000));
            goldbach_pairs(black_box(1_000), &sieve, &mut sink())
        })
    });
    group.bench_function("limit=10000", |b| {
        b.iter(|| {
            let sieve = build_sieve(black_box(10_000));
            goldbach_pairs(black_box(10_000), &sieve, &mut sink())
        })
    });
    group.finish();
}

criterion_group!(benches, bench_goldbach);
criterion_main!(benches);
