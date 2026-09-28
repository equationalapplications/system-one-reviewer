# r2 dispositions — field-evals brief

- Finding 1 (headline accuracy "1 of 5" wrong): **FIXED** — now "2 of 5 —
  the two TNs"; Known constraints now says 4 strong + pr46-fix-delta moderate,
  matching the table.
- Finding 2 (F1 miscounts #45 clusters): **FIXED** — now "all six
  whole-file-deletion clusters" and "Five were held back" (5× is_real
  0.37–0.44 below the 0.50 gate, 1× 0.65 crossed).
- Finding 3 (F2 rule wouldn't catch the cited defect; devModel.ts:1 is the
  only lone MAJOR, jitter-zone, unvetted): **FIXED** — F2 rewritten: names
  devModel.ts:1 (sev 1.51 → sev_level 2, is_real 0.52, |0.52−0.50| < 0.03
  jitter zone, unvetted); states the mockLlmProvider defect is MINOR so the
  rule never reaches it; reframes as severity-calibration + verdict-rule
  problem; proposal now "land F1 first, then sweep a (severity, is_real)
  joint rule — no knob flips before the sweep".
- Finding 4 nit (F3 "real findings" overstated): **FIXED** — "judged
  findings … some reported, some not".
- Finding 5 nit (F4 range 0.69–0.98 wrong): **FIXED** — recomputed from the
  ledger: 0.69–0.96 across all 33 runs with a pr_level, with named min/max
  records (v02-r2-negative-3 / v02-baseline-2); subset ranges unchanged and
  now consistent (0.90 ≤ 0.96).
