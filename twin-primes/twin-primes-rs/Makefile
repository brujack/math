.PHONY: twin-primes lint test bench clean mutants

twin-primes:
	cargo build --release
	cp target/release/twin-primes ~/Downloads/twin-primes

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
	rm -f ~/Downloads/twin-primes
