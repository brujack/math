#!/usr/bin/env bats

# Behaviour of scripts/crate_templates/install_deps.sh, which renders every
# crate's <crate>/<crate>-rs/install_deps.sh. The template is rendered for one
# crate into a temp dir and sourced (it has a sourcing guard); every external
# command is a PATH mock that logs its arguments, so nothing is installed.

load '../helpers/common'

setup() {
    BIN="${BATS_TEST_TMPDIR}/bin"
    LOG="${BATS_TEST_TMPDIR}/calls"
    mkdir -p "${BIN}"
    : > "${LOG}"
    export LOG
    export HOME="${BATS_TEST_TMPDIR}/home"
    mkdir -p "${HOME}/.cargo"
    : > "${HOME}/.cargo/env"
    export MATH_DEBIAN_VERSION_FILE="${BATS_TEST_TMPDIR}/no-debian"

    for tool in brew sudo apt-get dnf yum rustup curl sh; do
        _mock "${tool}"
    done
    # sudo runs its command so the apt/dnf mock is the one that logs.
    printf '#!/usr/bin/env bash\nprintf "sudo %%s\\n" "$*" >> "${LOG}"\n"$@"\n' > "${BIN}/sudo"
    printf '#!/usr/bin/env bash\nprintf "%%s\\n" "${FAKE_UNAME:-Linux}"\n' > "${BIN}/uname"
    # cargo: `cargo <tool> --version` succeeds only for tools in FAKE_HAVE;
    # `cargo install` fails when FAKE_INSTALL_FAIL is set.
    cat > "${BIN}/cargo" <<'FAKE'
#!/usr/bin/env bash
printf 'cargo %s\n' "$*" >> "${LOG}"
if [[ "$1" == "install" ]]; then
    [[ -n "${FAKE_INSTALL_FAIL:-}" ]] && exit 101
    exit 0
fi
[[ " ${FAKE_HAVE:-} " == *" $1 "* ]]
FAKE
    chmod +x "${BIN}"/*

    TEMPLATE="${REPO_ROOT}/scripts/crate_templates/install_deps.sh"
    SCRIPT="${BATS_TEST_TMPDIR}/install_deps.sh"
    sed 's/@CRATE@/pi/g' "${TEMPLATE}" > "${SCRIPT}"
    export PATH="${BIN}:/usr/bin:/bin"
}

_mock() {
    printf '#!/usr/bin/env bash\nprintf "%s %%s\\n" "$*" >> "${LOG}"\n' "$1" > "${BIN}/$1"
}

_unmock() {
    rm -f "${BIN}/$1"
}

@test "macOS without Homebrew fails and names the remedy" {
    _unmock brew
    export FAKE_UNAME=Darwin
    source "${SCRIPT}"
    run install_system_libs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"https://brew.sh"* ]]
}

@test "macOS installs GMP and MPFR with Homebrew" {
    export FAKE_UNAME=Darwin
    source "${SCRIPT}"
    run install_system_libs
    [ "${status}" -eq 0 ]
    grep -qx 'brew install gmp mpfr' "${LOG}"
}

@test "Debian installs GMP and MPFR with apt" {
    : > "${MATH_DEBIAN_VERSION_FILE}"
    source "${SCRIPT}"
    run install_system_libs
    [ "${status}" -eq 0 ]
    grep -qx 'apt-get update -qq' "${LOG}"
    grep -qx 'apt-get install -y libgmp-dev libmpfr-dev' "${LOG}"
}

@test "a non-Debian Linux with dnf installs with dnf" {
    source "${SCRIPT}"
    run install_system_libs
    [ "${status}" -eq 0 ]
    grep -qx 'dnf install -y gmp-devel mpfr-devel' "${LOG}"
}

@test "a Linux with neither apt, dnf nor yum fails" {
    _unmock dnf
    _unmock yum
    source "${SCRIPT}"
    run install_system_libs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"unrecognised Linux distribution"* ]]
}

@test "an unsupported OS fails and names it" {
    export FAKE_UNAME=Plan9
    source "${SCRIPT}"
    run install_system_libs
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"unsupported OS 'Plan9'"* ]]
}

@test "a failing package install fails install_system_libs" {
    : > "${MATH_DEBIAN_VERSION_FILE}"
    # update succeeds, install fails: the install's own status must propagate.
    printf '#!/usr/bin/env bash\n[[ "$1" == install ]] && exit 100\nexit 0\n' > "${BIN}/apt-get"
    chmod +x "${BIN}/apt-get"
    source "${SCRIPT}"
    run install_system_libs
    [ "${status}" -eq 1 ]
}

@test "missing cargo tools are installed at the pinned versions" {
    source "${SCRIPT}"
    run install_cargo_tools
    [ "${status}" -eq 0 ]
    grep -qx 'cargo install cargo-nextest --locked --version 0.9.148' "${LOG}"
    grep -qx 'cargo install cargo-machete --locked --version 0.9.2' "${LOG}"
    grep -qx 'cargo install cargo-tarpaulin --locked --version 0.37.5' "${LOG}"
}

@test "installed cargo tools are left alone (idempotent re-run)" {
    export FAKE_HAVE="nextest machete tarpaulin"
    source "${SCRIPT}"
    run install_cargo_tools
    [ "${status}" -eq 0 ]
    ! grep -q '^cargo install' "${LOG}"
}

@test "a failed cargo install stops install_cargo_tools" {
    export FAKE_INSTALL_FAIL=1
    source "${SCRIPT}"
    run install_cargo_tools
    [ "${status}" -eq 1 ]
    [ "$(grep -c '^cargo install' "${LOG}")" -eq 1 ]
}

@test "an existing Rust toolchain is updated, not reinstalled" {
    source "${SCRIPT}"
    run install_rust
    [ "${status}" -eq 0 ]
    grep -qx 'rustup update stable' "${LOG}"
    ! grep -q '^curl' "${LOG}"
}

@test "main stops at the first failing stage" {
    export FAKE_UNAME=Plan9
    source "${SCRIPT}"
    run main
    [ "${status}" -eq 1 ]
    ! grep -q '^rustup\|^cargo' "${LOG}"
}

@test "running the script exits 1 when a stage fails" {
    export FAKE_UNAME=Plan9
    run bash "${SCRIPT}"
    [ "${status}" -eq 1 ]
}
