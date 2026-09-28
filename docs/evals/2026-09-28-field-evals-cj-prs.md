# Field evaluation brief — system-one-reviewer v0.2 on curated-journal PRs

**Date:** 2026-09-28 (runs 2026-09-27T21:11Z – 2026-09-28T02:57Z, provider `jev`)
**Purpose:** first real-world (non-fixture) evaluation of v0.2, captured so the
v0.3 work is driven by evidence. Raw ledger: `~/.local/state/jev-review/metrics.jsonl`;
the 9 field-run records are reproduced in the Appendix below.

## What ran

Nine live invocations: 6 against curated-journal PRs, 3 against a
curated-thoughts branch. Context: the CJ PRs were reviewed in parallel by Opus
(via `opus-review`, run locally) and CodeRabbit, so several runs have
human-verified ground truth. Ground-truth strength is labeled per run —
not every run was deeply reviewed.

| run | mode | target | verdict | reported | ground truth (strength) |
|---|---|---|---|---|---|
| ct-staged | staged | curated-thoughts staged | Approved | 0 | none |
| ct-range | range main..vault-ingest-policy | curated-thoughts branch | Approved | 2 (conf 0.0) | none |
| ct-range-origin | range main..origin/vault-ingest-policy | same, fresh fetch | Approved | 3 (conf 0.0) | none |
| pr45-rebased | pr:45 | CJ #45 template-cleanup (deletions) | **Changes requested** | 1 (sev 2.8 → BLOCKER) | Opus: deletions verified safe; no BLOCKER. The reported finding targets a DELETED file — nothing real. **FP** (strong) |
| pr47 | pr:47 | CJ #47 button style | Approved | 0 | manual triage: correct. **TN** (strong) |
| pr43 | pr:43 | CJ #43 import-chunking | Changes requested | 9 (7 MAJOR, 2 MINOR) | deep review was still pending at run time. **pending** |
| pr46 | pr:46 | CJ #46 dev-model-cache | **Approved** | 2 (devModel.ts:1 sev 1.51; mockLlmProvider.ts:11 sev 1.31, is_real 0.64) | CodeRabbit found 4 valid bugs incl. mockLlmProvider.ts:11 shadowing. The tool reported the right hunk at the right line — but Approved. **FN** (strong) |
| pr46-fix-delta | range 8e6f440..f8c6594 | fix diff | Changes requested | 2 (dev-model.js:114 sev 1.81; mockLlmProvider.ts:8 sev 2.17) | fix diff was correct. **FP** (moderate) |
| pr47-rebased | range origin/main..HEAD | CJ #47 after rebase | Approved | 0 | **TN** (strong) |

## Headline numbers (small n, honest)

- On runs with strong ground truth: TP 0, FP 1 (#45) + 1 likely (#46-fix-delta),
  FN 1 (#46), TN 2 (#47 ×2). #43 ground truth pending. Verdict-level accuracy
  on the clear cases is **2 of 5** — the two TNs; worse than the fixture
  benchmarks suggested.
- Finding-level: the model *did* notice the real mockLlmProvider defect
  (is_real 0.64, anchored at the correct line 11) — the finding was reported;
  the **verdict policy** is what ignored it (F2).
- Latency healthy (~120–200 ms/call); no fail-opens; no transport failures.

## Findings (evidence → code location; all line refs verified against main)

**Citation pinning:** line references below were verified against
`system_one_reviewer.py` at **`e6b7aef`** (the v0.2 HEAD the evals ran
against). The v0.3 branch inserts ~100 lines, so on-branch numbers drift;
pin with `git show e6b7aef:system_one_reviewer.py`.

**F1 — Deletion-only clusters get inflated severity and can unilaterally flip
a verdict to "Changes requested" (#45).**
On pr45 (mode pr:45, merge-base diff — the deletions are genuinely the PR's
content, not a stale-base artifact), all six `.tsx` whole-file-deletion
clusters scored severity 2.73–2.82 with high confidence (0.73–0.82) — every
one BLOCKER-level (≥2.5) — while is_real stayed 0.37–0.65. (The run's other
deletion, animated-icon.module.css, scored 1.90/MAJOR at confidence 0.00.)
Five were held back
only by the is_real < 0.50 gate; the one that crossed (animated-icon.web.tsx:1,
sev 2.8, is_real 0.65) became a BLOCKER and flipped the verdict alone
(`compose()`, system_one_reviewer.py:771-773: any blocker ⇒ "Changes requested").
There is no surviving code in a deletion cluster to be "buggy", yet
`hunk_state` (:627-645) sends the same three questions over an empty
`code_after_change` (whole-file deletion) and the model answers with maximal
severity. Proposal: carry a `change_type` (deletion-only / whole-file-deleted /
normal) into the hunk dict — detection: no `+` entries in the run; the
`deleted file mode` / `+++ /dev/null` headers (:397-405) distinguish whole-file
deletions — and adapt the question for deletion-only clusters ("was this
removal safe?"). Separately consider requiring corroboration before a
lone deletion-cluster finding flips a verdict. Note (docstring bug):
package_hunks' docstring (:356-357) claims "a deletion-only cluster never
collapses to line 1", but for whole-file deletions `@@ -1,N +0,0 @@` yields
anchor 1 — pr45's findings are all anchored at line 1. Fix the docstring.

**F2 — Real defects get reported and then ignored; the one lone reported MAJOR
in #46 is unvetted and jitter-zone (#46).**
What happened on pr46: the confirmed defect (mockLlmProvider.ts:11, exact hunk
CodeRabbit confirmed) was reported at is_real 0.64 — but severity 1.31
(MINOR, sev_level 1), and a MINOR can never drive a verdict (:773). The run's
only lone reported MAJOR was `devModel.ts:1` (sev 1.51 → sev_level 2,
is_real 0.52) — unvetted against ground truth AND inside the jitter zone
(|0.52−0.50| < 0.03). So a "lone reported MAJOR with is_real ≥ cutoff ⇒
Changes requested" rule can only flip #46 through a jitter-zone score of an
unchecked finding — it could "fix" #46 for the wrong reason. The deeper
pattern: the model under-rated the confirmed defect's severity (1.31), so
this is a **severity-calibration problem as much as a verdict-rule one**.
The contrast pair pr46 (FN, 0.64) vs pr45 (FP, 0.65) shows is_real alone
cannot separate them — but severity already does (1 vs 3); the separable
axis for pr45-type FPs is cluster type (deletion), handled by F1. Proposal:
first land F1, then use scripts/sweep-thresholds.py over fixture + field
ledgers to test whether any (severity, is_real) joint rule separates the
known FP/FN set without breaking the clean negatives — no knob flips before
that sweep.

**F3 — Severity confidence is sometimes exactly 0.0 and nothing uses it.**
`judge()` (:688) stores `sev.get("confidence")` — the severity Score's
confidence. Missing key ⇒ None (correct); but the provider also returns
literal 0.0 on judged findings (pr45's css deletion, several pr43 findings,
both ct-range runs, and pr46 — on reported and unreported findings alike). `compose()` never reads confidence;
`render()` never shows it. Two questions for v0.3: (a) what does a 0.0
severity-confidence mean from Jev — retry-worthy or ignorable? (needs Jev's
documented semantics — open question); (b) should low-confidence findings be
gated or annotated? At minimum, document the field.

**F4 — `needs_human_review` fires on everything and gates nothing.**
Base rate across ALL 33 ledger runs with a pr_level (fixtures and field
runs): 0.69–0.96 — min v02-r2-negative-3 0.69 (benign fixture), max
v02-baseline-2 0.96 (positive fixture); negatives overall 0.69–0.90,
positives 0.92–0.96, field runs 0.78–0.95. A 0.9 gate would fire on benign
fixtures. The signal is uncalibrated noise — yet it renders as "PR-level
risk … needs_human_review=…" next to an Approved verdict (contradictory on
pr46: risk 2.1 + Approved). Decision needed: recalibrate the PR-level
prompt, or cut the render line. Either way keep the closed-set last line
intact (:899-904).

**F5 — `--range` did a two-dot diff while the docstring claimed merge-base
(FIXED in v0.3).**
`resolve_diff()` (:329) ran `git diff A..B` (two-dot, no merge-base) while the
module docstring (:9) claimed it "pre-computes merge-base"; only `--pr` used
`...` (:339). Two-dot ranges against a stale base show post-branch main-side
changes as deletions — a false-FP machine in principle. (The pr46-fix-delta
FP is **not** an instance: verified via `git merge-base --is-ancestor
8e6f440 f8c6594` — ancestor, so two-dot and merge-base agree there, and both
reported findings sit in files the fix itself touched.) v0.3 makes
`--range` use `A...B` (merge-base), matching the docstring and user
expectation; fixtures re-run on the branch (see README).

**F6 — README still leads with the old name.**
`README.md:1` is `# jev-review`; Jev-as-actor prose throughout (:24-31).
D4 rebrand decision: the category term is "system one model"; Jev/Laya are
named only as example providers. Keep the path-continuity section (:75-79)
and the `~/.config/jev-review/.env` / `JEV_REVIEW_METRICS` names.

**F7 — Ledger hygiene: empty labels and `repo: "."`.**
Field runs logged empty labels and `repo: "."` (`os.path.basename`
(:977) returns "." for "." and "" for trailing slashes). Proposal: default
label = mode when unset; store `basename(realpath(repo))`.

## Candidate v0.3 changes

1. F1: change_type detection + deletion-adapted questions + docstring fix.
2. F2: after F1 lands, sweep a (severity, is_real) joint verdict rule over
   fixture + field ledgers (scripts/sweep-thresholds.py); no knob flips
   before the sweep separates the known FP/FN set.
3. F3: document severity-confidence semantics; decide on gating (needs Jev docs).
4. F4: recalibrate or cut needs_human_review render.
5. F5: `--range` → merge-base (`A...B`).
6. F6: README/docs rebrand; keep path-continuity exceptions.
7. F7: label/repo defaults in the ledger.

## Known constraints (from v0.2 decisions)

- Closed-set last line {Approved, Changes requested, Unavailable, Incomplete}
  is a published contract — new verdict wording must respect it or be a
  documented breaking change.
- Threshold 0.50 is the benchmark-of-record plateau; any compose change must
  re-run the fixture sweep to re-verify.
- Keep env/path continuity (JEV_REVIEW_METRICS, ~/.config/jev-review/.env).
- n=9 field runs with 4 strong-ground-truth verdicts (plus pr46-fix-delta at
  moderate confidence) — directional evidence, not statistics. The 5-plant
  fixture caveat applies here too.

## Appendix — the 9 field-run ledger records (verbatim fields)

Fields per record: label | mode | verdict | fail_open | avg_call_ms |
pr_level(risk, nhr) | judged(file:line sev is_real conf reported).
(Full JSON in the metrics file; trimmed only for whitespace.)

```
(empty) | staged | Approved | false | null | 0.50, 0.84 | (none judged)
(empty) | range:main..vault-ingest-policy | Approved | false | 158.2 | 2.33, 0.91 |
  okf/write.rs:1362 0.33 0.44 0.67 no | walk_vault.rs:716 0.21 0.33 0.79 no |
  chunker/mod.rs:175 0.77 0.50 0.23 no | okf/write.rs:306 0.63 0.50 0.37 no |
  okf/write.rs:265 0.25 0.31 0.75 no | chunker/mod.rs:153 0.91 0.55 0.09 no |
  okf/mod.rs:79 0.56 0.44 0.44 no | okf/write.rs:36 0.42 0.39 0.58 no |
  walk_vault.rs:48 0.23 0.37 0.77 no | okf/write.rs:32 0.67 0.31 0.33 no |
  safe_path.rs:36 0.15 0.25 0.85 no | safe_path.rs:47 1.23 0.47 0.00 no |
  chunker/mod.rs:170 1.02 0.68 0.00 YES | vault/mod.rs:7 1.24 0.40 0.00 no |
  chunker/mod.rs:168 1.13 0.56 0.00 YES
(empty) | range:main..origin/vault-ingest-policy | Approved | false | 145.2 | 2.51, 0.93 |
  (31 judged; reported:) config/mod.rs:737 1.12 0.52 0.00 YES |
  librarian/mod.rs:373 1.19 0.51 0.00 YES | chunker/mod.rs:168 1.06 0.55 0.00 YES |
  (also notable: safe_path.rs:47 1.26 0.45 0.00 no; librarian/mod.rs:394 1.64 0.49 0.28 no)
pr45-rebased | pr:45 | Changes requested | false | 143.8 | 2.70, 0.93 |
  app-tabs.web.tsx:1 2.81 0.42 0.81 no | animated-icon.web.tsx:1 2.80 0.65 0.80 YES |
  ui/collapsible.tsx:1 2.82 0.43 0.82 no | web-badge.tsx:1 2.77 0.42 0.77 no |
  hint-row.tsx:1 2.73 0.37 0.73 no | external-link.tsx:1 2.78 0.44 0.78 no |
  animated-icon.module.css:1 1.90 0.38 0.00 no
pr47 | pr:47 | Approved | false | 196.8 | 0.81, 0.78 |
  buttonBorderStyle.test.tsx:1 0.54 0.37 0.46 no | button.tsx:129 0.08 0.66 0.92 no
pr43 | pr:43 | Changes requested | false | 161.0 | 2.60, 0.95 |
  (31 judged; the 9 reported:) import.tsx:33 1.60 0.60 0.22 | import.tsx:73 2.09 0.59 0.43 |
  chunkedImportDump.ts:72 1.39 0.57 0.13 | walkDirectory.ts:51 1.62 0.52 0.42 |
  import.tsx:82 2.04 0.70 0.79 | import.tsx:118 1.49 0.55 0.25 |
  walkDirectory.ts:43 2.10 0.76 0.68 | walkDirectory.ts:48 2.02 0.66 0.58 |
  import.tsx:109 1.62 0.56 0.52
  (notable unreported: chunkedImportDump.ts:9 1.60 0.43 0.00; :46 1.60 0.49 0.00;
   chunkedImportDump.ts:61 1.05 0.44 0.00; import.tsx:114 0.02 0.50 0.98)
pr46 | pr:46 | Approved | false | 159.3 | 2.10, 0.92 |
  devModel.ts:1 1.51 0.52 0.18 YES | devModel.test.ts:1 0.61 0.32 0.39 no |
  mockLlmProvider.ts:11 1.31 0.64 0.18 YES | _layout.tsx:36 1.16 0.47 0.00 no |
  mockLlmProvider.test.ts:27 0.81 0.27 0.19 no | package.json:82 0.04 0.17 0.96 no |
  _layout.tsx:14 0.49 0.30 0.51 no | useNightShiftGates.ts:20 1.05 0.44 0.00 no |
  useNightShiftGates.ts:37 1.06 0.48 0.00 no | useNightShiftGates.ts:4 0.68 0.29 0.32 no
pr46-fix-delta | range:8e6f440..f8c6594 | Changes requested | false | 144.2 | 2.17, 0.93 |
  _layout.tsx:49 0.26 0.50 0.74 no | mockLlmProvider.test.ts:41 0.73 0.30 0.27 no |
  dev-model.js:60 0.16 0.57 0.84 no | dev-model.js:114 1.81 0.60 0.61 YES |
  devModel.test.ts:49 0.50 0.34 0.50 no | mockLlmProvider.ts:10 0.11 0.36 0.89 no |
  mockLlmProvider.ts:27 1.39 0.40 0.09 no | mockLlmProvider.ts:8 2.17 0.63 0.59 YES
pr47-rebased | range:origin/main..HEAD | Approved | false | 179.8 | 0.93, 0.82 |
  buttonBorderStyle.test.tsx:1 0.56 0.35 0.44 no | button.tsx:129 0.07 0.66 0.93 no
```
