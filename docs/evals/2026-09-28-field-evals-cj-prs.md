# Field evaluation brief — system-one-reviewer v0.2 on curated-journal PRs

**Date:** 2026-09-28 (runs 2026-09-27T21:11Z – 2026-09-28T02:57Z, provider `jev`)
**Purpose:** first real-world (non-fixture) evaluation of v0.2, captured so the
v0.3 work is driven by evidence. Raw ledger: `~/.local/state/jev-review/metrics.jsonl`,
last 9 records (labels `pr45-rebased`, `pr47`, `pr43`, `pr46`, `pr46-fix-delta`,
`pr47-rebased`, plus 3 unlabeled curated-thoughts runs).

## What ran

Nine live invocations against real PR diffs. Context: these PRs were reviewed
in parallel by Opus (via `opus-review`) and CodeRabbit, so every run below has
human-verified ground truth from those deeper reviews plus manual inspection.

| run | target | verdict | reported | ground truth from deep review |
|---|---|---|---|---|
| (curated-thoughts) | vault-ingest-policy range | Approved | 2 (conf 0.0) | not deeply reviewed; conf-0.0 findings reported at all is itself a defect (F4) |
| pr45-rebased | CJ #45 template-cleanup | **Changes requested** | 1 (animated-icon.web.tsx, line 1) | Opus: no BLOCKER, deletions verified safe; only MAJOR was "rebase first" (a process issue, not a code defect). The reported finding targets a DELETED file region — nothing real. **FP** |
| pr47 | CJ #47 button-border-style | Approved | 0 | manual triage: change correct. **TN** |
| pr43 | CJ #43 import-chunking | Changes requested | 9 | Opus review queued at the time; aws-cloud-agent "no findings". Per-hunk scores are low (sev 1.4–2.1, is_real 0.52–0.76) — verdict driven by 9 × sev≥2 clusters on a genuinely risky diff. Not clearly wrong, but see F1/F3 |
| pr46 | CJ #46 dev-model-cache | **Approved** | 2 (devModel.ts, mockLlmProvider.ts — both line 1) | CodeRabbit found 4 valid bugs on this diff, incl. "mockLlmProvider keyword check shadows `Document Chunk:` → silent no-fact extraction". The tool *saw* the mockLlmProvider hunk (judged it, is_real 0.64) and still said **Approved**. **FN on the verdict** |
| pr46-fix-delta | fix range 8e6f440..f8c6594 | Changes requested | 2 | fix diff was fine; 2 findings on a benign range — likely FPs |
| pr47-rebased | CJ #47 after rebase | Approved | 0 | **TN** |

## Headline numbers (small n, honest)

- Verdict-level on PRs with solid ground truth: TP 2 (#43, #46-fix-delta arguable),
  **FP 1 (#45)**, **FN 1 (#46)**, TN 2 (#47 ×2). ~50/50 on the clear cases.
- Finding-level: the model *did* notice the mockLlmProvider defect (is_real 0.64)
  — the pipeline lost it. That is a composition/anchoring problem, not a model gap.
- Latency healthy (~120–160 ms/call); no fail-opens; no transport failures.

## Findings (evidence → suspected code location)

**F1 — Deletion-only / whole-file-deletion clusters are scored with the full
severity question set, producing a false "Changes requested" (#45).**
PR #45 was a template-cleanup (deleting unused components); the reported finding
targets `animated-icon.web.tsx` line 1 — the deliberate anchor for a
deletions-only cluster (package_hunks docstring, system_one_reviewer.py:348-362:
deletion-only clusters anchor at the '-' entry's tracked new_line). The model
was asked the same three questions over a cluster whose `code_after_change` is
empty (`hunk_state`, :627-645) and returned severity ≥2, and `compose()`
(:760-774) let that lone finding drive "Changes requested" — while the Opus
review verified the deletions safe. Anchoring itself is fine; the gap is that
a deletions-only cluster has no surviving code to be "buggy", yet full-severity
scoring on it can unilaterally flip a verdict. Proposal: mark after-empty
clusters in the state (e.g. `change_type: deletion-only`) and adapt the
questions ("was this removal safe? anything load-bearing removed?"), and/or
require corroboration before a deletion-only cluster alone produces "Changes
requested".

**F2 — Approved despite a seen-and-judged real defect (pr46).**
mockLlmProvider.ts:11: the model scored is_real 0.64 on the exact hunk
CodeRabbit later confirmed as a valid bug (keyword check shadowing `Document
Chunk:` → silent no-fact extraction), but its severity read below the
verdict-driving line, so the run said **Approved** with 2 findings. Two knobs:
(a) verdict rule counts only sev≥1 *reported* findings (line 769: `severity >= 1`
and threshold on is_real) — a real-but-"minor" defect can never change a verdict;
(b) severities may be miscalibrated on small hunks. Proposal: let is_real (Noul)
weight into the verdict — e.g. is_real ≥ 0.75 with any sev ≥1 is verdict-eligible,
or a per-finding "report as note" middle tier between silent and verdict-driving.

**F3 — Reported findings carry confidence 0.0 (curated-thoughts runs).**
Two findings with `confidence 0.0` were reported. Either the model returned
no confidence and it defaults to 0 (rendered misleadingly), or confidence is
not used in the report decision at all. `compose()` indeed never reads
`confidence`. Proposal: define semantics — if confidence missing → null, not 0;
optionally surface "model low-confidence" in the report instead of a bare 0.0.

**F4 — PR-level risk did not affect the verdict, and said "Approved" was fine
on pr46 (risk 2.1, needs_human_review 0.92) while the deep review found 4 valid
bugs.** `needs_human_review` is computed and rendered but never gates anything.
Proposal: either wire it in (e.g. needs_human_review ≥ 0.9 forces "Changes
requested — needs human review") or drop it from the output to avoid a
contradictory signal (risk 2.1/3 + verdict Approved reads as noise).

**F5 — Label/mode hygiene:** several runs logged empty labels and `repo: "."`,
weakening the ledger. Minor; document label conventions or default label = mode.

**F6 — README still leads with the old name** (`# jev-review`, Jev-as-actor
prose throughout) despite the D4 rebrand decision; category term is "system one
model", Jev/Laya named only as example providers.

## Candidate v0.3 changes (to be weighed by review)

1. Deletion-only hunk handling (F1): explicit after-empty flag + adapted prompt
   questions; consider not letting a deletion-only cluster alone produce
   "Changes requested" without corroborating findings.
2. Verdict composition (F2): Noul-weighted verdict eligibility; middle
   "notes" tier rendered but not verdict-driving; consider per-finding
   anchor-quality (line precision) in compose.
3. Confidence semantics (F3): null vs 0; render low-confidence findings as notes.
4. PR-level gate decision (F4): wire needs_human_review into the verdict or cut it.
5. README/docs rebrand to "system-one-reviewer / system one model" prose (F6),
   keeping the documented path-continuity exceptions.
6. Ledger hygiene: require/derive a label; record `repo` as basename when `.`.

## Known constraints (from v0.2 decisions)

- Closed-set last line {Approved, Changes requested, Unavailable, Incomplete}
  is a published contract — any new verdict wording must respect it or be a
  documented breaking change.
- Threshold 0.50 is the benchmark-of-record plateau; changes to compose must
  re-run the fixture sweep (scripts/sweep-thresholds.py) to re-verify.
- Keep env-var/path continuity (JEV_REVIEW_METRICS, ~/.config/jev-review/.env).
- Never claim general-recall from a 5-plant fixture — same honesty applies to
  this 9-run field eval: n is tiny, findings are directional.
