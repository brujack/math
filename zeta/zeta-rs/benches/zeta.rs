use criterion::{Criterion, criterion_group, criterion_main};
use std::hint::black_box;
use zeta::config::VerifyConfig;
use zeta::zfun::{RealZ, ZSource};

fn bench_z(c: &mut Criterion) {
    let mut group = c.benchmark_group("zeta");
    let evaluator =
        RealZ::new(&VerifyConfig::default()).expect("the default configuration builds every rung");
    for t in [1e4, 1e6] {
        group.bench_function(format!("z_{t:e}"), |b| b.iter(|| evaluator.z(black_box(t), 128)));
    }
    group.finish();
}

criterion_group!(benches, bench_z);
criterion_main!(benches);
