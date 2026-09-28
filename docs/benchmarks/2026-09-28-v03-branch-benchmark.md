# v0.3 branch benchmark — fixture re-run on the field-eval fixes

**Date:** 2026-09-28, branch `v03-field-evals` (commits e6b7aef..e763080+),
provider `jev`, `PACKAGING_VERSION = v03`.

Why: the v0.3 changes alter every model call's input (`change_type` in
hunk state; deletion-only clusters get `DELETION_QUESTIONS`) and `--range`
now diffs `A...B`. The benchmark of record must be re-verified on the new
inputs before merge (v0.2 rule: any compose/packaging change re-runs the
sweep fixtures).

## Positive fixture (5 plants, /tmp/jev-review-pos @ 3346ca1aa3)

| run | verdict | recall | precision | F1 |
|---|---|---|---|---|
| v03-r1-baseline-1 | Changes requested | 1.00 | 0.83 | 0.91 |
| v03-r1-baseline-2 | Changes requested | 1.00 | 0.83 | 0.91 |
| v03-r1-baseline-3 | Changes requested | 1.00 | 1.00 | 1.00 |

All runs complete (no fail-open, no parse failures). Compare v0.2 record
(`v02-r3-baseline-1..3`): 0.91 / 0.91 / 0.91 — same or better; run 3's
1.00 means the 6th (unlisted sentinel leftover) finding did not appear.

Note: plant #3 (unguarded division guard REMOVAL) is an in-file
deletion-only cluster, so these runs exercised the new
`DELETION_QUESTIONS` path against a real plant — recall held at 1.0 ×3.

## Negative fixture (/tmp/jev-review-neg)

| run | verdict | FP census |
|---|---|---|
| v03-r1-neg-1 | Approved | blocker_major 0, minor_notes 0, other_fp 0 |
| v03-r1-neg-2 | Approved | blocker_major 0, minor_notes 0, other_fp 0 |
| v03-r1-neg-3 | Approved | blocker_major 0, minor_notes 0, other_fp 0 |

## Verdict

Merge gate PASS at threshold 0.50 on the v03 packaging version. Raw
records: [2026-09-28-v03-branch-metrics.jsonl](2026-09-28-v03-branch-metrics.jsonl).

Still unproven: the #45 field failure mode (whole-file deletions of
unused Expo components) — no live re-run of that PR yet; the README
states this. The full threshold sweep over v03 records is the next v0.3
step (sweep default is now `--packaging-version v03`).
