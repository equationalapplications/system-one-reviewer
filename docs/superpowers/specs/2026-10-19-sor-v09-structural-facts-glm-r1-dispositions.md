# GLM r1 dispositions — SOR v0.9 spec (review: 2026-10-19-sor-v09-structural-facts-glm-r1.md)

Adjudication by Tessera (controller), 2026-10-19. Every finding ruled REAL / PARTIAL / FP
with anchor. 14 REAL, 1 PARTIAL, 0 FP. All REAL fixes land in spec rev 3.

- **B1 REAL.** Verified in binary: the only 40 is `--max-hunks` (run-level, post-expansion
  `kept[:args.max_hunks]`, reason `max-hunks>ceiling`); cutters engage only via
  `_unit_oversize`/`_unit_band` (expand_oversize_units skips all other units). The spec's
  "40-unit per-parent ceiling" premise was wrong (the 40 in source is the enrichment symbol
  cap). Fix in rev 3: site-cut engagement stated explicitly (all code-change clusters);
  `--max-hunks` governs top-level clusters pre-expansion only and site units are EXEMPT
  (per OQ1 ruling "no run-level site cap"); ceiling drops keep the existing
  incomplete-review banner at cluster level.
- **B2 REAL.** compose() counts majors flat (`len(majors) >= 2`); the per-parent guard is
  NEW behavior. V3 re-operationalized: (a) baseline noise band measured by running the
  baseline build TWICE on the negative heads (verdict flip rate = noise); (b) like-for-like
  verdict comparison = replay baseline findings through the new compose(); per-parent-rule
  flips counted and reported separately, never forbidden.
- **M1 REAL.** Ledger numbers as the review lists them (defect-unit is_real 0.30/0.56/0.45/
  0.39/0.48/0.33). §2 rewritten to the three-class taxonomy: anchor failures (B2+M2, unit
  reported but anchor 38 lines off), near-gate (M1 0.45, N3 0.48), deep recognition
  failures (B1+N1 0.30, M3 0.39, N4 0.33). E4 detector priority reordered accordingly.
- **M2 PARTIAL — conclusion REAL, causal claim FP.** Conclusion stands: the receipts cannot
  distinguish cutting paths (stamp has single input) and §3's claimed cause must go. The
  FP part: `ts_units` was never CALLED on those clusters — the engagement rule (B1) skips
  sub-120-line units before any cutter is consulted; wheels ARE importable on this box
  (verified: tree_sitter 0.26.0 parses TS; `ts_units` returns 2 subclusters on
  custody-envelope.ts when invoked). Fix in rev 3: §3 corrected to "cutter never engaged on
  these clusters; receipts cannot distinguish cause — see E1", plus E5 `--version` per-cutter
  self-check written into the ledger.
- **M3 REAL.** DELETION_REAL_THRESHOLD=0.70 precedent confirmed (own-rubric own-threshold).
  The probe measured N4 under the GENERIC question set. Fix: pre-implementation pilot
  (N4 unit, test variant, 3×3) pins `TEST_REAL_THRESHOLD` before V2 runs; compose() routes
  three question sets.
- **M4 REAL.** Routing pinned deterministically: path component in {tests, test, __tests__,
  spec, specs} OR basename `*.test.*` / `*.spec.*` / `*_test.*` / `test_*.*`; documented
  override flag. New V6 gate: routing unit test over the 47-PR corpus full file list —
  zero production-file units routed to the variant.
- **M5 REAL.** E4 detectors emit STRUCTURED rows only: kind enum, identifier strings
  validated `^[A-Za-z_$][A-Za-z0-9_$]*$`, integer line spans, fixed-vocabulary description
  phrases with length caps — no free text derived from the diff. `hunk_state` serializes the
  structured object. V3 sub-gate added: clean negative-head units rerun with a synthetic
  fact force-attached; is_real must stay below the report gate.
- **M6 REAL.** `packaging_version`/`record_version` stay constant per release (v09);
  cutting path rides an extended `wire_format` (line-window / ast-units / ts-units / sites)
  surfaced in BOTH `--out` meta and the ledger, plus a per-unit `cut` field on judged
  entries; `gate_run` like-for-like check compares wire_format.
- **m1 REAL.** Probe crosses: 7 of 8 defects (5 of 6 units) — B1, N1, B2, M2, M1, M3, N3;
  N4 stays under AND its fact severity 0.53 fails compose's sev≥1 report gate. Corrected.
- **m2 REAL.** Repeat spreads: ±0.02 (M1 clean, N3 fact), ±0.04 (N4 fact). Corrected to
  "within ±0.04".
- **m3 REAL.** Default run judged 40 of 46 (max-hunks ceiling); only the full-coverage run
  judged 46. Corrected; V2 rerun config pinned (full coverage, explicit `--max-hunks` per
  B1's exemption rule).
- **m4 REAL.** Exact wheel versions pinned in the install check and stamped into the ledger
  record (grammar determinism).
- **m5 REAL.** `--force-window-cut` flag named in E1 (V5's window-only leg).
- **m6 REAL.** Probe docstring/citation notes hand-built states; V2-priming runs rebuild
  states via `hunk_state()`.
- **m7 REAL.** No-op guard kept for site cuts: site set == changed set → judge whole / leaf
  immediately (no depth-cap recursion).
