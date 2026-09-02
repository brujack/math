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
    # Distinct from the label the script previously hardcoded, for the same
    # reason ISSUE_TITLE below is distinct from the workflow's real title:
    # a fixture matching the literal by coincidence cannot tell "reads the
    # env var" from "hardcodes the old value".
    export ISSUE_LABEL="mutation-failure-fixture-distinct-4b21"
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

# The case above puts the root-level entry at a directory. A probe with
# -type d added would still pass it while silently dropping any root-level
# FILE output -- not reachable today (both workflows' **/ upload patterns
# yield a sub-project directory), but this pins the probe as type-agnostic
# too rather than only name-agnostic.
@test "marker + a plain file at the artifact root, no status -> loop-began-no-verdict (root-level file, not a directory)" {
    mkdir -p "${ARTIFACT_DIR}/marker"
    printf 'placeholder\n' > "${ARTIFACT_DIR}/some-future-tool-output.txt"

    result="$(attribute)"
    [ "${result}" = "loop-began-no-verdict" ]
}

@test "marker only -> died-before-loop" {
    mkdir -p "${ARTIFACT_DIR}/marker"
    # The real fixture: mutation-testing.yml's "Mark job start" step writes
    # exactly this file, so an empty marker/ is a shape production cannot
    # produce. job-began sits at depth 2 under ARTIFACT_DIR, which is what
    # pins the probe's -maxdepth 1 -- a recursive probe matches it and
    # misattributes every real died-before-loop run as loop-began-no-verdict.
    printf '2026-09-01T00:00:00Z\n' > "${ARTIFACT_DIR}/marker/job-began"

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
    printf '2026-09-01T00:00:00Z\n' > "${ARTIFACT_DIR}/marker/job-began"

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

    # The whole call, not a prefix: --title and --label are both required, in
    # this order, for the next month's lookup to find this issue again. The
    # label is asserted through ${ISSUE_LABEL}, whose fixture value is
    # deliberately distinct from the workflow's real one -- matching it by
    # coincidence would make this assertion unable to tell a hardcoded label
    # from one read out of the environment. A prefix-only "gh issue create --repo" check cannot tell
    # a hardcoded title or a dropped --label from the real thing, and either
    # one causes an unbounded issue to be created every run forever.
    grep -qF -- "gh issue create --repo ${REPO} --title ${ISSUE_TITLE} --label ${ISSUE_LABEL} --body" "${MOCK_CALLS_FILE}"
    grep -q "Cause: verdicts-present" "${MOCK_CALLS_FILE}"
    # The lookup this whole change exists for: a hardcoded label here would
    # make a green Rust run's issue-list query match (and therefore close)
    # the Python tracking issue, since in:title matching is AND-over-tokens.
    grep -qF -- "gh issue list --repo ${REPO} --state open --label ${ISSUE_LABEL}" "${MOCK_CALLS_FILE}"
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

    grep -qF -- "gh issue create --repo ${REPO} --title ${ISSUE_TITLE} --label ${ISSUE_LABEL} --body" "${MOCK_CALLS_FILE}"
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

@test "main fails visibly when ISSUE_LABEL is unset" {
    unset ISSUE_LABEL
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

# Only three of the five `|| return 1` guards in main() are killable. The
# other two -- `gh issue comment` on the red-existing-issue path and
# `gh issue create` -- are each the last statement of their branch,
# so stripping `|| return 1` returns 4 (the mock's exit code) instead of 1,
# both non-zero, and no `status -ne 0` oracle can discriminate. Do not add
# cases for those two call sites.

@test "a failing issue lookup propagates and files nothing" {
    export RESULT="failure"
    export MOCK_GH_EXIT_ISSUE_LIST=4
    run main
    [ "${status}" -ne 0 ]
    run ! grep -q "gh issue create" "${MOCK_CALLS_FILE}"
    run ! grep -q "gh issue comment" "${MOCK_CALLS_FILE}"
}

@test "a failing green-path comment propagates and does not close the issue" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST="98"
    export MOCK_GH_EXIT_ISSUE_COMMENT=4
    run main
    [ "${status}" -ne 0 ]
    run ! grep -q "gh issue close" "${MOCK_CALLS_FILE}"
}

@test "a failing issue close propagates rather than reporting success" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST="98"
    export MOCK_GH_EXIT_ISSUE_CLOSE=4
    run main
    [ "${status}" -ne 0 ]
    grep -q "gh issue comment 98 --repo" "${MOCK_CALLS_FILE}"
}

# Every case above fixtures marker/ itself, so the suite is exhaustive over
# "given a marker exists, does attribution route correctly" and silent on
# "does a marker ever exist in production" -- attribute()'s entire verdict
# space keys off three strings agreeing: the "Mark job start" step's write
# path, that same workflow's Upload step's `path:` list, and the directory
# attribute() probes. Mutation-confirmed: renaming a workflow's marker
# directory in both the write step and the upload path left every case
# above green, because every one of them creates marker/ in its own
# fixture rather than reading what the workflow produces.
#
# The probed directory name is derived from scripts/mutation-notify.sh
# itself, not typed as a literal here -- typing "marker" on both the
# derivation side and the workflow side would recreate the exact displaced
# reference this test exists to close.
@test "each mutation workflow's Mark-job-start write and Upload path agree with what attribute() probes" {
    local _dir_name
    _dir_name=$(grep -oE '! -d "\$\{_dir\}/[A-Za-z0-9_-]+"' "${REPO_ROOT}/scripts/mutation-notify.sh")
    _dir_name="${_dir_name%\"}"
    _dir_name="${_dir_name##*/}"
    [ -n "${_dir_name}" ]

    # load_mocks() (setup()) put tests/mocks/ ahead of the real git on PATH,
    # and that mock has no ls-files branch -- it would print nothing and
    # exit 0, so the enumeration this test depends on has to bypass it
    # rather than rely on `command git` (which still finds the mock first).
    local _real_path
    _real_path=$(printf '%s' "${PATH}" | tr ':' '\n' | grep -v 'tests/mocks' | tr '\n' ':' | sed 's/:$//')

    local _workflows
    _workflows=$(cd "${REPO_ROOT}" && PATH="${_real_path}" git ls-files '.github/workflows/mutation-testing*.yml')
    [ -n "${_workflows}" ]

    local _workflow _wf_path _upload_block _conformant
    _conformant=0
    while IFS= read -r _workflow; do
        _wf_path="${REPO_ROOT}/${_workflow}"

        # The write step: mkdir the directory, then redirect job-began into it,
        # both under GITHUB_WORKSPACE -- exactly the shape production writes.
        grep -qE "mkdir -p \"\\\$\{GITHUB_WORKSPACE\}/${_dir_name}\" && date -u > \"\\\$\{GITHUB_WORKSPACE\}/${_dir_name}/job-began\"" \
            "${_wf_path}"

        # The Upload step's own path: list -- scoped to that step's block, not
        # the whole file, so an unrelated later occurrence of the same name
        # could not pass this by accident.
        _upload_block=$(awk '
            /^ *- name: Upload/ { capture=1 }
            capture && /^ *- (name|uses):/ && !/^ *- name: Upload/ { capture=0 }
            capture { print }
        ' "${_wf_path}")
        [ -n "${_upload_block}" ]
        printf '%s\n' "${_upload_block}" | grep -qE "^ +${_dir_name}/ *\$"

        _conformant=$((_conformant + 1))
    done <<< "${_workflows}"

    # A third mutation workflow added later without this write/upload pair
    # must fail this count rather than pass unnoticed -- membership alone
    # (does at least one conform) would not catch that.
    [ "${_conformant}" -eq 2 ]
}

# main() hard-fails on an unset ISSUE_LABEL, and setup() exports it -- so every
# test above runs with the precondition already supplied and none of them can
# detect a workflow that never sets it. Measured: deleting the env key from
# mutation-testing.yml leaves the whole suite green while the real notify job
# aborts with "parameter null or not set", filing nothing. This asserts the
# shipping artifact instead, and asserts a COUNT rather than membership so a
# partial parse cannot pass.
@test "every notify step that runs the script declares ISSUE_LABEL, distinctly" {
    local _real_path
    _real_path=$(printf '%s' "${PATH}" | tr ':' '\n' | grep -v 'tests/mocks' | tr '\n' ':' | sed 's/:$//')

    local _workflows
    _workflows=$(cd "${REPO_ROOT}" && PATH="${_real_path}" git ls-files '.github/workflows/mutation-testing*.yml')
    [ -n "${_workflows}" ]
    [ "$(printf '%s\n' "${_workflows}" | wc -l | tr -d ' ')" -eq 2 ]

    local _labels
    _labels=$(cd "${REPO_ROOT}" && PATH="${_real_path}" python3 -c '
import sys, yaml
out = []
for f in sys.argv[1:]:
    d = yaml.safe_load(open(f))
    for job in d.get("jobs", {}).values():
        for step in job.get("steps") or []:
            if "mutation-notify.sh" in (step.get("run") or ""):
                out.append(step.get("env", {}).get("ISSUE_LABEL", "<MISSING>"))
print("\n".join(out))
' ${_workflows})

    # One label per workflow, none missing, and the two differ -- a shared
    # label is what let a green Rust run close the Python tracking issue.
    [ "$(printf '%s\n' "${_labels}" | wc -l | tr -d ' ')" -eq 2 ]
    run ! grep -q '<MISSING>' <<< "${_labels}"
    [ "$(printf '%s\n' "${_labels}" | sort -u | wc -l | tr -d ' ')" -eq 2 ]
}
