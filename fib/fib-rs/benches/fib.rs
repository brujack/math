use criterion::{black_box, criterion_group, criterion_main, Criterion};
use fib::generate_fibonacci;

fn bench_fib(c: &mut Criterion) {
    let mut group = c.benchmark_group("fib");
    group.bench_function("max_digits=100", |b| {
        b.iter(|| {
            let mut sink = std::io::sink();
            generate_fibonacci(black_box(100), &mut sink).unwrap()
        })
    });
    group.bench_function("max_digits=1000", |b| {
        b.iter(|| {
            let mut sink = std::io::sink();
            generate_fibonacci(black_box(1_000), &mut sink).unwrap()
        })
    });
    group.bench_function("max_digits=5000", |b| {
        b.iter(|| {
            let mut sink = std::io::sink();
            generate_fibonacci(black_box(5_000), &mut sink).unwrap()
        })
    });
    group.finish();
}

criterion_group!(benches, bench_fib);
criterion_main!(benches);
