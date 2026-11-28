Tools: Read, Bash, SubagentHandback

The file-touch judge with a per-file presence list is the right design, and it now matches the measured data. I replayed the SARIF copies. The per-file counts in sarif1 and sarif2 match R16 exactly (3/8/4/1/1). sarif3 shows the 3-to-2 drop in `mutation_gate_items.py` that the presence list exists to catch. sarif1 coverage is `.py 118` and `.html 1`, and on `d3ef01e` there are 118 tracked non-empty `.py` files and 1 `.html` file (`git ls-tree -r -l`, none empty). `.pyi` is not in the coverage list, so leaving it out of R7 is correct. Dropping `.snyk` closes round 5's hole A without adding machinery. Keep the judge's unit (the file), keep the four red conditions, and keep `GATE_FILES` as the guard.

### F1.1 The suppression search matches the judge's own source and its tests, so every PR is red

R7 makes any tracked, non-empty `.py` file that contains `deepcode ignore` (case-insensitive) a suppression. Two files the implementing PR must add contain that string:
- `scripts/snyk_file_touch.py` needs it as its search needle.
- R10 requires `tests/test_snyk_file_touch.py` to cover "a suppression comment in upper and lower case". Fixture text written as a literal contains the string.

Failure: from the implementing PR onward, the judge prints `snyk-scan: scripts/snyk_file_touch.py contains an inline Snyk suppression` on every PR, and `auto-merge` never runs. V3 can never pass.

Measurement: none needed. It follows from the text: today the only tracked hit is the spec itself (`git grep -il 'deepcode ignore' HEAD` returned only the `.md` file), and R5 limits the scan to compared extensions. V1 would catch it, but as a red on the first PR.

Smallest fix, in R7 and R10:
- Search with a pattern whose source text does not contain the phrase, for example `re.compile(r"deepcode\s+ignore", re.I)`. This also catches whitespace variants, which the literal misses.
- Require tests to build suppression fixtures at runtime, for example `"deep" + "code ignore"`.
- Add an R10 case: the suppression check over the real tree at the implementing commit reports 0.

### F1.2 The "likely Snyk drift" label conflates drift with a new finding the PR caused, and the procedure sends that finding round the judgment

A presence difference in a file the PR did not change gets the drift label. The red procedure then says "The PR did not cause it… do not edit `.snyk-files`… the operator… merges one list update, which unblocks every PR."

Known limits names a case where the PR did cause it: a helper change in file A that produces a new result in unchanged file B, with a flow that does not name A. A `rollback-cycle` revert straight to master that adds or removes a finding (git-workflow-040) also shows up as "drift" on every open PR.

Failure: in both cases the output tells the agent and the operator that Snyk is at fault. The operator merges a list bump, the PR re-runs green, and it auto-merges. Nobody has judged the new result at source. The presence list was meant to be the backstop for exactly this case, and the label disarms it.

Fix (wording and red procedure only, no design change):
- Change the label to `(file unchanged by this PR: Snyk drift, a master-side change, or an effect of this PR's edits elsewhere)`.
- Treat a difference as drift only when the same difference appears on another open PR, or on an empty probe PR. Otherwise judge it at source, like a touched finding.
- Update the Known limits "helper change" row to match.

### F1.3 After the list update, "unblocks every PR" needs a new event on each PR

Round 2 Ergonomics already noted that a re-run reuses the old merge ref. The revision 6 drift branch still says one list-update merge "unblocks every PR".

As I recall, a re-run of a `pull_request` run keeps the original `GITHUB_SHA`. That SHA is the merge commit built against the old master, so the old `.snyk-files` is compared again and the PR stays red. I have not measured this. To check it: re-run `snyk-scan` on a PR after master moves, and compare the `HEAD is now at` line in the checkout log.

Fix: one sentence in the red procedure and in the Known limits drift row. Each PR needs a new event: a push, close and reopen, or a label (`labeled` is already a trigger).

### Smaller items

- F1.4 V1's `.py 120/120` assumes only two new `.py` files. R11's workflow test has no named file, and every existing workflow test is its own file (`tests/test_*_workflow.py`), so a new one gives 121. Either name R11's file or make V1 say "a/b equal". V1's rule "any other line, amend the spec" would otherwise trip on a count.
- F1.5 A result in a tracked path that contains whitespace is touched on every PR, permanently, and has no remedy. The red procedure and Known limits do not mention it. Add "rename the file".
- F1.6 V2 push 1 still cannot fail under file-touch: any edit to `zeta_results.py` touches its results (round 4 Adversarial). V4's quota figure has no decision attached. Both are harmless to keep; say what V4's number would change, or drop it.

No previous `Author response` table exists. This is the first external round, and the Multi-Lens rounds carry dispositions, not author-response rows, so there are no accepted or not-accepted lines.

F1.1 must be fixed before the plan, since R10 as written forces the wedge. F1.2 and F1.3 are red-procedure text and should go in the same edit. The rest can be left for the first red tests. The design has not moved since round 4, and none of these findings is against the judge itself, so another round costs more than it would find.

Recommend: stop
