#!/usr/bin/env bats

# scripts/install-actionlint.sh downloads a binary, so every failure branch must
# leave the target directory untouched. HOME and XDG_BIN_HOME point into
# BATS_TEST_TMPDIR (core.md tdd-007/009) and curl/uname are PATH mocks: no test
# reaches the network or the real ~/.local/bin.

load '../helpers/common'

SCRIPT="${REPO_ROOT}/scripts/install-actionlint.sh"

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    export HOME="${BATS_TEST_TMPDIR}/home"
    export XDG_BIN_HOME="${HOME}/bin"
    mkdir -p "${HOME}"
    MOCKS="${BATS_TEST_TMPDIR}/mocks"
    mkdir -p "${MOCKS}"
    export CURL_LOG="${BATS_TEST_TMPDIR}/curl.log"
    export MOCK_UNAME_S="Linux"
    export MOCK_UNAME_M="x86_64"

    # Fixture release tarball holding a fake `actionlint` that reports 1.7.12.
    local src="${BATS_TEST_TMPDIR}/src"
    mkdir -p "${src}"
    printf '#!/bin/sh\nprintf "1.7.12\\n"\n' > "${src}/actionlint"
    chmod 755 "${src}/actionlint"
    export FIXTURE_TGZ="${BATS_TEST_TMPDIR}/fixture.tar.gz"
    tar -czf "${FIXTURE_TGZ}" -C "${src}" actionlint
    FIXTURE_SHA="$(sha256sum "${FIXTURE_TGZ}" | cut -d' ' -f1)"

    cat > "${MOCKS}/curl" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${CURL_LOG}"
[[ -n "${MOCK_CURL_FAIL:-}" ]] && exit 22
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-o" ]]; then cp "${FIXTURE_TGZ}" "$2"; exit 0; fi
    shift
done
exit 2
MOCK
    cat > "${MOCKS}/uname" <<'MOCK'
#!/usr/bin/env bash
case "$1" in
    -s) printf '%s\n' "${MOCK_UNAME_S}" ;;
    -m) printf '%s\n' "${MOCK_UNAME_M}" ;;
esac
MOCK
    chmod 755 "${MOCKS}/curl" "${MOCKS}/uname"
    export PATH="${MOCKS}:${PATH}"
}

# Run the installer with the checksum table replaced by the fixture's hash.
run_with_fixture_sha() {
    run bash -c '
        source "$1"
        FIXTURE="$2"
        al_expected_sha256() { printf "%s\n" "${FIXTURE}"; }
        install_actionlint
    ' _ "${SCRIPT}" "${FIXTURE_SHA}"
}

@test "correct checksum installs an executable actionlint into XDG_BIN_HOME" {
    run_with_fixture_sha
    [ "${status}" -eq 0 ]
    [ -x "${XDG_BIN_HOME}/actionlint" ]
    [ "$("${XDG_BIN_HOME}/actionlint" -version | head -1)" = "1.7.12" ]
}

@test "defaults to HOME/.local/bin when XDG_BIN_HOME is unset" {
    unset XDG_BIN_HOME
    run_with_fixture_sha
    [ "${status}" -eq 0 ]
    [ -x "${HOME}/.local/bin/actionlint" ]
}

@test "downloads the pinned version URL for the detected platform" {
    MOCK_UNAME_S=Darwin MOCK_UNAME_M=arm64 run bash -c '
        source "$1"
        FIXTURE="$2"
        al_expected_sha256() { printf "%s\n" "${FIXTURE}"; }
        install_actionlint
    ' _ "${SCRIPT}" "${FIXTURE_SHA}"
    [ "${status}" -eq 0 ]
    grep -q 'releases/download/v1.7.12/actionlint_1.7.12_darwin_arm64.tar.gz' "${CURL_LOG}"
}

@test "wrong checksum fails nonzero and installs nothing" {
    run bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"checksum"* ]]
    [ ! -e "${XDG_BIN_HOME}/actionlint" ]
}

@test "unknown platform fails nonzero before any download" {
    MOCK_UNAME_S=FreeBSD run bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"unsupported platform"* ]]
    [ ! -e "${CURL_LOG}" ]
    [ ! -e "${XDG_BIN_HOME}/actionlint" ]
}

@test "unknown architecture fails nonzero before any download" {
    MOCK_UNAME_M=riscv64 run bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [ ! -e "${CURL_LOG}" ]
}

@test "already-installed 1.7.12 is a no-op: curl is never called" {
    mkdir -p "${XDG_BIN_HOME}"
    printf '#!/bin/sh\nprintf "1.7.12\\n"\n' > "${XDG_BIN_HOME}/actionlint"
    chmod 755 "${XDG_BIN_HOME}/actionlint"
    run bash "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [ ! -e "${CURL_LOG}" ]
}

@test "a different installed version is replaced" {
    mkdir -p "${XDG_BIN_HOME}"
    printf '#!/bin/sh\nprintf "1.6.0\\n"\n' > "${XDG_BIN_HOME}/actionlint"
    chmod 755 "${XDG_BIN_HOME}/actionlint"
    run_with_fixture_sha
    [ "${status}" -eq 0 ]
    [ "$("${XDG_BIN_HOME}/actionlint" -version | head -1)" = "1.7.12" ]
    [ -e "${CURL_LOG}" ]
}

@test "curl failure fails nonzero and installs nothing" {
    MOCK_CURL_FAIL=1 run_with_fixture_sha
    [ "${status}" -ne 0 ]
    [ ! -e "${XDG_BIN_HOME}/actionlint" ]
}

@test "refuses when neither XDG_BIN_HOME nor HOME is set" {
    run env -u XDG_BIN_HOME -u HOME PATH="${PATH}" bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [ ! -e "${CURL_LOG}" ]
}

@test "checksum table holds the four official 1.7.12 values" {
    run bash -c '
        source "$1"
        for p in linux_amd64 linux_arm64 darwin_amd64 darwin_arm64; do
            printf "%s %s\n" "${p}" "$(al_expected_sha256 "${p}")"
        done
    ' _ "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"linux_amd64 8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"* ]]
    [[ "${output}" == *"linux_arm64 325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6"* ]]
    [[ "${output}" == *"darwin_amd64 5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644"* ]]
    [[ "${output}" == *"darwin_arm64 aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f"* ]]
}
