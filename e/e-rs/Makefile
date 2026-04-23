.PHONY: e lint test clean

e:
	cargo build --release
	cp target/release/e ~/Downloads/e

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/e
