# Architecture brief: from naive 120-line windows to AST-aware batching

**Status:** step-zero architecture question, **rev 4** (2026-10-02).
Supersedes — or rather, re-scopes — the Approach A windowing plan (rev 8,
PR #9) per Kurt's ruling of 2026-10-01: "The question you are asking is
premature… the correct approach is to find better architecture, not
better thresholds."

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

## What the Jev docs actually say (official, verified 2026-10-01/02)

- `POST /v1/systemone` takes ONE `state` (string | object | array) and a
  MAP of questions, each independently and **in parallel evaluated
  against the same state**. "asking ten questions costs roughly the
  latency of asking one."
- **Two budgets (docs.typesafe.ai/models, verbatim):** "The 64k budget
  covers the `state` plus all questions combined; the 32k budget applies
  to the `state` plus the single longest question." The 32k rule is the
  binding one for code review states.
- **Addressing is a documented feature:** question keys "are not sent to
  the underlying model and are not used in inference"; questions point at
  state slices "using a backticked dot-and-index path" (e.g.
  `` `units[3].code_after_change` ``). A batched question that does not
  name its item by path leaves the model to guess which slice to judge —
  that is the S1 contamination mechanism below.
- **`usage.input_tokens` is request-level:** the response `usage` object
  is "Token usage for the request" — it counts the state plus ALL
  questions, not just the longest one. Usable as the 64k check; the 32k
  check must be estimated (state + longest question) before sending.
- **Over-budget failure:** NOT in the official errors table (401/422
  only). Community-measured (jevwiki/jevaiguide probes, 2026-09): HTTP
  **400** with body `{"detail":{"error_type":"max_tokens_exceeded"}}`,
  cutoff right at ~32k tokens even when far below 64k, no retry. Treat
  as observed behavior: split and retry, never count toward fail-open.
- Measured chars→tokens on real content: ~3.24 chars/token for TypeScript
  source (our own `wisdom.ts` probe: 23,748 chars → 7,322 input tokens);
  ~3 chars/token for dense log text (third-party probes); ~5.6 chars/
  token for neutral prose (our S4: 80k chars → 14.3k tokens). For code,
  estimate tokens ≈ chars/3.

**Today's sor does the opposite of batching:** one HTTP round-trip per
cluster (~430 ms each measured: 12,915 ms / 30 calls), and
`MAX_HUNK_LINES=120` exists mainly to keep that per-call state small.
Both constraints are self-imposed.

## What the research says about AST-aware chunking (verified 2026-10-01)

- tree-sitter is the standard tool: error-tolerant, fast, one API across
  many languages. NOT currently a sor dependency — sor is stdlib-only.
  Adopting it is a deliberate dependency-policy change (see m1 note in
  Revision history: `tree-sitter-languages` is community-reported as
  unmaintained; prefer `tree-sitter-language-pack` or per-language
  wheels — verify at implementation time).
- cAST (CMU/Augment Code): AST-boundary chunking beats fixed-size
  windows by +1.8–4.3 recall@5 on RepoEval.
- Blast-radius pattern: parse once → nodes + edges → SQLite → hop-1/2
  callers as context. Reported 6.8x fewer tokens on average, with better
  comments. Hop-2 is where signal flips to noise.
- Known limits: cross-file type resolution is approximate; dynamic
  dispatch and reflection defeat static call graphs.
- Official failure-modes doc lists "large state full of irrelevant
  detail" for jev-1.13 ("context rot") — consistent with our S1/S4.

## Candidate architectures

**Arch 1 — Batched per-file judging (transport change).**
Deterministic layer groups a file's clusters; ONE Jev call gets
`state = [unit_0, unit_1, …]` with per-unit question groups keyed
`u<N>_<field>` whose instructions address their item by backticked path.
Every file = 1 call (split into 2+ when the guard below trips).
Kept-cluster semantics, verdicts, gates unchanged — only the transport
batches.

**Arch 2 — AST-grouped units (cluster as unit of judgment).**
tree-sitter (stdlib `ast` for Python first) gives semantic boundaries.
**The CLUSTER remains the unit of judgment — this is load-bearing:**
`compose()` verdict math (any BLOCKER or ≥2 MAJORs → Changes requested),
the golden scorer's ±1-line anchor matching, per-cluster rubric routing
by `change_type`, the ±4-line `references_remaining` window, and every
cluster-counted counter all stay exactly as shipped. AST contributes
exactly two things: (a) **context** — each cluster's state item is
enriched with its enclosing function/class text; (b) **split points** —
an oversized cluster is cut at syntax boundaries into sub-clusters, EACH
keeping its own anchor line and its own full question triple. Merging
clusters into one judged unit would change verdict and scoring semantics
(rev 3's draft did this; r2-M2 rejected it). Fallback to line windows
for unsupported languages and for oversized single statements.

**Arch 3 — Blast-radius context enrichment.** UNCHANGED from rev 3:
call graph for changed files; for each unit prepend enclosing class,
direct callees' signatures, hop-1/2 callers. Findings stay anchored to
changed lines. UNPROVEN and DEFERRED; revisit after S1 settles.

**Arch 4 — Staged triage.** UNCHANGED: cheap whole-file risk pass first,
full units above threshold. Escape hatch only, never default.

## Smoke-test results (rev 2/3, 2026-10-01 evening — live Jev, real corpus PRs)

Reviewer subagent's full report: /tmp/ast-arch-review.md (REQUEST
CHANGES verdict, answered all 6 open questions). Live runs confirm:

**S1 — per-PR batching moves scores DOWN almost uniformly; calibration
unknown (stated per r2-M3).** PR curated-journal #43 (commit 99711a4,
30 judged clusters, defect-free head, ground truth 0 findings):
- Per-cluster (today): 30 calls, 12,915 ms. One batched call (array
  state, 90 questions): 345 ms — 37x faster.
- 28 of 30 batched severities are LOWER (mean |Δsev| = 0.709; worst
  2.13 → 0.60). Only `:23` (+0.01) and `:145` (+0.15) rose.
- **The batched arm was NOT finding-free:** `import.tsx:7` scored
  is_real 0.68 / sev 1.86 — a reported false-positive MAJOR under the
  shipped gate. So the score is **1 reported FP major vs 11**, not
  "0 vs 11". A uniform downward shift cuts false positives on a
  defect-free PR for free and would hide real bugs the same way; it
  does NOT demonstrate improved accuracy.
- Controls: single-vs-single repeats agree within the single-call noise
  floor (±0.09 on 5 repeats of one cluster; ±0.2 across positions —
  use **±0.2 as the conservative noise floor** for gate design). The
  n=2 S0 probe moved OPPOSITE directions (+0.25/−0.37) and its cluster
  a is a defect-FREE fix (`a - b` → `a + b`) — S0 is a contamination
  existence proof, not evidence of direction.
- **Ruling: per-PR mega-batching is DEAD as a judgment path.** S1 was
  per-PR (one call, 5 files, 90 questions): it says nothing directly
  about per-FILE batching, which bounds contamination to one file's own
  clusters. Per-file A/B on matched fixtures is gate G-B below.
  Batching IS proven safe and 37x faster where no per-item judgment
  calibration is at stake (the PR-level digest).

**S4 — state-size degradation is CONTENT-dependent, not size-dependent.**
Neutral-text filler: 1/4 specifics found at 20k AND 80k chars (confident
wrong, 0.88–0.99); code-like filler: 3/4 at both sizes; latency flat
143–266 ms (5k → 80k chars, 14.3k input tokens at 80k). Dilution lives
in the content, not a hard size wall. NOTE: S4 measured whole-state
"find the planted defect" questions — NOT the adopted per-unit addressing
shape; it bounds context-rot risk but does not validate the design (the
only evidence for/against that shape is S1, which is why G-B exists).

**S2 — AST units on the real PR #43 offenders (tree-sitter, live).**
- `importMachine.test.ts` (151 changed lines): naive = 2 windows with
  arbitrary cuts; AST = 16 top-level units, largest 117 lines.
- `importMachine.ts` (273 changed lines): naive = 3 windows; AST = 9
  units, largest 199 lines (`createImportMachine` — one xstate machine
  factory; the honest unit).
- Reviewer's dry-run (Python stdlib `ast`): 491-line `mine_corpus.py` =
  21 units, largest 87 lines; `wisdom.ts` (542 lines) = 50 units,
  largest 4.9k chars.
- Coverage: Arch 1 + Arch 2 removes the hunk>120 skip class entirely.

**S3 — call-graph blast radius on PR #43.** 5 exported symbols, exactly
2 importing files, hop-1 enrichment ≈ a handful of lines per unit. Cheap,
low context cost — value UNPROVEN. Deferred per S3 above.

**Skipped-file census (r1-m5, measured).** 37 unique code files skipped
as hunk>120 across the v06-postmerge corpus runs. Char counts of the
local-checkout copies: 5 files over 25k chars, up to `write.rs` at
114,454 chars (~35k state tokens — over the 32k state+longest-question
budget, so even per-file it must ship as MULTIPLE calls), plus
`chatComposer.test.tsx` 72k, `mine_corpus.py` 34k, `sweep-thresholds.py`
27k, `useAIChat.ts` 25k. (Caveat: local-checkout sizes, not pinned-SHA
sizes.) The brief's earlier "corpus max 24.0k" was wrong — that was the
max OFFENDER measured, not the max skipped file.

## Architecture answer (rev 4, pending Opus + Kurt)

**Adopt: Arch 1 restricted to per-file batching + Arch 2 with the
cluster as the unit of judgment (stdlib `ast` first, tree-sitter as a
lazy opportunistic import with line-window fallback). Batch the
PR-level digest aggressively (proven 37x). Do NOT batch judgment
questions across files. Keep Step 0′ + honest-verdict + Gate-3
framework; cancel the window-cutting core of Approach A rev 8. Arch 3
deferred pending evidence; Arch 4 documented escape hatch only.**

Concretely, one batched per-file call looks like:

- `state` = array of the file's units IN CLUSTER ORDER: each item carries
  `unit_id`, the cluster's `code_before_change`/`code_after_change`
  (r2-M1: the rubric judges CHANGES — a post-image alone cannot show
  `a - b` → `a + b`), enclosing-function context from the AST parse,
  and the cluster's `change_type`.
- Questions: per unit a full triple `u<N>_severity` (score),
  `u<N>_is_real` (noul), `u<N>_category` (choice), each instruction
  addressing its item by backticked path (`` `units[3].code_after_change` ``).
  Deletion-rubric clusters keep the DELETION_QUESTIONS variant set
  (`references_remaining` included); mixed rubrics batch in one call
  with rubric-specific key groups. At the 24-unit cap that is ≤72
  short questions ≈ well under 1k tokens (third-party measure: 20 short
  questions ≈ 256 tokens) — question overhead is noise; the state is
  the budget.
- Answers parse PER UNIT: one missing key marks only that unit
  `parse_error` (r2-M4) — never discard the whole call's answers.

## The guard that replaces MAX_HUNK_LINES (r2-B1)

The 32k budget (state + single longest question) is the binding limit,
so the guard is built on it, not on 64k:

- **Estimate** state tokens ≈ chars/3 for code; longest-question tokens
  measured, not estimated. **Soft cap: estimated state + longest
  question ≤ 28k tokens per call.** Second check: total request ≤ 56k
  (vs 64k).
- **Hard rule: never SEND an estimated-over-cap call.** A file whose
  units don't fit splits into a second batched call (still AST units —
  never line-window the SMALLER pieces back into worse cuts).
- **Runtime over-budget** (HTTP 400 `max_tokens_exceeded`): split the
  call's units in half and retry — and this error class NEVER counts
  toward `CALL_FAIL_LIMIT` or fail-open. These are the files the
  redesign exists to rescue; failing them open would reintroduce the
  blind spot.
- The 40k-chars class of caps from rev 2/3 is retired: chars are a bad
  token proxy in BOTH directions (code under-counted ~19% by chars/4,
  prose over-counted ~40%). The estimator is advisory; the send-gate is
  the estimate check, and `usage.input_tokens` (request-level) is
  logged every call to recalibrate chars/token per language.

## Requirements for the plan

1. **Per-mode file-content source (r2-M1).** AST parses run against the
   image the diff actually applied to:
   - `--range`/`--pr`: `git show <head_sha>:<path>` (post) +
     `git show <merge-base>:<path>` (pre).
   - `--staged`: `git show :<path>` (index) — NOT `HEAD:path`, which is
     the pre-change image in this mode.
   - `--uncommitted`: working-tree read as a DOCUMENTED EXCEPTION to the
     diff-only principle (the working tree IS the post-image here), or
     AST units disabled in this mode. Decision in plan.
   - Deletion-only and whole-file-deletion clusters STAY cluster-based
     (no post-image exists; `hunk_state` before/after text already
     carries what the rubric needs).
2. **Cluster-as-unit semantics (r2-M2).** No merged-unit judging. Every
   cluster (or AST sub-cluster of an oversized cluster) keeps its own
   anchor line and full question triple. `compose()`, the scorer,
   rubric routing, the `references_remaining` window, and all
   cluster-counted counters are untouched.
3. **Failure semantics (r2-M4).** Per-unit answer parsing; per-cluster
   unjudged counting feeds the existing incomplete-review downgrade; a
   failed per-file call counts as ONE failure toward the consecutive
   counter (a split-retry failure adds one more); two consecutive
   failed CALLS still fail open exactly as today.
4. **Thresholds stated per rubric (r2-m3).** Code-change findings:
   is_real ≥ 0.50. Deletion findings: is_real ≥ 0.70
   (`DELETION_REAL_THRESHOLD`). Never quote a single threshold.
5. **Laya parity gate is a VALUE check (r2-m6).** `laya_ask` accepting
   array state is not parity: the gate compares batched per-unit answer
   VALUES against per-unit single calls on a fixture, same as G-B.
6. **Dependency policy (r2-m1).** No installable-extra mechanism exists
   (single-script project): implement as lazy opportunistic
   `import tree_sitter*` (the laya pattern) with stdlib `ast` for
   Python and line-window fallback otherwise. Verify the maintained
   wheel choice (`tree-sitter-language-pack` vs per-language) at
   implementation time.
7. **Honest fallback (r2-M5).** If G-B fails per-file batching: the
   fallback is per-cluster calls (today's transport) WITH AST context
   enrichment — i.e. NO judgment batching at all; the only batched call
   remaining is the PR-level digest, which was always a single call.
   Kurt's directive-1 question must be answered against that honest
   statement, not against a "37x" that no longer applies.

## Validation gates

- **G-A — coverage:** the hunk>120 skip class is zero on the corpus
  replay; `wisdom.ts`-class files (114k chars) produce AST-split calls
  that all pass the send-gate.
- **G-B — per-file batching A/B (the adoption gate).** Fixture: 20–40
  clusters including multi-cluster files, two arms —
  per-file-batched vs per-cluster. **Defect-positive arm added
  (r2-M3):** #43's PRE-fix revisions as matched fixtures — 3 real
  majors are recorded in `examples/cj-field-goldens.tsv` history (two
  abort races, one signature contract) — plus any corpus golden with
  expected-issues > 0. Pass: gate-flip rate ≤ 5% of clusters (rate, not
  count — r2-m5), mean |Δsev| ≤ 0.2 (at the conservative single-call
  noise floor; contamination measured 0.709 — 3.5x floor), AND the
  defect-positive arm's reported findings survive at equal or better
  recall than per-cluster.
- **G-C — field regression on the negative goldens:** the 5
  defect-free merged heads stay at ≤ 1 reported FP major each (the
  batched arm's own S1 best case is 1: `import.tsx:7`). Verify the
  under-report direction does not eat real findings via G-B's
  defect-positive arm, not via G-C alone.
- **G-D — verifier equivalence replay (S5):** 108 archived ledgers
  re-run through the new transport; verdict + reported-findings
  equality where the old run had no skips (skipped cases are the
  improvement this design exists to make — they are expected to
  differ, toward MORE judged).

## Open decisions for Kurt

1. **D1 (was Q3):** approve lazy tree-sitter opportunistic import as
   the dependency mechanism (no packaging change; README notes it).
2. **D2:** if G-B fails per-file batching, accept the honest fallback
   (per-cluster calls + AST context, no judgment batching) — directive
   1 then applies only to the digest call. Recommended: yes, pending
   G-B evidence either way.
3. **D3:** Arch 3 (call-graph enrichment) stays deferred until G-B
   settles. No ruling needed now.
4. **D4:** `--uncommitted` mode: working-tree read exception, or AST
   units disabled in that mode? Plan-time decision, flagged for Kurt
   because it touches the diff-only principle.
5. **D5:** confirm the smoke-test conclusion that per-PR mega-batching
   is retired as a judgment path (evidence: S1, reproduced 3x).

## Revision history

- **rev 1 (2026-10-01):** initial question draft; 6 open questions.
- **rev 2 (2026-10-01 late):** smoke-test results S1–S4 folded in;
  architecture answer drafted.
- **rev 3 (2026-10-02, commit 6fb0b2b):** Opus r1 (16 findings)
  verified and folded: official docs replace third-party citations;
  per-unit addressing required; S1 overstated claims corrected
  (opposite-direction probe, defect-free cluster a, noise bound);
  24.0k corpus-max claim replaced by measured 37-file skipped census
  (max 114k chars); cluster-as-unit, per-unit parsing, per-mode file
  source, unit cap as split-into-second-call, value-parity laya gate,
  per-rubric thresholds, 5%-rate flip allowance, ±0.2 noise floor,
  honest batching fallback, DEFECT-positive G-B arm.
- **rev 4 (2026-10-02):** Opus r2 (1 BLOCKER, 5 MAJORS, 6 minors)
  verified and folded. B1: guard rebuilt on the 32k
  state+longest-question budget (28k est soft cap, 56k total check,
  chars/3 estimator, split-and-retry on 400, never fail-open on
  over-budget). M1: per-mode file-content sources; deletion clusters
  stay cluster-based; units carry before+after text. M2: cluster
  confirmed as the unit of judgment; AST = context + split points
  only. M3: S1 restated (28/30 down, 1 surviving FP major, no
  "improved accuracy" claim); G-B gains the pre-fix defect-positive
  arm. M4: failure semantics specified. M5: fallback stated honestly
  (no judgment batching in fallback). RESEARCH_REQUESTs answered from
  docs.typesafe.ai (budget wording, request-level `usage`, 400 status
  community-observed).
