.PHONY: factorial lint test clean

factorial:
	cargo build --release
	cp target/release/factorial ~/Downloads/factorial

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/factorial
