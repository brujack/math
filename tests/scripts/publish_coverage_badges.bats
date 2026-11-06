#!/usr/bin/env bats

# publish-coverage-badges.sh copies the PR's own coverage-badge-* artifacts to the
# coverage-data branch. gh and git are the PATH mocks in tests/mocks/.

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export HOME="${BATS_TEST_TMPDIR}/home"
    mkdir -p "${HOME}"
    export TMPDIR="${BATS_TEST_TMPDIR}/tmp"
    mkdir -p "${TMPDIR}"
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/calls"
    export MOCK_GH_ARTIFACT_ROOT="${BATS_TEST_TMPDIR}/artifacts"
    export GITHUB_REPOSITORY="test-owner/test-repo"
    export PUBLISH_RETRY_SLEEP=0
    export MOCK_GIT_DIFF_QUIET_RC=1
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    SCRIPT="${REPO_ROOT}/scripts/publish-coverage-badges.sh"
}

# add_badge <run id> <project> <lang> <message> <color>
add_badge() {
    local dir="${MOCK_GH_ARTIFACT_ROOT}/${1}/coverage-badge-${2}-${3}/${2}"
    mkdir -p "${dir}"
    printf '{"schemaVersion":1,"label":"coverage","message":"%s","color":"%s"}\n' \
        "${4}" "${5}" > "${dir}/${3}.json"
}

calls() { cat "${MOCK_CALLS_FILE}" 2>/dev/null; }

count_calls() { calls | command grep -c -- "${1}"; }

@test "no successful pull_request runs -> notice, exit 0, nothing pushed" {
    export MOCK_GH_WORKFLOW_RUNS=""
    run "${SCRIPT}" abc123
    [ "$status" -eq 0 ]
    [[ "$output" == *"no coverage runs"* ]]
    [ "$(count_calls 'git ')" -eq 0 ]
}

@test "runs without badge artifacts (docs-only PR) -> notice, exit 0" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    mkdir -p "${MOCK_GH_ARTIFACT_ROOT}/100"
    run "${SCRIPT}" abc123
    [ "$status" -eq 0 ]
    [[ "$output" == *"no coverage-badge artifacts"* ]]
    [ "$(count_calls 'git ')" -eq 0 ]
}

@test "missing head sha -> usage error, exit 1" {
    run "${SCRIPT}"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Usage"* ]]
}

@test "artifacts found -> one commit, one push, files copied to their paths" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100\n11\t101'
    add_badge 100 fib rust "95%" brightgreen
    add_badge 101 fib python "81%" green
    run "${SCRIPT}" abc123
    [ "$status" -eq 0 ]
    [ "$(count_calls 'commit')" -eq 1 ]
    [ "$(count_calls 'push')" -eq 1 ]
    calls | command grep -q 'coverage: publish badges for abc123'
    calls | command grep -q 'push origin coverage-data'
    calls | command grep -q 'worktree add'
}

@test "copied files carry the validated content (snapshot taken at commit)" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    add_badge 100 pi rust "93%" brightgreen
    export MOCK_GIT_COMMIT_SNAPSHOT="${BATS_TEST_TMPDIR}/keep"
    run "${SCRIPT}" abc123
    [ "$status" -eq 0 ]
    [ "$(jq -r .message "${MOCK_GIT_COMMIT_SNAPSHOT}/pi/rust.json")" = "93%" ]
    [ "$(jq -r .color "${MOCK_GIT_COMMIT_SNAPSHOT}/pi/rust.json")" = "brightgreen" ]
}

@test "latest run per workflow wins (highest run id)" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100\n10\t105'
    add_badge 100 fib rust "70%" yellow
    add_badge 105 fib rust "95%" brightgreen
    export MOCK_GIT_COMMIT_SNAPSHOT="${BATS_TEST_TMPDIR}/keep"
    run "${SCRIPT}" abc123
    [ "$status" -eq 0 ]
    [ "$(jq -r .message "${MOCK_GIT_COMMIT_SNAPSHOT}/fib/rust.json")" = "95%" ]
    [ "$(count_calls 'run download 100')" -eq 0 ]
    [ "$(count_calls 'run download 105')" -eq 1 ]
}

@test "nothing staged after copy (badge already published) -> exit 0, no commit" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    add_badge 100 fib rust "95%" brightgreen
    export MOCK_GIT_DIFF_QUIET_RC=0
    run "${SCRIPT}" abc123
    [ "$status" -eq 0 ]
    [ "$(count_calls 'commit')" -eq 0 ]
    [ "$(count_calls 'push')" -eq 0 ]
}

@test "push fails 3x -> exactly 3 attempts, ::error::, exit 1" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    add_badge 100 fib rust "95%" brightgreen
    export MOCK_GIT_EXIT_PUSH=1
    run "${SCRIPT}" abc123
    [ "$status" -eq 1 ]
    [[ "$output" == *"::error::"* ]]
    [ "$(count_calls 'push')" -eq 3 ]
}

@test "push fails once then succeeds -> exit 0" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    add_badge 100 fib rust "95%" brightgreen
    # A one-shot failure: the first push call trips, later ones pass.
    cat > "${BATS_TEST_TMPDIR}/flaky" <<'FLAKY'
#!/usr/bin/env bash
printf 'git %s\n' "$*" >> "${MOCK_CALLS_FILE}"
case " $* " in
    *" push "*)
        if [[ ! -e "${FLAKY_MARK}" ]]; then : > "${FLAKY_MARK}"; exit 1; fi ;;
    *" diff "*) exit 1 ;;
esac
exit 0
FLAKY
    mkdir -p "${BATS_TEST_TMPDIR}/flakybin"
    mv "${BATS_TEST_TMPDIR}/flaky" "${BATS_TEST_TMPDIR}/flakybin/git"
    chmod +x "${BATS_TEST_TMPDIR}/flakybin/git"
    export FLAKY_MARK="${BATS_TEST_TMPDIR}/flaky-mark"
    PATH="${BATS_TEST_TMPDIR}/flakybin:${PATH}" run "${SCRIPT}" abc123
    [ "$status" -eq 0 ]
    [ "$(count_calls 'push')" -eq 2 ]
}

@test "worktree cannot be created -> ::error::, exit 1, nothing pushed" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    add_badge 100 fib rust "95%" brightgreen
    export MOCK_GIT_EXIT_WORKTREE=1
    run "${SCRIPT}" abc123
    [ "$status" -eq 1 ]
    [[ "$output" == *"::error::"* ]]
    [ "$(count_calls 'push')" -eq 0 ]
}

@test "no coverage-data branch on origin -> orphan worktree is created" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    add_badge 100 fib rust "95%" brightgreen
    export MOCK_GIT_EXIT_FETCH=1
    run "${SCRIPT}" abc123
    [ "$status" -eq 0 ]
    calls | command grep -q -- '--orphan'
    [ "$(count_calls 'push')" -eq 1 ]
}

@test "gh run listing fails -> ::error::, exit 1" {
    export MOCK_GH_EXIT=1
    run "${SCRIPT}" abc123
    [ "$status" -eq 1 ]
    [[ "$output" == *"::error::"* ]]
}

@test "gh run download fails -> ::error::, exit 1, nothing pushed" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    add_badge 100 fib rust "95%" brightgreen
    export MOCK_GH_EXIT_RUN_DOWNLOAD=1
    run "${SCRIPT}" abc123
    [ "$status" -eq 1 ]
    [[ "$output" == *"::error::"* ]]
    [ "$(count_calls 'push')" -eq 0 ]
}

# Rejections: artifact content is produced by the PR, so nothing malformed is copied.

@test "wrong filename (fib/evil.json) -> rejected, exit 1, nothing pushed" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    local dir="${MOCK_GH_ARTIFACT_ROOT}/100/coverage-badge-fib-rust/fib"
    mkdir -p "${dir}"
    printf '{"schemaVersion":1,"label":"coverage","message":"95%%","color":"green"}\n' > "${dir}/evil.json"
    run "${SCRIPT}" abc123
    [ "$status" -eq 1 ]
    [[ "$output" == *"::error::"* ]]
    [ "$(count_calls 'push')" -eq 0 ]
    [ "$(count_calls 'worktree')" -eq 0 ]
}

@test "nested path (a/b/rust.json) -> rejected" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    local dir="${MOCK_GH_ARTIFACT_ROOT}/100/coverage-badge-b-rust/a/b"
    mkdir -p "${dir}"
    printf '{"schemaVersion":1,"label":"coverage","message":"95%%","color":"green"}\n' > "${dir}/rust.json"
    run "${SCRIPT}" abc123
    [ "$status" -eq 1 ]
    [ "$(count_calls 'push')" -eq 0 ]
}

@test "artifact name disagreeing with its path -> rejected" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    local dir="${MOCK_GH_ARTIFACT_ROOT}/100/coverage-badge-fib-rust/pi"
    mkdir -p "${dir}"
    printf '{"schemaVersion":1,"label":"coverage","message":"95%%","color":"green"}\n' > "${dir}/rust.json"
    run "${SCRIPT}" abc123
    [ "$status" -eq 1 ]
    [ "$(count_calls 'push')" -eq 0 ]
}

@test "symlink in an artifact -> rejected" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    add_badge 100 fib rust "95%" brightgreen
    ln -s /etc/passwd "${MOCK_GH_ARTIFACT_ROOT}/100/coverage-badge-fib-rust/fib/python.json"
    run "${SCRIPT}" abc123
    [ "$status" -eq 1 ]
    [ "$(count_calls 'push')" -eq 0 ]
}

@test "malformed JSON -> rejected" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100'
    local dir="${MOCK_GH_ARTIFACT_ROOT}/100/coverage-badge-fib-rust/fib"
    mkdir -p "${dir}"
    printf 'not json\n' > "${dir}/rust.json"
    run "${SCRIPT}" abc123
    [ "$status" -eq 1 ]
    [[ "$output" == *"::error::"* ]]
    [ "$(count_calls 'push')" -eq 0 ]
}

@test "one bad file among good ones -> nothing is pushed" {
    export MOCK_GH_WORKFLOW_RUNS=$'10\t100\n11\t101'
    add_badge 100 fib rust "95%" brightgreen
    add_badge 101 pi rust "95%" "hotpink"
    run "${SCRIPT}" abc123
    [ "$status" -eq 1 ]
    [ "$(count_calls 'push')" -eq 0 ]
}

# valid_badge_json: schemaVersion 1, label coverage, message N%, colour from the set.
@test "valid_badge_json rejects each wrong field and accepts the good shape" {
    # shellcheck source=/dev/null
    source "${SCRIPT}"
    local f="${BATS_TEST_TMPDIR}/b.json"
    printf '{"schemaVersion":1,"label":"coverage","message":"100%%","color":"red"}' > "${f}"
    valid_badge_json "${f}"
    printf '{"schemaVersion":2,"label":"coverage","message":"9%%","color":"red"}' > "${f}"
    run valid_badge_json "${f}"
    [ "$status" -ne 0 ]
    printf '{"schemaVersion":1,"label":"other","message":"9%%","color":"red"}' > "${f}"
    run valid_badge_json "${f}"
    [ "$status" -ne 0 ]
    printf '{"schemaVersion":1,"label":"coverage","message":"9","color":"red"}' > "${f}"
    run valid_badge_json "${f}"
    [ "$status" -ne 0 ]
    printf '{"schemaVersion":1,"label":"coverage","message":"1000%%","color":"red"}' > "${f}"
    run valid_badge_json "${f}"
    [ "$status" -ne 0 ]
    printf '{"schemaVersion":1,"label":"coverage","message":"9%%","color":"blue"}' > "${f}"
    run valid_badge_json "${f}"
    [ "$status" -ne 0 ]
    printf '{"schemaVersion":1,"label":"coverage","message":"9%%","color":"red","x":1}' > "${f}"
    run valid_badge_json "${f}"
    [ "$status" -ne 0 ]
    run valid_badge_json "${BATS_TEST_TMPDIR}/missing.json"
    [ "$status" -ne 0 ]
}

# valid_badge_path: <project>/(rust|python).json and nothing else.
@test "valid_badge_path rejects traversal, absolute, nested and wrong names" {
    # shellcheck source=/dev/null
    source "${SCRIPT}"
    valid_badge_path "fib/rust.json"
    valid_badge_path "perfect-numbers/python.json"
    run valid_badge_path "../x/rust.json"
    [ "$status" -ne 0 ]
    run valid_badge_path "fib/../rust.json"
    [ "$status" -ne 0 ]
    run valid_badge_path "/etc/rust.json"
    [ "$status" -ne 0 ]
    run valid_badge_path "fib/evil.json"
    [ "$status" -ne 0 ]
    run valid_badge_path "a/b/rust.json"
    [ "$status" -ne 0 ]
    run valid_badge_path "rust.json"
    [ "$status" -ne 0 ]
    run valid_badge_path ".hidden/rust.json"
    [ "$status" -ne 0 ]
    run valid_badge_path ""
    [ "$status" -ne 0 ]
}
