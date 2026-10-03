# Task 8 gate results — v08-ast (complete: G-A, G-C, G-D three arms, band check, re-sweep, corpus replay)

**Date:** 2026-10-02/03 (runs 2026-10-02T22:49 – 2026-10-03T08:50 UTC) ·
provider `jev` (live) · builds: v08 = `impl/ast-units` @ `5158f6c`
(`v08-ast`, incl. option-2 band engagement), control = `main` @ `394ea0a`
(`v03b`) · ledgers: labels `task8-*` in `~/.local/state/jev-review/metrics.jsonl`,
corpus config `v08-gates` in `corpus/work/runs/`. Suite at halt-of-work:
**363 passed, 1 skipped** (2 new skips absent; band tests added under
`tests/test_ast_units.py`).

**Supersedes** the interim STOP doc (this file's first revision @ `1a9d0ce`):
Kurt APPROVED option 2 on the missed-anchor data; the ruling was implemented
(`BAND_ENGAGE_LINES = 120`, TDD, commit `5158f6c`) and ALL gates re-run to
completion.

## 1. Option-2 ruling + implementation (the halt resolution)

The first v08 band run (build `8395b4f`) showed `importMachine.ts` (209-line
new file, ~2.6k est tokens) judged WHOLE (token gate never engages) and
reported 2-of-6 — band goldens missed on span-containment. Kurt approved
option 2. Implementation: a SECOND engagement test — a unit whose span
exceeds `BAND_ENGAGE_LINES = 120` while under the token cap routes through
the SAME cutter order (top-level AST → tree-sitter → line windows →
halving); band units can never become `unsplittable>cap` leaves (under-cap
content is legal to send; un-splittable band units are judged whole). The
token gate (r1-M4) stays primary; band is additive. Static proof on the real
cluster: splits 1–44 / 45–164 / 165–209; golden :16 in window 1, :119 in
window 2. Tests: 5 new (`test_band_*`), suite 363 green.

## 2. G-A fixture stability — PASS

Fixtures rebuilt at committed SHAs (`positive=3346ca1…`, `negative=5ca6f013…`).
3× positive + 3× negative on v08 (labels `task8-ga-pos/neg-1..3`):

- Positive: **Changes requested 3/3, TP 5/5, precision 1.00, recall 1.00,
  F1 1.00 on every run** (golden eval in each `--out`). The v03b-era
  `return None` FP_pos is GONE on v08 (anchor set now matches the golden
  exactly).
- Negative: **Approved 3/3, 0 blocker/major, 0 minor, 0 other-FP**; only
  skip = README docs-triage (deliberate).
- Stability bar (2-of-3 exact): **3-of-3** both fixtures. Zero `too_large`
  skips anywhere. `n_dropped = n_unjudged = 0` everywhere.

## 3. Threshold re-sweep on v08 — PASS (KEEP 0.50 / 0.70)

`scripts/sweep-thresholds.py` over the 6 v08 fixture runs: candidate
0.50 (tied 0.45–0.60), rule 1 FAIL = no candidate beats shipped, rule 2
PASS — **decision KEEP 0.50**; curve flat 1.00 min-F1 from 0.45–0.60, TP
holds 5/5 to 0.60. Deletion knob via field-mode on the v08 CJ clean runs:
**0 deletion FPs at shipped 0.70 → KEEP 0.70** (code-rubric FPs at pinned
0.50 are CODE-threshold pressure, noted, not this knob). Both calibrated
values HOLD on the v08 state distribution (r1-M1 resolved: no STOP).

## 4. G-C — 5 clean CJ heads × 3 on v08: FAIL on #46, pre-existing on #43

bm-FP = blocker+major FPs (eval_negative) per run:

| PR | v08 verdicts (3 runs) | findings | bm-FP | control (v03b, live) verdicts | findings | bm-FP |
|----|----|----|----|----|----|----|
| #43 | Changes requested ×3 | 10/11/11 | 6/7/8 | Changes requested (incomplete) ×3 | 11/11/11 | 7/8/8 |
| #44 | Approved ×3 | 0/0/1 | 0 | Approved ×3 | 0/0/1 | 0 |
| #45 | Approved ×3 | 0 | 0 | Approved ×3 | 0 | 0 |
| #46 | **Changes requested ×2, Approved ×1** | 3/3/3 | **2/1/2** | Approved ×3 | 2/2/2 | 1/0/1 |
| #47 | Approved ×3 | 0 | 0 | Approved ×3 | 0 | 0 |

- **#43 over-reporting is PRE-EXISTING** (same shape in the 2026-09-28 v03b
  field proof: 11 findings, Changes requested — documented caveat there) and
  UNCHANGED on v08 (findings-Jaccard vs control 0.97 mean). Not a v08
  regression; still a real G-C failure on the ≤1-bm bar — same as the
  reference era.
- **#46 IS a v08-caused regression:** the 220-line `scripts/dev-model.js`
  cluster (1–220) was `hunk>120`-SKIPPED by the control (never judged); v08's
  band engagement splits it (window 112–220 judged) and the model reports
  `scripts/dev-model.js:112-220` sev 1.50 → an EXTRA bm-FP on a defect-free
  head, flipping the verdict 2-of-3. This is exactly the cost G-C exists to
  surface (plan step 3: "the AST-split machinery turns previously-skipped
  files into findings on CLEAN heads; this is where that would bite").

**G-C disposition: FAIL** — #46 fails the ≤1-bm-major bar on v08 (2/1/2 vs
control 1/0/1). Per plan step 6 this is a gate failure → not landable as-is.

## 5. G-D — three arms, complete; agreement vs control

Same samples, 3 repeats, all live, same day. Exclusions (r8-m3): the two
explicit corpus monsters (ct#232@final write.rs, clanker#592@final) hit the
`--max-hunks 40` ceiling in ALL arms (v08 wr dropped 8, cl dropped 237; ctrl
wr analyzed 37 without ceiling, cl dropped 218) → **excluded from
comparison; exclusion differential reported**: wr v08 drops 8 vs ctrl 0
(v08 splits write.rs into more units → ceiling bites earlier); cl
ceiling-drops on both arms (237 vs 218).

| PR | findings-Jaccard (mean of 3 pairs) | verdict agreement |
|----|----|----|
| #43 | 0.97 | 3/3 (both arms Changes requested) |
| #44 | 1.00 | 3/3 |
| #45 | 1.00 | 3/3 |
| #46 | 0.67 | 1/3 (**the G-C #46 regression**) |
| #47 | 1.00 | 3/3 |

Enrichment-off arm (`--no-enrichment`, 15 runs): verdicts/findings match the
enriched v08 arm on every sample (#43 10-11 bm 6-8; #44-47 identical shapes;
wr/cl same incomplete-verdict shapes) — **enrichment's isolated effect ≈ 0
on this sample set** (all-TS/JS/Rust set; the py-ast path never engaged, all
`enrichment: none` stamps everywhere including enriched runs — the tree-sitter
symbol table produced no enclosing-symbol context on these files).

## 6. G-D band check (defect-positive, option-2 build) — geometry fixed, scoring miss remains

v08 band arm (`task8-gd-v08b-band-1..3`, range `67262aa...11be74c`, live ×3)
vs control (`task8-gd-ctrl-band-1..3`):

- **Control (v03b):** importMachine.ts SKIPPED `hunk>120` in 3/3
  (incomplete verdict 31-of-32) — band recall UNMEASURED by construction.
- **v08 + option 2:** the file splits into 3 windows, every window judged,
  in 3/3 runs (32→34 analyzed). **Geometric coverage: 6/6** — golden :16
  inside window 1–44, golden :119 inside window 45–164, each with its own
  anchor, on every run. **Span-containment HITS: 0/6** — the windows are
  judged but NOT REPORTED (window `is_real` 0.24–0.37, all below the 0.50
  gate; deterministic across repeats, spread ≤0.03).
- Interpretation (honest): option 2 FIXED the geometry problem the halt was
  about — band content is now judged with real anchors instead of skipped or
  whole-cluster-anchored. What remains is a MODEL-SCORING result on window
  content (the two defect sites score ~0.3 in their windows), not a
  transport/coverage artifact. Control cannot arbitrate (skips the file).
  The plan's strict criterion (reported AND covers) still reads MISS — the
  band check does NOT pass; the failure class changed from
  coverage/geometry (halted on) to scoring.

## 7. Corpus replay (36 samples × r1, config `v08-gates`) — G-A PASS, census recorded

- **Zero `hunk>`-prefix skips anywhere** (the old line gate is gone from jev
  runs). Skip census: 1481 `max-hunks>ceiling` (the run-level 40-unit
  ceiling, first-come order, explicit entries — 10 runs; v08 ceiling-drops
  vs v06's silent same-clusters), 400 docs/lockfile (deliberate), 6
  data/snapshot, 1 `whole-file-deleted>cap` (deliberate, r5-M3).
  `n_unjudged = 0` and `n_size_skipped_code = 0` on ALL 36 runs.
- **write.rs (114k chars)**: split into 22 send-legal units (all judged or
  ceiling-managed), run completes without failure — the depth-cap worry is
  exercised and safe.
- Split census vs Task 1b: total judged units 505 (v06 r1) → 583 (v08), ×1.15
  call growth — well under the accepted inflation bound; biggest gain is
  sor#7 (12→33: the tool's own repo, 8 formerly-skipped files now judged).
- Replay score vs v06 reference (same scorer, split all): recall_strict
  0.02 = 0.02; recall_cluster 0.07 vs 0.11; FP/clean **2.00 vs 2.98
  (improved)**; verdict accuracy 0.63 vs 0.70; `truncated` miss bucket = 12
  (new, honest ceiling accounting; v06 had 0 with 27 `not-judged` instead).
  Variance: identical True (v08 r1 single-sample; v06 r1×3 had spread 0.07).

## 8. Cost

87 live gate runs (~1,833 cluster+PR calls, mean ~949 input tokens) + 36
corpus runs (mean ~1,193) ≈ **123 live runs**, consistent with plan's
estimates; no fail-open anywhere.

## 9. Bottom line

- **G-A PASS. Re-sweep PASS (0.50/0.70 hold). G-D transport agreement PASS
  except #46. Band-check GEOMETRY fixed by option 2; scoring miss remains
  (0/6 span-HITs, coverage 6/6). Corpus replay: G-A PASS.**
- **G-C FAIL on #46** (band engagement turns a control-skipped cluster into
  a bm-FP on a clean head, flipping the verdict) — this is option-2's
  accepted-risk materializing, now measured. NOT landable without a Kurt
  decision on #46: options are (a) accept the #46 FP as option-2's cost,
  (b) raise `BAND_ENGAGE_LINES`, (c) gate band engagement on per-window
  content heuristics. Everything else is green.
