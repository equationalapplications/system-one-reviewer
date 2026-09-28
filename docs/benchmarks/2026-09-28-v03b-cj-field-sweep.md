# Deletion-threshold sweep — field mode, first real result (KEEP 0.70)

**Date:** 2026-09-28 · inputs: the five v03b CJ field runs (see
`docs/evals/2026-09-28-v03b-cj-field-proof.md`) + committed goldens
(`examples/cj-field-goldens.tsv`) · code: `scripts/sweep-thresholds.py
--field`.

## What was built (F2 executability plan, steps a–c)

- **(a)** CJ goldens committed: `pr<TAB>squashSHA<TAB>expected_issues`
  (all five heads expected clean — verified against bot+human review at
  each merged head). Nonzero expectations are refused loudly until
  positive golden rows exist.
- **(b)** `compose()` grew a `deletion_threshold` parameter (default =
  shipped 0.70, byte-identical behavior) so the sweep can move the knob;
  the sweep grew a `--field` mode: runs selected by `fixture_head` SHA,
  same gates as fixtures (fail-open, truncation, packaging_version,
  judged completeness, single provider), FP census split **by rubric** so
  the deletion knob is only blamed for deletion-rubric FPs.
- **(c)** the sweep ran on measured v03b field data. 122 tests green
  (17 new: `tests/test_field_sweep.py`).

## Design note — why the decision rule differs from the fixture sweep

For an `is_real >= t` gate the FP count is monotone non-increasing in t,
and an all-clean cohort has no recall signal — the fixture sweep's
"candidate beats 0.50 on F1" is structurally unpassable here. Clean field
data can decide exactly two things, encoded as the two outcomes:

- **0 deletion FPs at the shipped knob → KEEP** (clean-side validated)
- **deletion FPs at the shipped knob → RAISE_ABOVE_GRID** (0.70 is the
  grid ceiling per the plateau rule, so no auto-candidate — the value is
  a human call informed by the per-PR curve)

## Result

Full 9-row grid, verbatim sweep output:

```
deletion-threshold sweep, field mode (provider/model: jev; code threshold pinned at 0.5)
dt | deletion-rubric FPs | code-rubric FPs (pinned t) | deletion FP per-PR (#43 | #44 | #45 | #46 | #47)
0.30 | 5 | 13 | 2 | 0 | 3 | 0 | 0
0.35 | 5 | 13 | 2 | 0 | 3 | 0 | 0
0.40 | 5 | 13 | 2 | 0 | 3 | 0 | 0
0.45 | 4 | 13 | 1 | 0 | 3 | 0 | 0
0.50 | 4 | 13 | 1 | 0 | 3 | 0 | 0
0.55 | 1 | 13 | 0 | 0 | 1 | 0 | 0
0.60 | 0 | 13 | 0 | 0 | 0 | 0 | 0
0.65 | 0 | 13 | 0 | 0 | 0 | 0 | 0
0.70 | 0 | 13 | 0 | 0 | 0 | 0 | 0
deletion FPs at shipped 0.70: 0 — every clean field run stays clean at the shipped knob
decision: KEEP 0.70 (clean-side validated; recall-side evidence needs a positive field golden, see load_field_goldens)
note: 13 code-rubric FPs at pinned t=0.5 are CODE-threshold pressure — a separate calibration question (needs a positive field golden to evaluate), not this knob
```

**The 0.70 deletion threshold is no longer provisional: it is
clean-side-validated on live field data.** The curve documents that 0.60
would also have been clean on this cohort — but with zero recall-side
field evidence, lowering is not justified (and the #45 lesson is that
lower deletion thresholds are exactly how the v0.2 false-BLOCKER
happened).

## The FP pressure moved, it didn't vanish

13 **code-rubric** FPs at the pinned 0.50 (11 on #43's dense refactor, 2
on #46) are CODE-threshold pressure — a separate calibration question
that needs a positive field golden (a PR with a known real issue) to
evaluate. Not actionable with this cohort; tracked as the successor to
F2.

## Reproduce

```
python3 scripts/sweep-thresholds.py \
  --metrics docs/benchmarks/2026-09-28-v03b-cj-field-metrics.jsonl \
  --label v03bcj- --field --field-goldens examples/cj-field-goldens.tsv
```

Fixture-mode regression: the refactored script reproduces the committed
v03b branch benchmark exactly (candidate 0.55, KEEP 0.50).
