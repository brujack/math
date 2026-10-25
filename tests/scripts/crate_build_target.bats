#!/usr/bin/env bats

# `make <crate>` builds the release binary. Seven crates also copy it to
# ~/Downloads as a convenience; that copy used to fail the whole build on any
# machine without a Downloads directory (a fresh box, a server, a CI image).
# Each test runs the crate's real Makefile in a temp dir against a fake cargo,
# with HOME pointed at a fixture, so neither the repo nor the real home is touched.

load '../helpers/common'

CRATES=(amicable collatz e factorial fib goldbach perfect-numbers pi prime sq twin-primes)
COPYING=(e factorial fib pi prime sq twin-primes)

setup() {
    export HOME="${BATS_TEST_TMPDIR}/home"
    mkdir -p "${HOME}" "${BATS_TEST_TMPDIR}/bin"
    cat > "${BATS_TEST_TMPDIR}/bin/cargo" <<'FAKE'
#!/usr/bin/env bash
# Fake cargo: `cargo build --release` creates target/release/<crate dir name>.
[[ "${FAKE_CARGO_FAIL:-0}" == "1" ]] && exit 101
crate=$(basename "$(pwd)")
mkdir -p target/release && printf 'bin\n' > "target/release/${crate}"
FAKE
    chmod +x "${BATS_TEST_TMPDIR}/bin/cargo"
    export PATH="${BATS_TEST_TMPDIR}/bin:${PATH}"
}

_build() {
    local crate="$1" dir="${BATS_TEST_TMPDIR}/work/${1}"
    mkdir -p "${dir}"
    cp "${REPO_ROOT}/${crate}/${crate}-rs/Makefile" "${dir}/Makefile"
    run make -C "${dir}" -s "${crate}"
}

@test "every crate builds when ~/Downloads does not exist" {
    for crate in "${CRATES[@]}"; do
        _build "${crate}"
        [ "${status}" -eq 0 ] || { echo "${crate}: ${output}"; return 1; }
        [ -f "${BATS_TEST_TMPDIR}/work/${crate}/target/release/${crate}" ]
    done
    [ ! -e "${HOME}/Downloads" ]
}

@test "crates that copy to ~/Downloads still do when it exists" {
    mkdir -p "${HOME}/Downloads"
    for crate in "${COPYING[@]}"; do
        _build "${crate}"
        [ "${status}" -eq 0 ] || { echo "${crate}: ${output}"; return 1; }
        [ -f "${HOME}/Downloads/${crate}" ] || { echo "${crate} not copied"; return 1; }
    done
}

@test "a failing cargo build still fails make" {
    export FAKE_CARGO_FAIL=1
    for crate in "${CRATES[@]}"; do
        _build "${crate}"
        [ "${status}" -ne 0 ] || { echo "${crate} passed a failed build"; return 1; }
    done
}
