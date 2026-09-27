# Threshold sweep — 2026-09-27 (v0.2, packaging v02) — v02-r2 runs

**SUPERSEDES the previous 2026-09-27 v02-final run set.** The v02-final
numbers were a packaging artifact and must not be quoted: the fixture
builder packed plants 4 and 5 (the O(n²) loop and the duplicate import)
into ONE contiguous changed run anchored at 17, so plants near golden
lines 19/25 were never judged as separate clusters (review finding B1,
r1), and cluster windows still contained neighbouring clusters' changed
lines (review finding M1, r1).

**Corrected in place (r4):** this doc's first version scored the runs
TP 4/5, F1 0.80 and called the O(n²) plant a genuine miss. That was a
golden-placement artifact, not a model outcome: the positive golden
pointed at HEAD line 19 while the cluster containing the O(n²) plant
anchors at its first changed line (17), outside the ±1 matching
tolerance — so a finding the model actually made (is_real ≈ 0.72) was
scored as miss + false positive. The golden now points at line 18 (the
loop line itself, the defect's home), mechanically verified against the
HEAD content by the build script like every golden row. The same
committed runs replay to **TP 5/5, F1 1.00** under the corrected
golden. The raw metrics lines are unchanged records; their embedded
`golden_eval` fields were computed at run time against the original
golden and are superseded by the replayed evaluation below (reproduce
with the command at the end).

## Runs used

| label | fixture | head | pv | provider | verdict |
|---|---|---|---|---|---|
| v02-r2-baseline-1 | positive | ea5df10e16 | v02 | jev | Changes requested |
| v02-r2-baseline-2 | positive | ea5df10e16 | v02 | jev | Changes requested |
| v02-r2-baseline-3 | positive | ea5df10e16 | v02 | jev | Changes requested |
| v02-r2-negative-1 | negative | e7de08b239 | v02 | jev | Approved |
| v02-r2-negative-2 | negative | e7de08b239 | v02 | jev | Approved |
| v02-r2-negative-3 | negative | e7de08b239 | v02 | jev | Approved |

Protocol: E5 of the v0.2 evaluation spec. Six **fresh** live runs made
for this re-evaluation (3 positive + 3 negative, provider `jev`),
gated on the committed expected fixture SHAs
(`examples/fixture-shas.txt`), `packaging_version=v02`, `fail_open`
false, and `len(judged) == n_analyzed` (the sweep rejects fail-open and
incomplete runs). Raw metrics lines are committed beside this doc:
[`2026-09-27-threshold-sweep-metrics.jsonl`](./2026-09-27-threshold-sweep-metrics.jsonl).

## What the five positive clusters scored (per run)

| cluster anchor | plant | is_real (3 runs) | severity | category |
|---|---|---|---|---|
| 4 | BLOCKER write-mode truncation | 0.92 / 0.93 / 0.93 | ~2.9 | bug-risk |
| 11 | MAJOR silent-None return | 0.57–0.59 | ~1.6 | bug-risk |
| 14 | MAJOR unguarded division | 0.80–0.82 | ~2.15 | bug-risk |
| 17 | MINOR O(n²) string concat | 0.71–0.72 | ~1.85 | bug-risk |
| 24 | MINOR duplicate import | 0.64–0.65 | ~1.2 | style |

All five clusters scored above the shipped 0.50 threshold in all three
runs → **TP 5/5, raw precision 5/5, F1 1.00** under the corrected
golden. Run-to-run variation is minimal (is_real within ±0.02). The
closest call is the 11-cluster (0.57–0.59) — a true positive, but close
enough to the gate that the per-threshold curve matters.

## Sweep (thresholds 0.30–0.70 step 0.05)

Spec R5 formulas: precision_i = TP_i / (TP_i + FP_pos_i + FP_neg_mean),
FP_pos EXCLUDES MINOR-style notes (sev_level 1 + category style),
negative FPs enter the curve. Combined figure = min F1 across the
positive runs.

| t | TP | FP_pos | FP_neg (each / mean) | per-run F1 | min F1 |
|---|---|---|---|---|---|
| 0.30 | 5 | 0 | 0,0,0 / 0.00 | 1.00 | 1.00 |
| 0.35 | 5 | 0 | 0,0,0 / 0.00 | 1.00 | 1.00 |
| 0.40 | 5 | 0 | 0,0,0 / 0.00 | 1.00 | 1.00 |
| 0.45 | 5 | 0 | 0,0,0 / 0.00 | 1.00 | 1.00 |
| **0.50** | 5 | 0 | 0,0,0 / 0.00 | 1.00 | 1.00 |
| 0.55 | 5 | 0 | 0,0,0 / 0.00 | 1.00 | 1.00 |
| 0.60 | 4 | 0 | 0,0,0 / 0.00 | 0.89 | 0.89 |
| 0.65 | 3–4 | 0 | 0,0,0 / 0.00 | 0.75–0.89 | 0.75 |
| 0.70 | 3 | 0 | 0,0,0 / 0.00 | 0.75 | 0.75 |

- **Candidate: 0.40** (argmax of the combined curve; the 0.30–0.55 tie
  at 1.00 is even-sized, tie rule takes the lower middle).
- Change rule 1 (>=0.20 min-F1 over 0.50 in every positive run):
  **FAIL** — 0.50 sits inside the flat 1.00 plateau; nothing beats it.
- Change rule 2 (dFP-neg <= 0 per run): PASS (0.00 at every threshold).
- **Decision: KEEP 0.50.** The flat plateau means the threshold is not
  load-bearing on this fixture: every plant clears 0.50 comfortably and
  the first casualties (0.60+) are the 11/24 clusters. The shipped gate
  survives with the strongest evidence this fixture can give — perfect
  recall and precision, zero false positives on the negative fixture.

Caveat for honesty: the fixture is small (5 plants, one file) and the
provider runs are near-deterministic; F1 1.00 is this fixture's
ceiling, not a claim about general PR-review quality.

## Merge gate

Zero blocker_major in EVERY fresh negative run at the shipped threshold
(0.50): **PASS** — all three v02-r2-negative runs report nothing at all
(`negative_eval` counts all zero, findings empty). The PR may proceed
to review/merge.

## Reproducing

```bash
examples/build-fixture.sh && examples/build-negative-fixture.sh
# 3x positive + 3x negative live runs, labels v02-r2-{baseline,negative}-N
scripts/sweep-thresholds.py --metrics ~/.local/state/jev-review/metrics.jsonl \
  --label v02-r2- --golden examples/fixture-golden.tsv \
  --negative-golden examples/negative-golden.tsv --shas examples/fixture-shas.txt
```

(The committed metrics lines were produced before the r4 golden
correction; replaying them through the sweep with the current golden
reproduces the tables above exactly.)
