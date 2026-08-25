use criterion::{criterion_group, criterion_main, Criterion};
use std::hint::black_box;
use std::io::sink;
use twin_primes::find_twin_primes;

fn bench_twin_primes(c: &mut Criterion) {
    let mut group = c.benchmark_group("twin_primes");
    group.bench_function("limit=1000", |b| {
        b.iter(|| find_twin_primes(black_box(1_000), &mut sink()))
    });
    group.bench_function("limit=10000", |b| {
        b.iter(|| find_twin_primes(black_box(10_000), &mut sink()))
    });
    group.bench_function("limit=100000", |b| {
        b.iter(|| find_twin_primes(black_box(100_000), &mut sink()))
    });
    group.finish();
}

criterion_group!(benches, bench_twin_primes);
criterion_main!(benches);
