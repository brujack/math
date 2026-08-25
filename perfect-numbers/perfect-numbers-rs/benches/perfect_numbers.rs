use criterion::{criterion_group, criterion_main, Criterion};
use perfect_numbers::generate_perfect_numbers;
use rug::ops::PowAssign;
use rug::Integer;
use std::hint::black_box;

fn bench_perfect_numbers(c: &mut Criterion) {
    let mut group = c.benchmark_group("perfect_numbers");
    group.bench_function("limit=10000", |b| {
        b.iter(|| generate_perfect_numbers(black_box(&Integer::from(10_000u32))))
    });
    group.bench_function("limit=1e19", |b| {
        b.iter(|| {
            let mut limit = Integer::from(10u32);
            limit.pow_assign(19u32);
            generate_perfect_numbers(black_box(&limit))
        })
    });
    group.bench_function("limit=1e40", |b| {
        b.iter(|| {
            let mut limit = Integer::from(10u32);
            limit.pow_assign(40u32);
            generate_perfect_numbers(black_box(&limit))
        })
    });
    group.finish();
}

criterion_group!(benches, bench_perfect_numbers);
criterion_main!(benches);
