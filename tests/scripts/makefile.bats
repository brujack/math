#!/usr/bin/env bats

load '../helpers/common'

@test "make test-hooks recipe calls bats --recursive tests/" {
    run make -C "${REPO_ROOT}" -n test-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"bats --recursive tests/"* ]]
}

@test "make install-hooks recipe links pre-commit hook" {
    run make -C "${REPO_ROOT}" -n install-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"scripts/pre-commit"* ]]
}

@test "make install-hooks recipe links pre-push hook" {
    run make -C "${REPO_ROOT}" -n install-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"scripts/pre-push"* ]]
}

@test "install-hooks and test-hooks are declared .PHONY" {
    run grep -E "^\.PHONY" "${REPO_ROOT}/Makefile"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"install-hooks"* ]]
    [[ "${output}" == *"test-hooks"* ]]
}
