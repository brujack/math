.PHONY: goldbach lint test bench clean mutants

goldbach:
	cargo build --release

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

bench:
	cargo bench

mutants:
	cargo mutants --timeout 120 --no-shuffle

clean:
	cargo clean
