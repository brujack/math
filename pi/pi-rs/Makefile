.PHONY: pi lint test clean

pi:
	cargo build --release
	cp target/release/pi ~/Downloads/pi

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

clean:
	cargo clean
	rm -f ~/Downloads/pi
