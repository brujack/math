"""Shared helper for tests that inspect CI jobs running the bats suite."""

import re

_BATS_SUITE = re.compile(r"\bbats\b|\bbash-coverage\b|\btest-hooks\b")


def runs_bats_suite(step):
    # Matches installing bats (any job that installs it runs the suite), running
    # it directly, and the root make targets that reach it. A crate's own
    # `make test` runs cargo or pytest, not bats, so it is not matched.
    run = step.get("run") or ""
    return bool(_BATS_SUITE.search(run))
