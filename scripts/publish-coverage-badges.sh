#!/usr/bin/env bash
# Publish the coverage badges of a merged PR to the `coverage-data` branch.
#
# Usage: publish-coverage-badges.sh <head_sha>   (GH_TOKEN and GITHUB_REPOSITORY from env)
#
# Each crate/py workflow's coverage job uploads a `coverage-badge-<project>-<lang>`
# artifact (shields endpoint JSON at `<project>/<lang>.json`) from the pull_request run.
# auto-merge.yml calls this after the PR merges, so the README badges show merged code
# only, from the PR's own coverage results. Artifact content is produced by the PR, so
# every file is path- and shape-checked before anything is copied into the branch.
#
# Exit 0: published, or the PR ran no coverage (docs-only). Exit 1: any failure, loudly.

readonly BADGE_BRANCH="coverage-data"
readonly BADGE_PREFIX="coverage-badge-"
readonly BADGE_COLORS='"brightgreen","green","yellow","orange","red"'
readonly PUBLISH_ATTEMPTS=3

badge_error() {
    printf '::error::%s\n' "$*"
}

# The only paths allowed on the branch: <project>/rust.json or <project>/python.json.
valid_badge_path() {
    [[ "${1}" =~ ^[a-z0-9][a-z0-9-]*/(rust|python)\.json$ ]]
}

# Exactly the document the coverage jobs write; any extra key or other value is refused.
valid_badge_json() {
    local file="${1}"
    [[ -f "${file}" && ! -L "${file}" ]] || return 1
    jq -e --argjson colors "[${BADGE_COLORS}]" '
        type == "object"
        and (keys | sort) == ["color", "label", "message", "schemaVersion"]
        and .schemaVersion == 1
        and .label == "coverage"
        and (.message | type == "string" and test("^[0-9]{1,3}%$"))
        and (.color | type == "string" and IN($colors[]))
    ' "${file}" > /dev/null 2>&1
}

# Prints the id of the newest successful pull_request run of each workflow on a SHA.
latest_runs() {
    local repo="${1}" sha="${2}" listing
    listing=$(gh api --paginate \
        "repos/${repo}/actions/runs?head_sha=${sha}&event=pull_request&status=success&per_page=100" \
        --jq '.workflow_runs[]
              | select(.event == "pull_request" and .conclusion == "success")
              | [.workflow_id, .id] | @tsv') || return 1
    [[ -n "${listing}" ]] || return 0
    printf '%s\n' "${listing}" | sort -t $'\t' -k1,1n -k2,2nr | awk -F'\t' '!seen[$1]++ { print $2 }'
}

# Downloads one run's badge artifacts into $3. Returns 2 when the run has none.
download_run_badges() {
    local repo="${1}" run="${2}" dest="${3}" names
    names=$(gh api --paginate "repos/${repo}/actions/runs/${run}/artifacts?per_page=100" \
        --jq ".artifacts[] | select(.name | startswith(\"${BADGE_PREFIX}\")) | .name") || return 1
    [[ -n "${names}" ]] || return 2
    gh run download "${run}" --repo "${repo}" --pattern "${BADGE_PREFIX}*" --dir "${dest}" \
        > /dev/null || return 1
}

# Validates every file under $1 and copies the accepted ones, re-serialised, to $2.
# Any unexpected file fails the whole batch: nothing partial is ever published.
stage_badge_files() {
    local dir="${1}" stage="${2}" file rel top project lang
    while IFS= read -r -d '' file; do
        rel="${file#"${dir}"/}"
        top="${rel%%/*}"
        if [[ "${top}" == "${BADGE_PREFIX}"* ]]; then
            rel="${rel#*/}"
        else
            top=""
        fi
        if ! valid_badge_path "${rel}"; then
            badge_error "unexpected file in coverage artifact: ${file#"${dir}"/}"
            return 1
        fi
        project="${rel%%/*}"
        lang="${rel##*/}"
        lang="${lang%.json}"
        if [[ -n "${top}" && "${top}" != "${BADGE_PREFIX}${project}-${lang}" ]]; then
            badge_error "artifact ${top} carries ${rel}, which it does not own"
            return 1
        fi
        if ! valid_badge_json "${file}"; then
            badge_error "malformed coverage badge: ${rel}"
            return 1
        fi
        mkdir -p "${stage}/${project}" || return 1
        jq -c . "${file}" > "${stage}/${rel}" || return 1
    done < <(find "${dir}" -mindepth 1 -not -type d -print0)
}

# One commit, pushed with up to PUBLISH_ATTEMPTS tries. A lost race is not rebased: the
# worktree is reset to the remote tip and the staged files are applied again, because two
# badge commits touching one path would otherwise conflict.
publish_staged() {
    local stage="${1}" sha="${2}" wt="${3}" attempt
    local ident=(-c "user.name=github-actions[bot]" -c "user.email=github-actions[bot]@users.noreply.github.com")

    for ((attempt = 1; attempt <= PUBLISH_ATTEMPTS; attempt++)); do
        if ((attempt > 1)); then
            sleep "${PUBLISH_RETRY_SLEEP:-$((RANDOM % 5 + 1))}"
            # Without the reset the worktree still holds the rejected commit, and pushing
            # it again would only repeat the failure (or publish stale content): stop.
            if ! { git -C "${wt}" fetch origin "${BADGE_BRANCH}" 2> /dev/null \
                && git -C "${wt}" reset --hard -q FETCH_HEAD; }; then
                badge_error "could not reset ${BADGE_BRANCH} to the remote tip after a lost push race"
                return 1
            fi
        fi
        cp -R "${stage}/." "${wt}/" || continue
        git -C "${wt}" add -- . || continue
        if git -C "${wt}" diff --cached --quiet; then
            printf 'coverage-data already has these badges for %s\n' "${sha}"
            return 0
        fi
        git -C "${wt}" "${ident[@]}" commit -q -m "coverage: publish badges for ${sha}" || continue
        if git -C "${wt}" push origin "${BADGE_BRANCH}"; then
            return 0
        fi
    done
    badge_error "could not push ${BADGE_BRANCH} after ${PUBLISH_ATTEMPTS} attempts"
    return 1
}

# Checks out coverage-data at $1; creates it as an orphan the first time (no remote branch).
add_badge_worktree() {
    local wt="${1}"
    if git fetch origin "${BADGE_BRANCH}" 2> /dev/null; then
        git worktree add "${wt}" "${BADGE_BRANCH}" > /dev/null
    else
        git worktree add -b "${BADGE_BRANCH}" --orphan "${wt}" > /dev/null
    fi
}

run_publish() {
    local sha="${1}" tmp="${2}" repo run rc found=0 runs
    repo="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner --jq '.nameWithOwner')}"
    mkdir -p "${tmp}/dl" "${tmp}/stage" || return 1

    if ! runs=$(latest_runs "${repo}" "${sha}"); then
        badge_error "could not list workflow runs for ${sha}"
        return 1
    fi
    if [[ -z "${runs}" ]]; then
        printf 'no coverage runs for %s (docs-only PR?); no badges to publish\n' "${sha}"
        return 0
    fi

    while IFS= read -r run; do
        download_run_badges "${repo}" "${run}" "${tmp}/dl/${run}"
        rc=$?
        if ((rc == 2)); then
            continue
        elif ((rc != 0)); then
            badge_error "could not download coverage artifacts of run ${run}"
            return 1
        fi
        found=1
        stage_badge_files "${tmp}/dl/${run}" "${tmp}/stage" || return 1
    done <<< "${runs}"

    if ((!found)); then
        printf 'no coverage-badge artifacts on the runs for %s; nothing to publish\n' "${sha}"
        return 0
    fi

    if ! add_badge_worktree "${tmp}/cov-data"; then
        badge_error "could not create a ${BADGE_BRANCH} worktree"
        return 1
    fi
    publish_staged "${tmp}/stage" "${sha}" "${tmp}/cov-data"
}

# EXIT trap body: unregister the worktree (when one was made) before its directory goes.
badge_cleanup() {
    local tmp="${1}"
    [[ -n "${tmp}" ]] || return 0
    if [[ -d "${tmp}/cov-data" ]]; then
        git worktree remove --force "${tmp}/cov-data" > /dev/null 2>&1
    fi
    rm -rf -- "${tmp}"
}

publish_coverage_badges() {
    local sha="${1:-}"
    if [[ -z "${sha}" ]]; then
        printf 'Usage: publish-coverage-badges.sh <head_sha>\n' >&2
        return 1
    fi
    (
        tmp=$(mktemp -d) || exit 1
        trap 'badge_cleanup "${tmp}"' EXIT
        run_publish "${sha}" "${tmp}"
        exit $?
    )
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    publish_coverage_badges "$@"
    exit $?
fi
