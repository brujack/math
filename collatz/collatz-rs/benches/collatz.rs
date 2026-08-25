use collatz::generate_records;
use criterion::{criterion_group, criterion_main, Criterion};
use std::hint::black_box;

fn bench_collatz(c: &mut Criterion) {
    let mut group = c.benchmark_group("collatz");
    group.bench_function("limit=1000", |b| {
        b.iter(|| {
            let mut sink = std::io::sink();
            generate_records(black_box(1_000), &mut sink, &mut std::io::sink()).unwrap()
        })
    });
    group.bench_function("limit=10000", |b| {
        b.iter(|| {
            let mut sink = std::io::sink();
            generate_records(black_box(10_000), &mut sink, &mut std::io::sink()).unwrap()
        })
    });
    group.bench_function("limit=100000", |b| {
        b.iter(|| {
            let mut sink = std::io::sink();
            generate_records(black_box(100_000), &mut sink, &mut std::io::sink()).unwrap()
        })
    });
    group.finish();
}

criterion_group!(benches, bench_collatz);
criterion_main!(benches);
