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
    printf 'GNU LESSER GENERAL PUBLIC LICENSE\nfixture lgpl\n' >"${LIC}/LGPL-3.0.txt"
    printf 'GNU GENERAL PUBLIC LICENSE\nfixture gpl\n' >"${LIC}/GPL-3.0.txt"
    export LICENSES_DIR="${LIC}"
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

@test "GMP lockfile writes one notices file with components and both licence texts" {
    write_gmp_lock
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -eq 0 ]
    [ "$(find "${OUT}" -mindepth 1 | wc -l)" -eq 1 ]
    f="${OUT}/THIRD-PARTY-NOTICES.txt"
    [ -f "$f" ]
    for s in "gmp-mpfr-sys 1.7.0" "rug 1.30.0" "GMP" "MPFR" "MPC" "LGPL-3.0-or-later" \
        "statically linked" "GNU LESSER GENERAL PUBLIC LICENSE" "GNU GENERAL PUBLIC LICENSE"; do
        command grep -qF -- "$s" "$f"
    done
}

@test "non-GMP lockfile states no LGPL components and omits GPL text" {
    printf '[[package]]\nname = "other"\nversion = "0.3.1"\n' >"${CRATE}/Cargo.lock"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -eq 0 ]
    [ "$(find "${OUT}" -mindepth 1 | wc -l)" -eq 1 ]
    command grep -qF "links no LGPL components" "${OUT}/THIRD-PARTY-NOTICES.txt"
    ! command grep -qF "GNU GENERAL PUBLIC LICENSE" "${OUT}/THIRD-PARTY-NOTICES.txt"
}

@test "missing Cargo.lock fails naming the lockfile" {
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"missing Cargo.lock"* ]]
}

@test "absent LGPL text fails with its own wording" {
    write_gmp_lock
    rm "${LIC}/LGPL-3.0.txt"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"licence text not found"* ]]
    [[ "$output" != *"missing Cargo.lock"* ]]
    [ ! -e "${OUT}/THIRD-PARTY-NOTICES.txt" ]
}

@test "empty LGPL text fails with its own wording" {
    write_gmp_lock
    : >"${LIC}/LGPL-3.0.txt"
    run "${SCRIPT}" "${CRATE}" "${OUT}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"licence text is empty"* ]]
    [[ "$output" != *"missing Cargo.lock"* ]]
    [ ! -e "${OUT}/THIRD-PARTY-NOTICES.txt" ]
}

@test "nonexistent out-dir fails with its own wording" {
    write_gmp_lock
    run "${SCRIPT}" "${CRATE}" "${BATS_TEST_TMPDIR}/nope"
    [ "$status" -ne 0 ]
    [[ "$output" == *"output directory not writable"* ]]
    [[ "$output" != *"missing Cargo.lock"* ]]
}
