use criterion::{black_box, criterion_group, criterion_main, Criterion};
use factorial::calculate_factorial;

fn bench_factorial(c: &mut Criterion) {
    let mut group = c.benchmark_group("factorial");
    group.bench_function("n=100", |b| b.iter(|| calculate_factorial(black_box(100))));
    group.bench_function("n=1000", |b| b.iter(|| calculate_factorial(black_box(1_000))));
    group.bench_function("n=5000", |b| b.iter(|| calculate_factorial(black_box(5_000))));
    group.finish();
}

criterion_group!(benches, bench_factorial);
criterion_main!(benches);
