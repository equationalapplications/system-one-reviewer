# Opus r1 dispositions — SOR v0.9 spec rev 4 (review: sor-v09-opus-r1-review.md)

Adjudication by Tessera (controller), 2026-10-19. Verdict was BLOCKED; the two
blockers were resolved BEFORE rev 5 (V0 executed and failed the gate; root cause
found and fixed) — both stand CONFIRMED. All M/minor items below adjudicated and
fixed in rev 5 unless noted.

- **B1 CONFIRMED (fixed in rev 4 + V0).** Probe measured verdict prose; V0
  structured-row re-probe moved nothing past the gate. Rev 4 rewrote Problem 5;
  E3/E4 gated.
- **B2 CONFIRMED (fixed in rev 4 §3 + rev 5 E5).** Rev-4's "never consulted" claim
  was wrong (19 clusters → 46 units proves cutters ran); root cause = wheels
  missing from the binary's own interpreter; installed and measured (168 units).
- **M1 REAL.** E6 gets its own severity criteria + gate; pilot pins BOTH numbers
  (N4 severity 0.38–0.57 would fail compose's sev≥1 regardless of threshold).
- **M2 REAL.** B2 settled as anchor(E2)+recognition(P3) — both needed (§2a
  rewritten). V2 gains the attainable-ceiling report next to the exit bar; V0
  extension adds site-level states for 789/791.
- **M3 REAL.** Anchor rule defined: fact spans never move anchors; anchors are
  cutter-produced; V2 pre-flight (model-off reachability check: every golden line
  within ±1 of an anchor) added; unanchorable defects → coverage note, never a
  finding.
- **M4 REAL.** E2: leaf-most non-overlapping site selection; per-declaration
  major grouping (enclosing top-level declaration, not cluster); V7 model-off
  site-count census gate added (measured 8.8× baseline kills the old 3–6×
  envelope); banner denominator redefined.
- **M5 REAL.** E1: `hunk` value added for uncut clusters; mixed-run rule =
  highest-precedence path used + per-unit `cut` field; sweep gates check
  packaging_version AND wire_format; historical stamps mapped lossily and
  documented.
- **M6 REAL.** V3(c) prereq: `parent_declaration` id on judged entries + `rewrap`
  carries it; replay = new build's findings under flat vs per-declaration compose.
- **M7 REAL.** Self-check moved into every run (argparse `--version` exits before
  main); stamps availability + wheel versions per ledger record.
- **m1 REAL.** Probe docstring corrected (hand-built states, installed binary);
  V2-priming uses `hunk_state()`.
- **m2 REAL.** §3 rewritten to cluster/unit wording; banner denominator defined
  in E2.
- **m3 REAL.** E6 routing: `spec`/`specs` directory components dropped; basename
  rules + tests/test/__tests__ dirs only; deletion-only precedence stated;
  corroboration-pool exclusion stated; V6 ground truth = manually curated list.
- **m4 REAL.** V1 gains a TS fixture leg.
- **m5 REAL.** `docs/benchmarks/corpus-manifest.md` created; remaining TODO-PINs
  committed before their gates run.
- **m6 REAL.** E4 import-resolver scope stated (relative + index.ts, repo-only,
  fail-closed).
- **m7 REAL.** Scope filename corrected to `system_one_reviewer.py`.
- **RESEARCH_REQUESTS 1–3: ANSWERED.** (1) custody-envelope.ts is a new file in
  the range (all lines `+`), consistent with cutting having engaged; ledger
  stamps were identical by the stamp's single-input design (E1 fixes). (2)
  tree_sitter + tree_sitter_typescript NOW import inside the binary's
  interpreter (hermes venv, python 3.14) — they did not at r1 review time; this
  was the confirmed root cause. (3) Detector-firing checks on the d70d225
  pre-image are moot for v0.9 (E4 gated after V0) but preserved in the E4 spec
  text for the gated future work.
