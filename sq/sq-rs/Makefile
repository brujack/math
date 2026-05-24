.PHONY: sq lint test bench clean mutants

sq:
	cargo build --release
	cp target/release/sq ~/Downloads/sq

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

bench:
	cargo bench

mutants:
	cargo mutants --timeout 120 --no-shuffle

clean:
	cargo clean
	rm -f ~/Downloads/sq
