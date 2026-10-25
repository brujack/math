#!/usr/bin/env bats

# `make <crate>` only builds; `make install` copies the release binary to
# ${XDG_BIN_HOME:-$HOME/.local/bin}, the same on Linux and macOS. Seven crates
# used to copy into ~/Downloads as part of the build (a leftover from a
# macOS-only workflow), which failed the build on any machine without that
# directory. Each test runs the crate's real Makefile in a temp dir against a
# fake cargo, with HOME pointed at a fixture, so neither the repo nor the real
# home is touched.

load '../helpers/common'

CRATES=(amicable collatz e factorial fib goldbach perfect-numbers pi prime sq twin-primes)

setup() {
    export HOME="${BATS_TEST_TMPDIR}/home"
    unset XDG_BIN_HOME
    mkdir -p "${HOME}" "${BATS_TEST_TMPDIR}/bin"
    cat > "${BATS_TEST_TMPDIR}/bin/cargo" <<'FAKE'
#!/usr/bin/env bash
# Fake cargo: `cargo build --release` creates target/release/<crate dir name>;
# `cargo clean` removes target/.
[[ "${FAKE_CARGO_FAIL:-0}" == "1" ]] && exit 101
crate=$(basename "$(pwd)")
case "$1" in
    build) mkdir -p target/release && printf 'bin\n' > "target/release/${crate}" ;;
    clean) rm -rf target ;;
esac
FAKE
    chmod +x "${BATS_TEST_TMPDIR}/bin/cargo"
    export PATH="${BATS_TEST_TMPDIR}/bin:${PATH}"
}

_make() {
    local crate="$1" dir="${BATS_TEST_TMPDIR}/work/${1}"
    shift
    mkdir -p "${dir}"
    cp "${REPO_ROOT}/${crate}/${crate}-rs/Makefile" "${dir}/Makefile"
    run make -C "${dir}" -s "$@"
}

@test "make <crate> builds and writes nothing outside the crate" {
    for crate in "${CRATES[@]}"; do
        _make "${crate}" "${crate}"
        [ "${status}" -eq 0 ] || { echo "${crate}: ${output}"; return 1; }
        [ -f "${BATS_TEST_TMPDIR}/work/${crate}/target/release/${crate}" ]
    done
    [ -z "$(ls -A "${HOME}")" ] || { ls -AR "${HOME}"; return 1; }
}

@test "make install creates ~/.local/bin and installs the binary" {
    for crate in "${CRATES[@]}"; do
        _make "${crate}" install
        [ "${status}" -eq 0 ] || { echo "${crate}: ${output}"; return 1; }
        [ -f "${HOME}/.local/bin/${crate}" ] || { echo "${crate} not installed"; return 1; }
        [[ "${output}" == *"${HOME}/.local/bin/${crate}"* ]]
    done
}

@test "make install honours XDG_BIN_HOME" {
    export XDG_BIN_HOME="${BATS_TEST_TMPDIR}/xdg-bin"
    for crate in "${CRATES[@]}"; do
        _make "${crate}" install
        [ "${status}" -eq 0 ] || { echo "${crate}: ${output}"; return 1; }
        [ -f "${XDG_BIN_HOME}/${crate}" ] || { echo "${crate} not in XDG_BIN_HOME"; return 1; }
    done
    [ ! -e "${HOME}/.local" ]
}

@test "a failing cargo build fails both make <crate> and make install" {
    export FAKE_CARGO_FAIL=1
    for crate in "${CRATES[@]}"; do
        _make "${crate}" "${crate}"
        [ "${status}" -ne 0 ] || { echo "${crate} build passed a failed cargo"; return 1; }
        _make "${crate}" install
        [ "${status}" -ne 0 ] || { echo "${crate} install passed a failed cargo"; return 1; }
    done
    [ ! -e "${HOME}/.local" ]
}

@test "make clean leaves the home directory alone" {
    mkdir -p "${HOME}/Downloads" "${HOME}/.local/bin"
    for crate in "${CRATES[@]}"; do
        printf 'keep\n' > "${HOME}/Downloads/${crate}"
        printf 'keep\n' > "${HOME}/.local/bin/${crate}"
        _make "${crate}" clean
        [ "${status}" -eq 0 ] || { echo "${crate}: ${output}"; return 1; }
        [ -f "${HOME}/Downloads/${crate}" ] && [ -f "${HOME}/.local/bin/${crate}" ] \
            || { echo "${crate}: clean removed a file in HOME"; return 1; }
    done
}

@test "every crate Makefile declares install .PHONY" {
    for crate in "${CRATES[@]}"; do
        grep -qE '^\.PHONY:.*\binstall\b' "${REPO_ROOT}/${crate}/${crate}-rs/Makefile" \
            || { echo "${crate}: install not .PHONY"; return 1; }
    done
}
