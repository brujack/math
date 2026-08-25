use criterion::{criterion_group, criterion_main, Criterion};
use e::compute_e;
use std::hint::black_box;

fn bench_e(c: &mut Criterion) {
    let mut group = c.benchmark_group("e");
    group.bench_function("digits=100", |b| b.iter(|| compute_e(black_box(100))));
    group.bench_function("digits=1000", |b| b.iter(|| compute_e(black_box(1_000))));
    group.bench_function("digits=5000", |b| b.iter(|| compute_e(black_box(5_000))));
    group.finish();
}

criterion_group!(benches, bench_e);
criterion_main!(benches);
