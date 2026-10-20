# TS/JS `ast_context` enrichment and the enrichment effect gate

Status: implemented on `feat/ts-enrichment` (PR #22); effect UNMEASURED (this
spec defines how it will be). Plan:
`docs/superpowers/plans/2026-10-20-ts-enrichment-effect-gate.md`.

## Scope

In: enclosing-symbol `ast_context` for TS/JS units, its ledger stamps, the
`--out` `lines` field, the model-off census, the on/off A/B harness, and the
post-release evaluation. Out: see the end of this document.

## Problem

1. `ast_context` (top-level symbol table, enclosing-symbol chain, a
   head-first window of the innermost enclosing symbol) was built for
   Python only. For TypeScript/JavaScript `build_ast_context` returned
   `None`, so every TS/JS unit ran with ledger `enrichment: "none"` even
   though TS is the language the tool is dogfooded on. The v0.9 E2 cutter
   already gives TS/JS decision-site units; what was missing is the
   enclosing-symbol context for them.
2. The effect of enrichment has **never been validly measured**. The only
   A/B (`docs/evals/2026-10-02-v08-gate-results.md`, enrichment-off arm)
   ran on TS/JS/Rust where the Python path never engaged: both arms were
   unenriched. `docs/evals/2026-10-02-gb-batching-gate.md` inherits that.
   Python enrichment has been default-on since then, unmeasured.
3. INTENT rule 6 records that structured, conclusion-free rows moved
   nothing (M3 0.44 to 0.36). `ast_context` is such a row set, so the prior
   for a benefit is low. The GB batching gate (more code per call, not
   `ast_context`; see its stale note) saw `is_real` soften, which is a
   reason to watch for softening, not evidence about enrichment.

## Decision

Ship TS/JS enrichment **default-on**, under the existing `--no-enrichment`
off switch, so dogfooding exercises it on real PRs. This follows INTENT's
"How changes are made" item 4: metrics refine, they do not gate shipping.
Local smoke tests (below) prove the mechanism engaged, the off arm is one
flag away, runs are stamped and labelled, and the evaluation below decides
afterwards whether it stays default-on.

## Design

- `build_ast_context` dispatches on extension (`TS_LANGUAGE_BY_EXT`: ts,
  tsx, js, jsx, mjs, cjs) to `_ts_ast_context`. Same output shape and caps
  as Python (`ENRICHMENT_MAX_SYMBOLS` 40, `ENRICHMENT_MAX_CONTEXT_LINES`
  20), so the model-facing payload is like-for-like and only the parser
  differs.
- tree-sitter is loaded lazily through the same injectable `loader` seam as
  `ts_units` (no static import, no `# type: ignore`). Missing wheels, a
  parse error (`root_node.has_error`), a file over
  `TS_ENRICHMENT_MAX_CHARS` (256 K characters) or any exception yields no
  `ast_context` key, exactly like an unparseable Python file. The tool
  never fails because enrichment failed.
- The enclosing chain comes from a full-tree iterative walk with a parent
  chain (not top-level queries), so non-exported and nested arrows,
  class methods and fields (TS `public_field_definition`, JS
  `field_definition`), object-literal methods and arrow properties,
  namespaces, interfaces/types/enums and `export default function` (named
  `<default>`) resolve. Overload signatures, anonymous callbacks,
  destructuring and computed keys do not introduce a symbol. Decorators on
  an exported class sit outside the class span and get no enclosing symbol.
- The parse, symbol table and symbol spans are derived once per image and
  cached per run (`_TS_PARSE_CACHE`, keyed on language and the full source
  text, so memory is bounded by the images in the run and the cache is
  cleared with the other runtime caches). About ten sites per cluster share
  one image. Injected test loaders bypass the cache. Lines are split on
  "\n" only (`str.splitlines()` also splits on U+2028 and form feed, which
  tree-sitter rows and diff line numbers do not).
- Ledger stamp: per unit `"none" | "ast" | "ts-ast"`; run level
  `"none" | "ast" | "ts-ast" | "ast+ts-ast"`. `"ast"` keeps its old
  meaning (Python). `record_version` and `packaging_version` stay `v09`
  although TS wire payloads changed, so older receipts are compared to new
  ones only by the per-unit stamp (a pre-PR TS unit reads `none`).
- `--out` findings now carry the judged unit's `lines`, so a receipt is
  self-contained for REAL/FP adjudication (previously only location,
  scores and header were kept and the code had to be rebuilt from git).
- Known limit, carried over from Python and deliberately NOT changed here:
  the window is head-first. A change deep inside a long symbol sits outside
  the 20 lines shown. The census below measures how often that happens.
- Over-cap context is still dropped, never split: `reexpand_after_enrichment`
  removes `ast_context` from a unit that trips the soft cap (INTENT-era
  r12-M1 behaviour, unchanged). The per-unit stamp records the judged state,
  so such a unit reads `none` even though enrichment was attempted.

### Cost envelope (INTENT rule 1)

Enrichment adds input tokens per unit; it adds no model calls.

- **Model-off size.** Measured on the TS fixtures
  (`tests/data/ts-enrich/sample.ts` and `component.tsx`, 83 rows, every row
  enriched): `ast_context` adds a median of 416 characters (maximum 740)
  per unit, about 139 (maximum 247) tokens at `CHARS_PER_TOKEN = 3.0`,
  against about 220 characters for a bare five-line unit. The receipt
  `docs/benchmarks/2026-10-20-ts-enrichment-envelope.json` is authoritative
  and reproducible with `scripts/enrichment_census.py --json`, which
  reports `ctx_chars` per row and the summed `added_tokens`.
- **Multiplier.** Each E2 site unit carries its own copy, and the V7 census
  measured 9.63x site expansion on the Stage A range (INTENT rule 2 status),
  so added tokens per run scale with units, not files. The parse is cached;
  the wire copy is not.
- **Parse cost.** One tree-sitter parse per file image per run; the
  oversize guard (256 K characters) bounds the worst case.
- **Latency.** Not yet measured. Wall-clock on the Stage A range with and
  without `--no-enrichment` goes in the first evaluation receipt. Because
  this is judged after release (INTENT item 4), rule 1's envelope is
  watched, not pre-proved: if added latency or tokens make a run leave the
  seconds/cents envelope, that alone flips the default off.

## Validation

Steps 1 and the guard in step 3 are the pre-release smoke tests. The
envelope receipt (above), the census (2), the full A/B (3) and the
dogfooding adjudication (4) run on real work after release, with receipts
under `docs/benchmarks/` (labels per AGENTS.md). None of them blocks the
release.

1. **Mechanics (CI, model-off)** `tests/test_ts_enrichment.py` pins the
   chain for every fixture line in `tests/data/ts-enrich/` (arrows, class
   members, object-literal methods, TSX components, decorators, overloads,
   namespaces, default export, a syntax-error file, an oversize file),
   byte-identical determinism, the caps, the JS grammar, pre-image use for
   deletion-only units, the loader-failure fallback and the stamps. CI
   installs the tree-sitter wheels on the 3.12 leg only (and asserts they
   import), so the other legs cover the no-wheels path. An end-to-end test
   asserts the on-arm stamps `ts-ast` and `--no-enrichment` stamps `none`.
   A test asserts `--out` findings carry `lines`.
2. **Coverage census (model-off, free)** `scripts/enrichment_census.py`:
   for each golden row, does a symbol resolve, does the head-first window
   contain the golden line, and how many characters/tokens does the context
   add. The golden line stands in for a unit's first line, so "covered" is
   approximate (a real site unit may start earlier). Run it on the Stage A
   golden (`fb51dd6..d70d225`, 8 defects, long CDK constructors; the
   SynapseTree-login checkout holding that range is on the maintainer's
   other machine, not in this repo) before the live A/B. If coverage is
   poor, fix the window (a separate stamped variant) first, or the A/B
   measures the window bug, not the idea.
3. **Effect A/B (live, costs money)** `scripts/enrichment_ab.py`, on vs
   `--no-enrichment`, 3 repeats, over: TS fixture (3 defects), Stage A (8),
   the negative fixture and clean heads, and corpus TS/TSX rows. Python is
   run the same way on `examples/fixture-golden.tsv` and the corpus py rows
   to give Python its first valid measurement. Rules, read at the 0.80
   reflex gate:
   - **Counts** come from the ledger `judged` entries that cross the gate
     (`is_real >= 0.80`), not from `--out` `findings`, which is capped at 5
     per the ROADMAP standing rule and would saturate on Stage A.
   - **Vacuity guard:** abort (exit 2) unless the on-arm run stamp contains
     the expected value, the TS wheels are available, the run did not fail
     open, and every golden file has at least one unit stamped with the
     expected value. A golden file with none enriched means it failed to
     parse; partial enrichment is reported as an enriched share, not an
     abort, because over-cap context drop (above) legitimately turns some
     units to `none` on long constructors.
   - **Precision first:** on a clean sample (`--clean`) the on-arm may not
     surface more findings than the off-arm in any repeat; on a golden
     sample only false positives (gate-crossers minus true positives) are
     compared. A new FP *class* is a kill, judged by hand from the
     adjudicated findings, not by the script.
   - **Recall:** signal only if on beats off by at least 2 true positives in
     every repeat (11 TS defects x 3 repeats; the goldens are tiny, so this
     is a smoke test, not a significance claim).
   - **Softening:** a systematic negative paired `is_real` shift on
     identical units (sign test over per-unit means, p < 0.05) is a kill
     even if the above pass; below 6 non-zero pairs the test cannot reach
     significance and the output says `softening_test_underpowered`.
   - **Combining samples:** each `--sample` yields its own verdict. Overall
     is KILL if any sample is KILL; SIGNAL only if every golden sample is
     SIGNAL and none is KILL; otherwise NO-DETECTABLE-EFFECT.
   - **What a verdict does:** only a KILL flips the default off before
     dogfooding. NO-DETECTABLE-EFFECT and an underpowered result are
     recorded, not acted on; the default is decided by step 4.
4. **Dogfooding (the real decision).**
   - **Procedure per TS PR:** the normal production run (label `<scope>`,
     enrichment on by default, `--out`) plus one extra run with
     `--no-enrichment`, label `exp:enrich:off:<pr>:r1`, `--out`. The
     production run is the on-arm; both read the same range.
   - **Adjudicator:** the maintainer, in writing REAL/FP/DUP per surfaced
     finding (AGENTS.md Measurement discipline), before consuming the
     finding.
   - **Record:** `docs/benchmarks/<date>-enrich-adjudications.tsv`, template
     `docs/benchmarks/enrich-adjudications-TEMPLATE.tsv`; columns
     `run_label, arm, file, line_start, line_end, unit_stamp, is_real,
     verdict (REAL|FP|DUP), adjudicator, note`. `unit_stamp` records the
     per-unit stamp, because the installed binary's interpreter (AGENTS.md
     gotcha) can silently run the on-arm without the wheels and under a
     production label.
   - **Stop** at 10 adjudicated surfaced findings per arm or 15 TS PRs,
     whichever comes first. Keep the default only if the on-arm sustained
     rate is at least the off-arm's with no new FP class; otherwise flip the
     default off in a `feat:`/`chore:` PR and file the receipt in
     `docs/evals/`.
   - **If too few findings surface** (the 0.80 gate fired 0 of 48 wild false
     positives and surfaces little), the default stays on and the question
     reopens with the next golden or after the next 15 PRs.

## Known limits of the harness

- Paired `is_real` deltas key on `file:line:line_end`. Two sub-units with
  the same span in one cluster would collapse; not seen in practice, and the
  ledger carries no content key to disambiguate.
- With goldens this small (3 + 8 TS defects, 5 Python plants), the A/B is a
  smoke test. The dogfooding adjudication makes the real call.

## Open questions

- Is a head-first window the right shape for TS, or does the census show
  centred windows are needed? On the small fixture functions the window
  already misses the golden line on 24 of 83 rows (covered 59/83, median
  window 3 lines); the long CDK constructors in Stage A are expected to be
  worse. (Separate stamped variant if so.)
- Should site units carry only the enclosing chain, not the symbol table,
  to cut the 9.63x multiplier? Decide from the envelope receipt.
- Should `record_version` bump to separate TS-enriched wire payloads from
  older v09 receipts, or is the per-unit stamp enough?

## Out of scope

Head-first to centred windows; enrichment for languages other than
Python and TS/JS; telling the model what `ast_context` means (rule 6
says conclusions, not anatomy, are what move it).
