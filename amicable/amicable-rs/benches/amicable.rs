use amicable::proper_divisor_sum_sieve;
use criterion::{black_box, criterion_group, criterion_main, Criterion};

fn bench_amicable(c: &mut Criterion) {
    let mut group = c.benchmark_group("amicable");
    group.bench_function("limit=10000", |b| b.iter(|| proper_divisor_sum_sieve(black_box(10_000))));
    group.bench_function("limit=100000", |b| {
        b.iter(|| proper_divisor_sum_sieve(black_box(100_000)))
    });
    group.bench_function("limit=1000000", |b| {
        b.iter(|| proper_divisor_sum_sieve(black_box(1_000_000)))
    });
    group.finish();
}

criterion_group!(benches, bench_amicable);
criterion_main!(benches);
