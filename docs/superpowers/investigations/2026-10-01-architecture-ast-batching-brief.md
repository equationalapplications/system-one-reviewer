# Architecture brief: from naive 120-line windows to AST-aware batching

**Status:** step-zero architecture question, rev 1 (2026-10-01). Supersedes —
or rather, re-scopes — the Approach A windowing plan (rev 8, PR #9) per
Kurt's ruling of 2026-10-01: "The question you are asking is premature…
the correct approach is to find better architecture, not better
thresholds."

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

## What the Jev docs actually say (verified 2026-10-01)

- `POST /v1/systemone` takes ONE `state` (string | object | array) and a
  MAP of questions, each independently and **in parallel evaluated
  against the same state**. Per the API reference: "asking ten questions
  costs roughly the latency of asking one."
- State supports arrays: "Context made of multiple text items" — so one
  call can carry a whole file or several related fragments as state, with
  per-fragment questions keyed by ID.
- Typed answers (noul/score/choice) come back keyed by the question IDs
  we chose — one round-trip fans out to N judgments.
- Practical context scale (third-party TypeSafe integration docs): code
  material up to ~80,000 chars (~20k tokens) per request against Jev's
  32k context, with an explicit truncation note. Per-call state is far
  from the constraint we assumed.

**Today's sor does the opposite of batching:** `jev_ask(state=<one
cluster>, questions=<rubric for that cluster>)` — one HTTP round-trip
per cluster (~165ms each), and `MAX_HUNK_LINES=120` exists mainly to
keep that per-call state small. Both constraints are self-imposed.

## What the research says about AST-aware chunking (verified 2026-10-01)

- tree-sitter is the standard tool: error-tolerant (parses files that
  don't compile), fast (designed for per-keystroke reparse), one API
  across 19+ languages via the `tree-sitter-languages` wheel (or one
  package per language: `tree_sitter_python`, `tree_sitter_typescript`).
  NOT currently a sor dependency — sor is stdlib-only. Adopting it is a
  deliberate dependency-policy change.
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
`state = [cluster_1_context, cluster_2_context, …]` (array) with
questions keyed `c1_bug`, `c2_bug`, … Every file = 1 call regardless of
cluster count. Kept-cluster semantics, verdicts, gates unchanged — only
the transport batches. 10-cluster PRs drop from 10+1 calls to 2–3.

**Arch 2 — AST-grouped review units (replaces naive windows).**
tree-sitter parses the post-change file; oversized change regions are
grouped by syntax nodes (whole functions/methods/classes), never
mid-function cuts. A 491-line file touching 3 functions becomes 3
review units with real boundaries + a shared file-context header
(imports, class doc, signature). The ratio-floor/zero-interior-context
machinery from Approach A becomes mostly unnecessary — the hard cuts
that needed those rules no longer happen. Fallback to line windows for
unsupported languages (conservative, still honest).

**Arch 3 — Blast-radius context enrichment.**
Build the call graph for changed files (nodes + call/import edges in
SQLite); for each review unit, prepend read-only context: the unit's
enclosing class, direct callees' signatures, and hop-1/2 callers.
Judgments see what the function touches and who depends on it. This is
context ENRICHMENT — findings stay anchored to changed lines, keeping
the golden/scorer machinery intact.

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
2. Batching semantics: do parallel questions against a shared multi-item
   state risk cross-contamination between clusters (one cluster's content
   biasing another's answer)? Does per-file state with per-cluster
   questions vs per-cluster calls change answer quality? (Testable on the
   fixtures + corpus.)
3. Dependency policy: add `tree_sitter` + per-language grammars (binary
   wheels) to a stdlib-only tool? Optional-extra with fallback, or core
   dependency?
4. What happens to the Approach A plan: discard, or keep Step 0′ +
   honest-verdict work and replace the window-cutting core?
5. Latency budget: with "slower is fine" as ruling, what replaces the
   120-line limit as the per-call state guard — Jev's documented ~80k
   chars, with an explicit truncation note?
6. Validation: do the existing gates (corpus before/after, 24 rescued
   goldens, strict recall not dropped) still measure the right things for
   an AST+batched design? What new gate is needed for batching-induced
   cross-contamination?
