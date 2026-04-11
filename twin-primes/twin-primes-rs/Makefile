.PHONY: twin-primes lint test clean

twin-primes:
	cargo build --release
	cp target/release/twin-primes ~/Downloads/twin-primes

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/twin-primes
