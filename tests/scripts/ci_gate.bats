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
    export REQUIRED_CHECKS_FILE="${BATS_TEST_TMPDIR}/required-status-checks"
    printf 'secret-scan\n' > "${REQUIRED_CHECKS_FILE}"
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

@test "failing Coverage check blocks merge even when Test passes → exit 1 naming it" {
    run bash -c "GITHUB_REPOSITORY=test-owner/test-repo MOCK_GH_PR_SHA=abc123 MOCK_GH_CHECK_RUNS_1='{\"name\":\"Test pi-rs\",\"status\":\"completed\",\"conclusion\":\"success\"}
{\"name\":\"Coverage pi-rs\",\"status\":\"completed\",\"conclusion\":\"failure\"}' MOCK_GH_COUNTER_FILE=${BATS_TEST_TMPDIR}/gh_counter_cov CI_GATE_POLL_INTERVAL=0 CI_GATE_MAX_POLLS=5 ${REPO_ROOT}/scripts/ci-gate.sh 42 2>&1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Coverage pi-rs"* ]]
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

# Superseded-run tests: two check suites (one per workflow run) of the same
# workflow (id 7) carry the same check name; only the newer run counts.

@test "superseded cancelled run of a required check does not fail the gate → exit 0" {
    export MOCK_GH_WORKFLOW_RUNS='{"suite":1,"wf":7}
{"suite":2,"wf":7}'
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"bash-coverage","status":"completed","conclusion":"cancelled"}
{"id":200,"suite":2,"name":"bash-coverage","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
}

@test "newer failed run overrides an older success of the same check → exit 1" {
    export MOCK_GH_WORKFLOW_RUNS='{"suite":1,"wf":7}
{"suite":2,"wf":7}'
    export MOCK_GH_CHECK_RUNS_1='{"id":200,"suite":2,"name":"bash-coverage","status":"completed","conclusion":"failure"}
{"id":100,"suite":1,"name":"bash-coverage","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 1 ]
    [[ "$output" == *"bash-coverage"* ]]
}

@test "newer in-progress run keeps polling despite an older completed run → exit 0 on completion" {
    export MOCK_GH_WORKFLOW_RUNS='{"suite":1,"wf":7}
{"suite":2,"wf":7}'
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"bash-coverage","status":"completed","conclusion":"cancelled"}
{"id":200,"suite":2,"name":"bash-coverage","status":"in_progress","conclusion":""}'
    export MOCK_GH_CHECK_RUNS_2='{"id":100,"suite":1,"name":"bash-coverage","status":"completed","conclusion":"cancelled"}
{"id":200,"suite":2,"name":"bash-coverage","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
    [ "$(cat "${MOCK_GH_COUNTER_FILE}")" -eq 2 ]
}

@test "same check name in two different workflows is not collapsed → exit 1 on the older failure" {
    export MOCK_GH_WORKFLOW_RUNS='{"suite":1,"wf":7}
{"suite":2,"wf":8}'
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"test","status":"completed","conclusion":"failure"}
{"id":200,"suite":2,"name":"test","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 1 ]
    [[ "$output" == *"test"* ]]
}

@test "check suites with no workflow run (non-Actions apps) are not collapsed → exit 1" {
    export MOCK_GH_WORKFLOW_RUNS=''
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"GitGuardian Security Checks","status":"completed","conclusion":"failure"}
{"id":200,"suite":2,"name":"GitGuardian Security Checks","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 1 ]
}

@test "newer skipped run does not hide an older failure of the same check → exit 1" {
    export MOCK_GH_WORKFLOW_RUNS='{"suite":1,"wf":7}
{"suite":2,"wf":7}'
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"bash-coverage","status":"completed","conclusion":"failure"}
{"id":200,"suite":2,"name":"bash-coverage","status":"completed","conclusion":"skipped"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 1 ]
    [[ "$output" == *"bash-coverage"* ]]
}

@test "check runs with no suite id are not collapsed → exit 1 on the older failure" {
    export MOCK_GH_WORKFLOW_RUNS=''
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":null,"name":"bash-coverage","status":"completed","conclusion":"failure"}
{"id":200,"suite":null,"name":"bash-coverage","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 1 ]
}

@test "workflow-runs lookup failure fails closed → exit 1" {
    export MOCK_GH_EXIT_ACTIONS_RUNS=1
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"bash-coverage","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 1 ]
    grep -q 'actions/runs' "${MOCK_CALLS_FILE}"
}

# Exclusion is by exact name: a required check whose name merely is a substring of
# an excluded one (here "scan" inside "snyk-scan") must still be gated.
@test "required check named as a substring of an excluded name fails the gate → exit 1" {
    export MOCK_GH_CHECK_RUNS_1='{"name":"scan","status":"completed","conclusion":"failure"}
{"name":"snyk-scan","status":"completed","conclusion":"failure"}'
    run bash -c "${REPO_ROOT}/scripts/ci-gate.sh 42 2>&1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Required checks failed"* ]]
    failed_block="${output#*Required checks failed:}"
    [[ "$failed_block" == *"scan"* ]]
    [[ "$failed_block" != *"snyk-scan"* ]]
}

@test "in-progress check named as a substring of an excluded name still blocks → timeout" {
    export MOCK_GH_CHECK_RUNS='{"name":"scan","status":"in_progress","conclusion":""}'
    export CI_GATE_MAX_POLLS=2
    export CI_GATE_POLL_INTERVAL=0
    run bash -c "${REPO_ROOT}/scripts/ci-gate.sh 42 2>&1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Timeout: checks did not complete"* ]]
}

@test "failing check-run from a workflow_dispatch run is ignored → exit 0, not named" {
    export MOCK_GH_WORKFLOW_RUNS='{"suite":1,"wf":7,"event":"pull_request"}
{"suite":9,"wf":8,"event":"workflow_dispatch"}'
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"bash-coverage","status":"completed","conclusion":"success"}
{"id":300,"suite":9,"name":"notify","status":"completed","conclusion":"failure"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
    [[ "$output" != *"notify"* ]]
}

@test "failing check-run from a schedule run is ignored → exit 0, not named" {
    export MOCK_GH_WORKFLOW_RUNS='{"suite":1,"wf":7,"event":"pull_request"}
{"suite":9,"wf":8,"event":"schedule"}'
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"bash-coverage","status":"completed","conclusion":"success"}
{"id":300,"suite":9,"name":"notify","status":"completed","conclusion":"failure"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
    [[ "$output" != *"notify"* ]]
}

@test "failing check-run from a pull_request run still fails → exit 1" {
    export MOCK_GH_WORKFLOW_RUNS='{"suite":1,"wf":7,"event":"pull_request"}
{"suite":9,"wf":8,"event":"pull_request"}'
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"bash-coverage","status":"completed","conclusion":"success"}
{"id":300,"suite":9,"name":"notify","status":"completed","conclusion":"failure"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 1 ]
    [[ "$output" == *"notify"* ]]
}

@test "failing check-run whose workflow run has no event field fails closed → exit 1" {
    export MOCK_GH_WORKFLOW_RUNS='{"suite":1,"wf":7,"event":"pull_request"}
{"suite":9,"wf":8}'
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"bash-coverage","status":"completed","conclusion":"success"}
{"id":300,"suite":9,"name":"notify","status":"completed","conclusion":"failure"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 1 ]
    [[ "$output" == *"notify"* ]]
}

@test "failing check-run whose suite has no workflow run still fails → exit 1" {
    export MOCK_GH_WORKFLOW_RUNS='{"suite":1,"wf":7,"event":"workflow_dispatch"}'
    export MOCK_GH_CHECK_RUNS_1='{"id":300,"suite":9,"name":"external-app","status":"completed","conclusion":"failure"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 1 ]
    [[ "$output" == *"external-app"* ]]
}

@test "dispatch run of the same workflow never supersedes a PR run → exit 1 on the PR failure" {
    export MOCK_GH_WORKFLOW_RUNS='{"suite":1,"wf":7,"event":"pull_request"}
{"suite":2,"wf":7,"event":"workflow_dispatch"}'
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"test","status":"completed","conclusion":"failure"}
{"id":200,"suite":2,"name":"test","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 1 ]
    [[ "$output" == *"test"* ]]
}

@test "the actions/runs lookup requests the event field" {
    export MOCK_GH_CHECK_RUNS_1='{"id":100,"suite":1,"name":"test","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
    command grep -F "actions/runs" "${MOCK_CALLS_FILE}" | command grep -qF "event: .event"
}

# Required-context tests (R36): the gate waits for every context listed in the tracked
# required-status-checks file (a mirror of branch protection; GITHUB_TOKEN cannot read
# protection itself), even one that registers after all other checks finish.

write_required() {
    export REQUIRED_CHECKS_FILE="${BATS_TEST_TMPDIR}/required-status-checks"
    printf '%s\n' "$@" > "${REQUIRED_CHECKS_FILE}"
}

@test "required context registering late (pull_request_target) is waited for → exit 0 on poll 2" {
    write_required '# header' 'mutation-gate-items'
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"completed","conclusion":"success"}'
    export MOCK_GH_CHECK_RUNS_2='{"name":"Test pi-rs","status":"completed","conclusion":"success"}
{"name":"mutation-gate-items","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
    [ "$(cat "${MOCK_GH_COUNTER_FILE}")" -eq 2 ]
}

@test "required context that never registers ends red at the poll timeout → exit 1 naming it" {
    write_required 'mutation-gate-items'
    export MOCK_GH_CHECK_RUNS='{"name":"Test pi-rs","status":"completed","conclusion":"success"}'
    export CI_GATE_MAX_POLLS=3
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42 2>&1
    [ "$status" -eq 1 ]
    [[ "$output" == *"imeout"* ]]
    [[ "$output" == *"mutation-gate-items"* ]]
    [ "$(cat "${MOCK_GH_COUNTER_FILE}")" -eq 3 ]
}

@test "late-registering required context that fails → exit 1 naming it" {
    write_required 'mutation-gate-items'
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"completed","conclusion":"success"}'
    export MOCK_GH_CHECK_RUNS_2='{"name":"Test pi-rs","status":"completed","conclusion":"success"}
{"name":"mutation-gate-items","status":"completed","conclusion":"failure"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42 2>&1
    [ "$status" -eq 1 ]
    [[ "$output" == *"mutation-gate-items"* ]]
}

@test "missing required-checks file fails closed before polling → exit 1" {
    export REQUIRED_CHECKS_FILE="${BATS_TEST_TMPDIR}/absent"
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42 2>&1
    [ "$status" -eq 1 ]
    [[ "$output" == *"Cannot read"* ]]
    [ ! -e "${MOCK_GH_COUNTER_FILE}" ]
}

@test "empty required-checks file (only comments and blanks) fails closed → exit 1" {
    write_required '# only a comment' '' '   '
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42 2>&1
    [ "$status" -eq 1 ]
    [[ "$output" == *"required-checks file"* ]]
    [ ! -e "${MOCK_GH_COUNTER_FILE}" ]
}

@test "required self-checks and advisory checks are not waited for → exit 0" {
    write_required 'secret-scan' 'auto-merge' 'snyk-scan'
    export MOCK_GH_CHECK_RUNS_1='{"name":"Test pi-rs","status":"completed","conclusion":"success"}'
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42
    [ "$status" -eq 0 ]
    [ "$(cat "${MOCK_GH_COUNTER_FILE}")" -eq 1 ]
}

@test "default required-checks path is the tracked file: unregistered mutation-pr times out → exit 1" {
    unset REQUIRED_CHECKS_FILE
    export MOCK_GH_CHECK_RUNS='{"name":"Test pi-rs","status":"completed","conclusion":"success"}'
    export CI_GATE_MAX_POLLS=2
    run "${REPO_ROOT}/scripts/ci-gate.sh" 42 2>&1
    [ "$status" -eq 1 ]
    [[ "$output" == *"mutation-pr"* ]]
}

@test "the tracked required-checks file lists secret-scan and mutation-pr only" {
    run bash -c "sed -e 's/#.*//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*\$//' '${REPO_ROOT}/.github/required-status-checks' | awk 'NF'"
    [ "$status" -eq 0 ]
    [ "$output" = "secret-scan
mutation-pr" ]
}
