Tools: Read, Bash, SubagentHandback

The spec's core choice holds up, and the author should keep it. The CLI's numbers are recomputed from the exact f64 bracket midpoints, using the CLI's own erf, bin rule and operation order, and a mismatch stops the run. I checked this against `spacing.rs`, and the measurements agree:
- `normalised_spacings` uses `TAU`, and `math.tau == 2*math.pi` is True.
- `sqrt(4/π)` and `2/sqrt(π)` are the same f64 (`0x1.20dd750429b6dp+0`).
- The 30-digit `a`/`b` columns round-trip to the f64 brackets.
- On tr3, the Poisson KS recomputes to 0.32605.
- The Gram counts reproduce exactly for N = 3, 4 and 5.

The provenance parsing matches every real `err.txt` (`../zeta-f935b23 <N>[ --refine]`, with both `0:02.45` and `1:02:23`). The `.gitignore` negation works (git 2.53.0, scratch clone): `check-ignore -v` reports `.gitignore:104:!tests/fixtures/...` and the file shows as `??`. Two defects remain. One is the Gram-point tolerance rule. The other is a run-store gap that blocks R18.

## F1.1 The R7 snap tolerance of 1e-9·g hides real straddles, so S undercounts, and at N = 7 S is near 0 by construction

**Defect.** R7 and Computations treat a Gram point within 1e-9·g of a bracket end as being at that end. The rule is relative, but the error it absorbs is absolute and tiny. Refined brackets also get narrower as N grows. Median width is 6.9e-4 at N = 3, 1.1e-4 at N = 4 and 1.55e-5 at N = 5. Meanwhile the tolerance grows: about 1e-4 at g ≈ 1e5, and 1e-2 at g ≈ 1e7.

**Failure.** At N = 5 the rule as written gives S = 2. The Facts table says 7. Five Gram points that sit genuinely inside their brackets are treated as endpoints:

| g | distance to a | distance to b | width |
|---|---|---|---|
| 15681.47 | 6.6e-6 | 7.7e-6 | 1.4e-5 |
| 20512.24 | | | |
| 73098.75 | | | |
| 86747.29 | | | |
| 92185.86 | | | |

All five have bracket widths between 5.9e-6 and 7.3e-5, which is far wider than the f64 Gram error. Their zeros' intervals really are in doubt. At N = 7 the tolerance (up to 1e-2) is likely to exceed every refined width. The page would then show S ≈ 0, and the sentence "S bounds how much that matters" would be false. No test catches this:
- The N = 3 fixture pins S = 0, and every rule gives 0 there.
- The synthetic test sits at g₀ ≈ 17.85, where the tolerance is only 1.8e-8.

**Measurement.** I wrote my own Newton-on-θ plus bisect script (Python 3.15.2, Linux, over `/home/bruce/zeta-runs/{tr3,tr4,r5}`). Shares and counts match the spec exactly. S at N = 5 under each rule:

| Rule | S | Gram points snapped to an endpoint |
|---|---|---|
| strict, no tolerance | 7 | — |
| relative 1e-9·g | 2 | 5 |
| absolute 1e-8 | 6 | 1 |

The one case the tolerance exists for is g = 15789.05, which is 1.8e-12 from `a`.

**Fix.**
- Use an absolute tolerance sized to the f64 Newton error. 1e-8 covers the round-2 estimate of about 2e-9 at 1e7.
- Change the N = 5 S value in the Facts table to 6, the number the corrected rule gives.
- Add a synthetic R15 case at large g, for example a bracket of width 2e-5 straddling a Gram point near 9.2e4 by 1e-5, that must give S = 1. It fails under the current rule.
- This changes R7, the Facts table and R15.

## F1.2 The run store lacks the refined N = 6 and N = 7 runs that R18, V2 and V4 require

**Defect.** Facts says every run directory the page needs lives in `~/zeta-runs/`. The store actually holds t2, t3, t4, n5, n6, n7, tr3, tr4 and r5. It has no r6 and no r7. The review's "settled by `r6/rc.txt`" points to a directory that is not in the durable store. If it still exists, it is presumably in RAM-backed scratch.

**Failure.**
- R18 (refined N = 3–7) cannot be generated.
- V4 cannot close its Backlog row.
- A reboot loses the in-flight outputs.
- Re-running is expensive. Refine-to-plain wall time grows 3.5×, 10.7× and 18.2× at N = 3, 4 and 5. Plain N = 7 took 1:02:23, so refined N = 7 extrapolates to tens of hours. This is unmeasured. n7's own `err.txt` warns "may take many hours".

**Fix.**
- Before planning, move r6 and r7, with rc, out and err, into the store, or record that they are lost.
- If they are lost, either make refined N = 6/7 a follow-up PR, with R18 at N = 3–5 for the first PR, or state the re-run cost in the spec.
- This changes Facts ("Run storage"), R18 and V4.

## Smaller items

- **F1.3** R13 has no enforcing check. In `tests/test_root_python_deps.py`, lines 13–14 exclude any import inside `try/except ImportError`. The spec requires matplotlib's import to sit in such a block, so that gate never sees matplotlib. It also would not see a `numpy` import added to the same block. Fix: add an AST check in `tests/test_zeta_results.py` that the script's third-party imports are exactly {matplotlib}, and reword the "needs only that pin" sentence in Dependencies.
- **F1.4** The CI consistency test checks only id, commit and date against HTML the script wrote. A hand-edited count or elapsed time passes. Cheaper route the spec never weighed: commit each run's `out.txt` and `err.txt`. Each is at most 12 KB, carries only the relative path `../zeta-f935b23`, and is not blocked by N3. CI could then regenerate the counts table, the run table and the CLI 20-bin/KS lines, and diff them against `index.html`. Only the δ-derived figures and the Gram table would stay operator-attested. Record it as weighed, even if declined.
- **F1.5** The Facts Gram table header says S counts a Gram point "strictly inside, see Computations". Its 7 is the no-tolerance count, which disagrees with Computations' rule either way. It is fixed together with F1.1.

There is no prior External Review author-response table, so there are no accepted or not-accepted lines.

F1.1 and F1.2 must be fixed before the plan. F1.1 is a one-line rule change backed by a measured number. F1.2 is a data-custody step, not a design change. The design is otherwise stable, and the earlier rounds' fixes check out against the real data, so another round would cost more than the first red tests.

Recommend: stop
