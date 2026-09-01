#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    source "${REPO_ROOT}/scripts/mutation-notify.sh"
    export UNIT_NOUN="crate"
    export RUN_URL="https://github.com/brujack/math/actions/runs/123"
    export ARTIFACT_DIR="${BATS_TEST_TMPDIR}/artifact"
    # A malformed spec (no slash) so that if a load_mocks regression ever let
    # a real `gh` run, it would fail in gh's own argument parser before any
    # network call. A well-formed OWNER/REPO fixture would instead reach a
    # live authenticated GraphQL request -- the PATH mock is the only thing
    # standing between a regressed test and the operator's real tracker, and
    # this makes REPO itself unresolvable as a second line of defense.
    export REPO="invalid-repo-spec-no-slash"
    export ISSUE_TITLE="mutation-testing: monthly run failed"
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/calls"
}

# Lifted out of a single test so a --repo regression on any gh call site --
# including `gh label create`, whose --repo is exercised only on the
# no-existing-issue red path -- is caught wherever that call site actually
# fires, rather than depending on which literal strings one test greps for.
#
# Anchored on lines starting "gh " rather than every non-blank line: a
# red-path --body is build_body()'s multi-line output, and the mock logs
# each call's full "$*" verbatim, embedded newlines included -- so one gh
# invocation with a red-path body spans several lines in MOCK_CALLS_FILE.
# Counting every non-blank line (as this helper's first draft did) inflates
# the total against a single-line --repo hit and fails on every call whose
# body has more than one line, which is every red-path create/comment.
assert_all_gh_calls_carry_repo() {
    local _total _with_repo
    _total=$(grep -c '^gh ' "${MOCK_CALLS_FILE}")
    _with_repo=$(grep '^gh ' "${MOCK_CALLS_FILE}" | grep -c -- "--repo")
    [ "${_total}" -gt 0 ]
    [ "${_total}" -eq "${_with_repo}" ]
}

# Every body-asserting case below checks the full contract, not just a
# substring: the body must start with "Cause: <token>" and end with
# "Run: ${RUN_URL}" -- both are stated twice in the plan as the stable
# surface tests pin, and neither was asserted before this fix round.

@test "marker + status with one red file -> verdicts-present, names the crate" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"- pi-rs"* ]]
}

@test "marker + status with two red files -> both crate names appear" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"
    printf 'red: e-rs - exit code 3\n' > "${ARTIFACT_DIR}/status/e-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"- pi-rs"* ]]
    [[ "${body}" == *"- e-rs"* ]]
}

@test "marker + status with no red line -> none flagged message" {
    # The fixture must contain the substring "red" NOT at the start of the
    # line, so a mutant that drops the ^ anchor from grep -l '^red' is
    # distinguishable: anchored, this file never matches; unanchored, it
    # would.
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'green: pi-rs - 0 red mutants\n' > "${ARTIFACT_DIR}/status/pi-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"- (none flagged; see run log)"* ]]
}

@test "verdicts-present with a mixed red and green status directory lists only the red crate" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"
    printf 'green: e-rs - ok\n' > "${ARTIFACT_DIR}/status/e-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == *"- pi-rs"* ]]
    [[ "${body}" != *"e-rs"* ]]
}

@test "verdicts-present survives a status filename containing a space" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: twin primes-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/twin primes-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]

    body="$(build_body "${result}")"
    [[ "${body}" == *"- twin primes-rs"* ]]
}

@test "marker + mutants.out, no status -> loop-began-no-verdict" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/pi-rs/mutants.out"

    result="$(attribute)"
    [ "${result}" = "loop-began-no-verdict" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"loop began and no verdict was written"* ]]
}

@test "marker + amicable/mutants-report.txt, no status -> loop-began-no-verdict (python artifact shape)" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/amicable"
    printf 'placeholder\n' > "${ARTIFACT_DIR}/amicable/mutants-report.txt"

    result="$(attribute)"
    [ "${result}" = "loop-began-no-verdict" ]
}

@test "marker + amicable/cosmic-ray-session.sqlite, no status -> loop-began-no-verdict (python artifact shape)" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/amicable"
    printf 'placeholder\n' > "${ARTIFACT_DIR}/amicable/cosmic-ray-session.sqlite"

    result="$(attribute)"
    [ "${result}" = "loop-began-no-verdict" ]
}

# Pins that the probe is tool-agnostic -- any entry other than marker/ and
# status/ means the loop began -- rather than a longer hardcoded list of
# known filenames. A probe that merely added mutants-report.txt and
# cosmic-ray-session.sqlite to a fixed-name set would satisfy the two cases
# above and still fail this one, which is the whole point of it.
@test "marker + an arbitrarily-named entry, no status -> loop-began-no-verdict (tool-agnostic probe)" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/some-future-tool"
    printf '{}\n' > "${ARTIFACT_DIR}/some-future-tool/output.json"

    result="$(attribute)"
    [ "${result}" = "loop-began-no-verdict" ]
}

@test "marker only -> died-before-loop" {
    mkdir -p "${ARTIFACT_DIR}/marker"

    result="$(attribute)"
    [ "${result}" = "died-before-loop" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"failed before the loop"* ]]
}

@test "download failure, empty artifact dir -> no-attestation" {
    mkdir -p "${ARTIFACT_DIR}"
    export DL_OUTCOME="failure"

    result="$(attribute)"
    [ "${result}" = "no-attestation" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"own reporting never ran"* ]]
}

@test "download success, populated artifact but no marker -> no-attestation (same token as failed download)" {
    mkdir -p "${ARTIFACT_DIR}/status" "${ARTIFACT_DIR}/pi-rs/mutants.out"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"
    export DL_OUTCOME="success"

    result="$(attribute)"
    [ "${result}" = "no-attestation" ]

    body="$(build_body "${result}")"
    [[ "${body}" == "Cause: ${result}"$'\n'* ]]
    [[ "${body}" == *"Run: ${RUN_URL}" ]]
    [[ "${body}" == *"own reporting never ran"* ]]
}

@test "marker + status + mutants.out together -> verdicts-present (status takes precedence)" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status" "${ARTIFACT_DIR}/pi-rs/mutants.out"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"

    result="$(attribute)"
    [ "${result}" = "verdicts-present" ]
}

@test "marker + empty status directory, no mutants.out -> falls through to died-before-loop" {
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"

    result="$(attribute)"
    [ "${result}" = "died-before-loop" ]
}

@test "attribute fails visibly when ARTIFACT_DIR is unset" {
    unset ARTIFACT_DIR
    run attribute
    [ "${status}" -ne 0 ]
}

@test "build_body reports an unknown token rather than silently producing nothing" {
    body="$(build_body "some-bogus-token")"
    [[ "${body}" == "Cause: some-bogus-token"$'\n'* ]]
    [[ "${body}" == *"Unknown cause token: some-bogus-token"* ]]
}

@test "RESULT=success with an open issue comments then closes it, every call carrying --repo" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST="98"

    run main
    [ "${status}" -eq 0 ]

    local _comment_line _close_line
    _comment_line=$(grep -n "gh issue comment 98 --repo" "${MOCK_CALLS_FILE}" | cut -d: -f1)
    _close_line=$(grep -n "gh issue close 98 --repo" "${MOCK_CALLS_FILE}" | cut -d: -f1)
    [ -n "${_comment_line}" ]
    [ -n "${_close_line}" ]
    [ "${_comment_line}" -lt "${_close_line}" ]

    assert_all_gh_calls_carry_repo

    # NOT asserting that closing is correct behaviour: math#100 is open and
    # describes exactly this path as a defect -- a single-crate green run
    # closed the full-sweep issue #98 while pi-rs and e-rs were still red,
    # which the 2026-09-01 cron confirms is still true. This case pins
    # --repo scoping and the absence of a second issue only; asserting the
    # close itself as correct would make #100 harder to fix, since a
    # passing test reads as intent.
}

@test "RESULT=success with no open issue exits 0 and writes nothing to the tracker" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST=""

    run main
    [ "${status}" -eq 0 ]

    run ! grep -q "gh issue comment" "${MOCK_CALLS_FILE}"
    run ! grep -q "gh issue close" "${MOCK_CALLS_FILE}"
    run ! grep -q "gh issue create" "${MOCK_CALLS_FILE}"
}

@test "RESULT=failure with an open issue comments only, never files a second issue" {
    export RESULT="failure"
    export MOCK_GH_ISSUE_LIST="98"
    mkdir -p "${ARTIFACT_DIR}/marker"

    run main
    [ "${status}" -eq 0 ]

    grep -q "gh issue comment 98 --repo" "${MOCK_CALLS_FILE}"
    run ! grep -q "gh issue create" "${MOCK_CALLS_FILE}"
    assert_all_gh_calls_carry_repo
}

@test "RESULT=failure with no open issue creates one carrying the attributed cause, title, and label" {
    export RESULT="failure"
    export MOCK_GH_ISSUE_LIST=""
    # Distinct from setup()'s default ISSUE_TITLE so a mutant that hardcodes
    # the workflow's original literal title ("mutation-testing: monthly run
    # failed") diverges from this fixture value instead of matching it by
    # coincidence.
    export ISSUE_TITLE="mutation-testing: fixture-distinct-title-9f3c"
    mkdir -p "${ARTIFACT_DIR}/marker" "${ARTIFACT_DIR}/status"
    printf 'red: pi-rs - exit code 2\n' > "${ARTIFACT_DIR}/status/pi-rs"

    run main
    [ "${status}" -eq 0 ]

    # The whole call, not a prefix: --title and --label mutation-failure are
    # both required, in this order, for the next month's lookup to find this
    # issue again. A prefix-only "gh issue create --repo" check cannot tell
    # a hardcoded title or a dropped --label from the real thing, and either
    # one causes an unbounded issue to be created every run forever.
    grep -qF -- "gh issue create --repo ${REPO} --title ${ISSUE_TITLE} --label mutation-failure --body" "${MOCK_CALLS_FILE}"
    grep -q "Cause: verdicts-present" "${MOCK_CALLS_FILE}"
    assert_all_gh_calls_carry_repo
}

@test "RESULT=cancelled files an issue carrying the right title and label -- pinned, though never observed in this repo" {
    # cancelled has never occurred here: all four measured failures carry a
    # job conclusion of "failure", and "cancelled" is attested only at the
    # step level. This pins current behaviour (anything other than
    # RESULT=success takes the file/comment path) without claiming the shape
    # has ever actually been observed.
    export RESULT="cancelled"
    export MOCK_GH_ISSUE_LIST=""
    export ISSUE_TITLE="mutation-testing: fixture-distinct-title-9f3c"
    mkdir -p "${ARTIFACT_DIR}/marker"

    run main
    [ "${status}" -eq 0 ]

    grep -qF -- "gh issue create --repo ${REPO} --title ${ISSUE_TITLE} --label mutation-failure --body" "${MOCK_CALLS_FILE}"
    assert_all_gh_calls_carry_repo
}

@test "main propagates a failing gh rather than reporting success" {
    export RESULT="failure"
    export MOCK_GH_EXIT=4
    mkdir -p "${ARTIFACT_DIR}/marker"

    run main
    [ "${status}" -ne 0 ]
}

@test "main fails visibly when RESULT is unset" {
    unset RESULT
    export MOCK_GH_ISSUE_LIST=""

    run main
    [ "${status}" -ne 0 ]
}

@test "main fails visibly when ISSUE_TITLE is unset" {
    unset ISSUE_TITLE
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST=""

    run main
    [ "${status}" -ne 0 ]
}

# The mock echoes MOCK_GH_ISSUE_LIST verbatim -- it never runs the real
# --jq '.[0].number // empty' filter, so this suite cannot exercise that
# fallback directly (see the comment above the gh issue list call in
# scripts/mutation-notify.sh). What IS exercised, and worth pinning because
# there is no second line of defense: bash's [[ -n ]] test treats the
# 4-character string "null" as non-empty, so a literal JSON null from a
# malformed --jq expression would be read as a real, existing issue number.
@test "MOCK_GH_ISSUE_LIST=null is read as an existing issue number, not as absent" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST="null"

    run main
    [ "${status}" -eq 0 ]

    grep -q "gh issue comment null --repo" "${MOCK_CALLS_FILE}"
    grep -q "gh issue close null --repo" "${MOCK_CALLS_FILE}"
}

@test "main fails visibly when REPO is unset" {
    unset REPO
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST=""

    run main
    [ "${status}" -ne 0 ]
}

@test "direct execution (not sourced) exits 0 on a green run with no open issue" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST=""

    run bash "${REPO_ROOT}/scripts/mutation-notify.sh"
    [ "${status}" -eq 0 ]
}
