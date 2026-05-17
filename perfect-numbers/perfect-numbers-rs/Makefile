.PHONY: perfect-numbers lint test clean mutants

perfect-numbers:
	cargo build --release

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

mutants:
	cargo mutants --timeout 120 --no-shuffle

clean:
	cargo clean
