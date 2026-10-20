# SOR v0.9 Implementation Plan (E1 + E2 + E5 + telemetry)

Date: 2026-10-19  
Spec: `docs/superpowers/specs/2026-10-19-sor-v09-structural-facts-design.md` (rev 12)  
Branch: `impl/v09-structural-facts`  
Fork Resolution: **A + C combined** (anchor release + triage re-scope)

## Overview

This plan implements the v0.9 specification, a **frozen** design gated by 10 Fable conditions. Work is autonomous; each section is completed in foreground with commits as progress is made. The spec is binding — no redesign.

## Deliverables Summary

1. **E1 — honest stamp** (Problem 4 fix): `record_version` and `packaging_version` distinct
2. **E2 — decision-site cutting** (B2/M2 fix): site-level anchors per the spec
3. **E5 — wheels packaging**: tree_sitter wheels in binary's interpreter with self-check
4. **Telemetry — V7 census**: initial size floor, each tightening, median site size, wall time
5. **Triage re-scope**: NO "Approved"/"Changes requested" verdicts; findings list + banner only
6. **Tests covering V1/V2/V3/V5 gates** with noise-aware V1 and structured status field
7. **Documentation updates**: INTENT.md status lines, ROADMAP "six" → "seven" fix, corpus manifest pins

## Implementation Units

### Unit 1: Foundational Changes (Commits 1–2)

#### 1a. Code structure audit (no-op)
- Read existing code sections named in spec (compose line 2711, verdict field, jitter, packaging stamp)
- Identify change points for E1, E2, E5 integration
- Verify tree-sitter import structure

#### 1b. PACKAGING_VERSION bump (Commit 1)
- Change `PACKAGING_VERSION = "v08-ast"` → `PACKAGING_VERSION = "v09"`
- Add DEFAULT_PACKAGING_VERSION constant (matches PACKAGING_VERSION)
- Update RUBRIC_VERSIONS tracking in test_package.py if it exists

### Unit 2: E1 — Honest Wire-Format Stamp (Commits 3–4)

#### 2a. Wire-format enum and stamping (Commit 2)
- Define wire_format enum: `hunk`, `line-window`, `ast-units`, `ts-units`, `sites`
  - These map to current cutter paths and future E2 decision-site output
- Implement `get_max_cut_type(units)` → returns highest-precedence cut actually used
  - Precedence: `sites` > `ts-units` > `ast-units` > `line-window` > `hunk`
- Each unit already carries its cut source; compose max from all units
- Add per-unit `cut` field to reported findings (maps to actual cutter that produced it)

#### 2b. Ledger and JSON meta updates (Commit 3)
- Update metrics ledger record to include:
  - `record_version`: PACKAGING_VERSION (constant per release)
  - `packaging_version`: PACKAGING_VERSION (same constant)
  - `wire_format`: result of get_max_cut_type(units)
- Update --out JSON meta block to include same three fields
- Verify sweep gates check BOTH packaging_version AND wire_format
- Add per-unit `cut` field to --out findings list

### Unit 3: E2 — Decision-Site Cutting (Commit 4–5)

#### 3a. Site cutter skeleton (Commit 4)
- Add `def cut_sites_for_cluster(diff_text, file_lang, cluster_range)` → list of site objects
  - Each site: {start_line, end_line, kind, parent_cluster}
  - kind: `property_assignment`, `call_argument`, `conditional`, `sibling_const`
  - Return empty list if tree-sitter unavailable (fallback to line-window per E5 spec)
  - Return empty list if file_lang not in {ts, js, python} (per OQ1/B1)
- Add `def get_site_size_floor(kind)` → min lines for pure-data sites
  - property_assignment with no function calls: floor ≥ 3 lines
  - Others: no floor (spec E2)
- Integrate into cutting pipeline: after top-level clustering, before line-window fallback
  - Call site cutter if available
  - Validate no-op guard: if site set == changed set, judge whole per E2
  - Never subdivide a site below its size floor

#### 3b. per-declaration majors counting (Commit 5)
- In compose() function: when counting majors, group by `parent_declaration` (function/class/const)
  - Two sites in one function cannot trip the two-major rule twice
  - This changes verdicts vs flat count (measured in V3(c))
  - Add `parent_declaration` to state/unit structure

#### 3c. Coverage and max-hunks interaction (Commit 5)
- Truncation MOVES AHEAD OF EXPANSION (spec E2 behavior change):
  - Old: ceiling caps post-expansion `kept` units
  - New: ceiling caps TOP-LEVEL CLUSTERS before expansion
  - Once a cluster is admitted, its sites are never truncated
- Update incomplete-review banner denominator: total top-level clusters
- Write `skipped[].reason = max-hunks>ceiling` ONE PER DROPPED CLUSTER
- Verify banner reads e.g. "40/50" (40 clusters judged, 50 total)

### Unit 4: E5 — Wheels Packaging (Commit 6)

#### 4a. Tree-sitter self-check (Commit 6)
- Implement `def check_cutters_available()` → {language: available, version, wheels}
  - For each language (ts, python):
    - Try to import tree_sitter and language wheels
    - Parse a known snippet; record success/failure and pinned versions
    - Store wheel versions (e.g., "tree_sitter_typescript==0.20.1")
  - Return structured availability dict
- Call check_cutters_available() at startup (before packaging) and on --version
- HARD PRECONDITION (spec E5): if V2/V5 measurement run and TS cutting NOT AVAILABLE, abort
  - Spec: "a silent window fallback must be impossible on a measurement run"
  - Implement via `--force-measurement` flag requiring wheels, or early abort check
- Stamp per-cutter availability + versions in each ledger record

#### 4b. Version flag output (Commit 6)
- --version prints cutter availability table, then exits (before main())
- Table format: language | available (yes/no) | wheel version | timestamp
- Same info stamped into every ledger record for audit

### Unit 5: Triage Re-Scope — No Verdict Output (Commit 7)

#### 5a. Remove verdict field from compose() (Commit 7)
- Delete the line: `verdict = "Changes requested" if (blockers or len(majors) >= 2) else "Approved"`
- compose() now returns: (reported, jitter, status) where status replaces verdict
  - status values: `ok`, `fail-open`, `incomplete review` (per spec condition 10)
  - `fail-open` when provider unreachable → Unavailable banner
  - `incomplete review` when max-hunks ceiling hit → incomplete-review banner
  - `ok` for normal runs

#### 5b. Update report rendering (Commit 7)
- Remove any output containing "Approved" or "Changes requested"
- Findings list stays (ranked, max 5 per ROADMAP standing rule)
- Coverage banner stays (reflects honest judgment)
- Fail-open "Unavailable" banner stays (it's an honest-status signal, not verdict authority)
- Render findings as "ranked triage pointers" (new terminology)

#### 5c. Test for verdict-field replacement (Commit 7)
- Condition 1: Add test asserting no run output contains "Approved" or "Changes requested"
- Condition 2: Add test asserting "Unavailable" banner renders when needed
- Condition 2: Add test asserting incomplete-review banner renders when needed

### Unit 6: Telemetry — V7 Census (Commit 8)

#### 6a. Site-count census (Commit 8)
- New function: `def run_site_census(repo_path, range_spec)` → census report
  - Runs site cutter model-off over golden range and 47-PR corpus
  - For each range: count initial clusters, then count sites after expansion
  - Calculate expansion ratio per cluster
  - Report: median expansion ratio, site count percentiles, min/max
- Gate (spec V7): median expansion ≤ 5× (per Kurt's confirmation in spec)
- Size floor tightening iteration: if median > 5×, tighten floor, re-run
  - Forbidden: tightening that drives median site size > 120 lines (would undo anchor fix)
  - At most TWO tightenings allowed
- If still fails after 2 tightenings: E2 does NOT ship; return envelope decision to Kurt

#### 6b. Projected wall time (Commit 8)
- Add to census report: "projected wall time next to call multiple"
  - With site expansion 8.8× (measured) and 0.80 gate filtering, estimate model calls
  - Compare to current (46-unit default run with window fallback)
  - Surfaces cost impact of site cutting

### Unit 7: Status Field Carrier (Commit 9)

#### 7a. Structured status in outputs (Commit 9)
- Add `status` field to:
  - --out JSON meta block: {status: "ok|fail-open|incomplete review", ...}
  - Metrics ledger record: `"status": "ok"` alongside other fields
  - Coverage banner: displays status
- No consumer treats missing status as a pass (spec condition 10)
- Update AGENTS.md coverage rule and any verdict-checking code to read status field

#### 7b. Test for status carrier (Commit 9)
- Test: status field present in all outputs
- Test: status field has only valid values
- Test: coverage banner and ledger both carry matching status

### Unit 8: Test Suite for Gate Conditions (Commits 10–13)

#### 8a. V1 Noise-Aware Test (Commit 10)
- Baseline fixture run TWICE (e.g., fixture at 0.50 gate twice)
- Leg (a): per-unit is_real score at LEGACY 0.50 telemetry level
  - Assert: each fixture defect's score ≥ baseline value minus noise band (V3(a))
  - Noise band: observed delta between two baseline runs
- Leg (b): SURFACED set at 0.80 gate unchanged vs baseline
  - Compare findings where is_real ≥ 0.80 (new build vs baseline)
  - Assert: identical sets (no new pointers, none lost)
  - Jitter counts (units within noise band of 0.80 gate) reported alongside
- V1 test: baseline-versus-baseline rerun passing both legs (proves gate cannot fail on noise alone)
- TS leg: second fixture with planted TS defects at known lines (V1 not green on Python alone)

#### 8b. V2 Golden Recall Test (Commit 11)
- Pre-flight model-off: run site cutter over golden range, confirm every golden line
  - Has some unit anchor within ±1 (or absence-type defect documents anchoring rule)
  - Fact `span` does NOT move unit anchor in v0.9; cutter-produced anchors only
- PRE-FLIGHT MODEL-ON (spec V2 2a): B2/M2 site units (lines 789/791) judged 3× each at 0.80 gate
  - Measure whether site anchors land within ±1 AND cross gate WITHOUT domain facts
- TRIAGE CHECK: output contains no "Approved"/"Changes requested" anywhere
- Every finding is ranked triage pointer; "surfaced" means is_real ≥ 0.80
- Cite E1 wire_format + per-unit cut field in every claim
- Exit contract: defect recovered = anchored within ±1 of site unit (not verdict crossing)
- Honest fallback: 0/8 golden recall with anchor mechanism in place

#### 8c. V3 Negative Arm Precision Test (Commit 12)
- Baseline build runs TWICE on five defect-free negative heads + three reproof ranges
  - reproof:A6fix, reproof:ct-61cluster, reproof:wf59-fixdelta
  - Observed verdict/findings delta (is_real ≥ 0.80) = noise band
- New build findings run twice:
  - (1) flat compose() (existing)
  - (2) per-declaration compose() (E2 change)
  - Flips caused SOLELY by per-declaration rule counted and reported separately (V3(c))
- Assert: no reported-findings increase beyond noise band
- Prerequisite: judged entries have parent_declaration id and rewrap carries it forward
  - Old v08 ledgers have neither; cannot replay v08 for this comparison

#### 8d. V5 Stamp Test (Commit 13)
- Run same range with --force-window-cut and site-cut variants
- Assert: wire_format values differ (both in --out meta and ledger)
  - Window-only: `line-window`
  - Site-cut: `sites` or mixed
- Assert: per-unit `cut` fields agree with actual cut path used
- Fixes Problem 4 (distinguishing wheels-present from window-fallback)

### Unit 9: Documentation Updates (Commit 14)

#### 9a. INTENT.md Status Lines (Commit 14)
- Rule 1: Update to "Built." (nothing changes; already satisfies envelope)
- Rule 2: Update to "Partly built → Built" (E2 site cutting + wheels added)
- Rule 3: Update to "Built." (verdict output removed; findings + banner is output contract)
- Rule 4: Update to "Built." (0.80 gate adopted and implemented)
- Rule 7: Update to "Built." (honest stamps: E1 wire_format and status fields)
- Rule 8: Update to "Built." (V1/V2/V3/V5 gates measured; receipts in docs/benchmarks/)

#### 9b. ROADMAP "six" → "seven" fix (Commit 14)
- Line 26: change "six Oct 15–19 window runs" → "seven Oct 15–19 fix-window runs"
- Reason: wording fix from spec rev 12 (the actual October count was 7, not 6)

#### 9c. Corpus Manifest Pins (Commit 14)
- Pin five negative-head SHAs (from run-1 memo, pre-V3 run)
  - Candidates: doc-only and deps-only ranges from Oct 15–19 ledger
  - Section: Negative heads (V3 precision arm)
- Pin TS fixture filename once created (section: Fixture (v0.2-era))
- Verify all three reproof ranges listed correctly

### Unit 10: Test Suite Driver and Execution (Commit 15)

#### 10a. Structured test runner
- Create or update test_gates_v09.py with V1/V2/V3/V5 gate tests
- Test harness: parametrized per-gate execution with clear pass/fail reporting
- Fixture management: load golden TSV, negative heads, reproof ranges
- Output format: JSON or tabular (for PR description numbers)

#### 10b. Full suite execution
- Run all V1/V2/V3/V5 tests in foreground
- Report: pass/fail per gate, condition checklist (1–10), git log of branch
- Condition satisfaction matrix: which files/lines anchor each condition

## Fable Gate Conditions Checklist

- [ ] 1. Tests assert run output NEVER contains "Approved" or "Changes requested"
- [ ] 2. Deletion rubric threshold (0.70) STATED in code/docs; sweep receipt in PR if it moves
- [ ] 3. Ranking key for triage + 5-findings cap implemented and tested
- [ ] 4. INTENT rules 1,2,3,4,7,8 status lines updated in INTENT.md THIS BRANCH
- [ ] 5. Corpus manifest pins five negative-head SHAs, reproof ranges, TS fixture BEFORE V3/V1
- [ ] 6. V7 census reports: initial size floor, each tightening, median site size, projected wall time
- [ ] 7. Jitter counts at 0.80 gate in V2 and V3 reports
- [ ] 8. Three evidence wording fixes in spec (DONE rev 12); ROADMAP "seven" fix; list-indentation nits
- [ ] 9. V1 noise-aware (baseline run twice, leg (a) ≥baseline minus band, leg (b) jitter zone)
- [ ] 10. Honest-status signals: --out meta and ledger carry status field {ok, fail-open, incomplete review}

## Execution Flow

1. Write this plan (✓ DONE)
2. **Unit 1**: Code audit + PACKAGING_VERSION bump
3. **Unit 2**: E1 wire-format and stamping
4. **Unit 3**: E2 site cutting + per-declaration majors + max-hunks
5. **Unit 4**: E5 wheels self-check and --version
6. **Unit 5**: Remove verdict field + update rendering
7. **Unit 6**: V7 census and telemetry
8. **Unit 7**: Status field carrier and tests
9. **Unit 8**: V1/V2/V3/V5 gate tests (4 commits)
10. **Unit 9**: INTENT.md, ROADMAP, corpus manifest updates
11. **Unit 10**: Test suite driver and full execution
12. **Final report**: git log, condition checklist, test results

## Risk and Mitigation

- **Risk**: E2 site cutting may exceed envelope (measured 8.8× top-level; sites add more)
  - **Mitigation**: V7 census gate first; gates to Kurt if envelope tightening needed
- **Risk**: Per-declaration majors change verdicts; V3 must catch flips
  - **Mitigation**: V3(c) explicitly measures per-declaration effect
- **Risk**: Wheels unavailable on measurement runs
  - **Mitigation**: E5 HARD PRECONDITION: abort if TS wheels not found on --golden/V2/V5 run
- **Risk**: Test fixtures must match spec exactly (TS fixture, negative heads)
  - **Mitigation**: Corpus manifest pins all fixtures BEFORE gates run

## Budget and Constraints

- $10 USD budget (current: ~$0.13)
- 200 turns (current: ~20 used)
- All commands foreground; ≤8 minutes each
- All work commits to impl/v09-structural-facts branch
- No push, no PR creation, no background tasks
- Partial progress saved in commits at each unit

## Next Step

Proceed to Unit 1: Code structure audit and PACKAGING_VERSION bump.
