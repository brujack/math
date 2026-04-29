.PHONY: twin-primes lint test clean

twin-primes:
	cargo build --release
	cp target/release/twin-primes ~/Downloads/twin-primes

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

clean:
	cargo clean
	rm -f ~/Downloads/twin-primes
