.PHONY: amicable lint test clean

amicable:
	cargo build --release

lint:
	../../scripts/rust-check.sh lint

test:
	../../scripts/rust-check.sh test

clean:
	cargo clean
	rm -f amicable_1e*.txt
