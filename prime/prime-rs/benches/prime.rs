use criterion::{black_box, criterion_group, criterion_main, Criterion};
use prime::find_primes;

fn bench_prime(c: &mut Criterion) {
    let mut group = c.benchmark_group("prime");
    group.bench_function("limit=10000", |b| {
        b.iter(|| {
            let mut sink = std::io::sink();
            find_primes(black_box(10_000), &mut sink).unwrap()
        })
    });
    group.bench_function("limit=100000", |b| {
        b.iter(|| {
            let mut sink = std::io::sink();
            find_primes(black_box(100_000), &mut sink).unwrap()
        })
    });
    group.bench_function("limit=1000000", |b| {
        b.iter(|| {
            let mut sink = std::io::sink();
            find_primes(black_box(1_000_000), &mut sink).unwrap()
        })
    });
    group.finish();
}

criterion_group!(benches, bench_prime);
criterion_main!(benches);
