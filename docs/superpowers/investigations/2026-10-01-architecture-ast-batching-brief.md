# Architecture brief: from naive 120-line windows to AST-aware batching

**Status:** step-zero architecture question, **rev 6** (2026-10-02).
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

**Directive-1 outcome, stated once (r3-M1):** S1 proved batched
transport is 37x FASTER; it did NOT prove batched judgment is safe —
per-PR batching measurably shifted every score. Per-FILE batching is
the remaining candidate and is adopted ONLY if gate G-B passes. If G-B
fails, no judgment batching ships: the sole multi-question call left is
the PR-level digest, which has always been a single call
(`judge_pr_level`, "One extra round-trip"). There is no further 37x to
bank in the fallback case.

## What the Jev docs actually say (official, verified 2026-10-01/02)

- `POST /v1/systemone` takes ONE `state` (string | object | array) and a
  MAP of questions, each independently and **in parallel evaluated
  against the same state**. "asking ten questions costs roughly the
  latency of asking one." The fan-out pattern doc recommends "putting
  all of the questions your system needs in a single request."
- **Two budgets (docs.typesafe.ai/models, verbatim):** "The 64k budget
  covers the `state` plus all questions combined; the 32k budget applies
  to the `state` plus the single longest question." The 32k rule is the
  binding one for code review states.
- **Addressing is a documented feature** for OBJECT state: question keys
  "are not sent to the underlying model"; questions point at state
  slices "using a backticked dot-and-index path" — every documented
  example (`ticket.messages[0].text`) resolves from an object root.
  Array-root path resolution is NOT documented anywhere official, so the
  design uses an OBJECT state shape (see The wire format) and never
  relies on undocumented array paths (r3-m1).
- **`usage.input_tokens` is request-level:** "Token usage for the
  request" — state plus ALL questions. Usable as the 64k check; the 32k
  check (state + longest question) must be estimated pre-send.
- **Over-budget failure:** NOT in the official errors table (401/422
  only). Community-measured (jevwiki/jevaiguide probes, 2026-09): HTTP
  **400**, body `{"detail":{"error_type":"max_tokens_exceeded"}}`,
  cutoff right at ~32k tokens even when far below 64k, never retried by
  the SDKs. Treated as UNVERIFIED: the runtime match is lenient (400 +
  that `error_type` string in the body) AND the split path terminates
  unconditionally (see The guard) so a misclassified 400 cannot loop.
- Measured chars→tokens on real content: ~3.24 chars/token for
  TypeScript source (our `wisdom.ts` probe: 23,748 chars → 7,322 input
  tokens, request-level); ~3 chars/token dense log text; ~5.6 chars/
  token neutral prose (S4). These calibrate the ADVISORY pre-send
  estimator only — the real gate runs on the serialized payload (r3-M6).

**Today's sor does the opposite of batching:** one HTTP round-trip per
cluster (~430 ms each measured: 12,915 ms / 30 calls), and
`MAX_HUNK_LINES=120` exists mainly to keep that per-call state small.
Both constraints are self-imposed.

## What the research says about AST-aware chunking (verified 2026-10-01)

- tree-sitter is the standard tool: error-tolerant, fast, one API across
  many languages. NOT currently a sor dependency — sor is stdlib-only.
  Adopting it is a deliberate dependency-policy change. Note:
  `tree-sitter-languages` is community-reported unmaintained; prefer
  `tree-sitter-language-pack` or per-language wheels — verify at
  implementation time.
- cAST (CMU/Augment Code): AST-boundary chunking beats fixed-size
  windows by +1.8–4.3 recall@5 on RepoEval.
- Blast-radius pattern: parse once → nodes + edges → SQLite → hop-1/2
  callers as context. Reported 6.8x fewer tokens on average. Hop-2 is
  where signal flips to noise.
- Known limits: cross-file type resolution is approximate; dynamic
  dispatch and reflection defeat static call graphs.
- Official failure-modes doc lists "large state full of irrelevant
  detail" for jev-1.13 ("context rot") — consistent with our S1/S4.

## Candidate architectures

**Arch 1 — Batched per-file judging (transport change).**
Deterministic layer groups a file's clusters; ONE Jev call carries the
file's units (split into 2+ calls when the guard below trips).
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
keeping its own anchor line and its own full question triple.
**Sub-cluster `change_type` inheritance (r3-m3):** a sub-cluster with no
`+` lines INHERITS its parent cluster's `change_type` — a pure-context
slice of a code-change cluster is never re-routed to the deletion
rubric.
**Known semantic consequence, stated (r3-m4):** splitting one logical
change into N sub-clusters means it can now produce N independent
findings — a single change can trip "≥2 MAJORs → Changes requested"
where the unsplit cluster could not, and each sub-finding counts
against golden ±1-line matching separately. G-B measures exactly this
(split clusters are in the fixture set). If G-B shows split-induced
verdict inflation, the cap tightens or splitting falls back to
line-window context, NOT to merged judging.
Fallback to line windows for unsupported languages and oversized single
statements.

**Arch 3 — Blast-radius context enrichment.** Call graph for changed
files; for each unit prepend enclosing class, direct callees'
signatures, hop-1/2 callers. Findings stay anchored to changed lines.
UNPROVEN and DEFERRED; revisit after S1 settles.

**Arch 4 — Staged triage.** Cheap whole-file risk pass first, full units
above threshold. Escape hatch only, never default.

## Smoke-test results (rev 2/3, 2026-10-01 evening — live Jev, real corpus PRs)

Reviewer subagent's full report: /tmp/ast-arch-review.md (REQUEST
CHANGES verdict, answered all 6 open questions). Live runs confirm:

**S1 — per-PR batching moves scores DOWN almost uniformly; calibration
unknown.** PR curated-journal #43 (commit 99711a4, 30 judged clusters,
defect-free head, ground truth 0 findings):
- Per-cluster (today): 30 calls, 12,915 ms. One batched call (array
  state, 90 questions): 345 ms — 37x faster transport.
- 28 of 30 batched severities are LOWER (mean |Δsev| = 0.709; worst
  2.13 → 0.60). Only `:23` (+0.01) and `:145` (+0.15) rose.
- **The batched arm was NOT finding-free:** `import.tsx:7` scored
  is_real 0.68 / sev 1.86 — a reported false-positive MAJOR under the
  shipped gate. So the score is **1 reported FP major vs 11**, not
  "0 vs 11". A uniform downward shift cuts false positives on a
  defect-free PR for free and would hide real bugs the same way; it
  does NOT demonstrate improved accuracy.
- Stability: 3 repeated batched runs (n=5 clusters each) returned
  stable batched scores — consistent bias, not variance.
- Controls: single-vs-single repeats agree within the single-call noise
  floor (±0.09 across 5 repeats of one cluster; ±0.2 worst-case across
  positions — carried into G-B's calibration design as a prior, to be
  re-measured on the fixture itself).
- The n=2 S0 probe moved OPPOSITE directions (+0.25/−0.37) and its
  cluster a is a defect-FREE fix (`a - b` → `a + b`) — S0 is a
  contamination existence proof, not evidence of direction.
- **S1′ (r4-MAJOR-4, 2026-10-02): the shift is NOT an addressing
  artifact.** The r4 reviewer's hypothesis — S1's questions named
  clusters in prose while state items carried no resolvable id, so the
  model may have been scoring "the whole PR" 30 times — is now
  excluded: S1′ re-ran the same 30 clusters through the ADOPTED wire
  format (object state, `units[i]` items, documented backticked-path
  instructions). The shift PERSISTS: per-PR mean signed Δsev **−0.63**
  (26/30 lower, 13/30 gate flips), per-file **−0.55** (23/30 lower,
  14/30 gate flips) — same direction, same magnitude as S1's −0.71.
  Data: `/tmp/s1prime_report.json`; probe:
  `~/.hermes/cache/scratch/s1prime_probe.py`.
- **Ruling (updated by S1′): per-PR mega-batching is DEAD as a judgment
  path — with addressing ruled out, the contamination explanation
  stands.** And the S1′ per-file arm means per-FILE judgment batching
  now shows the SAME systematic bias at file scale; the earlier "per-
  file is still open / contamination bounded" framing is retired. The
  working default becomes **per-cluster transport + AST context
  enrichment**, with per-file batching allowed back ONLY if gate G-B —
  run on the adopted wire format, judged on the S1′-informed signed
  criteria below — shows the shift small enough to accept on the
  defect-positive criterion. Judgment-batching Kurt's directive 1
  survives in the digest call, the AST-unit fan-out (more units judged
  per call WITHOUT shared mega-state is the honest reading of "more
  than one judgement per batched query" if G-B fails), and staged
  triage (Arch 4) as an escape hatch.

**S4 — state-size degradation is CONTENT-dependent, not size-dependent.**
Neutral-text filler: 1/4 specifics found at 20k AND 80k chars (confident
wrong, 0.88–0.99); code-like filler: 3/4 at both sizes; latency flat
143–266 ms (5k → 80k chars, 14.3k input tokens at 80k). Dilution lives
in the content, not a hard size wall. NOTE: S4 measured whole-state
"find the planted defect" questions — NOT the adopted per-unit addressing
shape; it bounds context-rot risk but does not validate the design.

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
low context cost — value UNPROVEN. Deferred per Arch 3.

**Skipped-file census (r1-m5, measured).** 37 unique code files skipped
as hunk>120 across the v06-postmerge corpus runs. Char counts of the
local-checkout copies: 5 files over 25k chars, up to `write.rs` at
114,454 chars (~35k state tokens — over the 32k state+longest-question
budget, so even per-file it ships as MULTIPLE calls), plus
`chatComposer.test.tsx` 72k, `mine_corpus.py` 34k, `sweep-thresholds.py`
27k, `useAIChat.ts` 25k. (Caveat: local-checkout sizes, not pinned-SHA.)
The earlier "corpus max 24.0k" was wrong — that was the max OFFENDER
measured, not the max skipped file. **These are SOURCE chars; the plan
must recompute the census on the actual SERIALIZED per-file state**
(r3-M6: per-cluster before+after duplication and JSON encoding inflate
it, enclosing context dedup shrinks it).

**Architecture answer (rev 6, pending Kurt):**

**Adopt: Arch 2 with the cluster as the unit of judgment (stdlib `ast`
first, tree-sitter as a lazy opportunistic import with line-window
fallback), shipped on PER-CLUSTER transport + AST context enrichment.
Per-FILE judgment batching is DOWNGRADED to G-B-gated: S1′ measured the
same systematic downward shift at file scale (−0.55 mean signed Δsev,
23/30 lower, 14/30 gate flips) as per-PR (−0.63), on the adopted wire
format with documented path addressing — the "contamination is bounded
per file" assumption is empirically false at PR-#43 scale. Per-PR
mega-batching stays DEAD. Keep Step 0′ + honest-verdict + Gate-3
framework; cancel the window-cutting core of Approach A rev 8.
Arch 3 (enrichment) is now ON the default path (it no longer rides on a
batching decision); Arch 4 documented escape hatch only, never
default.**

### The wire format (r3-m1)

One batched per-file call:

- `state` is an OBJECT (documented path resolution): 
  `{"file": <path>, "units": [unit_0, unit_1, …], "contexts": {cid: text}}`.
  Each unit carries `unit_id`, `change_type`, the cluster's
  `code_before_change`/`code_after_change` (r2-M1: the rubric judges
  CHANGES — a post-image alone cannot show `a - b` → `a + b`), an anchor
  line, and `context_ref` pointing into the shared `contexts` table.
- **Enclosing-function text is DEDUPLICATED into `contexts`** (r3-M6):
  ten clusters inside one 199-line function reference ONE context entry,
  not ten copies.
- Questions: per unit a full triple `u<N>_severity` (score),
  `u<N>_is_real_issue` (noul — key matches the code's existing
  `is_real_issue`, r3-m5), `u<N>_category` (choice), each instruction
  addressing its item by backticked path
  (`` `units[3].code_after_change`, with context at `contexts.c7` ``).
  Deletion-rubric clusters keep the DELETION_QUESTIONS variant set
  (`references_remaining` included); mixed rubrics batch in one call
  with rubric-specific key groups.
- Question-map overhead is MEASURED, not assumed (r3-m5): the real
  HUNK_QUESTIONS triple serializes to ~800 chars, DELETION_QUESTIONS
  ~1.3k; at 24 units that is ~5–8k tokens — it fits the 64k check but is
  not noise. The pre-send estimator sums serialized questions exactly
  and the longest question exactly; only the state is estimated.

## The guard that replaces MAX_HUNK_LINES (r2-B1, r3-M5/M6)

The 32k budget (state + single longest question) is the binding limit:

- **Estimate on the SERIALIZED payload:** `len(json.dumps(state))` of
  the actual request body (chars/3 for code-dense JSON as the advisory
  prior), plus the EXACT serialized question map. 
  **Soft cap: state + longest question ≤ 28k tokens per call.** Second
  check: total request ≤ 56k (vs 64k).
- **Batch size cap: 24 units per call** (r3-m6), a send-gate rule
  alongside the token caps: a file with more units ships in multiple
  calls (cluster order preserved). "One call per file" means "one BATCH
  per file" — never line-window the SMALLER pieces back into worse cuts.
- **Hard rule: never SEND an estimated-over-cap call** — split first.
- **Runtime over-budget:** typed `_OverBudget` exception, raised ONLY
  when status is 400 AND the body contains
  `max_tokens_exceeded` (community-observed shape, lenient match).
  Handling: split the call's units in half (AST sub-clusters first,
  then ±1-line windows at the leaf) and retry.
  **Termination is unconditional (r3-M5):** recursion depth-capped at
  ⌈log2(24)⌉+1 ≈ 6 levels; at ONE unit, mark that cluster unjudged (it
  feeds the existing Incomplete downgrade) and stop. Any OTHER 4xx is
  today's `_NoRetry` path and counts toward `CALL_FAIL_LIMIT` as usual.
  A provider that 400s everything therefore terminates in bounded calls
  and degrades to Incomplete, never an infinite split loop.
- **Consecutive-failure accounting (r3-M5):** an over-budget split-retry
  chain counts as ONE call attempt for the consecutive counter; a
  non-budget failure inside the chain counts once like any call
  failure. One file alone can therefore never fail a PR open via
  over-budget splitting.
- `usage.input_tokens` (request-level) logged every call to recalibrate
  chars/token per language and content class.

## Requirements for the plan

1. **Per-mode file-content sources — BOTH sides (r2-M1, r3-m2).** AST
   parses run against the images the diff actually compares:
   - `--range`/`--pr`: `git show <head_sha>:<path>` (post) +
     `git show <merge_base>:<path>` (pre). The plan computes the
     merge base itself (`resolve_diff` does not return it).
   - `--staged`: `git show :<path>` (index, post) vs
     `git show HEAD:<path>` (pre). NOT HEAD:path as the post-image.
   - `--uncommitted`: working tree (post) vs `git show :<path>`
     (index, pre) — plain `git diff` compares index to worktree
     (r3-m2). The working-tree read is a DOCUMENTED EXCEPTION to the
     diff-only principle (the working tree IS the post-image here).
   - Deletion-only and whole-file-deletion clusters STAY cluster-based
     (no post-image exists; `hunk_state` before/after text already
     carries what the rubric needs).
2. **Cluster-as-unit semantics (r2-M2, r3-m3/m4).** No merged-unit
   judging. Every cluster (or AST sub-cluster) keeps its own anchor
   line and full question triple; sub-clusters inherit the parent's
   `change_type`. `compose()`, the scorer, rubric routing, the
   `references_remaining` window stay untouched; the split-inflation
   consequence is explicit (see Arch 2) and measured by G-B.
3. **Failure semantics (r2-M4, r3-M4).** 
   - Per-unit KEY misses (a unit's keys absent from an otherwise valid
     `answers` map) mark only that cluster `parse_error` and NEVER
     touch `parse_failures`/`failures`.
   - Only CALL-level shape failures count toward the consecutive limit:
     `answers` missing/not a dict, or zero parseable units in the call.
   - The existing "nothing judged → fail-open" rule is unchanged.
   - Over-budget accounting per the guard section above.
4. **Thresholds stated per rubric (r2-m3).** Code-change findings:
   is_real ≥ 0.50. Deletion findings: is_real ≥ 0.70
   (`DELETION_REAL_THRESHOLD`). Never quote a single threshold.
5. **Laya scope (r2-m6, r3-m9).** `laya_ask` accepting array/object
   state is not parity. This plan ships batching for the JEV provider
   ONLY; under laya the transport stays per-cluster (today's behavior)
   until laya's local context limit is measured and a value-parity gate
   equivalent to G-B passes on it. The old shape-only check
   (`answers` non-empty dict) stays as the laya contract.
6. **Dependency policy (r2-m1).** No installable-extra mechanism exists
   (single-script project): lazy opportunistic `import tree_sitter*`
   (the laya pattern) with stdlib `ast` for Python and line-window
   fallback otherwise. Verify the maintained wheel choice at
   implementation time.
7. **Honest fallback (r2-M5, r3-M1).** If G-B fails per-file batching:
   the fallback is per-cluster calls (today's transport) WITH AST
   context enrichment — NO judgment batching at all; the PR-level
   digest was always a single call. Directive 1 is then met only by the
   digest's existing single-call fan-out, and Kurt decides with that
   stated plainly.
8. **Plan prerequisite (r3-m8): BUILD the defect-positive fixture.**
   `examples/cj-field-goldens.tsv` records the #43 majors only as
   COMMENTS — no pre-fix SHAs, no `file<TAB>line<TAB>desc` anchor rows
   (`eval_against_golden` needs anchors). Before G-B runs: identify the
   pre-fix commits, add anchor rows for the 3 real majors (two abort
   races, one signature contract) in a fixture file, and verify
   per-cluster transport reports them.

## Validation gates

- **G-A — coverage:** the hunk>120 skip class is zero on the corpus
  replay; `write.rs`-class files (114k chars serialized larger) produce
  AST-split batches that all pass the send-gate. Census recomputed on
  SERIALIZED state (req above) before fixtures are built.
- **G-B — per-file batching A/B (the adoption gate; r3-M2).**
  Fixture: 20–40 clusters including multi-cluster files AND split
  clusters, two arms — per-file-batched vs per-cluster.
  **Calibration first:** run per-cluster vs per-cluster on the same
  fixture to measure the fixture's OWN noise (mean |Δ|, flip rate,
  sign distribution) — gates are expressed relative to that run, not a
  borrowed range (±0.2 is a prior, not the gate).
  **Defect-positive arm (r3-M3/m8):** the built pre-fix fixture (req 8)
  must keep equal-or-better recall than per-cluster.
  **Pass criteria, all of them:**
  - gate-flip rate ≤ 5% of clusters AND not above the calibration run's
    own flip rate by a meaningful margin;
  - **signed-bias test:** |mean signed Δsev| ≤ 0.05 AND a sign test on
    per-cluster Δsev with p > 0.05 — a uniform shift in EITHER
    direction fails even if mean |Δ| is small;
  - same signed treatment for Δis_real near EACH rubric's threshold
    (0.50 / 0.70);
  - defect-positive recall equal or better (see above).
- **G-C — field regression on the negative goldens:** the 5 defect-free
  merged heads stay at ≤ 1 reported FP major each (the batched arm's
  own S1 best case is 1: `import.tsx:7`). Under-report direction is
  policed by G-B's defect-positive arm, not here.
- **G-D — replay equivalence, noise-aware (r3-M3).** NOT exact
  equality. Baseline: the old ledgers' own 3-repeat disagreement
  (verdict agreement rate, findings Jaccard across repeats). Pass:
  new-transport vs old-transport agreement ≥ the old repeats' agreement
  baseline; wherever input shape is unchanged, replay RECORDED answers
  deterministically instead of re-calling. Skipped-case improvements
  (more judged) are expected and exempt.
- **G-E (future, laya):** value-parity gate on laya before batching
  ships there (req 5).

## Open decisions for Kurt

1. **D1 (was Q3):** approve lazy tree-sitter opportunistic import as
   the dependency mechanism (no packaging change; README notes it).
2. **D2:** if G-B fails per-file batching, accept the honest fallback
   (per-cluster calls + AST context, no judgment batching) — directive
   1 then applies only to the digest call. Recommended: yes, pending
   G-B evidence either way.
3. **D3:** Arch 3 (call-graph enrichment) stays deferred until G-B
   settles. No ruling needed now.
4. **D4:** `--uncommitted` mode: the required working-tree read is a
   documented exception to diff-only (index is the pre-image). Object
   if Kurt prefers disabling AST units in that mode instead.
5. **D5 (updated by S1′):** per-PR mega-batching stays retired as a
   judgment path — evidence is now addressing-proof (S1′ per-PR arm:
   mean signed Δsev −0.63, 26/30 lower, 13/30 gate flips, on the
   adopted object+path wire format; original S1: 28/30 down, 1 FP major
   on a 0-finding head). NEW sub-decision from the r4 round: whether
   per-FILE judgment batching ships by default anyway (accepting the
   −0.55 shift for the transport win) or only behind a passing G-B
   (recommended: behind G-B).
6. **D6 (r3-m9):** confirm laya stays per-cluster (no batching) until
   its context limit is measured (req 5).

## Revision history

- **rev 1 (2026-10-01):** initial question draft; 6 open questions.
- **rev 2 (2026-10-01 late):** smoke-test results S1–S4 folded in;
  architecture answer drafted.
- **rev 3 (2026-10-02, 6fb0b2b):** Opus r1 (16 findings) verified and
  folded: official docs replace third-party citations; per-unit
  addressing required; S1 overstated claims corrected; measured
  skipped-file census; honest batching fallback; DEFECT-positive G-B
  arm; cluster-as-unit; per-unit parsing; per-mode file sources.
- **rev 4 (2026-10-02, 54609c0):** Opus r2 (1 BLOCKER, 5 MAJORS) folded:
  guard rebuilt on the 32k state+longest-question budget; per-mode
  sources with before+after text; cluster-as-unit confirmed; S1
  restated honestly; failure semantics; honest fallback; RESEARCH
  answered from docs.typesafe.ai.
- **rev 5 (2026-10-02):** Opus r3 (0 BLOCKER, 6 MAJORS, 9 minors)
  verified and folded. M1: "batch the digest (37x)" claim removed;
  directive-1 outcome stated once, honestly. M2: G-B gains the signed-
  bias gate + fixture-self calibration. M3: G-D re-based on the old
  runs' own repeat-agreement baseline + deterministic replay. M4:
  per-unit key misses decoupled from fail-open counters; call-level
  shape failures only. M5: typed _OverBudget with unconditional
  termination, depth cap, single-attempt accounting. M6: estimation on
  serialized payload, shared `contexts` table, census recompute on
  serialized state. m1: object state shape (documented path root);
  m2: pre-images per mode + plan computes merge base; m3: sub-cluster
  change_type inheritance; m4: split-inflation consequence stated and
  measured; m5: question overhead measured, `is_real_issue` key;
  m6: 24-unit cap in the guard; m7: write.rs/wisdom.ts untangled;
  m8: defect-positive fixture is a plan prerequisite; m9: stability
  claim quantified (3 runs), laya excluded from batching until
  measured (D6). RESEARCH answered: object-root paths documented,
  array-root undocumented (avoided by design); over-budget shape
  community-only → lenient match + guaranteed termination.
