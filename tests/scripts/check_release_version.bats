#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    SCRIPT="${REPO_ROOT}/scripts/check-release-version.sh"
    CRATE="${BATS_TEST_TMPDIR}/sq/sq-rs"
    mkdir -p "${CRATE}"
    _write_manifest '[package]
name = "sq"
version = "0.2.0"
edition = "2021"

[dependencies]
rug = { version = "1.24.0" }'
}

_write_manifest() {
    printf '%s\n' "$1" >"${CRATE}/Cargo.toml"
}

@test "version equal to Cargo.toml -> exit 0, prints the version" {
    run "${SCRIPT}" "${CRATE}" "0.2.0"
    [ "${status}" -eq 0 ]
    [ "${output}" = "0.2.0" ]
}

@test "dependency version lines are not read as the package version" {
    run "${SCRIPT}" "${CRATE}" "1.24.0"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"0.2.0"* ]]
}

@test "version differing from Cargo.toml -> exit 1 naming both" {
    run "${SCRIPT}" "${CRATE}" "0.3.0"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"0.3.0"* ]]
    [[ "${output}" == *"0.2.0"* ]]
}

@test "v-prefixed version -> exit 1" {
    run "${SCRIPT}" "${CRATE}" "v0.2.0"
    [ "${status}" -eq 1 ]
}

@test "two-part version -> exit 1" {
    run "${SCRIPT}" "${CRATE}" "0.2"
    [ "${status}" -eq 1 ]
}

@test "leading-zero component -> exit 1" {
    run "${SCRIPT}" "${CRATE}" "0.02.0"
    [ "${status}" -eq 1 ]
}

@test "trailing newline smuggled into the version -> exit 1" {
    run "${SCRIPT}" "${CRATE}" $'0.2.0\n'
    [ "${status}" -eq 1 ]
}

@test "shell metacharacters -> exit 1 and nothing executes" {
    local marker="${BATS_TEST_TMPDIR}/pwned"
    run "${SCRIPT}" "${CRATE}" "0.2.0\" --output ${marker} \"\$(touch ${marker})"
    [ "${status}" -eq 1 ]
    [ ! -e "${marker}" ]
}

@test "empty version -> exit 2 with usage" {
    run "${SCRIPT}" "${CRATE}" ""
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"usage"* ]]
}

@test "missing crate dir argument -> exit 2 with usage" {
    run "${SCRIPT}"
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"usage"* ]]
}

@test "missing Cargo.toml -> exit 1 naming the manifest" {
    run "${SCRIPT}" "${BATS_TEST_TMPDIR}/nowhere" "0.2.0"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"nowhere/Cargo.toml"* ]]
}

@test "Cargo.toml without [package] version -> exit 1" {
    _write_manifest '[workspace]
members = ["a"]'
    run "${SCRIPT}" "${CRATE}" "0.2.0"
    [ "${status}" -eq 1 ]
}

@test "malformed Cargo.toml -> exit 1" {
    _write_manifest '[package'
    run "${SCRIPT}" "${CRATE}" "0.2.0"
    [ "${status}" -eq 1 ]
}

@test "every real crate manifest is readable by the check" {
    local manifest crate_dir version
    for manifest in "${REPO_ROOT}"/*/*-rs/Cargo.toml; do
        crate_dir="$(dirname "${manifest}")"
        version="$(sed -n 's/^version = "\(.*\)"$/\1/p' "${manifest}" | head -1)"
        run "${SCRIPT}" "${crate_dir}" "${version}"
        [ "${status}" -eq 0 ] || { echo "${manifest}: ${output}"; return 1; }
    done
}

@test "pre-release Cargo.toml version matching the input -> exit 1 (plain releases only)" {
    _write_manifest '[package]
name = "sq"
version = "0.2.0-rc.1"'
    run "${SCRIPT}" "${CRATE}" "0.2.0-rc.1"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"MAJOR.MINOR.PATCH"* ]]
}
