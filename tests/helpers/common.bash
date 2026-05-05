#!/usr/bin/env bash
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

load_mocks() {
    export PATH="${REPO_ROOT}/tests/mocks:${PATH}"
}
