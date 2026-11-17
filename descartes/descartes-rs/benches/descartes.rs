use criterion::{Criterion, criterion_group, criterion_main};
use descartes::descartes_fourth;
use std::hint::black_box;

fn bench_descartes(c: &mut Criterion) {
    let mut group = c.benchmark_group("descartes");
    group.bench_function("fourth", |b| {
        b.iter(|| descartes_fourth(black_box(2.0), black_box(3.0), black_box(6.0)))
    });
    group.finish();
}

criterion_group!(benches, bench_descartes);
criterion_main!(benches);
