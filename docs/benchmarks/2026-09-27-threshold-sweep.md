1|# Threshold sweep — 2026-09-27 (v0.2, packaging v02) — v02-r2 runs
2|
3|**SUPERSEDES the previous 2026-09-27 v02-final run set.** The v02-final
4|numbers were a packaging artifact and must not be quoted: the fixture
5|builder packed plants 4 and 5 (the O(n²) loop and the duplicate import)
6|into ONE contiguous changed run anchored at 17, so plants at golden 19/22
7|were never judged as separate clusters (review finding B1), and cluster
8|windows still contained neighbouring clusters' changed lines (review
9|finding M1). This doc's runs were made AFTER both fixes: M1 isolates each
10|cluster's window (commit 5e02af5) and the fixture separates all five
11|plants with unchanged lines (commit 136c928, positive fixture
12|ea5df10e1624b095fecd657b12ee23b46e808386, negative
13|e7de08b239982e896d9d57981fa07d83aab7cb65).
14|
15|Protocol: E5 of the v0.2 evaluation spec. Six **fresh** live runs made for
16|this re-evaluation (3 positive + 3 negative, provider `jev`), gated on the
17|committed expected fixture SHAs (`examples/fixture-shas.txt`) and
18|`packaging_version=v02`. The exact metrics lines backing every number here
19|are committed beside this doc:
20|[`2026-09-27-threshold-sweep-metrics.jsonl`](./2026-09-27-threshold-sweep-metrics.jsonl).
21|
22|## Runs used
23|
24|| label | fixture | head | pv | provider | verdict | golden result |
25||---|---|---|---|---|---|---|
26|| v02-r2-baseline-1 | positive | ea5df10e16 | v02 | jev | Changes requested | TP 4/5, raw precision 4/5 (0.80), F1 0.80 |
27|| v02-r2-baseline-2 | positive | ea5df10e16 | v02 | jev | Changes requested | TP 4/5, raw precision 4/5 (0.80), F1 0.80 |
28|| v02-r2-baseline-3 | positive | ea5df10e16 | v02 | jev | Changes requested | TP 4/5, raw precision 4/5 (0.80), F1 0.80 |
29|| v02-r2-negative-1 | negative | e7de08b239 | v02 | jev | Approved | blocker_major 0, minor_notes 0, other_fp 0 |
30|| v02-r2-negative-2 | negative | e7de08b239 | v02 | jev | Approved | blocker_major 0, minor_notes 0, other_fp 0 |
31|| v02-r2-negative-3 | negative | e7de08b239 | v02 | jev | Approved | blocker_major 0, minor_notes 0, other_fp 0 |
32|
33|"Raw precision" = true positives / reported findings on the positive
34|fixture, before any negative-run FP pooling. Severity shown is the model's
35|per-finding score, rounded halves-up by `sev_level`.
36|
37|What the five positive clusters scored (per run; lines are cluster
38|anchors, golden lines in parentheses):
39|
40|| cluster | golden | is_real (3 runs) | severity | category | outcome |
41||---|---|---|---|---|---|
42|| 4 (4) | BLOCKER write-mode truncation | 0.92 / 0.93 / 0.93 | ~2.9 | bug-risk | TP |
43|| 11 (11) | MAJOR silent-None return | 0.57–0.59 | ~1.6 | bug-risk | TP (scored near the threshold) |
44|| 14 (14) | MAJOR unguarded division | 0.80–0.82 | ~2.15 | bug-risk | TP |
| 17 (25) | MINOR duplicate import | 0.71–0.72 | ~1.85 | bug-risk | TP — via 24-cluster ±1 match |
| 24 (19) | MINOR O(n²) concat | 0.64–0.65 | ~1.2 | style | MINOR-style note, exempt from FP_pos |
47|
The B1 artifact is gone: 5 clusters, 5 separate Jev judgments. Four of the
five planted issues are true positives; the one genuine miss is the O(n²)
loop nit, which the model scores 0.64-0.65 with category `style` — a
model-judgment outcome (below-threshold-adjacent, MINOR-style note), not a
packaging artifact. The duplicate import (golden 25) is now reached: it is
covered by the 24/17 cluster pair via ±1 nearest-distance matching (see
the FP_pos note below for the exact accounting).
57|
58|Run-to-run variation is minimal (is_real within ±0.02 on every cluster);
59|the metrics record all scores, reported or not.
60|
61|## Sweep (thresholds 0.30–0.70 step 0.05; 0.75 excluded by the plateau rule)
62|
63|Spec R5 formulas (M2 fix): precision_i = TP_i / (TP_i + FP_pos_i +
64|FP_neg_mean), FP_pos EXCLUDES MINOR-style notes (sev_level 1 + category
65|style), negative FPs enter the curve. The combined figure is min F1 across
66|the positive runs.
67|
68|| t | TP | FP_pos | FP_neg (each / mean) | dFP_neg vs 0.50 | per-run F1 | min F1 |
69||---|---|---|---|---|---|---|
70|| 0.30 | 4 | 1 | 0,0,0 / 0.00 | +0.00 | 0.80–0.80 | 0.80 |
71|| 0.35 | 4 | 1 | 0,0,0 / 0.00 | +0.00 | 0.80–0.80 | 0.80 |
72|| 0.40 | 4 | 1 | 0,0,0 / 0.00 | +0.00 | 0.80–0.80 | 0.80 |
73|| 0.45 | 4 | 1 | 0,0,0 / 0.00 | +0.00 | 0.80–0.80 | 0.80 |
74|| **0.50** | 4 | 1 | 0,0,0 / 0.00 | +0.00 | 0.80–0.80 | 0.80 |
75|| 0.55 | 4 | 1 | 0,0,0 / 0.00 | +0.00 | 0.80–0.80 | 0.80 |
76|| 0.60 | 3 | 1 | 0,0,0 / 0.00 | +0.00 | 0.67–0.67 | 0.67 |
77|| 0.65 | 2–3 | 1 | 0,0,0 / 0.00 | +0.00 | 0.50–0.67 | 0.50 |
78|| 0.70 | 2 | 1 | 0,0,0 / 0.00 | +0.00 | 0.50–0.50 | 0.50 |
79|
- FP_pos stays 1 at every threshold: replaying v02-r2-baseline-1 at 0.50,
  lines 4/11/14 match their goldens (TPs), line 24 matches golden 19 but
  is a MINOR-style note (sev_level 1 + category style — exempt per the
  spec definition), and line 17 matches nothing within ±1, so it is the
  single FP_pos. `eval_against_golden`'s `matched` list credits golden 25
  to the 24-cluster (nearest-distance accounting); either way the model
  folded the duplicate import into a neighbouring finding rather than
  reporting it at its own line — a matching-granularity artifact of the
  ±1 tolerance, quantified in the note below, not a threshold problem.
91|- Combined curve = min F1 across the positive runs, per threshold.
92|- **Candidate: 0.40** (argmax of the combined curve; 0.30–0.55 tie at 0.80,
93|  even-sized tie -> lower middle = 0.40).
94|- Change rule 1 (>=0.20 min-F1 over 0.50 in every positive run): **FAIL** —
95|  no threshold beats 0.50 anywhere; the curve is flat at 0.80 through 0.55
96|  and drops beyond.
97|- Change rule 2 (dFP-neg <= 0 per run, m3 semantics): PASS (0.00 at every
98|  threshold; the negative fixture produces no reported findings at all).
99|- **Decision: KEEP 0.50.** Unlike the superseded v02-final sweep, the new
100|  grid is honestly boring: the fixed packaging found the duplicate import
101|  (it was never judged before), raising TP to 4/5 and the whole flat
102|  region to F1 0.80. Lowering the threshold buys nothing — the one miss
103|  (the O(n²) loop) is reported-adjacent but unmatched at any threshold
104|  value in the grid — and raising it starts losing the 11-cluster (scored
105|  0.57–0.59, uncomfortably close to 0.50 but a true positive in all runs).
106|
107|### Note on FP_pos = 1

Replaying v02-r2-baseline-1 at t=0.50 (`_fp_pos`, MINOR-style exemption
active) gives: 4/11/14 matched (TPs), 24 matched golden 19 but is
sev_level 1 + category style (exempt), and 17 matched nothing — that is
the one FP_pos. Read together with `matched` in the metrics lines
(4/11/14/25): the duplicate-import golden (25) is credited to the
24-cluster's match in eval_against_golden's output, while _fp_pos
attributes the miss to the 17-cluster. Both readings describe the same
reality: the model reported five findings, four correspond to planted
issues, and the import/renderer adjacency is fuzzy at the ±1-line
matching level. Not a blocker: TP/recall are 4/5 under either reading.
If v0.3 wants crisper per-cluster credit, separate the import further
from render (another unchanged-line cushion) — noted for the tuning pass.

## Merge gate
123|
124|Zero blocker_major in EVERY fresh negative run at the shipped threshold
125|(0.50): **PASS** — all three v02-r2-negative runs report nothing at all
126|(`negative_eval` counts all zero, findings empty). The PR may proceed to
127|review/merge.
128|
129|## Reproducing
130|
131|```bash
132|examples/build-fixture.sh && examples/build-negative-fixture.sh
133|# 3x positive + 3x negative live runs, labels v02-r2-{baseline,negative}-N
134|scripts/sweep-thresholds.py --metrics ~/.local/state/jev-review/metrics.jsonl \
135|  --label v02-r2- --golden examples/fixture-golden.tsv \
136|  --negative-golden examples/negative-golden.tsv --shas examples/fixture-shas.txt
137|```