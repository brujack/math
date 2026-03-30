.PHONY: fib lint test clean

fib:
	cargo build --release
	cp target/release/fib ~/Downloads/fib

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/fib
