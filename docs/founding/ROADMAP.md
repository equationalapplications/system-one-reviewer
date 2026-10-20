# ROADMAP — system-one-reviewer (gate-gated, no dates)

> Provenance. v0.1 DRAFT, 2026-10-19. Authority: Kurt VanDusen; directives in
> Discord thread 1561717581461848067 (msg 1561767191085453413). Derived from
> [INTENT.md](../../INTENT.md) and the Tier-4 Fable run-3 memo (vault:
> `records/investigations/2026-10-19-sor-quality-fable-step0-guidance/memo-run3.md`).
> The vault wins on disagreement. Changes by PR with a dated changelog line.

## Promise classes

- **BINDING** — steps whose gates are measured and ratified; the ladder may
  depend on them.
- **PLANNED** — sequenced, gates written, not yet run.
- **EXPLORATORY** — may be dropped by their own gate with no further ruling.

## Steps (each gate must be measured, never argued)

**S0 — Ledger + per-class sustained rate** [BINDING once landed]
Why first: every later gate reads from it; backfills the Oct 15–19 window
from written adjudications. Persist every report; an adjudications ledger
(sustained/rejected keys per reflex class); a stats command printing
sustained rate, cost per sustained finding, and firing counts per class.

**S1 — High-bar replay, model off** [ADOPTED — Kurt, msg 1561773701530386494]
Why first: zero cost; decides whether the generic rubric keeps any verdict
role. Method: sweep stored per-unit is_real scores (seven Oct 15–19 fix-window
runs, six Oct 2 fixture runs, v08-gates corpus replay) at bars
0.60–0.95. Gate: a bar where the 48 window false positives vanish and the
5 fixture true positives survive → adopt as the reflex gate; no such bar →
the generic question retires from verdict use permanently.
**RESULT** (`docs/benchmarks/2026-10-19-r1-high-bar-sweep.json`, zero model
calls): the 48 window FPs max out at is_real 0.76; the separating zone is
**bar ≥ 0.80 — zero window FPs survive, 45/205 fixture TP instances
(~22%) survive, but NO bar preserves full 5/5 per-run fixture recall
(0/35 runs at 0.80)**. A zero-FP reflex exists today at bar 0.80+ over
roughly a fifth of the fixture class; the generic question cannot be a
full-recall reviewer at any bar.
**ADOPTED (Kurt, 2026-10-19): bar 0.80 is the reflex gate.** Findings
below 0.80 become silent telemetry; the 5/5-fixture expectation is
retired in favor of "fires only when solid" (INTENT rule 4/6b). The
code-side change (gate constant + telemetry demotion) rides the v0.9 PR.

**S2 — Receptive-field census + boundary write-back into INTENT.md** [PLANNED]
Why here: turns "what SOR must never cover" from prose into a measured
list. Model off: classify the 55 corpus issues + 29 dismissals as
hunk-visible / needs-fact / design-judgment; tabulate hit rate at the S1
bar. Gate: a class at hit ≥ 0.5 with no dismissals above the bar becomes a
reflex candidate; everything else is written into INTENT rule 5 as
delegated.

**S3 — Deterministic negative reflexes + rung-skip ruling** [PLANNED]
Why here: the first money saved; no model involved. Classify every ledger
range (docs-only, lockfile, generated, rename-only, whitespace-only,
test-only); join against sustained findings. Gate: zero sustained findings
in a class across the ledger → Kurt rules whether the ladder may skip the
Haiku low rungs on that class.

**S4 — Guard-removal reflex (three-arm ablation)** [PLANNED]
Why here: extends the only reflex with measured zero false positives
(deletion rubric + `references_remaining`). Detector emits "guard removed,
N callers still reach this path" as a stated conclusion; arms: detector
alone / + Jev / + Haiku low-effort confirm on the flagged unit only.
Gate: 3/3 planted guard removals in the extended fixture at the bar;
negative heads silent; Jev beats detector-alone precision or is dropped
from this reflex.

**S5 — Site cutting under the bar (spec E1/E2/E5; V3/V5 gates)** [PLANNED]
Why here: the anchor fix is real (2/8 of golden misses) but adds firing
opportunities; needs S1's bar first. Measured caution: top-level cutting
alone was 46→168 units on the golden range; sites will be more.
Gate: B2/M2 anchor-class recovered; findings per run on reproof ranges not
up; V3 noise band respected. Does not ship without S1's bar.

**S6 — Lexicon reflexes with sourced provenance (P3)** [EXPLORATORY]
Why here: highest ceiling (prose-probe upper bound 5/6 units), highest
curation cost, lowest firing opportunity. Opportunity gate first, model
off: do the four measured literal classes (multivalued IAM keys,
CloudTrail eventCategory semantics, log-group ARN suffix rules, record
field casing) appear in the 47 corpus heads / last 90 days of org PRs?
Fewer than a handful → defer regardless of golden recall. Recall gate
second: golden 5/8 at the bar, three repeats, negative heads clean,
detector-alone arm reported. Governance: every row carries source URL,
date, and a both-ways fixture.

**S7 — Contrastive choice + Haiku confirm pairing** [EXPLORATORY]
Why last: ride-alongs. Contrastive choice stays fixture-only calibration
(gate: chosen variant matches the fixed code 4/5, three repeats agreeing).
Haiku-confirm pairing adopted per class only where cost per sustained
finding falls (measured in S0's ledger on S4/S6 arms).

## Standing rules

- Firing budget per run: 5 surfaced findings (S0 may re-rule from data).
- A reflex class ships at sustained rate ≥ 0.70 over ≥ 10 adjudicated
  firings; retires below 0.50 over the last 10.
- No verdict output from SOR in this phase (INTENT rule 3).
- Every surfaced finding is adjudicated in writing within the run that
  consumes it — the ledger is the precision-first mechanism, and it is
  non-negotiable.

## Stale-docs register

- v0.9 spec rev 4 "THE FORK" (A/B/C): superseded; A/B/C are raw material
  for S5/S6.
- Run-1 memo D1 (fix-delta rubric): superseded by the dual-review-loop SOP
  amendment of 2026-10-19 (fix rounds run full scope at the fix head).
- Run-2 memo P2 column: M3 reclassified as a design judgment (LLM-tier by
  construction); the polarity detector is withdrawn.
- Oct 4 ruling accepting the #46 band false positive: revisit under S1's
  bar.

## Ideas bank (external landscape research, 2026-10-19)

Digest with URLs: `docs/benchmarks/2026-10-19-landscape-research.md`
(Sonnet research run, ~22 searches). Candidates awaiting gates, not adopted:
Tricorder-style hard FP-rate retirement gate for reflex classes (matches the
ship/retire bars in rule 6b); BugLens' deterministic-candidates + model-judge
precision lift (0.1->0.72) as an external benchmark; Semgrep Assistant's
"memories" feedback + hide-don't-delete default; Feature Slice Matching
(arXiv 2512.24858 — embed-and-match ranking, rejected LLM judges as unstable:
external validation for a non-LLM judge, and a candidate embed-and-match
reflex); abstention-vs-calibration check on the 0.80 gate. Each rides an
existing S-step's gate; none is adopted standalone.
