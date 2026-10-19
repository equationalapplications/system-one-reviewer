# SOR v0.9 — structural facts + decision-site cutting (structural evidence for the System One classifier)

Date: 2026-10-19 (rev 2 — OQ1/OQ2/OQ3 ruled by Kurt, msg 1561746424616460349:
"1,2,1". OQ1: accept the 3–6× call envelope, no run-level site cap. OQ2: ADD the
test-file question variant (E6 — scope line updated accordingly). OQ3: one release —
stamp fix + wheels + cutting ship together, V5 is the release gate. Awaiting review
ladder.)
Status: DRAFT rev 2 — rulings applied, ladder next
Scope: `system-one-reviewer.py` (+ tests), `examples/`, `docs/benchmarks/`, install
docs. No provider/API changes; NO changes to the generic code-change question set
(HUNK_QUESTIONS); one NEW question variant scoped to test files (E6, per Kurt's OQ2
ruling). Packaging-version bump.
Evidence base (all measured 2026-10-19, artifacts in
`~/Documents/equational-wiki/records/investigations/2026-10-19-sor-quality-fable-step0-guidance/`,
receipts copied in-repo under `examples/` + `docs/benchmarks/`):
8-defect Stage A golden (byte-verified at d70d225), golden runs
(default/full/tsunits: recall 0/8), fact-sensitivity probe (36 calls, 0 failures),
pre-image shape verification, two Tier-4 Fable guidance memos (run 1: quality of
Oct 15–19 reviews; run 2: deterministic-algorithm proposals).

## Problem (measured, not argued)

1. **Wild recall is 0.** On the SynapseTree Stage A gate range (`fb51dd6..d70d225`),
   SOR judged all 46 units and matched **0 of 8** controller-confirmed defects
   (`examples/golden-stageA-8defects.tsv`), at default AND full coverage
   (`docs/benchmarks/2026-10-19-golden-run-*.json`). Recall on this class is
   unmeasured-broken, and the run-1 adjudication ledger shows the same direction in
   the wild: 0/48 findings sustained across the six Oct 15–19 fix-window runs.
2. **The failure is recognition, not coverage.** All 8 defect sites were inside
   judged units (plus-lines of mostly-new files), scoring is_real 0.45–0.50 — BELOW
   the 0.53–0.60 of the run's false positives. No threshold change can fix this.
3. **The TS path is structurally dormant.** All 46 units were 120-line line-window
   fallbacks: (a) `tree_sitter`/`tree_sitter_typescript` wheels are absent from the
   install path, and (b) even with wheels installed (verified 2026-10-19), the
   cutters only engage on oversize/band clusters and return None on single-symbol
   files — this diff gets windows either way (`docs/benchmarks/2026-10-19-golden-run-tsunits.json`).
4. **The ledger cannot tell units from windows.** The packaging stamp reads
   `ast-units-v1` whenever any cutter RAN, so a line-window run and an AST run are
   indistinguishable — defeating the D7 like-for-like comparison contract.
5. **But the model responds to deterministic facts — decisively.** Fact-sensitivity
   probe (`docs/benchmarks/2026-10-19-fact-probe-results.json`, script
   `docs/benchmarks/fact-probe.py`): one hand-written fact row per defect-bearing
   unit, 3 clean vs 3 fact calls each, repeats within ±0.01: **6/6 units moved up;
   5/8 defects crossed the 0.50 is_real gate** — B1+N1 0.31→0.96, B2+M2 0.55→0.95,
   M1 0.45→0.94, M3 0.43→0.88, N3 0.52→0.76; N4 0.31→0.39 stays under. The judge
   is not the bottleneck; the state it sees is.

## Design (E-numbers continue the v0.2 scheme)

- **E1 — honest wire-format stamp (prerequisite).** `packaging_version` /
  per-unit records must distinguish `line-window` / `ast-units` / `ts-units` cutting
  paths. A run whose units are all windows must not stamp AST. Ledger comparability
  is restored before any recall claim is made.
- **E2 — decision-site cutting (P1 substrate).** For TS/JS/Python code-change
  clusters, cut to DECISION SITES, not just top-level units: object-literal property
  assignments, call-argument expressions, conditional expressions, and
  sibling-constant declarations become first-class anchors (tree-sitter node kinds
  for TS/JS; `ast` walk for Python). The 40-unit per-parent ceiling is redefined as
  a SITE ceiling (Fable run-2 memo: expect 3–6× call growth on cluster-heavy ranges —
  still cents at 114 ms/call). Two guards from the memo: majors are counted per
  PARENT unit in compose() so one decision cannot trip the two-major rule twice
  (split-inflation mitigation); pure-data sites (e.g. 60-entry array literals) get a
  size floor. Single-site results no longer fall back to windows (the
  `len(subs)==1 → None` rule is retired for site cuts).
- **E3 — `structural_facts` state key (P2 substrate).** Packaging may attach zero or
  more named fact rows to a unit state; `hunk_state` serializes them into the model
  payload verbatim (same ride-along pattern as `references_remaining` and
  `ast_context`). Facts are EVIDENCE, never verdicts: they never gate, never
  compose, and are always attributable in the report (`facts: [...]` per finding).
- **E4 — detector library v1 (tree-sitter query DSL, domain-free).** Five detectors,
  each emitting ≤N bounded fact rows per unit: (1) branch-name polarity — condition
  identifier tokens vs branch constructor tokens (M3 class); (2) writer/reader field
  symmetry — fields written into a typed object never read by the same-type consumer
  one import hop away (N3); (3) literal-type discriminator never compared (N3, second
  angle); (4) duplicate literal across sibling exported constants bound to different
  construct instances (N1); (5) placeholder-test — typeof/toBeDefined-only
  assertions with no call into a subject (N4). Each detector ships with a corpus
  false-fire screen (V4) and is dropped, not tuned, if it carries no signal.
- **E5 — dependency packaging.** `tree_sitter` + `tree_sitter_typescript` wheels join
  the supported-install path (README + install check in `--version`); the lazy
  import seam and CI-without-wheels behavior stay exactly as ratified 2026-10-02.

- **E6 — test-file question variant (Kurt, OQ2 ruling).** Test-file units get a
  question set adapted to test-quality instead of production-bug scoring: the
  `severity` criteria stay, `is_real_issue` becomes "does this test fail to actually
  test anything?" (placeholder/import-justifying tests, assertions on imports,
  tests that cannot fail), and `category` gains no new values. Applies to units
  whose file lives under a test directory or matches the repo's test-name
  conventions. Target: the N4 class (probe: 0.31→0.39 under the generic set)
  crosses the 0.50 gate under the test variant, with NO is_real increase on
  production-code units (they never see the variant).

## Validation protocol (exit contract — every gate measured, none argued)

- **V1 fixture regression:** the saturated fixture golden stays 5/5 with precision
  1.0 under site-level cutting (run-2 missing experiment #5).
- **V2 golden recall:** 8-defect Stage A golden rerun on the P1+P2 build.
  **Exit ≥ 4/8** (M3, N3, N1, N4 are the P2-covered classes); stretch 6–7/8 if
  site-level anchors localize B2/M2 past the gate. With E6 active, N4-class sites
  are additionally judged under the test variant — target: crossing the gate there
  too. Any recall claim cites the E1-stamped cutting path per unit.
- **V3 negative arm (precision):** the five defect-free negative heads and the three
  `reproof:` ranges (A6fix, ct-61cluster, wf59-fixdelta) must show NO increase in
  reported findings per run and no verdict flip beyond the calibration run's own
  noise (the G-B criterion).
- **V4 detector screens (model off):** every E4 detector runs over the 47-PR corpus
  pinned heads; fire rate on clean heads ≥ fire rate on positive heads → detector
  dropped before any model spend.
- **V5 stamp test:** a window-only run and a unit-cut run of the same range must
  carry distinguishable stamps (fixes Problem 4; run-2 missing experiment #2).

## Non-goals

- **P3 domain fact lexicon (B1/B2/M1 classes) is NOT in v0.9.** The probe proves the
  model USES domain facts (those three classes moved 0.45–0.55 → 0.94–0.96), but the
  facts must be GENERATED deterministically, and that requires a curated,
  source-governed AWS lexicon. Per the Fable advisory: hold behind a governance rule
  (every row carries a source URL + date; unsourced rows never ship); revisit as
  v0.10 once v0.9 measures how much P1+P2 alone recover. Design notes for it stay in
  the run-2 memo.
- P4 contrastive choice questions: fixture-experiment only, no production wiring.
- No threshold changes; the generic code-change question set is untouched (the E6
  test-file variant is a separate set scoped to test files); no new providers.

## Open questions — ALL RULED (Kurt, msg 1561746424616460349, "1,2,1")

- **OQ1 — RULED (1):** accept the 3–6× call envelope; no run-level site cap.
- **OQ2 — RULED (2):** test-file question variant added as E6 (scope + Non-goals
  updated accordingly).
- **OQ3 — RULED (1):** one release — E1 stamp + E5 wheels + E2/E3/E4 cutting ship
  together; V5 is the release gate.
