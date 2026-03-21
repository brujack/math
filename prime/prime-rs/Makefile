.PHONY: prime test clean

prime:
	cargo build --release
	cp target/release/prime ~/Downloads/prime

test:
	cargo test

clean:
	cargo clean
	rm -f ~/Downloads/prime
