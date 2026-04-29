.PHONY: fib lint test clean

fib:
	cargo build --release
	cp target/release/fib ~/Downloads/fib

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

clean:
	cargo clean
	rm -f ~/Downloads/fib
