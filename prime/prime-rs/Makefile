.PHONY: prime lint test clean

prime:
	cargo build --release
	cp target/release/prime ~/Downloads/prime

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/prime
