# Threshold sweep — 2026-09-27 (v0.2, packaging v02) — v02-r3 runs (final)

**This set supersedes v02-r2 and v02-final.** History, briefly: v02-final
was a packaging artifact (two plants packed into one cluster — r1 B1 —
and cluster windows still contained neighbours' changed lines — r1 M1).
v02-r2 fixed the packaging and the golden placement (r4 M1: the O(n²)
"miss" was a golden-line artifact, not a model outcome) and replayed to
TP 5/5, F1 1.00. r7 m5 then made plant 2 a REAL behavior change
(`missing` sentinel default instead of a cosmetic `None` default) — the
SHA gate caught the fixture change, and this v02-r3 set is the first
run against the fully corrected fixture. Raw metrics lines for all
three generations are committed beside this doc.

## Runs used (v02-r3)

| label | fixture | head | pv | provider | verdict |
|---|---|---|---|---|---|
| v02-r3-baseline-1 | positive | 3346ca1aa3 | v02 | jev | Changes requested |
| v02-r3-baseline-2 | positive | 3346ca1aa3 | v02 | jev | Changes requested |
| v02-r3-baseline-3 | positive | 3346ca1aa3 | v02 | jev | Changes requested |
| v02-r3-negative-1 | negative | e7de08b239 | v02 | jev | Approved |
| v02-r3-negative-2 | negative | e7de08b239 | v02 | jev | Approved |
| v02-r3-negative-3 | negative | e7de08b239 | v02 | jev | Approved |

Protocol: E5 of the v0.2 evaluation spec. Six **fresh** live runs,
gated on the committed expected fixture SHAs
(`examples/fixture-shas.txt`), `packaging_version=v02`, `fail_open`
false, and `len(judged) == n_analyzed` (the sweep rejects fail-open and
incomplete runs). All six v02-r3 runs pass every gate; `judged 6 of 6`
on every positive run (the sentinel change adds a sixth judged cluster:
the `return None` line is now a separate edit from the signature).

## Positive-fixture results

**TP 5/5, recall 1.00, raw precision 5/6 (0.83), F1 0.91 — identical
across all three runs.** The sixth reported finding is the model
flagging the `return None` line that the sentinel plant leaves behind;
it does not correspond to a golden row and counts as the single FP_pos
at the shipped threshold. The negative fixture still produces zero
findings of any kind in all three runs.

Per-cluster is_real (3 runs): 6 → 0.92/0.93/0.93 · 13 → 0.57–0.59 ·
16 → 0.80–0.82 · 20 → 0.71–0.72 · 27 → 0.64–0.65 (anchors shifted +2
from the r2 numbers by the sentinel's two added lines).

## Sweep (thresholds 0.30–0.70 step 0.05)

Spec R5 formulas: precision_i = TP_i / (TP_i + FP_pos_i + FP_neg_mean),
FP_pos EXCLUDES MINOR-style notes (sev_level 1 + category style),
negative FPs enter the curve. Combined figure = min F1 across the
positive runs.

| t | TP | FP_pos | FP_neg (each / mean) | per-run F1 | min F1 |
|---|---|---|---|---|---|
| 0.30 | 5 | 1 | 0,0,0 / 0.00 | 0.91 | 0.91 |
| 0.35 | 5 | 1 | 0,0,0 / 0.00 | 0.91 | 0.91 |
| 0.40 | 5 | 1 | 0,0,0 / 0.00 | 0.91 | 0.91 |
| 0.45 | 5 | 1 | 0,0,0 / 0.00 | 0.91 | 0.91 |
| **0.50** | 5 | 1 | 0,0,0 / 0.00 | 0.91 | 0.91 |
| 0.55 | 4–5 | 0–1 | 0,0,0 / 0.00 | 0.89–1.00 | 0.89 |
| 0.60 | 4 | 0 | 0,0,0 / 0.00 | 0.89 | 0.89 |
| 0.65 | 3–4 | 0 | 0,0,0 / 0.00 | 0.75–0.89 | 0.75 |
| 0.70 | 3 | 0 | 0,0,0 / 0.00 | 0.75 | 0.75 |

- **Candidate: 0.40** (argmax of the combined curve; 0.30–0.50 tie at
  0.91, tie rule takes the lower middle).
- Change rule 1 (>=0.20 min-F1 over 0.50 in every positive run):
  **FAIL** — 0.50 sits inside the flat 0.91 plateau; nothing beats it.
- Change rule 2 (dFP-neg <= 0 per run): PASS (0.00 at every threshold).
- **Decision: KEEP 0.50.**

Caveat for honesty: the fixture is small (5 plants, one file) and the
provider runs are near-deterministic; these numbers measure this
fixture, not general PR-review quality.

## Merge gate

Zero blocker_major in EVERY fresh negative run at the shipped threshold
(0.50): **PASS** — all three v02-r3-negative runs report nothing at all
(`negative_eval` counts all zero, findings empty). The PR may proceed
to review/merge.

## Reproducing

```bash
examples/build-fixture.sh && examples/build-negative-fixture.sh
# 3x positive + 3x negative live runs, labels v02-r3-{baseline,negative}-N
scripts/sweep-thresholds.py --metrics ~/.local/state/jev-review/metrics.jsonl \
  --label v02-r3- --golden examples/fixture-golden.tsv \
  --negative-golden examples/negative-golden.tsv --shas examples/fixture-shas.txt
```
