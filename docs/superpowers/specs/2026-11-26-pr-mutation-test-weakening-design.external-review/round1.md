Tools: Read, Bash, SubagentHandback

Keep three things as they are. First, judging the base arm on failure sites rather than messages. Second, running the items job on `pull_request_target` from master's code only. Third, keying each clearance on content and bound to the PR number. Each closes a real hole that earlier rounds measured, and none of them has a defect I could find. The Rust half is the simplest correct design. It is the sweep's rule, applied to a crate the PR touched.

### F1.1 The continuing runner continues only past `AssertionError`, but in the real refactor PR, errors mask far more often than failures do

**Defect.** R11 rewrites assertion statements to record and continue on `AssertionError` only. When a base test raises any other exception on the head module, the test still stops at that line, so every assertion after it is masked for every mutant. This is the masking the runner was built to remove. An `AttributeError` raised inside `self.assertEqual(sq.f(...), ...)` is one example.

**Failure.** Take a PR that renames or removes an attribute, then weakens an assertion that comes later in a base test that touches the renamed name. It reports `weakened: 0`. That PR is the "ordinary refactor PR" that round 4 F1 named as the main recall hole.

**Measurement.** I ran each commit's parent test file against the commit's own module, using plain `unittest`. Setup: Python 3.15.2, hypothesis 6.168.5, `PYTHONHASHSEED=0`, Linux. I classified each error by the statement it was raised in, using `ast`.

| Commit             | Dirs      | Failures | Errors | Errors raised inside a `self.assert*` call or `with self.assert*` block |
| ------------------ | --------- | -------- | ------ | ----------------------------------------------------------------------- |
| 68a2f8a (math#171) | 8 dirs    | 14       | 99     | at least 77                                                             |
| 57271ec            | descartes | 13       | 3      | none counted (all 3 in assignments)                                     |
| ced3726            | pi, e     | 0        | 4      | none counted (all `TypeError` in assignments)                           |

Examples from 68a2f8a sq: `AttributeError: 'Namespace' object has no attribute 'size'` at line 402, and `module 'sq' has no attribute 'ask_yes'`. Many of these errors come from tests of removed functions, where continuing would add nothing. I did not measure how many kills are lost. The Facts entry "7 (68a2f8a) 13-65%" groups errors with failures, which hides this split.

**Smallest fix.**

- R11: the rewritten assertion statements and `with self.assert*` blocks catch `Exception`, not only `AssertionError`. The site key becomes (line, subTest parameters, ordinal, exception type), and the runner continues. Errors raised outside assertion statements still end the test, as now.
- R18 and R33: add a case. A base test whose first assertion raises `AttributeError` on head must still report a mutant that only a later assertion kills.
- V6: also print, per commit, the base-arm kills that come from sites after an error.

### F1.2 The bootstrap does not pin the expected source of the new required check, and agents hold a token that can write statuses (unmeasured)

**Defect.** The bootstrap step reads "the operator adds `mutation-gate-items` to branch protection". It does not choose the expected source.

GitHub's protected-branches page (fetched 2026-11-26) says:

> "Any person or integration with write permissions to a repository can set the state of any status check … you can select an app … as the expected source … If the status is set by any other person or integration, merging won't be allowed."

Agent sessions here hold the operator's `gh` token.

**Failure.** On "any source", a `gh api repos/<owner>/math/statuses/<head-sha> -f state=success -f context=mutation-gate-items` call is a candidate pass. I have not measured whether it beats a red check run of the same name. The same page warns that duplicate job names across workflows give "ambiguous status check results". A PR can also add a `pull_request` workflow whose job is named `mutation-gate-items` or `mutation-pr`, and R25 does not list a new workflow file as an item.

**How to check.** Use a throwaway draft PR with the items job red, then post a success status with the same context. Read `gh pr view --json mergeStateStatus` and the merge box.

**Smallest fix.**

- Bootstrap and V4: add the required check with expected source GitHub Actions. Do the same for the existing `mutation-pr` and `secret-scan`.
- V4: add the status-post case.
- R25: any changed `.github/workflows/*` file that declares a job id or `name:` equal to a required context is a `gate` item.

### Smaller items

- **F1.3** `K` is not defined anywhere. It appears in both Design step 1 and R6, which reads `n = min(40, max(10, ceil(K * s / 600)))`. State that it is the dir's whole-module mutant count after the prune.
- **F1.4** Stale text: Design step 10 lists two canary pairs, while R18 lists four. Bring step 10 into line with R18.
- **F1.5** Known limits says an assertion "inside a helper function" still stops its test. R11, however, rewrites every `self.assert*` expression statement in the file, so helper methods on the test class are rewritten too. Say which helpers stay a limit, for example module-level functions or ones that call `self.fail` or `raise AssertionError`.
- **F1.6** `scripts/ci-gate.sh` waits only for check runs that already exist on the head SHA. On a PR where nothing in `mutation-pr` runs, it can pass before the `pull_request_target` run registers. `gh pr merge` is then refused, the `auto-merge` job goes red, and nothing re-triggers it. Unmeasured; I also have not checked which SHA the `pull_request_target` check run attaches to. Either make `ci-gate.sh` wait for the named required contexts, or say that V4 covers this case.
- **F1.7** R29 runs `mutation-gate-items.sh` in pre-push. Under R21 that means four `cargo mutants --list` runs per touched crate with a fresh empty `CARGO_HOME`, so each push may re-resolve and download dependencies. Unmeasured: cargo would not run under the redirected HOME. R29 is advisory, so it is the first thing to delete if it turns out slow.
- **F1.8** The trust root `.github/mutation-gate-allowed-signers` lives on master, and `enforce_admins: false`. A session holding the operator's push credentials is stopped from pushing it directly only by the local branch guard. Record this as instruction-only enforcement, or turn on `enforce_admins`.
- **F1.9** The Facts entry "same 17 of the last 100 PRs" was measured before R1 widened the trigger paths. I counted 18 of the last 100 PRs that touch R1's paths (an upper bound by path). Of the 7 that touched `Cargo.toml`, 2 bumped `[package] version`, so release PRs will trigger whole-crate runs (zeta about 37 min). State whether `version` should be exempt.

There is no previous `## External Review` section, so there are no `Author response` rows to answer.

F1.1 and F1.2 must be fixed before the plan. Both are local edits: one to the rewriter's exception scope, one to the bootstrap configuration. The design has otherwise stopped moving, and the rest is wording or apparatus that the first red tests will find, so another round is not worth running.

Recommend: stop
