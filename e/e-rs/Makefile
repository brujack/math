.PHONY: e lint test clean

e:
	cargo build --release
	cp target/release/e ~/Downloads/e

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

clean:
	cargo clean
	rm -f ~/Downloads/e
