# SOR v0.9 — structural facts + decision-site cutting (structural evidence for the System One classifier)

Date: 2026-10-19 (rev 4 — Opus Tier-3 r1 adjudicated: verdict BLOCKED, 2 BLOCKER
confirmed REAL after verification. **V0 gate executed and FAILED**: structured
E3-schema rows without conclusion text do NOT lift Jev past the gate (M3 0.44→0.36,
N4 0.31→0.37; only N3 crossed, from an already-clean 0.51; details below). Root
cause of §3 confirmed and fixed: the cutters DID engage in prior runs; the wheels
were missing from the BINARY'S interpreter (a different python3 than the one
wheels were first tested under); wheels now installed there and the rerun measures
top-level cutting at 46→168 units (8.8×) — EXCEEDING the OQ1 3–6× envelope, which
must be re-ruled. E3/E4 recall premise is dead as specified; the direction fork
goes to Kurt.)
Date rev 3: GLM Tier-2 cycle 1 adjudicated (14 REAL / 1 PARTIAL / 0 FP).
Date rev 2: OQ1/OQ2/OQ3 ruled by Kurt ("1,2,1").
Status: DRAFT rev 4 — DIRECTION FORK, awaiting Kurt's pick (see THE FORK)
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
   SOR matched **0 of 8** controller-confirmed defects
   (`examples/golden-stageA-8defects.tsv`) in BOTH configs: the default run judged
   40 of 46 clusters (6 dropped at the `--max-hunks` ceiling) and the full-coverage
   run judged all 46 (`--max-hunks 500`) — `docs/benchmarks/2026-10-19-golden-run-*.json`.
   The run-1 adjudication ledger shows the same direction in the wild: 0/48 findings
   sustained across the six Oct 15–19 fix-window runs.
2. **The failure splits into three classes — only one is deep non-recognition.**
   Per-ledger defect-unit is_real: B1+N1 0.30, B2+M2 **0.56 (REPORTED — the finding
   anchored at the unit anchor, 38 lines from the golden anchors)**, M1 0.45, M3 0.39,
   N3 0.48, N4 0.33. Taxonomy:
   (a) **anchor failures** — B2+M2: the unit crossed the gate; only anchor placement
   missed (HUNK_QUESTIONS asks no location question, so ±1 golden matching succeeds
   only if the CUTTER anchors within ±1) — fixable by E2 alone;
   (b) **near-gate** — M1 (0.45) and N3 (0.48) miss by 0.05/0.02; a threshold move
   would catch them but floods false positives (clean units at 0.45–0.47 exist), so
   "no threshold change fixes this" holds in conclusion;
   (c) **deep recognition failures** — B1+N1 (0.30), M3 (0.39), N4 (0.33): the actual
   E3/E4/E6 cases.
3. **The TS cutting path never engaged on this range.** All 46 units were 120-line
   line-window fallbacks. Cutters engage ONLY on oversize (>28k-token estimate) or
   band (>120-line) units (`expand_oversize_units`); every cluster here is smaller,
   so no cutter was ever consulted — with or without wheels. The tsunits receipt
   CANNOT distinguish wheels-present from wheels-absent (the stamp's only input is
   the parent-cluster pointer, identical either way) — which is itself the cleanest
   demonstration of Problem 4. Wheels are now installed and `ts_units` is verified
   working when invoked (2 subclusters on custody-envelope.ts).
4. **The ledger cannot tell units from windows.** Both `record_version` and
   `packaging_version` are written from the single constant `PACKAGING_VERSION`, and
   the window fallback stamps the same `wire_format` input as a cut run — the D7
   like-for-like comparison contract is unenforceable on today's outputs.
5. **The model responds to CONCLUSIONS, not to structure — measured both ways.**
   First probe (`docs/benchmarks/2026-10-19-fact-probe-results.json`): hand-written
   prose facts stating the CONCLUSION moved 6/6 units; 7 of 8 defects (5/6 units)
   crossed 0.50. **V0 gate (Opus r1 B1; `docs/benchmarks/2026-10-19-v0-probe-results.json`,
   script `v0-probe.py`): the same units re-probed with rows in the EXACT E3 schema —
   kind enum, identifier, span, count/presence note, ZERO conclusion text — moved
   NOTHING past the gate: M3 0.44→0.36 (DOWN), N4 0.31→0.37 (still under); N3
   0.51→0.60 crossed only from an already-clean start.** Conclusion: Jev uses
   semantic/domain conclusions when a reviewer states them; bare structural
   observations without domain interpretation are inert. SOR's recall gap cannot be
   closed by domain-free structural facts (P2) — the working ingredient is the
   domain-lexicon class (P3), which requires sourced-row governance.
6. **Measured cutting cost exceeds the ruled envelope.** With wheels installed in
   the binary's actual interpreter, top-level cutting on the golden range yields
   46→168 units (8.8× the cluster count) — beyond the OQ1 3–6× ruling, and BEFORE
   decision-site subdivision. The envelope needs a re-rule informed by this number
   and by the size floor's measured reduction.

## THE FORK (Kurt's pick; replaces the E3/E4 recall premise)

The ladder has now measured the mechanism from both ends. What survives:

- **E1 honest stamp + E2 site cutting are untouched and validated as the anchor
  fix** — the B2/M2 class (2/8) is an anchor-placement failure, and site anchors
  fix it with zero facts. This is worth shipping regardless.
- **E4 domain-free structural detectors do not lift recall (V0, measured).** As
  recall levers they are dead. Their only surviving use would be as report
  annotations, which has no measured value.
- **The recall lever is P3 — domain conclusions with sourced provenance** (the
  first probe: prose conclusions lifted 5/6 units, including all three
  domain-classes 0.45–0.55 → 0.94–0.96). That is a bigger lift: a curated AWS
  lexicon with sourced-row governance (every row: source URL + date + validator),
  because conclusions cannot be derived domain-free.

Options for v0.9:
- **Option A — anchor release (smallest).** v0.9 = E1 + E2 + E5 + telemetry gates
  (V1/V2-split/V3/V5/V6). Recall exit: anchor-class 2/8 + no precision regression.
  E3/E4/E6 move to v0.10, folded into the P3 lexicon design. Honest, shippable in
  days, fixes a real (anchor) failure class, but recall moves 0/8 → ~2/8.
- **Option B — bring the lexicon forward.** v0.9 = E1 + E2 + P3 lexicon v1 (small,
  sourced: IAM multivalued keys, CloudTrail eventCategory semantics, logGroupArn
  suffix rules, CloudTrail field casing — the four measured classes) + E6 with its
  piloted threshold. Recall exit: ≥5/8 per the prose-probe upper bound, V3
  precision gates as written. Highest value, biggest lift (lexicon authoring +
  governance is real work), and it changes SOR's maintenance profile (a curated
  knowledge base ships with the tool).
- **Option C — triage re-scope (run-1 D4, revived).** Accept that a System One
  judge cannot recognize these classes; stop asking it to gate. v0.9 = E1 + E2 +
  verdict demotion for structural classes: SOR outputs ranked site-level findings
  as TRIAGE for the paid tiers, no Changes-requested authority. Cheapest honest
  repositioning, but abandons the autonomous-recall goal.

Tessera's advisory (non-binding): **B**, with A as the fallback if lexicon
governance stalls — the probe evidence says conclusions are the only lever that
moves Jev, and the four measured classes are small enough to govern properly.
E6 (test variant) rides along in either option per the OQ2 ruling.

## Design (E-numbers continue the v0.2 scheme)

- **E1 — honest wire-format stamp (prerequisite, reworked per M6).**
  `packaging_version`/`record_version` stay CONSTANT per release (`v09`) — existing
  exact-match gates (test_sweep, test_field_sweep) keep working. The cutting path
  rides an EXTENDED `wire_format` enum — `line-window` / `ast-units` / `ts-units` /
  `sites` — surfaced in BOTH the `--out` JSON `meta` block and the metrics ledger,
  plus a per-unit `cut` field on every judged entry. `gate_run`'s like-for-like
  check compares `wire_format`, not packaging versions. A `--force-window-cut` flag
  provides the window-only leg for V5.
- **E2 — decision-site cutting (P1 substrate; engagement stated per B1).**
  ENGAGEMENT: site cutting engages for ALL code-change clusters (TS/JS/Python) —
  not only oversize/band units; the oversize/band rules keep governing the legacy
  top-level cutters exactly as today. Sites: object-literal property assignments,
  call-argument expressions, conditional expressions, and sibling-constant
  declarations become first-class anchors (tree-sitter node kinds for TS/JS; `ast`
  walk for Python). `--max-hunks` interaction (per OQ1 "no run-level site cap"):
  `--max-hunks` continues to cap TOP-LEVEL CLUSTERS pre-expansion; site units are
  EXEMPT from the post-expansion truncation — a cluster admitted to judging is
  judged in full at site granularity. Ceiling drops keep the existing
  incomplete-review banner at cluster level. Call growth: the ruled 3–6× envelope,
  no run-level cap. Guards: (a) NEW compose() behavior — majors are counted per
  PARENT cluster so one decision cannot trip the two-major rule twice (a unit is
  its own parent when uncut); this deliberately changes verdicts vs the flat count
  on multi-site runs, and V3 measures that change like-for-like instead of
  forbidding it; (b) pure-data sites (e.g. 60-entry array literals) get a size
  floor; (c) no-op guard retained — site set == changed set → judge whole / leaf
  immediately (no depth-cap recursion).
- **E3 — `structural_facts` state key (P2 substrate; GATED — see THE FORK).**
  V0 measured this mechanism inert for recall (Problem 5/6). The contract below is
  retained as the SPEC for any future facts system (P3 lexicon rows would ride the
  same key with sourced `note` provenance fields added); it ships in v0.9 ONLY if
  Option B is picked.
  Packaging may attach zero or more fact rows to a unit state. Rows are STRUCTURED:
  `kind` (fixed enum), `id` (identifier string validated
  `^[A-Za-z_$][A-Za-z0-9_$]*$`), `span` (integer line pair), `note` (fixed-vocabulary
  phrase, length-capped — NO free text derived from the reviewed diff; fact text is
  attacker-adjacent in SOR's threat model and must never carry instruction-like
  content). `hunk_state` serializes the structured object (same ride-along pattern
  as `references_remaining`/`ast_context`). Facts are EVIDENCE, never verdicts: they
  never gate, never compose, and are always attributable in the report
  (`facts: [...]` per finding).
- **E4 — detector library v1 (tree-sitter query DSL, domain-free; GATED — V0
  measured NO recall lift; see THE FORK).** Detectors emit only E3-structured rows, ≤N per unit:
  (1) branch-name polarity — condition identifier tokens vs branch constructor
  tokens (M3 class, the deepest P2-covered failure);
  (2) writer/reader field symmetry — fields written into a typed object never read
  by a same-type consumer one import hop away (N3);
  (3) literal-type discriminator never compared (N3, second angle);
  (4) duplicate literal across sibling exported constants bound to different
  construct instances (N1);
  (5) placeholder-test — typeof/toBeDefined-only assertions with no call into a
  subject (N4; feeds E6's variant).
  Each detector ships with a corpus false-fire screen (V4) and is dropped, not
  tuned, if it carries no signal.
- **E5 — dependency packaging (pinned per M2/m4).** `tree_sitter` and
  `tree_sitter_typescript` wheels join the supported-install path with EXACT pinned
  versions recorded in the install check and stamped into each ledger record
  (grammar determinism). `--version` runs a per-cutter self-check (parse a known
  snippet per language) and reports per-cutter availability INTO THE LEDGER — so
  "cutter never engaged" is always distinguishable from "cutter unavailable". The
  lazy import seam and CI-without-wheels behavior stay exactly as ratified
  2026-10-02. **HARD PRECONDITION (Opus r1 B2):** any V2/V5 measurement run aborts
  unless the per-cutter self-check reports TS cutting AVAILABLE in the running
  interpreter — a silent window fallback must be impossible on a measurement run.
  (Measured root cause 2026-10-19: the binary's interpreter is a distinct venv;
  wheels present in one python3 and absent in another produced the 46-vs-168-unit
  discrepancy between runs of the same commit.)
- **E6 — test-file question variant (Kurt, OQ2 ruling; deterministic routing + own
  threshold per M3/M4).** ROUTING (deterministic, no convention inference): path
  component in {`tests`, `test`, `__tests__`, `spec`, `specs`} OR basename matching
  `*.test.*` / `*.spec.*` / `*_test.*` / `test_*.*`; a documented override flag
  exists for misroutes. The variant's `is_real_issue` asks "does this test fail to
  actually test anything?" (placeholder/import-justifying tests, assertions on
  imports, tests that cannot fail); `severity` criteria and `category` values stay.
  THRESHOLD: per the codebase's own precedent (deletion rubric has its own
  threshold because answer distributions differ), the variant gets
  `TEST_REAL_THRESHOLD`, pinned by a pre-implementation pilot (the golden N4 unit +
  2 negative test-file units, 3×3 calls) BEFORE any V2 run. compose() routes by
  question set. Production-code units never see the variant (enforced by V6).

## Validation protocol (exit contract — every gate measured, none argued)

- **V1 fixture regression:** the saturated fixture golden stays 5/5 with precision
  1.0 under site-level cutting (run-2 missing experiment #5).
- **V2 golden recall (config pinned per m3):** 8-defect Stage A golden rerun on the
  P1+P2 build at FULL coverage with an explicit `--max-hunks` value (sites exempt
  per E2). **Exit ≥ 4/8**, with the M1-taxonomy split reported: anchor-class
  recoveries (B2/M2) counted separately from recognition-class recoveries
  (M3/N3/N1 via E4 facts; N4 via E6 at its piloted threshold). Stretch 6–7/8.
  Every claim cites the E1 `wire_format` + per-unit `cut` field. V2-priming runs
  rebuild states via `hunk_state()` (m6).
- **V3 negative arm (precision; re-operationalized per B2):** (a) noise band: the
  BASELINE build runs TWICE on the five defect-free negative heads + the three
  `reproof:` ranges — observed verdict/findings delta defines the noise band;
  (b) the new build must show no reported-findings increase beyond that band;
  (c) like-for-like verdict comparison: baseline findings replayed through the new
  compose() — flips caused SOLELY by the per-parent major rule are counted and
  reported separately, not forbidden;
  (d) M5 sub-gate: clean negative-head units rerun with a synthetic fact
  force-attached — is_real must stay below the report gate (anchoring bound).
- **V4 detector screens (model off):** every E4 detector runs over the 47-PR corpus
  pinned heads; fire rate on clean heads ≥ fire rate on positive heads → detector
  dropped before any model spend.
- **V5 stamp test:** a `--force-window-cut` run and a site-cut run of the same
  range must carry distinguishable `wire_format` values in BOTH `--out` meta and
  the ledger, and per-unit `cut` fields must agree with the actual cut path
  (fixes Problem 4; run-2 missing experiment #2).
- **V6 routing gate (new, per M4):** the E6 routing rule runs over the 47-PR
  corpus's full changed-file list; zero production-file units may route to the
  test variant (unit test, permanent).

## Non-goals

- **P3 domain fact lexicon (B1/B2/M1 classes) is NOT in v0.9.** The probe proves the
  model USES domain facts (those classes moved 0.45–0.55 → 0.94–0.96), but the
  facts must be GENERATED deterministically, and that requires a curated,
  source-governed AWS lexicon. Per the Fable advisory: hold behind a governance rule
  (every row carries a source URL + date; unsourced rows never ship); revisit as
  v0.10 once v0.9 measures how much P1+P2 alone recover. Design notes for it stay in
  the run-2 memo.
- P4 contrastive choice questions: fixture-experiment only, no production wiring.
- No threshold changes to the generic code-change question set; the E6 test-file
  variant is a separate set with its own piloted threshold; no new providers.

## Open questions — ALL RULED (Kurt, msg 1561746424616460349, "1,2,1")

- **OQ1 — RULED (1):** accept the 3–6× call envelope; no run-level site cap.
  (B1 operationalization: `--max-hunks` caps top-level clusters pre-expansion; site
  units exempt — the cap the ruling forbids is the post-expansion one.)
- **OQ2 — RULED (2):** test-file question variant added as E6 (scope + Non-goals
  updated accordingly; deterministic routing + piloted threshold per M3/M4).
- **OQ3 — RULED (1):** one release — E1 stamp + E5 wheels + E2/E3/E4 cutting ship
  together; V5 is the release gate.
