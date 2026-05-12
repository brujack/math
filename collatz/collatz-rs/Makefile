.PHONY: collatz lint test clean

collatz:
	cargo build --release

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

clean:
	cargo clean
