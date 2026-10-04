# G-B per-file batching gate — per-file judgment batching FAILS, stays retired

**Date:** 2026-10-04 · provider `jev` (live) · build: `impl/ast-units` at
`cee6c22` (v08 + §10 close-out) · plan Task 9, brief rev 7 G-B spec.
Harness: `/tmp/gb_harness.py` + `/tmp/gb_analysis.py` (OUT-OF-TREE per
r2-B1 — imports the working tree's `hunk_state`/`jev_ask`/etc. read-only,
never ships; raw data `/tmp/gb_results/gb_run.json`, arm-A ledger JSONs in
`/tmp/gb_results/a1..a3/`).

## Verdict: **FAIL — all pass criteria miss. Per-file batching stays OFF
(default outcome per D5). No transport code ships.**

## Design (exactly per the brief)

- **Samples:** the 5 merged clean CJ heads (#43–#47, `cj-field-goldens.tsv`
  SHAs) × 3 repeats per arm. #43 is the defect-positive arm (3 bot majors:
  2 non-band anchors in `import.tsx` + the 3 `importMachine.ts` band spans
  from `cj43-prefix-band-goldens.tsv`); the other 4 are negative goldens.
  Cluster census: 34/9/7/12/2 units (64 total), multi-cluster files
  (`import.tsx` 14, `chunkedImportDump.ts` 9, `useNightShiftGates.ts` 3)
  AND split clusters (`dev-model.js` 112–220, `importMachine.ts` bands)
  both present, per the fixture spec.
- **Arms:** A = per-cluster baseline (product path, `--no-enrichment`,
  subprocess via the real CLI); B = per-cluster + AST enrichment (isolation
  arm, same 64 clusters, in-process `hunk_state` incl. `ast_context`);
  C = per-file-batched + the SAME enrichment (treatment arm: brief's
  `{"file", "units", "contexts"}` object state, dedup'd `contexts`, per-unit
  `u<N>_*` triples with backticked-path addressing per D8, DELETION_
  QUESTIONS variant for deletion rubrics, 24-unit batch cap — largest file
  is 34 units → 2 calls).
- **Calibration first:** A1 vs A2/A3 (24 paired clusters, all of #47
  + #44 + #45 whole-file runs): mean |Δsev| 0.042, report-flip rate
  **0.000**. The fixture's own noise floor is essentially zero, so the
  treatment deltas below are signal, not noise.

## Criteria table (all must pass; none do)

| Criterion | Bar | Measured | Result |
|---|---|---|---|
| Gate-flip rate (cluster level) | ≤5% and ≤ calibration + margin | **17.2%** (33/192; calibration 0.0%) | **FAIL** |
| Verdict-level flip rate | 0 across fixture PRs | **3/3 flips on #43** (B Changes-requested → C Approved every repeat) | **FAIL** |
| Signed bias Δsev | \|mean\| ≤ 0.05 AND sign test p>0.05 (beat S1′ −0.55 prior) | **−0.301** mean (sd 0.335), 47 pos / 144 neg, sign-p ≈ **1.2e-12** | **FAIL** (shift smaller than S1′'s −0.55 but far from zero and overwhelmingly one-directional) |
| Δis_real near 0.50 (code rubric) | \|mean\| small, p>0.05 | **−0.113** mean, 5 pos / 153 neg, sign-p ≈ **4.4e-39** | **FAIL** — systematic push BELOW the report threshold |
| Δis_real near 0.70 (deletion rubric) | \|mean\| small, p>0.05 | −0.007 mean, 15/12 split, sign-p ≈ **0.70** | PASS (only criterion that passes) |
| Defect-positive recall | ≥ per-cluster | Non-band: golden hit both arms. Band spans: 3/3 both arms. **BUT** the verdict flip (above) means the batched arm misses the defect-positive PR's verdict-level signal | **FAIL** (verdict-level; cluster-span coverage itself is equal) |

## The mechanism (same as S1′, now at file scale on real PRs)

Batching 2–34 clusters into one call systematically *softens* every
judgment: 75% of clusters score lower (mean −0.30 severity, −0.11
is_real). The damage concentrates exactly where it matters: on #43, the
per-cluster arms report the import-race majors (verdict Changes-requested,
correctly — the head is post-fix but the fixture's non-band anchors at
:73/:82 are what the majors look like); the batched arm's softened scores
fall below the report gate and the verdict flips to Approved. A transport
that cannot hold a defect-positive verdict on its own fixture fails G-B by
definition (r3-M3/#45 failure shape: correlated within-call errors feeding
the same-file corroboration gate).

 bm-FP census on clean heads (mean of 3): A 0/0/1/0, B 0.3/0/0.7/0,
C 0/0/0/0 — batching also suppresses #46's accepted band-window FP, but
that "improvement" is the same under-reporting mechanism, not a quality
win.

## Disposition (plan step 4)

- **Per-file judgment batching remains RETIRED.** The honest fallback
  stands: per-cluster transport + AST context enrichment (already shipped
  in Task 6 and validated by Task 8's enrichment-off arm).
- Directive 1 ("more than one judgement per batched query") survives in
  the digest call (`judge_pr_level`, always one call) and as the documented
  escape hatch only — same ruling shape the brief pre-registered for a G-B
  failure.
- No follow-up plan, no transport code, no further gates: D5's default
  outcome is now measured evidence, not assumption.
- Laya (D6) stays per-cluster a fortiori.

## Cost

64 clusters × 2 in-process arms × 3 repeats + 5×3 subprocess runs ≈ **64
live jev calls** (B) + **9 batched calls** (C, 2-call batches on #43) +
15 CLI-run call sets (A, already counted in the Task 8 ledger era shape).
Wall clock ≈ 8 min. Harness and raw JSON stay in /tmp (out-of-tree,
r2-B1); this doc + the ledger lines (`gb9-A<rep>-pr<NN>` labels) are the
record.

## Notes for future readers

- The per-file arm's verdict suppression reproduced across all 3 repeats
  with zero variance — this is a property of the transport, not noise.
- If anyone revisits batching after a model upgrade: re-run THIS gate
  (harness recipe above) before reopening D5; the criteria table is the
  pre-registered bar.
