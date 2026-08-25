use std::io;

use criterion::{criterion_group, criterion_main, Criterion};
use sq::generate_squares;
use std::hint::black_box;

fn bench_sq(c: &mut Criterion) {
    let mut group = c.benchmark_group("sq");
    group.bench_function("max_digits=1", |b| {
        b.iter(|| generate_squares(black_box(1), &mut io::sink()).unwrap())
    });
    group.bench_function("max_digits=2", |b| {
        b.iter(|| generate_squares(black_box(2), &mut io::sink()).unwrap())
    });
    group.bench_function("max_digits=3", |b| {
        b.iter(|| generate_squares(black_box(3), &mut io::sink()).unwrap())
    });
    group.finish();
}

criterion_group!(benches, bench_sq);
criterion_main!(benches);
