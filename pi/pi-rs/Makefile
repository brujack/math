.PHONY: pi test clean

pi:
	cargo build --release
	cp target/release/pi ~/Downloads/pi

test:
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/pi
