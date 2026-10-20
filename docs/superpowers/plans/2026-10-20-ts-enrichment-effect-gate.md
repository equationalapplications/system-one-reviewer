# TS/JS enrichment and effect gate: implementation plan

Spec: `docs/superpowers/specs/2026-10-20-ts-enrichment-effect-gate.md`
(read it first; it wins on intent and rationale, this plan only orders the
work). Branch `feat/ts-enrichment`, PR #22. Tools: `ruff check .`, `mypy`,
`python -m pytest -q` (run once with the tree-sitter wheels and once
without; the no-wheels run must skip, not fail). Commit only when told.

## Done (already on the branch)

- [x] T1 `_ts_parse`, `_ts_symbol_table`, `_ts_symbol_label`,
      `_ts_symbol_spans`, `_ts_enclosing_span`, `_ts_ast_context`,
      dispatch in `build_ast_context`/`attach_ast_context`.
- [x] T2 Stamps `none|ast|ts-ast`, run level `+`-joined
      (`_enrichment_stamp`, `_run_enrichment_stamp`); `--out` findings
      carry `lines`.
- [x] T3 Fixtures `tests/data/ts-enrich/` and `tests/test_ts_enrichment.py`
      (chains, determinism, caps, unicode separators, JS fields, cache,
      loader fallback, end-to-end stamp).
- [x] T4 `scripts/enrichment_census.py` (position-based coverage, wheel
      check, `MISSING-AT-REV`).
- [x] T5 `scripts/enrichment_ab.py` (vacuity guard, fail-open guard,
      `--clean`, label helper, per-unit-mean sign test).
- [x] T6 CI: wheels on the 3.12 leg plus an import assertion.
- [x] T7 INTENT rule 2 status, INTENT item 4 relaxed, AGENTS.md
      spec-plan-implement, README, stale notes on the two Oct 2 eval docs.
- [x] T8 Spec reviewed by Fable and revised (this plan follows the revision).

## Remaining

Each task touches distinct files so they can run in parallel.

### T9 Census: cost columns and envelope receipt
Files: `scripts/enrichment_census.py`, new `tests/test_enrichment_census.py`,
new `docs/benchmarks/2026-10-20-ts-enrichment-envelope.json`, new
`docs/benchmarks/enrich-adjudications-TEMPLATE.tsv`.
1. Add `ctx_chars` (length of the JSON-serialised `ast_context`) to every
   census row and `added_tokens` (sum of `ctx_chars` / `CHARS_PER_TOKEN`
   from the tool module) to `summarize`. Keep existing keys and output.
2. Move the census test out of `tests/test_enrichment_scripts.py` ONLY if
   needed; otherwise add new tests in `tests/test_enrichment_census.py`
   covering `ctx_chars`/`added_tokens` on a throwaway git repo (reuse the
   pattern in `test_census_on_a_throwaway_repo`).
3. Produce the envelope receipt: run the census with `--json` over every
   line of `tests/data/ts-enrich/sample.ts` and `component.tsx` (write a
   small golden TSV in a scratch dir, one row per line, not committed) in a
   throwaway git repo built from those files; save the per-file summary and
   the median/max `ctx_chars` and token estimates to the receipt JSON, with
   the command used and the date.
4. Create the adjudications template (header row only):
   `run_label<TAB>arm<TAB>file<TAB>line_start<TAB>line_end<TAB>unit_stamp<TAB>is_real<TAB>verdict<TAB>adjudicator<TAB>note`.

### T10 A/B harness: ledger counts, guard semantics, sample combination
Files: `scripts/enrichment_ab.py`, `tests/test_enrichment_scripts.py` (A/B
tests only; do not touch the census test).
1. Count reported findings and false positives from the ledger `judged`
   entries with `is_real >= REFLEX_GATE` (0.80; read the constant from the
   tool module), not from `--out` `findings` (capped at 5). True positives
   were first read from `golden_eval`, which the second review showed is
   capped at 5; see T14.
2. `guard_files`: abort only when a golden file has NO unit stamped with the
   expected value (never engaged / parse failure). When some units are
   stamped and some are not (over-cap context drop), do not abort; return
   the enriched share per golden file and include it in the printed result
   as `golden_file_enriched_share`.
3. Add `combine_verdicts(results)` implementing the spec rule (any KILL
   kills; SIGNAL only if every golden sample SIGNAL and none KILL; else
   NO-DETECTABLE-EFFECT) and a `--combine FILE...` mode, or a small
   documented function plus test if a CLI mode is disproportionate.
4. Tests for each change, in the existing style (fake subprocess helper).

### T11 `--out` lines test
Files: new `tests/test_out_lines.py` only.
Drive `main()` offline (pattern: `tests/test_enrichment.py::_run_main`) with a
fake judge that returns a finding crossing the 0.80 gate so it is reported,
write `--out`, and assert `findings[0]["lines"]` equals the unit's lines and
is a list of strings. Include a case with no reported findings (empty list).

### T14 Second-review fixes (done in the follow-up commit)
Findings from the second independent review, applied after T9 to T11:
- A/B counts rebuilt from the uncapped ledger via the tool's own `compose()`
  and `eval_against_golden()` (the `--out` list and its `golden_eval` are
  capped at 5, which capped true positives and could fake a KILL); guard
  covers negative-golden files and rejects a non-`ok` status; the census
  wheel check imports the modules instead of `find_spec`.
- TS symbol table gets a character budget and per-line truncation; Python
  `splitlines()` line drift fixed with a form-feed test; tie-break test.
- Docs: INTENT rule 8 sentence aligned with item 4, "small fixtures"
  wording, unsupported claim removed, spec rules updated.

### T12 Gates (controller)
`ruff check .`, `mypy`, pytest with and without wheels; re-run the vacuity
mutation (remove the oversize guard, the oversize test must fail).

### T13 Wrap-up (controller)
INTENT rule 1 status line updated with the envelope result; PR description
updated; commit, push, request re-review.

## Not in this plan

Running the live A/B, the Stage A census, and the dogfooding adjudication:
post-release evaluation (spec Validation 2 to 4).
