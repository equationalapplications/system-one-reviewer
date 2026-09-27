# Threshold sweep — 2026-09-27 (v0.2, packaging v02)

Protocol: E5 of the v0.2 evaluation spec. Six **fresh** live runs made for
this PR (3 positive + 3 negative, provider `jev`), gated on the committed
expected fixture SHAs (`examples/fixture-shas.txt`) and
`packaging_version=v02`. The exact metrics lines backing every number here
are committed beside this doc:
[`2026-09-27-threshold-sweep-metrics.jsonl`](./2026-09-27-threshold-sweep-metrics.jsonl).

## Runs used

| label | fixture | head | pv | provider | verdict | golden result |
|---|---|---|---|---|---|---|
| v02-final-baseline-1 | positive | 5ddacab7f1 | v02 | jev | Changes requested | TP 3/5, raw precision 3/4 (0.75), F1 0.67 |
| v02-final-baseline-2 | positive | 5ddacab7f1 | v02 | jev | Changes requested | TP 3/5, raw precision 3/4 (0.75), F1 0.67 |
| v02-final-baseline-3 | positive | 5ddacab7f1 | v02 | jev | Changes requested | TP 3/5, raw precision 3/4 (0.75), F1 0.67 |
| v02-final-negative-1 | negative | 332bd13e02 | v02 | jev | Approved | blocker_major 0, minor_notes 0, other_fp 0 |
| v02-final-negative-2 | negative | 332bd13e02 | v02 | jev | Approved | blocker_major 0, minor_notes 0, other_fp 0 |
| v02-final-negative-3 | negative | 332bd13e02 | v02 | jev | Approved | blocker_major 0, minor_notes 0, other_fp 0 |

All six runs are identical in judged content run-to-run (deterministic
packaging, stable Jev answers on this fixture): TP 3, FP_pos 1 (the
reported-but-unmatched 4th finding), FP_neg 0 at the shipped threshold.

"Raw precision" = true positives / reported findings on the positive
fixture, before any negative-run FP pooling.

## Sweep (thresholds 0.30–0.70 step 0.05; 0.75 excluded by the plateau rule)

| t | TP | FP_pos | FP_neg (each / mean) | ΔFP_neg vs 0.50 | per-run F1 | min F1 |
|---|---|---|---|---|---|---|
| 0.30 | 3 | 1 | 1,1,1 / 1.00 | +1.00 | 0.67–0.67 | 0.67 |
| 0.35 | 3 | 1 | 1,1,0 / 0.67 | +0.67 | 0.67–0.67 | 0.67 |
| 0.40 | 3 | 1 | 0,0,0 / 0.00 | +0.00 | 0.67–0.67 | 0.67 |
| 0.45 | 3 | 1 | 0,0,0 / 0.00 | +0.00 | 0.67–0.67 | 0.67 |
| **0.50** | 3 | 1 | 0,0,0 / 0.00 | +0.00 | 0.67–0.67 | 0.67 |
| 0.55 | 3 | 1 | 0,0,0 / 0.00 | +0.00 | 0.67–0.67 | 0.67 |
| 0.60 | 3 | 1 | 0,0,0 / 0.00 | +0.00 | 0.67–0.67 | 0.67 |
| 0.65 | 3 | 1 | 0,0,0 / 0.00 | +0.00 | 0.67–0.67 | 0.67 |
| 0.70 | 3 | 1 | 0,0,0 / 0.00 | +0.00 | 0.67–0.67 | 0.67 |

- Combined curve = min F1 across the positive runs, per threshold.
- **Candidate: 0.50** (argmax of the combined curve; the whole grid ties at
  0.67 and the tie rule returns the middle of the odd-sized tied range).
- Change rule 1 (≥0.20 min-F1 over 0.50 in every positive run): **FAIL** —
  no threshold beats 0.50 anywhere on the curve.
- Change rule 2 (no FP increase on any negative run): PASS at 0.40–0.70.
- **Decision: KEEP 0.50.** The shipped threshold survives the sweep, as
  expected: the two misses (the O(n²) loop nit and the duplicate import)
  are scored below 0.30 by Jev itself, so lowering the gate cannot recover
  them — it only imports negative-run FPs (0.30/0.35).

## Merge gate

Zero blocker_major in EVERY fresh negative run at the shipped threshold
(0.50): **PASS** (see the three negative rows above; each `negative_eval`
counts are all zero). The PR may proceed to review/merge.

## Reproducing

```bash
examples/build-fixture.sh && examples/build-negative-fixture.sh
# 3x positive + 3x negative live runs, labels v02-final-{baseline,negative}-N
scripts/sweep-thresholds.py --metrics ~/.local/state/jev-review/metrics.jsonl \
  --label v02-final- --golden examples/fixture-golden.tsv \
  --negative-golden examples/negative-golden.tsv --shas examples/fixture-shas.txt
```
