.PHONY: perfect-numbers lint test clean

perfect-numbers:
	cargo build --release

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

clean:
	cargo clean
