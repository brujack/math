use criterion::{black_box, criterion_group, criterion_main, Criterion};
use sq::generate_squares;
use std::io::sink;

fn bench_sq(c: &mut Criterion) {
    let mut group = c.benchmark_group("sq");
    group
        .bench_function("max_digits=4", |b| b.iter(|| generate_squares(black_box(4), &mut sink())));
    group
        .bench_function("max_digits=6", |b| b.iter(|| generate_squares(black_box(6), &mut sink())));
    group
        .bench_function("max_digits=8", |b| b.iter(|| generate_squares(black_box(8), &mut sink())));
    group.finish();
}

criterion_group!(benches, bench_sq);
criterion_main!(benches);
