.PHONY: prime lint test clean

prime:
	cargo build --release
	cp target/release/prime ~/Downloads/prime

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

clean:
	cargo clean
	rm -f ~/Downloads/prime
