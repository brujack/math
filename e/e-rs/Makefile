.PHONY: e lint test clean mutants

e:
	cargo build --release
	cp target/release/e ~/Downloads/e

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

mutants:
	cargo mutants --timeout 120 --no-shuffle

clean:
	cargo clean
	rm -f ~/Downloads/e
