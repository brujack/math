#!/usr/bin/env bats

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    SCRIPT="${REPO_ROOT}/scripts/third-party-notices.sh"
    CRATE="${BATS_TEST_TMPDIR}/crate"
    OUT="${BATS_TEST_TMPDIR}/out"
    LIC="${BATS_TEST_TMPDIR}/lic"
    mkdir -p "${CRATE}" "${OUT}" "${LIC}"
    printf 'GNU LESSER GENERAL PUBLIC LICENSE\nfixture lgpl body\n' >"${LIC}/LGPL-3.0.txt"
    printf 'GNU GENERAL PUBLIC LICENSE\nfixture gpl body\n' >"${LIC}/GPL-3.0.txt"
    export LICENSES_DIR="${LIC}"
}

teardown() {
    chmod -R u+rwx "${BATS_TEST_TMPDIR}" 2>/dev/null
    return 0
}

write_gmp_lock() {
    cat >"${CRATE}/Cargo.lock" <<'LOCK'
version = 4

[[package]]
name = "other"
version = "0.3.1"

[[package]]
name = "gmp-mpfr-sys"
version = "1.7.0"

[[package]]
name = "rug"
version = "1.30.0"
LOCK
}

assert_out_empty() {
    [ "$(find "${OUT}" -mindepth 1 | wc -l)" -eq 0 ]
}

assert_gmp_notice() {
    f="${OUT}/THIRD-PARTY-NOTICES.txt"
    [ -f "$f" ]
    command grep -qF "gmp-mpfr-sys 1.7.0" "$f"
    command grep -qF "fixture lgpl body" "$f"
}

@test "GMP lockfile writes one notices file with components and both embedded texts" {
    write_gmp_lock
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -eq 0 ]
    [ "$(find "${OUT}" -mindepth 1 | wc -l)" -eq 1 ]
    f="${OUT}/THIRD-PARTY-NOTICES.txt"
    [ -f "$f" ]
    for s in "gmp-mpfr-sys 1.7.0" "rug 1.30.0" "GMP" "MPFR" "MPC" "LGPL-3.0-or-later" \
        "statically linked" "GNU LESSER GENERAL PUBLIC LICENSE" "GNU GENERAL PUBLIC LICENSE" \
        "fixture lgpl body" "fixture gpl body"; do
        command grep -qF -- "$s" "$f"
    done
    [ "$(stat -c %a "$f")" = "644" ]
}

@test "CRLF GMP lockfile still produces the GMP notice" {
    write_gmp_lock
    sed -i 's/$/\r/' "${CRATE}/Cargo.lock"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -eq 0 ]
    assert_gmp_notice
    command grep -qF "rug 1.30.0" "${OUT}/THIRD-PARTY-NOTICES.txt"
}

@test "version-before-name GMP lockfile still produces the GMP notice" {
    cat >"${CRATE}/Cargo.lock" <<'LOCK'
[[package]]
version = "1.7.0"
name = "gmp-mpfr-sys"

[[package]]
version = "1.30.0"
name = "rug"
LOCK
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -eq 0 ]
    assert_gmp_notice
    command grep -qF "rug 1.30.0" "${OUT}/THIRD-PARTY-NOTICES.txt"
}

@test "non-GMP lockfile states no LGPL components and omits GPL text" {
    printf '[[package]]\nname = "other"\nversion = "0.3.1"\n' >"${CRATE}/Cargo.lock"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -eq 0 ]
    [ "$(find "${OUT}" -mindepth 1 | wc -l)" -eq 1 ]
    command grep -qF "links no LGPL components" "${OUT}/THIRD-PARTY-NOTICES.txt"
    ! command grep -qF "GNU GENERAL PUBLIC LICENSE" "${OUT}/THIRD-PARTY-NOTICES.txt"
}

@test "multiple locked versions of one component are all listed, sorted" {
    write_gmp_lock
    printf '\n[[package]]\nname = "rug"\nversion = "1.29.0"\n' >>"${CRATE}/Cargo.lock"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -eq 0 ]
    command grep -qF "rug 1.29.0, 1.30.0" "${OUT}/THIRD-PARTY-NOTICES.txt"
}

@test "missing Cargo.lock fails naming the lockfile" {
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"missing Cargo.lock"* ]]
    assert_out_empty
}

@test "no arguments fails with usage" {
    run "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"usage:"* ]]
}

@test "gmp-mpfr-sys without rug fails with its own wording" {
    printf '[[package]]\nname = "gmp-mpfr-sys"\nversion = "1.7.0"\n' >"${CRATE}/Cargo.lock"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"rug is not locked"* ]]
    [[ "$output" != *"missing Cargo.lock"* ]]
    assert_out_empty
}

@test "Cargo.toml declares rug but lockfile lacks gmp-mpfr-sys fails" {
    printf '[[package]]\nname = "other"\nversion = "0.3.1"\n' >"${CRATE}/Cargo.lock"
    printf '[dependencies]\nrug = "1.30"\n' >"${CRATE}/Cargo.toml"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"declares rug but Cargo.lock has no gmp-mpfr-sys"* ]]
    assert_out_empty
}

@test "absent LGPL text fails with its own wording" {
    write_gmp_lock
    rm "${LIC}/LGPL-3.0.txt"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"licence text not found"*"LGPL-3.0.txt"* ]]
    [[ "$output" != *"missing Cargo.lock"* ]]
    assert_out_empty
}

@test "empty LGPL text fails with its own wording" {
    write_gmp_lock
    : >"${LIC}/LGPL-3.0.txt"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"licence text is empty"*"LGPL-3.0.txt"* ]]
    [[ "$output" != *"missing Cargo.lock"* ]]
    assert_out_empty
}

@test "absent GPL text fails naming the GPL file" {
    write_gmp_lock
    rm "${LIC}/GPL-3.0.txt"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"licence text not found"*"/GPL-3.0.txt"* ]]
    [[ "$output" != *"LGPL-3.0.txt"* ]]
    assert_out_empty
}

@test "empty GPL text fails naming the GPL file" {
    write_gmp_lock
    : >"${LIC}/GPL-3.0.txt"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"licence text is empty"*"/GPL-3.0.txt"* ]]
    [[ "$output" != *"LGPL-3.0.txt"* ]]
    assert_out_empty
}

@test "nonexistent out-dir fails with its own wording" {
    write_gmp_lock
    run "${SCRIPT}" "${CRATE}" "${BATS_TEST_TMPDIR}/nope"
    [ "$status" -ne 0 ]
    [[ "$output" == *"output directory not writable"* ]]
    [[ "$output" != *"missing Cargo.lock"* ]]
}

@test "read-only out-dir fails with its own wording" {
    if [ "$(id -u)" -eq 0 ]; then skip "root ignores directory modes"; fi
    write_gmp_lock
    chmod 0555 "${OUT}"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    chmod 0755 "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"output directory not writable"* ]]
    assert_out_empty
}

@test "unreadable Cargo.lock fails closed with cannot read" {
    if [ "$(id -u)" -eq 0 ]; then skip "root ignores file modes"; fi
    write_gmp_lock
    printf '[dependencies.rug]\nversion = "1"\n' >"${CRATE}/Cargo.toml"
    chmod 000 "${CRATE}/Cargo.lock"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"cannot read"* ]]
    [[ "$output" != *"links no LGPL"* ]]
    assert_out_empty
}

@test "unreadable Cargo.toml fails closed" {
    if [ "$(id -u)" -eq 0 ]; then skip "root ignores file modes"; fi
    printf '[[package]]\nname = "other"\nversion = "0.3.1"\n' >"${CRATE}/Cargo.lock"
    printf '[dependencies]\n' >"${CRATE}/Cargo.toml"
    chmod 000 "${CRATE}/Cargo.toml"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"cannot read"*"Cargo.toml"* ]]
    assert_out_empty
}

@test "table-form [dependencies.rug] without gmp-mpfr-sys in lock fails" {
    printf '[[package]]\nname = "other"\nversion = "0.3.1"\n' >"${CRATE}/Cargo.lock"
    printf '[dependencies.rug]\nversion = "1"\n' >"${CRATE}/Cargo.toml"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"declares rug"* ]]
    assert_out_empty
}

@test "renamed dependency with package = rug without gmp-mpfr-sys in lock fails" {
    printf '[[package]]\nname = "other"\nversion = "0.3.1"\n' >"${CRATE}/Cargo.lock"
    printf '[dependencies]\nbig = { package = "rug", version = "1" }\n' >"${CRATE}/Cargo.toml"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"declares rug"* ]]
    assert_out_empty
}

@test "rug.workspace form without gmp-mpfr-sys in lock fails" {
    printf '[[package]]\nname = "other"\nversion = "0.3.1"\n' >"${CRATE}/Cargo.lock"
    printf '[dependencies]\nrug.workspace = true\n' >"${CRATE}/Cargo.toml"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"declares rug"* ]]
}

@test "rug locked but gmp-mpfr-sys not locked fails with its own wording" {
    printf '[[package]]\nname = "rug"\nversion = "1.30.0"\n' >"${CRATE}/Cargo.lock"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"rug is locked but gmp-mpfr-sys is not"* ]]
    assert_out_empty
}
