#!/usr/bin/env bats

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/calls"
    export MOCK_GH_COUNTER_FILE="${BATS_TEST_TMPDIR}/gh_counter"
    export MOCK_GH_PR_SHA="abc123def456"
    export GITHUB_REPOSITORY="test-owner/test-repo"
    export CI_GATE_POLL_INTERVAL=0
    export CI_GATE_MAX_POLLS=5
}

@test "all required checks pass → exit 0" {
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
}

@test "required check failure → exit 1 naming failed check" {
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"completed","conclusion":"failure"}'
    run bash -c "GITHUB_REPOSITORY=test-owner/test-repo MOCK_GH_PR_SHA=abc123 MOCK_GH_CHECK_RUNS_1='{\"name\":\"Test pi-rs\",\"status\":\"completed\",\"conclusion\":\"failure\"}' MOCK_GH_COUNTER_FILE=${BATS_TEST_TMPDIR}/gh_counter2 CI_GATE_POLL_INTERVAL=0 CI_GATE_MAX_POLLS=5 ${REPO_ROOT}/scripts/ci-gate.sh 42 2>&1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Test pi-rs"* ]]
}

@test "advisory snyk-scan failure with required passing → exit 0" {
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"completed","conclusion":"success"}
{"name":"snyk-scan","status":"completed","conclusion":"failure"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
}

@test "polls until terminal: in-progress first then success → exit 0" {
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"in_progress","conclusion":""}'
    export MOCK_GH_CHECK_RUNS_2='{"name":"Test pi-rs","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
}

@test "timeout when checks remain in-progress → exit 1 with timeout message" {
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"in_progress","conclusion":""}'
    export CI_GATE_MAX_POLLS=1
    run bash -c "GITHUB_REPOSITORY=test-owner/test-repo MOCK_GH_PR_SHA=abc123 MOCK_GH_CHECK_RUNS_1='{\"name\":\"Test pi-rs\",\"status\":\"in_progress\",\"conclusion\":\"\"}' MOCK_GH_COUNTER_FILE=${BATS_TEST_TMPDIR}/gh_counter3 CI_GATE_POLL_INTERVAL=0 CI_GATE_MAX_POLLS=1 ${REPO_ROOT}/scripts/ci-gate.sh 42 2>&1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"imeout"* ]]
}

@test "no required checks triggered (docs-only PR) → exit 0" {
    export MOCK_GH_CHECK_RUNS_1='{"name":"snyk-scan","status":"completed","conclusion":"failure"}
{"name":"secret-scan","status":"completed","conclusion":"success"}
{"name":"auto-merge","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
}

@test "missing PR number argument → exit 1 with usage message" {
    run bash -c "${REPO_ROOT}/scripts/ci-gate.sh 2>&1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"sage"* ]]
}

@test "gh CLI failure → exit 1" {
    export MOCK_GH_EXIT=1
    run bash -c "GITHUB_REPOSITORY=test-owner/test-repo MOCK_GH_EXIT=1 MOCK_GH_COUNTER_FILE=${BATS_TEST_TMPDIR}/gh_counter4 ${REPO_ROOT}/scripts/ci-gate.sh 42 2>&1"
    [ "$status" -eq 1 ]
}

@test "self-check (auto-merge) in-progress does not block polling → exit 0" {
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"completed","conclusion":"success"}
{"name":"auto-merge","status":"in_progress","conclusion":""}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
}

@test "required check in skipped state → exit 0" {
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"completed","conclusion":"skipped"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
}
