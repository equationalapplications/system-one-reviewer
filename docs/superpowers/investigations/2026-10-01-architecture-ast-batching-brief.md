# Architecture brief: from naive 120-line windows to AST-aware batching

**Status:** step-zero architecture question, **rev 3** (2026-10-02).
Supersedes — or rather, re-scopes — the Approach A windowing plan (rev 8,
PR #9) per Kurt's ruling of 2026-10-01: "The question you are asking is
premature… the correct approach is to find better architecture, not
better thresholds."

Revision history: rev 1 (2026-10-01, research summary + 4 architectures).
rev 2 (2026-10-01 evening, + live smoke tests S0–S4). rev 3 (2026-10-02,
Opus high-effort review round 1: 1 BLOCKER + 6 MAJORS + 9 minors, all
verified against source and folded in — corrected S1 statistics, official
API budgets replacing third-party figures, measured skip-file sizes,
question-addressing requirement, unit-count cap, defined fallback chain,
file-content source, concrete validation gate).

## Kurt's three directives (verbatim intent)

1. **"Jev can run more than one judgement per batched query. Read the
   docs about this and utilize this ability to the maximum potential."**
2. **"A slightly longer processing time is trivial and not a concern…
   It will not be slow for our purposes, regardless."** — the latency
   assumptions behind the 120-line limit are retired as decision input.
3. **"The hard coded algorithm must do the heavy lifting to prepare the
   judgment comparisons for Jev… I wonder if AST/tree-sitter can help us
   group functions and what calls what programmatically… something more
   advanced than naive chunking."**

## What the Jev docs actually say (official sources, re-verified 2026-10-02)

- `POST /v1/systemone` takes ONE `state` (string | object | array) and a
  MAP of questions, each independently and **in parallel evaluated
  against the same state** (docs.typesafe.ai/api, /models).
- **Official budgets (docs.typesafe.ai/models, verified 2026-10-02):**
  64k tokens per request covering `state` + all questions combined, AND
  32k tokens for `state` + the single longest question. Over-budget
  requests fail with `max_tokens_exceeded` — **the server does NOT
  truncate** (rev 2's "~80k chars with an explicit truncation note" came
  from a third-party integration doc and is retired).
- The response carries `usage.input_tokens` (API reference examples) —
  the per-call guard reads this, not a char estimate.
- **Question-addressing is a documented feature** (learnjev.com
  "writing-state", citing docs.typesafe.ai/concepts/state): questions
  about one part of structured state name that part in the instructions
  with a **backticked dot-and-index path** (`` `units[3].code_after_change`
  ``). The question ID itself "is not sent to the underlying model and is
  not used in inference" (API reference, `‹question id›` param) — so
  addressing MUST live in the instruction text and/or state field names,
  which is exactly what rev 2's probe design failed to do (see M1 below).
- "Context rot" is a named TypeSafe failure mode for jev-1.13: accuracy
  falls as state grows with unrelated content (model-jaggedness page).

**Today's sor does the opposite of batching:** `jev_ask(state=<one
cluster>, questions=<rubric for that cluster>)` — one HTTP round-trip
per cluster (measured ~430 ms each on the PR #43 sweep: 12,915 ms / 30
calls), and `MAX_HUNK_LINES=120` exists mainly to keep that per-call
state small. Both constraints are self-imposed.

## What the research says about AST-aware chunking (verified 2026-10-01)

- tree-sitter is the standard tool: error-tolerant (parses files that
  don't compile), fast (designed for per-keystroke reparse), one API
  across 19+ languages via the `tree-sitter-languages` wheel (or one
  package per language: `tree_sitter_python`, `tree_sitter_typescript`).
  NOT currently a sor dependency — sor is stdlib-only. Adopting it is a
  deliberate dependency-policy change (proposed: optional extra, below).
- cAST (CMU/Augment Code): AST-boundary chunking beats fixed-size
  windows by +1.8–4.3 recall@5 on RepoEval. Fixed windows "halve
  functions, strand imports and decorators."
- Blast-radius pattern (kenimoto.dev write-ups, code-review-graph): parse
  once → nodes (functions/classes) + edges (calls/imports) → SQLite →
  for each changed symbol, BFS hop-2 callers → the model reviews the
  union of diff + callers. Reported 6.8x fewer tokens on average, up to
  49x on monorepos, with BETTER comments ("the agent finally reads the
  right files"). Hop-2 is where signal flips to noise.
- Known limits: cross-file type resolution is approximate; dynamic
  dispatch and reflection defeat static call graphs; tree-sitter gives
  syntax trees, not semantic analysis.

## Candidate architectures

**Arch 1 — Batched per-file judging (minimal change, big win).**
Deterministic layer groups a file's changed clusters; ONE Jev call gets
`state = {"units": [unit_0, unit_1, …]}` with questions keyed
`u0_bug`, `u1_bug`, … and instructions addressing units by backticked
path (`units[0].code_after_change`). Every file = 1 call regardless of
unit count, subject to the unit-count cap below. Kept-cluster semantics,
verdicts, gates unchanged — only the transport batches. 10-unit PRs drop
from 10+1 calls to 2–3.

**Arch 2 — AST-grouped review units (replaces naive windows).**
Parse the post-change file; oversized change regions are grouped by
syntax nodes (whole functions/methods/classes), never mid-function cuts.
A 491-line file touching 3 functions becomes 3 review units with real
boundaries + a shared file-context header (imports, class doc,
signature). Fallback chain (defined): stdlib `ast` (Python) / tree-sitter
(optional extra: `tree-sitter-languages`) → if both unavailable or the
language is unsupported → line windows (today's cutter, kept as final
fallback). If a single unit still exceeds the per-call guard, it is
split at the next-lower AST nesting level (statements) before line
windows are used.

**Arch 3 — Blast-radius context enrichment.**
Build the call graph for changed files (nodes + call/import edges in
SQLite); for each review unit, prepend read-only context: the unit's
enclosing class, direct callees' signatures, and hop-1/2 callers.
Judgments see what the function touches and who depends on it. This is
context ENRICHMENT — findings stay anchored to changed lines, keeping
the golden/scorer machinery intact. **Note (rev 3, honesty): sor is a
diff-only tool — it does not read tree files today, so this architecture
requires a new file-access surface (see "File-content source" below).**

**Arch 4 — Staged triage (cheapest first).**
Call 1: whole-file state, cheap questions per region ("does this region
contain risky logic?" noul). Regions above threshold get full review
units; the rest get a cheap pass. Risk-based, could combine with 1–3.

## Why this re-opens the spec honestly

Approach A (rev 8 plan) solved "oversize hunks get skipped" with
line-window surgery: proportional −/+ pairing, zero interior context,
ratio floors, per-run caps, window breakers. Much of that complexity
exists BECAUSE cuts were naive. AST grouping removes the cause: cuts
land on semantic boundaries, and batching removes the per-call cost
pressure that motivated caps. The honest-verdict machinery (Step 0′:
base_verdict, unjudged counting, gate_run) survives intact — it is
orthogonal to how units are cut.

Open questions for review:

1. Which architecture (or combination) maximizes judgment quality per
   Kurt's directives, at acceptable complexity?
2. Batching semantics: does per-file state with per-unit questions vs
   per-unit calls change answer quality? (Testable; see S1 evidence and
   the required S1b/S4b gates below.)
3. Dependency policy: add `tree_sitter` + per-language grammars (binary
   wheels) to a stdlib-only tool? Proposed: optional extra with stdlib
   `ast` covering Python and line-window fallback for the rest; revisit
   core-dependency status after the corpus gate.
4. What happens to the Approach A plan: discard, or keep Step 0′ +
   honest-verdict work and replace the window-cutting core?
5. Latency budget: with "slower is fine" as ruling, what replaces the
   120-line limit as the per-call state guard — see "The guard" below.
6. Validation: see "Validation gate" below (rev 3 makes this concrete).

## Smoke-test evidence (rev 2 experiments, statistics corrected in rev 3)

Reviewer subagent's full report: /tmp/ast-arch-review.md (REQUEST
CHANGES verdict, answered all 6 open questions). Opus r1 (this repo's
review log) then audited rev 2's claims; the corrections below are
Opus's, each verified against the raw run data.

**S1 — batching shifts scores; the rev-2 "0/30 agree" headline was a
broken agreement field, and the "systematically LOWER" claim was wrong.**
PR curated-journal #43 (commit 99711a4, 30 judged clusters):
- Per-cluster (today's way): 30 calls, 12,915 ms (~430 ms/call). One
  batched call (array state, 90 questions): 345 ms — 37x faster.
- The `agree` boolean in the S1 report is broken: `src/app/import.tsx:23`
  scored sev 0.58 vs 0.59 and is_real 0.31 vs 0.32 (Δ≈0.01) yet
  `agree: false`. Recomputed with the real gate (is_real ≥ 0.5 AND
  sev ≥ 1, the compose() reporting rule): **10 of 30 clusters flip
  gate status between arms; mean |Δsev| = 0.709.**
- Direction is **contrast-dependent, not one-way**: the GLM probe's
  n=2 test (cluster a: `a - b` → `a + b`, a defect-FREE fix; cluster b:
  hardcoded password) showed batched scores HIGHER for both (a: 1.42 vs
  1.05; b: 2.66 vs 2.41) — a weak signal next to a strong one reads
  *stronger*, opposite to rev 2's shrink-toward-zero claim. PR #43's
  batched arm skewing lower on bug-containing clusters does not
  generalize; both directions occur.
- **Crucial context Opus exposed (BLOCKER-grade framing fix): PR #43 is
  a DEFECT-FREE head** (SHA-pinned negative golden,
  `examples/cj-field-goldens.tsv`, expected-issues=0). The batched arm
  reported **0 findings — the CORRECT answer**. The per-cluster arm's 11
  findings were the false positives. So on this PR batching IMPROVED
  accuracy; what the data shows is score mobility (10/30 gate flips),
  not that batching degrades judgments. Whether batched scores on
  bug-containing clusters stay calibrated is exactly what the required
  A/B gates must measure on defect-positive fixtures.
- Controls stand: single-vs-single repeats agree 5/5 within ±0.09 (the
  mobility is a batching effect, not noise); the drop/arm-shift comes
  from the multi-item state, not question tagging (tagged single-state
  control agreed with untagged singles on code clusters). Batched
  results are stable across repeats (repro 3x at n=5).

**S4 — state-size degradation is CONTENT-dependent, not size-dependent
— and its shape does not match the adopted design (Opus m6).** Synthetic
filler + 5 planted defects, questions of the form "find the defect in
this whole state":
- Neutral-text filler: found 1/4 specifics at 20k AND 80k — but one
  2-defect probe at 20k found both, at front/middle/back equally
  (position irrelevant). 80k finds only 1/4 with confidence 0.88–0.99
  (confidently wrong).
- Code-like filler: 3/4 found at 20k AND 80k — identical at both sizes.
  Latency flat 143–266 ms across all rungs (5k → 80k chars, 14.3k input
  tokens at 80k).
- **Scope limit (rev 3): S4 tested whole-state defect SEARCH. The
  adopted design is per-unit ADDRESSED questions over a multi-item
  state — a different task shape with only S1-grade evidence so far.**
  S4b (below) closes this. The corpus-max claim is also corrected:
  see "Measured skip census" — real files reach 114k chars.

**S2 — AST units on the real PR #43 offenders (tree-sitter, live).**
- `importMachine.test.ts` (151 changed lines): naive = 2 windows with
  arbitrary cuts; AST = 16 top-level units, largest 117 lines — fits.
- `importMachine.ts` (273 changed lines): naive = 3 windows; AST = 9
  units, largest 199 lines (`createImportMachine` — one xstate machine
  factory). One giant function is the honest unit; cutting it
  mid-body (naive) is strictly worse.
- Reviewer's dry-run (Python stdlib ast): the 491-line `mine_corpus.py`
  = 21 units, largest 87 lines — all fit. `wisdom.ts` (542 lines, the
  CTI PR #22 blind spot) = 50 units, largest 4.9k chars.
- Coverage story: Arch 1 (batch transport, no 120-line limit) + Arch 2
  (AST units) removes the hunk>120 skip class entirely; Arch 2 alone
  changes cut quality.

**S3 — call-graph blast radius on PR #43.** `importMachine.ts`
exports 5 symbols; exactly 2 files import them (`import.tsx`,
its test). Hop-1 enrichment ≈ a handful of lines per unit on this
corpus. Cheap to build, low context cost — but its value is UNPROVEN
(the only architecture of the four with no quality evidence). Deferred
per the reviewer's recommendation, revisit after S1b/S4b settle.

## Measured skip census (rev 3, answers Opus m5's RESEARCH_REQUEST)

Char counts of oversized skips recorded across the v06-postmerge corpus
runs (`corpus/work/runs/v06-postmerge/**`, `skipped[]` with reason
"hunk>120 lines"; 37 unique oversized CODE files; sizes measured in
local checkouts — approximate where the checkout rev differs from the
run's pinned SHA). Largest:

| file | max line_end | chars (approx) |
|---|---|---|
| curated-thoughts `src-tauri/src/okf/write.rs` | 1944 | **114,454** |
| clanker `__tests__/chatComposer.test.tsx` | 1771 | **72,465** |
| sor `scripts/mine_corpus.py` | 491 | 33,610 |
| clanker `src/hooks/useAIChat.ts` | 224 | 25,070 |
| sor `scripts/sweep-thresholds.py` | 334 | 27,427 |
| CTI `integrations/hermes/scripts/ct_preflight.py` | 437 | 21,558 |
| sor `tests/test_field_evals.py` | 486 | 20,751 |

Rev 2's "corpus max is 24.0k" measured only the two #43 offender files,
not the skip population. **Real skipped files reach 114k chars — a
whole-file state for `write.rs` would exceed even the official 64k-token
budget. The per-call input_tokens guard is therefore mandatory, not
defensive, and whole-file states are NOT universally safe.** (Test-heavy
files like `tests/test_ct_doctor.py`, 1240 changed lines, also exceed
any whole-file comfort zone.)

## Architecture answer (rev 3, pending Opus round 2 + Kurt)

**Adopt: Arch 1 restricted to per-file batching + Arch 2 AST units
(fallback chain: stdlib `ast` → tree-sitter optional extra → line
windows; over-cap units split at next AST nesting level before line
windows). Batch the PR-level digest aggressively (proven 37x). Do NOT
batch judgment questions across files. Keep Step 0′ + honest-verdict +
Gate-3 framework; cancel the window-cutting core of Approach A rev 8
(proportional pairing, ratio floors, window breakers — cause removed).
Arch 3 deferred pending evidence; Arch 4 documented escape hatch only,
never default.**

Binding design requirements added in rev 3:

1. **Question addressing (fixes rev 2's probe design):** every state
   item carries an explicit `unit_id` field (e.g. `{"unit_id": "u3",
   "file": …, "code_after_change": […]}`) and every question names its
   unit with the documented backticked path (`units[3].code_after_change`).
   The API reference confirms question IDs never reach the model —
   addressing must be in instructions/state, and rev 2's probes (prose
   naming only) under-tested exactly this mechanism. S1b re-runs WITH
   addressing.
2. **Unit-count cap (new, closes the unbounded-N hole):** per-file calls
   cap at `MAX_UNITS_PER_CALL = 24` units. Overflow: largest-units-first
   keeps 24, the remainder are line-windowed and folded into a SECOND
   call for the same file (deterministic, logged). The existing global
   `--max-hunks 40` stays as the outer bound across files.
3. **The guard replacing MAX_HUNK_LINES:** per-call `usage.input_tokens`
   logged on every call. Budgets (official): 64k tokens state+questions,
   32k state+longest-question; over-budget = `max_tokens_exceeded`, no
   server truncation. sor enforces: soft cap ~40k input_tokens → split
   the call's unit set (AST-fragment splitting, units redistributed to
   a follow-up call); hard stop before the 64k budget — never send a
   request predicted to exceed ~60k input_tokens (estimate pre-send from
   chars/4, confirm from usage, and alert if estimate and usage diverge
   >25%).
4. **File-content source (new, required by Arch 2/3):** units are cut
   from the post-change file image, obtained via `git show <diff
   head_sha>:<path>` in the target repo — no working-tree reads, no
   tree-walk. Diff hunks map onto unit line ranges computed from that
   image. This keeps sor diff-scoped (the references_remaining scope
   contract at system_one_reviewer.py:834 is unchanged) while letting
   AST grouping see real boundaries.
5. **Provider parity (new):** the laya provider path (`laya_ask` →
   `router.predict`, system_one_reviewer.py:301-309) must accept the
   same array/object state shape; a parity check (one batched laya call
   in CI-smoke shape) is part of the plan's gate. If local `router.
   predict` rejects multi-item state, laya keeps per-unit calls and the
   transport difference is logged per run.
6. **Validation gate (concrete, replaces "strict recall not dropped"):**
   - **G-A (recall, addressed units):** 24 rescued goldens + corpus
     before/after replay (S5, 108 ledgers, free) through the NEW
     transport (batched + addressed + AST units). Gate: reported
     BLOCKER/MAJOR findings per golden within the same verdict class;
     strict recall not lower than the per-cluster baseline.
   - **G-B (batching A/B on defect-positive fixtures):** the 20–40-
     cluster fixture A/B (S1b) re-run with unit_id addressing: per-unit
     calls vs per-file batched calls on fixtures with KNOWN planted
     defects. Gate: batched arm finds ≥ the planted defects the
     per-unit arm finds (calibration, not just correlation); gate flips
     ≤ 2/30 and mean |Δsev| ≤ 0.35, else per-file batching is rejected
     and per-unit calls ship with AST units only (still a big win: no
     120-line skips).
   - **G-C (FP census):** the 5 negative goldens (cj-field-goldens.tsv)
     under the new transport: eval_negative blocker_major count must
     not increase vs v0.3b baseline. PR #43's batched arm already
     posted 0 (correct) — this gate checks it stays honest.
   - **G-D (addressing ablation, small):** S1b shape WITH vs WITHOUT
     unit_id/backtick addressing, n=10. If addressed-batched matches
     per-unit calls but unaddressed-batched drifts, the rev-2 S1 shift
     was substantially an addressing artifact — record which, since it
     determines whether cross-contamination was ever real at n=30.

## Remaining before plan

(a) S1b per-file A/B **with unit_id addressing** on multi-cluster
defect-positive fixtures (settles batching + addressing together;
G-B/G-D), (b) S4b addressed-shape size probe (S4's whole-state search
shape does not transfer to the adopted design), (c) laya state-shape
parity check, (d) Opus review round 2 of this rev-3 brief, (e) Kurt
sign-off.

## Kurt rulings still needed

1. **Dependency policy:** tree-sitter as optional extra (stdlib `ast`
   for Python, line-window fallback elsewhere) vs core dependency.
   Recommended: optional extra first, promote after G-A/G-B pass.
2. **If G-B fails calibration:** ship AST units + per-unit calls (no
   batching for judgment questions) and batch only the PR-level digest —
   confirm this fallback satisfies directive 1 ("maximum potential") or
   whether he wants more gate rounds first.
3. Confirmation that `MAX_UNITS_PER_CALL = 24` and the ~40k
   input_tokens soft cap are acceptable starting constants (both
   adjustable via CLI flags from day one).
