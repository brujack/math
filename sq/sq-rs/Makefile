.PHONY: sq lint test clean mutants

sq:
	cargo build --release
	cp target/release/sq ~/Downloads/sq

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

mutants:
	cargo mutants --timeout 120 --no-shuffle

clean:
	cargo clean
	rm -f ~/Downloads/sq
