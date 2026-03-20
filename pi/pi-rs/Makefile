.PHONY: pi clean

pi:
	cargo build --release
	cp target/release/pi ~/Downloads/pi

clean:
	cargo clean
	rm -f ~/Downloads/pi
