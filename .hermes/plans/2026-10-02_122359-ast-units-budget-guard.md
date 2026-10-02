# AST Units + Budget Guard — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace the 120-line skip with AST-aware review units, a 32k payload budget guard, and AST context enrichment — closing the hunk>120 coverage hole per the approved architecture brief (rev 7, D1–D8 ruled).

**Architecture:** Clusters stay the unit of judgment and per-cluster calls stay the transport (D5). What changes: (1) oversize change regions are cut on AST boundaries first (stdlib `ast` for Python, lazy tree-sitter import for TS/JS/etc., line-window fallback), producing AST sub-clusters that inherit the parent cluster's identity; (2) every outgoing call is budget-checked against Jev's real 32k state+longest-question limit, with a guaranteed-terminating split on `_OverBudget`; (3) each unit's state gains read-only AST context (enclosing symbol, file symbol table) — enrichment, not merged units; (4) the ledger stamps transport/wire_format/enrichment/record-version (D7). Honesty machinery (Step 0′, `base_verdict`, gate_run, Incomplete) is untouched.

**Spec:** `docs/superpowers/investigations/2026-10-01-architecture-ast-batching-brief.md` (rev 7) on this branch — authoritative for every number and rule cited below. D1–D8 all ruled as recommended (2026-10-02).

**Tech Stack:** Python 3.14 stdlib only at core (ast, json, math); optional lazy `tree_sitter` + per-language grammar packages (D1 — import failure = silent fallback to line windows); pytest. No new required dependencies.

**Branch:** `impl/ast-units` off `main` (394ea0a). Baseline: full suite green on main; 254+ tests.

**Hard constraints from the brief (do not deviate):**
- Cluster = unit of judgment; NO merged-unit judging. Every cluster/sub-cluster keeps its own anchor + full question triple (u triples, D8). Sub-clusters inherit parent `change_type`.
- The 32k budget = state + longest question, SERIALIZED estimate, computed on every call; never send an estimated-over-cap call. Soft cap 28k (split proactively), hard behavior on runtime 400+`max_tokens_exceeded`: typed `_OverBudget`, split in half (AST sub-clusters first, then ±1-line windows at the leaf), depth-capped ⌈log2(24)⌉+1 ≈ 6 levels, at ONE unit mark that cluster unjudged (feeds Incomplete) and stop. Over-budget chain = ONE attempt for the consecutive-failure counter; any other 4xx = existing `_NoRetry`.
- `MAX_HUNK_LINES` RETIRED as a skip mechanism (no more `hunk>120 lines` skips); `--max-hunks` redefined as units-per-run (run-level ceiling 40, no file-level drops).
- Per-mode file sources for AST parsing: `--range/--pr` = `git show <head>:<path>` post + `git show <merge_base>:<path>` pre (plan computes merge base — `resolve_diff` doesn't return it); `--staged` = `git show :<path>` post vs `git show HEAD:<path>` pre; `--uncommitted` = worktree post vs `git show :<path>` pre (documented diff-only exception, D4). Deletion-only/whole-file-deleted clusters stay cluster-based (no post-image; no AST parsing).
- Failure semantics: per-unit KEY misses mark only that cluster `parse_error` (never touch `failures`/`parse_failures`); only CALL-level shape failures (`answers` missing/not-dict, zero parseable units) count toward consecutive limits; nothing-judged → fail-open unchanged.
- Thresholds stay per-rubric (code 0.50, deletion 0.70) — untouched.
- Laya: per-cluster transport unchanged; batching/AST path is JEV-only (D6). Old shape-only laya contract stays.
- Ledger contract (D7): every run stamps `transport` (`per-cluster`), `wire_format` (`hunk_state-v1` / `ast-units-v1`), `enrichment` (`none`/`ast`), and `PACKAGING_VERSION` bumps (new value `v08-ast`) so replays compare like-for-like.
- Tree-sitter = lazy opportunistic import; ImportError → stdlib/fallback silently (D1). README documents it.

---

## Task 0: Defect-positive fixture (plan prerequisite, brief req 8)

**Objective:** Anchor the 3 real pre-fix majors of curated-journal PR #43 (two abort races, one signature contract) as golden anchor rows, and verify per-cluster transport reports them at the pre-fix SHAs. G-B (later task) needs defect-positive ground truth.

**Files:**
- Create: `examples/cj43-prefix-goldens.tsv` (anchor rows: `file<TAB>line<TAB>desc`)
- Create: `docs/evals/2026-10-02-cj43-prefix-verification.md` (results only)

**Steps:**
1. In a scratch clone of curated-journal, locate the pre-fix commits (before 99711a4): the importDump abort-race and 3-arg signature eras. Record candidate SHAs.
2. Run current sor per-cluster (`--range <base>...<prefix_sha>`, JEV provider, live) on each candidate; identify the commit where the 3 majors are present as real defects.
3. Record anchors (file + line at that SHA) for: abort-race #1 (stopped-flag), abort-race #2 (cancel handshake), signature contract (importDump arity). Format matches `eval_against_golden` expectations (mirror `examples/cj-field-goldens.tsv` header comments style).
4. Verify: run `scripts/` golden eval path against the fixture; all 3 anchors hit, ≤1 FP beyond them.
5. Commit: `test(fixture): defect-positive CJ#43 pre-fix goldens (3 anchors, verified)`.

**Verification:** eval doc states SHAs, anchors, live-run result; fixture committed.

---

## Task 1: Serialized-size estimator

**Objective:** The shared measurement everything else uses: `estimate_call_size(state, questions)` → serialized JSON length of state + longest serialized question, cheap and deterministic.

**Files:**
- Modify: `system_one_reviewer.py` (new function near `jev_ask` ~:157; constant `STATE_CHAR_BUDGET = 32_000` and `SOFT_CAP = 28_000` near `MAX_HUNK_LINES` :50 — MAX_HUNK_LINES itself is RETIRED in Task 4)

**Steps:**
1. Failing test (`tests/test_budget.py`, new):
   - `test_estimate_matches_actual`: build a state+questions, `estimate_call_size` ≤ actual `len(json.dumps({"state":…, "questions":…}))` and ≥ actual − slack(64) (estimator may reuse pre-serialization; must never undercount).
   - `test_estimate_monotonic`: doubling a state's text roughly doubles the estimate.
2. Run: `.venv/bin/python -m pytest tests/test_budget.py -q` → FAIL.
3. Implement: serialize state once with `json.dumps`; questions likewise; return len(state_json) + max(len(q_json) for q in questions.values()). No caching games (YAGNI).
4. Tests → PASS; full suite green.
5. Commit: `feat(budget): serialized call-size estimator + 32k/28k constants`.

---

## Task 2: AST unit extraction — Python (stdlib)

**Objective:** `ast_units(path, before_text, after_text, entries)` → for an oversize code-change cluster, return sub-clusters whose boundaries land on top-level def/class ends in the post-image; fallback `None` when AST can't help (parse error, non-Python, units don't cover the span).

**Files:**
- Modify: `system_one_reviewer.py` (new function after `package_hunks` ~:697)
- Test: `tests/test_ast_units.py` (new)

**Steps:**
1. Failing tests:
   - `test_oversize_python_splits_on_defs`: synthetic .py post-image with 3 top-level functions (total 200 changed lines) → 3 sub-clusters, each boundary = a function's end line, none mid-function; union of changed lines == original; no line in two sub-clusters.
   - `test_subcluster_inherits_identity`: every sub-cluster carries parent's `file`, `change_type`, and a `parent_cluster` reference; own anchor = first `+` entry's tracked line; own `line_start/line_end`.
   - `test_parse_error_returns_none`: post-image that doesn't parse → `None` (caller falls back to line windows).
   - `test_deletion_cluster_skipped`: `change_type` deletion-only → `None` immediately (no post-image; brief req: deletion clusters stay cluster-based).
   - `test_small_cluster_skipped`: cluster under the size threshold → `None` (AST path only engages for oversize regions).
   - `test_determinism`: same input twice → identical output.
2. Run → FAIL; implement with stdlib `ast.parse` on the post-image; walk top-level nodes with `end_lineno` (3.8+); map changed lines to enclosing top-level symbol; group.
3. Tests → PASS; full suite green.
4. Commit: `feat(ast): stdlib ast unit extraction for oversize Python clusters`.

---

## Task 3: Tree-sitter lazy import + TS/JS units + line-window fallback

**Objective:** Same contract for TS/JS (the corpus's biggest offenders are .ts) via tree-sitter with a lazy import; and `line_window_subclusters()` — the always-works fallback cutting at blank lines nearest the target, never mid-line.

**Files:**
- Modify: `system_one_reviewer.py` (tree-sitter helper near Task 2's function)
- Test: `tests/test_ast_units.py` (extend)

**Steps:**
1. Failing tests:
   - `test_treesitter_lazy_import_missing`: monkeypatch `sys.modules` to hide tree_sitter → TS file returns `None` (fallback), no exception, no hard dependency at import time of the module itself.
   - `test_treesitter_units_when_present`: with tree_sitter installed (skipif), a 200-line .ts with 3 top-level functions → 3 boundary-true sub-clusters.
   - `test_line_window_fallback`: 200 changed lines, no AST at all → sub-clusters ≤120 lines each, cuts at blank lines where possible, union == original, no overlap, deterministic.
2. Run → FAIL; implement: `try: import tree_sitter…` inside the function (laya pattern); grammar loading also lazy per language; fallback cutter shares Task 2's sub-cluster assembly.
3. Tests → PASS (tree-sitter tests skipif-marked); full suite green.
4. Commit: `feat(ast): lazy tree-sitter units (D1) + deterministic line-window fallback`.

---

## Task 4: Triage rewiring — MAX_HUNK_LINES retired, oversize → AST sub-clusters

**Objective:** `package_hunks` stops marking `too_large` for skipping; `main()` routes oversize code-change clusters through the Task 2/3 extractor and judges sub-clusters as first-class units. `--max-hunks` becomes units-per-run (ceiling 40, run-level).

**Files:**
- Modify: `system_one_reviewer.py` (`MAX_HUNK_LINES` :50 comment→retired note; triage :722–724 no longer appends `hunk>` skip; oversize routing in `main()` near :1325; argparse `--max-hunks` help text)
- Test: `tests/test_triage_and_failreason.py` (extend), `tests/test_package.py` (extend)

**Steps:**
1. Failing tests:
   - `test_no_hunk_skip_reason_ever`: any cluster, any size → no skip record with reason starting `hunk>`.
   - `test_oversize_python_becomes_subclusters`: 273-line .ts-equivalent (Python for stdlib path) → N judged units, each with own anchor/triple, `parent_cluster` set.
   - `test_oversize_fallback_judged_as_windows`: unparseable oversize → line-window sub-clusters, all judged.
   - `test_max_hunks_is_run_level`: 3 oversize files × windows with `--max-hunks 40` → nothing dropped file-wise; dropping happens only at the run ceiling and produces explicit unjudged records (feeding Incomplete), never a silent file skip.
   - `test_deletion_wholefile_stay_cluster_based`: whole-file deletion + deletion-only oversize → judged as single clusters (no AST), question set = deletion rubric.
   - Existing tests updated BY DESIGN: `test_triage_size_skip_carries_change_type` (or successors) now assert sub-cluster routing instead of a skip record.
2. Run → FAIL; implement. NOTE per-mode file sources: AST parsing needs post-image text — `--range/--pr`: `git show <head>:<path>`; `--staged`: `git show :<path>`; `--uncommitted`: worktree read (documented exception, D4). Cache per (sha, path) — shared `contexts` table per brief.
3. Tests → PASS; full suite green.
4. Commit: `feat(units): oversize clusters → AST sub-clusters; MAX_HUNK_LINES retired; --max-hunks = units-per-run`.

---

## Task 5: Budget guard — proactive split + _OverBudget runtime handling

**Objective:** Every outgoing call passes `estimate_call_size ≤ SOFT_CAP` (proactive split of the unit's payload: trim context first, then split sub-clusters); runtime 400+`max_tokens_exceeded` → typed `_OverBudget`, halve-and-retry, depth-capped 6, one-attempt accounting, unjudged at the leaf.

**Files:**
- Modify: `system_one_reviewer.py` (`ask()` wrapper + `judge()` call loop :946–949; `_NoRetry` neighborhood :148 for `_OverBudget`)
- Test: `tests/test_budget.py` (extend)

**Steps:**
1. Failing tests:
   - `test_over_softcap_splits_proactively`: unit whose estimated size > 28k → call(s) sent all ≤28k; union of answers maps back to the unit; context lines trimmed first (assert context shrunk before any changed-line split).
   - `test_runtime_400_max_tokens_splits`: stub transport returns 400 `max_tokens_exceeded` once, then 200 → retry happens with halved payload; attempt counter sees ONE attempt; `_OverBudget` never escapes.
   - `test_depth_cap_terminates`: transport always 400s → ≤6 split levels, then the unit is marked `parse_error` (unjudged, feeds Incomplete), run continues, no infinite loop, no fail-open.
   - `test_other_400_still_NoRetry`: 401 → `_NoRetry` immediately (existing behavior intact).
   - `test_consecutive_accounting_single`: a full over-budget chain counts once toward consecutive failures (brief r3-M5).
2. Run → FAIL; implement.
3. Tests → PASS; full suite green.
4. Commit: `feat(budget): proactive 28k split + typed _OverBudget with depth-capped termination`.

---

## Task 6: AST context enrichment (Arch 3, default path per D3)

**Objective:** Each unit's `hunk_state()` gains read-only AST context: enclosing symbol chain (e.g. `Class.method`) and the file's top-level symbol table (name → signature line). Enrichment is text-only context — no merged units, no question changes.

**Files:**
- Modify: `system_one_reviewer.py` (`hunk_state` :884 — new `ast_context` key when enrichment available)
- Test: `tests/test_enrichment.py` (new)

**Steps:**
1. Failing tests:
   - `test_enrichment_present_for_python`: unit inside a class method → `ast_context` contains enclosing chain + symbol table; keys absent (not None-valued) when unavailable.
   - `test_enrichment_absent_for_deletion`: deletion-only cluster → no `ast_context` (no post-image).
   - `test_enrichment_size_bounded`: symbol table truncated deterministically at 40 symbols / unit context ≤ 20 lines (keeps budget headroom).
   - `test_budget_interaction`: enrichment counts in `estimate_call_size` (a state with huge enrichment trips the soft cap → splits).
2. Run → FAIL; implement (stdlib ast for Python; tree-sitter when present; omit otherwise).
3. Tests → PASS; full suite green.
4. Commit: `feat(enrichment): AST enclosing-symbol + file symbol table on unit states (D3)`.

---

## Task 7: Ledger contract (D7) + PACKAGING_VERSION bump

**Objective:** Every run stamps `transport` (`per-cluster`), `wire_format` (`hunk_state-v1` when no AST engaged, `ast-units-v1` when any unit came from AST), `enrichment` (`none`/`ast`); `PACKAGING_VERSION` → `v08-ast`; sweep-thresholds recognizes it.

**Files:**
- Modify: `system_one_reviewer.py` (`PACKAGING_VERSION` :71; result/log_run block ~:1399); `scripts/sweep-thresholds.py` (`RUBRIC_VERSIONS` :41, packaging default :557)
- Test: `tests/test_package.py`, `tests/test_sweep.py` (extend)

**Steps:**
1. Failing tests: version string asserted in ledger from a `main()`-level run; sweep admits `v08-ast`; `select_runs` default updated; old-version ledgers still gate under explicit `--packaging-version v03b`/`v06`/`v07`.
2. Implement.
3. Full suite green.
4. Commit: `feat(ledger): D7 contract stamps + v08-ast packaging version`.

---

## Task 8: Fixture stability + corpus replay gates (G-A, G-D)

**Objective:** Prove coverage and stability: (G-A) zero `hunk>` skips on the corpus; `write.rs`-class files split and send within budget; (G-D) new-transport vs old-transport agreement ≥ the old runs' own repeat-agreement baseline (noise-aware, replay RECORDED answers where input shape is unchanged).

**Files:**
- Modify: fixture/golden TSVs only if anchors shift (they shouldn't — cluster anchors unchanged for ordinary clusters)
- Create: `docs/evals/2026-10-02-ast-units-ga-gd.md`

**Steps:**
1. Fixture run (v08): all fixtures judged, no `too_large` skips, verdicts byte-comparable modulo documented differences; TP/FP set stable ≥2/3.
2. Corpus replay: `run_corpus` on the v08 build; census recompute — 0 size-skips; write.rs/wisdom.ts-class files produce send-legal batches.
3. G-D: replay recorded answers deterministically for unchanged-shape clusters; agreement ≥ old repeats' baseline; skipped-case improvements exempt.
4. Any gate failure → stop, diagnose, fix, re-run. No partial claims.
5. Commit: `docs(eval): G-A coverage + G-D replay results (v08-ast)`.

---

## Task 9: G-B per-file batching gate (evidence task, may NEGATE the feature)

**Objective:** Run the G-B A/B exactly as the brief specifies (three arms: per-cluster baseline, per-cluster+enrichment, per-file-batched+enrichment; fixture-self calibration first; defect-positive arm must hold recall). Default outcome per D5: per-file batching stays OFF unless every pass criterion is met.

**Files:**
- Create: `docs/evals/2026-10-02-gb-batching-gate.md`
- Create (only if G-B PASSES): batching transport code in a follow-up plan

**Steps:**
1. Calibration run: per-cluster vs per-cluster on the 20–40-cluster fixture (includes multi-cluster files AND split clusters) → measure the fixture's own |Δ| noise, flip rate, sign distribution.
2. Treatment arms: per-cluster+enrichment vs per-file-batched+enrichment.
3. Apply ALL pass criteria: gate-flip ≤5% and within calibration margin; verdict-level flip = 0 across fixture PRs; signed-bias |mean Δsev| ≤ 0.05 AND sign test p > 0.05 (must beat the S1′ −0.55 prior); Δis_real signed test near both rubric thresholds; defect-positive arm recall ≥ per-cluster.
4. Record verdict. If FAIL (expected given S1′): document; per-file batching remains retired; done — no code.
5. Commit: `docs(eval): G-B batching gate — <PASS|FAIL> with full criteria table`.

---

## Task 10: README + Opus review + land

**Objective:** Ship it.

**Files:**
- Modify: `README.md` (units + budget + enrichment section; tree-sitter optional note per D1; new `--max-hunks` semantics)

**Steps:**
1. README section + constraint checklist appended to the brief's verification section.
2. Push branch; PR to main; dispatch Opus review of the full diff (doc-mode loop until APPROVE / APPROVE WITH NITS).
3. Address findings; land per the dual-review-cycle.

---

## Gate → Task map

| Gate | Criterion | Where |
|---|---|---|
| G-A | Zero hunk>120 skips; write.rs-class sends legal | Task 8 |
| G-B | Per-file batching adoption (expected: stays retired) | Task 9 |
| G-D | Noise-aware replay equivalence | Task 8 |
| Fixture | Defect-positive 3-anchor golden | Task 0 |

## Risks / notes

- **Anchor drift:** ordinary (non-oversize) clusters keep byte-identical packaging — their anchors, spans, and states are untouched; only oversize regions change. Golden comparability for ordinary clusters is therefore structural, not hoped-for. Asserted in Task 4 tests.
- **Split inflation:** more units = more calls on oversize files. Accepted: time policy is none (Kurt ruling); cost logged via input_tokens.
- **write.rs (114k chars)**: exercises the depth cap for real. Task 8 includes it explicitly.
- **Laya regression risk:** zero — laya path untouched (D6); Task 5's guard wraps the ask transport only for jev.
- **Tree-sitter wheel choice** (tree-sitter-languages vs per-language): verify maintained wheel at implementation time (brief req 6); either way the import stays lazy and optional.
