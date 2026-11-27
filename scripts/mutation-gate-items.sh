#!/usr/bin/env bash
# Lists the mutation-gate items of a PR and exits 1 when there is any (spec R20-R26).
#
# Usage: mutation-gate-items.sh <base-sha> <head-sha>
#
# Thin wrapper: scripts/mutation_gate_items.py does the work. It runs from the base branch's
# checkout and never builds, imports or runs a PR file (N4). Exit 0 no items,
# 1 red, 2 usage.

main() {
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 1
    if [[ "$#" -lt 2 ]]; then
        printf 'usage: %s <base-sha> <head-sha>\n' "${0##*/}" >&2
        return 2
    fi
    exec python3 "${here}/mutation_gate_items.py" "$@"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
    exit "$?"
fi
