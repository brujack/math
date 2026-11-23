use criterion::{Criterion, criterion_group, criterion_main};
use std::hint::black_box;

fn bench_placeholder(c: &mut Criterion) {
    let mut group = c.benchmark_group("zeta");
    group.bench_function("placeholder", |b| b.iter(|| black_box(1u64) + black_box(1u64)));
    group.finish();
}

criterion_group!(benches, bench_placeholder);
criterion_main!(benches);
