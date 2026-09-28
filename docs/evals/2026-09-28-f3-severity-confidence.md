# F3 — severity-confidence semantics (Jev provider docs)

**Date:** 2026-09-28 · sources:
[docs.typesafe.ai/confidence](https://docs.typesafe.ai/confidence),
[/primitives/score](https://docs.typesafe.ai/primitives/score),
[/primitives/choice](https://docs.typesafe.ai/primitives/choice)
(the vendor's authoritative pages; the jev-review clone that hosted older
notes was deleted today — the docs are the source of record).

## What confidence is (vendor semantics)

- Every **Score** and **Choice** answer carries `probabilities` (full
  distribution over levels/options) and `confidence` ∈ [0,1] — **a
  statistic of the distribution's shape**, computed by the provider.
  All mass on one level ⇒ 1.0; evenly spread ⇒ →0. **Noul answers carry
  no confidence.**
- `score` is the probability-weighted mean of level numbers. **Different
  distributions can produce the same score** — a 1.5 on a 0–3 scale can be
  all mass on level 1–2 boundary *or* the uniform mean of a maximally
  flat distribution.
- **confidence 0.0 = maximally flat distribution.** The model has no
  basis to prefer any level; the severity score is then approximately the
  scale midpoint regardless of content. It does NOT mean "the model
  confidently asserts something odd" — it means *the model could not
  place this hunk*.
- Vendor's stated causes of low confidence: levels overlap for this
  state, the question measures more than one thing, or **the state
  doesn't say enough to place it**.
- Confidence "describes the model's answer, not a guarantee that the
  answer is correct" — high confidence ≠ correctness; it is a routing
  signal ("I don't know" → ask a human), with thresholds that scale with
  the risk of the action taken.

## What the tool does today (verified in code)

`confidence` is parsed, logged to the ledger, and rendered — and **never
consulted by `compose()`**. Verdicts gate on `is_real` (a Noul — which
carries no confidence by design) and `severity` (a Score — whose
confidence is ignored). So a severity-2.1 MAJOR at conf 0.0 flips
verdicts exactly like one at conf 0.9.

## What the fresh field data shows

From the five v03b CJ runs (see
`2026-09-28-v03b-cj-field-proof.md`): the #43 Changes-requested-on-clean
run is saturated with exactly the vendor's "state insufficient" shape —
`import.tsx:101 sev 1.04 conf 0.0`, `chunkedImportDump.ts:48 sev 2.07
conf 0.07`, `chunkedImportDump.ts:9 sev 1.65 conf 0.0` (all *unreported*
despite sev, because is_real < 0.50 — but two of the *reported* 11 also
sit at conf 0.0–0.22). The v0.2 ledger shows the same signature
(`safe_path.rs:47 1.26 0.45 0.00` et al.). Dense-refactor hunks
confuse severity placement; the severity number from those entries is
≈ noise around the scale midpoint, and is_real is doing all the real
gating work.

## Options for gating (F3's open decision — Kurt's call)

1. **Status quo — log, don't gate.** Confidence stays observability.
   Zero behavior risk; uncertain-severity findings keep full verdict
   power when is_real is high.
2. **Severity-confidence floor.** A Score answer below a confidence
   floor (e.g. 0.10–0.30, the vendor's "ask a human" band) contributes
   to the verdict at MINOR strength regardless of its raw severity — the
   finding still reports, but an unplaceable severity can't alone
   produce BLOCKER/MAJOR verdict weight. Interacts with the corroboration
   gate (a conf-floor finding should probably not count as a
   corroborating CODE-CHANGE finding either — needs a written rule).
3. **Route to needs_human_review (F4 interplay).** Don't change verdict
   math; surface conf-floor MAJOR+ findings through the
   `needs_human_review` render instead. Deciding this together with F4
   (recalibrate or cut nhr) avoids building the flag twice.

**Recommendation:** decide 2-vs-3 only with recall-side evidence (a
positive field golden — a PR with a known real issue — plus the fixture
sweep re-run), per the standing "no knob flips before the sweep separates
the known FP/FN set" constraint. The clean-cohort data alone shows the
FP side (uncertain-severity majors inflate #43-style over-reporting) but
says nothing about what a floor would suppress on dirty PRs. Until then,
option 1 is the defensible default, and F3's documentation duty is done
by this file.
