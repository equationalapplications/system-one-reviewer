# v0.3b branch benchmark — fixtures re-run on the corroboration-round code

**Date:** 2026-09-28, branch `v03-field-evals` at the v0.3b review-round
commit (Opus r2 fixes), provider `jev`, `PACKAGING_VERSION = v03b`.

Why: v0.3b changed every model call's input again (references_remaining in
state, three-valued change_type, rewritten deletion rubric) and changed
compose() (per-rubric threshold, corroboration gate). Per the standing
rule, thresholds and benchmark claims are re-verified on the new code.

The NEGATIVE fixture now contains a benign whole-file deletion
(`src/format_extra.py`, the #45 failure shape) — the FP census judges it
under the deletion rubric on every run. The v03 negative benchmark file is
superseded (its fixture_head predates the deletion cluster).

## Results (runs `v03b-pos2-1..3`, `v03b-neg2-1..3`)

- Positive fixture: recall 5/5 (1.00), raw precision 5/6 (0.83),
  **F1 0.91 — identical across all three runs**, matching the v0.2 record.
- Negative fixture (incl. the whole-file deletion): **zero reported
  findings of any kind, all three runs.**
- The benign deletion cluster scored under the deletion rubric:
  severity 0.03–0.04, is_real 0.20–0.24, confidence 0.96–0.97 — versus
  2.73–2.82 severity (BLOCKER-level) under the old generic questions in
  the #45 field run. The rewritten rubric + 0.70 gate hold it far below
  the reporting line.

Raw records: [2026-09-28-v03b-branch-metrics.jsonl](2026-09-28-v03b-branch-metrics.jsonl).

## Standing caveat

DELETION_REAL_THRESHOLD (0.70) is provisional. The sweep tool cannot yet
sweep the deletion rubric's threshold (tracked as the open F2 executability
work in docs/evals/2026-09-28-field-evals-cj-prs.md); the fixture numbers
above verify the current gate does not misfire, not that 0.70 is optimal.
