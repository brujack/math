#!/usr/bin/env python3
"""
Run Python unittest with per-test timing → normalized test-metrics.json.

Usage:
    python3 scripts/time_tests.py --repo REPO --run-id RUN_ID \
        --module MODULE [--artifact-name test-metrics-factorial-py]
"""
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from datetime import datetime, timezone


class TimingResult(unittest.TestResult):
    """TestResult that records per-test wall-clock duration in self.timings."""

    def __init__(self):
        super().__init__()
        self.timings: dict = {}
        self._starts: dict = {}

    def startTest(self, test):
        self._starts[str(test)] = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        elapsed = time.perf_counter() - self._starts.get(str(test), time.perf_counter())
        self.timings[str(test)] = round(elapsed * 1000, 1)
        super().stopTest(test)


def fetch_historical(repo: str, artifact_name: str) -> list:
    r = subprocess.run(
        ["gh", "api", f"repos/brujack/{repo}/actions/artifacts",
         "--field", f"name={artifact_name}", "--field", "per_page=10",
         "--jq", "[.artifacts[].id]"],
        capture_output=True, text=True, check=False,
    )
    if r.returncode != 0 or not r.stdout.strip():
        return []
    ids = json.loads(r.stdout.strip() or "[]")
    runs = []
    for aid in ids:
        with tempfile.TemporaryDirectory() as d:
            zp = os.path.join(d, "a.zip")
            dl = subprocess.run(
                ["gh", "api", f"repos/brujack/{repo}/actions/artifacts/{aid}/zip",
                 "--output", zp],
                capture_output=True, check=False,
            )
            if dl.returncode != 0:
                continue
            try:
                with zipfile.ZipFile(zp) as z, z.open("test-metrics.json") as f:
                    runs.append(json.load(f))
            except Exception:
                continue
    return runs


def compute_slow(timings: dict, historical: list, z_threshold: float = 2.5) -> list:
    by_name: dict = {}
    for run in historical:
        for name, ms in run.get("all_timings", {}).items():
            by_name.setdefault(name, []).append(ms)

    slow = []
    for name, ms in timings.items():
        hist = by_name.get(name, [])
        if len(hist) < 3:
            continue
        mean = sum(hist) / len(hist)
        std = math.sqrt(sum((x - mean) ** 2 for x in hist) / len(hist))
        if std < 1.0:
            # fall back to ratio-based detection for near-constant tests
            if mean > 0 and ms > mean * 3:
                slow.append({"name": name, "duration_ms": ms, "z_score": round(ms / mean, 2)})
            continue
        z = (ms - mean) / std
        if z >= z_threshold:
            slow.append({"name": name, "duration_ms": ms, "z_score": round(z, 2)})

    return sorted(slow, key=lambda x: -x["z_score"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--module", required=True)
    p.add_argument("--artifact-name", default="test-metrics")
    args = p.parse_args()

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(args.module)

    result = TimingResult()
    suite.run(result)

    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = total - failed

    historical = fetch_historical(args.repo, args.artifact_name)
    slow = compute_slow(result.timings, historical)

    output = {
        "repo": args.repo,
        "run_id": args.run_id,
        "date": datetime.now(timezone.utc).isoformat(),
        "runner": "unittest",
        "flaky_tests": [],
        "slow_tests": slow,
        "all_timings": result.timings,
        "stats": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "flaky": 0,
            "total_duration_ms": round(sum(result.timings.values()), 1),
        },
    }
    with open("test-metrics.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"test-metrics.json: {total} tests, {len(slow)} slow")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
