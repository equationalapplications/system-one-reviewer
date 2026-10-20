# INTENT — system-one-reviewer (SOR)

**Read this file first.** It explains why SOR exists, the rules it must
follow, what it deliberately does not do, and how changes are made. If this
file and another document disagree, this file wins on *intent* (what we are
trying to do) and the specs win on *detail* (exactly how).

Each rule has a **Status** line saying how much of it the code does today:

- **Built** — the code does this.
- **Partly built** — some of it exists; the line says what is missing.
- **Planned** — decided, but not in the code yet.
- **Open decision** — not decided yet.

Statuses were checked against the code on 2026-10-19. Update a status line
in the same pull request that changes the behavior.

## Why SOR exists

SOR is an experimental PR reviewer built on a **System One model** — a
small, fast model that makes instant judgments the way a reflex fires,
rather than reasoning step by step the way an LLM does. That makes it
nearly free and nearly instant. It also means it has strengths and blind
spots that are the opposite of an LLM reviewer's.

The goal is a **new concept of PR reviewer**: one built entirely around
those strengths. SOR exists to surface **solid findings in seconds for
fractions of a cent** — findings a person can trust enough to act on. It
exists to say nothing when it has nothing solid. It does not exist to
imitate an LLM reviewer.

The division of labor is the point. Our review ladder already has LLM
tiers (a Haiku first-pass reviewer, then GLM, Opus, Fable) that are good
at deep semantic reading. SOR covers only the classes of problems a reflex
is genuinely reliable on. A subtle logic bug that SOR misses is not a
defect of SOR; asking SOR to find those was a design error.

False positives are the current enemy. A false positive costs a person's
attention and often a paid re-review — more expensive than anything SOR
saves. Solid positives that arrive instantly and cheaply are the product —
the way a biological reflex works: fast, reliable for its stimulus, and
silent otherwise.

The creative surface is **deterministic preparation**: ordinary code (git
plumbing, tree-sitter/AST structure, reference counts, curated fact
tables) decides what evidence the classifier sees; the classifier judges
what we show it. Finding the preparations that make reflex judgments solid
is an open, unsolved problem, and experimentation is how we work on it.

## Glossary

- **System One model** — a small model that makes typed, instant
  judgments (a score, a yes/no, a category). Named for Kahneman's fast
  cognition. EA uses two: **Jev** (hosted, SOR's judge today) and
  **Laya** (open-weight, not integrated here).
- **Cluster / unit / site** — a diff is split into changed chunks
  (clusters); cutters may subdivide a cluster into units (top-level
  functions/classes) or sites (individual decisions, like one property
  assignment). What gets split determines what the judge can see.
- **Preparation** — the deterministic code that decides that evidence:
  parsing, splitting, enrichment, fact tables.
- **Golden** — a labeled list of known defects at known lines, used to
  measure recall (how many known defects a run finds).
- **Sustained** — a finding that downstream adjudication confirmed real.
- **Ladder** — the review tiers SOR feeds: SOR → Haiku first-pass →
  GLM → Opus → Fable.
- **Fail-open** — when the model cannot be reached, SOR reports
  "Unavailable" rather than pretending the code is clean.

## The rules

### 1. Reflex-fast and reflex-cheap, or it is nothing

A full run takes seconds and costs fractions of a cent, runs locally, and
posts nothing anywhere. Every design decision protects this envelope. A
change that makes SOR slower or pricier needs a spec saying why the
envelope moves and by how much.

*Why:* the cheap tier is only worth having if using it always is cheaper
than thinking about whether to use it.

**Status: Built.** (v0.8.0: 0.3–4.6 s per run on real ranges. v0.9: E1 wire_format stamp and status field added; no verdict output.) TS/JS enrichment adds no model calls but adds input tokens per unit: model-off, a median of about 139 tokens (max about 247) per enriched unit on the small TS fixtures (`docs/benchmarks/2026-10-20-ts-enrichment-envelope.json`), and the TS symbol table is bounded in characters so a module with many long signatures cannot blow that up. Its latency is not yet measured; it is watched after release, and leaving the seconds/cents envelope would by itself turn the default off (`docs/superpowers/specs/2026-10-20-ts-enrichment-effect-gate.md`, Cost envelope).

### 2. Deterministic code prepares; the model only judges

Ordinary code decides what evidence exists: how the diff is split, what
context rides along, what facts are attached. The model never gathers its
own evidence. When a class of defect is missed, the first question is
always "what preparation would make it visible?" — never "can the model
try harder?".

*Why:* the judgment is only as good as the evidence shown, and
deterministic preparation is testable, cheap, and ours to invent.

**Status: Partly built (v0.9).** Packaging, splitting, enrichment, golden harness, E1 wire_format stamping, and E2 decision-site cutting (object-literal property assignments, call-argument expressions, conditionals, sibling-constant declarations; TS/JS via tree-sitter, Python via `ast`) exist and are wired into every code-change cluster. E5 wheels self-check added (per-cutter availability + version pinning, parses a known snippet per language). Enclosing-symbol enrichment (`ast_context`) covers Python and, behind the same default-on `--no-enrichment` switch, TS/JS; its effect on judgment has never been validly measured (the 2026-10-02 enrichment-off A/B ran with the Python path unengaged), and the gate that will measure it is `docs/superpowers/specs/2026-10-20-ts-enrichment-effect-gate.md`. Known gap, MEASURED not assumed: the V7 model-off census on the real golden range (`docs/benchmarks/2026-10-19-v7-site-census-golden-range.json`) shows median site expansion at 9.63× even after both allowed floor tightenings — above the adopted 5× envelope. E2 ships anyway (item 4 under "How changes are made": metrics refine, they do not gate shipping); the envelope decision is open, not resolved, and the expansion is watched in use.

### 3. SOR emits no verdict; it is input to adjudication

SOR's destination shape is reflex findings plus a coverage banner — no
"Changes requested" authority. Until a finding class earns its way past the
measured bar (see rule 4), its output is telemetry. Findings are never
auto-fixed, and a clean SOR run is never treated as proof the code is good —
recall on subtle defects is measured, published, and modest by design.

*Why:* a cheap reflex must never carry merge authority; that is what the
paid tiers are for. Measured 2026-10-19: the generic rubric's verdicts went
0-for-5 against adjudication on fix-window runs, and its clean control unit
scores above its own gate.

**Status: Built (v0.9).** SOR output is ranked triage pointers (max 5 per ROADMAP standing rule) + coverage banner + status signal. No "Approved" or "Changes requested" verdicts ship. The deletion rubric (with `references_remaining` check) carries zero false positives. Fork resolution A+C (triage re-scope) resolves rule 3 in v0.9 per Fable gate.

### 4. A false positive is a defect

In the current phase, precision outranks recall. A finding must be worth a
person's attention; if adjudication routinely rejects a class of findings,
that class is turned off or re-prepared — not tolerated. Sustained-rate
per finding class is tracked, and a class whose sustained-rate falls below
the bar is treated as a bug, not a nuisance.

*Why:* a false positive costs a person's time and often a paid re-review —
strictly more than SOR saves.

**Status: Built (v0.9).** The reflex gate is **adopted at is_real 0.80** (Kurt, 2026-10-19, from the R1 sweep: zero of 48 wild false positives reach 0.80). V2 TRIAGE CHECK asserts no run output contains "Approved" or "Changes requested"; findings are reported only as ranked triage pointers at 0.80+ gate. Test-file findings are judged and logged but held back by default (field data: all three test-file firings in the 2026-10-20 sample of five were false or arguable); see `docs/superpowers/specs/2026-10-20-test-file-class-and-locator.md`.

### 5. SOR does not cover what an LLM covers better

Deep semantic defects — subtle logic errors, domain-semantic mistakes,
architecture problems — are the LLM tiers' job by design. SOR's target
classes are ones a reflex can be reliable on: mechanical, structural,
preparable signals a fast classifier can judge from well-prepared
evidence. Missing a deep semantic bug is not a failure of SOR; asking it
to catch those is a failure of design.

*Why:* a reflex that tries to reason produces confident noise, and
confident noise is the most expensive output a cheap tool can emit.

**Status: Open decision.** The exact class boundary is the current design
question; the measured record is in the v0.9 spec's evidence receipts.

### 6. Reflexes need prepared stimuli — and the stimulus must already mean something

Measured 2026-10-19, both directions. **Upper bound:** when a correct domain
CONCLUSION is stated to the judge (hand-written prose facts), it acts
decisively — 5 of 6 defect units crossed the report gate. **Lower bound:** the
same units probed with structured, conclusion-free observation rows moved
nothing (M3 0.44→0.36), and the anchoring control did not lift a clean unit.
Caveat that keeps us honest: the prose probe is an ORACLE UPPER BOUND — the
facts were written by someone who already knew the defects. It proves the
judge accepts correct conclusions; it does not prove deterministic code can
produce them. That production question is open (ROADMAP R6). Also measured:
M3 itself is not a structural defect at all — it is a safe-default design
judgment, which belongs to the LLM tiers by construction.

*Why:* a reflex responds to a shaped stimulus; showing it anatomy does
nothing, and telling it the answer is not a capability we can ship until
something deterministic can supply the answer.

**Status: Open decision.** Sourced conclusion-facts (ROADMAP R6, with an
opportunity gate before build) are the candidate; the structured-rows-only
variant was probed and rejected the same day.

### 6b. What a reflex is

A **reflex** is the unit of SOR functionality, and specs are checked against
this definition: a deterministic trigger that prepares one narrow, fully
stated observation about a change; a single System One judgment gating
whether the observation is a real problem in context; a threshold set far
from chance; and a written ledger of every firing and its adjudication. A
reflex ships only after its ledger shows its findings are usually right
(sustained rate ≥ 0.70 over ≥ 10 adjudicated firings) and retires
automatically when they stop being (below 0.50 over the last 10). Outside
its reflexes, SOR is silent.

### 7. A run is honest about what it judged

Every run states its coverage: what was judged, what was skipped and why,
which cutting path produced each unit, and whether the model was reachable
(fail-open runs can never read as clean). Same range in, same verdict out
— and near-threshold scores are flagged as untrustworthy in the report
itself.

*Why:* downstream adjudication must be able to trust the run's self-report
without re-deriving it.

**Status: Built (v0.9).** Coverage banners, jitter flags, fail-open verdicts, E1 wire_format stamps (hunk/line-window/ast-units/ts-units/sites), per-unit `cut` field, and status field (ok/fail-open/incomplete review) exist. Ledger and JSON both carry wire_format and status for complete run characterization (D7 like-for-like contract enforceable).

### 8. Every judgment is measured

All runs append to one metrics ledger. Recall claims need a golden;
precision claims need adjudicated outcomes; threshold changes need a
sweep. A change that moves judgments should say what it moved and, where the
author has them, ship before/after numbers on the same receipts (item 4 under
"How changes are made" sets what is required before release).

*Why:* SOR is experimental — measurement is how an experiment stays
honest.

**Status: Built (v0.9).** The metrics ledger, golden evaluation, fixtures, threshold sweeps, V1/V2/V3/V5 gate tests, and before/after receipts exist. v0.9 commit: wire_format stamp, status field, 0.80 gate, 5-findings cap, and fork resolution A+C (triage re-scope) all measured and tested.

## Out of scope (don't build these here)

- Deep semantic defect recall. The LLM tiers own that class; SOR asking to
  share it is the design error this file exists to prevent.
- Merge-gate authority for SOR verdicts, in any form.
- LLM-style narrative code review. SOR outputs classified findings, not
  prose reviews.
- Anything that breaks the seconds/cents/local envelope (rule 1).
- Posting anywhere. SOR prints reports; delivery is the caller's job.
- A second place for review truth: SOR feeds the existing review ladder;
  it does not maintain its own verdict-of-record.

## How changes are made

1. **Spec first.** Design changes get a spec under `docs/superpowers/specs/`,
   based on an investigation that reads the real code, with measured
   evidence committed as receipts (`docs/benchmarks/`, `examples/`).
   Spec, plan and implementation travel in one pull request.
2. **Decision history** for the v0.9 direction lives in the equational-wiki
   vault (`records/investigations/2026-10-19-sor-quality-fable-step0-guidance/`),
   including two Fable guidance memos and their probes. That vault is
   separate from this repo.
3. **Review, then merge.** The review ladder per the dual-review-cycle
   skill; unresolved questions hold the pull request.
4. **Metrics refine; they do not gate shipping.** SOR is built by using
   it. The loop is: small smoke tests locally during development (the
   fixture golden, the Stage A 8-defect golden with the negative heads, and
   the stamp/coverage tests, whenever they are quick to run), then release,
   then use it on real coding tasks and pull requests, then evaluate from
   adjudicated outcomes and improve. Numbers we have not yet collected in
   the wild are not a precondition for releasing a judgment-affecting
   change. What a change does need:
   - a smoke test that proves the mechanism engaged (a treatment that
     silently did nothing teaches nothing);
   - a way to turn it off (a flag, as with `--no-enrichment`), so the off
     arm stays available for comparison;
   - ledger labels and stamps (`exp:`, `reproof:`, the `enrichment` and
     `wire_format` stamps) so its runs can be told apart later;
   - a plain statement in the PR of what is unmeasured and how it will be
     evaluated, plus before/after numbers if the author has them.

   This relaxes the release gate, not the claim standard: a claim of
   recall or precision still needs `--golden` or adjudicated outcomes
   (AGENTS.md, Measurement discipline). The hard rules above (no verdict
   output, no posting, the cost envelope, false positives as defects) are
   not relaxed by this item.
5. **The metrics ledger is append-only.** Re-runs for evidence use
   distinct labels (`reproof:`, `exp:`) so audits can tell them apart.
