#!/usr/bin/env bash
# Shared by tests/scripts/pre_push.bats and tests/scripts/pre_push_budget.bats: runs scripts/pre-push
# from a COPY whose `_pcg_fetch` is a fake, so no test reaches the network while the
# push-gates wiring (ADR-0099 2A) still executes. The fake serves the ai-config master
# commit JSON and a recorder `push_gates_run` for the gates paths, falls through to the
# real fetch only for the push-content gate library, which only a master/main push asks
# for (pre_push.bats' gh mock fails it; pre_push_budget.bats never pushes master), and fails
# every other path. Every fetched path is appended to FETCH_LOG.
#
# The copy is LINE-PRESERVING and lives at <dir>/covalias/scripts/pre-push: every line is
# identical to the hook's except the `# >>> _pcg_fetch` marker line, which becomes a trampoline
# into the fake, and the header line after it, which is renamed `_pcg_fetch_real() {`. The body
# lines up to the closing marker are kept verbatim, so they trace as the real hook's. The
# trampoline sits on a comment line of the real file, so the coverage runner drops its trace and
# claims no real line. The coverage
# runner (scripts/run-bash-coverage.sh) attributes traces under `covalias/` to the real
# hook at the same line numbers, so these runs count as coverage of scripts/pre-push.
# Callers run the copy as plain `bash <copy>`, not `bash -p`: -p ignores BASH_ENV, which is how
# the coverage tracer attaches. The shebang's -p is pinned separately in tests/scripts/pre_push.bats.
#
# math specifics. The hook finds its repo root through `git rev-parse` (mocked or real, never
# through its own path), so moving the copy changes no root. It finds the parallel runner beside
# itself (HOOK_DIR), so pg_hook_copy links scripts/parallel-make-test.sh into the copy's directory.
# pg_env puts a `make` wrapper first on PATH that appends `make` to ORDER_LOG and then runs the
# next `make` on PATH (the tests/mocks one or a test's own stub), which is how a test proves the
# gates ran before the first make.

readonly PG_FAKE_MASTER_SHA="0123456789abcdef0123456789abcdef01234567"

# pg_env <dir> -- creates <dir> and exports the log paths the fakes read.
pg_env() {
  PG_DIR="${1}"
  mkdir -p "${PG_DIR}" || return 1
  export GATES_LOG="${PG_DIR}/gates.log" ORDER_LOG="${PG_DIR}/order.log" FETCH_LOG="${PG_DIR}/fetch.log"
  export FAKE_MASTER_SHA="${PG_FAKE_MASTER_SHA}" FAKE_DRIVER="${PG_DIR}/fake_driver.sh"
  export PG_FAKE_FETCH="${PG_DIR}/fake_fetch.sh"
  mkdir -p "${PG_DIR}/bin" || return 1
  cat > "${PG_DIR}/bin/make" <<'WRAP'
#!/usr/bin/env bash
printf 'make\n' >> "${ORDER_LOG:?}"
here="${0%/*}"
newpath=""
IFS=: read -ra parts <<< "${PATH}"
for part in "${parts[@]}"; do
  [[ "${part}" == "${here}" ]] || newpath+="${newpath:+:}${part}"
done
PATH="${newpath}" exec make "$@"
WRAP
  chmod +x "${PG_DIR}/bin/make" || return 1
  export PATH="${PG_DIR}/bin:${PATH}"
}

# pg_hook_copy <hook> -- writes an executable line-preserving copy of <hook> and prints
# its path. The original `_pcg_fetch` body stays in the copy, verbatim, under the name
# `_pcg_fetch_real` (only its header line is rewritten), so its lines trace as the real hook's.
# Fails loudly when the markers or header are not where expected, or the line counts differ.
pg_hook_copy() {
  local hook="${1}" copy="${PG_DIR}/covalias/scripts/pre-push" start end
  # The header may carry only a trailing comment after `{`: the copy renames the whole line.
  local header_re='^_pcg_fetch\(\) \{( #.*)?$'
  # shellcheck disable=SC2016 # the trampoline text is literal; it expands when the copy runs
  local tramp='_pcg_fetch() { . "${PG_FAKE_FETCH:?}"; _pg_fake_fetch "$@"; }'
  start="$(grep -n "^[#] >>> _pcg_fetch\$" "${hook}" | cut -d: -f1)"
  end="$(grep -n "^[#] <<< _pcg_fetch\$" "${hook}" | cut -d: -f1)"
  if [[ ! "${start}" =~ ^[0-9]+$ || ! "${end}" =~ ^[0-9]+$ ]] || (( end <= start + 1 )) \
    || [[ ! "$(sed -n "$((start + 1))p" "${hook}")" =~ ${header_re} ]]; then
    printf 'pg_hook_copy: _pcg_fetch markers not found in %s\n' "${hook}" >&2
    return 1
  fi
  mkdir -p "${PG_DIR}/covalias/scripts" || return 1
  ln -sf "$(cd "$(dirname "${hook}")" && pwd)/parallel-make-test.sh" "${PG_DIR}/covalias/scripts/parallel-make-test.sh" || return 1
  cat > "${FAKE_DRIVER}" <<'DRV'
push_gates_run() {
  printf 'url=%s\nsha=%s\nrefs=%s\n' "${1}" "${3}" "${2}" >> "${GATES_LOG}"
  printf 'gates\n' >> "${ORDER_LOG}"
  return "${GATES_RC:-0}"
}
DRV
  {
    cat <<'FAKE'
_pg_fake_fetch() {
  printf '%s\n' "${1}" >> "${FETCH_LOG}"
  case "${1}" in
    repos/brujack/ai-config/commits/master)
      [[ -z "${FAKE_MASTER_FAIL:-}" ]] || return 1
      printf '{"sha":"%s"}\n' "${FAKE_MASTER_SHA}"
      ;;
    "repos/brujack/ai-config/contents/.claude/hooks/push-gates.sh?ref=${FAKE_MASTER_SHA}")
      printf '%s\n' "$(< "${FAKE_DRIVER}")"
      ;;
    repos/brujack/ai-config/contents/.claude/hooks/push-content-gate.sh?ref=master) _pcg_fetch_real "${1}" ;;
    *) return 1 ;;
  esac
}
FAKE
  } > "${PG_FAKE_FETCH}" || return 1
  awk -v s="${start}" -v e="${end}" -v t="${tramp}" 'NR == s { print t; next } NR == s + 1 { print "_pcg_fetch_real() {"; next } { print }' "${hook}" > "${copy}" || return 1
  # Same line count, the trampoline exactly on the opening marker line, the header line renamed,
  # every body line up to the closing marker byte-identical, and the closing marker unchanged.
  if [[ "$(wc -l < "${copy}")" -ne "$(wc -l < "${hook}")" ]] \
    || [[ "$(sed -n "${start}p" "${copy}")" != "${tramp}" ]] \
    || [[ "$(sed -n "$((start + 1))p" "${copy}")" != "_pcg_fetch_real() {" ]] \
    || ! cmp -s <(sed -n "$((start + 2)),$((end - 1))p" "${copy}") <(sed -n "$((start + 2)),$((end - 1))p" "${hook}") \
    || [[ "$(sed -n "${end}p" "${copy}")" != "$(sed -n "${end}p" "${hook}")" ]]; then
    printf 'pg_hook_copy: copy of %s is not line-preserving\n' "${hook}" >&2
    return 1
  fi
  chmod +x "${copy}" || return 1
  printf '%s' "${copy}"
}
