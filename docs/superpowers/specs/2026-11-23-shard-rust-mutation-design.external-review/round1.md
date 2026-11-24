Tools: Read, Bash, SubagentHandback

The spec gets the core right, and I checked it rather than taking it on trust. The plan's count formula matches cargo-mutants' round-robin split: at 26dde61, zeta's 339 diff mutants list as 68/68/68/68/67. `total_mutants` in `outcomes.json` is the shard's own count, not the crate total: amicable shard 2/3 gave 6, and a `--check` run of zeta PR 3 shard 4/5 gave 67. A shard that selects nothing writes `mutants.out/` but no `outcomes.json` and exits 0, so the `--expect` "missing file is 0" rule is what turns it red. The `set +e` / `PIPESTATUS` form, a plan script shared by both runs, and the post-run count check against the run itself are the right shapes; keep them. (cargo-mutants 27.1.0, cargo 1.100.0, Linux 7.0.0 on `claude`.)

## F1.1 The per-crate cap (16 shards, K > 1200 red) protects against a total that can't happen, and it collides with the spec's own fix

**Defect.** The cap is justified by 13 crates x 16 = 208 jobs, under GitHub's 256-job matrix limit. But the limit is on the whole matrix, and the real sweep total is far smaller. The cap is also a mutant count, while the budget it protects is time.

**Concrete failure.**
- At 26dde61 (#246's 120-minute commit) the sweep plans 41 shards in total (table below).
- descartes-rs has 831 mutants, the most of any crate, and the spec never mentions it. Its suite runs in about 3 s on 4 CPUs. At 1201 mutants it becomes a permanent sweep fault, even though 16 shards of it would take about 5 minutes each.
- The spec's remedy for a slow shard is "B is lowered" (Design 5). The ceiling is 16 x B, so lowering B lowers it. Below B = 47 the ceiling drops under zeta's 748 and zeta's sweep faults the same month. After PR 4 (planned in `zeta-rh-verification`) zeta is larger still, so the B that triggers this rises.

**Measurement.** `cargo mutants --list --json | jq length` per crate at 26dde61:

| Crate | K | n |
| --- | --- | --- |
| amicable | 20 | 1 |
| collatz | 44 | 1 |
| descartes | 831 | 12 |
| e | 136 | 2 |
| factorial | 64 | 1 |
| fib | 41 | 1 |
| goldbach | 87 | 2 |
| perfect-numbers | 89 | 2 |
| pi | 166 | 3 |
| prime | 158 | 3 |
| sq | 32 | 1 |
| twin-primes | 121 | 2 |
| zeta | 748 | 10 |
| **Total** | **2537** | **41** |

descartes test time: `taskset -c 0-3 cargo test` took 3.03 s wall.

**Smallest fix.** Drop the per-crate cap and the K > 1200 rule. Fail the plan only when the sum of n across all emitted units exceeds 256. This changes Design 1, R3 (its error line), and the BATS cases for K = 1200 and K = 1201. N4 is unaffected.

## F1.2 The sweep, not the PR, is the case that sets B, and V1 has no rule for acting on its result

**Defect.** zeta's 748 whole-crate mutants split into 8 shards of 75 and 2 of 74. That is exactly B, against 68 for the PR 3 diff. The sweep's `mutants` job also pays more setup than the 4 minutes Design 1 budgets:
- it keeps the from-source `cargo install cargo-mutants`;
- it has no GMP cache restore (`mutation-testing.yml` never mentions gmp);
- R9 changes neither.

**Concrete failure.** Design 1 puts the cancellation point near 42 s per mutant, and that figure assumes the PR job's setup. Sweep shards cross that line first. The "past about 50 minutes, lower B" rule is attached only to V2, which measures the easier PR case after merge. V1 measures the binding case but only says "under 60 minutes" and "record".

**Measurement.** A cold `cargo build --tests` of zeta-rs (GMP included) took 108.6 s wall on `claude` with `taskset -c 0-3`. CI will be slower. I did not time the from-source cargo-mutants install, so the total overhead is unmeasured.

**Smallest fix.**
- Give V1 the same 50-minute rule: if any shard runs past about 50 minutes, B is lowered before merge.
- Either give the sweep `mutants` job the prebuilt install and the GMP cache restore, or state its larger setup in Design 1.
- This changes V1, and R9 if you take the install route.

## F1.3 R12 cannot be done in the CI PR

**Defect.** The Backlog row "zeta monthly mutation sweep budget" does not exist on master or at b091030. It exists only on #246's branch.

**Concrete failure.** The CI PR branches from master, so it has nothing to delete. The row then survives when #246 merges after its rebase.

**Measurement.** `git show <ref>:docs/superpowers/README.md | grep -c 'mutation sweep budget'` returns 0 on master and 1 at 26dde61.

**Smallest fix.** Move the deletion to #246's rebase in Design 5 and R12. The CI PR keeps only the plan-index row.

## F1.4 Root `CLAUDE.md` has 9 bytes of headroom, and R11 adds content

**Defect.** `CLAUDE.md` is 29991 bytes against the 30000-byte ceiling. Both pre-push and `claude-md-budget` enforce it.

**Concrete failure.** R11 adds the plan job, the shard matrix, `--expect`, the canary-only `--min-caught`, the sweep's per-shard jobs and a `cargo mutants -F` line. That is well over 9 bytes, so the first push of the CI PR is refused.

**Smallest fix.** Have R11 require the Rust mutation lines (140–142; line 142 is 556 bytes) to be rewritten with no net growth in bytes, and push the detail behind the existing `→ ai-config/docs/knowledge/math-testing-policy.md` pointer. That pointer is in another repo, so the plan needs a separate ai-config change and notice to the ai-config session.

## Smaller items

- **F1.5** The table row "313 with outcomes" is an earlier PR 3 diff. #246's own Backlog row says "313 diff-scoped mutants ... about 70 minutes". The spec presents it beside "339 listed" as the same diff. Label it, because the 14.5 s per mutant figure comes from it.
- **F1.6** The "947 total, 11 crates" context row is stale (2537 across 13 crates, see F1.1). The fast-crate cost example should be descartes (12 shards), not pi (3).
- **F1.7** R5 does not require the Rust toolchain step or the GMP cache restore in the `mutation-rs` and `mutation-rs-canary` jobs. Design 1's setup budget assumes the cache. Name both in R5.
- **F1.8** `scripts/mutation-shard-count.sh` runs on the PR path but is not added to `RS_CANARY_PATHS`. R13's reasoning ("the gate's scripts join the canary") covers it. The value is low, since root bats runs on any `scripts/` change.
- **F1.9** The BATS live-log test should pull the four lines out of `mutation-pr.yml` rather than retype them. Otherwise it tests a copy. The unittest's text pin partly covers this.
- **F1.10** The summary `grep` runs after `set -e`, and its exit status is not specified. A no-match grep would fail the step. It cannot happen today because the `repro:` line always prints, but the step should wrap the grep so it cannot fail.
- **F1.11** V1's branch dispatch runs `notify` with `FULL_SWEEP=true`, so branch code closes or comments on the real tracking issue. Say that this is intended.

No `Author response` table exists yet, so there are no accepted / not accepted lines.

Checked and not raised:
- the stability of the plan-to-shard diff: three-dot against a fixed merge commit gives the same diff in every job;
- the aggregator skip rules;
- the canary through the plan, which plans n = 1;
- the shard formula arithmetic;
- slug uniqueness;
- the `notify` slug handling;
- the Python baseline move.

F1.1 through F1.4 should be fixed before the plan is written. F1.1 and F1.2 are small design edits, and F1.3 and F1.4 are sequencing and byte-count fixes. Once they are in, the design has stopped moving. V1, V2 and the first red tests will find the rest more cheaply than another review round.

The decision that fixes F1.1: are you willing to change the one-formula cap from per crate to a total across the whole plan? N4 survives either way.

Recommend: stop
