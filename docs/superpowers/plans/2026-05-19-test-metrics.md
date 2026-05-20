> **Status: DONE**

# Test Metrics CI — math Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument math CI (Rust and Python) to emit test-metrics artifacts capturing nextest retries and Python test timing.

**Architecture:** Shared scripts at math repo root. Rust: nextest CI profile (retries=2, JUnit) → `scripts/test_metrics.py` post-processor. Python: `scripts/time_tests.py` timing wrapper (no retry support in unittest). Each workflow uploads a sub-project-specific artifact (`test-metrics-{sub-project}`, 90 days). Implemented for `factorial` as the reference; other sub-projects follow identical pattern.

**Tech Stack:** `cargo nextest`, JUnit XML, Python 3 (stdlib only), `gh` CLI, GitHub Actions `upload-artifact@v5`

---

## Files

- **Create:** `.config/nextest.toml` (math repo root — applies to all Rust sub-projects)
- **Create:** `scripts/test_metrics.py` (Rust JUnit post-processor — same logic as etch-cli)
- **Create:** `scripts/time_tests.py` (Python unittest timing wrapper)
- **Create:** `tests/test_time_tests.py` (TDD tests for time_tests.py)
- **Modify:** `.github/workflows/factorial-rs.yml`
- **Modify:** `.github/workflows/factorial-py.yml`

---

## Task 1: nextest.toml + test_metrics.py

**Files:**

- Create: `.config/nextest.toml`
- Create: `scripts/test_metrics.py`

- [ ] **Step 1: Create `.config/nextest.toml` at math repo root**

```toml
[profile.ci]
retries = { backoff = "fixed", count = 2 }

[profile.ci.junit]
path = "junit.xml"
```

This config is found by nextest for ANY Rust sub-project in the math repo (nextest walks up to the git root).

- [ ] **Step 2: Verify nextest finds the profile from a sub-project**

```bash
cd factorial/factorial-rs && cargo nextest run --profile ci --list 2>&1 | head -5
```

Expected: lists tests without error.

- [ ] **Step 3: Create `scripts/test_metrics.py`**

This is the same JUnit XML post-processor used by etch-cli. Copy it exactly:

```python
#!/usr/bin/env python3
"""
Parse nextest JUnit XML → normalized test-metrics.json.

Usage:
    python3 scripts/test_metrics.py --repo REPO --run-id RUN_ID [--junit junit.xml] \
        [--artifact-name test-metrics-factorial-rs]
"""
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone


def parse_junit(path: str):
    tree = ET.parse(path)
    root = tree.getroot()
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]

    flaky, timings = [], {}
    total = passed = failed = 0

    for suite in suites:
        for tc in suite.findall("testcase"):
            name = f"{tc.get('classname', '')}.{tc.get('name', '')}"
            timings[name] = round(float(tc.get("time", 0)) * 1000, 1)

            reruns = tc.findall("flakyFailure") + tc.findall("rerunFailure")
            failures = tc.findall("failure") + tc.findall("error")
            total += 1

            if reruns and not failures:
                flaky.append({"name": name, "attempts": len(reruns) + 1, "final": "pass"})
                passed += 1
            elif failures:
                failed += 1
            else:
                passed += 1

    stats = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "flaky": len(flaky),
        "total_duration_ms": round(sum(timings.values()), 1),
    }
    return flaky, timings, stats


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


def compute_slow(timings: dict, historical: list, z_threshold: float = 2.0) -> list:
    by_name: dict[str, list] = {}
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
            continue
        z = (ms - mean) / std
        if z >= z_threshold:
            slow.append({"name": name, "duration_ms": ms, "z_score": round(z, 2)})

    return sorted(slow, key=lambda x: -x["z_score"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--junit", default="junit.xml")
    p.add_argument("--runner", default="nextest")
    p.add_argument("--artifact-name", default="test-metrics")
    args = p.parse_args()

    if not os.path.exists(args.junit):
        print(f"ERROR: {args.junit} not found", file=sys.stderr)
        sys.exit(1)

    flaky, timings, stats = parse_junit(args.junit)
    historical = fetch_historical(args.repo, args.artifact_name)
    slow = compute_slow(timings, historical)

    result = {
        "repo": args.repo,
        "run_id": args.run_id,
        "date": datetime.now(timezone.utc).isoformat(),
        "runner": args.runner,
        "flaky_tests": flaky,
        "slow_tests": slow,
        "all_timings": timings,
        "stats": stats,
    }
    with open("test-metrics.json", "w") as f:
        json.dump(result, f, indent=2)
    print(f"test-metrics.json: {stats['total']} tests, {stats['flaky']} flaky, {len(slow)} slow")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit**

```bash
git add .config/nextest.toml scripts/test_metrics.py
git commit -m "feat: add nextest CI profile and test-metrics post-processor

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: time_tests.py Python timing wrapper (TDD)

**Files:**

- Create: `scripts/time_tests.py`
- Create: `tests/test_time_tests.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_time_tests.py`:

```python
#!/usr/bin/env python3
import json
import math
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.time_tests import TimingResult, compute_slow


class TestTimingResult(unittest.TestCase):
    def _suite(self):
        class Fast(unittest.TestCase):
            def test_quick(self):
                pass

        class Slow(unittest.TestCase):
            def test_slow(self):
                time.sleep(0.01)

        class Fail(unittest.TestCase):
            def test_fail(self):
                self.fail("intentional")

        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        suite.addTest(loader.loadTestsFromTestCase(Fast))
        suite.addTest(loader.loadTestsFromTestCase(Slow))
        suite.addTest(loader.loadTestsFromTestCase(Fail))
        return suite

    def test_records_timing_per_test(self):
        result = TimingResult()
        self._suite().run(result)
        self.assertGreater(len(result.timings), 0)
        for name, ms in result.timings.items():
            self.assertIsInstance(ms, float)
            self.assertGreaterEqual(ms, 0.0)

    def test_slow_test_has_higher_timing(self):
        result = TimingResult()
        self._suite().run(result)
        timings = result.timings
        slow_key = next((k for k in timings if "slow" in k), None)
        fast_key = next((k for k in timings if "quick" in k), None)
        if slow_key and fast_key:
            self.assertGreater(timings[slow_key], timings[fast_key])

    def test_counts_failures(self):
        result = TimingResult()
        self._suite().run(result)
        self.assertEqual(len(result.failures), 1)

    def test_total_tests_run(self):
        result = TimingResult()
        self._suite().run(result)
        self.assertEqual(result.testsRun, 3)


class TestComputeSlow(unittest.TestCase):
    def test_no_history_returns_empty(self):
        self.assertEqual(compute_slow({"a": 500.0}, []), [])

    def test_detects_slow_test(self):
        hist = [{"all_timings": {"a": 100.0}} for _ in range(5)]
        result = compute_slow({"a": 600.0}, hist)
        self.assertEqual(len(result), 1)
        self.assertGreaterEqual(result[0]["z_score"], 2.0)

    def test_normal_test_not_flagged(self):
        hist = [{"all_timings": {"a": ms}} for ms in [100, 102, 98, 101, 100]]
        result = compute_slow({"a": 103.0}, hist)
        self.assertEqual(result, [])

    def test_insufficient_history_skipped(self):
        hist = [{"all_timings": {"a": 100.0}}, {"all_timings": {"a": 200.0}}]
        self.assertEqual(compute_slow({"a": 9999.0}, hist), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
python3 -m unittest tests.test_time_tests -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'scripts.time_tests'`

- [ ] **Step 3: Create `scripts/time_tests.py`**

```python
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
        self.timings: dict[str, float] = {}
        self._starts: dict[str, float] = {}

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


def compute_slow(timings: dict, historical: list, z_threshold: float = 2.0) -> list:
    by_name: dict[str, list] = {}
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
            continue
        z = (ms - mean) / std
        if z >= z_threshold:
            slow.append({"name": name, "duration_ms": ms, "z_score": round(z, 2)})

    return sorted(slow, key=lambda x: -x["z_score"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--module", required=True, help="unittest module name (e.g. test_factorial)")
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
```

- [ ] **Step 4: Run tests — confirm they all pass**

```bash
python3 -m unittest tests.test_time_tests -v
```

Expected: `OK (8 tests)`

- [ ] **Step 5: Commit**

```bash
git add scripts/time_tests.py tests/test_time_tests.py
git commit -m "feat: add Python unittest timing wrapper

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Modify factorial-rs.yml

**Files:**

- Modify: `.github/workflows/factorial-rs.yml`

The test job has `working-directory: factorial/factorial-rs` set on most steps. The JUnit output (`junit.xml`) will appear at `factorial/factorial-rs/junit.xml` (relative to the repo root).

- [ ] **Step 1: Locate the Run tests step**

```bash
grep -n "Run tests\|make test" .github/workflows/factorial-rs.yml
```

Note the line number and confirm the `working-directory: factorial/factorial-rs` context.

- [ ] **Step 2: Replace Run tests step and add post-processor + upload**

Find the `Run tests` step block (currently `run: make test` with `working-directory: factorial/factorial-rs`). Replace it with:

```yaml
- name: Run tests
  working-directory: factorial/factorial-rs
  run: make lint && cargo nextest run --profile ci
- name: Generate test metrics
  if: always()
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    python3 scripts/test_metrics.py \
      --repo math \
      --run-id "${{ github.run_id }}" \
      --junit factorial/factorial-rs/junit.xml \
      --artifact-name test-metrics-factorial-rs
- name: Upload test metrics
  if: always()
  uses: actions/upload-artifact@v5
  with:
    name: test-metrics-factorial-rs
    path: test-metrics.json
    retention-days: 90
```

The post-processor and upload steps run from the repo root (no `working-directory`). The `--junit` path is relative to the repo root.

- [ ] **Step 3: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/factorial-rs.yml'))" && echo "valid"
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/factorial-rs.yml
git commit -m "ci(factorial-rs): add test-metrics collection

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

> **Note:** Other Rust sub-projects (fib-rs, pi-rs, prime-rs, etc.) follow the identical pattern. For each: add same 3 steps, update `working-directory`, `--junit`, and `--artifact-name` / artifact `name` to match the sub-project.

---

## Task 4: Modify factorial-py.yml

**Files:**

- Modify: `.github/workflows/factorial-py.yml`

The test job has `working-directory: factorial` set on most steps. The Python module is `test_factorial`.

- [ ] **Step 1: Locate the Run tests step**

```bash
grep -n "Run tests\|make test" .github/workflows/factorial-py.yml
```

- [ ] **Step 2: Add post-processor + upload steps after Run tests**

Keep the existing `Run tests` step unchanged. Add after it:

```yaml
- name: Generate test metrics
  if: always()
  working-directory: factorial
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    python3 ${{ github.workspace }}/scripts/time_tests.py \
      --repo math \
      --run-id "${{ github.run_id }}" \
      --module test_factorial \
      --artifact-name test-metrics-factorial-py
- name: Upload test metrics
  if: always()
  uses: actions/upload-artifact@v5
  with:
    name: test-metrics-factorial-py
    path: factorial/test-metrics.json
    retention-days: 90
```

Note: `time_tests.py` runs from `factorial/` (`working-directory: factorial`) so it can import `test_factorial`. The `test-metrics.json` is written to the current working directory (`factorial/`), so the upload path is `factorial/test-metrics.json`.

- [ ] **Step 3: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/factorial-py.yml'))" && echo "valid"
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/factorial-py.yml
git commit -m "ci(factorial-py): add test-metrics timing collection

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

> **Note:** Other Python sub-projects follow the identical pattern. For each: update `working-directory`, `--module`, `--artifact-name`, artifact `name`, and `path` to match the sub-project.

---

## Task 5: Post-merge docs update

> **Do this directly on main after the PR merges — not inside the worktree.**

- [ ] **Step 1: Update plan index in math README**

In `docs/superpowers/README.md`, add or update the test-metrics row to Done.

- [ ] **Step 2: Add Done banner**

Add at the top of `docs/superpowers/plans/2026-05-19-test-metrics.md`:

```markdown
> **Status: DONE**
```

- [ ] **Step 3: Commit on main**

```bash
git add docs/superpowers/README.md docs/superpowers/plans/2026-05-19-test-metrics.md
git commit -m "docs: mark test-metrics plan done

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push
```
