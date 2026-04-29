.PHONY: sq lint test clean

sq:
	cargo build --release
	cp target/release/sq ~/Downloads/sq

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

clean:
	cargo clean
	rm -f ~/Downloads/sq
