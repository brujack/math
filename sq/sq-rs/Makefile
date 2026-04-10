.PHONY: sq lint test clean

sq:
	cargo build --release
	cp target/release/sq ~/Downloads/sq

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/sq
