# TS/JS `ast_context` enrichment and the enrichment effect gate

Status: implemented on `feat/ts-enrichment`; effect UNMEASURED (this spec
defines how it will be).

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
   for a benefit is low and the GB gate saw more context soften `is_real`.

## Decision

Ship TS/JS enrichment **default-on**, under the existing `--no-enrichment`
off switch, so dogfooding exercises it on real PRs. This follows INTENT's
"How changes are made" item 4: metrics refine, they do not gate shipping.
Local smoke tests (below) prove the mechanism engaged, the off arm is one
flag away, runs are stamped and labelled, and the evaluation below decides
afterwards whether it stays default-on.

## Design

- `build_ast_context` dispatches on extension (`TS_LANGUAGE_BY_EXT`) to
  `_ts_ast_context`. Same output shape and caps as Python
  (`ENRICHMENT_MAX_SYMBOLS` 40, `ENRICHMENT_MAX_CONTEXT_LINES` 20), so the
  model-facing payload is like-for-like and only the parser differs.
- tree-sitter is loaded lazily through the same injectable `loader` seam as
  `ts_units` (no static import, no `# type: ignore`). Missing wheels, a
  parse error (`root_node.has_error`), a file over
  `TS_ENRICHMENT_MAX_CHARS` (256 K characters) or any exception yields no
  `ast_context` key, exactly like an unparseable Python file.
- The enclosing chain comes from a full-tree iterative walk with a parent
  chain (not top-level queries), so non-exported and nested arrows,
  class methods and fields, object-literal methods and arrow properties,
  namespaces, interfaces/types/enums and `export default function` resolve.
  Overload signatures, anonymous callbacks, destructuring and computed
  keys do not introduce a symbol. Decorators on an exported class sit
  outside the class span and get no enclosing symbol.
- The parse, symbol table and symbol spans are derived once per image and
  cached per run (`_TS_PARSE_CACHE`, cleared with the other runtime
  caches) because about ten sites per cluster share one image. Lines are
  split on "\n" only (`str.splitlines()` also splits on U+2028 and form
  feed, which tree-sitter rows and diff line numbers do not).
- Ledger stamp: per unit `"none" | "ast" | "ts-ast"`; run level
  `"none" | "ast" | "ts-ast" | "ast+ts-ast"`. `"ast"` keeps its old
  meaning (Python), so existing receipts stay comparable.
- `--out` findings now carry the judged unit's `lines`, so a receipt is
  self-contained for REAL/FP adjudication (previously only location,
  scores and header were kept and the code had to be rebuilt from git).
- Known limit, carried over from Python and deliberately NOT changed here:
  the window is head-first. A change deep inside a long symbol sits outside
  the 20 lines shown. The census below measures how often that happens.

## Validation

Steps 1 and the guard in step 3 are the pre-release smoke tests. The census
(2), the full A/B (3) and the dogfooding adjudication (4) run after release,
on real work, and their receipts go under `docs/benchmarks/` (labels per
AGENTS.md). None of them blocks the release.

1. **Mechanics (CI, model-off)** `tests/test_ts_enrichment.py` pins the
   chain for every fixture line in `tests/data/ts-enrich/` (arrows, class
   members, object-literal methods, TSX components, decorators, overloads,
   namespaces, default export, a syntax-error file, an oversize file),
   byte-identical determinism, the caps, the JS grammar, pre-image use for
   deletion-only units, the loader-failure fallback and the stamps. CI
   installs the tree-sitter wheels on the 3.12 leg only, so the other legs
   cover the no-wheels path. An end-to-end test asserts the on-arm stamps
   `ts-ast` and `--no-enrichment` stamps `none`.
2. **Coverage census (model-off, free)** `scripts/enrichment_census.py`:
   for each golden row, does a symbol resolve and does the head-first window
   contain the golden line. Run it on the Stage A golden
   (`fb51dd6..d70d225`, 8 defects, long CDK constructors) before the live
   A/B. If coverage is poor, fix the window (a separate stamped variant)
   first, or the A/B measures the window bug, not the idea.
3. **Effect A/B (live, costs money)** `scripts/enrichment_ab.py`, on vs
   `--no-enrichment`, 3 repeats, over: TS fixture (3 defects), Stage A (8),
   the negative fixture and clean heads, and corpus TS/TSX rows. Python is
   run the same way on `examples/fixture-golden.tsv` and the corpus py rows
   to give Python its first valid measurement. Pre-registered rules, read at
   the 0.80 reflex gate:
   - **Vacuity guard:** abort (exit 2) unless the on-arm run stamp contains
     the expected value and wheels are available.
   - **Precision first:** on a clean sample (`--clean`) the on-arm may not
     surface more findings than the off-arm in any repeat; on a golden
     sample only false positives (reported minus true positives) are
     compared. A new FP *class* is a kill, judged by hand from the
     adjudicated findings, not by the script.
   - **Recall:** signal only if on beats off by at least 2 true positives in
     every repeat (11 TS defects x 3 repeats; the goldens are tiny, so this
     is a smoke test, not a significance claim).
   - **Softening:** a systematic negative paired `is_real` shift on
     identical units (sign test p < 0.05) is a kill even if the above pass.
   - Anything short of precision + recall passing is "no detectable
     effect": enrichment stays available but is switched off by default.
4. **Dogfooding:** on-arm runs on TS PRs that are already being adjudicated,
   labels `exp:enrich:{on,off}:<sample>:r<k>`, always `--out`. Record each
   surfaced finding in `docs/benchmarks/<date>-enrich-adjudications.tsv`:
   `run_label, arm, file, line_start, line_end, is_real, verdict
   (REAL|FP|DUP), adjudicator, note`. Stop at 10 adjudicated surfaced
   findings per arm or 15 TS PRs. Keep the default only if the on-arm
   sustained rate is at least the off-arm's with no new FP class; otherwise
   flip the default off in a `feat:`/`chore:` PR and file the receipt in
   `docs/evals/`.

## Known limits of the harness

- Paired `is_real` deltas key on `file:line:line_end`. Two sub-units with
  the same span in one cluster would collapse; not seen in practice, and the
  ledger carries no content key to disambiguate.
- The softening kill needs at least 6 non-zero per-unit deltas to be able to
  reach p < 0.05; the output flags `softening_test_underpowered` otherwise.
  With goldens this small, treat the A/B as a smoke test and rely on the
  dogfooding adjudication for the real call.

## Out of scope

Head-first to centred windows; enrichment for languages other than
Python and TS/JS; telling the model what `ast_context` means (rule 6
says conclusions, not anatomy, are what move it).
