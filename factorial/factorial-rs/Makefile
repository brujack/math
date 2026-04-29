.PHONY: factorial lint test clean

factorial:
	cargo build --release
	cp target/release/factorial ~/Downloads/factorial

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

clean:
	cargo clean
	rm -f ~/Downloads/factorial
