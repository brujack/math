#!/usr/bin/env bats
# shellcheck disable=SC1090  # each test sources a rendered copy of the template

# Behaviour of scripts/crate_templates/python/install_deps.sh, which renders every
# Python sub-project's <project>/install_deps.sh. A rendered copy is sourced (it
# has a sourcing guard); every external command is a PATH mock that logs its
# arguments, so no real sudo, package manager or pip is ever reached.

load '../helpers/common'

PINNED='mpmath==1.4.1 gmpy2==2.3.2 coverage==7.16.2 cosmic-ray==8.7.0 hypothesis==6.168.5 pytest==9.1.1 pytest-cov==7.1.0 ruff==0.16.4 pyright==1.1.411 pip-audit==2.10.1'

setup() {
    BIN="${BATS_TEST_TMPDIR}/bin"
    LOG="${BATS_TEST_TMPDIR}/calls"
    mkdir -p "${BIN}"
    : > "${LOG}"
    export LOG
    export HOME="${BATS_TEST_TMPDIR}/home"
    mkdir -p "${HOME}"
    export MATH_DEBIAN_VERSION_FILE="${BATS_TEST_TMPDIR}/no-debian"
    export MATH_RHEL_RELEASE_FILE="${BATS_TEST_TMPDIR}/no-rhel"

    for tool in brew apt-get dnf yum pip pip3; do
        _mock "${tool}"
    done
    # sudo only logs: the real package manager is never reached through it.
    printf '#!/usr/bin/env bash\nprintf "sudo %%s\\n" "$*" >> "${LOG}"\n"$@"\n' > "${BIN}/sudo"
    printf '#!/usr/bin/env bash\nprintf "%%s\\n" "${FAKE_UNAME:-Linux}"\n' > "${BIN}/uname"
    # python3: `-m pip ...` logs (and fails when FAKE_PIP_FAIL is set); anything
    # else is the heredoc import check, which reads stdin and succeeds.
    cat > "${BIN}/python3" <<'FAKE'
#!/usr/bin/env bash
if [[ "$1" == "-m" && "$2" == "pip" ]]; then
    printf 'pip %s\n' "${*:3}" >> "${LOG}"
    [[ -n "${FAKE_PIP_FAIL:-}" ]] && exit 1
    exit 0
fi
printf 'python3-check\n' >> "${LOG}"
cat > /dev/null
FAKE
    chmod +x "${BIN}"/*

    SCRIPT="${BATS_TEST_TMPDIR}/install_deps.sh"
    sed 's/@MODULE@/fib/g; s/@CRATE@/fib/g' "${REPO_ROOT}/scripts/crate_templates/python/install_deps.sh" > "${SCRIPT}"
    # Mocks first, then the system dirs the script itself needs (printf is builtin).
    export PATH="${BIN}:/usr/bin:/bin"
}

_mock() {
    printf '#!/usr/bin/env bash\nprintf "%s %%s\\n" "$*" >> "${LOG}"\n' "$1" > "${BIN}/$1"
}

@test "sourcing the file runs nothing" {
    source "${SCRIPT}"
    [ ! -s "${LOG}" ]
    declare -F main > /dev/null
}

@test "inert: the mocked sudo, brew, apt-get, dnf, yum, pip shadow the real ones" {
    for tool in sudo brew apt-get dnf yum pip pip3 python3 uname; do
        [ "$(command -v "${tool}")" = "${BIN}/${tool}" ]
    done
}

@test "happy path on Debian exits 0 and pip receives exactly the pinned packages" {
    : > "${MATH_DEBIAN_VERSION_FILE}"
    run bash "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"All dependencies installed successfully"* ]]
    grep -qx 'apt-get update -qq' "${LOG}"
    [ "$(grep -c '^pip ' "${LOG}")" -eq 1 ]
    grep -qxF "pip install ${PINNED}" "${LOG}"
    grep -qx 'python3-check' "${LOG}"
}

@test "pip failure exits nonzero and never prints the success line" {
    : > "${MATH_DEBIAN_VERSION_FILE}"
    export FAKE_PIP_FAIL=1
    run bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${output}" != *"All dependencies installed successfully"* ]]
    ! grep -qx 'python3-check' "${LOG}"
}

@test "main stops at a pip failure before verifying" {
    : > "${MATH_DEBIAN_VERSION_FILE}"
    export FAKE_PIP_FAIL=1
    source "${SCRIPT}"
    run main
    [ "${status}" -eq 1 ]
    [[ "${output}" != *"All dependencies installed successfully"* ]]
    ! grep -qx 'python3-check' "${LOG}"
}

@test "macOS without Homebrew fails with the Homebrew error" {
    rm -f "${BIN}/brew"
    export FAKE_UNAME=Darwin
    run bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"Homebrew is required on macOS"* ]]
    ! grep -q '^pip ' "${LOG}"
}

@test "macOS installs GMP and MPFR with Homebrew" {
    export FAKE_UNAME=Darwin
    run bash "${SCRIPT}"
    [ "${status}" -eq 0 ]
    grep -qx 'brew install gmp mpfr' "${LOG}"
}

@test "a non-Debian Linux with dnf installs with dnf" {
    : > "${MATH_RHEL_RELEASE_FILE}"
    run bash "${SCRIPT}"
    [ "${status}" -eq 0 ]
    grep -qx 'dnf install -y gmp-devel mpfr-devel libmpc-devel python3-devel' "${LOG}"
}

@test "RHEL family with neither dnf nor yum fails" {
    : > "${MATH_RHEL_RELEASE_FILE}"
    rm -f "${BIN}/dnf" "${BIN}/yum"
    run bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"neither dnf nor yum found"* ]]
    ! grep -q '^pip ' "${LOG}"
}

@test "an unrecognised Linux distribution fails" {
    run bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"unrecognised Linux distribution"* ]]
    ! grep -q '^pip ' "${LOG}"
}

@test "an unsupported OS fails and names it" {
    export FAKE_UNAME=Plan9
    run bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"unsupported OS 'Plan9'"* ]]
    ! grep -q '^pip ' "${LOG}"
}

@test "a failing apt install stops before pip" {
    : > "${MATH_DEBIAN_VERSION_FILE}"
    printf '#!/usr/bin/env bash\n[[ "$1" == install ]] && exit 100\nexit 0\n' > "${BIN}/apt-get"
    chmod +x "${BIN}/apt-get"
    run bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    ! grep -q '^pip ' "${LOG}"
}
