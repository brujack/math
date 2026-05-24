.PHONY: fib lint test bench clean mutants

fib:
	cargo build --release
	cp target/release/fib ~/Downloads/fib

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
	rm -f ~/Downloads/fib
