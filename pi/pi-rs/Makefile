.PHONY: pi lint test clean

pi:
	cargo build --release
	cp target/release/pi ~/Downloads/pi

lint:
	cargo clippy -- -D warnings

test: lint
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/pi
